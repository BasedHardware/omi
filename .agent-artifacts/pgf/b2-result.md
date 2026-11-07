# B2 fix round 1 implementation result

Repository: BasedHardware/omi. Worktree: /Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-b2-upstream-keep-clean. Branch: lane/pgf-b2. Rebased onto origin/main 4b1c40b5ef03242b82013a64c1dc941728715bab before implementation. No push, PR, deploy, GCP tier or production access. The pre-existing app/analysis_options.yaml and app/pubspec.lock edits are preserved byte-for-byte and uncommitted.

Source implementation is committed at `6c194bfa7d35f410efac6eb03bcbe5731871b750`. Frozen preflight passed all 46 checks on this product tree. Final source selector coverage is exact: 186 checkpointed + 2491 resumed = all 2677 unique selected files, with no omitted or duplicated path. Result: **2670 nonfailing file sessions, 7 nonzero files; resumed runner exit 1**. No full-suite green claim is made. Qualification timestamp: 2026-11-06T21:45:39.447640+00:00.

## Built

Full B2 foundation: sticky directory routing/enrollment, lazy bounded pools, auth dependency resolution, generation-zero cell cutover extension, required fail-closed cell/directory wipe, ramp registration and configuration classification.

Round-1 fixes: Redis epochs with atomic idle publication and pre/post-commit deletion, in-flight writer guard, random epoch initialization across key loss, authoritative reads on Redis outage, and refusal to commit an unfenced cutover state write. Cell mutations, replay, cursors and epoch changes require an existing live space head. Enrollment creates heads explicitly; wipe tombstones under the same lock before drain/purge and retains the tombstone. Added real Postgres regressions including independent-process writes after purge and resolver interleavings. Invalid directory modes map to retryable 503 / WS 1013; cell is required on directory enrollment; duplicate fence docstring merged; generated registry has only B2 rows relative to the rebased base.

Files in the B2 branch (excluding preserved app edits and the restored shared report):

- `backend/config/directory_routing.py`
- `backend/database/account_cutover.py`
- `backend/database/cells/errors.py`
- `backend/database/cells/feed.py`
- `backend/database/cells/migrations/0002_write_fence.sql`
- `backend/database/cells/purge.py`
- `backend/database/cells/serving.py`
- `backend/database/cells/store.py`
- `backend/database/directory/migrations/0002_enrollment.sql`
- `backend/database/directory/router.py`
- `backend/database/directory/store.py`
- `backend/database/directory/wipe.py`
- `backend/database/rollout_cohorts.py`
- `backend/dependencies.py`
- `backend/docs/feature-flag-registry.md`
- `backend/models/account_cutover.py`
- `backend/scripts/runtime_env_validation/manifest.py`
- `backend/services/users/account_deletion.py`
- `backend/tests/services/users/test_account_deletion.py`
- `backend/tests/support/lifecycle_writer_inventory.py`
- `backend/tests/unit/test_account_cutover_foundation.py`
- `backend/tests/unit/test_backend_runtime_env_validator.py`
- `backend/tests/unit/test_cell_store_conformance.py`
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

- `.agent-artifacts/pgf/b2-result.md` (this report)
- `.agent-artifacts/pgf/b2-pr-body.md` (standalone draft)

Round-1 source commits (all local, not pushed):

- `df457294d67 feat(cutover): guard idle admission with write epochs`
- `12b4de66a49 feat(cells): retain a durable owner wipe write fence`
- `8c7eb50f198 test(deploy): reject partially enabled directory routing`
- `559690344f2 test(deploy): guard inherited routing configuration`
- `6c194bfa7d35 test(deploy): fence routing activation across the environment`

## Deviations and rulings

