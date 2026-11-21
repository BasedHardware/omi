# Speaker final-pass typecheck validation — 2026-11-05

Round 11, `lane/spkfix`, starting at `2d5b784d298a` with comparison base
`747ccc9ddcd4`. Local implementation and hermetic checks only; no production
access, GCP tier, push, merge or PR creation.

## Changes

- Carry failing-unit diagnostics in a declared invocation context, preserving
  original exceptions, causes and the selected unit. Initialize projection
  cleanup references even when a unit has no parts.
- Declare the final-pass result and non-returning reference refusal. Guard
  optional diagnostic keys and invalid enrichment payloads.
- Expose budgeted SDK snapshot lifecycle operations through a transaction
  subclass, public dispatch/failure helpers, and Prometheus's Collector interface.
  Migrate in-tree helper callers together.
- Add six regression cases for selected-unit diagnostics, empty-part cleanup and
  real SDK snapshot cleanup on success/refusal. No new suppression comments,
  casts, rollout changes or persistence-policy changes.

## Enforced typecheck

From the repository root, using the worktree's Python 3.11 environment and the
repository-pinned pyright 1.1.403:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 1800 --no-priority -- \
  bash -c 'cd backend && PYRIGHT_PYTHON="$PWD/.venv/bin/python" bash scripts/typecheck.sh'
```

Baseline: **18 errors**, exit 1. Fixed sources: **0 errors**, exit 0. The final
run retains 73,574 configured warnings; warnings are not promoted or suppressed.
The same check also passed inside `check_backend_typecheck_if_needed` below.

## Focused regression suites

Run through `omi-heavy`, from `backend/`:

```sh
.venv/bin/python -m pytest \
  tests/unit/test_batch_final_pass_types.py \
  tests/unit/test_batch_final_pass.py \
  tests/unit/test_batch_final_pass_resources.py \
  tests/unit/test_batch_final_pass_terminal_metrics.py \
  tests/unit/test_batch_final_pass_transient.py \
  tests/unit/test_batch_final_pass_repro.py \
  tests/unit/test_batch_final_pass_direct.py \
  tests/unit/test_batch_final_pass_outage.py \
  tests/unit/test_enrichment_route.py \
  tests/unit/test_sync_reprocess_coalesce.py -q
```

**633 passed, 10 warnings in 22.85 seconds**, exit 0. The renamed helper's
integration-emulator caller was migrated but not executed; no emulator was used.

## Full local pre-push gate

Run the actual hook with empty stdin; this does not invoke `git push`:

```sh
OMI_PR_BODY_FILE=/Volumes/Ephemeral/scratch/spkfix/round11-pr-body.md \
OMI_CHECKS_JOBS=2 BACKEND_PYTEST_WORKERS=1 OMI_PREFLIGHT_BACKGROUND=0 \
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 1800 --no-priority -- \
  bash scripts/pre-push </dev/null
```

**Passed, exit 0.** Shared PR preflight passed all 55 checks. Backend runtime
environment, enforced typecheck, runtime-image closure, selected backend unit
tests, OpenAPI contract, release/workflow/client guards and optional formatting
phases all passed. No later failing phase. The bounded unit selector ran 18
changed backend test files instead of the full backend suite; the new type
regression file was also covered explicitly by the focused command above.
The formatter checked 51 branch-changed Python files without changes.

Local logs are `round11-typecheck-before.log`, `round11-typecheck-final.log`,
`round11-focused-tests.log` and `round11-full-preflight.log` under
`/Volumes/Ephemeral/scratch/spkfix/`. They are disposable execution evidence;
this report is the committed result. Full CI and production acceptance remain
outside this local validation.
