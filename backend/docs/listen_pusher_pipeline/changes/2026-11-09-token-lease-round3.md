# Part A token lease: round-3 implementation and validation

Both remaining findings against `711f96a41552` were verified against the code and fixed.
Receipt finalized 2026-11-09T15:28:13Z.
Final integration base: `42265f951eb2166f96bed62199b4f92c45605b3c`. Validated runtime/test head: `ba858792d093b99850ba2f964b10756f58749400`.
The initial rebase used `c59aee8dd07e`; main advanced during validation, so the branch
was rebased again and all focused suites were rerun. Expanded preflight is pinned
to the immutable final base. No push, PR, deployment or GCP tier was used.

## Changes

- Custody tokens use `max(frame lease, checked-in backend-sync request timeout + CUSTODY_REQUEST_MARGIN_SECONDS)`.
  The packaged config owns the existing 3600-second request timeout and the staging
  shape renderer reads it. The named margin is 300 seconds: default custody minimum
  3900 seconds; frame default remains 3600. Per-operation server-observed heartbeats remain.
  The deployment test renders the actual pure shape function and rejects a lease that
  does not strictly cover the request timeout and margin.
- An accepted, durably committed upload that loses its final fence takes transactional
  `recover_committed`: revision bump, existing partial continuation, and a terminal
  exact-request receipt. Repeated recovery is read-only. Other fences, original work,
  raw audio and existing privacy authority remain intact. Rollback after acquisition
  still preserves the accepted append's recovery obligation.
- The backend-sync GMP profile admits late-append and lease metric families. Regression
  coverage extracts every metric queried by the lease alerts and checks the actual
  emitting service's scrape path, production PodMonitoring and dev/prod exporter prefixes.
- Rebase integration preserves upstream's absent metric ages and invalid-clock counters.
  The lease gauge excludes absent ages; two run-level cases cover mixed/all-absent
  conversation ages. Enqueue-clock filtering remains telemetry-only; selection and
  cursors match the metric-free discovery call exactly.
- The repair IPC fixture waits for child readiness before starting its unchanged 0.3s
  deadline, including a forced 0.5s startup delay. The worker export fixture supplies
  upstream's new invalid-clock argument and checks its real endpoint output.

No Part B/discovery selection work. `users.py`, `live.py`, projection-release and
held-dead-letter source files have no branch changes. The protected seal/pending
functions have identical ASTs before/after the R3 commit. Alert entries remain the
exact 222-entry main prefix plus two approved append-only additions; declared metric
entries remain the 80-entry prefix plus three additions, with all 2300 observed
inventory entries unchanged. The idle seal worker remains disabled under prod values.

## Final results

All focused files use fresh Python 3.11 processes through canonical `backend/test.sh`,
one worker, file isolation, standard plugin exclusions and CPU checks. All 21 files
have no slow/integration markers; the marker selection omits no case.

| Focused unit file | Passed | Failed |
| --- | ---: | ---: |
| sync_v2 | 182 | 0 |
| record_seal_cluster_repair | 148 | 0 |
| record_token_lease | 80 | 0 |
| record_custody_append | 30 | 0 |
| record_producer_proof | 27 | 0 |
| record_partial | 82 | 0 |
| record_seal_repair | 48 | 0 |
| record_pending_repair | 63 | 0 |
| record_audio_seal | 57 | 0 |
| record_seal_nojob | 44 | 0 |
| lifecycle_state_table_writers | 1738 | 0 |
| record_token_lease_deploy | 12 | 0 |
| record_seal_cluster_repair_deploy | 10 | 0 |
| monitoring_alert_backtest | 29 | 0 |
| monitoring_notification_contract | 8 | 0 |
| monitoring_alert_rule_contract | 75 | 0 |
| monitoring_telemetry_contract | 54 | 0 |
| pusher_record_abandon | 24 | 0 |
| pusher_storage_pcm_metrics | 15 | 0 |
| batch_pipeline_live | 102 | 0 |
| record_seal_worker | 23 | 0 |
| **Total (21 files)** | **2851** | **0** |

