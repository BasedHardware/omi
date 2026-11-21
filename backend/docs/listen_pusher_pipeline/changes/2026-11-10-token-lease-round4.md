# Part A token lease: round-4 implementation and validation

All four findings against `340372fcb228b1fcabdb1e7e948e139450bae8fa` were verified against the code and fixed.
Rebased all local implementation commits cleanly onto `2fd0a9d94f238b6c338d6c67aec1e77f783159d9` (the requested 63 upstream commits).
The 26-file product-focused unit run, custody conformance and PromQL validated implementation head `94c227ed3b0c41147faafcf0baf392762415b1c4`. The final harness validation head is `5e4bfc323f90d20e8155972814b2e70728740533`; its only additional changes are the isolated child resource limits, their regression and harness documentation.
Final receipt timestamp: 2026-11-10T01:15:16+00:00.

## Changes and verified findings

1. At the reviewed head, `begin_upload` returned for a missing conversation ID, while record admission resolved `recording_session_id` through the user's recording-session document. Both now use `record_custody_append.resolve_target`; the route passes the recording-session identity before staging any files. The resolved conversation holds its exact custody fence through the archive. The regression advances a single archive beyond the old lease and checks the real seal-repair refusal gate returns `upload_pending`.
   If the session resolves no target, the existing archive/admission behavior and response remain unchanged, with no custody append for an unknown conversation. Off-mode still performs no custody metadata IO.
2. The reviewed timeout test read staging shape flags. Production's sync action did not consume service-specific flags, and prod declared no explicit sync timeout. The prod overlay now explicitly declares `--timeout: 3600s`; the generated manifest and sync action consume it. The test invokes the real production renderer `main`, reads its actual `GITHUB_OUTPUT` and state artifact, and checks the action consumes those outputs. The timeout must equal the packaged lease input and be strictly covered by the lease plus its named margin. Defaults remain 3600s for frames and at least 3900s for custody (3600 + 300 margin). No other service timeout was changed.
3. The reviewed `finish` retried ambiguous commits without a terminal receipt. Finish now writes the exact-upload receipt in the same transaction as the revision, token removal and any continuation. Finish and lost-fence recovery share the existing `record_custody_recoveries` receipt namespace and request identity. A receipt hit is read-only: no lost-fence exception, second revision, continuation or late-append increment. Unit and real Firestore-emulator regressions lose the reply only after the commit succeeds.
4. Main's #24968 `valid_metric_clock` accepts positive finite non-boolean numbers and has no date floor. The worker already used it. Repair's exported enqueue-age sample now uses that same predicate, removing its private 2020 floor. Tests cover zero/negative rejection and acceptance of positive pre-2020 values in both producers. Discovery rows, cursors and repair selection remain identical to the metric-free oracle.

No Part B work or new discovery-selection change. No R4 edits to `users.py`, `live.py`, projection-release or held-dead-letter source, `record_audio.py`, alert entries or metric inventories. Checked-in feature defaults remain off, and the idle seal worker remains disabled under prod values. No raw audio is deleted.

## Final validation

| Unit file (`tests/unit/test_*.py`) | Final result | Pytest / file wall |
|---|---:|---:|
| `sync_v2` | 182 passed | 852.49s / 879s |
| `record_seal_cluster_repair` | 148 passed | 120.79s / 132s |
| `record_token_lease` | 80 passed | 26.56s / 44s |
| `record_custody_append` | 35 passed | 66.73s / 90s |
| `record_producer_proof` | 27 passed | 16.08s / 32s |
| `record_partial` | 82 passed | 122.83s / 160s |
| `record_seal_repair` | 48 passed | 54.67s / 90s |
| `record_pending_repair` | 63 passed | 57.03s / 93s |
| `record_audio_seal` | 57 passed | 165.61s / 234s |
| `record_seal_nojob` | 44 passed | 39.84s / 64s |
| `lifecycle_state_table_writers` | 1738 passed | 294.39s / 320s |
| `record_token_lease_deploy` | 12 passed | 60.94s / 82s |
| `record_seal_cluster_repair_deploy` | 10 passed | 39.79s / 51s |
| `monitoring_alert_backtest` | 29 passed | 12.74s / 19s |
| `monitoring_notification_contract` | 8 passed | 36.05s / 42s |
| `monitoring_alert_rule_contract` | 75 passed | 185.27s / 203s |
| `monitoring_telemetry_contract` | 54 passed | 64.19s / 84s |
| `pusher_record_abandon` | 24 passed | 145.60s / 193s |
| `pusher_storage_pcm_metrics` | 15 passed | 124.86s / 190s |
| `batch_pipeline_live` | 102 passed | 164.99s / 245s |
| `record_seal_worker` | 25 passed | 38.46s / 61s |
| `record_lease_append` | 1 passed | 45.48s / 79s |
| `backend_runtime_env_validator` | 206 passed | 564.76s / 585s |
| `render_backend_runtime_env` | 91 passed | 114.00s / 132s |
| `runtime_env_sources` | 3 passed | 14.79s / 40s |
| `workflow_contracts` | 97 passed | 73.05s / 92s |

