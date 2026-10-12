import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*args, input_data=None):
    return subprocess.run(
        [sys.executable, "-m", "repomedic", *map(str, args)],
        input=input_data,
        capture_output=True,
        check=False,
    )


def test_file_input_json_and_module_entrypoint():
    result = run_cli(FIXTURES / "risky.diff")
    assert result.returncode == 0
    assert result.stderr == b""
    assert json.loads(result.stdout)["summary"]["findings"] == 5


def test_stdin_markdown_and_report_file(tmp_path):
    output = tmp_path / "report.md"
    result = run_cli(
        "-",
        "--format",
        "markdown",
        "--output",
        output,
        input_data=(FIXTURES / "risky.diff").read_bytes(),
    )
    assert result.returncode == 0
    assert result.stdout == result.stderr == b""
    assert output.read_text().startswith("# RepoMedic report\n")


@pytest.mark.parametrize("severity", ["low", "medium", "high"])
def test_threshold_returns_one_but_still_produces_report(severity):
    result = run_cli(FIXTURES / "risky.diff", "--fail-on", severity)
    assert result.returncode == 1
    assert json.loads(result.stdout)["summary"]["confirmed"] == 1


def test_threshold_can_include_risk_without_confirmed_defect():
    diff = b"--- /dev/null\n+++ x.py\n@@ -0,0 +1 @@\n+eval(value)\n"
    assert run_cli("--fail-on", "medium", input_data=diff).returncode == 1
    assert run_cli("--fail-on", "high", input_data=diff).returncode == 0


def test_clean_input_and_empty_stdin():
    assert run_cli(FIXTURES / "normal.diff", "--fail-on", "low").returncode == 0
    result = run_cli(input_data=b"")
    assert result.returncode == 0
    assert json.loads(result.stdout)["summary"]["files_changed"] == 0


def test_malformed_input_no_partial_report_or_overwritten_output(tmp_path):
    output = tmp_path / "existing.json"
    output.write_text("preserve me")
    result = run_cli(FIXTURES / "malformed.diff", "--output", output)
    assert result.returncode == 2
    assert result.stdout == b""
    assert b"truncated hunk" in result.stderr
    assert b"Traceback" not in result.stderr
    assert output.read_text() == "preserve me"


@pytest.mark.parametrize("payload", [b"\xff", b"unexpected text\n"])
def test_invalid_encoding_and_format(payload):
    result = run_cli(input_data=payload)
    assert result.returncode == 2
    assert result.stdout == b""
    assert b"repomedic:" in result.stderr


def test_missing_input_and_unwritable_output(tmp_path):
    assert run_cli(tmp_path / "missing.diff").returncode == 2
    assert run_cli(FIXTURES / "normal.diff", "--output", tmp_path).returncode == 2


def test_refuses_to_overwrite_input(tmp_path):
    diff = tmp_path / "change.diff"
    original = (FIXTURES / "normal.diff").read_bytes()
    diff.write_bytes(original)
    result = run_cli(diff, "--output", diff)
    assert result.returncode == 2
    assert b"must not overwrite" in result.stderr
    assert diff.read_bytes() == original


def test_rejects_oversize_input(tmp_path):
    path = tmp_path / "huge.diff"
    path.write_bytes(b"x" * (10 * 1024 * 1024 + 1))
    result = run_cli(path)
    assert result.returncode == 2
    assert b"10 MiB" in result.stderr
    assert result.stdout == b""


def test_invalid_arguments():
    result = run_cli("--format", "html")
    assert result.returncode == 2
    assert b"invalid choice" in result.stderr


@pytest.mark.parametrize("alias_kind", ["symlink", "hardlink"])
def test_output_alias_cannot_overwrite_input(tmp_path, alias_kind):
    source = tmp_path / "input.diff"
    source.write_bytes((FIXTURES / "normal.diff").read_bytes())
    output = tmp_path / "report.json"
    if alias_kind == "symlink":
        output.symlink_to(source)
    else:
        output.hardlink_to(source)
    before = source.read_bytes()
    result = run_cli(source, "--output", output)
    assert result.returncode == 2
    assert b"must not overwrite" in result.stderr
    assert source.read_bytes() == before


def test_closed_stdout_is_a_controlled_io_error():
    with subprocess.Popen(
        [sys.executable, "-m", "repomedic"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as process:
        process.stdout.close()
        assert process.wait(timeout=10) == 2
        errors = process.stderr.read()
    assert b"output pipe closed" in errors
    assert b"Exception ignored" not in errors
    assert b"Traceback" not in errors


def test_unreadable_input_reports_permission_error(monkeypatch, capsys, tmp_path):
    from repomedic.cli import main

    def denied(*args, **kwargs):
        raise PermissionError("permission denied by test filesystem")

    monkeypatch.setattr(Path, "open", denied)
    assert main([str(tmp_path / "restricted.diff")]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "permission denied" in output.err


def test_symlink_cycle_input_is_a_controlled_io_error(tmp_path):
    source = tmp_path / "first.diff"
    other = tmp_path / "second.diff"
    source.symlink_to(other)
    other.symlink_to(source)
    result = run_cli(source, "--output", tmp_path / "report.json")
    assert result.returncode == 2
    assert result.stdout == b""
    assert b"Traceback" not in result.stderr
