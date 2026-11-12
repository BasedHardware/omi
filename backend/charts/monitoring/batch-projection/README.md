# Batch projection and timeliness alarms

The all-epoch compute-queue alarm and bounded-scan blindness page are in
`../alerts/batch-queue-safety.json`; see
`../../../docs/runbooks/batch-queue-safety.md`. They are independent of the
epoch-scoped delivery rules below. They do not waive held recovery or custody.

`alerts.yaml` holds the projection-obligation PrometheusRule. Prod runs no Alertmanager, so that file is a record,
not a live route. Live alerts are Grafana-managed rules in `../alerts/*.json`.

## 2-hour timeliness alarm (David, 2026-11-02)

Target: process most batch audio within 30 minutes of admission, and alarm when a unit is still unpublished after
2 hours. Failed-held, quarantined and repair waits count, because that is how 165 segments were lost on 2026-11-01.

The batch worker queue sample exports these series (`utils/batch_pipeline/metrics.py`, at most once per 5 minutes
per data namespace on healthy leases with election enabled, across serving and GKE worker processes):

| series | meaning |
|---|---|
| `omi_batch_timeliness_new_oldest_age_seconds{leg}` | oldest unpublished unit admitted at or after the epoch. `uncommitted`, `quarantined` and `assignment_held` clock from `enqueued_at`; `projection` and `quarantine_held_rows` clock from `committed_at`, a lower bound |
| `omi_batch_timeliness_new_over_sla_units{leg}` | units admitted at or after the epoch and unpublished past 2 h, per leg |
| `omi_batch_timeliness_backlog_units{leg}` | unpublished units from before the epoch; each leg capped at 10,000 with election enabled (a lower bound at the cap); assignment-held growth or saturation feeds a separate page |
| `omi_batch_timeliness_scan_truncated{leg}` | 1 when a walk page is full and may hide an older admission (`uncommitted`, `projection`); the blind rule fires after 30 minutes, which is expected during large catch-up uploads |
| `omi_batch_timeliness_samples_total{outcome}` | `ok`, `error`, `disabled` |

The ship-on `FIRESTORE_READ_LEVERS` lever `batch_timeliness_leader` (default 100) uses the
`LeaderLease` role `timeliness_metrics` in `{namespace}_leases`, independent of queue
metrics and maintenance. Its TTL covers the sampling interval (default 300 s, clamped to 60–600 s) plus a fixed 60 s
refresh grace (default TTL 360 s, maximum 660 s for new leases). The 600 s ceiling leaves headroom below
the <1200 s freshness budget, so successful recurring samples can sustain the held-backlog page's
full 15-minute pending window. Configuring 3600 s now clamps to 600 s; hourly sampling is no longer supported.
This keeps a successful sample
visible through normal supervised tick jitter and RPCs, preserving continuous
5-minute breach evaluation. Another holder waits for that full TTL before takeover.
After losing an election, a follower retries every 60 s (at most one lease
transaction per minute), rather than waiting another full sampling interval.
This bounds takeover delay after lease expiry to 60 s plus supervisor scheduling;
successful leaders still sample only at the configured interval. The lease gates
each retry, so non-leaders execute no timeliness queries. Before a successful sample
and after losing the lease, all
sampler gauges (including drain/held ages and the observation timestamp) are absent.
Failures retain the previous stored values and timestamp without extending their
collection deadline; expired samples stay absent even after a fail-open lease retry. In every election mode,
including lever 0, samples expire at collection after the interval plus 60 s from the start of the attempt
that last succeeded. Changing the lever cannot revive them. A stalled replica's old breach cannot borrow
another replica's fresh timestamp. Lease-store errors fail open using the existing lease behavior.

With `batch_timeliness_leader` enabled, each pre-epoch aggregation applies `limit(10000).count()`; a saturated value means
**at least** 10,000 units. Post-epoch SLA counts and the oldest-unit queries retain
their semantics. The separate `omi-batch-held-backlog-growing` page fires on assignment-held stock >1000
with 1h growth >50, **or stock >=10,000**, with a <1200 s fresh sample for 15 minutes. Each stock series is
filtered by its own observation timestamp with `and ignoring(leg)` before taking the fleet maximum;
only stock has the extra `leg` label. Every other replica/resource label must match. The comparison omits
`bool` so a stale timestamp is absent from the set join. Both growth (including its 1h subquery) and
saturation use this fresh fleet value, with a zero fallback if none qualifies. Saturation is actionable
held debt, not proof of growth: a flat capped count must keep paging. The saturation branch needs no
growth history. Drain below the cap and inspect the held leg; do not infer exact stock or drain rate from
the capped value. See [critical failures](../critical-failures.md). This bounds historical
index entries per leg independently of stock size. For N healthy instances in one
namespace, election removes approximately (N−1)/N of sampler queries, plus the
historical count cap. Lease transactions are additional small reads, not samples.
No measured production savings are claimed.