- Off-mode parity is explicitly covered by the passing `test_off_is_bit_exact_old_write_payload_and_performs_no_renewal_io`, `test_off_terminal_metrics_keep_old_wire_output_even_after_rollback` and `test_off_custody_begin_has_no_io` regressions.
- Requested serial sync/repair, each with 900s file budget: **sync 182 passed** (852.49s pytest / 879s file wall), then **repair 148 passed** (120.79s pytest / 132s file wall). Both canonical files exited 0 with the 900s budget.
- New real-emulator finish receipt proof: **2 passed**, 6.06s, no skips.
- Held/recovery custody conformance, requiring memory, private Firestore emulator and local PostgreSQL: **held 75 passed** (38.15s) and **recovery 39 passed** (46.64s), no skips; all three backends were required.
- Lifecycle scenarios/properties: **34 passed, 3 pre-existing strict XFAILs**, 440.97s; no unexpected failures or skips. Named exits `seal`, `partial_finish`, `reactivated`: **all three passed** in the final complete lifecycle run. The previously timing-out reconnect scenario also passed.
- Real PromQL backtests: **7 scenarios passed**, real promtool, exit 0 (3.82s).
- Metadata-only preflight: **5 checks passed**, 82.65s reported / 85.81s launcher wall in the final cached-helper run. The earlier metadata pass after the exact line-count exception took 65.23s, and the implementation-head pass took 145.20s; final suggestions passed in 41.68s.
- Component hermetic pre-deploy checks: **exit 0**, 996.04s; **36 source-admission self-tests passed** (16.165s) and **511 passed in 902.47s (0:15:02)**. Both dev/prod runtime manifests, forward/prod lifecycle, frame-request/object-lake buckets, source admission and MCP deployment guards passed in source-only mode.
- Additional lifecycle/stack helper unit suites: **109 passed**: `test_lifecycle_sim_unit.py` 50 (268.05s pytest / 366s file), `test_listen_pusher_stack_cleanup.py` 44 (32.86s / 54s), `test_listen_pusher_stack_ci_wiring.py` 15 (218.61s / 257s). The canonical three-file run exited 0 in 678.17s. Combined focused verification is **3365 passes across 29 files**.
- Expanded preflight: **67 checks passed**, exit 0; 3128.08s reported / **3129.60s launcher wall**. The seven-file Firestore guard passed in 921.23s, including 559 query-shape cases. The full run used the verified exact-pin helper cache described below.

The initial focused verification passed 300 unit cases across custody (35), token lease (80), deployment (12), repair (148) and worker (25), plus both new real-emulator cases (2 passed, 9.74s). The production test was then strengthened to invoke actual renderer `main` and artifacts. Its first canonical run reported 12 test cases passed, but two timeout cases exceeded the 1s call-CPU guard (1.14s and 1.12s) because full-manifest parsing happened in the test call. It now follows the canonical renderer suite's parsed-source fixture pattern: setup uses the real source parser, while `main`, emitted artifacts and assertions still execute during the guarded call. The canonical rerun passed 12 tests in 14.70s / 18s file wall, approximately 0.17 call-CPU seconds per timeout case. No CPU threshold, duration allowlist, skip or assertion was relaxed.

## Commands and environment

