# Lane-worktree bootstrap

One command takes a fresh linked worktree to the point where **cheap pre-push
gates can run** and **`bash app/test.sh` can run**, without syncing the full
backend lock.

```bash
make lane-bootstrap
```

Equivalent: `bash scripts/dev-harness/bootstrap-lane-worktree.sh`. Idempotent.
Never touches another worktree. Never rewrites a pre-existing `app/.dev.env`.

## What it does

- Checks Flutter on PATH is **3.44.5** (repo pin, not latest).
- Leaves `PUB_CACHE` at `$HOME/.pub-cache` (or the caller's `PUB_CACHE`) so
  worktrees share the Dart package cache.
- Creates `backend/.venv` with **Python 3.11 via uv** (never the system 3.14).
- Detects an **incomplete** venv (the directory existing is not enough) by
  probing `import yaml, dotenv`. If those fail, installs only
  `scripts/dev-harness/cheap-gate-python-packages.txt` — not `uv pip sync`
  of `pylock.macos.toml`.
- Copies git-ignored mobile build inputs when missing (same files `app/test.sh`
  bootstraps). If `app/.dev.env` already exists with a non-loopback
  `API_BASE_URL`, the command **refuses** and does not rewrite the file.
- Runs `flutter pub get` in `app/` (shared `PUB_CACHE`) and `build_runner`
  only when `lib/env/*.g.dart` is missing.
- Installs git hooks when the pre-commit hook is missing.

## What it does not do

- `uv pip sync` of the full backend lock (llvmlite/scipy/av/pyarrow). Run
  `make setup-backend` only when the change touches backend code.
- `git fetch` / fast-forward of `main` in another worktree.

## Why yaml + dotenv

`scripts/pre-push` always prefers `backend/.venv/bin/python` when that path
is executable. The always-on cheap gates (PR preflight, promotion policy,
deployment concurrency) are stdlib-only, but `check_desktop_flow_lint_if_needed`
imports **PyYAML**, and harness wrappers import **python-dotenv** via
`dev_harness.cli`. An incomplete venv that exists as a directory makes
`git push` fail with `desktop E2E flow metadata checks require Python 3 and
PyYAML`. The resolver now ignores such a venv until `make lane-bootstrap`
completes the cheap-gate extras.
