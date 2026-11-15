# Batch queue safety: late work and incomplete scans

The queue guard targets 30-minute commitment age. Grafana's
`omi-batch-unit-unpublished-2h` rule is the single human lateness page. It fires
when either a fresh queue sample contains an all-epoch compute commitment older
than two hours or a fresh timeliness sample measures a new-cohort delivery breach,
for five minutes. Each source has its own freshness gate, so a stale source cannot
silence positively measured late work from the other. There is no second queue
lateness UID to duplicate the same incident.
Import the committed Grafana rules
through the monitoring runbook; a merged JSON file is not a live alert.

`oldest()` and `oldest_retry()` skip deliberate policy holds and rows in
`dead`, `quarantined`, `committed`, or `privacy_blocked`. These rows retain their custody
and recovery obligations. A completed terminal-disposition marker does **not**
exempt `result_ready`: its ordered commit is still owed. Unknown states remain
measured. The broader timeliness alarm separately covers quarantine, assignment
holds and projection; this queue proxy does not prove delivery to the user.
That delivery rule is promoted into the existing Grafana import gate with a human
page tier; its diagnostic companions remain agent tier. Historical `dead` rows
are outside those timeliness legs: exclusion from the compute proxy is not a
claim that their retained recovery debt has an age alarm. The rollout lead must
census and track any such debt separately through the legacy recovery path.
The lead must dispatch
the production import and verify live definitions after deploying this fix.

A bounded scan reads at most 501 documents. If the first 500 are all exempt and
a sentinel remains, it exports NaN, meaning unknown age. It must neither invent
late work from a hold's enqueue time nor publish a healthy zero. Prometheus
`max` can ignore NaNs beside finite priorities, so the guard separately counts
`age != age` for both oldest and retry clocks and reports BLIND. A fresh finite
over-30-minute observation in another priority still reports TRIP, with
`metrics_blind=true`; incomplete coverage never erases positively measured late work.
The page-tier
`omi-batch-queue-safety-blind` rule alerts after five minutes of scan blindness
or absent observations, or after queue freshness is stale for fifteen minutes
plus five minutes pending. Capacity and timeliness sampling continue independently.

## Triage without weakening custody

Use `ro-prod` and metadata aggregates. Count states and bounded reason codes;
never read user content, print owners, or delete source audio. Read the guard's
`batch_safety` log and compare age, `age_incomplete`, `retry_incomplete`, and freshness. An allowance
hold is an admission decision, not poisoned audio. Let its normal authorized
re-evaluation proceed; never waive allowance or redrive it to silence a metric.

For actual failures, use the existing fenced paths:

- Worker failure: `Scheduler.fail` / `quarantine_job` retains encrypted audio,
  removes the queue commitment and opens held recovery. Never patch state by
  hand or reset a paid intent.
- Failed-held speech: `scripts/batch_pipeline_speech_redrive.py` requires an
  owner/time/unit cohort, fresh census digest, paid-epoch authorization and
  bounded apply. Provider/abandoned-running outcomes are not proof of silence.
- Proven silent failed-held: `scripts/batch_pipeline_held_disposition.py` uses
  strict VAD and the silence contract. Positive or unknown speech is refused.
- Exhausted validated empty: `scripts/batch_pipeline_terminal_empty.py` requires
  the exhaustion evidence, lineage/privacy checks and approved plan digest;
  language-guarded units require independent recognizer evidence.
- Committed projection debt: `scripts/batch_pipeline_projection_repair.py`
  replans and applies one owner's fenced projection. A `result_ready` queue
  row must first pass normal ordered merge; projection repair is not a shortcut.
- Privacy-blocked: retain the privacy fence. No audio recovery is authorized
  across it.
- Historical dead records: the authenticated `/redrive-dead` handler uses
  `Scheduler.redrive_dead` and its privacy transaction. It does not waive custody
  or authorize a new paid recovery epoch.

