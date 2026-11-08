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
`RECORD_TOKEN_LEASE_DEPLOYED_AT` is the fixed serve-enable epoch (set by the release owner at first serve enable
and held fixed throughout the ramp; shadow uses a fixed preview epoch), not process-start time. The Helm guard refuses an enabled
mode without that epoch; off keeps the inert default zero. Bind the same epoch
on every pusher/custody writer through runtime_env and on repair through
recordTokenLease.deployedAt, so late stock renewals compute the same lapse and
revision bump as repair. Identified legacy tokens use
max(finished_at, abandoned_at, serve-enable epoch), bounded at the enable epoch;
only explicit server signals can extend beyond enable + lease. Retry wakes are
excluded. The refusal stamp is excluded because a successful seal clears it,
so a reopened record can receive a new stamp; it is not globally write-once.
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

Lead resolution (2026-11-09): moving repair/defer metadata cannot postpone stock
lapse. Historical anchors are capped at serve enable; post-enable metadata alone
is not a heartbeat. Server-observed signals newer than pod/abandon proof keep the
token alive, including a stale abandoned marker on an otherwise lapsed token.
The exact two pending alert objects are in `.agent-brief/alert-rules-addition.json`
for the aggregate owner; the aggregate mirror tests intentionally remain red.

The late-append page uses `increase(counter[5m]) > 0`, equivalent to the design's
positive rate trigger, with `for: 0s`. This expresses an invariant event without
weakening the generic noisy-rate pending-duration lint. Its first-event test passes.
The production metric inventory is also owned by #24893: exact source declarations
are handed off in `.agent-brief/metric-inventory-addition.json`, separately from
observed production series. Neither authoritative monitoring file changes in the final branch.

## Local validation receipt

Recorded 2026-11-08T23:54:02+00:00.

