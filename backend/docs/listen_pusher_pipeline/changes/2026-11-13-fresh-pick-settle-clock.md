# Fresh-first pick: settle clock and a probe that reads past one page (2026-11-13)

## What was wrong

When an owner's head is catch-up or held backlog, the merge probes the owner's earliest pending
fresh rows and commits the earliest once it is ready. If that earliest fresh row is not ready, a
later ready fresh row may pass it after the head wait. Two gaps made that wait never end:

1. The wait was measured only from the row's `ready_at`. A provider row that settled while the
   stamp was off, or whose `ready_at` was removed, carries the same instant on
   `provider_intent.settled_at`. The head-wait path already read it (`_ready_since`); the fresh pick
   did not.
2. The probe read 32 rows. A longer run of unready fresh rows at the front hid every ready row
   behind it.

Production, 2026-11-13 (job metadata, counts only): 15 of 71 owners with fresh provider units
committed none. Each had a fresh unit held on a rate-limited vendor in front, and ready fresh rows
behind it without `ready_at`. 7,784 ready fresh units were affected. They were released by
restoring `ready_at` on those rows (operator script, 7,375 rows written); this change removes the
dependency on that field for provider rows.

## Change

- `_fresh_pick` measures the wait with `_ready_since`: `ready_at`, or for a provider row while
  provider merge membership is on, `provider_intent.settled_at`.
- The fresh-pending probe (`fresh_pending` in the Firestore store, the Postgres job store and the
  simulator store) reads up to four pages of 32 while a full page holds no ready row. Same query,
  same index. It stops at the first page that is short or contains a ready row, so the common case
  is still one page.
- The newest-commits read in projection discovery records a fallback
  (`recent_discovery` to `main_cursor`) when its query fails, instead of failing silently.

## Cost

One extra query per page read, only for an owner whose first 32 pending fresh rows are all unready,
at most three extra per probe. The commit transaction re-reads every skipped earlier row, so a
commit that passes N unready rows reads N job documents, at most 127.

## What it does not do

- It does not make a held unit ready. A fresh unit held on a vendor still waits for the vendor;
  later ready rows pass it and it appends afterwards as a late capture, as before.
- Past four pages of unready fresh rows the ready rows behind them are still not seen.
- A GPU row without `ready_at` is unchanged: the settle instant stands in only for provider rows.

## Off switch

None of its own. `BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED=false` removes the settle-instant
fallback together with the rest of provider merge membership.
