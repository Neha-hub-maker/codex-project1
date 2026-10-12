import difflib
import random

import pytest

from repomedic import DiffParseError, parse_diff


def test_normal_change_tracks_both_line_numbers(fixture_diff):
    files = parse_diff(fixture_diff("normal.diff"))
    assert len(files) == 2
    modified, added = files
    assert (modified.old_path, modified.new_path) == ("src/math_utils.py", "src/math_utils.py")
    context, removed, inserted, blank = modified.hunks[0].lines
    assert (context.kind, context.old_line, context.new_line) == ("context", 1, 1)
    assert (removed.kind, removed.old_line, removed.new_line) == ("removed", 2, None)
    assert (inserted.kind, inserted.old_line, inserted.new_line) == ("added", None, 2)
    assert (blank.content, blank.old_line, blank.new_line) == ("", 3, 3)
    assert added.old_path is None
    assert added.added_lines[-1].new_line == 3


def test_rename_delete_binary_and_mode_changes(fixture_diff):
    renamed, deleted, binary, mode = parse_diff(fixture_diff("operations.diff"))
    assert (renamed.old_path, renamed.new_path) == ("old name.txt", "new name.txt")
    assert renamed.hunks == ()
    assert deleted.new_path is None
    assert deleted.path == "obsolete.txt"
    assert [line.old_line for line in deleted.removed_lines] == [1, 2]
    assert binary.binary
    assert binary.hunks == ()
    assert mode.path == "script.sh"
    assert mode.hunks == ()


def test_multiple_hunks_and_omitted_counts():
    diff = "--- original.txt\n+++ updated.txt\n@@ -2 +2 @@\n-before\n+after\n"
    diff += "@@ -10,0 +11,2 @@ section\n+one\n+two\n"
    file = parse_diff(diff)[0]
    assert (file.old_path, file.new_path) == ("original.txt", "updated.txt")
    assert [line.new_line for line in file.added_lines] == [2, 11, 12]


def test_no_newline_markers_do_not_change_counts():
    diff = (
        "--- old\n+++ new\n@@ -1 +1 @@\n-old\n\\ No newline at end of file\n"
        "+new\n\\ No newline at end of file\n"
    )
    file = parse_diff(diff)[0]
    assert len(file.hunks[0].lines) == 2
    assert file.added_lines[0].content == "new"


@pytest.mark.parametrize("diff", ["", "\n"], ids=["empty", "blank-line"])
def test_empty_vs_blank_input(diff):
    if diff:
        with pytest.raises(DiffParseError):
            parse_diff(diff)
    else:
        assert parse_diff(diff) == ()


@pytest.mark.parametrize(
    "name,header",
    [
        ("file with spaces.txt", "a/file with spaces.txt b/file with spaces.txt"),
        ("file with spaces.txt", '"a/file with spaces.txt" "b/file with spaces.txt"'),
        ("café.py", '"a/caf\\303\\251.py" "b/caf\\303\\251.py"'),
    ],
)
def test_git_paths_with_spaces_and_c_quoting(name, header):
    # Mode-only patches exercise the Git header rather than overriding it.
    file = parse_diff(f"diff --git {header}\nold mode 100644\nnew mode 100755\n")[0]
    assert file.path == name


def test_quoted_file_headers_and_timestamps():
    diff = '--- "a/a b.py"\t2026-10-11\n+++ "b/a b.py"\t2026-10-11\n'
    # Plain unified diffs preserve arbitrary path prefixes.
    file = parse_diff(diff + "@@ -1 +1 @@\n-before\n+after\n")[0]
    assert file.new_path == "b/a b.py"


def test_crlf_transport(fixture_diff):
    diff = fixture_diff("normal.diff")
    assert parse_diff(diff.replace("\n", "\r\n")) == parse_diff(diff)


