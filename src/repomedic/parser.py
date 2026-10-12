"""Parse ordinary Git/unified text diffs without opening paths from the input."""

import re

from .models import ChangedFile, DiffLine, Hunk

_HUNK = re.compile(r"^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@(?: .*)?$")
_METADATA = (
    "index ",
    "new file mode ",
    "deleted file mode ",
    "old mode ",
    "new mode ",
    "similarity index ",
    "dissimilarity index ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
)


class DiffParseError(ValueError):
    """Malformed or unsupported diff; no partial analysis is returned."""


def _error(index: int, message: str) -> DiffParseError:
    return DiffParseError(f"Diff line {index + 1}: {message}")


def _unquote_path(raw: str, index: int) -> str:
    """Decode Git's byte-oriented C quoting, not Python string syntax."""
    if not re.fullmatch(r'"(?:[^"\\]|\\.)*"', raw):
        raise _error(index, "invalid quoted path")
    escapes = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}
    result = bytearray()
    position = 1
    while position < len(raw) - 1:
        char = raw[position]
        if char != "\\":
            result.extend(char.encode("utf-8"))
            position += 1
            continue
        position += 1
        char = raw[position]
        if char in "01234567":
            match = re.match(r"[0-7]{1,3}", raw[position:])
            value = int(match[0], 8)
            if value > 255:
                raise _error(index, "octal path escape exceeds one byte")
            result.append(value)
            position += len(match[0])
        elif char in escapes:
            result.append(escapes[char])
            position += 1
        else:
            raise _error(index, "unsupported Git path escape")
    try:
        return result.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _error(index, "quoted path is not valid UTF-8") from exc


def _path(raw: str, index: int, *, git_prefix: str = "", file_header: bool = False) -> str | None:
    try:
        raw.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _error(index, "path is not valid UTF-8") from exc
    if file_header:
        raw = raw.split("\t", 1)[0]
    if raw.startswith('"'):
        raw = _unquote_path(raw, index)
    if raw == "/dev/null":
        return None
    if git_prefix:
        if not raw.startswith(git_prefix):
            raise _error(index, f"expected Git path prefix {git_prefix}")
        raw = raw[len(git_prefix) :]
    if not raw or any(char in raw for char in "\x00\n\r"):
        raise _error(index, "empty path or path with unsupported control characters")
    return raw


def _git_paths(header: str, index: int) -> tuple[tuple[str, str], ...]:
    raw = header.removeprefix("diff --git ")
    quoted = r'"(?:[^"\\]|\\.)*"'
    if raw.startswith('"'):
        match = re.fullmatch(rf"({quoted}) ({quoted}|b/.*)", raw)
        candidates = [(match[1], match[2])] if match else []
    elif ' "' in raw:
        match = re.fullmatch(rf"(a/.*) ({quoted})", raw)
        candidates = [(match[1], match[2])] if match else []
    else:
        candidates = [(raw[: m.start()], raw[m.start() + 1 :]) for m in re.finditer(r" b/", raw)]
        equal = [pair for pair in candidates if pair[0].removeprefix("a/") == pair[1][2:]]
        if equal:
            candidates = equal
    if not candidates:
        raise _error(index, "invalid Git file header paths")
    result = []
    for old, new in candidates:
        old = _path(old, index)
        new = _path(new, index)
        if old is None or new is None or not old.startswith("a/") or not new.startswith("b/"):
            raise _error(index, "Git paths require the standard a/ and b/ prefixes")
        result.append((old[2:], new[2:]))
    # Ambiguous unquoted paths can be resolved by ---/+++ or rename metadata.
    return tuple(result)


