# Shared serving custody and all-runtime rollback

Direct conversation processing and queued speaker-only retries now use the same
durable, content-free obligation. Pending direct replays use its bounded claim
budget; live claims and closed receipts suppress automatic re-resolution while
still applying fresh manual overrides. Direct success settles after canonical
persistence. Failed persistence defers speaker-only work, never full enrichment.
Existing atomic receipt/counter settlement prevents duplicate terminal outcomes.

The processing boundary injects this custody runner into shared reconstruction.
The outbox remains outside the GPU batch-pipeline worker closure. Pusher's locked
finalizer path reaches it through `process_conversation`.

Production Cloud Run backend/sync/sync-backfill/integration bind the existing kill
switch explicitly. GKE backend-listen/Pusher and the dedicated sync worker use the
shared ConfigMap. Admission checks an independent six-host roster and rejects
overrides that defeat the ConfigMap; the worker's rendered chart is tested too.
The existing switch defaults remain unchanged; no cohort or new flag is added.

The [runbook](../../runbooks/batch-conversation-speakers.md) specifies immediate
100% serving, rollback with `BATCH_FINAL_PASS_ENABLED=false` across all surfaces
and restarts, and the linked T+2h GPU-hours/day readout. Local tests do not prove
deployment, owner-data acceptance, live rollback or measured GPU spend.
