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

The ordinary-job starvation bound is **unbounded while urgency fills every
job allocation**: if each run selects `max(1, workers // 2)` urgent rows, the
ordinary recency leg gets zero places until a run has spare urgent capacity.
Conversation discovery retains its reservation. No finite wall-clock guarantee
is claimed for ordinary work under a sustained urgent backlog; reserving an
ordinary share is a follow-up fairness decision (production-safety P2-1).
Malformed deadlines are skipped before advancing the urgent frontier, including
at a saturated page's tail; an all-malformed page wraps instead of persisting
an unreadable cursor. Such a page can delay urgent progress until the corrupt
metadata is repaired, within the existing per-run scan/time bounds.

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
an unavailable urgent index skips only the urgent leg, emits a content-free
`index_unavailable` event and shared degraded fallback telemetry, and allows
ordinary and conversation discovery to continue with a successful run. The
`gcp_diarizer.yml` batch-pipeline-worker path now enforces the shared readiness
gate against the selected source SHA before building or deploying the image.

Rollback the jobs priority with `RECORD_SEAL_REPAIR_AGE_ORDER=off`: this skips the
urgent scan and restores the original hash query. Code rollback restores the
previous conversation ordering and its untouched frontier. Neither rollback
changes custody or deletes recordings. The CPU, placement and bytecode changes
are independently reversible through the chart values or a code revert.
