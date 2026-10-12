"""Small checks with explicit evidence and applicability; no code is executed."""

import ast
import re
from dataclasses import dataclass
from typing import Protocol

from .models import ChangedFile, Finding


@dataclass(frozen=True)
class CheckResult:
    findings: tuple[Finding, ...] = ()
    notices: tuple[str, ...] = ()


class Check(Protocol):
    name: str

    def run(self, file: ChangedFile) -> CheckResult: ...


class TrailingWhitespaceCheck:
    name = "trailing-whitespace"

    def run(self, file: ChangedFile) -> CheckResult:
        return CheckResult(
            tuple(
                Finding(
                    self.name,
                    file.path,
                    line.new_line,
                    "low",
                    "confirmed",
                    "Added line ends with spaces or tabs. Verify whether they are intentional "
                    "or violate the project's formatting rules.",
                    repr(line.content),
                )
                for line in file.added_lines
                if line.content.endswith((" ", "\t"))
            )
        )


class ConflictMarkerCheck:
    name = "conflict-marker"
    pattern = re.compile(r"^(?:<{7}(?: .*)?|={7}|>{7}(?: .*)?|\|{7}(?: .*)?)$")

    def run(self, file: ChangedFile) -> CheckResult:
        return CheckResult(
            tuple(
                Finding(
                    self.name,
                    file.path,
                    line.new_line,
                    "medium",
                    "risk",
                    "Added line resembles a Git conflict marker. It may instead be intentional "
                    "text; inspect the surrounding file before treating it as an unresolved merge.",
                    line.content,
                )
                for line in file.added_lines
                if self.pattern.fullmatch(line.content)
            )
        )


def _complete_new_source(file: ChangedFile) -> str | None:
    """A diff can prove a complete snapshot only for a contiguous file addition."""
    if file.old_path is not None or file.new_path is None or not file.hunks:
        return None
    expected = 1
    source: list[str] = []
    for hunk in file.hunks:
        if hunk.old_count != 0 or hunk.old_start != 0 or hunk.new_start != expected:
            return None
        for line in hunk.lines:
            if line.kind != "added":
                return None
            source.append(line.content)
        expected += hunk.new_count
    return "\n".join(source) + "\n"


class PythonSourceCheck:
    name = "python-source"

    def run(self, file: ChangedFile) -> CheckResult:
        if file.new_path is None or not file.new_path.endswith(".py"):
            return CheckResult()
        if file.new_mode is not None and file.new_mode not in {"100644", "100755"}:
            return CheckResult(
                notices=(
                    f"{file.path}: Python syntax/call analysis skipped; "
                    f"Git mode {file.new_mode} is not a regular source file.",
                )
            )
        source = _complete_new_source(file)
        if source is None:
            return CheckResult(
                notices=(
                    f"{file.path}: Python syntax/call analysis skipped; "
                    "a complete newly added file is required.",
                )
            )
        try:
            # Compile validates context-sensitive errors (e.g. return outside a function).
            # The resulting code object is never executed or imported.
            compile(source, file.path, "exec", dont_inherit=True)
            tree = ast.parse(source, filename=file.path)
        except SyntaxError as exc:
            return CheckResult(
                findings=(
                    Finding(
                        "python-syntax",
                        file.path,
                        exc.lineno,
                        "high",
                        "confirmed",
                        "Complete added Python file does not compile on this interpreter: "
                        f"{exc.msg}.",
                        (exc.text or "").rstrip("\n") or exc.msg,
                    ),
                )
            )
        findings = []
        source_lines = source.split("\n")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"eval", "exec"}
            ):
                findings.append(
                    Finding(
                        "python-dynamic-execution",
                        file.path,
                        node.lineno,
                        "medium",
                        "risk",
                        f"Call to {node.func.id} may execute untrusted Python. This is a risk "
                        "indicator, not a proven vulnerability: name binding and input trust "
                        "are not established by this check.",
                        source_lines[node.lineno - 1],
                    )
                )
        return CheckResult(tuple(findings))


DEFAULT_CHECKS: tuple[Check, ...] = (
    TrailingWhitespaceCheck(),
    ConflictMarkerCheck(),
    PythonSourceCheck(),
)
