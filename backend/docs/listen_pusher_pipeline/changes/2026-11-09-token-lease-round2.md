# Token lease round-2 review corrections

This applies the lead's five decisions from the two FIX-FIRST re-reviews of
`b70acd27e098`. It supersedes the rollback/recovery descriptions in the
[earlier receipt](2026-11-09-token-lease-review-fixes.md) and updates the
[custody contract](../../listen_pusher_pipeline.mdx).

The branch was rebased onto freshly fetched `origin/main`,
`82969e2b845b4f1c76d78f63272ad83b11cf9aa0`. No Part B changes are introduced.

Recovery reads the original job's captured input revision, without a
conversation-status gate. A newer revision creates or rearms the existing
partial continuation, retaining original units and waiting for any older full
publication. Legacy captured jobs without the new revision field are handled
conservatively. An uncaptured reservation stays on normal admission, which
reads the current upload barrier and validates it transactionally after staging.
Lease-enabled native admission pins `record_input_upload_revision`; off-mode
admission retains its previous payload. Recovery remains explicitly partial.

A custody fence acquired in serve is a durable obligation: accepted stored
bytes still revise and recover after rollback. Podless custody fences retain
their own lease exit in every mode, including after a crash; off-mode frame
pod/abandon proof remains unchanged. The clock parser now accepts the explicit
clocks on these podless custody tokens.

Frame fence/renewal transactions report a late observation without incrementing
the late-append counter. Only a successful durable-window/object commit consumes
that observation. Refused/failed storage does not count, and an older in-flight
window cannot consume a later observation. Custody counting still follows
accepted durable storage.

Private-cloud-sync-disabled uploads skip custody fences. If archiving becomes
disabled after fencing and returns no paths, finalization clears only that
fence without bumping revision or creating recovery; the original route response
is preserved. If cleanup is unavailable, the existing token's lease remains the
exit and the original response is still preserved.

The active production repair CronJob now serves its existing shared probe
collectors plus the bounded oldest-unsealed discovery sample on port 9090.
Its PodMonitoring scrapes `/metrics` every 15 seconds. The idle seal worker's
runtime setting is unchanged. The backlog expression filters idle NaN samples,
aggregates the actual repair age, and carries the last valid sample for ten
minutes across short CronJob gaps before deriving its slope. Pod replacement
cannot invent a flat per-pod trend or reset the warning's hold period.
Only this branch's backlog alert expression and its mirrors are updated; main's
existing alert entries are preserved.

Mode defaults remain off; the 3600-second default, 48-hour shadow soak and
lead/P4 ramp gates remain unchanged. No production access, push or PR is part
of this work. GCP tier: none.

## Validation

Initial focused validation passed token lease (80), custody append (26), partial
recovery (82), deployment/HTTP telemetry (9), native admission (102), and producer
proof (27). The new pusher fixture initially omitted its explicit runtime stage;
the fixture was corrected without relaxing an assertion. Final focused,
all-backend conformance, lifecycle, alert/telemetry and expanded preflight results
are recorded below after the complete run.

The real-engine backtest runner is `tests/promql/record_token_lease.py` (run from
backend with `--promtool <path>`). It reads the checked-in Grafana expression
and its threshold/hold period, then tests rotating repair pods with idle NaN,
healthy falling age, no recent releases, and no valid repair sample.

## Final validation receipt

Recorded 2026-11-09T06:27:11.603816+00:00. Local verification only; no CI, deploy, push or PR.

- Runtime correction: `b38a4782d3b4dc903d6e09d87391789c1f39610c`.
- Lifecycle declaration: `c4c58c8f3c282bd6fb11d76ed0a5cb8ca90098be`.
- Operational warning and real PromQL regression: `b3563c08b3af77b3372d24f186eca57aaeea8825`.
- Rebased main at task start: `82969e2b845b4f1c76d78f63272ad83b11cf9aa0`.

