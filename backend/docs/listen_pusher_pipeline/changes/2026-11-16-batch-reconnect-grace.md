# Mobile batch reconnect grace

A phone/listen transport close no longer immediately finalizes an eligible mobile
server-batch conversation. The producer drains its immutable original packs, then
persists a fixed reconnect deadline while the conversation stays `in_progress`.
A same-origin, same-device, same-source reconnect before that deadline claims the
same conversation. It starts a new archive capture session without reopening a
terminal batch obligation. Concurrent sockets get retryable 1013 while a live
producer owns the row; tokens fence stale disconnects and audio metadata writes.

`LISTEN_BATCH_RECONNECT_ENABLED` defaults true. It changes transport boundaries,
not semantic boundaries; default-on prevents avoidable new fragmentation. Set
false to restore immediate teardown finalization on the next socket teardown.
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

Release rollout order is required: upgrade finalization/reconciler/backend readers
(including terminating/traffic-reachable revisions) first, then roll listen through
Release's train and drain old listen sockets. Pusher uses the existing producer
upload/close protocol and needs no wire change. Old workers ignore the shortened
deadline and can wait for the old quiet timeout; old listen can finalize on close,
so mixed listen versions can still split a chapter. Do not claim continuity or the
120-second processing-admission bound until old workers and listen sockets have
drained. New code always refuses a sealed/terminal row. Rollback uses the kill
switch with the upgraded finalization workers retained until existing holds drain.

This is prevention for future transient interruptions. A reconnect after expiry
or after a terminal batch obligation starts a separate conversation. Immutable
successor members and composed chapter reads (A2) remain with the Home redesign
and sync/projection owners. Historical fragments are not consolidated. Duration
presentation of absorbed pre-origin sync content (A3) also remains separate; no
`app/lib` changes are included. No production deployment or flag change is part
of this PR.

Contract: [disconnect recovery](../../listen_pusher_pipeline.mdx#mobile-server-batch-reconnect-grace).
