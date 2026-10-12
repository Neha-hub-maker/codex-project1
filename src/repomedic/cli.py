"""Local CLI with separate operational errors and optional finding thresholds."""

import argparse
import os
import sys
from pathlib import Path

from .engine import analyze
from .parser import DiffParseError
from .reports import render_json, render_markdown

MAX_DIFF_BYTES = 10 * 1024 * 1024
_SEVERITY = {"low": 1, "medium": 2, "high": 3}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze a local unified diff without executing it."
    )
    parser.add_argument("diff", nargs="?", default="-", help="UTF-8 diff file, or - for stdin")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path, help="Write report here instead of stdout")
    parser.add_argument(
        "--fail-on", choices=tuple(_SEVERITY), help="Exit 1 for findings at this severity or higher"
    )
    args = parser.parse_args(argv)
    try:
        if args.diff != "-" and args.output:
            input_path = Path(args.diff)
            if args.output.exists() and input_path.samefile(args.output):
                raise ValueError("output must not overwrite the input diff")
        if args.diff == "-":
            data = sys.stdin.buffer.read(MAX_DIFF_BYTES + 1)
        else:
            with Path(args.diff).open("rb") as stream:
                data = stream.read(MAX_DIFF_BYTES + 1)
        if len(data) > MAX_DIFF_BYTES:
            raise ValueError("diff exceeds the 10 MiB input limit")
        report = analyze(data.decode("utf-8"))
        rendered = render_json(report) if args.format == "json" else render_markdown(report)
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
            sys.stdout.flush()
    except BrokenPipeError:
        # Prevent the interpreter's final flush from turning an I/O error into exit 120.
        with open(os.devnull, "w") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
        print("repomedic: output pipe closed", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, DiffParseError, ValueError, RecursionError) as exc:
        print(f"repomedic: {exc}", file=sys.stderr)
        return 2
    if args.fail_on and any(
        _SEVERITY[finding.severity] >= _SEVERITY[args.fail_on] for finding in report.findings
    ):
        return 1
    return 0
