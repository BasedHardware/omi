# Token lease round-3 review corrections

Both findings against `711f96a41552` are confirmed. The initial custody expiry
used the general lease in `database/record_custody_append.py:55`, while accepted
finalization raised before recording recovery when its token was absent at
lines 76–78. The sync GMP keep rule in `deploy/cloud_run_gmp_sync.yaml:48`
excluded the late-append and lease families. No finding was rejected.

Rebased onto `c59aee8dd07e471fb0bf938c0f6a380301fe60c0` before editing.

## Custody lifetime and recovery

The checked-in backend-sync Cloud Run shape's 3600-second timeout is now owned
by packaged `config/cloud_run_request_timeouts.json`. The pure staging shape
renderer reads that same value, preserving its rendered timeout. Custody tokens
use the greater of the general lease and this timeout plus the named
`CUSTODY_REQUEST_MARGIN_SECONDS` (300 seconds). The default custody floor is
3900 seconds; frame leases retain the configured 3600-second default.
Per-operation heartbeats remain and use the appropriate token duration for
coalescing and renewal. Crashed custody still expires in off/shadow/serve.

If an accepted durable upload loses its exact fence, finalization records its
revision bump and existing partial continuation in a transaction. A per-request
receipt in the conversation's `record_custody_recoveries` subcollection makes
repeated recovery read-only. Receipts contain revision/time metadata only.
Other live tokens, original work and raw audio remain intact. Existing privacy
authority still gates recovery; metadata unavailability retains the retry/WAL
response. Rollback after begin still preserves accepted bytes.

The regression exercises a single archive operation beyond the old lease,
loss of the fence after durable commit, exact-request retry and a serve-to-off
rollback. The deployment test executes only `shape_flags` (never a deploy or
cloud CLI) and fails if the rendered timeout is not strictly below the token
duration. Lifecycle declarations include the recovery clear.

## Alert ingestion

The sync GMP profile admits `omi_record_token_late_append_total` and the entire
`omi_record_token_lease_*` family. The regression extracts all metrics queried
by the actual lease alerts, checks their emitting service's scrape filters,
renders production pusher/repair PodMonitoring, and checks dev/prod Cloud Run
exporter prefixes. Alert definitions and metric inventory are unchanged.

Mode defaults remain off. No production/GCP access, push, PR or deployment is
part of this work. The 48-hour shadow soak and ramp acceptance remain pending.

## Validation

The full validation runs the reported `test_sync_v2.py` and
`test_record_seal_cluster_repair.py` serially first, with
`BACKEND_UNIT_FILE_BUDGET_SECONDS=900` and individual 900-second process limits.
Unit files use fresh interpreters. All heavy work is admitted through
`/Users/dazheng/workspace/omi/bin/omi-heavy`; launchers unset
GOOGLE_APPLICATION_CREDENTIALS, all CLOUDSDK_* variables and auth-file bindings,
and isolate HOME/config/temp directories to prevent ADC fallback. Custody
conformance requires memory, Firestore emulator and fixture-owned local
PostgreSQL, followed by the real-emulator lifecycle scenarios/properties.
No new test waiver or xfail is authorized.

Final commands, pass/fail counts and preflight results are recorded after the run.

## Initial validation receipt

Fix commit: `51bf58f7e165486fd4b063852d2832b5cc09e4a4`.

The requested serial reruns completed with the 900-second budget: sync **182 passed, 0 failed**, pytest 394.47 seconds (launcher 406.19); repair **129 passed, 0 failed**, pytest 60.69 seconds (launcher 70.81). Both original `test_killed_child_reports_last_received_stage` cases passed; the reviewer's reported child-stage failure was not reproduced in that run. A subsequent static review verified that Python startup races the fixture's 0.3s coordinator deadline. The fixture now signals readiness before that deadline starts, and covers a synthetic 0.5s startup delay. All original profile, byte, disposition, elapsed-time and child-reaping assertions remain, as does the production deadline. The full repair suite is rerun after this fixture correction.

The first sixteen suites passed. The new telemetry test initially reported 52 passed/2 failed because its pusher Helm fixture omitted the required deployment image identity. The fixture now supplies a synthetic digest and IfNotPresent policy, with stderr surfaced on render failure. No assertion was relaxed. Telemetry and the remaining gates are rerun separately.

