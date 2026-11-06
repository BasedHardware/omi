# B2 implementation result (core implemented; final verification in progress)

Repository: BasedHardware/omi. Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-b2-upstream-keep-clean`. Branch: `lane/pgf-b2`. Initial base: `d47819297e39` (contains B1 #24790 and M9 #24778); rebased onto current main `c536dbb41bbd` after the shared result artifact caused a synthetic-merge conflict. All B2 Python/SQL/test blobs are unchanged by the rebase; only the three shared registry/classification blobs incorporate upstream C1. Both pre-existing app files retain their saved SHA-256 hashes, including the lockfile whose bytes were restored after autostash. No push or PR. No GCP tier or production access used. Pre-existing `app/analysis_options.yaml` and `app/pubspec.lock` changes remain untouched and uncommitted.

## Built

Sticky lazy directory enrollment before platform telemetry; process/Redis/PG routing; fail-closed HTTP 503 and WS 1013; bounded lazy IAM/DSN pools; IO-free plane probe lookup; recorded bucket/revision migration; migrated cell cutover state; reads-open migration with mutation fence; idle-cache invalidation in both persistence seams; required running-marker/fence/drain/cell-purge/directory-purge wipe step; runtime ramp name; three registered flags and 13 setting classifications.

Files committed:

- `.agent-artifacts/pgf-result.md`
- `backend/config/directory_routing.py`
- `backend/database/account_cutover.py`
- `backend/database/cells/serving.py`
- `backend/database/directory/migrations/0002_enrollment.sql`
- `backend/database/directory/router.py`
- `backend/database/directory/store.py`
- `backend/database/directory/wipe.py`
- `backend/database/rollout_cohorts.py`
- `backend/dependencies.py`
- `backend/docs/feature-flag-registry.md`
- `backend/models/account_cutover.py`
- `backend/services/users/account_deletion.py`
- `backend/tests/services/users/test_account_deletion.py`
- `backend/tests/support/lifecycle_writer_inventory.py`
- `backend/tests/unit/test_account_cutover_foundation.py`
- `backend/tests/unit/test_cell_wipe_step.py`
- `backend/tests/unit/test_delete_account_purge_storage.py`
- `backend/tests/unit/test_delete_account_stripe_cancel.py`
- `backend/tests/unit/test_dependency_async_boundaries.py`
- `backend/tests/unit/test_desktop_transcribe.py`
- `backend/tests/unit/test_directory_router.py`
- `backend/tests/unit/test_directory_store.py`
- `backend/tests/unit/test_plane_leak_probe.py`
- `backend/tests/unit/test_sync_transcription_prefs.py`
- `backend/tests/unit/test_verify_token_admin_and_local_dev_gating.py`
- `backend/tests/unit/test_ws_auth_handshake.py`
- `backend/tests/unit/test_ws_auth_rejection_logging.py`
- `backend/utils/account_cutover/access.py`
- `backend/utils/account_cutover/control.py`
- `backend/utils/account_cutover/coordinator.py`
- `backend/utils/account_cutover/fence.py`
- `backend/utils/account_cutover/state.py`
- `backend/utils/account_cutover/telemetry.py`
- `backend/utils/other/endpoints.py`
- `backend/utils/other/plane_routing.py`
- `config/deployment-setting-classification.json`
- `config/feature-flags.yaml`

## Deviations and reasons

- Idle bits are set only for generation-zero universally open records with no configured minimum build. Caching open bridge records with a positive generation would bypass the existing generation-header check; caching a platform-dependent upgrade decision would bypass the build floor. These retain the authoritative read. Redis loss still adds a read and never opens a paused account.
- Existing bridge coordinator callers/tests now pass `data_plane='legacy'` explicitly; the existing bridge convenience entrypoint also supplies it. `begin` itself defaults to cell as specified. No compatibility wrapper was added.
- `get_current_user_uid_ws` is synchronous in this base; it resolves synchronously in FastAPI's dependency thread pool. The two actual async WS dependencies offload on db_executor.
- Real Postgres was initially unavailable (9 router/wipe cases and 9 directory cases skipped). Installed `pgserver==0.1.4` only into this worktree's test venv and reran with `OMI_REQUIRE_STORE_BACKENDS=postgres`; the final Postgres cases pass without skips. No dependency/lock files changed.

- Probe lookup checks the already-loaded router in `sys.modules` rather than eagerly importing serving code. The eager graph entered a jobstore initialization cycle in the real worker and a shadow-planning wall-budget failure also appeared in the broad run. The latter passes in replay; its timing causality is not independently proven. The pinned baseline passes; current code failed the worker repeatably; the lazy lookup fixes both original suites without changing jobstore or weakening tests. Missing/partial-module tests preserve the no-IO/no-raise probe contract.
- Cell kind is sticky when either the request or existing record is cell, including same-state refreshes; a later legacy request cannot reintroduce a generation bump.

- Additional isolated caller fixtures migrated under the user-authorized exception: storage purge, Stripe cancellation, desktop transcription, WS handshake, WS rejection logging, token/admin/local gating, and sync transcription preferences. These stub the new directory collaborator at their existing persistence boundary, with routing off, and retain their existing behavioral assertions.
- Local native setup: `uv pip install --python backend/.venv/bin/python pgserver` supplies real local PG. The installed `/opt/homebrew/lib/libopus.dylib` was not found by managed Python's default lookup. A temporary task-only `backend/.venv/lib/python3.11/site-packages/pgf_b2_native_paths.pth` sets `DYLD_LIBRARY_PATH=/opt/homebrew/lib` inside Python startup; this makes real Opus load without a host/global setting or mocked codec.

## Known gaps / required lead actions

- Runtime bindings are pending: the brief forbids guessing PG host/database/IAM users and requires values from the deploy owner; none were supplied. The base now generates `backend/deploy/runtime_env.yaml` from files outside B2's exact file list. A clarification asks for values and permission to update owning compose sources. No guessed or generated-only manifest edits made; the new binding validator fixtures also remain unimplemented. This leaves acceptance criterion 8 incomplete. ANX ask: `event:ev_77757863d2f3cbfc70593225b023691f`. Its answer waiter exited with HTTP 401 (expired/revoked token); no answer was retrieved and no credentials changed.
- No loopback Firestore emulator was available: both named integration suites skipped, not verified.
- No provisioning, deployment, positive ramp, prod connection-budget measurement or serving-domain integration authorized. W5 must gate before its first 1% enrollment. The PR draft records the connection arithmetic and gate.
- Lead owns the separate INV-CUTOVER-1 revision note for `migrated`; invariant files remain untouched.

- The caller sweep found the explicit executor-call witness `backend/tests/unit/test_dependency_async_boundaries.py`; updated its stub and expected calls, and added a resolver event-loop responsiveness test under the user-authorized witness exception.

- The lifecycle-writer inventory now declares the new wipe result statuses (`noop`, `absent`, `purged`); its full contract passes 1,694 tests. This uses the explicitly authorized support-witness exception.

## Verification

Every command below ran through `/Volumes/Ephemeral/scratch/pgf-b2-test`, which removes `GOOGLE_APPLICATION_CREDENTIALS`, every `CLOUDSDK_*` variable, `SERVICE_ACCOUNT_JSON`, and `FIREBASE_AUTH_CREDENTIALS_PATH`, uses this worktree's backend/.venv Python, and uses `omi-heavy run --` for heavy runs. Root-relative paths unless a command starts with `cd backend`.

| Exact command | Result |
| --- | --- |
| `bash backend/test-preflight.sh` | 17 pass, 9 optional warnings, 0 fail |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_directory_router.py tests/unit/test_cell_wipe_step.py -q` | Initial 17 pass, 9 skip; final with `OMI_REQUIRE_STORE_BACKENDS=postgres`: 28 pass, 0 skip; post-type-fix rerun also 28 pass |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_account_cutover_foundation.py tests/unit/test_plane_leak_probe.py -q` | Initial 72 pass; after T3 additions 79 pass; upgrade-floor guard: 80 pass; persisted-cell-kind: 81 pass; final lazy probe/missing-router guard: 82 pass |
| `cd backend && .venv/bin/python -m pytest tests/services/users/test_account_deletion.py tests/unit/test_account_deletion_single_executor.py -q` | 106 pass |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_directory_store.py -q` | Initial 9 skip (no local PG); final standalone rerun with required Postgres: 9 pass, 0 skip |
| `cd backend && OMI_REQUIRE_STORE_BACKENDS=postgres .venv/bin/python -m pytest tests/unit/test_directory_router.py tests/unit/test_cell_wipe_step.py tests/unit/test_directory_store.py -q` | 35 pass, 0 skip (before 2 additional IAM pool cases) |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_batch_ramp.py tests/unit/test_ramp_controller.py tests/unit/test_mcp_streamable_http.py tests/unit/test_sync_worker_execution.py -q` | 408 pass |
| `cd backend && .venv/bin/python -m pytest tests/integration/test_bpp_generation_fence_emulator.py tests/integration/test_stuck_backfill_emulator.py -q -rs` | 107 skip, loopback Firestore emulator unavailable |
| `python3 scripts/render_feature_flag_registry.py --as-of 2026-11-06 && python3 scripts/check_feature_flag_registry.py` | Pass after correcting placement of new entries under flags (two initial renderer errors: entries were placed under retired/ignore) |
| `bash backend/scripts/pre-deploy-check.sh` | Pass: 36 source-admission tests + 456 deploy tests; runtime manifest unchanged |
| `python backend/scripts/scan_async_blockers.py --dirs backend/routers backend/utils` | Pass (exit 0) |
| `black --line-length 120 --skip-string-normalization <changed Python files>` | Pass; commit hook pinned formatter also passes (initial `.venv/bin/python -m black` unavailable; used installed black CLI) |
| `scripts/pr-preflight --suggest` | Pass, demands INV-CUTOVER-1; draft also cites INV-DATA-1 and wipe-triggered INV-MEM-3 |
| `bash backend/scripts/run-unit-ci.sh --changed-files /Volumes/Ephemeral/scratch/pgf-b2-changed-files.txt` (with `BACKEND_UNIT_FILE_BUDGET_SECONDS=900`) | First attempt: stopped before tests, 2 router type errors (defensive row validation and spec-required private normalizer reuse). Corrected full type-check: 0 errors, 74888 warnings. Retry completed on the initial base: 2669 file sessions, 2656 nonfailing files, 12 failed/error files and 1 file timeout (13 nonzero total); exit 1. Repaired and diagnostic replays are separate below. The broad run spans intermediate B2 commits; it is not a frozen-final-tree green run |
| `OMI_PR_BODY_FILE=/Volumes/Ephemeral/scratch/pgf-b2-pr-body.md BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight` | First run: 44 checks pass, 0 checks fail; overall FAIL because I edited tracked files during its parallel run. Other attempts were canceled for scoped corrections. Frozen attempt on the old base: 25 checks pass, 1 fails, 3 canceled after first failure, 15 not started; the failure is a synthetic-merge conflict on the shared result report after main advanced. Rebased onto c536dbb41bbd; a fresh frozen rerun is pending. |

Named keep-green witness sweep: one `cd backend && .venv/bin/python -m pytest tests/unit/<name>.py -q` process per brief witness. All 19 files finished: 1402 passed, 1 skipped, 0 failed. The one referral skip is intentional: the two-purchase first-claim case has no unconsumed slot.

| `<name>` | Pass | Skip |
| --- | ---: | ---: |
| `test_finalization_replay_exhaustion` | 56 | 0 |
| `test_mcp_streamable_http` | 270 | 0 |
| `test_fsr_scope_opener` | 20 | 0 |
| `test_sync_worker_execution` | 19 | 0 |
| `test_sync_v2` | 175 | 0 |
| `test_sync_cloud_tasks` | 208 | 0 |
| `test_listen_finalization_cloud_tasks` | 222 | 0 |
| `test_conversation_quiet_finalization` | 65 | 0 |
| `test_audio_merge_destructive_deferral` | 8 | 0 |
| `test_audio_merge_tasks` | 23 | 0 |
| `test_playback_idempotency` | 62 | 0 |
| `test_recovery_discard_pipeline` | 34 | 0 |
| `test_repeat_work_cuts` | 37 | 0 |
| `test_referral_campaign_money_review` | 31 | 1 |
| `test_sync_audio_merge_job_tombstone_guard` | 10 | 0 |
| `test_batch_ramp` | 24 | 0 |
| `test_ramp_controller` | 95 | 0 |
| `test_batch_ramp_deploy` | 18 | 0 |
| `test_cell_store_conformance` | 25 | 0 |

Caller search includes `backend/tests/support`, `backend/tests/routers`, all coordinator begin callers, auth paths, ramp readers and purge-shape witnesses; no jobstore, .github, or testing/store_fixtures.py edits.

Product code frozen at `9bda55ffb323` (same Python/SQL blobs as pre-rebase `86676e802de4`); only handoff/report metadata may be finalized after the frozen preflight completes.

ANX outcome note: `event:3aa44637-2cff-47c7-a4ac-616b4178fd57` on `card:backend-target-architecture`, using the anx-participant skill.

Additional exact diagnostic/regression commands:

| Command | Result |
| --- | --- |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_dependency_async_boundaries.py -q` | 12 pass; witness migrated, including event-loop responsiveness |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_batch_pipeline_runtime.py -q` | Before lazy probe fix: 1 fail, 54 pass (twice: full selector and isolated replay); after: 55 pass |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_batch_pipeline_shadow_projection.py -q` | Full selector before lazy fix: 1 fail, 7 pass; after: 8 pass |
| `backend/.venv/bin/python /Volumes/Ephemeral/scratch/pgf-b2-baseline-tests.py backend/tests/unit/test_batch_pipeline_runtime.py -q` | Baseline production source import overlay: 55 pass; final baseline pinned to d47819297e39, without modifying the worktree |
| `cd backend && .venv/bin/python -m pyright utils/account_cutover/state.py --pythonpath .venv/bin/python` | 0 errors, 0 warnings |
| `cd backend && .venv/bin/python -m pyright utils/account_cutover/state.py utils/other/plane_routing.py --pythonpath .venv/bin/python` | Final delta: 0 errors, 0 warnings |
| `scripts/pr-preflight --pr-body-file /Volumes/Ephemeral/scratch/pgf-b2-pr-body.md --metadata-only` | Pass |

