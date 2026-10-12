"""Compatibility tests use real Git output; no commits, hooks, or network access."""

import subprocess

import pytest

from repomedic import DiffParseError, analyze


@pytest.mark.parametrize("name", ["simple.py", "file with spaces.py", "café.py", "tab\tfile.py"])
def test_real_git_new_file_diff(tmp_path, name):
    path = tmp_path / name
    path.write_text("def broken(a, b)\n    return a / b\n", encoding="utf-8")
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.quotePath=true",
            "diff",
            "--no-index",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--",
            "/dev/null",
            str(path),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1, result.stderr.decode()
    report = analyze(result.stdout.decode("utf-8"))
    assert report.files[0].old_path is None
    assert report.files[0].new_path.endswith(name)
    assert len(report.findings) == 1
    assert report.findings[0].rule_id == "python-syntax"
    assert report.findings[0].line == 1


def test_real_git_modified_file_without_final_newline(tmp_path):
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text("original")
    after.write_text("updated")
    result = subprocess.run(
        [
            "git",
            "diff",
            "--no-index",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--",
            str(before),
            str(after),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    file = analyze(result.stdout.decode()).files[0]
    assert file.added_lines[0].content == "updated"
    assert file.removed_lines[0].content == "original"


def test_real_git_paths_with_ambiguous_b_prefix(tmp_path):
    before = tmp_path / "old b" / "name.py"
    after = tmp_path / "new b" / "name.py"
    before.parent.mkdir()
    after.parent.mkdir()
    before.write_text("old = 1\n")
    after.write_text("new = 2\n")
    result = subprocess.run(
        [
            "git",
            "diff",
            "--no-index",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--",
            str(before),
            str(after),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    file = analyze(result.stdout.decode()).files[0]
    assert file.old_path == str(before).removeprefix("/")
    assert file.new_path == str(after).removeprefix("/")
    assert file.added_lines[0].new_line == 1


def test_real_git_zero_context_ranges_and_line_numbers(tmp_path):
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text("one\ntwo\nremoved\nfour\nfive\nold\n")
    after.write_text("inserted one\ninserted two\none\ntwo\nfour\nfive\nnew\n")
    result = subprocess.run(
        [
            "git",
            "diff",
            "--no-index",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "-U0",
            "--",
            str(before),
            str(after),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    file = analyze(result.stdout.decode()).files[0]
    assert [line.new_line for line in file.added_lines] == [1, 2, 7]
    assert [line.old_line for line in file.removed_lines] == [3, 6]


@pytest.mark.parametrize("name", ["name.py", "café.py"])
def test_real_git_rename_with_changes_without_committing(tmp_path, name):
    def git(*args):
        return subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.quotePath=true",
                "-C",
                str(tmp_path),
                *args,
            ],
            capture_output=True,
            check=True,
        ).stdout

    git("init", "--quiet")
    old = tmp_path / "old b" / name
    new = tmp_path / "new b" / name
    old.parent.mkdir()
    new.parent.mkdir()
    old.write_text("value = 1\n" + "# unchanged\n" * 18 + "value = 2\n")
    git("add", "--", str(old))
    tree = git("write-tree").decode().strip()
    git("mv", "--", str(old), str(new))
    new.write_text("value = 1\n" + "# unchanged\n" * 18 + "value = 3  \n")
    git("add", "--", str(new))
    diff = git("diff", "--cached", "--no-ext-diff", "--no-textconv", "--no-color", "-M", tree)
    assert b"rename from" in diff
    report = analyze(diff.decode())
    assert (report.files[0].old_path, report.files[0].new_path) == (
        f"old b/{name}",
        f"new b/{name}",
    )
    assert [(finding.file, finding.line) for finding in report.findings] == [(f"new b/{name}", 20)]


def test_real_git_binary_notice_and_payload_rejection(tmp_path):
    path = tmp_path / "binary file.bin"
    path.write_bytes(b"\x00binary\xffdata")
    args = ["git", "diff", "--no-index", "--no-ext-diff", "--no-textconv", "--no-color"]
    notice = subprocess.run([*args, "--", "/dev/null", str(path)], capture_output=True, check=False)
    assert notice.returncode == 1
    report = analyze(notice.stdout.decode())
    assert report.files[0].binary
    assert report.files[0].old_path is None
    assert report.files[0].path.endswith("binary file.bin")
    assert report.findings == () and report.notices
    payload = subprocess.run(
        [*args, "--binary", "--", "/dev/null", str(path)], capture_output=True, check=False
    )
    assert payload.returncode == 1
    assert b"GIT binary patch" in payload.stdout
    with pytest.raises(DiffParseError):
        analyze(payload.stdout.decode())


def test_real_git_python_symlink_is_not_compiled(tmp_path):
    (tmp_path / "target.py").write_text("value = 1\n")
    (tmp_path / "links").mkdir()
    link = tmp_path / "links" / "link.py"
    link.symlink_to("../target.py")
    result = subprocess.run(
        [
            "git",
            "diff",
            "--no-index",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--",
            "/dev/null",
            str(link),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    report = analyze(result.stdout.decode())
    assert report.files[0].new_mode == "120000"
    assert report.findings == ()
    assert report.notices
