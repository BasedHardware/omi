# Capacity-evicted recording producers attest stoppage

lead2 ruling `88ba4d`: one PR, pusher train only. See the
[closed-drain contract](../../listen_pusher_pipeline.mdx#8-websocket-task-supervision).

A cancelled closed worker previously left a live-process producer token pending
until pod death. Capacity eviction now forgets its recovery hint, waits for the
worker and actual storage/barrier futures (including deadline-expired metadata),
and marks each exact remaining owned token `abandoned_at`. Inherited pending clears from another socket stay fenced until their own producer settles; a different socket cannot attest their stoppage. This never certifies a
projected tail. Seal repair retains its archive-required listing, finish/tail
validation and privacy transaction gate. A new reconnect token remains live;
normal clears cannot remove an abandoned token from a stale recovery snapshot.

`PUSHER_ABANDON_EVICTED_TOKENS` is on unless set to `off`. Metadata admission
refusal and write failures retry with bounded exponential jitter while the
process lives. Death mid-abandon falls back to the existing dead-pod proof.
`PUSHER_MAX_CLOSED_RECORD_DRAINS` defaults to 32, clamps to 8..128, and logs the
chosen value once. Prod Helm values and the runtime env manifest set 64. The
production memory limit stays 3.5 GiB; a count cap is not a byte budget or a
production p99 guarantee. Do not raise production to 128 without a PCM budget.

Ship off-peak through the standard pusher drain/train: one canary pod at 64,
then expand only after reviewing per-pod memory p99 against the limit,
`record_closed_finish outcome=capacity`, `outcome=abandoned`, and seal repair's
`upload_pending`. Roll back with cap 32 and abandonment `off`. This PR performs
no deployment or production data access.

Regression coverage exercises real pusher WebSocket cleanup with held upload
and projection threads, raw receipt readback, registration-response cancellation,
deadline-expired metadata, idempotent exact-token transactions, reconnects,
admission retry, the kill switch and missing-tail seal refusal.