Producer, custody, admission and repair runtime code remained unchanged after the first commit. The lifecycle follow-up registers the new uncaptured-reopen builder and documents its exits. The warning follow-up changes only the branch-owned backlog expression/mirrors and its tests/documentation. The receipt-only commit is reported separately.

| Unit suite | Final passed |
| --- | ---: |
| `test_record_token_lease.py` | 80 |
| `test_record_custody_append.py` | 26 |
| `test_record_lease_append.py` | 1 |
| `test_record_producer_proof.py` | 27 |
| `test_record_seal_repair.py` | 48 |
| `test_record_partial.py` | 82 |
| `test_pusher_record_abandon.py` | 24 |
| `test_record_pending_repair.py` | 63 |
| `test_record_audio_seal.py` | 57 |
| `test_record_seal_cluster_repair.py` | 121 |
| `test_record_seal_nojob.py` | 44 |
| `test_refactor_modes.py` | 17 |
| `test_lifecycle_state_table_writers.py` | 1738 |
| `test_record_token_lease_deploy.py` | 9 |
| `test_monitoring_telemetry_contract.py` | 52 |
| `test_sync_v2.py` | 181 |
| `test_record_seal_worker.py` | 20 |
| `test_record_seal_worker_deploy.py` | 7 |
| `test_record_seal_cluster_repair_deploy.py` | 10 |
| `test_record_seal_worker_guards.py` | 13 |
| `test_monitoring_alert_backtest.py` | 29 |
| `test_monitoring_notification_contract.py` | 8 |
| `test_monitoring_alert_rule_contract.py` | 75 |
| `test_record_gap_fill.py` | 52 |
| `test_pusher_storage_pcm_metrics.py` | 15 |
| `test_pusher_storage_pcm_saturation.py` | 38 |
| `test_record_barrier_executor.py` | 15 |
| `test_batch_pipeline_live.py` | 102 |
| `test_batch_pipeline_intake.py` | 45 |
| `test_batch_pipeline_admission.py` | 50 |
| `test_record_admission_review_fixes.py` | 26 |
| `test_record_seal_sweeper_deploy.py` | 4 |
| **32 suites** | **3,079** |

| Integration / gate | Final result |
| --- | --- |
| Held custody, all three backends | 75 passed |
| Recovery custody, all three backends | 39 passed |
| Real-emulator lifecycle scenarios/properties | 34 passed, 3 pre-existing xfailed |
| Named lease exits: seal / partial_finish / reactivated | All three passed |
| Real PromQL engine (promtool 2.55.1) | 4 scenarios passed |
| Final expanded preflight | 56/56 checks passed; exit 0; 2299.20 seconds |

The five affected suites were rerun after the warning follow-up: deployment/HTTP 9, alert backtests 29, notification contracts 8, rule/mirror contracts 75 and telemetry 52; all passed. They are included in the 3,079-unit total rather than counted twice.

