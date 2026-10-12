"""Compose the parser and replaceable deterministic checks."""

from collections.abc import Iterable

from .checks import DEFAULT_CHECKS, Check
from .models import AnalysisReport
from .parser import parse_diff


def analyze(text: str, *, checks: Iterable[Check] = DEFAULT_CHECKS) -> AnalysisReport:
    files = parse_diff(text)
    selected_checks = tuple(checks)
    findings = []
    notices = []
    for file in files:
        if file.binary:
            notices.append(
                f"{file.path}: binary content skipped; only the change notice is available."
            )
            continue
        for check in selected_checks:
            result = check.run(file)
            findings.extend(result.findings)
            notices.extend(result.notices)
    findings.sort(key=lambda finding: (finding.file, finding.line or 0, finding.rule_id))
    return AnalysisReport(
        files, tuple(findings), tuple(notices), tuple(check.name for check in selected_checks)
    )