The requested serial 900-second runs passed: sync 182 tests, 575.69 pytest seconds /
606 total file-wall seconds; repair 148 tests, 170.50 pytest seconds / 186 file-wall
seconds. Token lease 80, custody 30, telemetry 54. Fixed worker file 23 tests,
13.22 pytest seconds / 22 file-wall seconds. No final unit skips or new allowlist entries.

- Held-custody conformance: **75 passed, 0 failed, 0 skipped**.
- Recovery-custody conformance: **39 passed, 0 failed, 0 skipped**.
  Both require memory, private Firestore emulator and fixture-owned local PostgreSQL.
- Lifecycle scenarios/properties: **34 passed, 3 existing strict xfailed, 0 failed**,
  329.45 pytest seconds. Named exits `seal`, `partial_finish`, `reactivated` all passed.
- Real `promtool` backtests: **7 scenarios passed**.
- Pinned metadata-only validation: **5 checks passed**.
- Expanded preflight: **56 checks passed, 0 failed; 3545.24 preflight seconds / 3549.25 launcher seconds; exit 0**.

## Commands and environment

All heavy invocations use `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --`.
The owned launcher unsets GOOGLE_APPLICATION_CREDENTIALS, all CLOUDSDK_* variables and
auth-file bindings, isolates HOME/config/temp directories, and uses native numerical
thread caps of one. No production credentials or services are used.

Actual heavy launchers for final validation:

```sh
# 21-file canonical run: first 20 green; the worker fixture mismatch below was then fixed.
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-round3-rebased-validate.py --contract
# Repeated only the fixed worker, then PromQL and all-backend conformance/lifecycle.
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-round3-rebased-validate.py --worker-fix
# Full lifecycle-only retry with unchanged startup/invariant budgets, then pinned preflight.
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-round3-rebased-validate.py --lifecycle-retry
```

Canonical unit child command, cwd `backend`; the owned list contains the table's 21
paths (worker-only for its correction rerun):

```sh
PYTHON=.venv/bin/python BACKEND_PYTEST_FILE_ISOLATION=1 BACKEND_PYTEST_PARALLEL_SESSION=0 BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_UNIT_TEST_FILE_LIST=<owned-state>/focused-unit-files.txt bash test.sh
```

Remaining child commands; conformance/lifecycle execute inside a private loopback
Firestore emulator in `demo-omi-listen-stack`, with `OMI_REQUIRE_STORE_BACKENDS=all`
and offline providers:

```sh
# cwd backend; each conformance file uses a fresh process
.venv/bin/python -m pytest -q --tb=short tests/integration/test_held_custody_conformance.py
.venv/bin/python -m pytest -q --tb=short tests/integration/test_recovery_custody_conformance.py
.venv/bin/python -m testing.lifecycle_sim.run --keep --state-dir <owned-state>/lifecycle --extra-test-module testing/lifecycle_properties/test_properties.py
.venv/bin/python tests/promql/record_token_lease.py --promtool /Volumes/Ephemeral/scratch/tokenlease-promtool/promtool
# cwd root: exact make-preflight entrypoint with an immutable base
bash scripts/dev-harness/run-python.sh .github/scripts/pr_preflight.py --lane local --base 42265f951eb2166f96bed62199b4f92c45605b3c
```

Expanded preflight uses `CI=true OMI_CHECKS_JOBS=1 BACKEND_PYTEST_WORKERS=1`, private
`OMI_PR_BODY_FILE=.agent-brief/tokenlease-pr-body.md` and an 1800-second local file
wall guard. Requested sync/repair retain 900 seconds. No CI default changes.
`--suggest` and `--metadata-only` were run against the same pinned base first.

## Resolved validation failures

The first new telemetry fixture omitted required image identity (52 passed/2 failed);
it now renders with a synthetic digest and valid pull policy, then passes all 54.
The first preflight's index file hit its 900-second wall guard; serial retry passed
all seven guard files, longest file 804 seconds. That retry later hit a real synthetic
merge conflict because shared origin/main advanced; the second rebase and pinned
base resolve it. A rebased direct-pytest sync run timed out at 900 seconds without
an assertion failure; canonical test.sh passed all 182 within the same 900-second limit.
The worker fixture mismatch reported 22 passed/1 failed before its four-argument API
correction; the full worker rerun passed 23. The first rebased lifecycle run reported
33 passed/3 existing xfailed/1 failed on a third pusher cold start exceeding its
120-second readiness guard. Its log shows readiness after the deadline and clean
shutdown. The full standalone retry passed all lifecycle cases with the same guard;
no harness, invariant, assertion or xfail budget was changed.

