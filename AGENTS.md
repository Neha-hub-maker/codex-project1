# RepoMedic contributor instructions

## Scope and design

- Use the existing checkout. Cloud tasks already run in isolated environments;
  do not create worktrees unless the user requests one.
- This MVP is a local, deterministic diff analyzer. Keep parsing, checks, reports,
  and CLI I/O separate. Prefer the Python standard library; justify new dependencies.
- Preserve immutable models and stable JSON fields. Bump the schema version for
  incompatible report changes and document new rule IDs and applicability.
- Every finding must have real input-derived evidence. Distinguish confirmed
  defects from risk indicators. Describe uncertainty and skipped analysis.
- Do not add speculative GitHub/AI scaffolding before a working use case exists.

## Setup and verification

Run from the repository root with Python 3.12+:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m pip wheel --no-deps . --wheel-dir /tmp/repomedic-wheels
```

Use realistic fixtures under `tests/fixtures` and test public API and CLI behavior.
For parser changes, cover line numbers, counts, malformed input, and unsupported
formats. For checks, test both true triggers and false positives. For report
changes, test JSON structure and Markdown escaping. Keep errors visible; do not
disable assertions or claim skipped/unrun checks passed.

## Safety

- Never execute or import analyzed code or open paths named by the diff.
- No paid API calls, API keys, or external AI dependencies in this phase.
- Never print or commit credentials. Reports may contain source excerpts; treat
  input and generated artifacts as potentially sensitive.
- GitHub integration is read-only until explicitly authorized otherwise. Do not
  post comments, change external repositories, propose automatic fixes, or merge
  PRs as part of this MVP.
- Preserve TLS verification and build/test failures. Report repository defects
  plainly instead of weakening checks to obtain a passing result.