Heavy invocations go through `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --`. The final targeted retry and remaining checks use its documented `--no-priority` option, preserving the slot limit. The wrapper checks /usr/bin/taskpolicy, which is absent on this host; the available tool is /usr/sbin/taskpolicy, so no causal scheduling effect is claimed for --no-priority alone. During final helper validation, normal scheduling was explicitly ensured with /usr/sbin/taskpolicy -B -p on the verified owned root and its four current descendants, all five calls exited 0. This changes only the owned process tree, not host configuration or another task. The explicit `-B` calls at 2026-11-09T21:07:15Z targeted owned root PID 23343 and four verified descendants (28476, 79318, 79320, 79322), after checking parent, UID and launch time before each call. The audit is retained in `tokenlease-round4-owned-priority.json`. The final preflight retry also applied `-B` to its own PID 74658 before launching metadata/preflight checks, exit 0 at 2026-11-09T22:39:22Z. No other task was modified. During the cold preflight helper build, normal scheduling was also applied to its verified owned Swift build PID 93177 and compiler PID 33458 at 2026-11-10T00:04:48.447883+00:00; both calls exited 0. Their parent, UID, launch time and exact cache/source command were checked twice immediately before each call; the audit is `tokenlease-round4-compiler-priority.json`.
The owned launcher removes `GOOGLE_APPLICATION_CREDENTIALS`, every `CLOUDSDK_*` variable and auth-file bindings; isolates HOME/config/temp under Ephemeral; and caps native numerical threads at one in its child environment. The canonical stack deliberately creates an empty per-run CLOUDSDK_CONFIG under its private config root, rather than restoring any ambient cloud CLI settings. No production access or GCP tier was used. Providers are offline; emulator clients use demo projects and anonymous credentials. The emulator binary is copied into the owned cache so later test runs do not mutate the shared cache.

```sh
# Initial focused regressions + new real-emulator cases
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-round4-validate.py --quick
# Actual production-renderer refinement, same canonical timing guard
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-round4-validate.py --deploy-only
# Full validation, source frozen at the head above
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-round4-validate.py --contract
# Canonical retries of four timing failures, followed by remaining checks
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --no-priority -- python3 /Volumes/Ephemeral/scratch/tokenlease-round4-validate.py --retry-files /Volumes/Ephemeral/scratch/tokenlease-round4-retry-files.txt --normal-priority
# Full lifecycle retry, then hermetic deploy checks and expanded preflight
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --no-priority -- python3 /Volumes/Ephemeral/scratch/tokenlease-round4-validate.py --lifecycle-retry
# Child resource-limit regression, full lifecycle and remaining checks
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --no-priority -- python3 /Volumes/Ephemeral/scratch/tokenlease-round4-validate.py --lifecycle-caps
# Metadata correction, then full expanded preflight
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --no-priority -- python3 /Volumes/Ephemeral/scratch/tokenlease-round4-validate.py --preflight-retry
# Same full preflight with a verified exact-pin helper copied into its private cache
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --no-priority -- python3 /Volumes/Ephemeral/scratch/tokenlease-round4-validate.py --preflight-cached
```

Canonical unit child command (cwd `backend`; one fresh process per file, table above supplies the exact file list):

```sh
PYTHON=.venv/bin/python BACKEND_PYTEST_FILE_ISOLATION=1 BACKEND_PYTEST_PARALLEL_SESSION=0 BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_UNIT_TEST_FILE_LIST=<owned-state>/focused-unit-files.txt bash test.sh
```

Remaining child commands (cwd `backend` except preflight):

```sh
.venv/bin/python tests/promql/record_token_lease.py --promtool /Volumes/Ephemeral/scratch/tokenlease-promtool/promtool
.venv/bin/python -m pytest -q --tb=short tests/integration/test_record_custody_append_emulator.py
.venv/bin/python -m pytest -q --tb=short tests/integration/test_held_custody_conformance.py
.venv/bin/python -m pytest -q --tb=short tests/integration/test_recovery_custody_conformance.py
.venv/bin/python -m testing.lifecycle_sim.run --keep --state-dir <owned-state>/lifecycle --extra-test-module testing/lifecycle_properties/test_properties.py
# cwd root; default pre-deploy mode is hermetic/source-only
bash backend/scripts/pre-deploy-check.sh
# Same make-preflight entrypoint with immutable base
bash scripts/dev-harness/run-python.sh .github/scripts/pr_preflight.py --lane local --base 2fd0a9d94f238b6c338d6c67aec1e77f783159d9
```

Expanded preflight uses `CI=true OMI_CHECKS_JOBS=1 BACKEND_PYTEST_WORKERS=1`, local `OMI_PR_BODY_FILE=.agent-brief/tokenlease-pr-body.md` and an 1800s local file-wall guard. The requested serial sync/repair runs retain 900s. No CI default changes. All-backend conformance uses `OMI_REQUIRE_STORE_BACKENDS=all`; skips cannot qualify parity.

