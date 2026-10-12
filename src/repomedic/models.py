"""Immutable inputs and evidence-bearing results shared by all components."""

from dataclasses import dataclass
from typing import Literal

Severity = Literal["low", "medium", "high"]
Assessment = Literal["confirmed", "risk"]
LineKind = Literal["added", "removed", "context"]


@dataclass(frozen=True)
class DiffLine:
    kind: LineKind
    content: str
    old_line: int | None
    new_line: int | None


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[DiffLine, ...]


@dataclass(frozen=True)
class ChangedFile:
    old_path: str | None
    new_path: str | None
    hunks: tuple[Hunk, ...]
    binary: bool = False
    new_mode: str | None = None

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or "<unknown>"

    @property
    def added_lines(self) -> tuple[DiffLine, ...]:
        return tuple(line for hunk in self.hunks for line in hunk.lines if line.kind == "added")

    @property
    def removed_lines(self) -> tuple[DiffLine, ...]:
        return tuple(line for hunk in self.hunks for line in hunk.lines if line.kind == "removed")


@dataclass(frozen=True)
class Finding:
    rule_id: str
    file: str
    line: int | None
    severity: Severity
    assessment: Assessment
    explanation: str
    evidence: str


@dataclass(frozen=True)
class AnalysisReport:
    files: tuple[ChangedFile, ...]
    findings: tuple[Finding, ...]
    notices: tuple[str, ...]
    checks_run: tuple[str, ...]
