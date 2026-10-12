# RepoMedic

RepoMedic is a local, evidence-based Git diff analyzer. This first version builds
the deterministic foundation for an AI repository reliability agent. It uses no
AI service, network calls, API keys, or runtime third-party dependencies.

## Setup and use

Requires Python 3.12 or later. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/repomedic tests/fixtures/risky.diff --format json
.venv/bin/repomedic tests/fixtures/risky.diff --format markdown --output /tmp/report.md
git diff --no-ext-diff --no-color | .venv/bin/repomedic --format markdown
```

Use a plain unified diff (`git diff`, without `--binary` or combined merge diff
options). stdin is the default; a UTF-8 input file is also accepted. The CLI limits
input to 10 MiB. Exit codes: **0** for completed analysis (including findings),
**1** when `--fail-on low|medium|high` matches a finding at that severity or higher,
and **2** for malformed/unsupported input or an operational error. The threshold
includes both confirmed findings and risk indicators. Empty input is a valid
no-change result, not an error. No partial report is emitted for malformed input.

```sh
.venv/bin/repomedic tests/fixtures/risky.diff --fail-on high
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

## Implemented features

- Parses added, removed, and context lines with old/new line numbers and file paths.
  Handles ordinary unified and Git headers, multiple hunks/files, renames, deletions,
  mode-only changes, omitted range counts, quoted paths, and no-newline markers.
- Validates declared hunk counts, ordering, and file headers. Rejects malformed,
  duplicate-file, combined, and binary-payload diffs instead of guessing.
- Reports binary change notices as skipped content.
- Checks added lines for trailing spaces/tabs (confirmed observation, which may be intentional) and
  possible merge conflict markers (risk indicator, since they can be intentional text).
- Compiles **complete newly added Python files** without executing them to detect
  syntax defects on the running Python version. In valid added Python files, AST
  analysis flags direct `eval`/`exec` calls as risks. Strings/comments are not calls.
- Emits JSON (schema version 1) and readable Markdown with location, severity,
  assessment (`confirmed` or `risk`), explanation, and evidence for every finding.
  Reports include changed lines, counts, selected checks, and explicit skip notices.
  File entries include `new_mode` when supplied by Git metadata (otherwise `null`).

The sample `risky.diff` contains deliberate defects. Findings in a real run come
from the supplied input; fixtures are never used by the analysis engine.

## Architecture

```text
UTF-8 diff → parser → immutable change models → checks → analysis report
                                                       ├─ JSON
                                                       └─ Markdown
```

`parser.py` strictly interprets diff structure. `models.py` holds the shared data
types. `checks.py` defines the small `Check` protocol and default rules.
`engine.py` coordinates analysis and accepts custom checks via `analyze(text,
checks=...)`. `reports.py` formats results; `cli.py` manages local I/O and exit
status. The parser never reads files named inside a diff. An analyzed Python
file is never imported or executed.

The only development dependencies are pytest (tests) and Ruff (lint/format);
setuptools is the build backend. CI runs these checks and builds a wheel on
Python 3.12 and 3.13 with read-only repository permission. It makes no PR comments.

## Limitations and trust boundaries

- This is diff-only analysis, not a full repository, test runner, or vulnerability
  scanner. It does not diagnose failing tests, prove behavior, propose fixes, or
  claim a clean report means a safe change. An arbitrary logic bug can pass.
- Syntax and call analysis skips modified Python files because diff fragments do
  not establish the full source. Syntax-invalid added files get a syntax finding
  but no AST call analysis. Syntax semantics depend on the running Python version.
  Git symlinks and submodules are skipped rather than compiled as Python. Plain
  unified diffs provide no file modes, so regular text files are assumed.
- Direct `eval`/`exec` may be safe or shadowed by another binding. Input trust and
  name resolution are not analyzed. Conflict-like text can be deliberate.
- Binary content, combined merge diffs, patch-email wrappers, and nonstandard
  Git prefix options are outside scope. Paths must decode as UTF-8 and cannot contain
  NUL, newline, or carriage return. CRLF diff line terminators are normalized.
  Input paths are report labels, not trusted filesystem paths.
- Markdown displays control and bidirectional formatting characters as visible escapes.
  JSON retains the original text using JSON escaping. Evidence code blocks preserve tabs/newlines.
- Reports include source excerpts (and JSON includes changed lines). Treat them
  with the same confidentiality as the input diff; do not publish sensitive diffs.
- The CLI's size limit is a practical guard, not a sandbox for hostile inputs.
  Run untrusted analysis with normal process/resource isolation. No submitted
  code, external diff tool, Git hook, or test command is executed by RepoMedic.

## Development stages

1. **Current:** local diff parsing, deterministic checks, structured evidence,
   CLI, fixtures, and continuous integration.
2. **Next:** read-only GitHub PR ingestion and full-file snapshots pinned to base
   and head SHAs. Test the adapter with recorded responses; start with public PRs,
   then optional least-privilege GitHub App authentication for private reads.
   Keep fetching outside the analysis engine. No posting permissions are needed.
3. Add isolated test execution and failure evidence with time/resource limits.
4. Add an optional AI reasoning provider that consumes evidence and labels
   hypotheses distinctly from verified findings. Credentials remain external.
5. Consider proposed patches only after verification and explicit human approval.
   Automated commenting, mutation, and merging are separate future decisions.

These later stages are design direction, not implemented capabilities.