Production disposition is an operator decision, separate from this signal fix.
The lead owns worker/guard deployment and Grafana import. Verify the worker's
serving image identity, then a new bounded age/BLIND reading, and read back the
live alert UID, page tier, receiver and absence of the agent mute interval.
Do not test notification delivery by notifying users.

Rollback: restore the prior worker image and guard chart and restore the Grafana
rule backup through the documented importer. Preserve the approved worker HPA
min 4 / max 8 and baseline 4 (2026-11-06, David D4 / bc18db). Restore baseline/min
6 and max 12 if GPU queue depth or ready_units climbs back past 50k.
Disposition/redrive cannot be undone by
resetting a paid token; stop further apply, preserve durable receipts, and
replan after an uncertain result.

## Fleet queue sample ownership

`FIRESTORE_READ_LEVERS` includes `batch_metrics_oldest_leader` (default 100).
Serving instances elect one queue sampler per store namespace using the existing
`LeaderLease` implementation and a `queue_metrics` role (20-second TTL), separate
from maintenance ownership. Followers query neither `oldest`, `oldest_retry` nor
`ready_for_capacity`, and export no queue age/count/freshness samples. Lease errors
retain the existing advisory fail-open behavior. At default settings, the serving
30-second reservation plus 20-second ticks produces a sample every 40 seconds;
a lost holder hands over within 60 seconds, excluding IO/runtime delays. A metrics
scrape can refresh earlier. Longer configured tick/reservation values can exceed
that target; keep their combined effective cadence within 60 seconds.

GPU workers retain per-pod sampling because the adapter gates each pod's
GPU busy-time metric on sampler freshness. Electing a single worker would remove
other healthy pods from that signal. Only process index 0 samples; its independent
15-second loop now runs fleet queue queries every 60 seconds, including capacity
counts. Timeliness, projection, lifecycle and local event gauges keep their prior
schedules. Queue ages/counts stop exporting after 60 seconds without a successful
sample, even when the refresh task stops; capacity retains its independent success
clock. Failed and never-observed samples cannot become fresh zeroes. The adapter's
existing `< 60` freshness filter still rejects cached stale scrapes; a delayed
GPU query can briefly make its queue demand signal unavailable, retaining capacity.
GPU busy-time instead uses the independent per-instance sampler heartbeat, still
updated by the 15-second loop (plus IO); the adapter accepts the old queue clock
as well for mixed-version fleets and rollback. Both clocks retain a 60s bound.

The queue-age and over-SLA Grafana rules (`alerts/batch-timeliness.json`,
`alerts/batch-queue-safety.json`) use `max`/any-instance semantics, as do the
ready-age/capacity adapter rules. No average or pinned-instance consumer was
found in the repository. The 2h timeliness sampler is unchanged. Its observed-at
staleness rules remain independent of this queue sampler.

Rollback: set `"batch_metrics_oldest_leader": 0` in the existing
`FIRESTORE_READ_LEVERS` JSON map, preserving other entries. This bypasses election,
GPU throttling and export expiry, restoring the prior per-instance behavior and
existing adapter freshness checks. There is no new environment variable.

## 2026-11-08 production import preparation

`omi-batch-queue-safety-blind` uses a 900s staleness budget, then 5m pending.
The aggregate dry-run at 2026-11-08T14:05–14:59Z measured the worker-plane sample
cadence at approximately 514s; the prior 120s arm was a false positive. This
alert-only budget does not alter producer cadence or adapter freshness. Other
query arms remain unchanged. Read back the 900s expression after import.

`omi-batch-unit-unpublished-2h` lands paused for the known backlog. Its threshold
and source freshness gates are unchanged. Unpause only after #24731/#24893
drain work ships and both fresh sources stay below 7200s for 24h with no blind
scan, via a separate owner-approved change. Missing/stale samples cannot prove
recovery. Full import disposition and the five paused UIDs are in
[the pipeline alert runbook](../../charts/monitoring/batch-projection/pipeline-alerts.md#production-import-disposition-lead2-ruling-699300-2026-11-08t1513z).