## Files and commits

R3 direct changes:

- `backend/config/cloud_run_request_timeouts.json`
- `backend/config/record_seal_rules.py`
- `backend/database/record_audio.py` (renewal only)
- `backend/database/record_custody_append.py`
- `backend/utils/sync/record_token_lease.py`
- `backend/deploy/cloud_run_gmp_sync.yaml`
- `backend/deploy/staging/deploy.sh`
- `backend/docs/listen_pusher_pipeline.mdx`
- `backend/docs/listen_pusher_pipeline/changes/2026-11-09-token-lease-round3.md`
- `backend/tests/support/lifecycle_state_table.py`
- `backend/tests/support/lifecycle_writer_inventory.py`
- `backend/tests/unit/test_record_custody_append.py`
- `backend/tests/unit/test_record_token_lease.py`
- `backend/tests/unit/test_record_token_lease_deploy.py`
- `backend/tests/unit/test_monitoring_telemetry_contract.py`
- `backend/tests/unit/test_record_seal_cluster_repair.py`
- `backend/tests/unit/test_record_seal_worker.py`

Rebase integration also reconciled `backend/utils/batch_pipeline/record_seal_worker.py`
and `backend/utils/batch_pipeline/record_seal_cluster_repair.py` with upstream's
metric-clock handling. The runtime fix is `7ebbb6287d117effe93d5758cf42dd18cda50b30`;
the child readiness fixture is `23ee451132a20a2916c25ad7ead411b0957bf096`; worker fixture correction is
`ba858792d093b99850ba2f964b10756f58749400`. Receipt commit is reported in the final handoff.

<details><summary>Full Part A branch file manifest (81 files relative to the pinned base)</summary>

```text
.agent-brief/alert-rules-addition.json
.agent-brief/metric-inventory-addition.json
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
backend/tests/integration/test_held_custody_conformance.py
backend/tests/integration/test_recovery_custody_conformance.py
backend/tests/promql/record_token_lease.py
backend/tests/support/firestore_batch_pipeline_drivers.py
backend/tests/support/lifecycle_state_table.py
backend/tests/support/lifecycle_writer_inventory.py
backend/tests/unit/test_backend_runtime_env_validator.py
backend/tests/unit/test_batch_pipeline_live.py
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
```
</details>

<details><summary>Local implementation history before this final receipt</summary>

