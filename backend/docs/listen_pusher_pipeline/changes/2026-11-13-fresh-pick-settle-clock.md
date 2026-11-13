# Fresh-first pick reads the settle instant (2026-11-13)

## What was wrong

When an owner's head is catch-up or held backlog, the merge probes the owner's earliest pending
fresh rows and commits the earliest once it is ready. If that earliest fresh row is not ready, a
later ready fresh row may pass it after the head wait. That wait was measured only from the row's
`ready_at`. A provider row that settled while the stamp was off, or whose `ready_at` was removed,
carries the same instant on `provider_intent.settled_at`. The head-wait path already read it
(`_ready_since`); the fresh pick did not, so for such a row the wait never ended.

Production, 2026-11-13 (job metadata, counts only): 15 of 71 owners with fresh provider units
committed none. Each had a fresh unit held on a rate-limited vendor in front, and ready fresh rows
behind it without `ready_at`. 7,784 ready fresh units were affected. They were released by
restoring `ready_at` on those rows (operator script, 7,375 rows written); this change removes the
dependency on that field for provider rows.

## Change

- `_fresh_pick` measures the wait with `_ready_since`: `ready_at`, or for a provider row while
  provider merge membership is on, `provider_intent.settled_at`.
- The merge logs `event=batch_merge outcome=fresh_probe_full_no_ready` when the fresh probe returns
  a full page (32 rows) with no ready row: one line per commit attempt. An owner drain makes up to
  100 attempts and repeats the line only after another of the owner's rows commits in between. See
  the limit below.
- The newest-commits read in projection discovery records a fallback
  (`recent_discovery` to `main_cursor`) when its query fails, instead of failing silently.

- **Re-offer marker.** The merge writes the existing durable hold marker (`merge_holds`) for an
  owner when a merge call commits nothing while ready fresh rows sit on the probe page, or when a
  drain spends its 100-commit budget with such rows left. Maintenance already re-offers marked
  owners; `release_hold` now keeps the marker while the owner's last drain in that process left
  ready fresh rows, and clears it after a drain that finds none. Each marker written for this
  reason logs `event=batch_merge outcome=fresh_reoffer_marked`.
  Kill switch `BATCH_PIPELINE_FRESH_REOFFER_MARKER_ENABLED` (unset = on).

## Why the re-offer marker

An owner's merge drain runs when one of its units settles, when maintenance finds one of its rows
on the global ready page, or when it carries a hold marker. Since the provider backlog hold the
global ready page (the 100 oldest `result_ready` rows) holds only held backlog rows, and the merge
writes no depth-hold marker for a held-backlog head. An owner that went quiet while ready fresh rows
were inside the head wait, or whose drain stopped at its budget, was not drained again.
Production, 2026-11-13 22:07Z (counts only): 23 owners, about 3,400 ready fresh rows, no commits;
none of the owners had a held marker. Those owners were released with an operator script that
writes the same marker.

Bounds on the re-offer:

- A row inside its head wait: the marker lasts until the wait ends and the row commits.
- An owner with more ready rows than one drain commits: every visit commits rows, so it ends.
- An owner whose probe page is 32 unready rows with ready rows behind: the page shows no ready
  row, so no marker is written or kept. That owner is not re-offered (and still does not drain;
  see below).
- A fenced owner is not marked.
- Anything else that leaves a ready fresh row on the page without a commit: the process stops
  keeping the marker after 30 minutes without a commit for that owner
  (`event=batch_merge outcome=fresh_reoffer_gave_up`); a later commit, or 10 minutes without
  seeing the owner, starts the clock again. The clock is per process.
- Cost of a visit: the marker listing reads the owner's first pending row, then one drain (a strict
  transaction, the probe query, and a second transaction when a row commits). Maintenance visits
  at most 50 markers a pass.

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

`BATCH_PIPELINE_FRESH_REOFFER_MARKER_ENABLED=false` stops new marker writes for this reason;
markers already written are cleared by maintenance the way any hold marker is (below the depth
cap, or depth hold off). The marker is written only on the fresh-probe path, that is when the
owner's head is catch-up or held backlog. The settle-instant pick has no switch
of its own: `BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED=false` removes it together with the
rest of provider merge membership.
