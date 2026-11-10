# Record-seal repair: deadline priority, then newest first

This supersedes the ordering in [the November 9 change](2026-11-09-record-seal-age-order.md)
for Plan v3 L2 (David's newest-first / near-dead-letter-first ruling, reference
`6db8f2`). The urgency window is the final 24 hours before the **stored**
`record_dead_letter_deadline_at`; enqueue age never fabricates a deadline.
Pending jobs already past that deadline are included, while terminal jobs are
excluded by the existing state filter.

The jobs half of the existing first worker group checks urgent pending jobs in
deadline/name ascending order, then fills remaining places with enqueue/name
descending order. Conversation discovery uses finish/name descending order.
Urgent jobs precede ordinary jobs and conversations, with duplicates removed.
The existing half-worker reservation for conversation discovery remains. This
does not increase the production worker count (16), row/run budgets, candidate
cap (1,024), or aggregate scan cap (10,000). The extra urgent page consumes up to
128 of that existing scan cap, rather than adding to it. All seal, privacy,
producer-proof and minimum-age eligibility checks remain unchanged.

Recency scans retain a frozen horizon and wrap so sustained new inflow cannot
strand the tail. The deadline scan can expand its upper boundary on resume:
newly urgent jobs have later deadlines and cannot prevent progress through the
earlier ones. All three encrypted frontiers checkpoint before proofs and after
actual attempts; preview writes none. New recency frontier names end in `v2`
so an old ascending cursor cannot skip newer work after the ordering change.
The old frontier documents remain available to an older binary on rollback.

The batch index registry and generated manifest add newest-job and deadline-job
indexes for both stages, plus a newest-completed conversation-group index.
The existing deployment readiness gate must confirm these indexes before
shipping the new image. No index apply or production deployment was performed.
Ordinary recency discovery retains its missing-index fallback to hash order;
the urgent scan fails if its index is unavailable, rather than silently
discarding deadline priority.

Rollback the jobs priority with `RECORD_SEAL_REPAIR_AGE_ORDER=off`: this skips the
urgent scan and restores the original hash query. Code rollback restores the
previous conversation ordering and its untouched frontier. Neither rollback
changes custody or deletes recordings. The CPU, placement and bytecode changes
are independently reversible through the chart values or a code revert.
