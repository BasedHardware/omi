# 2026-11-18: end-of-recording proof wakes the waiting summary early

## What changed

- The end-of-recording proof from [2026-11-14](2026-11-14-capture-end-proof.md) is now also asked as soon as it
  can change: when `POST /v2/sync-capture-end` stores a marker with `pending_wals == 0`, and after a sync
  projection that extends an obligation that is still waiting.
- When it holds, `FirestoreEnrichmentOutbox.expedite` makes the obligation due now under a fresh wake. `version`
  is unchanged, so no extra processing pass is owed. Leased, dormant and already-due rows are left alone.
- Hold admission still re-checks the proof before the run. Contract: the end-of-recording proof section of
  [the pipeline doc](../../listen_pusher_pipeline.mdx).

## Why

Before, the proof was read only when the wake fired, and that wake was the 600 s
`SYNC_REPROCESS_SETTLE_SECONDS` after the last arrival, so it never shortened anything. Example: a 30-minute
offline meeting gets its full summary about 5 minutes after it syncs instead of about 15.

## Reads and writes

Per check: one conversation read limited to `finished_at`, `external_data` and `sync_processing_hold`, plus the
existing session-document read when the row carries a recording session id. One outbox transaction and one task
create only when the proof holds. Each check also counts in `omi_sync_capture_end_proof_total{result}`.

## Kill switch and rollback

`SYNC_UPLOAD_WATERMARK_ENABLED=false` stops the early check along with the rest of the proof. Rows already
expedited simply run; nothing to clean up.