Branch `lane/tokenlease`, rebased cleanly onto freshly fetched `origin/main`
`db09790d1d76cf7b9247cfbaa6f4645946962a0a` (includes #24950, `fadad03099acbf133fa6461f8f928d606cf6a236`).
Runtime/custody suites ran at `25fd3ed07ca3`; alert tests and expanded checks at
`b2102be20c72`; corrected registry/Firestore checks at `06f8abb76e92d45dcb71629db0f72453aa53291d`.
The later receipt-only commit is reported separately in the final handoff.
Local only: no push, PR, deployment, PR closure or production access. GCP tier: **none**.

Every test launcher removes `GOOGLE_APPLICATION_CREDENTIALS`, all `CLOUDSDK_*`,
service-account/auth-file and external PostgreSQL test bindings. Private HOME,
config and temporary directories prevent ADC fallback. No backend stage env files
exist here. Units/custody use `OMI_ENV_STAGE=offline`; production route exports and
hermetic deployment checks use the production source surface without service access.
Custody requires all three store backends; Firestore uses `demo-omi-listen-stack`
on loopback, with private local PostgreSQL. No store-backend skips were accepted.

Actual heavy admissions:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-followup-validation.py
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-review-runner.py
```

The second runner executes the child commands below serially, then exits and
releases its slot. Shared slots/priorities were not changed. Full logs:
`/Volumes/Ephemeral/scratch/tokenlease-followup-results.log` and
`/Volumes/Ephemeral/scratch/tokenlease-alert-review-results.log`.
Commands/counts are preserved here independently of disposable launcher files.

### Focused units: 2,527 passed across 18 suites

Each command runs from `backend`, in its own interpreter:

```sh
.venv/bin/python -m pytest -q --tb=short <suite>
```

| Suite | Exact result |
| --- | --- |
| `tests/unit/test_record_token_lease.py` | 67 passed |
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
| `tests/unit/test_record_token_lease_deploy.py` | 8 passed |
| `tests/unit/test_monitoring_telemetry_contract.py` | 52 passed |
| `tests/unit/test_sync_v2.py` | 180 passed |
| `tests/unit/test_record_seal_worker.py` | 20 passed |
| `tests/unit/test_record_seal_worker_deploy.py` | 7 passed |
| `tests/unit/test_record_seal_cluster_repair_deploy.py` | 10 passed |
| `tests/unit/test_record_seal_worker_guards.py` | 13 passed |

The new lease suite proves exact old mint/clear/seal write payloads, no renewal IO
in off/unset modes, inert lease fields, and old terminal metric wire output after
rollback. New lead regressions cover moving retry wakes, metadata newer than
enable, strict newer-than-proof signals, and moving `available_at` between plan
and apply. Both plan/apply cases seal with the original fixed expiry.

### Custody and lifecycle

Under `firebase emulators:exec --only firestore --project demo-omi-listen-stack`,
with a private loopback config (`/Volumes/Ephemeral/scratch/tokenlease-validation-whznxqvi/firebase.json`):

```sh
# cwd backend, OMI_REQUIRE_STORE_BACKENDS=all
.venv/bin/python -m pytest -q --tb=short tests/integration/test_held_custody_conformance.py
.venv/bin/python -m pytest -q --tb=short tests/integration/test_recovery_custody_conformance.py
.venv/bin/python -m testing.lifecycle_sim.run --keep --state-dir /Volumes/Ephemeral/scratch/tokenlease-validation-whznxqvi/lifecycle --extra-test-module testing/lifecycle_properties/test_properties.py
```

| Suite | Exact result |
| --- | --- |
| Held custody | 75 passed |
| Recovery custody | 39 passed |
| Lifecycle scenarios/properties | 34 passed, 3 pre-existing xfailed |

All three `test_leased_lapsed_token_has_named_exit` rows passed:
`seal`, `partial_finish`, `reactivated`. Existing lifecycle xfails were not widened.

### Deployment, alerts and preflight

```sh
# cwd backend; hermetic default, no --live:
bash scripts/pre-deploy-check.sh
.venv/bin/python -m pytest -q --tb=short tests/unit/test_monitoring_alert_backtest.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_monitoring_notification_contract.py::test_severity_timing_and_actionable_annotations tests/unit/test_monitoring_notification_contract.py::test_split_and_combined_rule_objects_are_byte_identical tests/unit/test_monitoring_alert_rule_contract.py::test_combined_alert_export_matches_every_split_source_rule
# cwd repository root; private body file supplied via OMI_PR_BODY_FILE:
make preflight
backend/.venv/bin/python .github/scripts/pr_preflight.py --metadata-only --pr-body-file .agent-brief/tokenlease-pr-body.md
backend/.venv/bin/python backend/scripts/check_route_policy_baseline.py --base-ref origin/main
backend/.venv/bin/python backend/scripts/generate_plan_catalog.py --check --base-ref origin/main
```

| Command / gate | Exact result |
| --- | --- |
| Hermetic deployment pytest | 511 passed |
| Deployment source-admission unittest | 36 passed |
| PR metadata | 4 checks passed |
| Route-policy / plan catalog | Passed; zero new missing routes |
| Monitoring backtest suite | 28 passed, 1 failed (committed inventory admission) |
| Notification timing/actionable + two mirror checks | 1 passed, 2 failed (both mirrors) |
| `make preflight` | Exit 2 at `monitoring-alert-backtest-lint`; missing three owner-fenced declarations |
| Expanded manifest run | 55 distinct checks: 52 passed, 3 failed |
| Corrective named-check rerun | 2 checks passed: Firestore index guard and feature-flag registry |
| Final last-completed status for each selected check | 54 passed, 1 failed (owner-fenced alert inventory) |

The expanded command (changed-files list is `git diff --name-only BASE...HEAD`):

```sh
backend/.venv/bin/python .github/scripts/run_checks.py --lane local --base db09790d1d76cf7b9247cfbaa6f4645946962a0a --head HEAD --changed-files /Volumes/Ephemeral/scratch/tokenlease-final-changed-files.txt --pr-body-file .agent-brief/tokenlease-pr-body.md --keep-going
```

Its other two failures were corrected and rerun, without weakening assertions:

- The harness initially set `OMI_ENV_STAGE=prod` for every check. This made a
  non-publisher queue-age driver correctly record no queries: query-shape suite
  **558 passed, 1 failed**. The canonical guard was rerun under the documented
  offline test stage, with unchanged source/drivers/indexes: **842 passed across
  seven guard files**, including **559 query-shape tests**.
- A manual generated-doc description differed from its registry source. The
  source reason was corrected and the doc regenerated with
  `python3 scripts/render_feature_flag_registry.py --as-of 2026-11-05`.
  Only the source description changed; no review dates/exceptions were extended.
  The registry check passed, including #24950's UTC review-date handling.

Corrective command, still through the admitted heavy runner:

```sh
env OMI_ENV_STAGE=offline backend/.venv/bin/python .github/scripts/run_checks.py --lane local --base db09790d1d76cf7b9247cfbaa6f4645946962a0a --head HEAD --changed-files /Volumes/Ephemeral/scratch/tokenlease-final-changed-files.txt --pr-body-file .agent-brief/tokenlease-pr-body.md --check-id firestore-index-guard --check-id feature-flag-registry --keep-going
```

There is **no terminal-green full preflight claim**. The remaining inventory
failure is the same boundary as `test_committed_offline_admission_gate`:
`omi_record_seal_oldest_age_seconds`, `omi_record_token_late_append_total`, and
`omi_record_token_lease_expired_sealed_total` need adding to `declared_metrics`.
A temporary copy with exactly `.agent-brief/metric-inventory-addition.json`
applied passed `alert_backtest.py --lint --inventory <copy>`; the authoritative
inventory was asserted byte-identical to the rebase base and observed series
were not changed. No production observations are claimed.

Both mirror failures remain as requested:
`test_split_and_combined_rule_objects_are_byte_identical` and
`test_combined_alert_export_matches_every_split_source_rule`. The exact two alert
objects are in `.agent-brief/alert-rules-addition.json`, byte-identical to the
split file: `omi-record-token-lease-late-append`, `omi-record-token-lease-backlog`.
No test was skipped or converted to xfail for these boundaries.

## Design clarifications, deviations and open risks

- Latest lead rulings replace the body stock formula: retry/defer timestamps
  cannot renew a lease. `record_seal_refused_at` is excluded because successful
  seal clears it (`record_audio.py`), so it can be stamped again after reopen.
  Historical finished/abandoned anchors are capped at fixed serve enable.
- The stock deadline applies to identified legacy token dictionaries. Bare True
  and malformed tokens retain the design's existing conservative fences.
- `increase(counter[5m]) > 0` preserves the design's positive-rate trigger and
  immediate event paging. No generic lint exception or legacy debt was added.
- A preliminary metric-inventory edit was removed after checking #24893's full
  file list; its additions are handed off instead. Final branch content leaves
  the authoritative inventory and aggregate alert export unchanged. The routine
  shared feature-flag registry files remain within the design's allowed scope.
- The owner must integrate both monitoring handoffs before admission/mirror
  gates can be green. #24866 adjacent integration and #24832 supersession/closure
  remain lead responsibilities. No PR or closure was performed here.
- No production acceptance, signal-gap measurement, 48h soak or ramp occurred.
  Lead2/P4 owns 1/10/50/100 steps, stable serve-enable epoch, and gap-fill >=10
  before lease serve 100. Defaults remain off.
- No Part B work: `discover_jobs` and `seal_record_audio` AST bodies match the
  rebase base; index declarations, users.py, live.py, ProjectionReleaseStore,
  held_dead_letter files and aggregate alerts are unchanged. No raw audio is deleted.

## Local commits

Rebased implementation and follow-up commits, before the final receipt-only
commit (whose SHA is reported in the final handoff):

- `df76164b38bc03e4897b4b700d1102f8b16a8f24` feat: add server-renewed record custody token leases
- `c374b1e67203da9d62d87607802ed20e4f5422c0` harden: preserve stock producer proofs and align lease seed checks
- `0fdc4b0b11126e2221157454b98f25752d558ada` chore: align token lease alert routing with fleet contract
- `2a20c158bd503e48d30bf442ac2c7e8dff50afe6` harden: bind stock lease epochs across producer runtimes
- `2b7b66ddb41c70fd1a180154e8f742789cc0102e` harden: renew leases while draining queued frame batches
- `9c76cbc9bbf7cc0cb092919a65f80b8feabb9456` harden: restore pre-seal producer custody after partial finish
- `0af79875359bfb0caf1a7123c36fbb3591f9f855` fix: preserve dark lease telemetry and bind runtime settings
- `38f0572b1ae7db1dd0ce0852a23e7916113536b3` test: declare no-job lease cohort context in writer inventory
- `d06983dfc5952542428a7d51e31d8802f6585e8b` fix: keep lease backlog alert quiet after drain completes
- `644e75bd5f96af8a8707e746572598affdd294b1` test: include dark lease settings in synthetic Cloud Run revisions
- `454e114e730a00ef4e30ede530a3e69bf9f64556` docs: record token lease validation and lead handoff risks
- `2300ad1892493944f7f8c7559e15f10883326f6b` fix: bound legacy leases at serve enable and honor newer custody proof
- `25fd3ed07ca322b5d36a9ab428ddea9e078d3826` test: keep stock lease expiry stable across repair retry wakes
- `b2102be20c72c9d537470a27e018b5f425d46b8b` fix: page on first lease event and hand off metric declarations
- `06f8abb76e92d45dcb71629db0f72453aa53291d` fix: align lease epoch registry source with generated documentation

## Files changed (55)

- `.agent-brief/alert-rules-addition.json`
- `.agent-brief/metric-inventory-addition.json`
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
- `backend/tests/unit/test_monitoring_alert_backtest.py`
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
