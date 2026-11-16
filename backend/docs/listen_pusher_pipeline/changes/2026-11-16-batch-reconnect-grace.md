# Mobile batch reconnect grace

A phone/listen transport close no longer immediately finalizes an eligible mobile
server-batch conversation. The producer drains its immutable original packs, then
persists a fixed reconnect deadline while the conversation stays `in_progress`.
A same-origin, same-device, same-source reconnect before that deadline claims the
same conversation. It starts a new archive capture session without reopening a
terminal batch obligation. Concurrent sockets get retryable 1013 while a live
producer owns the row; tokens fence stale disconnects and audio metadata writes.

`LISTEN_BATCH_RECONNECT_ENABLED` defaults **false** and enables only for trimmed,
case-insensitive `true`. This is a temporary default-off rollout flag, reviewed by
2026-11-20, per the Q12-R31 lead decision: old listeners can bypass the producer
fence. An unconfigured deployment preserves origin/main's legacy behavior,
including #25460's full-quiet-timeout mobile recovery for unmarked sessions.
Switch-off refuses all marked-row claims. A reconnect to a drained hold durably
ends it and rearms the existing quiet check due now, without acquiring its token.
Workers with the switch off also treat a drained hold as due immediately and
persist its ended state when sealing it. Without a reconnect/early wake, the
previously indexed wake remains due within 120 seconds plus reconciler latency.
Active producers drain on the new revision and take the immediate end path at
teardown; the switch does not seize a live producer or reopen terminal rows.
`LISTEN_BATCH_RECONNECT_GRACE_SECONDS` defaults 120, clamped to 1..120. Synthetic
coverage models short sockets and 75-second reconnect gaps. 120 seconds covers
that shape with headroom and stays far below the 1,800-second occasion quiet
window. A shorter quiet deadline, explicit user/capture end, scheduled calendar
end, local midnight (stored user zone; UTC fallback), or four-hour span cap wins.

The existing durable quiet-check outbox owns expiry, with the same dispatch and
reconciler fallback. Successful producer drain releases that session's lease;
expiry therefore does not wait an additional five minutes for the legacy lease.
The check seals the logical original archive and requests normal finalization.
Existing job ID, generation, lease, upload barrier, deterministic batch work ID,
privacy, and paid-STT gates remain authoritative. Duplicate wakes cannot create a
second finalization revision. Failed/cancelled drain publishes no grace or close
receipt and acknowledges no new audio; retention/repair keep their existing role.

## Activation gate and ramp (Release owns the train)

1. Keep the flag off. Deploy upgraded finalization/reconciler/backend readers,
   then every listen pod, through Release's train. Verify the running release SHA
   of every traffic-reachable and terminating revision, **zero old listen pods**,
   and **zero sockets still served by old revisions**. Image deployment alone is
   insufficient. Pusher's upload/close wire contract is unchanged.
2. Only after that gate, enable the flag consistently on readers and listen.
   Use a small canary percentage only if the deployment supports routing every
   reconnect in a recording to the enabled pool; otherwise use a fleet activation
   after the gate. This PR adds no percentage selector or deployment automation.
3. Quality reviews chapters per hour per active recording, finalization lag,
   zero drained `in_progress` rows older than grace plus the observed reconciler
   period, and exactly one batch obligation per finalized generation. Compare
   like-for-like active recordings; socket count alone is not chapter reduction.
   Release expands through its train after the clean window. Proposed completion
   and flag review: **2026-11-20**. If the gate/window is unavailable, keep off and
   record the block/review rather than treating dark deployment as delivery.

There is no safe cheap old-reader exclusion field: old resume checks accept
`in_progress` and reject deleted/discarded/locked rows; those fields also govern
privacy, presentation and finalization. Reusing them would strand or hide valid
recordings. Old metadata writers do not check producer tokens. **Residual risk:
routing a marked live row to an old listener defeats producer fencing.** The
activation/drain gate is mandatory; this PR does not make mixed active listener
versions safe. Default-off plus a DB claim guard prevents accidental enrollment
with an unset/invalid flag, but cannot police an old binary or prove fleet state.

## Rollback gate and aggregate readback

1. Set the flag false on all upgraded listen and reader processes. Keep those
   binaries running. Drain existing sockets on those new listeners so active
   marked rows seal and finalize there; held rows cannot resume and use the
   due-now exit above. Do not roll back a live marked owner to old code.
2. Wait **more than 120 seconds plus one observed reconciler period** after the
   final old enabled process/socket drains. The source default period is 60 s
   while quiet finalization is enabled (thus >180 s minimum); verify the actual
   serving period and backlog. Keep quiet finalization and its reconciler enabled.
3. Read back aggregate counts below until zero: all marked `in_progress` rows,
   their held subset, and overdue held rows. Inspect finalization lag and normal
   batch admission to confirm exactly-once obligations. A timer alone is not a
   drain receipt. Any nonzero count, unknown query coverage, protected/failed row,
   unavailable reconciler or backlog blocks rollback and needs investigation.
4. Only after this zero-live-marked-row gate may Release roll back listen. Keep
   upgraded readers until outstanding finalization work drains normally.

Readback query (Release's authorized read-only environment; **not run by this
implementation lane**): project only routing/state timestamps from a collection-
group scan, perform the filters locally, and emit counts only. A complete scan is
required; do not truncate/sample this safety gate. This avoids a new composite
index or reading transcript/audio fields. Scope the client to the customer-data
project using the normal operator bootstrap, never an interactive login.

```python
from datetime import datetime, timedelta, timezone
from database._client import get_firestore_client

now = datetime.now(timezone.utc)
reconciler_period = 60  # replace with Release's observed serving period
counts = dict(marked_in_progress=0, held_in_progress=0, held_overdue=0)
rows = get_firestore_client().collection_group('conversations').select([
    'status', 'listen_batch_producer.version', 'listen_batch_producer.phase',
    'listen_batch_producer.drained', 'listen_batch_producer.deadline_at',
]).stream()
for snapshot in rows:
    row = snapshot.to_dict() or {}
    state = row.get('listen_batch_producer') or {}
    if row.get('status') != 'in_progress' or state.get('version') != 1:
        continue
    counts['marked_in_progress'] += 1
    if state.get('phase') in {'disconnected', 'ended'} and state.get('drained') is True:
        counts['held_in_progress'] += 1
        end = state.get('deadline_at')
        if end is None or end + timedelta(seconds=reconciler_period) < now:
            counts['held_overdue'] += 1
print(counts)  # no IDs, user data, or transcript output
```

The scan is a read-only rollout recipe, not a newly deployed metric. It can be
expensive on a large fleet; Release may substitute an independently verified,
complete aggregate exporter with the same three counts. No such production
exporter or observation is claimed here.

This is prevention for future transient interruptions. A reconnect after expiry
or after a terminal batch obligation starts a separate conversation. Immutable
successor members and composed chapter reads (A2) remain with the Home redesign
and sync/projection owners. Historical fragments are not consolidated. Duration
presentation of absorbed pre-origin sync content (A3) also remains separate; no
`app/lib` changes are included. No production deployment or flag change is part
of this PR.

Contract: [disconnect recovery](../../listen_pusher_pipeline.mdx#mobile-server-batch-reconnect-grace).
