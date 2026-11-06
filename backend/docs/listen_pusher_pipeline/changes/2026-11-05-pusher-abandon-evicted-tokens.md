# Capacity-evicted recording producers attest stoppage

lead2 rulings `88ba4d` and fast follow-up `8fea2c`: pusher train only. See the
[closed-drain contract](../../listen_pusher_pipeline.mdx#8-websocket-task-supervision).

A cancelled closed worker previously left a live-process producer token pending
until pod death. An admitted capacity eviction now forgets its recovery hint, waits for the
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

Ship off-peak through the standard pusher drain/train: one canary pod at 64
for 15 minutes. Expand only with socket kills <=15/15min and memory p99 below
75% of 3.5 GiB. Also review `record_closed_finish outcome=capacity`,
`outcome=abandoned`, `outcome=abandon_overflow`, and seal repair's `upload_pending`.
Roll back with cap 32 and abandonment `off`. This change performs no deployment
or production data access; the canary gates remain unmeasured here.

Regression coverage exercises real pusher WebSocket cleanup with held upload
and projection threads, raw receipt readback, registration-response cancellation,
deadline-expired metadata, idempotent exact-token transactions, reconnects,
admission retry, the kill switch and missing-tail seal refusal.

Overflow owners remain independently bounded by
`PUSHER_MAX_ABANDON_RECORD_DRAINS` (default/prod 4, clamp 0..16). Full admission
starts no coordinator and logs `abandon_overflow`; the durable token stays fenced
for process/pod-death repair. Refusal removes its local recovery hint so a later
successful producer cannot clear it while its storage future is still running.

The #24689 dedicated recording pool and its saturation/refusal behavior are
removed in #24689b per `8fea2c`. Durable recording calls again use the shared
`storage_executor` (128 workers) and the original separate PCM-read, upload and
projection-refresh calls. The completion tracker remains: queued and running
shared-storage futures must settle before abandonment, even after caller
cancellation. No new pool is sized here. The count caps do not bound retained PCM
or pod RSS; production memory and socket-kill acceptance require the canary.
The lifecycle table keeps refused overflow in capturing, with the old exit;
abandoned dwell/deadline/alert gaps remain strict expected failures.
