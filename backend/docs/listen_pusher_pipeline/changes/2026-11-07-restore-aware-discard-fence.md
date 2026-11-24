# Restore-aware discard fence for batch recording obligations

Finalization skips `register_recording` when processing persists a relevance
discard, avoiding registration retry churn for intentionally discarded live
captures. It combines the processed discard result with the original recording
and archive metadata, so a revival still registers its required `record_pending`
audio obligation before fanout.

The [durable fanout ownership fence](../../listen_pusher_pipeline.mdx) checks
`expected_discarded` inside the claim transaction. If a concurrent user restore
revives the current completed generation, the claim returns `lease_conflict`
without admitting fanout or terminalizing the job. Retry reloads the restored row
and registers its obligation. Missing, still-discarded, and superseded generations
retain the terminal stale outcome and exactly-once projection bookkeeping.

This fix is on without a new flag. It preserves the existing recording-owner and
proven-empty-archive rules. Unit regressions cover processing discard/revival,
registration refusal, silent backfill, and terminal fencing. The listen lifecycle
Firestore emulator harness holds a real restore transaction ahead of a concurrent
fanout claim, then verifies refusal and durable recording registration before a
successful retry. These are local lifecycle guarantees, not deployment evidence.
