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
Lead2 approved the monitoring owner additions (bus f0125d, relayed by David).
The two split rules are appended to the combined import: backlog is a warning,
and late append remains an unpaused custody-invariant page.

Late signals before seal bump upload revision and re-fence; apply transactions
re-read the exact token map. Live custody leases override stale pod/abandon proof
because uploaders can outlive the pusher. Tail/partial/privacy gates still apply;
late bytes after seal remain retained and are counted for gap-fill/revert.
Part B discovery and indexes are unchanged. Landing order updated 2026-11-10: #25018 first; then #24866 merges resulting main and reconciles both transaction intents.

Lead resolution (2026-11-09): moving repair/defer metadata cannot postpone stock
lapse. Historical anchors are capped at serve enable; post-enable metadata alone
is not a heartbeat. Server-observed signals newer than pod/abandon proof keep the
token alive, including a stale abandoned marker on an otherwise lapsed token.
The exact objects in `.agent-brief/alert-rules-addition.json` are now appended
to the aggregate. Both mirror tests pass.

The late-append page uses `increase(counter[5m]) > 0`, equivalent to the design's
positive rate trigger, with `for: 0s`. This expresses an invariant event without
weakening the generic noisy-rate pending-duration lint. Its first-event test passes.
The three source declarations in `.agent-brief/metric-inventory-addition.json`
are appended only to the production inventory's `declared_metrics`. Observed
series, capture time, legacy debt and all other inventory fields are unchanged.

## Approved monitoring follow-up

Recorded 2026-11-09T00:31:38+00:00 at `93e3ec087dffb80f0ecf0e9a3dc12ec2518ca88a`.
Lead2's YES in bus f0125d authorizes the two owner-file additions, relayed
explicitly by David. Existing alert object bytes and order were verified against
`6a03440964b9`; the exact two payload objects form the new tail. The inventory's
existing declared names remain its prefix, followed by the exact three payload
names; all other fields and bytes outside that insertion are preserved.

The full alert suite exposed a pre-existing static-scanner blind spot: the seal
worker constructed `omi_record_seal_oldest_age_seconds` through a local helper.
Its declaration is now an equivalent literal Gauge, with identical help text,
labels and registry. The existing HTTP metrics test now proves the exported
name, labels and sampled value. No alert query or assertion was weakened.