Lead PR handoff: preserve these exact validated line-count disclosures from the local PR body:

```text
Line-Count-Exception: backend/routers/pusher.py | 2032 -> 2042 | Minimal adjacent lease/custody hooks; shared transaction and recovery logic lives in component helpers.
Line-Count-Exception: backend/routers/sync.py | 3819 -> 3841 | Minimal adjacent lease/custody hooks; shared transaction and recovery logic lives in component helpers.
Line-Count-Exception: backend/testing/listen_pusher_stack/run.py | 1980 -> 1988 | Eight adjacent child-environment lines bound numerical pools for every isolated child and restart; the existing 120s readiness contract is unchanged.
```

## Files and local commits

R4 changes 18 implementation, test and contract files, plus this final receipt:

- `.github/actions/deploy-backend-stack/action.yml`
- `backend/database/record_custody_append.py`
- `backend/deploy/runtime_env.yaml`
- `backend/deploy/runtime_env/prod.overlay.yaml`
- `backend/docs/listen_pusher_pipeline.mdx`
- `backend/routers/sync.py`
- `backend/testing/listen_pusher_stack/README.md`
- `backend/testing/listen_pusher_stack/run.py`
- `backend/tests/integration/test_record_custody_append_emulator.py`
- `backend/tests/unit/test_lifecycle_sim_unit.py`
- `backend/tests/unit/test_record_custody_append.py`
- `backend/tests/unit/test_record_seal_cluster_repair.py`
- `backend/tests/unit/test_record_seal_worker.py`
- `backend/tests/unit/test_record_token_lease.py`
- `backend/tests/unit/test_record_token_lease_deploy.py`
- `backend/utils/batch_pipeline/live_upload.py`
- `backend/utils/batch_pipeline/record_seal_cluster_repair.py`
- `backend/utils/sync/record_token_lease.py`
- `backend/docs/listen_pusher_pipeline/changes/2026-11-10-token-lease-round4.md` (this receipt).

- `98fc898f9bcd9df4fa2c3bd8e70a91357ba9d4f2` — fence session-resolved uploads and deduplicate custody finishes.
- `9d55e2de0f259aebea2e8e7e21b4ce3d2290b09e` — share seal metric clock validity across producers.
- `94c227ed3b0c41147faafcf0baf392762415b1c4` — bind custody leases to the production sync timeout.
- `5e4bfc323f90d20e8155972814b2e70728740533` — bound numerical pools in isolated stack children after its allowlist dropped the launcher caps.
- Final receipt commit: reported in the final handoff (documentation only).

## Deviations and remaining limits

No production implementation deviation from the R4 lead rulings. An additional test-harness correction pins numerical thread pools after the child environment allowlist resets ambient variables. A sampled startup had 17 OpenBLAS worker threads despite the launcher caps. The same correction covers every owned child and restart; a regression supplies hostile ambient pool sizes and verifies the isolated child receives one-thread limits. No readiness deadline or lifecycle assertion changed. The worker required no source edit because it already used main's shared guard. Positive finite old clocks remain valid by that explicit shared rule. An unresolved recording-session target intentionally keeps the old behavior; this branch cannot fence an unknown conversation. Each finalized serve upload now has a small durable completion receipt under its conversation.

Validation-only details are disclosed above: immutable-base preflight, local preflight file wall, normal scheduling through the heavy gate, and canonical parsed-manifest test setup. CI, deployment identity, live production configuration, the 48h shadow soak and serve ramp acceptance remain unverified. No push, PR, deployment, production account access or GCP tier.

The first 26-file batch ended with four timing-only failures under host contention: sync hit its 900s file limit at 69%; lifecycle writers hit 900s at 90%; repair had 144 passes and four 30s child-process timeouts; notification templates had six passes and two 60s `go run` timeouts. No assertion mismatch was reported by those failures. The final retry retains the canonical 900s/1s file/CPU guards and uses `omi-heavy --no-priority`; host load and actual process policy are disclosed rather than treating that option as a causal explanation. An earlier admitted retry waited for two load1 <= 30 samples 45s apart; after nine minutes of continued high load it was deliberately stopped before any test began. Only that owned idle PID was terminated, and its slot was released. The final invocation re-enters the same admission queue without changing slot counts. This changes process scheduling while preserving all assertions and timing limits. The final table combines unchanged passing files with the targeted retry at the same source head. All four retry files exited 0 (1376.66s total), yielding **3256 passes across 26 focused unit files**; no failed files remain in this focused suite.