def _parse_hunk(lines: list[str], index: int) -> tuple[Hunk, int, set[str]]:
    match = _HUNK.fullmatch(lines[index])
    if match is None:
        raise _error(index, "invalid hunk header")
    try:
        old_start, old_count, new_start, new_count = (
            int(match[1]),
            int(match[2]) if match[2] is not None else 1,
            int(match[3]),
            int(match[4]) if match[4] is not None else 1,
        )
    except ValueError as exc:
        raise _error(index, "hunk range integer is too large") from exc
    if (old_count and old_start == 0) or (new_count and new_start == 0):
        raise _error(index, "nonempty hunk ranges must start at line 1 or later")
    if old_count == new_count == 0:
        raise _error(index, "empty hunk")
    old_seen = new_seen = 0
    result: list[DiffLine] = []
    index += 1
    previous_marker = False
    eof_sides: set[str] = set()
    while index < len(lines):
        value = lines[index]
        if value == "\\ No newline at end of file":
            if not result or previous_marker:
                raise _error(index, "misplaced no-newline marker")
            previous_kind = result[-1].kind
            if (previous_kind != "added" and old_seen != old_count) or (
                previous_kind != "removed" and new_seen != new_count
            ):
                raise _error(index, "no-newline marker before the end of a file range")
            previous_marker = True
            if previous_kind != "added":
                eof_sides.add("old")
            if previous_kind != "removed":
                eof_sides.add("new")
            index += 1
            continue
        if old_seen == old_count and new_seen == new_count:
            break
        if not value or value[0] not in " +-":
            raise _error(index, "hunk ended before its declared line counts")
        kind = {" ": "context", "+": "added", "-": "removed"}[value[0]]
        old_line = old_start + old_seen if kind != "added" else None
        new_line = new_start + new_seen if kind != "removed" else None
        old_seen += kind != "added"
        new_seen += kind != "removed"
        if old_seen > old_count or new_seen > new_count:
            raise _error(index, "hunk exceeds its declared line counts")
        result.append(DiffLine(kind, value[1:], old_line, new_line))
        previous_marker = False
        index += 1
    if old_seen != old_count or new_seen != new_count:
        raise _error(index, "truncated hunk")
    return Hunk(old_start, old_count, new_start, new_count, tuple(result)), index, eof_sides


def _range_before(start: int, count: int) -> int:
    # Empty ranges name the line *before* an insertion/deletion point.
    return start - bool(count)


