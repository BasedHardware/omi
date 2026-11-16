# Transactional fresh gate (SCA-2015 PR 1)

The old fresh-first pick used an outside-transaction page of 32 pending rows. It could miss a ready row behind that page or pass an earlier row that settled or was redriven after the probe.

Fresh-first selection now reads the earliest pending fresh row and earliest ready pending fresh row inside the commit transaction with two LIMIT 1 queries, without a terminal-state exclusion. The ready row commits when it is first or its own ready age reaches the head wait. If a later selected ready row has no ready or provider settle time, the gate leaves the decision to the existing outside probe, which can measure another ready row on its page. The existing commit body preserves late marking, predecessor chain, privacy fence and commit metrics.

Cost: gate attempts add up to two transactional queries on the fresh path. When the gate decides, they replace the outside-transaction 32-row probe and its per-skipped-row rechecks; an undetermined gate or missing index still uses that probe. A row that becomes ready after the transaction's snapshot can commit on a later drain when it is first, has a ready time (including the provider settle fallback) old enough to pass the head wait, or is picked by the outside probe. It is marked as a late capture if behind the watermark.

This change does not release held provider backlog, change discovery or projection, or deploy indexes. The existing merge_fresh index serves F1; merge_fresh_ready adds state equality for FR, retaining capture_at and segment_id ordering. Matching Postgres partial indexes are additive.

FailedPrecondition on either query logs fresh_tx_gate_unavailable, records a fallback, and restores the old probe for 300 seconds. Set BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED=false to restore the old probe path.

Review round 1: distinguish an undetermined gate from a decided empty result; handle transient gate query errors with fresh_tx_gate_retry and no backoff, preserving commit-write error propagation. Deterministic settle/redrive interleavings and transaction identity spies cover selection and result writes; the scheduler transaction wrapper delegates both new queries. The Postgres migration is numbered 0006.

Review round 2: with the head wait off the gate does not let a ready fresh row pass an unready earlier fresh row; an `Aborted` raised by a gate query is re-raised to the transaction retry (or to the caller when contention retries are off) rather than handled as a gate retry.

fresh_probe_full_no_ready is not emitted on the decided gate path; a falling or zero count alone is therefore not proof of progress. Production proof requires ready fresh rows committing behind more than 32 unready rows, the shape covered locally by test_ready_fresh_beyond_probe_page_obeys_its_own_wait; production has not been checked.