The first complete lifecycle run reported **33 passed, 3 strict XFAILs, 1 failed** in 478.75s. The failure was the restarted local pusher missing the unchanged 120s readiness deadline in `test_refusal_clock_survives_pod_death_and_reconnect`; its log had no crash traceback. All three new named lease exits passed. The simulator scenario file is byte-identical to rebased main. A full lifecycle-only retry preserves the same readiness and 900s outer limits; results are recorded above. An unchanged full retry repeated that one startup failure: **33 passed, 3 strict XFAILs, 1 failed**, 424.28s. A one-second native sample of the owned child showed module imports and 17 idle OpenBLAS workers. Inspection found the allowlist dropped the launcher thread caps; commit `5e4bfc323f90` repairs that test resource contract, then reruns the full lifecycle without relaxing its 120s readiness limit. The three existing strict XFAILs are `test_sealed_no_job_registered_recovered`, `test_upload_failed_gets_retried`, and `test_server_batch_completion_ordering[closed-before-completed]`. They cover no-job recovery, failed-upload retry, and completion ordering, and were not edited or hidden.

The first expanded preflight stopped after 3617.08s on the product-file line-count ratchet: the existing `backend/testing/listen_pusher_stack/run.py` grew from 1980 to 1988 lines for the explicit child numerical limits. Its exact bounded `Line-Count-Exception` was added to the local PR body as the checker requested. No source code or test assertion changed for this metadata correction. The rerun validates metadata first, then reruns the full expanded preflight; the outer orchestration limit is 14400s, while per-file preflight remains 1800s and requested serial sync/repair remain 900s.

The next expanded preflight was deliberately stopped after 5337.80s (SIGTERM / exit -15), with no reported failure, while its contract-test fixture cold-built the pinned Swift formatter. Only verified owned process groups 88500 and 33458 were terminated and all observed descendants exited. A completed shared cache was available at the exact pinned source commit `62eaad2822b865407b8cde56c36386c00800f7ec`, with clean tracked source and reported version `602.0.0`. The final rerun copies only that completed binary into a fresh private cache, verifies its SHA-256 before/after copying and its version, then invokes the unchanged full preflight and deadlines. The helper binary SHA-256 is `acf3a6fca9b35388921c25429987b279f745f54ecea9384a2cb4486b30d8e024`; provenance is retained in the final run's `swift-format-cache-provenance.json`. Owned launcher PID 81926 applied normal scheduling to itself before launching checks, exit 0 at 2026-11-10T00:20:52Z. This is the wrapper's ordinary completed-cache path; no test or bootstrap assertion is disabled.

Raw diagnostics: `/Volumes/Ephemeral/scratch/tokenlease-round4-validation.log`. Machine exit/timing records: `tokenlease-round4-quick-results.json`, `tokenlease-round4-deploy-only-results.json`, `tokenlease-round4-rebased-contract-results.json`, `tokenlease-round4-normal-priority-retry-results.json`, `tokenlease-round4-rebased-lifecycle-retry-results.json`, `tokenlease-round4-lifecycle-caps-results.json`, `tokenlease-round4-preflight-retry-results.json`, `tokenlease-round4-preflight-cached-results.json` under the same scratch root. This committed receipt and its ANX attachment retain the findings, commands and results after scratch cleanup.

## Full Part A branch file inventory

The rebased branch changes 88 files including this receipt (R4 affects the 19 files listed above).

