SCA-1800 repairs replicated coalescing scans under the approved strict-owner
design. Contract: [fleet recovery scan coordination](../../listen_pusher_pipeline.mdx#fleet-recovery-scan-coordination).

Every serving or projection-pump process previously queried groups and updated
`coalesce_quota/global` every 2s. The 2026-11-14 16:37Z Verify receipt reported
35 integration replicas, continuous contention and no eligible uploads.

The existing namespace `leases` store now elects `upload_coalescing_scan` with
a 6s lease, half-TTL renewal and 2s checks. Random startup phase spreads contenders.
Followers only read the lease. Lease failure/lost acknowledgement skips the
scan, even if the advisory maintenance switch is false. A retry adopts its own
durable token after a lost acknowledgement. Cursor/heartbeat and new group
claims recheck the immutable token and live expiry inside their transactions.
Late query results cannot advance a replaced scanner's cursor or heartbeat.
Slow already-claimed work keeps its own 120s group lease and can finish through
the existing privacy and intake fences; discovery leadership never owns audio.

The fair cursor still advances before processing denied/failed pages. Only a
healthy completed pass publishes admission health. No group failure, lease
renewal or follower tick refreshes that heartbeat. A long audio operation can
outlive the discovery lease: the old pass cannot publish health and new holds
bypass once health is older than five seconds. Nominal discovery takeover is
<=8s plus RPC/scheduling delay; group recovery may still wait for its existing
120s lease. These are not hard bounds on outage latency or unit creation.
Deliberate hold stays <=60s and the 600s stale guard is unchanged.

The correction needs no new flag. Existing
`BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED` keeps producer and conversion semantics;
compatible drainers still run OFF. No language/eligibility, receipt, custody,
retention or runtime-flag changes are included.

Fixed empty-scan model, excluding retries and index billing: at 35 replicas,
105 reads/35 writes per 2s becomes 40 reads/<=2 writes. Each follower pays one
lease read. The leader pays one election read, two lease/quota fenced read pairs
and the empty-query minimum. Renewal need not write each tick. Nonempty/wrap
pages add two reads/<=one write for cursor advance plus <=8 query rows and
unchanged group/privacy/unit/receipt IO. Modeled daily reads are
4,536,000 -> 1,728,000 and writes 1,512,000 -> <=86,400. These are estimates,
not production savings. Producer-only sync/backfill and workers that do not
start the serving/pump loop pay no election or discovery IO.

Release owner must map every serving/pump process across services and retire
all old scanners, including zero-traffic revisions with background CPU, before
claiming repair. Old binaries ignore the lease; overlap is compatible with
group custody but remains operationally unqualified. Preserve service flag maps.
Rollback is OFF across all producers/drainers, individual conversion of holds,
and receipt/source reconciliation before removing compatible support. A merged
intake already committed remains the immutable receipt target. Never delete
holds or restore the unleased scanning binary as an operational repair.

Metrics: `omi_batch_leader_lease_total{role="upload_coalescing_scan",outcome=...}`
counts logical `attempt`, actual transaction-body `transaction_attempt`,
`leader`, `follower` and `error`. `omi_batch_upload_coalescing_scan_total` counts
`query_completed`, `cursor_advanced`, `success`, `group_retry`, `ownership_lost`
and `failed`. Scan duration includes group IO; scan-last-success is a
process-local timestamp. Aggregate counters across the exact fleet and use the
maximum last-success timestamp, not a follower's absent/zero gauge. Existing
coalescing events add `claimed`; accepted observations are not distinct sources.

The required production readback is one stable, exact-image/flag-bound 15-minute
window at 35 replicas: zero quota/lease exhausted-contention failures, >=400
healthy empty passes, <=5s maximum heartbeat gap, one valid scan writer and
no follower quota writes/queries. Report actual lease attempts/retries, scan
counts/durations, fixed reads/writes and index charges, and startup/handover
separately. Illustrative fleet-scoped queries (add deployment/namespace selectors):

```promql
sum(increase(omi_batch_upload_coalescing_scan_total{outcome="success"}[15m]))
sum(increase(omi_batch_leader_lease_total{role="upload_coalescing_scan",outcome="error"}[15m]))
sum(increase(omi_batch_leader_lease_total{role="upload_coalescing_scan",outcome="transaction_attempt"}[15m]))
max(omi_batch_upload_coalescing_scan_last_success_seconds)
```

Derive the maximum heartbeat gap from the recorded timestamp time series and
scrape interval; one fresh timestamp cannot prove the window. Combine metrics
with contention logs (`event=batch_store_contention`, read/write table labels),
aggregate operation evidence and settled billing; no metric alone proves that
every old instance is retired. Worker source/config presence is a bounded
compatibility check only, never evidence of worker runtime flags or production
qualification. Unknown flags remain unknown until release-owner readback.

The production cohort is explicitly empty/UNKNOWN at the cited readback:
zero observed accepted sources/drained groups, multilingual intake excluded.
An empty healthy queue can pass scan health only. Original quality/freshness,
nonempty mixed-fleet rollback, matched-original-audio savings and settled stable
billing gates remain outstanding. No eligibility widening or paid inference.
Book $0 until the original Done check passes through release/Verify.