@pytest.mark.parametrize(
    "diff",
    [
        "not a patch\n",
        "--- a/x\n",
        "+++ b/x\n",
        "--- a/x\n+++ b/x\n",
        "--- /dev/null\n+++ /dev/null\n@@ -0,0 +1 @@\n+x\n",
        "--- a/x\n+++ b/x\n@@ invalid @@\n+x\n",
        "--- a/x\n+++ b/x\n@@ -0 +1 @@\n-x\n+y\n",
        "--- a/x\n+++ b/x\n@@ -0,0 +0,0 @@\n",
        "--- a/x\n+++ b/x\n@@ -1,2 +1,2 @@\n-x\n+y\n",
        "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-x\n+y\n+extra\n",
        "--- a/x\n+++ b/x\n@@ -1 +1 @@\n+x\n+y\n",
        "--- a/x\n+++ b/x\n@@ -1 +1 @@\n\n",
        "--- a/x\n+++ b/x\n@@ -1 +1 @@\n\\ No newline at end of file\n",
        "--- a/x\n+++ b/x\n@@ -1,2 +1,2 @@\n-x\n\\ No newline at end of file\n-y\n+a\n+b\n",
        "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-x\n+y\n"
        "\\ No newline at end of file\n\\ No newline at end of file\n",
        "--- a/x\n+++ b/x\n@@ -3 +3 @@\n-x\n+y\n@@ -2 +2 @@\n-y\n+z\n",
        "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-x\n+y\n@@ -1 +1 @@\n-y\n+z\n",
        "diff --cc x\n",
        "diff --git a/x b/x\nGIT binary patch\nliteral 1\n",
        "diff --git a/x b/x\n@@ -1 +1 @@\n-x\n+y\n",
        "diff --git a/x b/x\n",
        "diff --git a/x b/x\nindex 123..456\n",
        "diff --git a/x b/x\nrename from x\n",
        "--- /dev/null\n+++ x\n@@ -1 +1 @@\n-old\n+new\n",
        "--- x\n+++ /dev/null\n@@ -1 +1 @@\n-old\n+new\n",
        'diff --git "a/x b/x\n',
        '--- "unterminated\n+++ x\n@@ -1 +1 @@\n-x\n+y\n',
        "--- \x00\n+++ x\n@@ -1 +1 @@\n-x\n+y\n",
    ],
)
def test_rejects_malformed_and_unsupported_input(diff):
    with pytest.raises(DiffParseError):
        parse_diff(diff)


def test_duplicate_file_entries_are_rejected(new_python_diff):
    diff = new_python_diff("x = 1\n")
    with pytest.raises(DiffParseError, match="Duplicate"):
        parse_diff(diff + diff)


def test_truncated_fixture_has_actionable_error(fixture_diff):
    with pytest.raises(DiffParseError, match=r"Diff line \d+: truncated hunk"):
        parse_diff(fixture_diff("malformed.diff"))


def test_unreasonably_large_range_reports_parse_error():
    diff = "--- x\n+++ x\n@@ -" + "1" * 5000 + " +1 @@\n-old\n+new\n"
    with pytest.raises(DiffParseError, match="integer is too large"):
        parse_diff(diff)


@pytest.mark.parametrize(
    "quoted,expected",
    [
        ('"cafÃ©.py"', "cafÃ©.py"),
        ('"caf\\303\\251.py"', "café.py"),
        ('"tab\\tname.py"', "tab\tname.py"),
        ('"back\\\\slash.py"', "back\\slash.py"),
    ],
)
def test_quoted_paths_preserve_unicode_and_decode_only_git_escapes(quoted, expected):
    diff = f"--- /dev/null\n+++ {quoted}\n@@ -0,0 +1 @@\n+content\n"
    assert parse_diff(diff)[0].path == expected


@pytest.mark.parametrize("quoted", ['"\\u0078.py"', '"\\x78.py"', '"\\777.py"', '"\\377.py"'])
def test_invalid_git_escapes_and_non_utf8_paths_are_rejected(quoted):
    diff = f"--- /dev/null\n+++ {quoted}\n@@ -0,0 +1 @@\n+content\n"
    with pytest.raises(DiffParseError):
        parse_diff(diff)


@pytest.mark.parametrize(
    "diff",
    [
        "diff --git a/x b/x\n--- a/x\n+++ b/other\n@@ -1 +1 @@\n-old\n+new\n",
        "diff --git a/x b/x\nnew file mode 100644\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n",
        "diff --git a/old b/new\nrename from old\nrename to different\n",
        "diff --git a/old b/new\nrename from old\n--- a/old\n+++ b/new\n@@ -1 +1 @@\n-old\n+new\n",
        "diff --git a/x b/x\nnew file mode 100644\ndeleted file mode 100644\n",
        "diff --git a/x b/x\nold mode 100644\nold mode 100644\nnew mode 100755\n",
        "--- x\n+++ x\n@@ -2 +20 @@\n-old\n+new\n",
        "--- x\n+++ x\n@@ -1 +1 @@\n-old\n+new\n@@ -5 +50 @@\n-old\n+new\n",
        "--- x\n+++ x\n@@ -1 +1 @@\n-old\n+new\n\\ No newline at end of file\n"
        "@@ -3 +3 @@\n-old\n+new\n",
    ],
)
def test_contradictory_headers_offsets_and_eof_markers_are_rejected(diff):
    with pytest.raises(DiffParseError):
        parse_diff(diff)