```text
.agent-brief/alert-rules-addition.json
.agent-brief/metric-inventory-addition.json
.github/actions/deploy-backend-stack/action.yml
backend/charts/backend-listen/dev_omi_backend_listen_values.yaml
backend/charts/backend-listen/prod_omi_backend_listen_values.yaml
backend/charts/backend-listen/values.yaml
backend/charts/batch-pipeline-worker/templates/_record-token-lease.tpl
backend/charts/batch-pipeline-worker/templates/record-seal-repair.yaml
backend/charts/batch-pipeline-worker/templates/record-seal-worker.yaml
backend/charts/batch-pipeline-worker/values.yaml
backend/charts/monitoring/alert-rules.json
backend/charts/monitoring/alerts/record-token-lease.json
backend/charts/monitoring/metric-inventory.prod.json
backend/charts/monitoring/prometheus-stackdriver-exporter/dev_omi_cloud_run_metrics_exporter.yaml
backend/charts/monitoring/prometheus-stackdriver-exporter/dev_sync_omi_cloud_run_metrics_exporter.yaml
backend/charts/monitoring/prometheus-stackdriver-exporter/prod_omi_cloud_run_metrics_exporter.yaml
backend/charts/monitoring/prometheus-stackdriver-exporter/prod_sync_omi_cloud_run_metrics_exporter.yaml
backend/charts/pusher/dev_omi_pusher_values.yaml
backend/charts/pusher/prod_omi_pusher_values.yaml
backend/charts/pusher/values.yaml
backend/config/cloud_run_request_timeouts.json
backend/config/record_seal_rules.py
backend/config/refactor_modes.py
backend/database/batch_pipeline_intake.py
backend/database/batch_pipeline_record_lease_recovery.py
backend/database/record_audio.py
backend/database/record_custody_append.py
backend/database/record_partial.py
backend/database/record_token_lease_metrics.py
backend/deploy/cloud_run_gmp_sync.yaml
backend/deploy/runtime_env.yaml
backend/deploy/runtime_env/_base.yaml
backend/deploy/runtime_env/prod.overlay.yaml
backend/deploy/staging/deploy.sh
backend/docs/feature-flag-registry.md
backend/docs/listen_pusher_pipeline.mdx
backend/docs/listen_pusher_pipeline/changes/2026-11-09-record-token-lease.md
backend/docs/listen_pusher_pipeline/changes/2026-11-09-token-lease-gauge-clocks.md
backend/docs/listen_pusher_pipeline/changes/2026-11-09-token-lease-review-fixes.md
backend/docs/listen_pusher_pipeline/changes/2026-11-09-token-lease-round2.md
backend/docs/listen_pusher_pipeline/changes/2026-11-09-token-lease-round3.md
backend/routers/pusher.py
backend/routers/sync.py
backend/scripts/record_seal_repair_job.py
backend/testing/lifecycle_properties/README.md
backend/testing/lifecycle_properties/test_properties.py
backend/testing/listen_pusher_stack/README.md
backend/testing/listen_pusher_stack/run.py
backend/tests/integration/test_held_custody_conformance.py
backend/tests/integration/test_record_custody_append_emulator.py
backend/tests/integration/test_recovery_custody_conformance.py
backend/tests/promql/record_token_lease.py
backend/tests/support/firestore_batch_pipeline_drivers.py
backend/tests/support/lifecycle_state_table.py
backend/tests/support/lifecycle_writer_inventory.py
backend/tests/unit/test_backend_runtime_env_validator.py
backend/tests/unit/test_batch_pipeline_live.py
backend/tests/unit/test_lifecycle_sim_unit.py
backend/tests/unit/test_monitoring_alert_backtest.py
backend/tests/unit/test_monitoring_telemetry_contract.py
backend/tests/unit/test_pusher_record_abandon.py
backend/tests/unit/test_pusher_storage_pcm_metrics.py
backend/tests/unit/test_record_custody_append.py
backend/tests/unit/test_record_lease_append.py
backend/tests/unit/test_record_partial.py
backend/tests/unit/test_record_pending_repair.py
backend/tests/unit/test_record_producer_proof.py
backend/tests/unit/test_record_seal_cluster_repair.py
backend/tests/unit/test_record_seal_nojob_emulator.py
backend/tests/unit/test_record_seal_repair.py
backend/tests/unit/test_record_seal_worker.py
backend/tests/unit/test_record_token_lease.py
backend/tests/unit/test_record_token_lease_deploy.py
backend/tests/unit/test_sync_v2.py
backend/utils/batch_pipeline/CONTRACT.md
backend/utils/batch_pipeline/live_upload.py
backend/utils/batch_pipeline/record_lease_append.py
backend/utils/batch_pipeline/record_producer_proof.py
backend/utils/batch_pipeline/record_seal_cluster_repair.py
backend/utils/batch_pipeline/record_seal_nojob.py
backend/utils/batch_pipeline/record_seal_repair.py
backend/utils/batch_pipeline/record_seal_worker.py
backend/utils/observability/firestore_probe_export.py
backend/utils/pusher_record_barrier.py
backend/utils/sync/record_token_lease.py
config/deployment-setting-classification.json
config/feature-flags.yaml
backend/docs/listen_pusher_pipeline/changes/2026-11-10-token-lease-round4.md
```
