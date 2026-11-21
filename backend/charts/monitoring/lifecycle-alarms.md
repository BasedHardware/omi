# Lifecycle alarms

WP-C evidence date: 2026-11-04. Owner: two-lane lead. These observations never
change account lifecycle state, schedule work, or replay historical obligations.

New page rules live in `alerts/resilience.json`, already in the metrics-egress
workflow's trigger list. Every new rule, including agent companions and stock
rules, is listed in `live-alert-gate.json`, so the existing gate-based import
includes it. `alert-rules.json` is the combined mirror. No workflow change is
needed. Deploy emitters and reconcile their indexes before importing rules.
The dev/prod Cloud Run exporter allowlists and sync-sidecar keep filter carry
the lifecycle metric families. Their existing ten-minute collection and one-minute
offset, plus the five-minute producer cadence, need a 20-minute freshness
budget for enrichment/BYOK. Direct batch samples keep the 15-minute budget.
Freshness is applied to each observer's value before replicas aggregate, so
each included age or scan flag has its own recent observation timestamp.

| Source | Page cohort and budget | Bounded observation |
| --- | --- | --- |
| Record admission | `record_pending`, `enqueued_at` in last 24h, >2h for 10m | 1000 oldest cohort jobs; stock COUNT capped at 5001 |
| Enrichment | active fresh obligations, `first_pending_at` in last 24h, >1h for 10m | 1000 oldest cohort rows; dormant receipts excluded; backfill stock COUNT capped at 20001 |
| BYOK | `blocked_byok_at` in last 7d, >3d for 1h | 1000 oldest cohort rows; stamp written on initial entry and stranded-job reclaim |
| No job | agent stock only, >0 for 30m | 128 owner/name-indexed conversations and at most 128 job existence reads |

Every source samples at most every five minutes per observer, with ten-second
RPC deadlines and no SDK retry loop. A failed read preserves its previous
values and timestamp. Queries return only aggregate gauges with closed label
sets; identities remain transient in memory. Metrics do not store log text.

The freshness companions treat absent/never-taken samples as blind. The scan
companions flag full pages or capped counts. Count saturation is conservative:
it stays blind even where the oldest cohort row can still prove a breach.
Agent rules use the existing silent receiver policy; page rules reach Telegram.