def test_zero_length_ranges_use_insertion_and_deletion_boundaries():
    diff = (
        "--- x\n+++ x\n@@ -0,0 +1,2 @@\n+inserted one\n+inserted two\n"
        "@@ -3 +4,0 @@\n-removed\n@@ -6 +7 @@\n-old\n+new\n"
    )
    file = parse_diff(diff)[0]
    assert [line.new_line for line in file.added_lines] == [1, 2, 7]
    assert [line.old_line for line in file.removed_lines] == [3, 6]


def test_ambiguous_rename_header_uses_authoritative_metadata():
    diff = (
        "diff --git a/old b/name.py b/new b/name.py\n"
        "similarity index 100%\nrename from old b/name.py\nrename to new b/name.py\n"
    )
    file = parse_diff(diff)[0]
    assert (file.old_path, file.new_path) == ("old b/name.py", "new b/name.py")


@pytest.mark.parametrize(
    "metadata",
    [
        "new file mode BAD\n",
        "old mode 100644\nnew mode 999999\n",
        "similarity index 101%\nrename from x\nrename to y\n",
        "similarity index nope\nrename from x\nrename to y\n",
        "rename from /dev/null\nrename to y\n",
        "rename from x\nrename to /dev/null\n",
        "index invalid\nnew file mode 100644\n",
        "new file mode 120000\nindex 000..abc 100644\n",
    ],
)
def test_invalid_git_metadata_is_rejected(metadata):
    with pytest.raises(DiffParseError):
        parse_diff("diff --git a/x b/y\n" + metadata)


def test_wrong_side_git_header_prefix_is_rejected():
    diff = "diff --git a/x b/x\n--- b/x\n+++ a/x\n@@ -1 +1 @@\n-old\n+new\n"
    with pytest.raises(DiffParseError, match="expected Git path prefix"):
        parse_diff(diff)


@pytest.mark.parametrize("path", ["surrogate\ud800.py", '"surrogate\ud800.py"'])
def test_non_utf8_python_api_paths_have_controlled_parse_errors(path):
    with pytest.raises(DiffParseError, match="not valid UTF-8"):
        parse_diff(f"--- /dev/null\n+++ {path}\n@@ -0,0 +1 @@\n+content\n")


def test_generated_unified_diffs_reconstruct_expected_files():
    rng = random.Random(4321)
    for _ in range(100):
        before = [f"line {number}\n" for number in range(rng.randrange(30))]
        after = before.copy()
        for change in range(5):
            start = rng.randrange(len(after) + 1)
            stop = min(start + rng.randrange(4), len(after))
            after[start:stop] = [
                f"change {change}:{number}\n" for number in range(rng.randrange(4))
            ]
        diff = "".join(
            difflib.unified_diff(before, after, "old.txt", "new.txt", n=rng.randrange(4))
        )
        if not diff:
            assert parse_diff(diff) == ()
            continue
        file = parse_diff(diff)[0]
        reconstructed = []
        cursor = 0
        for hunk in file.hunks:
            start = hunk.old_start - 1 if hunk.old_count else hunk.old_start
            reconstructed.extend(before[cursor:start])
            for line in hunk.lines:
                if line.old_line is not None:
                    assert line.content + "\n" == before[line.old_line - 1]
                if line.new_line is not None:
                    assert line.content + "\n" == after[line.new_line - 1]
                    reconstructed.append(line.content + "\n")
            cursor = start + hunk.old_count
        reconstructed.extend(before[cursor:])
        assert reconstructed == after


@pytest.mark.parametrize("header", ["@@ -1 +1 @@suffix", "@@ -١ +١ @@"])
def test_nonstandard_hunk_range_syntax_is_rejected(header):
    with pytest.raises(DiffParseError, match="invalid hunk header"):
        parse_diff(f"--- x\n+++ x\n{header}\n-old\n+new\n")
