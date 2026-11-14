# Transactional fresh gate (SCA-2015 PR 1)

The old fresh-first pick used an outside-transaction page of 32 pending rows. It could miss a ready row behind that page or pass an earlier row that settled or was redriven after the probe.

Fresh-first selection now reads the earliest pending fresh row and earliest ready pending fresh row inside the commit transaction with two LIMIT 1 queries, without a terminal-state exclusion. The ready row commits when it is first or its own ready age reaches the head wait. The existing commit body preserves late marking, predecessor chain, privacy fence and commit metrics.

Cost: two extra transactional queries per commit attempt on the fresh path replace the outside-transaction 32-row probe and its per-skipped-row rechecks. A row that becomes ready after the transaction's snapshot commits on a later drain as a late capture when its capture position is behind the watermark.

This change does not release held provider backlog, change discovery or projection, or deploy indexes. The existing merge_fresh index serves F1; merge_fresh_ready adds state equality for FR, retaining capture_at and segment_id ordering. Matching Postgres partial indexes are additive.

FailedPrecondition on either query logs fresh_tx_gate_unavailable, records a fallback, and restores the old probe for 300 seconds. Set BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED=false to restore the old probe path.