Record-pending/enrichment page cohorts also require entry at or after
2026-11-04 09:27Z (the lane's evidence cutoff). A rolling 24h window alone
would include the known 8–24h incident stock and page immediately on import.
The fixed cutoff excludes that stock during initial rollout; the rolling
lookback bounds ongoing observations as the fleet ages.

Known legacy stock (record_pending aged 8–72h, BYOK aged 13d, 2000+ dead letters)
does not enter the new dwell pages. The existing dead-letter stock rule is
included in the import gate and remains agent tier. Unstamped historical BYOK
rows remain covered by existing informational age/stock metrics. No backfill.

No-job discovery is a fixed bounded prefix, not a census. Saturation stays
explicitly blind; a healthy prefix cannot prove global absence. No seal-entry
timestamp exists, so no no-job dwell page is claimed (thread-owner ruling
135c64). A separately owned seal-clock follow-up is needed for that page.

Enrichment's backfill stock includes backfill-labeled pending first summaries;
the fresh age gauge also includes those summaries, matching watchdog promotion.
Fresh count is the recent-cohort sampled count, not a fleet-wide total.

## Pair consistency and repair fences

The pair observer rotates through three indexed legs: active finalization jobs,
queued conversation mirrors, and processing conversations. A fleet-wide CAS
lease plus `next_due` admits at most one pass every 300 seconds. Each pass reads
at most 200 source rows, 200 distinct counterparts and two lease/cursor rows
(402 document reads); successful passes write the single private cursor twice.
Transactions have one attempt and RPCs have ten-second deadlines. No account
rows are mutated. A failed read or lost owner never advances the cursor or
freshness timestamp. The scan state contains the keyset cursor needed to resume;
it is never exported in labels or logs.

Every admitted page rotates to the next domain, even when that page is full.
Three separate keyset cursors preserve progress. A large jobs backlog therefore
cannot prevent the queued and processing domains from being sampled on each
three-pass rotation.

At 288 passes/day, the ceiling is 115,776 document reads plus 576 cursor writes
per day, plus up to 288 denied lease reads/day per calling observer. This is a
bound, not measured spend. Reconcile the additional conversation group field
index and summary-repair composite before the emitter train.

`omi_finalization_pair_mismatch{leg,kind}` counts each indexed leg's last bounded page's all-age
mismatches. `omi_finalization_pair_new_mismatch{leg,kind}` restricts those mismatches
to jobs with `created_at` within 24 hours and at/after 2026-11-04 09:27Z. The
recent gauge pages at >25 for 30m; stock is agent tier. Each leg retains its own
page and clock while other legs run. The 35-minute freshness budget covers the
nominal 15-minute rotation plus the 10-minute bridge and one-minute offset.
Across replicas, page, stock and blind values use only the newest successful
observation of each leg. `topk by(leg)` selects the observer clock while keeping
its labels, so the matching value comes from that same observer. A newer clear
therefore supersedes an older bad snapshot; a different leg's clear cannot
erase the retained jobs observation. Merely taking the maximum of every
still-fresh replica would allow one old bad sample to satisfy the pending timer
after a later leader had already observed recovery.
Stale checks the freshest observer of each leg, so a busy jobs leg cannot hide
starvation of the queued/processing legs. The four closed kinds are
terminal-job/queued-mirror, terminal-job/processing-mirror, live-job/missing-
conversation and linked-but-missing-job. Deleted, discarded, merged and deferred
mirrors and superseded generations are excluded.

This is a bounded page, not an exact global mismatch count. A full page, malformed
row or mismatch lacking a job entry clock sets the incomplete flag. Missing jobs
have no job creation clock and cannot qualify for the new-cohort page. Terminal
history with settled mirrors and bare processing rows without job links are
outside coverage. Sparse drift across pages can remain below the page threshold;
the observer does not promise detection of every individual mismatch. The
stale/blind companions remain agent tier. Missing-clock/coverage follow-up owner:
uicleanup, evidence date 2026-11-04.

Only `users/{uid}/conversations/{cid}` mirrors are inspected. Other collection-
group paths, such as nested archives, mark the sample blind and are skipped.
The keyset cursor still accepts those valid document paths so a full excluded
page cannot strand the scan at the same cursor forever.

`omi_enrichment_summary_repair_count{lane="all"}` is a capped count of active
outbox obligations with `summary_repair=true` and numeric `due_at>=0`. COUNT101
can prove >100 but cannot report total stock. Settled receipts have no numeric
due date. This metric is repair-fence stock, not attempt count or a retry cap.
There is no numeric retry cap in the current source; uicleanup owns that policy
debt (ruling 4256d5). Its stock and stale rules are agent tier.

The offline semantic regression at
`tests/unit/test_lifecycle_pair_alert_semantics.py` evaluates the committed
queries with Prometheus `promtool test rules`, including the pending timer.
Provide `PROMTOOL_BIN` outside the test and run it through the canonical selected
`backend/test.sh` harness. It performs no download, network request or server
startup. The engine check explicitly skips when no tool is provided; the
always-on rule contract still pins the reviewed expressions. Local release
validation includes the real engine check. Cases cover a newer clear, ongoing
drift across leader changes, independent legs, stale observations and absent
observers.

## Day-1 import disposition, 2026-11-08

Lead2 ruling 699300 (15:13Z) keeps thresholds intact while suppressing known
backlog pages at import. `omi-record-pending-dwell` lands paused until #24893
drain work ships and fresh, untruncated cohort age remains below 7200s for 24h.
`omi-enrichment-fresh-dwell` lands paused until its #24893 drain ships and fresh,
untruncated fresh-cohort age remains below 3600s for 24h. Missing or stale samples
do not count as healthy. Each needs a separate lifecycle-owner-approved unpause.
The full five-rule pause list and criteria are in
[the pipeline alert runbook](batch-projection/pipeline-alerts.md#production-import-disposition-lead2-ruling-699300-2026-11-08t1513z).

`omi-finalization-byok-dwell-page` remains active with the same UID, strict
259200s/1h threshold and freshness gate. It now routes as an agent-tier warning
with audience agent and `omi-tier-silent`, so known BYOK debt does not page on
import. The blocked-state triage owner still tracks the debt; the threshold
does not authorize lifecycle changes. Read back pause flags and BYOK mute/tier
after the separately authorized prod provisioning dispatch.

The reviewed lifecycle source inventory records BYOK's agent tier. Eleven table
rows that borrow the paused record/unpublished/held pages are explicit strict
known gaps under ruling699300, not claimed active coverage. The invariant still
rejects every paused dwell rule; unpause produces a strict XPASS until the owner
removes that row's debt record. All runtime states, exits and deadlines are
unchanged. Unreviewed pauses still fail normally.