Rollback: set `batch_timeliness_leader` to `0` in the existing `FIRESTORE_READ_LEVERS`
JSON on both planes. This restores per-instance sampling and unbounded exact
pre-epoch counts. Collection expiry remains bounded and the >=10,000 alert condition still applies to
exact counts. No new environment key is added. The existing global
`BATCH_PIPELINE_LEADER_LEASE_ENABLED=false` still bypasses election.

The timeliness alert inputs join each value to its own source's observation,
ignoring only the extra `leg` label. Before taking the fleet maximum, keep only
sources whose observation equals the newest fleet observation. All shared
resource labels (including namespace, job and instance) must match in the join.
A superseded Cloud Run leader can be replayed by the bridge's 10-minute lookback
with fresh scrape timestamps; numeric `observed_at` values, rather than scrape
timestamps, determine which source is current. A healthy GKE successor therefore
cannot lend freshness to the prior Cloud Run breach, or vice versa.

Observation selection uses `max_over_time(observed_at[20m])` per source. The
range retains observation values across instant-vector lookback gaps even if a
bridge preserves old point timestamps. The sample-stale rule compares the newest
numeric observation's age with 1200 seconds, retaining `or vector(1e9)` when all
observations disappear, `noDataState: Alerting` and the 5-minute pending period.
The 600-second maximum sample interval plus 60-second collection grace and up to
180 seconds of Monitoring/offset/scrape delivery delay totals 840 seconds, leaving
360 seconds for RPC/scheduling jitter below the 1200-second boundary. The same
1200-second freshness condition applies to breach, held, drain, backlog and blind
inputs; their business thresholds and pending periods stay unchanged. The blind
rule retains `noDataState: OK`. A stopped sampler still pages after freshness
expires; historical bridge replay cannot advance its numeric observation.

Every eligible leader must have the same export coverage. Cloud Run integration uses
`deploy/cloud_run_gmp_sync.yaml`; its GMP resource labels are
`cluster="__run__"`, `namespace="backend-integration"` (from `K_SERVICE`) and
`job="omi-cloud-run-application-metrics"` (the RunMonitoring name).
GKE uses `namespace="prod-omi-backend"` and the batch worker PodMonitoring job;
that PodMonitoring has no metric allowlist. The dev/prod sync Stackdriver exporter
prefixes must also import the timeliness families. The Prometheus bridge scrapes
them as `job="cloud-run-application-metrics"` and rewrites the metric names back to
`omi_*`. Keep timeliness selectors independent of job and namespace: a production
GKE namespace selector excludes the Cloud Run leader. For manual over-SLA
verification, join `omi_batch_timeliness_new_over_sla_units`
to the freshest observation as above before `max by (leg)`; this is guidance, not
an existing live count query. No alert or recording expression
currently consumes that count directly; the breach rule uses oldest age and
the freshness rule uses the observation timestamp, both with fleet-wide `max`.
`test_timeliness_metrics_are_scraped.py` derives all names from the producer's
timeliness registration section and checks both export filters. Deployment still
needs to qualify a sustained Cloud Run-led window in GMP and the alert datasource
at the configured sample cadence, including freshness and both handoff directions;
source coverage alone does not verify a live handoff.

An interval reduction across a restart can wait for the previous holder's stored TTL.
Older binaries could create a 3660 s lease under the former hourly interval contract; that stored lease
expires normally and is neither rewritten nor revoked by a new follower. New leases are bounded at 660 s.
Use a stable interval across the
fleet and account for that handover window when changing it. Restarting with
lever 0 bypasses the stored lease and restores per-instance queries.

Read attribution uses five fixed origins: `job:batch_pipeline_quarantine_recovery:held_candidates`,
`job:batch_pipeline_quarantine_recovery:recovery_candidates`, `job:record_seal_cluster_repair:discover_jobs`,
`job:record_seal_worker:pending_page`, and `job:batch_pipeline_store:timeliness_sample`.
The existing opt-in Firestore probe records these on its origin-labelled billed-read
counter when exported. GKE batch workers use a private metrics registry while the
Firestore probe counters register globally; the worker endpoint does not export
those counters. The repair CronJob has no metrics endpoint. Exporter work is scope B
and is not included here; labels alone do not make those GKE reads visible.

