# Contained-donor bridge merge

A sync donor summarized before its live target closed is refused forever by the
`already_processed` fence in `_finish_pending_live_bridge`. The Fable class 8
scoping measured 54 of 204 surviving duplicate pairs (26%, about 4.2k rows a
week) where the donor's recorded span is fully inside the live target's and the
only blocker is that fence.

`SYNC_BRIDGE_CONTAINED_DONOR_MERGE_ENABLED` (default on) lets the bridge absorb
such a donor. Containment is by recorded/segment spans (`conversation_span`),
never by the wall-clock envelope, with a 0.5 s jitter tolerance. Every other
fence is unchanged: user curation, an open target, `choose_live_overlap` (live
provenance plus recorded overlap), privacy and size. Partial overlap keeps the
standalone row.

The assignment transaction re-proves containment on the rows it will merge. If
the donor grew past the target between the bridge read and the transaction, the
whole assignment is refused with `contained_donor_not_contained`; the bridge
treats that as "not yet" and leaves the donor visible. The existing donor
retraction path then discards the donor's standalone notes, copies its audio,
and regenerates notes from the merged transcript.

Risk: the donor's notes are rewritten from the merged transcript. Containment
bounds this to the same minutes and audio is copied rather than deleted, so the
loss is a note rewrite, not data loss. Rollback: set the flag to `false`, which
restores the pre-change refusal exactly. Deployment belongs to the lead's
backend image train and the sync/enrichment hosts after review and merge.

Regression coverage: `tests/unit/test_sync_pending_live_bridge.py` covers a
contained donor merging, partial overlap refused, an open target refused, and
the switch off restoring today's refusal. `tests/unit/test_sync_live_overlap.py`
and `tests/unit/test_sync_cross_job_assignment.py` retain the ordinary
assignment and overlap contracts.