All runs used the existing heavy admission, private HOME/config/TMP, and removed
Google credentials, every CLOUDSDK_* variable and external PostgreSQL bindings.
OMI_ENV_STAGE and PROVIDER_MODE were unset for the repository checks: ordinary
route exports stay free of local harness routes, while units do not inherit a
production singleton role. No backend stage env files exist here; no GCP tier
or production service was used.

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-approved-monitoring-runner.py
# Separate interpreters, cwd backend, for each suite in the table:
.venv/bin/python -m pytest -q --tb=short tests/unit/<suite>
# Initial expanded run, cwd repository root, 57 changed files at 31cc5d6584e9:
backend/.venv/bin/python .github/scripts/run_checks.py --lane local --base db09790d1d76cf7b9247cfbaa6f4645946962a0a --head HEAD --changed-files /Volumes/Ephemeral/scratch/tokenlease-approved-changed-files.txt --pr-body-file .agent-brief/tokenlease-pr-body.md --keep-going
# Final expanded local lane, origin/main pinned at 6a03440964b9, 59 changed files:
make preflight
```

| Suite / gate | Exact terminal result |
| --- | --- |
| `test_monitoring_alert_backtest.py` | 29 passed |
| `test_monitoring_notification_contract.py` (full timing and mirror suite) | 8 passed |
| `test_monitoring_alert_rule_contract.py` (full suite, including aggregate mirror) | 75 passed |
| `test_monitoring_telemetry_contract.py` | 52 passed |
| `test_record_token_lease.py` | 67 passed |
| `test_record_seal_worker.py` | 20 passed |
| `test_record_seal_worker_guards.py` | 13 passed |
| Focused total | **264 passed, zero failed/skipped/xfail** |
| Expanded `run_checks.py --keep-going` at `31cc5d6584e9` (57 changed files) | **55 checks passed**, exit 0 |
| Final `make preflight` at `93e3ec087dff` (59 changed files) | **56 checks passed**, exit 0 |
| Append-only validation and `git diff --check` | Passed |

During final verification shared origin/main advanced. The first make preflight
stopped at its synthetic-merge line-count check because the alert aggregate had
parallel tail additions. The branch was rebased onto freshly fetched
`6a03440964b9ecf21330cc87a8b2c30dcce712da`; all upstream alert objects were retained
byte-for-byte and only the approved payload appended. The inventory merge was
verified against that same base. The focused suites and full preflight were
rerun after rebase; the table reports those final results. Current main added
the P6 state-exit disclosure gate, making 56 selected checks. Its first run
required the local draft to name lease_would_expire explicitly. The visible
draft now explains that it is a shadow-only diagnostic on upload_pending,
cleared by the next rebuilt plan: fresh signals renew custody, serve may take
the seal or partial_finish exit after tail/privacy gates, and a late append
takes reactivated with a new upload revision. It adds no persistent state or
retry deadline. No waiver was used.

The first combined monitoring run was 230 passed / 1 failed at the static
emitter check. The literal gauge declaration fixed that failure; every suite
above was then rerun in its own interpreter. No remaining red mirror,
notification-timing, inventory admission or preflight gate exists. The full
runtime/custody rerun below predates this monitoring-only follow-up and is not
claimed as rerun here. Full current log:
`/Volumes/Ephemeral/scratch/tokenlease-approved-monitoring-results.log`.

## Prior runtime/custody validation receipt

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

### Prior deployment validation

The hermetic `bash scripts/pre-deploy-check.sh` run passed **511 pytest tests**
and **36 source-admission unittest tests**. Prior metadata validation passed
four checks, and route-policy / plan catalog passed with zero new missing routes.
The old owner-fenced inventory and mirror failures are resolved by the approved
follow-up above. Earlier global-prod test-stage and generated registry-description
issues were corrected without changing production drivers, indexes, review dates
or exceptions; the final full preflight passes all selected checks.

## Design clarifications, deviations and open risks

- Latest lead rulings replace the body stock formula: retry/defer timestamps
  cannot renew a lease. `record_seal_refused_at` is excluded because successful
  seal clears it (`record_audio.py`), so it can be stamped again after reopen.
  Historical finished/abandoned anchors are capped at fixed serve enable.
- The stock deadline applies to identified legacy token dictionaries. Bare True
  and malformed tokens retain the design's existing conservative fences.
- `increase(counter[5m]) > 0` preserves the design's positive-rate trigger and
  immediate event paging. No generic lint exception or legacy debt was added.
- Lead2's explicit approval supersedes the earlier aggregate/inventory fence
  only for these append-only additions. No existing entries were edited.
- #24866 adjacent integration and #24832 supersession/closure remain lead
  responsibilities. No PR or closure was performed here.
- No production acceptance, signal-gap measurement, 48h soak or ramp occurred.
  Lead2/P4 owns 1/10/50/100 steps, stable serve-enable epoch, and gap-fill >=10
  before lease serve 100. Defaults remain off.
- No Part B work: `discover_jobs` and `seal_record_audio` AST bodies match the
  rebase base; index declarations, users.py, live.py, ProjectionReleaseStore,
  held_dead_letter files are unchanged. Aggregate alerts only gained the approved tail. No raw audio is deleted.

## Local commits

Implementation and validation commits before the final receipt-only commit:

- `d7cff12b2f9ca1b50bb6212d77e571a76396d392` feat: add server-renewed record custody token leases
- `38f6698264f816df836a2bf9e683391c5d6a7959` harden: preserve stock producer proofs and align lease seed checks
- `885513edf54e8cd23f600081c132ebe2701058fd` chore: align token lease alert routing with fleet contract
- `babc38dc71e20779fc25da1c4b93b39fd91a5b27` harden: bind stock lease epochs across producer runtimes
- `29513a717fc0c46ab913205408f20c39413d6d8d` harden: renew leases while draining queued frame batches
- `62960994c021bab3718f82fef69901a4dd100028` harden: restore pre-seal producer custody after partial finish
- `90f28835dbae83061e537aa6a9037ecd98c8cd25` fix: preserve dark lease telemetry and bind runtime settings
- `996c0ace3436ebe056f5cb2ffd530a688db73a30` test: declare no-job lease cohort context in writer inventory
- `58a817ca0680894d859a0e6017f456febb3eebfa` fix: keep lease backlog alert quiet after drain completes
- `a99cad0f46561c0b282a80ce80e300f907d3cf57` test: include dark lease settings in synthetic Cloud Run revisions
- `ed4a28ccab0ae8fa4c24d657472c4e0ca658a10e` docs: record token lease validation and lead handoff risks
- `2844b9c5c9dc547c9e7646edad8532bd039a9082` fix: bound legacy leases at serve enable and honor newer custody proof
- `b307d55ac79daeac2b349dbb3c061c72adb4ce21` test: keep stock lease expiry stable across repair retry wakes
- `9a97176ca53c4da79e144659d4079c6a15e9277c` fix: page on first lease event and hand off metric declarations
- `5b19cc2273afb671459e138634b036a599f57b1c` fix: align lease epoch registry source with generated documentation
- `9c1652930abf638b57ce37461a94101deb64a2b7` docs: record rebased token lease validation and owner handoffs
- `d8daf1e97a5eb9e60448c7556bde34f071023715` chore: admit approved record token lease monitoring additions
- `93e3ec087dffb80f0ecf0e9a3dc12ec2518ca88a` fix: expose seal age gauge declaration to alert admission

## Files changed (59)

- `.agent-brief/alert-rules-addition.json`
- `.agent-brief/metric-inventory-addition.json`
- `backend/charts/backend-listen/dev_omi_backend_listen_values.yaml`
- `backend/charts/backend-listen/prod_omi_backend_listen_values.yaml`
- `backend/charts/backend-listen/values.yaml`
- `backend/charts/batch-pipeline-worker/templates/_record-token-lease.tpl`
- `backend/charts/batch-pipeline-worker/templates/record-seal-repair.yaml`
- `backend/charts/batch-pipeline-worker/templates/record-seal-worker.yaml`
- `backend/charts/batch-pipeline-worker/values.yaml`
- `backend/charts/monitoring/alert-rules.json`
- `backend/charts/monitoring/alerts/record-token-lease.json`
- `backend/charts/monitoring/metric-inventory.prod.json`
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
- `backend/tests/unit/test_record_seal_worker.py`
- `backend/tests/unit/test_record_token_lease.py`
- `backend/tests/unit/test_record_token_lease_deploy.py`
- `backend/tests/unit/test_sync_v2.py`
- `backend/utils/batch_pipeline/CONTRACT.md`
- `backend/utils/batch_pipeline/record_producer_proof.py`
- `backend/utils/batch_pipeline/record_seal_cluster_repair.py`
- `backend/utils/batch_pipeline/record_seal_nojob.py`
- `backend/utils/batch_pipeline/record_seal_repair.py`
- `backend/utils/batch_pipeline/record_seal_worker.py`
- `backend/utils/observability/firestore_probe_export.py`
- `backend/utils/pusher_record_barrier.py`
- `config/deployment-setting-classification.json`
- `config/feature-flags.yaml`
