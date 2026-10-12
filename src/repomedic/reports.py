"""Stable JSON and Markdown representations of the same analysis result."""

import html
import json
import re
import unicodedata
from dataclasses import asdict

from .models import AnalysisReport


def report_dict(report: AnalysisReport) -> dict:
    return {
        "schema_version": 1,
        "summary": {
            "files_changed": len(report.files),
            "lines_added": sum(len(file.added_lines) for file in report.files),
            "lines_removed": sum(len(file.removed_lines) for file in report.files),
            "findings": len(report.findings),
            "confirmed": sum(finding.assessment == "confirmed" for finding in report.findings),
            "risks": sum(finding.assessment == "risk" for finding in report.findings),
        },
        "checks_run": list(report.checks_run),
        "files": [asdict(file) for file in report.files],
        "findings": [asdict(finding) for finding in report.findings],
        "notices": list(report.notices),
    }


def render_json(report: AnalysisReport) -> str:
    return json.dumps(report_dict(report), indent=2, ensure_ascii=True) + "\n"


def _visible(value: str, *, code: bool = False) -> str:
    """Keep control/bidi characters from changing terminal or report presentation."""
    return "".join(
        char
        if (code and char in "\n\t") or unicodedata.category(char) not in {"Cc", "Cf", "Cs"}
        else ascii(char)[1:-1]
        for char in value
    )


def _escape(value: str) -> str:
    value = _visible(value)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~\-])", r"\\\1", html.escape(value, quote=False))


def _code(value: str) -> str:
    value = _visible(value, code=True)
    longest = max((len(match[0]) for match in re.finditer(r"`+", value)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{value}\n{fence}"


def render_markdown(report: AnalysisReport) -> str:
    summary = report_dict(report)["summary"]
    lines = [
        "# RepoMedic report",
        "",
        f"{summary['files_changed']} files changed; {summary['lines_added']} lines added; "
        f"{summary['lines_removed']} lines removed.",
        f"{summary['confirmed']} confirmed findings; {summary['risks']} risk indicators.",
        "",
        "Checks: " + ", ".join(_escape(name) for name in report.checks_run),
        "",
        "## Changed files",
        "",
    ]
    for file in report.files:
        lines.append(
            f"- {_escape(file.path)}: +{len(file.added_lines)} / -{len(file.removed_lines)}"
            + (" (binary content skipped)" if file.binary else "")
        )
    if not report.files:
        lines.append("No changes supplied.")
    lines.extend(["", "## Findings", ""])
    for finding in report.findings:
        location = finding.file + (f":{finding.line}" if finding.line is not None else "")
        lines.extend(
            [
                f"### {_escape(finding.severity.upper())} — {_escape(finding.rule_id)} "
                f"({_escape(finding.assessment)})",
                "",
                f"Location: {_escape(location)}",
                "",
                _escape(finding.explanation),
                "",
                "Evidence:",
                "",
                _code(finding.evidence),
                "",
            ]
        )
    if not report.findings:
        lines.extend(["No findings from the selected checks; this does not prove correctness.", ""])
    if report.notices:
        lines.extend(["## Analysis notices", ""])
        lines.extend(f"- {_escape(notice)}" for notice in report.notices)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
