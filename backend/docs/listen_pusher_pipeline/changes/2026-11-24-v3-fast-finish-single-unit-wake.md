# A written single-unit fast finish sends its own manual-end wake

SCA-3024 / SCA-4084, follow-up to [the batch manual end](./2026-11-24-v3-batch-manual-end.md).

Admission stores the cut for a single-unit recording before the fast pass starts,
so the pass was given no cut callback. It relied on the transcript writer's
ordinary wake, which `triggers.enqueue()` names by owner and minute.
`enqueue_named_task()` skips that name when the owner's ordinary reconcile already
ran in the same minute. The pass reported `written`, but Home could still wait
for canonical delivery, another change, or the ten-minute pending sweep.

## The change

For a single unit that admission promoted, the pass now gets the same cut
callback as a multi-unit recording. After a written transcript it calls
`changed(uid, cid, manual_end=True)`. That call runs one `mark_pending`
transaction (setting `v3_manual_end` again, which is idempotent) and one Cloud
Tasks enqueue under the distinct `manual_end_id` task name. A single unit that
admission did not promote gets no manual-end wake, so the marker is never set
past `promote_manual_end`'s guards. Multi-unit recordings are unchanged.

Cost: at most one transaction and one enqueue per written single-unit fast
finish, for members of the `v3-fast-finish` cohort only.

Rollout and rollback: no new flag. `CONVERSATIONS_V3_FAST_FINISH=off` stops the
pass, and `CONVERSATIONS_V3_BATCH_MANUAL_END=off` stops the marker. Otherwise
revert the PR.

Verification: `tests/unit/test_conversations_v3_fast_finish.py` covers one wake
after a written single-unit pass, none after a provider error or funding
refusal, and none for an unpromoted single unit. Readback joins the SCA-4084
owner-account reading (seconds from the finish request to `tile_state=done`).
