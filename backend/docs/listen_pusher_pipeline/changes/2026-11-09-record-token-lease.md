# Producer custody token leases (Part A)

Contract: [record custody](../../../utils/batch_pipeline/CONTRACT.md#record_audio-custody-and-conversation).
Supersedes #24832: no completed-age exemption is retained. Its chart locations
and identity/status/boundary tests are adapted to three quiet lease clocks.

`RECORD_TOKEN_LEASE_MODE=off|shadow|serve` defaults off. Off performs no lease IO
and ignores inert fields. Shadow stamps/renews but only reports would-expire.
Serve uses the fresh `record-token-lease` uid salt and explicit
`RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT` (default 0). Unlike the older refactor
modes, shadow never serves, and serve still honors the percentage.

`RECORD_TOKEN_LEASE_SECONDS` defaults 3600 (bounded 1800–7200). Frame batches
renew at most once per lease/2 per conversation on receive and projection,
including queued drain batches after socket close. An async conversation lock
coalesces concurrent receive/projection renewals; custody appends renew before
admission, including memoized retry waits. No users.py or client-state changes.
A renewal outage returns retryable custody refusal; the phone retains WAL/audio.
`RECORD_TOKEN_LEASE_DEPLOYED_AT` is a fixed release epoch (pinned by the release owner with the shadow flip and
inherited by children), not process-start time. The Helm guard refuses an enabled
mode without that epoch; off keeps the inert default zero. Bind the same epoch
on every pusher/custody writer through runtime_env and on repair through
recordTokenLease.deployedAt, so late stock renewals compute the same lapse and
revision bump as repair. Identified legacy tokens use
max(finished_at, refusal, abandoned_at, job available_at, deployment epoch);
bare True and malformed tokens remain fenced. Missing epoch fails closed.

Dark deployment → shadow for **48h** → serve **1 → 10 → 50 → 100%**.
Lead2 approves every step; P4 auto-revert guards every step after a full clean
lookback. Retune at 10% from the signal-gap histogram using
clamp(3 × p99(gap), 1800, 7200). Before 100%, **RECORD_GAP_FILL_PERCENT >= 10**
is required on custody intake. Keep late-appends zero, oldest-unsealed falling,
and immediate reactivation churn absent. Roll back with mode shadow/off.
The new split alerts file is reviewable here; the lead must incorporate it into
the combined import after #24893, whose alert-rules.json is fenced in this lane.

Late signals before seal bump upload revision and re-fence; apply transactions
re-read the exact token map. Live custody leases override stale pod/abandon proof
because uploaders can outlive the pusher. Tail/partial/privacy gates still apply;
late bytes after seal remain retained and are counted for gap-fill/revert.
Part B discovery and indexes are unchanged. Land after #24866 rebase/merge.

Implementation review risk: the design's stock seed includes the job's current
`available_at`. The pending drainer advances that retry wake every minute, so
such stock can remain fenced indefinitely even with an old deployment epoch.
This lane preserves the written formula, including matching plan/apply anchor
reads. The lead must resolve whether post-deployment retry wakes should be
excluded before relying on stock drainage. No age-only escape is layered on.

## Local validation receipt

Recorded 2026-11-08T21:05:40+00:00.

Branch `lane/tokenlease`, based on `2333dc70300dfd165ad8411cdfbd1d6bc2fb1cf7`.
Local only: no push, PR, deployment, PR closure or production access. GCP tier: **none**.
All test launchers remove `GOOGLE_APPLICATION_CREDENTIALS` and every `CLOUDSDK_*`.
Focused units, integration and final contract checks use private HOME/config/temp
directories; no backend stage env files exist. Custody requires all three store
backends, with demo Firestore emulator and private local PostgreSQL. Each focused
unit suite runs in its own Python process.

Actual aggregate launch:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-final-validation.py
```

The first admission attempt hit the default 900-second queue deadline without
running tests; the longer waiter uses the same slot count. Full output:
`/Volumes/Ephemeral/scratch/tokenlease-final-results.log`. Deployment fixture correction
was rerun via `omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-deploy-final.py`;
output is `/Volumes/Ephemeral/scratch/tokenlease-deploy-final-results.log`.
The durable commands/counts below preserve the receipt independently of scratch.

Focused unit and custody child command (cwd `backend`), once for each suite below:

```sh
.venv/bin/python -m pytest -q --tb=short <suite>
```

The integration launcher executes the two conformance suites under:

```sh
firebase emulators:exec --only firestore --project demo-omi-listen-stack --config /Volumes/Ephemeral/scratch/tokenlease-validation-n1c6yuzv/firebase.json '<worktree>/backend/.venv/bin/python /Volumes/Ephemeral/scratch/tokenlease-local-child.py /Volumes/Ephemeral/scratch/tokenlease-validation-n1c6yuzv'
```

The config binds a private loopback port. Environment:
`OMI_REQUIRE_STORE_BACKENDS=all`, `OMI_ENV_STAGE=offline`, private HOME/config/temp,
no external PostgreSQL binding; the child pins only the demo emulator project.
Lifecycle child command (cwd `backend`):

```sh
.venv/bin/python -m testing.lifecycle_sim.run --keep --state-dir /Volumes/Ephemeral/scratch/tokenlease-validation-n1c6yuzv/lifecycle --extra-test-module testing/lifecycle_properties/test_properties.py
```

Final results (last completed result for each suite):

| Suite / gate | Result |
| --- | --- |
| `tests/unit/test_record_token_lease.py` | 61 passed |
| `tests/unit/test_record_producer_proof.py` | 27 passed |
| `tests/unit/test_record_seal_repair.py` | 48 passed |
| `tests/unit/test_record_partial.py` | 71 passed |
| `tests/unit/test_pusher_record_abandon.py` | 24 passed |
| `tests/unit/test_record_pending_repair.py` | 63 passed |
| `tests/unit/test_record_audio_seal.py` | 57 passed |
| `tests/unit/test_record_seal_cluster_repair.py` | 97 passed |
| `tests/unit/test_record_seal_nojob.py` | 44 passed |
| `tests/unit/test_refactor_modes.py` | 17 passed |
| `tests/unit/test_lifecycle_state_table_writers.py` | 1722 passed |
| `tests/integration/test_held_custody_conformance.py` | 75 passed |
| `tests/integration/test_recovery_custody_conformance.py` | 39 passed |
| `lifecycle_sim + lifecycle_properties` | 34 passed, 3 xfailed |
| `tests/unit/test_record_token_lease_deploy.py` | 8 passed |
| `tests/unit/test_monitoring_telemetry_contract.py` | 52 passed |
| `tests/unit/test_sync_v2.py` | 180 passed |
| `tests/unit/test_record_seal_worker.py` | 20 passed |
| `tests/unit/test_record_seal_worker_deploy.py` | 7 passed |
| `tests/unit/test_record_seal_cluster_repair_deploy.py` | 10 passed |
| `tests/unit/test_record_seal_worker_guards.py` | 13 passed |
| `hermetic pre-deploy pytest suites` | 511 passed |
| `monitoring notification / combined export contracts` | 2 failed, 1 passed |

The first writer-inventory run had 1 failure / 1721 passes: no-job refusal now
carries owner_id for cohort selection. The manually reviewed inventory entry was
corrected in ec4c08669e90; the complete rerun passed 1722/1722. No production code
changed in that correction. The initial hermetic deploy batch had 508 passes /
3 failures because its synthetic Cloud Run snapshots lacked the four new lease
settings; 67a1ca2b590e completes those fixtures without weakening any assertion.
The complete hermetic batch was rerun afterward. All three new real-store named exits passed:
`test_leased_lapsed_token_has_named_exit[seal|partial_finish|reactivated]`.
The lifecycle run's three existing xfails remain explicit, rather than skipped or
reclassified. The added backlog alert also requires nonzero age so a completely
drained backlog does not warn solely because its age stays flat at zero.

The 18 focused unit suites total **2621 passed**. The newly touched runtime-env
validator fixture suite accounts for **206 passed** of the hermetic batch's
511; the per-file JUnit record is
`/Volumes/Ephemeral/scratch/tokenlease-deploy-final.xml`.

`git diff --check` passed. Forbidden-file diffs are empty; AST comparison confirms
`discover_jobs` (Part B) and `seal_record_audio` are unchanged from the pinned base.
Off-mode tests assert exact original mint/clear/seal write payloads, no renewal IO,
inert lease-field decisions, and original CLI terminal metrics after rollback.

Additional commands (all through the admitted heavy runner, cloud env stripped):

```sh
backend/.venv/bin/python .github/scripts/pr_preflight.py --metadata-only --pr-body-file .agent-brief/tokenlease-pr-body.md
backend/.venv/bin/python backend/scripts/check_route_policy_baseline.py --base-ref origin/main
backend/.venv/bin/python backend/scripts/generate_plan_catalog.py --check --base-ref origin/main
# cwd backend; default is hermetic, no --live:
bash scripts/pre-deploy-check.sh
.venv/bin/python -m pytest -q --tb=short tests/unit/test_monitoring_notification_contract.py::test_severity_timing_and_actionable_annotations tests/unit/test_monitoring_notification_contract.py::test_split_and_combined_rule_objects_are_byte_identical tests/unit/test_monitoring_alert_rule_contract.py::test_combined_alert_export_matches_every_split_source_rule
```

Metadata: 4 checks passed on frozen source. Route policy: passed, zero new missing
routes (use production surface export, not the offline harness's extra routes).
Plan catalog: passed. Hermetic deploy: dev/prod runtime env and source-only bucket,
source-admission and OAuth contracts passed. Its source-admission unittest script
also passed 36 tests. Earlier `.github/scripts/test_run_checks.py` passed 78 tests.

Full `make preflight` was run through omi-heavy during implementation and is **not
green**: the existing ACTION_ITEM_REFRESH_PRESERVE_ENABLED review_by=2026-11-01
is past its seven-day grace. That same ruling exists on the pinned starting base;
this lane neither extends its date nor suppresses the gate. Initial broad checks
also overlapped formatting/commits and tripped the tracked-mutation sentinel;
the final frozen metadata check passed, and the affected focused suites reran.
The duplicate broad preflight was stopped after the known baseline failure;
there is no claim of a terminal-green full preflight.

The two combined-export mirror tests intentionally remain red because the new
split rules are absent from #24893-owned `monitoring/alert-rules.json`:
`test_split_and_combined_rule_objects_are_byte_identical` and
`test_combined_alert_export_matches_every_split_source_rule`. The actionable
notification/timing contract passes. The lead must integrate the split rules
when that file is available; no assertion was weakened or skipped.

Implementation clarifications / open risks:

- Fresh server-observed signals override stale pod/abandon proof in the serve
  cohort, satisfying the hard live-uploader rule even if custody outlives pusher.
- A fixed deployment epoch is required across every writer/repair runtime;
  mode-on custody renewal failures return retryable 503 before accepting bytes,
  preserving phone WAL rather than silently losing the liveness fence.
- The specified mutable job available_at seed can keep old retrying stock fenced
  indefinitely (live.py's defer updates it to now+delay). The formula is preserved
  exactly; the lead must resolve it before promising backlog drainage.
- #24866 adjacent record_audio integration and #24893 aggregate alert integration
  remain lead dependencies. #24832 tests/wiring are salvaged, with closure left
  to its owner/lead2. No Part B discovery/index work is included.
- No live uploader / production acceptance or 48h shadow soak was performed.
  Lead2/P4 owns the ramp; gap-fill >=10 before serve 100 and the shared epoch
  remain explicit rollout prerequisites. All defaults remain off.

Implementation commits (the later receipt-only commit is not self-referenced):

- `c6f6d7f552a99b062988258432e3c606943ba063` feat: add server-renewed record custody token leases
- `5987486bf95942d0130b8a9f66bed1b407d71792` harden: preserve stock producer proofs and align lease seed checks
- `0b856a62ee57422cc770eb1fc1052c07caa050cf` chore: align token lease alert routing with fleet contract
- `bf6e5577c3c61f4dbb21af4ae419c402fb04dad3` harden: bind stock lease epochs across producer runtimes
- `d8fe1ef6c8fa338b1e9ad1368587a62035abc816` harden: renew leases while draining queued frame batches
- `94efbe1742a04d5a1824d77e00635d3062bcf237` harden: restore pre-seal producer custody after partial finish
- `d16393806a0a7f954b8104d993f4bba4a16d8e99` fix: preserve dark lease telemetry and bind runtime settings
- `ec4c08669e900e066ef7f0a4d6889b36978c58c5` test: declare no-job lease cohort context in writer inventory
- `7055900413180ecf8978f7b4f94f802db7313e97` fix: keep lease backlog alert quiet after drain completes
- `67a1ca2b590e9f1d38230f61698ef55f45ec539c` test: include dark lease settings in synthetic Cloud Run revisions

Changed files relative to the pinned starting base (52):

- `backend/charts/backend-listen/dev_omi_backend_listen_values.yaml`
- `backend/charts/backend-listen/prod_omi_backend_listen_values.yaml`
- `backend/charts/backend-listen/values.yaml`
- `backend/charts/batch-pipeline-worker/templates/_record-token-lease.tpl`
- `backend/charts/batch-pipeline-worker/templates/record-seal-repair.yaml`
- `backend/charts/batch-pipeline-worker/templates/record-seal-worker.yaml`
- `backend/charts/batch-pipeline-worker/values.yaml`
- `backend/charts/monitoring/alerts/record-token-lease.json`
- `backend/charts/monitoring/prometheus-stackdriver-exporter/dev_omi_cloud_run_metrics_exporter.yaml`
- `backend/charts/monitoring/prometheus-stackdriver-exporter/dev_sync_omi_cloud_run_metrics_exporter.yaml`
- `backend/charts/monitoring/prometheus-stackdriver-exporter/prod_omi_cloud_run_metrics_exporter.yaml`
- `backend/charts/monitoring/prometheus-stackdriver-exporter/prod_sync_omi_cloud_run_metrics_exporter.yaml`
- `backend/charts/pusher/dev_omi_pusher_values.yaml`
- `backend/charts/pusher/prod_omi_pusher_values.yaml`
- `backend/charts/pusher/values.yaml`
- `backend/config/record_seal_rules.py`
- `backend/config/refactor_modes.py`
- `backend/database/record_audio.py`
- `backend/database/record_partial.py`
- `backend/database/record_token_lease_metrics.py`
- `backend/deploy/runtime_env.yaml`
- `backend/deploy/runtime_env/_base.yaml`
- `backend/docs/feature-flag-registry.md`
- `backend/docs/listen_pusher_pipeline.mdx`
- `backend/docs/listen_pusher_pipeline/changes/2026-11-09-record-token-lease.md`
- `backend/routers/pusher.py`
- `backend/routers/sync.py`
- `backend/testing/lifecycle_properties/README.md`
- `backend/testing/lifecycle_properties/test_properties.py`
- `backend/tests/integration/test_held_custody_conformance.py`
- `backend/tests/integration/test_recovery_custody_conformance.py`
- `backend/tests/support/lifecycle_state_table.py`
- `backend/tests/support/lifecycle_writer_inventory.py`
- `backend/tests/unit/test_backend_runtime_env_validator.py`
- `backend/tests/unit/test_monitoring_telemetry_contract.py`
- `backend/tests/unit/test_pusher_record_abandon.py`
- `backend/tests/unit/test_record_partial.py`
- `backend/tests/unit/test_record_pending_repair.py`
- `backend/tests/unit/test_record_producer_proof.py`
- `backend/tests/unit/test_record_seal_repair.py`
- `backend/tests/unit/test_record_token_lease.py`
- `backend/tests/unit/test_record_token_lease_deploy.py`
- `backend/tests/unit/test_sync_v2.py`
- `backend/utils/batch_pipeline/CONTRACT.md`
- `backend/utils/batch_pipeline/record_producer_proof.py`
- `backend/utils/batch_pipeline/record_seal_cluster_repair.py`
- `backend/utils/batch_pipeline/record_seal_nojob.py`
- `backend/utils/batch_pipeline/record_seal_repair.py`
- `backend/utils/observability/firestore_probe_export.py`
- `backend/utils/pusher_record_barrier.py`
- `config/deployment-setting-classification.json`
- `config/feature-flags.yaml`