Commands (all heavy work admitted through omi-heavy):

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-round2-closeout.py
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-round2-units.py lifecycle_state_table_writers
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-round2-alert-closeout.py
# Each unit suite above, cwd backend, in a separate interpreter:
.venv/bin/python -m pytest -q --tb=short tests/unit/<suite>
# All-backend conformance, inside a private loopback Firestore emulator:
.venv/bin/python -m pytest -q --tb=short tests/integration/test_held_custody_conformance.py
.venv/bin/python -m pytest -q --tb=short tests/integration/test_recovery_custody_conformance.py
.venv/bin/python -m testing.lifecycle_sim.run --keep --state-dir /Volumes/Ephemeral/scratch/tokenlease-validation-yydc_z68/lifecycle --extra-test-module testing/lifecycle_properties/test_properties.py
# Real PromQL backtests, cwd backend:
.venv/bin/python tests/promql/record_token_lease.py --promtool /Volumes/Ephemeral/scratch/tokenlease-promtool/promtool
# Repository root, private draft body supplied through OMI_PR_BODY_FILE:
make preflight
```

The launchers unset GOOGLE_APPLICATION_CREDENTIALS, every CLOUDSDK_* variable and service-account/auth-file bindings; private subprocess HOME/config/TMP prevent ADC fallback. Conformance requires all store backends, uses anonymous loopback Firestore and fixture-owned local PostgreSQL, and never uses a remote GCP service. GCP tier: **none**. Promtool was downloaded from the official public Prometheus v2.55.1 release into scratch, without installing a host service.

Initial failures were resolved without waivers: the pusher fixture lacked its explicit stage; the first broad state-table run reported 1 failed/1,737 passed for the undeclared uncaptured-reopen builder, then the unchanged guard passed 1,738 after its declaration. The first batch driver retains that initial nonzero status in its log; its other suites, conformance/lifecycle and first 56-check preflight passed. The PromQL fixture initially used unsupported compressed NaN notation; explicit NaN samples fixed the fixture without changing expected outcomes. Final PromQL, affected suites and the full expanded preflight passed. No assertion was relaxed and no xfail was added.

Logs: `/Volumes/Ephemeral/scratch/tokenlease-round2-closeout-results.log`, `/Volumes/Ephemeral/scratch/tokenlease-round2-units-results.log`, `/Volumes/Ephemeral/scratch/tokenlease-round2-alert-closeout-results.log`. Disposable paths are evidence pointers; exact commands/counts are preserved here independently.

## Round-2 files changed (29)

- `.agent-brief/alert-rules-addition.json`
- `backend/charts/batch-pipeline-worker/templates/record-seal-repair.yaml`
- `backend/charts/monitoring/alert-rules.json`
- `backend/charts/monitoring/alerts/record-token-lease.json`
- `backend/config/record_seal_rules.py`
- `backend/database/batch_pipeline_intake.py`
- `backend/database/batch_pipeline_record_lease_recovery.py`
- `backend/database/record_audio.py`
- `backend/database/record_custody_append.py`
- `backend/docs/listen_pusher_pipeline.mdx`
- `backend/docs/listen_pusher_pipeline/changes/2026-11-09-token-lease-round2.md`
- `backend/routers/pusher.py`
- `backend/scripts/record_seal_repair_job.py`
- `backend/tests/promql/record_token_lease.py`
- `backend/tests/support/lifecycle_state_table.py`
- `backend/tests/support/lifecycle_writer_inventory.py`
- `backend/tests/unit/test_batch_pipeline_live.py`
- `backend/tests/unit/test_pusher_storage_pcm_metrics.py`
- `backend/tests/unit/test_record_custody_append.py`
- `backend/tests/unit/test_record_partial.py`
- `backend/tests/unit/test_record_seal_cluster_repair.py`
- `backend/tests/unit/test_record_token_lease.py`
- `backend/tests/unit/test_record_token_lease_deploy.py`
- `backend/utils/batch_pipeline/CONTRACT.md`
- `backend/utils/batch_pipeline/record_producer_proof.py`
- `backend/utils/batch_pipeline/record_seal_cluster_repair.py`
- `backend/utils/observability/firestore_probe_export.py`
- `backend/utils/pusher_record_barrier.py`
- `backend/utils/sync/record_token_lease.py`

## Remaining acceptance

All five lead decisions are implemented. No reviewed fix remains open. Original raw audio and immutable original work remain retained; partial recovery does not invent completeness. The complete-seal and Part B discovery ASTs are unchanged from the pinned base, and main alert entries/metric inventory are preserved apart from the previously approved branch additions. No users.py, live.py, projection-release, held-dead-letter or index changes are introduced.

Production signal-gap measurement, the 48-hour shadow soak and lead/P4 ramp acceptance remain unperformed. Mode still defaults off. The checked-in production values and actual local HTTP endpoint are verified; this is not a claim that the new metrics endpoint has been deployed.