- fix-r1 supersedes the original request to write `.agent-artifacts/pgf-result.md`. That shared path is restored from origin/main; its branch diff is empty. Reports live under `.agent-artifacts/pgf/` instead.
- D5 is explicitly waived by the lead: ship dark with no real runtime_env PG bindings. Provisioning is gated on N2 before the first 1% ramp. The existing runtime deploy validator rejects partial enablement, with positive/negative fixtures for both environments and all five surfaces. CELLS bindings are required on all enrollment surfaces because enrollment now creates cell heads explicitly. No identities or infrastructure values were guessed. The earlier ANX ask `event:ev_77757863d2f3cbfc70593225b023691f` is superseded; it is no longer a B2 blocker.
- The fix brief authorizes a small B1 change: added cells/0002_write_fence.sql, explicit enrollment and the retained space-head tombstone, plus conformance/caller updates. No edits under database/jobstore/, .github/, or testing/store_fixtures.py.
- A pre-commit epoch increment alone leaves a reader-starts-during-commit race. The pending-writer guard and post-commit epoch advance close that window, also across concurrent writers. Redis must accept the write fence before a cutover state commit. A crashed pending marker disables caching rather than reopening traffic; authoritative reads continue.
- The W6 cutover driver is out of scope. Its explicit quiesce requirement is CELL_CUTOVER_QUIESCE_SECONDS=65, greater than the 60-second idle TTL, with a regression guard and runbook instruction; the ordinary wipe drain remains independently bounded at 0..60 seconds.
- Ran the requested registry renderer at 2026-11-06, then regenerated at the rebased base's 2026-11-05 date to remove unrelated overdue churn (NB8). Both registry checks passed.

## Exact verification commands and counts

Every test command is prefixed by `/Volumes/Ephemeral/scratch/pgf-b2-test`, a task-local runner that unsets GOOGLE_APPLICATION_CREDENTIALS, all CLOUDSDK_* vars, SERVICE_ACCOUNT_JSON and FIREBASE_AUTH_CREDENTIALS_PATH and selects this worktree's backend/.venv. Heavy commands are then wrapped with `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 --` (the first two focused runs used its default wait). No live checks were requested or run. Native Opus discovery in this worktree required a temporary `.venv`-only `.pth` hook that adds `/opt/homebrew/lib` to `DYLD_LIBRARY_PATH`; the existing `libopus.dylib` and a real `opuslib.Encoder` were verified. No dependency lock or host configuration was changed. The owned `.pth` hook was removed after the final test command; the final cwd/process inventory found no remaining test server or watcher.

| Exact command (repository root unless stated) | Result |
| --- | --- |
| `cd backend && bash test-preflight.sh` | 17 passed, 9 optional warnings, 0 failed |
| `cd backend && OMI_REQUIRE_STORE_BACKENDS=postgres .venv/bin/python -m pytest tests/unit/test_directory_router.py tests/unit/test_cell_wipe_step.py tests/unit/test_directory_store.py tests/unit/test_cell_store_conformance.py -q` | 68 passed, 0 skipped; real local pgserver Postgres |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_account_cutover_foundation.py tests/unit/test_plane_leak_probe.py -q` | 88 passed |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_backend_runtime_env_validator.py -q` | Initial 193 passed; final 198 validator cases are included in the final 503-test deploy run |
| `cd backend && .venv/bin/python -m pytest tests/services/users/test_account_deletion.py tests/unit/test_account_deletion_single_executor.py -q` | 106 passed |
| `cd backend && .venv/bin/python -m pytest tests/unit/test_batch_ramp.py tests/unit/test_ramp_controller.py tests/unit/test_mcp_streamable_http.py tests/unit/test_sync_worker_execution.py -q` | 408 passed |
| `cd backend && .venv/bin/python -m pytest tests/integration/test_bpp_generation_fence_emulator.py tests/integration/test_stuck_backfill_emulator.py -q -rs` | 107 skipped: no loopback Firestore emulator; not acceptance evidence |
| `python3 scripts/render_feature_flag_registry.py --as-of 2026-11-06 && python3 scripts/check_feature_flag_registry.py` | Passed |
| `python3 scripts/render_feature_flag_registry.py --as-of 2026-11-05 && python3 scripts/check_feature_flag_registry.py` | Passed; only 8 added B2 registry lines relative to origin/main |
| `bash backend/scripts/pre-deploy-check.sh` | Initial 498 + 36 passed; inherited-mode rerun 499 + 36 passed; final activation guard 503 + 36 passed |
| `python3 backend/scripts/scan_async_blockers.py --dirs backend/routers backend/utils` | Passed; zero blocking findings |
| `black --line-length 120 --skip-string-normalization <changed Python files>` | Passed; pinned commit hook also passed |
| `scripts/pr-preflight --suggest` | Passed; identified required invariant citations and selected gates |
| `scripts/pr-preflight --base 4b1c40b5ef03242b82013a64c1dc941728715bab --pr-body-file .agent-artifacts/pgf/b2-pr-body.md --metadata-only` | 4 checks passed, exit 0, 20.10 seconds |
| `BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash backend/scripts/run-unit-ci.sh --changed-files /Volumes/Ephemeral/scratch/pgf-b2-r1-changed-files.txt` | Completed all 2677 file sessions at source 559690344f2: 2666 nonfailing, 11 nonzero; detailed matrix below |
| `OMI_PR_BODY_FILE=.agent-artifacts/pgf/b2-pr-body.md BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight` | Final frozen source 6c194bfa7d35: 46 passed, 0 failed, exit 0, 470.69 seconds. Earlier source 559690344f2 also passed 46 checks (957.64 seconds). One earlier queued attempt was stopped before execution to add the inherited-ConfigMap guard |

