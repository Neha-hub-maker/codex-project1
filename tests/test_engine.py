import pytest

from repomedic import analyze
from repomedic.checks import CheckResult
from repomedic.models import Finding


def test_realistic_risky_fixture_has_evidence(fixture_diff):
    report = analyze(fixture_diff("risky.diff"))
    assert len(report.findings) == 5
    syntax = next(f for f in report.findings if f.rule_id == "python-syntax")
    assert (syntax.file, syntax.line, syntax.severity, syntax.assessment) == (
        "src/calculator.py",
        1,
        "high",
        "confirmed",
    )
    assert syntax.evidence == "def divide(a, b)"
    dynamic = next(f for f in report.findings if f.rule_id == "python-dynamic-execution")
    assert (dynamic.file, dynamic.line, dynamic.assessment) == ("src/expression.py", 3, "risk")
    assert "eval(expression)" in dynamic.evidence
    assert "not a proven vulnerability" in dynamic.explanation
    assert all(f.assessment == "risk" for f in report.findings if f.rule_id == "conflict-marker")


def test_clean_diff_does_not_invent_findings(fixture_diff):
    report = analyze(fixture_diff("normal.diff"))
    assert report.findings == ()
    assert len(report.notices) == 1
    assert "src/math_utils.py" in report.notices[0]
    assert "skipped" in report.notices[0]


def test_added_whitespace_only_and_line_numbers():
    diff = "--- x.txt\n+++ x.txt\n@@ -1,2 +1,2 @@\n-old  \n+new\n context  \n"
    assert analyze(diff).findings == ()
    report = analyze("--- x.txt\n+++ x.txt\n@@ -1 +1 @@\n-old\n+new \t\n")
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert (finding.rule_id, finding.line, finding.assessment) == (
        "trailing-whitespace",
        1,
        "confirmed",
    )
    assert finding.evidence == repr("new \t")


def test_binary_is_explicitly_skipped(fixture_diff):
    report = analyze(fixture_diff("operations.diff"))
    assert report.findings == ()
    assert report.notices == (
        "icon.png: binary content skipped; only the change notice is available.",
    )


def test_python_string_comments_and_attributes_are_not_direct_calls(new_python_diff):
    source = '# eval(user_input)\ntext = "exec(user_input)"\nobj.eval(value)\n'
    assert analyze(new_python_diff(source)).findings == ()


def test_both_dynamic_calls_detected_with_multiline_arguments(new_python_diff):
    source = "eval(\n    expression\n)\nexec(program)\n"
    findings = analyze(new_python_diff(source)).findings
    assert [finding.line for finding in findings] == [1, 4]
    assert all(finding.assessment == "risk" for finding in findings)


def test_compile_detects_context_sensitive_syntax_error(new_python_diff):
    finding = analyze(new_python_diff("return 1\n")).findings[0]
    assert finding.rule_id == "python-syntax"
    assert "outside function" in finding.explanation


def test_analyzed_code_is_never_executed(new_python_diff, tmp_path):
    marker = tmp_path / "should-not-exist"
    source = (
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
        "raise Exception()\n"
    )
    report = analyze(new_python_diff(source, "../../untrusted.py"))
    assert report.findings == ()
    assert not marker.exists()


def test_fragment_of_new_file_is_not_treated_as_complete():
    diff = "--- /dev/null\n+++ fragment.py\n@@ -0,0 +20 @@\n+return 1\n"
    report = analyze(diff)
    assert report.findings == ()
    assert "complete newly added file" in report.notices[0]


def test_modified_fragment_is_not_compiled():
    diff = "--- old.py\n+++ old.py\n@@ -10 +10 @@\n-    return 1\n+    return 2\n"
    report = analyze(diff)
    assert report.findings == ()
    assert report.notices


def test_checks_are_replaceable_not_hard_coded(new_python_diff):
    class CustomCheck:
        name = "custom"

        def run(self, file):
            return CheckResult(
                (Finding("custom", file.path, None, "low", "risk", "Custom policy", file.path),)
            )

    report = analyze(new_python_diff("broken syntax here\n"), checks=[CustomCheck()])
    assert report.checks_run == ("custom",)
    assert [finding.rule_id for finding in report.findings] == ["custom"]


def test_empty_analysis_and_explicit_no_checks():
    report = analyze("", checks=[])
    assert report.files == report.findings == report.notices == report.checks_run == ()


def test_result_is_repeatable(fixture_diff):
    diff = fixture_diff("risky.diff")
    assert analyze(diff) == analyze(diff)


def test_intentional_markdown_whitespace_is_observed_without_claiming_a_defect():
    diff = "--- /dev/null\n+++ README.md\n@@ -0,0 +1 @@\n+Intentional hard break  \n"
    finding = analyze(diff).findings[0]
    assert finding.assessment == "confirmed"
    assert finding.evidence == repr("Intentional hard break  ")
    assert "intentional" in finding.explanation
    assert "defect" not in finding.explanation


def test_renamed_file_findings_use_new_path_and_new_line():
    diff = (
        "diff --git a/old name.txt b/new name.txt\n"
        "similarity index 90%\nrename from old name.txt\nrename to new name.txt\n"
        "--- a/old name.txt\n+++ b/new name.txt\n@@ -3 +3,2 @@\n-old\n+new\n+trailing  \n"
    )
    finding = analyze(diff).findings[0]
    assert (finding.file, finding.line) == ("new name.txt", 4)


@pytest.mark.parametrize(
    "mode,source", [("120000", "../target.py"), ("160000", "Subproject commit abc")]
)
def test_nonregular_python_paths_are_not_confirmed_syntax_defects(mode, source):
    diff = (
        f"diff --git a/path.py b/path.py\nnew file mode {mode}\n"
        f"--- /dev/null\n+++ b/path.py\n@@ -0,0 +1 @@\n+{source}\n"
    )
    report = analyze(diff)
    assert report.files[0].new_mode == mode
    assert report.findings == ()
    assert "not a regular source file" in report.notices[0]