def parse_diff(text: str) -> tuple[ChangedFile, ...]:
    """Strictly parse a diff; empty input is a valid no-change input.

    Supports Git headers, ordinary unified headers, renames, mode-only changes,
    deletion, and binary *notices*. Binary patch payloads and combined diffs are
    rejected. Paths are labels, never instructions to access the filesystem.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()
    if not lines:
        return ()
    files: list[ChangedFile] = []
    index = 0
    while index < len(lines):
        file_index = index
        git_header = lines[index].startswith("diff --git ")
        old_path = new_path = None
        new_mode = None
        metadata_seen: set[str] = set()
        metadata_paths: dict[str, str | None] = {}
        header_paths: tuple[tuple[str, str], ...] = ()
        if git_header:
            header_paths = _git_paths(lines[index], index)
            old_path, new_path = header_paths[0]
            index += 1
            while index < len(lines) and lines[index].startswith(_METADATA):
                metadata = lines[index]
                prefix = next(prefix for prefix in _METADATA if metadata.startswith(prefix))
                if prefix in metadata_seen:
                    raise _error(index, "duplicate Git change metadata")
                metadata_seen.add(prefix)
                if prefix in {"new file mode ", "deleted file mode ", "old mode ", "new mode "}:
                    if not re.fullmatch(r"[0-7]{6}", metadata[len(prefix) :]):
                        raise _error(index, "invalid Git file mode")
                    if prefix in {"new file mode ", "new mode "}:
                        if new_mode is not None and new_mode != metadata[len(prefix) :]:
                            raise _error(index, "contradictory Git file modes")
                        new_mode = metadata[len(prefix) :]
                elif prefix in {"similarity index ", "dissimilarity index "}:
                    value = metadata[len(prefix) :]
                    if not re.fullmatch(r"[0-9]{1,3}%", value) or int(value[:-1]) > 100:
                        raise _error(index, "invalid Git similarity percentage")
                elif prefix == "index ":
                    if not re.fullmatch(r"index [0-9a-f]+\.\.[0-9a-f]+(?: [0-7]{6})?", metadata):
                        raise _error(index, "invalid Git index metadata")
                    if len(metadata.split()) == 3:
                        if new_mode is not None and new_mode != metadata.split()[2]:
                            raise _error(index, "contradictory Git file modes")
                        new_mode = metadata.split()[2]
                if metadata.startswith(("rename from ", "copy from ")):
                    old_path = _path(metadata.split(" ", 2)[2], index)
                    if old_path is None:
                        raise _error(index, "rename/copy path cannot be /dev/null")
                    metadata_paths["old"] = old_path
                elif metadata.startswith(("rename to ", "copy to ")):
                    new_path = _path(metadata.split(" ", 2)[2], index)
                    if new_path is None:
                        raise _error(index, "rename/copy path cannot be /dev/null")
                    metadata_paths["new"] = new_path
                elif metadata.startswith("new file mode "):
                    old_path = None
                    metadata_paths["old"] = None
                elif metadata.startswith("deleted file mode "):
                    new_path = None
                    metadata_paths["new"] = None
                index += 1
            for first, second in (
                ("rename from ", "rename to "),
                ("copy from ", "copy to "),
                ("old mode ", "new mode "),
            ):
                if (first in metadata_seen) != (second in metadata_seen):
                    raise _error(file_index, "incomplete paired Git change metadata")
            if (
                {"new file mode ", "deleted file mode "} <= metadata_seen
                or ({"new file mode ", "deleted file mode "} & metadata_seen)
                and ({"rename from ", "copy from ", "old mode "} & metadata_seen)
                or {"rename from ", "copy from "} <= metadata_seen
            ):
                raise _error(file_index, "contradictory Git change metadata")
        elif not lines[index].startswith("--- "):
            raise _error(index, "expected Git or unified file header")

        binary = False
        has_headers = False
        if index < len(lines) and lines[index].startswith("--- "):
            has_headers = True
            old_path = _path(
                lines[index][4:], index, git_prefix="a/" if git_header else "", file_header=True
            )
            index += 1
            if index >= len(lines) or not lines[index].startswith("+++ "):
                raise _error(index, "missing +++ file header")
            new_path = _path(
                lines[index][4:], index, git_prefix="b/" if git_header else "", file_header=True
            )
            index += 1
        if git_header:
            for side, value in (("old", old_path), ("new", new_path)):
                if side in metadata_paths and metadata_paths[side] != value:
                    raise _error(file_index, "file headers contradict Git change metadata")
            if len(header_paths) > 1 and not has_headers and len(metadata_paths) != 2:
                raise _error(file_index, "ambiguous Git paths without authoritative file headers")
            compatible = [
                pair
                for pair in header_paths
                if (old_path is None or pair[0] == old_path)
                and (new_path is None or pair[1] == new_path)
            ]
            if len(compatible) != 1:
                raise _error(file_index, "file paths contradict or do not resolve the Git header")
        if index < len(lines) and lines[index].startswith("Binary files "):
            if not git_header or not lines[index].endswith(" differ"):
                raise _error(index, "unsupported binary notice")
            binary = True
            index += 1
        hunks: list[Hunk] = []
        eof_sides: set[str] = set()
        while index < len(lines) and lines[index].startswith("@@"):
            hunk_index = index
            if not has_headers or binary:
                raise _error(index, "hunk requires text file headers")
            hunk, index, hunk_eof = _parse_hunk(lines, index)
            if old_path is None and (hunk.old_count != 0 or hunk.old_start != 0):
                raise _error(index, "new file hunk must have an empty old range")
            if new_path is None and (hunk.new_count != 0 or hunk.new_start != 0):
                raise _error(index, "deleted file hunk must have an empty new range")
            old_gap = _range_before(hunk.old_start, hunk.old_count)
            new_gap = _range_before(hunk.new_start, hunk.new_count)
            if hunks:
                previous = hunks[-1]
                old_gap -= (
                    _range_before(previous.old_start, previous.old_count) + previous.old_count
                )
                new_gap -= (
                    _range_before(previous.new_start, previous.new_count) + previous.new_count
                )
            if old_gap < 0 or new_gap < 0:
                raise _error(hunk_index, "overlapping or out-of-order hunks")
            if old_path is not None and new_path is not None and old_gap != new_gap:
                raise _error(hunk_index, "hunk offsets imply unequal unchanged line gaps")
            if ("old" in eof_sides and (old_gap or hunk.old_count)) or (
                "new" in eof_sides and (new_gap or hunk.new_count)
            ):
                raise _error(hunk_index, "hunk continues beyond a no-newline end-of-file marker")
            eof_sides.update(hunk_eof)
            hunks.append(hunk)
        if old_path is None and new_path is None:
            raise _error(index, "both file paths are /dev/null")
        if has_headers and not hunks:
            raise _error(index, "text file headers without a hunk")
        if not binary and not hunks:
            metadata_change = (
                "new file mode " in metadata_seen
                or "deleted file mode " in metadata_seen
                or {"old mode ", "new mode "} <= metadata_seen
                or {"rename from ", "rename to "} <= metadata_seen
                or {"copy from ", "copy to "} <= metadata_seen
            )
            if not metadata_change:
                raise _error(file_index, "Git file header without content or change metadata")
        files.append(
            ChangedFile(
                old_path, new_path, tuple(hunks), binary, new_mode if new_path is not None else None
            )
        )
        if index < len(lines) and not lines[index].startswith(("diff --git ", "--- ")):
            raise _error(index, "unexpected content or unsupported diff format")
    paths = [file.path for file in files]
    if len(set(paths)) != len(paths):
        raise DiffParseError("Duplicate file entries are not supported")
    return tuple(files)
