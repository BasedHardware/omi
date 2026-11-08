# Projection pump deploy bundle for cl2-deploy

Prepared 2026-11-08. This is a proposal for David's morning prod-gate batch;
**nothing below is approved or applied**. The code default remains off. Owner:
cl2-deploy executes only after David approves the named jobs; lead2 evaluates
the cutover evidence. Shape and rollback follow the
[pump design](2026-11-05-projection-pump.md).

## Preconditions

Step (i) below must finish before pump enablement: apply the declared Cloud
Logging metric `logging.googleapis.com/user/omi_pipeline_owner_drain_advanced`
in `based-hardware`, rerun the reconciler to `MATCH`, then prove actual ingestion
through the `gmp-cloud-run` Prometheus datasource. A metric definition alone is
insufficient. Use these queries; both must return nonempty, advancing series:

```promql
sum(increase(logging_googleapis_com:user_omi_pipeline_owner_drain_advanced_sum{monitored_resource="cloud_run_revision",project_id="based-hardware"}[5m] offset 10m))
sum(increase(logging_googleapis_com:user_omi_pipeline_owner_drain_advanced_count{monitored_resource="cloud_run_revision",project_id="based-hardware"}[5m] offset 10m))
```

The sum measures advanced rows and the count measures completed turns. Compare
the same window with a bounded census of the metric's exact turn-log filter.
Allow the documented ten-minute logging-metric delay; creation does not backfill
old logs. Do not zero-fill missing throughput and call it a healthy gate. See
[metric mapping and ingestion admission](../../../charts/monitoring/batch-projection/pipeline-alerts.md#sources-and-verification).

Before (ii), cl2-deploy must pin an eligible merged release SHA and immutable
CI-produced image digest containing the pump, resolve the runtime identity,
network, secret bindings and GMP scrape/export configuration from the serving
integration revision, and review the dedicated service deployment plan. Proposed
service name: `backend-projection-pump`, project `based-hardware`, region
`us-central1`. Preserve `BATCH_PIPELINE_SERVING_ENABLED=false` on this service so
turning the pump off leaves it inert. Never enable the pump on
`backend-integration` or another existing serving service.

Capture a dated pre-enable baseline of Firestore read rate, owner-drain rows/s,
claim_busy share, sweep elapsed time and executor saturation in the deployment
receipt. Retain/verify the read-rate alarm at +50% of that baseline and the
owner-drain floor at 70% of baseline. Missing baseline or alarms block cutover.
No live baseline or heartbeat-alert delivery was verified by this preparation.

## Exact proposed prod changes (owning tool on each line)

- **(i) Metric apply — `backend/scripts/messaging_operations.py`:** after David's approval, run `backend/.venv/bin/python backend/scripts/messaging_operations.py batch-projection-log-metrics --apply`, then `--check`; this reconciles **all four** bodies in `backend/charts/monitoring/batch-projection/log-metrics.json`: `omi_pipeline_upload_admission_503`, `omi_pipeline_firestore_contention_exhausted`, `omi_pipeline_owner_drain_advanced`, `omi_pipeline_owner_drain_claim_busy`.
- **(ii) Dedicated service deploy — cl2-deploy's approved GitHub Actions / Cloud Run deployment path (`google-github-actions/deploy-cloudrun`, under the prod-train lock):** deploy `backend-projection-pump` using the pinned CI digest, always allocated CPU (`--no-cpu-throttling`), N=4 (`--min-instances=4 --max-instances=4`), `BATCH_PIPELINE_PUMP_SWEEP_PAGES=1`, `BATCH_PIPELINE_PUMP_TICK_SECONDS=2`, `BATCH_PIPELINE_MAX_OWNER_DRAINS=8`, `BATCH_PIPELINE_SERVING_ENABLED=false`, `BATCH_PIPELINE_PROJECTION_PUMP_ENABLED=false`, with reviewed integration-compatible runtime bindings and GMP export; David's approval required.
- **(iii) Pump enable — service-scoped Cloud Run revision via cl2-deploy's approved config path, in three gated steps.** Nothing here is run by this PR.
  - **(iii-a) Capture the prior revision.** Record the serving revision and its traffic before any change: `gcloud run services describe backend-projection-pump --project=based-hardware --region=us-central1 --format='yaml(status.traffic,status.latestReadyRevisionName)'`. Save the output with the approval record. The prior revision name is `PRIOR_REV`.
  - **(iii-b) Create the flag-on revision without routing traffic:** `gcloud run services update backend-projection-pump --project=based-hardware --region=us-central1 --no-traffic --update-env-vars=BATCH_PIPELINE_PROJECTION_PUMP_ENABLED=true`, keeping (ii)'s bounds and serving flag. The new revision name is `NEW_REV`, read from `status.latestReadyRevisionName`.
  - **(iii-c) Shift traffic and verify it is serving:** `gcloud run services update-traffic backend-projection-pump --project=based-hardware --region=us-central1 --to-revisions=NEW_REV=100`. Verify `status.traffic` shows `NEW_REV` at 100 percent, that `gcloud run revisions describe NEW_REV --format='value(spec.containers[0].env)'` contains `BATCH_PIPELINE_PROJECTION_PUMP_ENABLED=true`, and that `omi_batch_projection_pump_last_tick_seconds` reports fresh ticks from the `NEW_REV` instances. Only a verified `NEW_REV` at 100 percent counts as enabled.
  - **Rollback for (iii), kept next to the step:** `gcloud run services update-traffic backend-projection-pump --project=based-hardware --region=us-central1 --to-revisions=PRIOR_REV=100`, then verify `status.traffic` shows `PRIOR_REV` at 100 percent and that `NEW_REV` has no traffic. Then, if needed, flip the flag off on a new revision as described under the (iii) rollback below. If (v) already ran, restore serving sweeps first.
  - David's approval required for (iii), and serving sweeps stay on throughout this dual-running phase.
- **(iv) Missing/stale alert — Grafana, via the existing reviewed alert pipeline (not an isolated file):** the rule is one new split source plus the regenerated combined export, applied only by CI, as follows.
  1. **Author the split source.** Add `backend/charts/monitoring/alerts/batch-projection-pump.json`, a JSON array of rule objects in the format of `alerts/batch-timeliness.json`. Each rule needs `uid`, `title`, `folderUID`, `ruleGroup`, `condition`, `data`, `noDataState`, `execErrState`, `for`, `annotations`, `labels` with `alert_identity` equal to `uid`, `isPaused`, and `notification_settings.receiver` equal to `Omi - Services Alerting (Telegram)`. Use the PromQL above as the expression.
  2. **Regenerate the combined export.** `python3 backend/scripts/provision_monitoring_alerts.py --regenerate`. It is offline, reads every `alerts/*.json` in sorted order, keeps existing rule order, and appends new UIDs to `backend/charts/monitoring/alert-rules.json`. Commit both files.
  3. **Offline validation.** `python3 backend/scripts/provision_monitoring_alerts.py --lint`. It fails if the split sources do not concatenate to the combined export. CI's `validate` job runs this too.
  4. **Read-only production checks.** With `MONITOR_GRAFANA_TOKEN` loaded from the approved secret store, run `python3 backend/scripts/provision_monitoring_alerts.py --probe-datasources`, then `python3 backend/scripts/provision_monitoring_alerts.py` with no mode flag, which prints drift only. Review every `DRIFT` line. Drift on any rule other than the new pump rule is a separate blocker.
  5. **Merge to `main` through review.** The `--regenerate` output is the reviewed artifact.
  6. **Apply only through CI.** `gh workflow run grafana_dashboard_provisioning.yml --repo BasedHardware/omi --ref main -f environment=prod`. Its `prod` Environment approval gates the step `python3 backend/scripts/provision_monitoring_alerts.py --apply --backup-file "$RUNNER_TEMP/grafana-alert-backup.json"`. That apply upserts every rule in the combined export and never deletes one, so the drift review in step 4 is the gate. The pre-apply backup is uploaded as the `grafana-alert-backup-<run_id>` artifact.
  7. **Rollback.** Revert the split source and combined-export commit on `main`, re-run the workflow, or pause only the new rule in Grafana. Restore from the `grafana-alert-backup-<run_id>` artifact if a rule must return to its captured definition.
  - Verify rule read-back, finite GMP data and receiver delivery before any serving-sweep switch-off, and preserve the read-rate and throughput alarms above.
- **(v) Later serving-sweep switch-off — reviewed ops-file change and `.github/workflows/config_train.yml` (plan, then approved apply):** set `BATCH_PIPELINE_SERVING_PROJECTION_SWEEP=off` only on the enumerated existing serving services that currently run these sweeps, after the sustained throughput gate below and verified (iv); preserve all other serving work and pump settings.

The existing backend workflow has no dedicated `backend-projection-pump` target;
this document does not add one or authorize a full-stack train as a substitute.
cl2-deploy must present the exact reviewed deployment/config invocation, service
bindings, the traffic revision names for (iii-a) to (iii-c), the receiving service
list for (v), and the reviewed `alerts/*.json` split source with its regenerated
combined export for (iv), before the corresponding approval/execution. No workflow, runtime manifest or alert rule is
changed by this prep PR. IAM/secret grants, if needed, are separate explicit asks.

For (iv), use the actual GMP dedicated-service label (verify whether it is
`service_name`; substitute the verified label consistently). Proposed condition
(fires when fewer than four instances have a tick in the last 120 seconds; this
covers a missing instance, a stale instance, and zero, and `or vector(0)` makes
an empty result count as zero rather than NoData):

```promql
(count((time() - omi_batch_projection_pump_last_tick_seconds{project_id="based-hardware",service_name="backend-projection-pump"}) <= 120) or vector(0)) < 4
```

Proposed pending time: 2 minutes, with query errors/NoData alerting, routed to the
existing pipeline receiver. This is a tick-liveness signal, not success: failed
ticks also update the gauge (the write sits in a `finally` block in
`backend/utils/batch_pipeline/serving.py`, so it runs after a retry too), so it
must never gate step (v). Test
missing, zero, stale, recovery and receiver delivery; verify four instances export
fresh ticks. Do not assert four-instance coverage from a single fresh series.

The (v) gate is **blocked** and cannot be satisfied by this bundle as written,
for two reasons:

1. **No success-only signal exists.** A sustained successful-pump signal must
   hold for the agreed window before (v). The only pump gauge is the tick-liveness
   heartbeat above, which failed ticks also update. A separately reviewed, dark
   code change must add a gauge set only after a successful sweep, with its own
   tests; until that lands and is deployed dark, (v) does not run.
2. **The owner_drain metric excludes the dedicated service.** The candidate query
   below covers only backend-sync, backend-sync-backfill and backend-integration. It
   proves the serving owner-drain floor, not pump throughput, so it cannot be the
   throughput gate for pump enablement. A pump-inclusive rate metric needs its own
   reviewed filter change and renewed observation.

Candidate serving owner-drain query, for reference only (not the (v) gate):

```promql
sum(rate(logging_googleapis_com:user_omi_pipeline_owner_drain_advanced_sum{monitored_resource="cloud_run_revision",project_id="based-hardware"}[5m] offset 10m))
```

When both are satisfied, the (v) gate is **owner_drain >=20 advanced rows/s
continuously for 30 minutes** on a pump-inclusive metric, evaluated every minute
over a settled window that starts after enablement, plus the 10-minute ingestion
offset and 5-minute rate lookback. All samples must be present and >=20; a short
spike or a missing sample fails admission. After (v), compare claim_busy share with
the baseline; it must not increase. Watch sweep duration and executor saturation
throughout. If any gate fails, leave serving sweeps on.

## Rollback for each step

- **(i):** retain the metrics if enablement stops; they do not run the pump. For a bad metric config, restore captured pre-apply bodies with the Logging metrics API (same reconciler after restoring the reviewed JSON); disable only newly created metrics with Logging `metrics.update` (PUT the full captured body with `disabled=true`), retaining their data. Capture existence and bodies before apply. No deletion is part of this bundle.
- **(ii):** keep both pump and serving flags false and return the dedicated service to its captured pre-step scaling/config through the deployment/config owner; for a new service, scale its minimum to zero to stop idle cost. Do not delete it as an implicit rollback.
- **(iii):** env-only rollback is the same service-scoped update command with `BATCH_PIPELINE_PROJECTION_PUMP_ENABLED=false`, through a new serving revision. Keep `BATCH_PIPELINE_SERVING_ENABLED=false` and owner capacity 8 there. If (v) already ran, restore serving sweeps **first**, then flip the pump flag false. Explicitly route traffic to and verify the new flag-off revision; a service pinned to an old revision can otherwise keep running the pump.
- **(iv):** restore the captured alert definition, or pause only the newly installed pump alert, via Grafana; keep serving sweeps on (restore them first if necessary). Retain unrelated alarms and rules.
- **(v):** set `BATCH_PIPELINE_SERVING_PROJECTION_SWEEP=on` on exactly the changed serving services through the config train and verify receiving revisions, then roll back (iii) if abandoning the pump. Owner drain capacity returns/remains at 8.

For every env/deploy step, record `status.traffic` revision names and percentages,
read `OMI_BACKEND_RELEASE_SHA` from **each receiving revision** (or resolve its
image digest to source), and retain the visible new metric/tick log evidence.
The service template alone is not deployment proof. Review rollback diffs before
execution; no data rewrite, lease reset or requeue-cap change is included.

## GATE ASK — David's morning prod-gate batch

Every job below is proposed and unapproved; no item implies approval of another.
David is asked to approve (i)–(iii) explicitly, plus the alert write and the later
cutover separately when their concrete inputs and gates are ready.

1. **(i) Apply all four batch-projection log metrics — REQUIRES DAVID'S APPROVAL.** Risk: project-wide metric configuration, ingestion cost and bad gate evidence; rollback: restore pre-apply bodies or disable only newly created metrics, retaining data. Include the reconciler diff and saved bodies in the ask.
2. **Metric ingestion verification and baseline capture (read-only).** Jobs: reconciler `--check`, bounded turn-log census, GMP sum/count queries and baseline/retained-alarm checks. Risk: delayed or incomplete data causing a false admission; rollback: stop admission and leave existing serving sweeps on. No approval is claimed by these reads.
3. **(ii) Deploy the dedicated four-instance service — REQUIRES DAVID'S APPROVAL.** Risk: idle compute cost, incorrect runtime bindings or unintended serving work; rollback: keep both flags false, restore captured config/scaling, minimum zero for a new inert service. This includes CI image build/admission if a suitable eligible digest is unavailable; its spend must be included in the concrete ask.
4. **(iii) Enable the dedicated pump — REQUIRES DAVID'S APPROVAL.** Runtime jobs enabled: one projection discovery loop per instance, one page per tick, discovered/owed asynchronous follow-ups (`start_followups`), owed index flush (`schedule_index_flush`) and owed owner drains (`start_drains`, capacity 8 per process). Risk: extra Firestore reads/writes, contention and executor pressure during dual running; rollback: pump flag false on that service, restoring serving sweeps first if already off. No new Scheduler, Cloud Tasks, record-admission, maintenance or quarantine-dispatch job is enabled on the dedicated service.
5. **(iv) Install and exercise the missing/stale alert — approval requested, UNAPPROVED.** Jobs: isolated rule apply/read-back and controlled missing/stale/recovery plus receiver-delivery checks; retain/verify read-rate +50% and owner-drain 70%-baseline alarms. Risk: false pages, missing-instance blind spots or a noisy receiver test; rollback: restore/pause only that rule and keep serving sweeps on. Any actual pump stop for alert testing uses the separately approved (iii) rollback.
6. **Sustained gate observation (read-only).** Jobs: settled-window throughput evaluation, sweep/executor/read-rate watch, and a dated receipt reviewed by lead2. Risk: early-window contamination or misattribution; rollback: fail closed on admission and retain dual running only within the approved observation period, otherwise pump=false. No unattended writer or automatic rollback job is installed by this bundle.
7. **(v) Later serving-sweep cutover — separate approval requested, UNAPPROVED and gated.** Jobs: exact serving-service inventory, ops-file plan/apply and receiving-revision verification, then post-cutover claim_busy/baseline watch. Risk: discovery stalls if the pump stops; rollback: serving sweep=on first, verify recovery, then pump=false if needed. Existing owner wakes, held drains, metrics refresh, maintenance and recovery dispatch remain running; this is not an approval to stop them.

## Tick clamp verification

This bundle uses `BATCH_PIPELINE_PUMP_TICK_SECONDS=2`: two seconds of sleep
**after** sweep work, not a guaranteed two-second wall-clock tick. In
`backend/config/batch_pipeline.py`, `projection_pump_tick_seconds()` calls
`_pump_bound(raw, 20, 60, 2)`, whose fourth argument is the minimum. The actual
range is **2–60 seconds**, default/malformed value **20 seconds**. It matches
the design's two-second safe start; **there is no clamp mismatch**. No config
code or default is changed by this bundle.

## Read-only preparation evidence

Measured 2026-11-08T06:52:46Z in this task worktree, using only the `ro-prod`
tier. Command: `source ~/.local/bin/gcp-agent-env.sh ro-prod`, then
`backend/.venv/bin/python backend/scripts/messaging_operations.py batch-projection-log-metrics --check`.
Exact stdout (exit **1**, planned drift; no writes):

```text
DIFF omi_pipeline_upload_admission_503
DIFF omi_pipeline_firestore_contention_exhausted
DIFF omi_pipeline_owner_drain_advanced
DIFF omi_pipeline_owner_drain_claim_busy
```

The reconciler's existing output uses `DIFF` for both absent and changed bodies.
A subsequent `ro-prod` `gcloud logging metrics describe omi_pipeline_owner_drain_advanced --project=based-hardware --format=json`
returned `NOT_FOUND: Metric omi_pipeline_owner_drain_advanced does not exist.`
Thus owner-drain advanced needs creation, not merely an update. Other `DIFF`
lines are not independent proof of absence. Neither `--apply` nor a prod write
was run. GMP ingestion, pump runtime health, alert delivery and the cutover gate
remain unverified and must not be inferred from this preparation.