Legs:
- `uncommitted`: `ready`, `leased`, `result_ready`, `retry`, `vendor_held`, skipping deliberate admission holds
  (allowance, budget, fair use, daily ceiling) and live vendor holds.
- `quarantined`: every recovery state, including `failed_held` and `prepared`.
- `assignment_held`: committed, but the projection receipt is quarantined (job `recovery_state=held`), so the text
  never reached the conversation.
- `projection`: committed, projection `pending`, `persisted` or `ready`.
- `quarantine_held_rows`: result rows at `quarantine_held`. Counted, never alarmed: most are ready receipts whose text
  is already in the conversation and only the content ledger waits; the rest are the assignment holds above.
- `terminal_empty` (counts only): the quarantined units that are `failed_held` with recovery failure `empty_asr`
  and measured held VAD speech exactly 0, the existing silence contract for "no recoverable speech".

David, 2026-11-02 10:45Z: "finished recording counts as processed". So `TERMINAL_EMPTY_IS_PROCESSED` in
`config/batch_timeliness.py` defaults to `True`: terminal empty units are subtracted exactly from the `quarantined`
leg, and `terminal_empty` stays visible. `False` puts them back in the alarm. On prod at 2026-11-02 10:36Z, no
quarantined `empty_asr` unit had zero measured speech: 13 of 13 admitted since the epoch carried some (10 under
2 s), so today the default changes nothing. Units with measured speech always stay in the alarm.

Config: `BATCH_TIMELINESS_ALARM_ENABLED` (default on; `false` stops the Firestore reads),
`BATCH_TIMELINESS_EPOCH` (default `2026-11-02T06:09:00Z`, when the target was set) and
`BATCH_TIMELINESS_INTERVAL_SECONDS` (default 300, clamped to 60–600).

Reads per sample, worst case: 8 bounded walks of 20 documents (160; 9 with the terminal-empty switch on), the projection walk and its job reads (100), 3
single-document reads, and 17 count aggregations (one read per 1,000 index entries each, about 25 at today's backlog).
That is under 300 reads per process per sample. Sixteen workers at the default cadence read at most about 1.4M per day
(roughly $0.4–0.8/day); a healthy queue reads far less, because walks stop at the first unheld row. The
`assignment_held` leg needs the new jobs `(state, recovery_state, enqueued_at)` composite index, and `terminal_empty`
needs jobs `(state, recovery_state, recovery.failure.reason, measured_held_vad_speech_seconds, enqueued_at)`. Until
both are READY, the whole sample fails and counts as `error`, and the stale rule fires.

The metric is alert-only. No scheduler, ramp, hard-3 rollback trigger or gate reads it.

### Apply (lead)

The producer is now present in prod and the measured metric inventory includes its series. The three rules
live in `../alerts/batch-timeliness.json`, in the combined export and the existing `live-alert-gate.json` import
set. Gate changes trigger the existing metrics-egress workflow; no workflow change is needed. A committed
definition is not evidence that production Grafana has imported it.

1. Deploy the batch worker image and queue-age guard chart containing this fix **before** importing any
   queue-safety pages. Keep the audited worker min 6 / max 12 bounds.
2. Confirm in Prometheus that `max(omi_batch_timeliness_observed_at_seconds) > 0` and that
   `omi_batch_timeliness_samples_total{outcome="ok"}` increases.
3. Run the monitoring contracts. Dispatch the existing metrics-egress workflow for production at the reviewed
   main SHA, or use the documented Grafana provisioning path (`--apply --backup-file <new-file>`).
4. Read back every gated UID, its definition, unpaused state and receiver; distinguish import proof from actual
   notification-delivery proof.
5. Complete the delivery qualification in [critical-failures.md](../critical-failures.md) for the new
   critical-failure pages admitted alongside these rules.

`omi-batch-unit-unpublished-2h` is page tier with human audience and no agent mute interval: it uses the existing
Telegram receiver. The stale and truncated-scan diagnostics remain agent tier. The independent queue-safety blind
rule is page tier. The single lateness rule combines the new-cohort delivery legs with all-epoch active
compute commitments. Each source has its own freshness gate; no separate queue lateness UID duplicates it.
No contact point, secret or notification-policy tree is changed.

Rollback an incorrect definition with a forward revert and the same import;
keep real timeliness breaches tracked while reverting. The index step: merge
triggers the Firestore index reconcile; approve its prod job and wait for READY
before shipping the worker (merge_pr.sh waits out these gates).
