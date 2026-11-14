# Pipeline drain warning policies

Owner: omi-pipeline. Evidence: wave 4 `WAVE4-1715Z.md` (Now 1, Overnight guards),
`out-t8.md`, `out-t5.md` in the workspace run
`data/run-2026-11-05-omi-pipeline/swarm-oversla-1105/`; held-age request: coordinator 8b38e3.
Evidence cutoff: 2026-11-05T17:15Z. **review_by: 2026-11-07** (coordinator reviews thresholds after the drain).

These are alert-only warnings. No scheduler, ramp, rollback, release gate or autoscaling decision reads them.
The Telegram receiver matches batch-timeliness. Warning timing follows the existing notification contract
(5m group wait, 1h group interval, 24h repeat), as on the batch-timeliness warning diagnostics; these are human
warnings without the agent mute. Grafana resolves on a healthy evaluation (`keep_firing_for=0s`); log queries zero-fill absent series, so these
recover through the false threshold. Unfilled vanished held-leg series resolve after two evaluations
(`missingSeriesEvalsToResolve=2`). No Cloud Monitoring native policy is added.

| UID | Signal | Strict threshold | Pending |
| --- | --- | --- | --- |
| `omi-pipeline-upload-503-storm` | backend-sync POST `/v2/sync-local-files`, status 503, responseSize 266 | >100 entries in each trailing minute | 10m |
| `omi-pipeline-firestore-contention` | `FirestoreContentionExhausted` log entries, fleet sum | >20 entries in each trailing minute | 10m |
| `omi-pipeline-projection-drain-stall` | completed owner_drain turns: claim_busy turns / all turns OR advanced rows / wall second, trailing 5m | >50% OR <10/s, while fresh pending projection debt exists | 15m |
| `omi-pipeline-held-row-age` | oldest all-epoch held row, independently by leg | >21600 seconds (6h) | 10m |

## Sources and verification

`log-metrics.json` declares project-level Cloud Logging API metric bodies, following the existing
`backend/deploy/record-seal-sweeper/log-metrics.json` pattern. They contain no IDs or free-text labels.
An operator must provision them separately before importing rules. This PR neither provisions nor verifies them.

The upload filter uses platform request logs, the upload route (with optional query string/trailing slash),
method POST, status 503 and exactly 266 response bytes. The size is a custody-wait **proxy**, not captured response
body proof; 259-byte `sync_batch_unavailable` responses and polling requests are excluded. `out-t8.md` gives the
size-class attribution but does not contain a literal full filter or an explicit contention service list. We
scope contention to backend-sync, backend-sync-backfill and backend-integration. The paired owner-drain
metrics cover those serving services plus backend-projection-pump, preserving the claim_busy numerator and
turn denominator scope and the existing metric names/queries. This filter extension requires a separately
approved reconciler apply, readback to MATCH and new service-scoped ingestion evidence; it does not backfill
pump history. Contention matches textPayload or jsonPayload.message. Verify counts with the exact
committed filter in one-minute buckets; counts are log entries, not unique failed transactions.

Main exposes no owner-drain GMP counters. The authoritative existing line is:

```text
event=batch_projection action=owner_drain outcome=turn steps=%d advanced=%d more=%s stop=%s elapsed_ms=%d
```

Use a distribution extracting `advanced` including zero. Its `_sum` yields advanced rows; `_count` yields turns.
A second counter matches `stop=claim_busy` on that same turn line. This avoids treating rows as turns, averaging
per-revision ratios, or adding runtime instrumentation to the drain. The producer currently preserves
textPayload; a future JSON migration must migrate these metric filters and extractor together. No raw log
scan runs during rule evaluation.

