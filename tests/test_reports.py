import json

from repomedic import analyze
from repomedic.models import AnalysisReport, Finding
from repomedic.reports import render_json, render_markdown


def test_json_schema_counts_locations_and_evidence(fixture_diff):
    report = analyze(fixture_diff("risky.diff"))
    data = json.loads(render_json(report))
    assert data["schema_version"] == 1
    assert data["summary"] == {
        "files_changed": 3,
        "lines_added": 10,
        "lines_removed": 1,
        "findings": 5,
        "confirmed": 1,
        "risks": 4,
    }
    assert data["files"][0]["hunks"][0]["lines"][0] == {
        "kind": "added",
        "content": "def divide(a, b)",
        "old_line": None,
        "new_line": 1,
    }
    for finding in data["findings"]:
        assert set(finding) == {
            "rule_id",
            "file",
            "line",
            "severity",
            "assessment",
            "explanation",
            "evidence",
        }
        assert finding["evidence"]


def test_markdown_contains_same_findings_and_notices(fixture_diff):
    report = analyze(fixture_diff("risky.diff"))
    markdown = render_markdown(report)
    assert "1 confirmed findings; 4 risk indicators." in markdown
    assert "src/calculator\\.py:1" in markdown
    assert "def divide(a, b)" in markdown
    assert "(confirmed)" in markdown and "(risk)" in markdown


def test_empty_report_does_not_claim_correctness():
    markdown = render_markdown(analyze(""))
    assert "No changes supplied." in markdown
    assert "does not prove correctness" in markdown
    assert json.loads(render_json(analyze("")))["findings"] == []


def test_markdown_escapes_untrusted_text_and_evidence_fences():
    finding = Finding(
        "custom",
        "[click](https://example.com)<script>.py",
        None,
        "medium",
        "risk",
        "<script>alert(1)</script> [link](https://example.com)",
        "```\n<script>alert(1)</script>\n```",
    )
    markdown = render_markdown(AnalysisReport((), (finding,), (), ()))
    assert "&lt;script&gt;" in markdown
    assert "\\[click\\]" in markdown
    assert "````text\n```\n<script>" in markdown
    assert markdown.endswith("```\n````\n")


def test_notices_and_binary_content_are_visible(fixture_diff):
    markdown = render_markdown(analyze(fixture_diff("operations.diff")))
    assert "## Analysis notices" in markdown
    assert "binary content skipped" in markdown


def test_control_and_bidi_characters_are_visible_in_markdown_and_preserved_in_json():
    finding = Finding(
        "custom",
        "tab\tfile\x1b[31m\u202e\ud800.py",
        1,
        "low",
        "risk",
        "inspect\x07",
        "first\x1b[31m\u202e\n\tsecond",
    )
    report = AnalysisReport((), (finding,), (), ())
    markdown = render_markdown(report)
    assert all(char not in markdown for char in ("\x1b", "\x07", "\u202e", "\ud800"))
    assert "\\x1b" in markdown and "\\u202e" in markdown
    assert "\n\tsecond\n" in markdown
    encoded = render_json(report)
    assert "\x1b" not in encoded
    assert json.loads(encoded)["findings"][0]["file"] == finding.file
    assert json.loads(encoded)["findings"][0]["evidence"] == finding.evidence