```text
703f3dcf2ee84de7fd19a93ff18e8067b1139c63 feat: add server-renewed record custody token leases
f739b3fa2c7086072551987130281eda5d00dd38 harden: preserve stock producer proofs and align lease seed checks
d4455ae8de98ef12462522ebf4c70afd13af6a86 chore: align token lease alert routing with fleet contract
abd162c50389f53a01e5dbf6b200e98f210a18da harden: bind stock lease epochs across producer runtimes
e6cc7dae8285a2771f3ac117694dc1d89d27f53b harden: renew leases while draining queued frame batches
6f97905dfe54afaa30da469a25e34b0b26f0acdb harden: restore pre-seal producer custody after partial finish
21e5e92fc7eb34c2ecc743cc8da82b11b13c4bd4 fix: preserve dark lease telemetry and bind runtime settings
450ef33c33d28811920e1222b9c07dc03c073429 test: declare no-job lease cohort context in writer inventory
07f0f733a1088b24067a43a04c330c286a5bdf2b fix: keep lease backlog alert quiet after drain completes
dbb580dd288da3c042588c01af0b37c638a41e3d test: include dark lease settings in synthetic Cloud Run revisions
9cd66e6511684d3789b1a8e172bacb2b247e4d3b docs: record token lease validation and lead handoff risks
d679610751a966a98bdb83b91be01d8ef917f356 fix: bound legacy leases at serve enable and honor newer custody proof
a48a56c713f0c4ca8566969b7619c85bd2142216 test: keep stock lease expiry stable across repair retry wakes
5810385f4ce29b80291a2b1e368e9ac9792defe8 fix: page on first lease event and hand off metric declarations
5e64a81a6bc61196c98e0f49ce5afe0f7669289c fix: align lease epoch registry source with generated documentation
787c72dc64eab184b267d803112922e047ebe314 docs: record rebased token lease validation and owner handoffs
3e0d7402b9aaa121116d279b162a17700911a8f4 chore: admit approved record token lease monitoring additions
4dcd2590a556e0b1a677d265c6f9a4e26db771e1 fix: expose seal age gauge declaration to alert admission
32b649a743426d9c9d9261ed76c9f93916554e45 docs: record approved monitoring additions and green rebased checks
33629779ee08e7cc38e0d4e0a8b4d447ec35fdb8 fix: fence custody appends and recover post-seal interior audio
ac5044f67b184e45ae9a36eed3349b4b2fd32757 test: cover crashed recovery producers and rearm partial storage failures
5d28536cb390f21b8a951be1173c9d25a4f8e9c9 fix: order late partial recovery after original record publication
9002dfd868ec65df17731b9b966aca2743dbb216 test: model durable append heartbeat in lifecycle reactivation exit
84c1fba0b77024b3a285e4c3bbdcaf39d0124b29 test: align custody completion and approved alert contract regressions
aac984fa0398580479bee68747afe27dbfc5312f fix: pin recovery policy canonically and keep closed shadow rows inert
6cb53682df328c75294a865058b6a696e74ac89c test: exercise closed shadow rows with existing producer tokens
3320804649b71c8f2df6a213432846582e888bc7 fix: reconcile fresh socket mints after complete record seals
df377325f97de036e2ad37eb82b77c471cecd2cb fix: subtract earlier WAL units before retaining later overlap
f1630231a25a987e3310fea861b368a2e4881400 docs: record green token lease review corrections and validation
901890487123a37deeb0bde2d31b1e8670dd6d15 test: restrict seal no-job emulator cleanup to owned fixtures
4c82ad7835fb2d9de221ec173fd3cf1bce18b451 fix: preserve late audio recovery and custody leases across rollback
e0e8d21895d9c460370eabe9d17ae007db218b3b test: declare uncaptured record reopening and custody rollback exits
970ddfb1456da569a9fb7ee496322da9e471adbf fix: preserve backlog warning across repair pod gaps
a27d77fa51abee13208a2b526f0c4058967c72f3 docs: record verified round-two token lease corrections
56ab080c08f22d2c089a42d918a53f95d93cf5fc fix: exclude invalid enqueue clocks from repair age gauge
dadb50e6df93b6040019e45d16115b7c2326b7aa docs: record repair gauge clock validation
7ebbb6287d117effe93d5758cf42dd18cda50b30 fix: protect long custody uploads and recover committed audio
23ee451132a20a2916c25ad7ead411b0957bf096 test: synchronize repair child startup before deadline
9b4073a276537da8817611f046024f99c0efa8af docs: record round three validation progress
ba858792d093b99850ba2f964b10756f58749400 test: update seal metrics fixture for invalid clocks
```
</details>

## Limits and risks

No implementation deviation from the lead's rulings. The 3900-second custody minimum
is the explicit R3 override; frames remain 3600 by default. Preflight's immutable-base
entrypoint is equivalent to make preflight and prevents concurrent-ref drift.
Local preflight's timing guard is explicitly disclosed above. Three pre-existing
strict lifecycle xfails remain; no R3 finding is left intentionally unfixed.
CI, live production timeout/configuration, deployment identity, 48-hour shadow soak
and serve ramp acceptance are unverified. The feature remains off. No push, PR,
GCP tier or production access.

Raw diagnostic log: `/Volumes/Ephemeral/scratch/tokenlease-round3-validation.log`.
Machine exit/timing records are `tokenlease-round3-rebased-contract-results.json`,
`tokenlease-round3-rebased-worker-fix-results.json` and
`tokenlease-round3-rebased-lifecycle-retry-results.json` under the same scratch root.
This committed dated receipt and its ANX attachment retain the results after scratch cleanup.