Raw direct-file pyright diagnostic initially reported 30 errors: one new binding-key type issue (fixed), with 29 existing script-module private-import/optional/unused diagnostics outside the normal typecheck boundary. The required CI typecheck passed with 0 errors, 75154 warnings; the direct diagnostic is not a green typecheck claim.

Named keep-green witnesses (one pytest process per file): **3073 passed, 1 intentional referral skip**. In command order, pass counts were 56, 270, 20, 19, 175, 208, 222, 65, 8, 23, 62, 34, 37, 31 (plus one skip), 10, 24, 95, 18, 1696. The full command is `cd backend && for name in test_finalization_replay_exhaustion test_mcp_streamable_http test_fsr_scope_opener test_sync_worker_execution test_sync_v2 test_sync_cloud_tasks test_listen_finalization_cloud_tasks test_conversation_quiet_finalization test_audio_merge_destructive_deferral test_audio_merge_tasks test_playback_idempotency test_recovery_discard_pipeline test_repeat_work_cuts test_referral_campaign_money_review test_sync_audio_merge_job_tombstone_guard test_batch_ramp test_ramp_controller test_batch_ramp_deploy test_lifecycle_state_table_writers; do .venv/bin/python -m pytest tests/unit/$name.py -q || exit; done`. B1 cell conformance ran in the required real-PG group above.


### Broad selector and replays

The first selector completed **all 2677 files**, without a B2 test failure; its exit was 1 because of the following 11 nonzero file sessions. No timeout, assertion, CPU budget, or retry policy was weakened. A later passing replay does not erase the raw first-run failure or prove a scheduling root cause.

| File (`backend/tests/unit/`) | Initial failure | Follow-up |
| --- | --- | --- |
| `test_batch_pipeline_shadow_projection.py` | One per-test time-budget failure; 7 passed | Current and baseline-overlay runs: 8 passed each; guarded replay: 8 passed |
| `test_batch_pipeline_worker_bundle.py` | One 3-second event wait; 48 passed | Current and baseline-overlay runs: 49 passed each; guarded replay: 49 passed |
| `test_daily_summary_monitoring_contract.py` | One static assertion; 6 passed | Test and input manifest match rebased main; offenders `omi-enrichment-queue-depth-page` and `omi-incluster-guard-unsafe-page` are unchanged from main. Outside B2 boundaries |
| `test_executors.py` | Two 2-second future timeouts (lead-known main red) | Guarded replay: 36 passed |
| `test_fleet_deployment.py` | One fake-gcloud subprocess 30-second timeout | Guarded replay: 11 passed |
| `test_cross_service_deploy_contract.py` | 900-second file timeout, status 124 | Lead-known main red; budget retained, no repeated 900-second diagnostic run |
| `test_live_cap_codec.py` | One ffmpeg 20-second timeout; 13 passed | Guarded replay: 14 passed |
| `test_live_stt_language_policy.py` | One 50-ms background telemetry observation; 39 passed | Guarded replay: 40 passed |
| `test_migrate_pinecone_partitions.py` | One CLI 10-second shutdown timeout; 25 passed | Guarded replay: 26 passed; intended loopback/dev safety error was emitted, no production request |
| `test_qualify_parakeet_route.py` | One fake-WebSocket startup 10-second timeout | Guarded replay: 34 passed |
| `test_soniox_race_checkpoints.py` | Two 100-ms asyncio waits; 39 passed | Guarded replay: 41 passed |

