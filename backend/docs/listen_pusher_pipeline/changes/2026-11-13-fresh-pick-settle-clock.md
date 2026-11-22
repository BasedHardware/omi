# Fresh-first pick reads the settle instant (2026-11-13)

## What was wrong

When an owner's head is catch-up or held backlog, the merge probes the owner's earliest pending
fresh rows and commits the earliest once it is ready. If that earliest fresh row is not ready, a
later ready fresh row may pass it after the head wait. That wait was measured only from the row's
`ready_at`. A provider row that settled while the stamp was off, or whose `ready_at` was removed,
carries a settle instant on `provider_intent.settled_at`. The head-wait path already read it
(`_ready_since`); the fresh pick did not, so such a row's wait was not measured and it did not pass
the unready row in front.

Production, 2026-11-13 (job metadata, counts only): 15 of 71 owners with fresh provider units
committed none. Each had a fresh unit held on a rate-limited vendor in front, and ready fresh rows
behind it without `ready_at`. 7,784 ready fresh units were affected. They were released by
restoring `ready_at` on those rows (operator script, 7,375 rows written); this change removes the
dependency on that field for provider rows.

## Change

- `_fresh_pick` measures the wait with `_ready_since`: `ready_at`, or for a provider row while
  provider merge membership is on, `provider_intent.settled_at`.
- The merge logs `event=batch_merge outcome=fresh_probe_full_no_ready` when the fresh probe returns
  a full page (32 rows) with no ready row: one line per commit attempt that finds it, not
  throttled. See the limit below.
- The newest-commits read in projection discovery records a fallback
  (`recent_discovery` to `main_cursor`) when its query fails, instead of failing silently.

## What it does not do

- It does not make a held unit ready. A fresh unit held on a vendor still waits for the vendor;
  later ready rows pass it and it appends afterwards as a late capture, as before.
- The probe still reads one page of 32. If an owner's first 32 pending fresh rows are all unready,
  ready rows behind them are not seen and nothing commits through the pick for that owner. The new
  log line reports that state. Reading further pages was tried and left out: a probe of several
  pages is not one consistent read. A pick that can see past one page, made inside the
  transaction, is a requirement of the metered release work.
- The probe is a hint read outside the transaction. A row it did not return that becomes ready
  between the probe and the transaction can be passed by the picked row; it then commits on a later
  drain as a late capture. This window is unchanged by this change.
- The pick takes the longest time any ready fresh row on the probe page has been ready and, once
  that reaches the head wait, commits the earliest ready row on the page. Only a provider row
  supplies a settle instant. A ready GPU row without `ready_at` still cannot start the wait by
  itself, but a later provider row's settle instant can now make that earlier row the one picked.
- A recovered provider unit whose `ready_at` was removed would be measured from an earlier
  attempt's settle instant, which can shorten its wait behind an unready row.

## Off switch

None of its own. `BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED=false` removes the settle-instant
fallback together with the rest of provider merge membership.