Heavy launchers:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-round3-validate.py
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-round3-validate.py --resume
```

Exact unit commands, cwd `backend`, each in its own interpreter with `BACKEND_UNIT_FILE_BUDGET_SECONDS=900`:

```sh
.venv/bin/python -m pytest -q --tb=short tests/unit/test_sync_v2.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_seal_cluster_repair.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_token_lease.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_custody_append.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_producer_proof.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_partial.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_seal_repair.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_pending_repair.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_audio_seal.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_seal_nojob.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_lifecycle_state_table_writers.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_token_lease_deploy.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_seal_cluster_repair_deploy.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_monitoring_alert_backtest.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_monitoring_notification_contract.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_monitoring_alert_rule_contract.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_monitoring_telemetry_contract.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_pusher_record_abandon.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_pusher_storage_pcm_metrics.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_batch_pipeline_live.py
```

Remaining commands inside the same sanitized heavy launcher:

```sh
# cwd backend
.venv/bin/python tests/promql/record_token_lease.py --promtool /Volumes/Ephemeral/scratch/tokenlease-promtool/promtool
# root; starts private loopback emulator, requires all three store backends
python3 /Volumes/Ephemeral/scratch/run-tokenlease-local-validation.py
# root, private metadata draft supplied through OMI_PR_BODY_FILE
make preflight
```

The conformance launcher runs `tests/integration/test_held_custody_conformance.py` and `tests/integration/test_recovery_custody_conformance.py` using `.venv/bin/python -m pytest -q --tb=short`, then `.venv/bin/python -m testing.lifecycle_sim.run --keep --state-dir <owned-state>/lifecycle --extra-test-module testing/lifecycle_properties/test_properties.py`. The owned state path is emitted in the log. Existing recursive conversation/account purge enumerates child collections, including the new terminal recovery receipts; their transaction reads the live parent before writing.

Log: `/Volumes/Ephemeral/scratch/tokenlease-round3-validation.log`. Exit/timing records: `/Volumes/Ephemeral/scratch/tokenlease-round3-full-results.json` and `tokenlease-round3-resume-results.json`. The resumed run also repeats pusher abandon/storage and captured-input admission regressions. Final resumed validation is pending.


## Unit results before resumed gates

| Suite | Passed | Failed |
| --- | ---: | ---: |
| sync_v2 | 182 | 0 |
| record_seal_cluster_repair (before fixture correction) | 129 | 0 |
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
| monitoring_telemetry_contract (initial fixture error) | 52 | 2 |

Fixture correction commit: `295a0745f724`.


## Resumed validation

The corrected repair suite passed **131 passed, 0 failed**, pytest 101.78 seconds
(launcher 117.07), including all four checkpoint/startup-delay cases. Additional
regressions passed: pusher abandon **24**, durable PCM commit **15**, captured-input
admission **102**, telemetry **54**, each with zero failures. The reconciled latest
results across all 20 unit files are **2811 passed, 0 failed, 0 skipped**.
The earlier 2 telemetry fixture failures are superseded by its complete green rerun.

Real `promtool` backtests passed all **7 scenarios**, including the pinned epoch,
corrected normal-row maximum, all-invalid zero page, and CronJob replacement gaps.
Held-custody conformance passed **75**, requiring all three backends.
Recovery-custody conformance passed **39**, also requiring all three backends;
neither suite skipped a backend. Lifecycle passed **34**, with **3 existing strict
xfails**, zero failures, in 236.82 seconds. All three named exits passed:
`seal`, `partial_finish`, `reactivated`. The owned emulator shut down successfully.
The first expanded `make preflight` selected 56 checks, passed four, then stopped
at `firestore-index-guard`: `test_firestore_query_shapes.py` hit the 900-second
file wall guard at its determinism test (96%), without an assertion failure.
The launcher reported 1194.57 seconds, exit 2. The index guard explicitly gates
correctness rather than machine-dependent speed (`run_firestore_index_guard.py`),
so the full preflight retry uses one backend worker and an 1800-second local file
wall guard. No tests, assertions, CI defaults or skip lists change. The specifically
requested sync/repair serial runs above retain their 900-second budgets.


## Round-3 files changed

- `backend/config/cloud_run_request_timeouts.json`
- `backend/config/record_seal_rules.py`
- `backend/database/record_audio.py` (renewal only; protected seal/pending functions unchanged this round)
- `backend/database/record_custody_append.py`
- `backend/utils/sync/record_token_lease.py`
- `backend/deploy/cloud_run_gmp_sync.yaml`
- `backend/deploy/staging/deploy.sh` (same rendered timeout, shared config source)
- `backend/docs/listen_pusher_pipeline.mdx`
- `backend/docs/listen_pusher_pipeline/changes/2026-11-09-token-lease-round3.md`
- `backend/tests/support/lifecycle_state_table.py`
- `backend/tests/support/lifecycle_writer_inventory.py`
- `backend/tests/unit/test_record_custody_append.py`
- `backend/tests/unit/test_record_token_lease.py`
- `backend/tests/unit/test_record_token_lease_deploy.py`
- `backend/tests/unit/test_monitoring_telemetry_contract.py`
- `backend/tests/unit/test_record_seal_cluster_repair.py` (test fixture only)

No Part B implementation or discovery/repair selection changes. No alert aggregate,
metric inventory, users route, protected projection/live or dead-letter file edits
in this round. The longer custody floor is the explicit round-3 lead ruling;
there are no other design deviations. Production request timeout and rollout
acceptance were not measured: no GCP tier was used. The feature remains off;
the 48-hour shadow soak and ramp require the separate deployment lane.


Preflight retry, same credential-isolated heavy launcher, cwd root:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-round3-validate.py --preflight-retry
# Child environment additionally sets:
# BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_FILE_BUDGET_SECONDS=1800
# Child command: make preflight
```

Retry results: pending. No runtime/test implementation changed after `295a0745f724`.


The serial retry's Firestore guard passed all **7 files** (check 1334.49 seconds).
`test_firestore_query_shapes.py` passed **559**, pytest 765.82 seconds and total
file wall **804 seconds**. Every guard file finished below 900 seconds. The
retry retained the documented 1800-second local safety limit; assertions and
CI defaults were unchanged. Remaining preflight checks are still running.
