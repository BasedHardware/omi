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
- Runs `flutter pub get` in `app/` (shared `PUB_CACHE`) and
  `scripts/dev-harness/generate-app-env.sh` when `lib/env/*.g.dart` is missing
  (full `build_runner`, never a filtered env-only run).
- Installs git hooks when the pre-commit hook is missing.

## What it does not do

- Install uvicorn / pyright / google.* (needed by `mobile-session start` and
  `check_backend_typecheck_if_needed`). After bootstrap, PRs that touch
  `backend/` must run **`make lane-backend`** before `git push` or the
  typecheck gate fails with a missing pyright. That command uses
  `uv pip install -r backend/requirements.txt` (index wheels, ~1 min) and is
  **not lock-hash identical**. `make setup` / `make setup-backend` remain
  the locked environment (`uv pip sync pylock.macos.toml`). The pylock lists
  hashed sdist+wheel for av/llvmlite/scipy/pyarrow and can stall ~20 min.
- Envied generation goes through `scripts/dev-harness/generate-app-env.sh`:
  no `--delete-conflicting-outputs`, no `--build-filter`. A filtered env-only
  build_runner run deleted tracked `lib/utils/manifest/manifest.g.dart`.
- The Flutter generated-output pre-push gate needs **`flutter pub get` in `app/`**.
  This command already runs it; re-run after adding Dart deps. Skipping
  bootstrap surfaces only as a failed push.
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