Queries use the existing `gmp-cloud-run` Prometheus datasource and its project-scoped frontend, including
`monitored_resource="cloud_run_revision"`. Cloud Monitoring exposes log-based metrics through that API;
[its documented mapping](https://docs.cloud.google.com/monitoring/promql) replaces the first slash with a colon
and the remaining punctuation with underscores, and supports distribution `_sum`/`_count` suffixes.
This avoids the legacy Cloud Monitoring datasource PromQL evaluator failure documented by daily-recap alerts.
All log queries use `offset 10m`: their 1m count or 5m rate window ends ten minutes before evaluation.
[Cloud Logging documents up to ten minutes of metric-update delay](https://docs.cloud.google.com/logging/docs/logs-based-metrics/troubleshooting).
This preserves the requested per-minute thresholds and pending windows while allowing on-time metrics to settle:
expect roughly 20m before storm/contention firing and at least 25m for drain stalls (plus rate-window and
notification grouping delays). This is a deliberate latency tradeoff, not a live delay measurement. Late-arriving
logs beyond that allowance and rare metric gaps can still affect detection. No backfill is available before
metric creation. Operators must verify source completeness and compare the same delayed window before admission.
Declared metric names are scoped to GMP in the inventory; they are **not** added to observed metric evidence.
Verify `_sum` and `_count` exist, advance, and agree with a bounded turn-log census before notification admission.
Missing busy counts mean zero busy; missing turn logs mean zero throughput. The rate denominator is wall time,
not logged elapsed_ms. A fresh positive all-epoch runnable projection age enables the drain warning; idle/empty queues
remain quiet. Existing timeliness sample stale alerts own unavailable debt measurements. A roll has the full
15-minute pending period to recover; this adds no post-train gate.

Held stock uses `omi_batch_held_oldest_age_seconds{leg}` from three indexed oldest-first queries
that skip invalid leg clocks:

- quarantine_held: result projection_state, clocked from committed_at;
- assignment_held: committed job with recovery_state held, clocked from enqueued_at;
- record_pending: job state, clocked from enqueued_at.

There is no epoch or rolling 24h predicate. Even a stock larger than a scan page yields its exact oldest row;
empty stocks reset to zero. Valid held stock stops at its first row; invalid clocks require
additional reads, using existing query/index shapes. Sample errors preserve the last values and freshness. Freshness is checked on the
same producer series before max-by-leg aggregation; missing/stale samples are owned by the existing
`omi-batch-timeliness-sample-stale` warning. The 24h-capped `omi_batch_record_pending_new_oldest_age_seconds` is
not a source. Existing new-cohort 2h delivery semantics remain unchanged. The fourth indexed oldest-row read exports
`omi_batch_projection_drain_oldest_age_seconds` for pending/persisted/ready only, so held-only stock never
enables the stalled-drain warning. It shares timeliness sample freshness (1200 seconds) and the newest-source identity join.

## Offline checks and operator admission

```bash
python backend/scripts/provision_monitoring_alerts.py --regenerate
python backend/scripts/provision_monitoring_alerts.py --lint
python backend/scripts/alert_backtest.py --lint
```

Split rules are maintained in `alerts/pipeline-drain.json`; the offline regeneration mode preserves existing
combined-rule order, then appends new UIDs. Run backend unit tests for the monitoring contracts, backtest,
provisioner and timeliness sampler. Synthetic evaluation covers both branches, strict boundaries, missing
frames, recovery and the pending windows. It does not establish live ingestion or delivery.

Before manual import, the coordinator must verify metric provisioning, nonempty fresh series on each named
datasource, live filter counts and receiver delivery. These warnings are intentionally outside the release
`live-alert-gate.json` allowlist. No workflow change is needed for the existing standalone alert provisioner.
Rollback: pause the four UIDs or revert their split definitions and regenerate the combined export; no drain,
scheduler, capacity or custody state is changed. The read-only held gauge may remain deployed.

## Oldest-age sampler flat for one hour

`omi-oldest-age-gauge-flat-1h` is an agent-tier warning, muted by `omi-tier-silent`.
It counts each positive series whose one-hour maximum equals its minimum for
projection obligations, vendor-held work, summary debt and demand processing.
Each series must also have an observation at least 3300 seconds (55 minutes) old
in that one-hour window: `time() - min_over_time(timestamp(age)[1h:1m]) >= 3300`.
The timestamp subquery uses the same labels as the age series, so a new replica
cannot borrow another replica's history. It tolerates five minutes of scrape/grid
alignment without assuming that these independently scheduled producers share a
sample cadence. This establishes an observed span, not uninterrupted scrapes;
freshness companions still own collection gaps. A single new positive sample or
ten minutes of constant samples cannot qualify. The condition must then persist
for ten minutes (`noDataState: OK`), earliest about 65 minutes after first observation.
Zero is a healthy empty queue. Missing age emitters contribute zero.
This detects frozen sampling: live ages increase while a head is stuck and fall
when it drains. Drain-stall and age-threshold rules still own stalled processing.

Check the emitting pod's supervised tick logs; restart the pod; confirm the gauge
resumes changing. This alert authorizes no runtime changes beyond a pod restart.
Check projection-obligation `omi_batch_projection_obligation_observed_at_seconds`
and the existing `omi-batch-queue-safety-blind` companion on
`omi_batch_pipeline_metrics_refreshed_at_seconds` for queue sampling blindness.
Fresh-gated timeliness/queue ages vanish instead of going flat; their existing
sample-stale/blind rules own that absence. Summary ages additionally require the
matching replica's `omi_summary_debt_sample_timestamp_seconds` to be younger than
300 seconds, per `backend/docs/runbooks/summary-guarantee.md`. A former lease
holder's retained positive gauge must not count after its sample expires. Compare
series with their original labels rather than aggregating ages across replicas.

**Separate debt: summary-debt producer blindness.** This rule does not alert on a
missing, zero or stale summary timestamp. Repair is optional and can be disabled;
there is no exported enablement/expected-producer signal to distinguish that
intentional state from collection failure. Add a separate enablement-aware
freshness rule once that signal exists, then verify its disabled/rollback path.
Until then, excluded or absent summary samples are unknown coverage, not evidence
of healthy repair. The flat rule never fabricates a failure with `or vector(1)`.

The held-age sampler skips nonnumeric, nonfinite and nonpositive leg clocks,
continuing oldest-first with a snapshot cursor until a usable clock is found.
Each RPC retains `limit(1)`, so healthy stock still reads just its first row. Empty or entirely undated
stock emits zero age; it is not evidence that no held rows exist. This only changes
metric sampling, never stored rows or lifecycle decisions. Valid stock still stops
at its first row; a corrupt prefix requires additional reads, with no cohort or
scan-page cutoff. The projection-drain clock and new-cohort metrics are unchanged.

Deploy the guard through the normal backend train. After merge, an authorized
operator dispatches `grafana_dashboard_provisioning.yml` with `environment=prod`
for alert definitions; a main push provisions dev only. Run the provisioner's
read-only drift check against production, then verify both new UIDs, tier, mute,
query and no-data state in Grafana. The flat rule is expected quiet given the N5
2026-11-08T14:03–14:10Z baseline; recheck current signals at deployment.
Rollback: pause the new UID or revert its split definition and regenerate/reapply.
Revert the sampler commit through the backend train if needed; no data repair is
required. The existing held-row-age rule's tier and 21600-second threshold are
unchanged; it lands paused under the import ruling below.

## Production import disposition (lead2 ruling 699300, 2026-11-08T15:13Z)

The dry-run of the 66 unprovisioned/changed rules measured production aggregates
at 2026-11-08T14:05–14:59Z. Known backlog pages land paused, with their existing
thresholds intact. Pausing suppresses notification coverage; the drain owners
track the known debt until an explicit unpause change. This is alert preparation,
not permission to deploy, drain, alter row state or unpause automatically.

| Paused UID | Written unpause criteria |
| --- | --- |
| `omi-pipeline-held-row-age` | After #24731/#24893 drain work and the N5 invalid-clock sampler guard reach production, require fresh samples of every held leg below 21600s continuously for 24h. The drain owner must approve a separate unpause change; missing, stale or undated samples do not count as healthy. |
| `omi-batch-unit-unpublished-2h` | After #24731/#24893 drain work reaches production, require both fresh timeliness and queue sources below 7200s continuously for 24h, with no blind scan. The drain owner must approve a separate unpause change; missing or stale samples do not count as healthy. |
| `omi-enrichment-fresh-dwell` | After #24893 enrichment drain work reaches production, require fresh, untruncated fresh-cohort observations below 3600s continuously for 24h. The lifecycle owner must approve a separate unpause change; missing or stale samples do not count as healthy. |
| `omi-record-pending-dwell` | After #24893 record-admission drain work reaches production, require fresh, untruncated record_pending cohort observations below 7200s continuously for 24h. The lifecycle owner must approve a separate unpause change; missing or stale samples do not count as healthy. |
| `omi-pipeline-projection-drain-stall` | After #24731 projection drain work reaches production, require fresh projection-debt samples and complete delayed turn metrics continuously for 24h: either no pending projection debt, or claim_busy share <=0.5 and progress >=10 rows/s. The drain owner must approve a separate unpause change; missing or stale samples do not count as healthy. |

`omi-batch-queue-safety-blind` remains an active page: its freshness arm now
requires at least 900s staleness plus 5m pending. The worker-plane cadence was
approximately 514s in the dry-run; 120s falsely breached between healthy samples.
Other query arms and all backlog thresholds are unchanged. This adjusts alert
freshness only; worker sampling, custody and admission are unchanged.

`omi-finalization-byok-dwell-page` keeps its UID, strict 259200s threshold and 1h
pending window, but lands active as severity warning, tier/audience agent, with
`omi-tier-silent` and sibling warning notification timings. It reaches no human
page receiver while muted. The measured 219900s BYOK stock could cross in about
11h if it keeps aging; that prediction is conditional, not fresh acceptance.

After an authorized prod provisioning dispatch, read back all five paused flags,
900s freshness, BYOK routing, exact unchanged backlog thresholds and the agent
mute. Record the running backend release identity and fresh clock-guard sample
before importing. Undo an incorrect import using the provisioner's backup; do
not restore the known 120s false-page arm as a rollout shortcut. Reverting these
definitions requires another authorized provisioning apply; source edits alone
do not change production Grafana.