Guarded replay command: `BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/pgf-b2-r1-guarded-replays.txt BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_PYTEST_WORKERS=1 bash backend/test.sh`; **259 passed across 9 file sessions, exit 0**. The list contains the nine replayed files above. It preserves file isolation, the standard `not integration and not slow` marker expression, and CPU warn/fail budgets 0.1/1.0 seconds. Bare per-file diagnostics additionally passed fleet (11), codec (14), language (40), Pinecone (26), executors (36), route qualification (34), and Soniox (41); these are not substitutes for the guarded replay.

Baseline comparison command: `backend/.venv/bin/python /Volumes/Ephemeral/scratch/pgf-b2-r1-baseline-tests.py backend/tests/unit/test_batch_pipeline_shadow_projection.py -q` (and `backend/tests/unit/test_batch_pipeline_worker_bundle.py`), plus the matching current `backend/.venv/bin/python -m pytest ... -q` commands. The helper loaded changed production Python modules from rebased main `4b1c40b5ef03242b82013a64c1dc941728715bab`, without changing the worktree. Both baseline and current passed **57 tests** across those two files. These comparisons demonstrate nondeterminism; they do not establish causal attribution.

Final source selector: `backend/.venv/bin/python backend/scripts/select_backend_unit_tests.py --changed-files /Volumes/Ephemeral/scratch/pgf-b2-r1-admission-delta.txt --output /Volumes/Ephemeral/scratch/pgf-b2-r1-admission-tests.txt` selected all 2677 files again after the final pure manifest-validator change. Enforced typecheck again passed with zero errors. The first 186 file sessions completed with zero failures using four file workers. With the scheduler stopped, all active test children exited naturally; no test case was killed. The checkpointed parent command exited 137 when its stopped scheduler was ended after all active test children had finished; this is an explicit scheduling handoff, not a passing command status. A checkpoint preserved the completed set, then the remaining 2491 files resumed through `BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/pgf-b2-r1-admission-remaining.txt BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_PYTEST_WORKERS=auto bash backend/test.sh`. All source, isolation, markers, budgets and credential scrubbing remain unchanged. Final source selector coverage is exact: 186 checkpointed + 2491 resumed = all 2677 unique selected files, with no omitted or duplicated path. Result: **2670 nonfailing file sessions, 7 nonzero files; resumed runner exit 1**. No full-suite green claim is made.

Final-source nonzero files were `test_daily_summary_monitoring_contract.py` (unchanged static alert-rule assertion), `test_executors.py` (the same two 2-second future waits), `test_fleet_deployment.py` (fake-gcloud subprocess 30-second timeout), `test_cross_service_deploy_contract.py` (900-second budget, status 124), and these three additional files:

| File (`backend/tests/unit/`) | Final selector failure | Follow-up |
| --- | --- | --- |
| `test_soniox_capture_axis_r11.py` | `test_every_socket_diagnostic_fault_preserves_exact_managed_receipt[response]`: 100-ms async queue wait timeout | Guarded replay: 24 passed |
| `test_soniox_wire_rollout_metrics.py` | `test_receive_teardown_settles_metrics_without_anchoring_later_queued_audio`: 100-ms async wait timeout | Guarded replay: 11 passed |
| `test_speaker_tag_prompts_service.py` | `test_prompt_list_verification_budget_returns_without_empty_cooldown`: background verification worker had not signaled startup | Guarded replay: 58 passed |

All three additional files passed the first full selector and are unchanged from rebased main. The Soniox/listen and speaker-prompt runtime implementations are also unchanged. This is evidence of nondeterminism, not a proved scheduling root cause. Their guarded follow-up command is `BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/pgf-b2-r1-soniox-replays.txt BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_PYTEST_WORKERS=1 bash backend/test.sh`; the list contains the three files above. Assertions and all standard test.sh guards are retained. **93 passed across all 3 guarded file sessions, exit 0** (24 + 11 + 58). No 100-ms wait, assertion, CPU budget or file deadline was weakened.

For exact brief selectors, the separate commands `cd backend && OMI_REQUIRE_STORE_BACKENDS=postgres .venv/bin/python -m pytest tests/unit/test_directory_router.py tests/unit/test_cell_wipe_step.py -q` and the same command with only `tests/unit/test_directory_store.py` passed **31** and **9** tests respectively, without skips.

## Known gaps and integration gates

