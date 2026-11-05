# Projection discovery and productive drain turns

Serving-side assignment discovery groups each page by the durable job binding's
owner before attempting projection. With owner drains enabled, only the first
page row for each owner is attempted; collapsed rows count as waiting and wake
that owner's drain once. Job hints still cost one read per row, but non-head rows
avoid full projection reads and predecessor checks. A page may begin beyond the
true chain head; the existing predecessor replay resumes from the watermark.

Follow-up discovery also offers one receipt per owner per page. A bounded
per-owner rotation offers siblings on later passes so a ready receipt cannot
pin the siblings it needs to complete. Targeted and owed recovery wakes retain
their existing behavior. No authorization, predecessor, privacy, receipt or owner
claim fence changes; see [the pipeline contract](../../listen_pusher_pipeline.mdx).

A productive turn ending at its deadline gets up to two consecutive queue-head
requeues, then yields to the tail. Zero-advance turns keep FIFO behavior. This is
on by default with no new flag. Revert this change to roll back; pending rows
remain durable. The existing owner-drain switch restores sweep walks.

`omi_batch_projection_page_collapsed_rows_total{source="sweep|followup"}` and
`omi_batch_projection_drain_head_requeues_total` expose the scheduling changes
and are retained by the serving GMP profile. Unit tests cover read/attempt counts,
follow-up rotation, bounded fairness, predecessor fencing and exclusive claims;
this lane does not perform a production throughput measurement.
