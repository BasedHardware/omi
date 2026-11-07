# B2 merge-owner fixes — qualification in progress

Repository: BasedHardware/omi. Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-b2-upstream-keep-clean`. Branch: `lane/pgf-b2`.

The initial 24 branch commits were rebased onto `origin/main` at `0433d12e05d3b97363779c57495bb3e23965903f` before implementation. Pre-existing `app/analysis_options.yaml` and `app/pubspec.lock` edits are preserved in stash `a75f3e017ca4bf4071017f617ea5c2844752cee2` during qualification and must be restored before handoff.

Checkpoint UTC: 2026-11-07T04:52:46.922655+00:00

Verification update UTC: 2026-11-07T05:22:09.945366+00:00

- Initial focused root invocation: **158 passed, 1 failed**, no skips. The existing independent-process wipe witness could not import `database` because the invocation used the repository root; the canonical runner uses `backend/`. Its assertions are unchanged. The frozen job reruns these files separately from `backend/`.
- Backend environment preflight: **17 passed, 9 optional warnings, 0 failed**.
- `138a3d4b06a2` preserves invalid-mode HTTP 503 / WS 1013 mapping at all six async entry points: only literal `off` bypasses resolution, while every other mode is validated inside the transport helper. Six invalid-mode regressions were added alongside the existing off/on assertions.
- The first full-selector run was deliberately stopped in its type-check phase, before any pytest file ran, so the new correction can be qualified coherently. Its environment phase passed; no type-check success is claimed.
- The queued frozen job now runs the eight focused files separately, the exact requested `make preflight`, and the complete changed-file backend selector sequentially at one captured, tracked-clean commit. All phase outcomes are pending until its receipt is complete.

## Required items and commits

1. Mode off must add no resolver coroutine/executor submission, and no wipe heartbeat: `c078158a3b80` gates all four async HTTP and two async WebSocket routing sites synchronously; `ef525bf9ce55` gates the entire account-deletion step before heartbeat. Regression families: `test_async_http_routing_submits_only_when_on`, `test_async_ws_routing_submits_only_when_on`, `test_off_wipe_never_enters_cell_step`, `test_worker_heartbeats_at_major_operation_boundaries`.
2. Wipe requires explicit cell enrollment: `ef525bf9ce55` (boundary typing refined in `c26882f49bf7`) rejects malformed/Firestore cell routes before destructive calls and requires a persisted cell enrollment head. A disabled directory row additionally requires a retained wipe tombstone for retry. Tests: `test_no_destructive_work_without_explicit_enrollment`, existing real-Postgres retry and stale-writer families.
3. Wipe has its own default-off switch: `ef525bf9ce55` adds `CELL_DIRECTORY_WIPE_ENABLED` and registers/classifies it. Routing off skips the entire step; routing on with this switch disabled fails the required step before new cell/directory IO. Tests: `test_wipe_kill_switch_blocks_before_io`, `test_off_constructs_nothing`, service ceremony ordering and required-failure propagation.
4. Cross-worker route epochs: `c078158a3b80` adds a mandatory raw Redis GET to every warm resolver call, tags both cache tiers, rotates epoch on invalidate, and fails closed on Redis errors. Epoch-key loss gets a fresh identity, avoiding stale cache reuse. `1849b8ebd6f2` reads the cached plane/epoch from one tuple to avoid a torn concurrent read. Tests: `test_process_hit_checks_one_epoch_get_without_pg`, `test_route_flip_reaches_two_warm_resolvers`, `test_stale_read_cannot_poison_post_flip_cache`, `test_epoch_loss_rejects_both_stale_cache_tiers`, `test_warm_resolver_and_invalidation_fail_closed_on_redis_loss`.
5. Core transition preconditions: `b4d225f39200` checks the persisted cell kind, `cutover_ready`, and `destination_backend_bound` inside `apply_cutover_transition`, including direct callers. Completed migrated retries retain idempotence. Test: `test_core_migrated_transition_requires_durable_readiness`, plus the existing coordinator generation-zero ceremony.

`02dd231742e0` appends the requested Merge-owner review fixes section to `.agent-artifacts/pgf/b2-pr-body.md`.

## Files changed in this fix round

- `.agent-artifacts/pgf/b2-pr-body.md`
- `backend/config/directory_routing.py`
- `backend/database/directory/router.py`
- `backend/database/directory/wipe.py`
- `backend/dependencies.py`
- `backend/docs/feature-flag-registry.md`
- `backend/services/users/account_deletion.py`
- `backend/tests/services/users/test_account_deletion.py`
- `backend/tests/unit/test_account_cutover_foundation.py`
- `backend/tests/unit/test_cell_wipe_step.py`
- `backend/tests/unit/test_dependency_async_boundaries.py`
- `backend/tests/unit/test_directory_router.py`
- `backend/utils/account_cutover/state.py`
- `backend/utils/other/endpoints.py`
- `config/deployment-setting-classification.json`
- `config/feature-flags.yaml`
- `.agent-artifacts/pgf/merge-owner-fix-result.md` (this report).

## Deviations and scope extensions taken

Scope extension taken: `backend/tests/unit/test_dependency_async_boundaries.py` explicitly enables routing for its existing executor/concurrency witnesses. Their assertions previously assumed unconditional resolution, so leaving the fixture at the default off mode would test the wrong branch after required item 1. All concurrency assertions remain intact (`fe1d84ebcc9a`).

No forbidden paths edited. No changes under `.github/`, `backend/database/jobstore/`, or `testing/store_fixtures.py`. No wrappers added. The wipe tombstone is written before disabling the directory route so an interruption cannot leave a disabled row without durable proof for retry. The existing durable cell enrollment head is used instead of inventing a second enrollment authority.

## Verification

All test/check subprocesses use `python3 .agent-artifacts/pgf/run-merge-owner-check.py ...`, which removes `GOOGLE_APPLICATION_CREDENTIALS`, `SERVICE_ACCOUNT_JSON`, `FIREBASE_AUTH_CREDENTIALS_PATH`, and every `CLOUDSDK_*` variable before exec. No GCP tier was used, no production data was accessed, and no api.omi.me calls were made. Python for backend tests is this worktree's `backend/.venv` (3.11).

Completed:

- `backend/.venv/bin/python backend/scripts/scan_async_blockers.py --dirs backend/routers backend/utils`: PASS, 594 sync + 171 async endpoints scanned, zero blocking findings.

- `scripts/pr-preflight --metadata-only --pr-body-file .agent-artifacts/pgf/b2-pr-body.md`: PASS, 5 checks, including invariants, UI evidence, failure-class declarations, and line-count limits.
- `python3 scripts/render_feature_flag_registry.py --as-of 2026-11-05`: PASS (preserves the existing generated catalog date).
- `python3 scripts/check_feature_flag_registry.py`: PASS; existing registry warnings remain.
- `black --line-length 120 --skip-string-normalization <all changed Python files>` and `git diff --check`: PASS.
- `backend/.venv/bin/python backend/scripts/select_backend_unit_tests.py --changed-files .agent-artifacts/pgf/merge-owner-changed-files.txt --output .agent-artifacts/pgf/merge-owner-selected-tests.txt --reason-output .agent-artifacts/pgf/merge-owner-selection-reason.txt`: PASS. Selector requires full backend suite (2,682 files in this snapshot).

In flight / queued through `/Users/dazheng/workspace/omi/bin/omi-heavy run`:

- The short focused auth/core invocation (`-k 'routing_submits or core_migrated'`) hit the shared gate's 900-second queue deadline before any tests ran (exit 75); the complete four-file focused invocation below includes every one of these regressions and has a 7,200-second queue deadline.
- Four focused directory/wipe/cutover/plane-probe files; real local Postgres via pgserver.
- Backend environment preflight: completed, 17 passed / 9 optional warnings / 0 failed.
- `BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash backend/scripts/run-unit-ci.sh --changed-files <absolute changed-files artifact>`.
- Frozen `OMI_PR_BODY_FILE=.agent-artifacts/pgf/b2-pr-body.md BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight` at the committed product head captured on admission (product source at `c26882f49bf7`, with executor witness migration `fe1d84ebcc9a`; guarded head + tracked-clean checks before/after).


No green claim for queued or in-flight checks. Exact final outcomes will replace this section before handoff.

## Known gaps

No deployment or production acceptance is claimed. Route invalidation must succeed before a flip is complete; already-admitted requests still require the existing cutover drain. W5 remains gated by full plane-aware integration, wipe qualification, and connection-budget approval. Redis now participates in routing availability when routing mode is enabled. With routing on, non-cell or directory-only owners intentionally fail the required wipe step rather than silently skip it, as required by the review.

## Draft PR body

The complete draft with the repository template headings is `.agent-artifacts/pgf/b2-pr-body.md`.

UI-Evidence: none -- backend only
Failure-Class: none
