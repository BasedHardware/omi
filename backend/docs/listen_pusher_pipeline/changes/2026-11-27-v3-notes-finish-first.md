# v3 notes drain: manual Finishes first

Contract: [`CONVERSATIONS_V3_NOTES_FINISH_FIRST`](../../listen_pusher_pipeline.mdx).

## Why

The goal (David, 2026-11-27) is Finish to Home under 60 s at p90. After a builder pass commits, the same
request writes notes for every due `v3_process_pending` row of the owner. It does them one at a time,
and each row takes a summary call (p50 15–24 s) plus folders, apps and memories. The rows came in
document-id order, which is effectively random. So a Finish the owner is waiting on could sit behind
unrelated rows: another window of the same stretch, or an owner backlog. The backlog case shows up as
reconcile requests running to the 600 s dispatch deadline, 53 of 3,000 sampled on 2026-11-27.

## What changed

The drain puts Finishes first. A media or background window the owner finished that shows on Home
leads, because it settles without a model call; manual-intent rows follow. Each group is newest first.
Other rows keep their order after them.

Not changed here: `pending_processing` still takes the first 128 due rows in document-id order before
this reorder, so in an owner backlog deeper than that a Finish with a high document id may not be in
the page, and waits for a later drain. Querying Finishes first is a follow-up.

## Cost

None. The rows, reads, writes, leases and model calls are the same; only the order changes.

## Rollback

Set `CONVERSATIONS_V3_NOTES_FINISH_FIRST=off` on backend-sync.

## Readback

- `omi_conversations_v3_notes_finish_first_total` counts each Finish moved ahead of at least one other
  pending row.
- The Finish-to-Home SLI (SCA-4489) should show fewer Finishes whose summary trails their outline by
  more than one summary call.