During the final replay wait, the shared `origin/main` ref advanced to `2f8d8cda2691b82188270ce5286f09f204ed9e70` (PR #24804, monitoring-rule fix). The monitoring assertion above is against the pinned qualification base `4b1c40b5ef03242b82013a64c1dc941728715bab`; it is already fixed on that newer main. This task did not rebase again after freezing and qualifying source `6c194bfa7d35`. The forbidden-path audit uses the pinned merge base and is empty; a two-dot diff against the newer main would misleadingly include its incoming failure-class file.

No provisioning, production measurements, serving-domain integration, migration, positive ramp or deployment was performed. W5 must resolve long-lived WS plane binding (NB2), plane_for's missing/partial-router fallback admission constraint (NB3), and rejected-uid negative-cache policy if metrics warrant it (NB6). N2 connection headroom/pooler gate precedes 1%; all _ramp readers deploy before the new name is written; all five surfaces deploy before enrollment. Lead owns the separate migrated invariant revision note. A local green suite does not establish deployed acceptance.

D5 ruling recorded at ANX event `9664f09c-f585-4eed-aa2b-6566e5ac711f`. Attempting withdrawal of the superseded older ask returned owner-only 403; no identity or access workaround was used. The superseding ruling was recorded instead. Final local outcome recorded at [ANX event c1ef3239-3ef1-4148-a2d3-cd0e7d4e7969](https://anx.scalingforever.com/o/david-zhang/w/omi/r/event:c1ef3239-3ef1-4148-a2d3-cd0e7d4e7969). The parent program was not marked done and no broader ownership was assumed.

## Draft PR body

## What changed and why

Add sticky directory enrollment before signup telemetry, fail-closed HTTP/WS plane resolution, generation-zero cell cutovers, and the required cell/directory account-wipe step. Routing ships off; this PR authorizes no cell serving or positive enrollment ramp.

Round-1 review fixes prevent stale open cutover reads from publishing an idle cache entry and prevent stale routes from recreating wiped cell data. Redis epochs plus a pending-writer guard protect both Firestore write seams; the cell space-head lock guards mutation/replay, cursor, epoch, enrollment and purge paths. Wipe retains a content-free tombstone and retries safely after fencing.

D5 waiver (lead fix-r1 ruling): B2 ships dark with no runtime_env PG bindings. Exact host/database/IAM identities belong to the provisioning PR, gated on the N2 connection-budget measurement. The deploy validator now rejects partial enablement across backend, backend-sync, backend-sync-backfill, backend-listen and pusher. DIRECTORY and CELLS bindings are required on every surface because every enrollment dependency can initialize a cell head; backend also runs account wipe. DSN or complete IAM bindings and explicit pool sizes 1..2 are supported. No infrastructure values were guessed. The earlier ANX values ask `event:ev_77757863d2f3cbfc70593225b023691f` is superseded by this ruling.

## Product invariants affected

INV-CUTOVER-1, INV-DATA-1, INV-MEM-3. Extend the existing cutover control record rather than introducing another authority. Bridge generation fencing, auth/control reachability and destination-binding honesty remain intact. Migrating allows reads and denies mutations; migrated allows cell traffic at generation zero while legacy writes remain fenced. Cell/directory wipe failures remain required failures before Firestore deletion. The lead owns the separate locked-invariant revision note for migrated; invariant files are unchanged.

## How it was verified

Local tests only, with GOOGLE_APPLICATION_CREDENTIALS and every CLOUDSDK_* variable unset (also SERVICE_ACCOUNT_JSON and FIREBASE_AUTH_CREDENTIALS_PATH). Python is this worktree's backend/.venv (3.11.15); heavy runs use omi-heavy. No GCP tier, production access, or api.omi.me calls. Current round-1 results:

- Real local Postgres: directory router, cell wipe, directory store and cell conformance: 68 passed, no skips.
- Cutover foundation and M9 plane probes: 88 passed.
- Runtime deployment validator, including positive/negative binding fixtures: 198 passed (included in the final 503-test deploy run).
- Registry renderer/checker passed. Final generated output keeps origin/main's as-of date (2026-11-05), removing unrelated overdue churn; only B2 entries differ.
- Async blocker scan passed with zero findings.
- Deployment verification passed: 503 deploy tests plus 36 source-admission tests. Backend environment preflight: 17 passed, 9 optional warnings, zero failures.
- Enforced backend typecheck passed: zero errors. Frozen local preflight passed all 46 checks in 470.69 seconds; the resulting product tree is committed as 6c194bfa7d35.
- Named witnesses: 3,073 passed, one intentional referral skip; real-PG conformance is included above. The first full 2,677-file selector had 11 nonzero files. Nine passed guarded replays (259 tests); the remaining results are an unchanged main-branch monitoring contract failure and the known 900-second cross-service timeout. The final source selector covered all 2,677 files (checkpoint 186 + resumed 2,491), verified by exact path-set equality: 2,670 nonfailing files and seven nonzero files. Those seven are monitoring contract, executors, fleet deployment, cross-service timeout, Soniox capture-axis, Soniox wire metrics, and speaker prompts. The three additional guarded replays passed all 93 tests (24 + 11 + 58), with standard assertions, 100-ms waits, file isolation and CPU guards intact. No full-suite green claim is made.
- Firestore emulator integration: 107 skipped because no loopback emulator was available; no deployed acceptance is claimed.

The monitoring failure is on the pinned qualification base `4b1c40b5ef03`; PR #24804 fixed it on main while the final replay waited. No second rebase was performed after freezing the qualified product tree.

Exact commands and counts: `.agent-artifacts/pgf/b2-result.md`. `.agent-artifacts/pgf-result.md` matches origin/main and is owned by another PR.

Operations runbook (future authorized provisioning/integration work):

1. B1 (#24790) precedes B2. Deploy B2 with DIRECTORY_ROUTING_MODE off everywhere. Apply directory and cell migrations, including cells/0002_write_fence.sql, on staging before enabling routing. Only enrollment/backfill creates cell heads; writes never auto-create them, and tombstones cannot be revived.
2. O4: write new-owner-cell1 via backend/scripts/rollout/ramp_set.py only after every _ramp reader knows the name (backend, backend-listen, pusher, backend-sync and notifications-job). Older readers reject the whole document and freeze other ramps at last-known-good.
3. O6: all five plane-aware surfaces must run B2 before the first enrollment. The provisioning PR must supply reviewed bindings on all surfaces and pass the new admission validator. W5 adapters/readers, plane-leak zero, wipe coverage and connection budget must be green before the first 1% ramp.
4. Connection budget: with pool sizes 2, each instance adds at most 2 directory + 2 cell connections. Incremental fleet bound = `4 * sum(max instances for the five surfaces)`, plus existing clients. Cell pools open for cell enrollment or wipe. Fleet maxima and database max_connections have not been measured here; N2 must establish headroom or a pooler before 1%.
5. R10/W6: after the cell migration fence, wait CELL_CUTOVER_QUIESCE_SECONDS (65 seconds, strictly greater than the 60-second idle TTL), and drain admitted writers before backfill/flip. The W6 driver is outside this PR. Redis loss disables idle publication and uses authoritative reads; if a write cannot acquire its Redis epoch fence it refuses to commit. A crashed pending writer leaves caching disabled until the operator reconciles that marker against authoritative state; traffic stays authoritative.
6. Rollback before cell serving: routing mode off makes directory rows inert and the cell wipe step a no-op. Ramp zero stops new cell enrollment without moving existing rows. After W5 starts serving cell owners, use its migration ceremony rather than blindly disabling routing.

W5 gates recorded without code changes (flash NB2/NB3/NB6): bind the plane for the lifetime of WebSocket sessions; require auth resolution before relying on plane_for's missing/partial-module fallback; evaluate a short negative cache for rejected uid inputs if metrics justify it. No domain adapter or traffic migration is included here.

## Tests

Deterministic regressions interleave stale read → epoch INCR/Firestore commit/idle DEL → refused late cache publication → denied next mutation, for both write seams. Additional tests cover in-flight/crashed writers, Redis outages and key loss, upgrade/generation checks, and quiesce > TTL. Real Postgres tests cover an independent-process stale writer after purge, a resolver paused across the fence, crash-after-tombstone retry, and no implicit enrollment from mutation/cursor/epoch operations. Deployment fixtures cover both environments, all five surfaces, IAM/DSN/ConfigMap bindings, missing bindings, invalid modes, dark manifests, inherited shared-ConfigMap activation, activation from other environment surfaces, and the actual deploy-validator entrypoint.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## New guards (only when adding a check or ratchet)

The PGF B2 round-1 D5 review identified incomplete deployment admission following B1 #24790 and M9 #24778. This extends the existing runtime-env validation primitive with fleet-wide binding admission and positive/negative fixtures; it adds no parallel checker or workflow.