More caller/environment verification (one pytest process per file):

| Exact command (from backend) | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests/unit/test_delete_account_purge_storage.py -q` | 8 pass after new wipe-module stub registration; original full run had setup errors |
| `.venv/bin/python -m pytest tests/unit/test_delete_account_stripe_cancel.py -q` | 3 pass after new wipe-module stub registration; original full run had setup errors |
| `.venv/bin/python -m pytest tests/unit/test_desktop_transcribe.py -q` | 64 pass, including 5 slow cases; original full selector had 59 setup errors/5 deselected |
| `.venv/bin/python -m pytest tests/unit/test_ws_auth_handshake.py -q` | 24 pass |
| `.venv/bin/python -m pytest tests/unit/test_ws_auth_rejection_logging.py -q` | 16 pass |
| `.venv/bin/python -m pytest tests/unit/test_verify_token_admin_and_local_dev_gating.py -q` | 9 pass |
| `.venv/bin/python -m pytest tests/unit/test_sync_transcription_prefs.py -q` | 58 pass |
| `.venv/bin/python -m pytest tests/unit/test_empty_capture_recovery.py -q` | Initial full run: 7 fail/61 pass, missing native Opus discovery; local library bootstrap replay: 68 pass |
| `.venv/bin/python -m pytest tests/unit/test_executors.py -q` | 2 cold-import timeouts/34 pass, reproduced on current code and pinned baseline |
| `backend/.venv/bin/python /Volumes/Ephemeral/scratch/pgf-b2-baseline-tests.py backend/tests/unit/test_executors.py -q` (root) | Same 2 failures/34 pass on baseline production modules pinned to d47819297e39 |
| `.venv/bin/python -c 'import openai; import utils.llm.gateway_error_contract; import pytest; raise SystemExit(pytest.main(["tests/unit/test_executors.py", "-q"]))'` | 36 pass; dependencies warmed outside test-call budget; no source/assertion changes |

Additional broad-selector qualifications (original assertions and budgets retained):

| Exact command | Result |
| --- | --- |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_lifecycle_state_table_writers.py -q` | 1694 pass after registering new wipe return statuses in the support inventory |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_live_evidence_settlement.py -q` | 1 concurrent-CAS timing failure, 43 pass in full and isolated background runs |
| `backend/.venv/bin/python /Volumes/Ephemeral/scratch/pgf-b2-baseline-tests.py backend/tests/unit/test_live_evidence_settlement.py -q` | Pinned baseline production import overlay: 44 pass |
| `backend/.venv/bin/python /Volumes/Ephemeral/scratch/pgf-b2-baseline-tests.py backend/tests/unit/test_live_router_hardening.py -q` | Pinned baseline production import overlay: 158 pass |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_live_evidence_settlement.py::test_concurrent_cas_cannot_spend_a_user_budget_twice -q && .venv/bin/python -m pytest "tests/unit/test_live_router_hardening.py::test_write_result_identity_change_stops_cleanup_and_new_scope_writes[exec]" -q` (through `omi-heavy run --no-priority --`) | Both cases pass: 1 + 1; the bulk run had 1 failure/157 pass in the hardening file. Isolation and priority both changed, so this supports scheduling sensitivity without uniquely proving its cause. |

The raw broad selector retains its original failing results even where repaired or diagnostic replays pass. These replays are separate evidence, not a green full-suite claim.

Final diagnostic replays before rebasing (no assertions or intrinsic deadlines changed):

| Exact command (from backend; `omi-heavy run --no-priority --`) | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests/unit/test_record_seal_cluster_repair.py -q` | 89 pass; original background run had 1 fail/88 pass at the child checkpoint deadline |
| `.venv/bin/python -m pytest tests/unit/test_executors.py -q && .venv/bin/python -m pytest tests/unit/test_live_evidence_settlement.py -q && .venv/bin/python -m pytest tests/unit/test_live_router_hardening.py -q` | 36 + 44 + 158 pass; full files, separate Python processes, no dependency prewarm |
| `BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/pgf-b2-late-failures.txt BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_FAST_UNIT_WARN_SECONDS=0.1 BACKEND_FAST_UNIT_FAIL_SECONDS=1.0 BACKEND_PYTEST_FILE_ISOLATION=1 BACKEND_PYTEST_MARK_EXPR="not integration and not slow" BACKEND_PYTEST_XDIST=auto BACKEND_PYTEST_WORKERS=1 PYTHON=.venv/bin/python bash test.sh` | Vision stream: 11 pass (original 1 fail/10 pass at 50 ms health budget). Cross-service deploy contract: original 900s timeout; this replay was deliberately stopped for the rebase and is pending a new replay. File list contains exactly test_vision_stream_async.py and test_cross_service_deploy_contract.py. |

## Draft PR body

## What changed and why

Add sticky directory enrollment and fail-closed request resolution, generation-zero cell cutovers, and the required fenced cell/directory account-wipe step. Ships with DIRECTORY_ROUTING_MODE=off and new-owner-cell1 at zero; B2 authorizes no positive serving ramp. Domain adapters and traffic migration remain W5 work. Runtime bindings and their validator fixtures are incomplete pending deploy-owner values and scope authorization; this draft is not merge-ready.

## Product invariants affected

INV-CUTOVER-1, INV-DATA-1, INV-MEM-3. The account-wipe step also touches INV-MEM-3: canonical purge failures stay required failures; no historical fallback is added. Extend the existing control record/projection; bridge generation fences, auth/control reachability, destination-binding honesty, and legacy write fencing remain. Migrating permits reads and denies mutations; migrated is open on the directory plane. Lead must schedule the separate locked-invariant revision note for the migrated state.

## How it was verified

Local hermetic checks only, with GOOGLE_APPLICATION_CREDENTIALS and all CLOUDSDK_* variables removed. No GCP tier used; no production access, API calls, provisioning, rollout or deployment.

- backend/test-preflight.sh: 17 pass, 9 optional warnings, 0 fail.
- Postgres router/wipe/store suites: 35 pass; final router/wipe with IAM-pool cases: 28 pass. Real local pgserver, synthetic owners, separate databases; no skips.
- Account cutover + plane-leak probes: final 82 pass, including cached-bit/new-upgrade-floor, persisted-cell-kind and missing/partial-router regressions.
- Account deletion + single executor: 106 pass.
- Batch/ramp/MCP/sync-worker witness command: 408 pass.
- All 19 named witness files: 1,402 pass, one intentional skip. Registry render/check passes; hermetic pre-deploy check: 36 source-admission and 456 deploy tests pass on the initial base. Full type-check: zero errors. The initial-base 2,669-file selector exits 1 with 13 nonzero files (12 failures/errors, one 900s timeout); repairs and separate diagnostic replays are detailed in the result report. Full normal-priority replay files pass 36 executor, 44 live-evidence, 158 live-router and 89 checkpoint tests without deadline/assertion changes. No frozen-final-tree full-suite green claim. Rebased onto c536dbb41bbd to resolve the shared result-artifact merge conflict; final preflight and post-rebase core/deploy qualification are pending.
- Firestore emulator integrations: 107 skipped because no loopback emulator was running; these are not acceptance evidence.

Operations runbook:

1. Merge B1 (#24790) then B2; deploy B2 with routing off everywhere. Apply `python -m database.directory migrate` on staging before mode turn-on; cell migrations are unchanged.
2. Deploy-before-write (O4): write the new-owner-cell1 _ramp percent only after every reader knows the name: backend, backend-listen, pusher, backend-sync and notifications-job. Use backend/scripts/rollout/ramp_set.py. Older readers reject the entire unknown-name document and freeze other ramps at last-known-good.
3. Deploy-before-enroll (O6): all five plane-aware services (backend, backend-listen, pusher, backend-sync, backend-sync-backfill) must run B2 before routing mode changes. Positive enrollment is gated on W5 adapters/readers, plane-leak zero, wipe coverage and connection budget before 1%.
4. Connection budget: at configured pool size 2 the upper bound added by each serving instance is 2 directory + 2 cell = 4 connections; total incremental bound is `4 * sum(max instances across the five serving surfaces)`, in addition to jobstore/admin/other clients. Normal auth creates only directory connections; cell pool first opens on purge. Actual fleet counts and prod-jobs max_connections are unmeasured here (no prod authorization); W5 1% remains blocked until the owner verifies headroom or supplies a pooler.
5. Rollback: set DIRECTORY_ROUTING_MODE=off (directory rows inert; cell wipe no-op). Ramp zero stops new cell enrollment without moving enrolled owners. Off is a pre-serving rollback only; after W5 serves cell owners, never route them back without its migration ceremony.

## Tests

Core coverage: asynchronous auth boundary witness updated for directory resolution and event-loop responsiveness; sticky enrollment at 0/100%, existing-owner protection, concurrency, cache tiers and outage paths, off-mode no resources, IAM pool bounds, HTTP/WS retryable mapping, cutover graph and generation semantics, idle-bit invalidation in both persistence seams, directory fence/drain/purge ordering and crash retry, required wipe-step failures.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none
