# Fresh re-offer marker (2026-11-14)

Follows `2026-11-13-fresh-pick-settle-clock.md`, which shipped without this part.

## Change

The merge writes the existing durable hold marker (`merge_holds`) for an
owner when a merge call commits nothing while ready fresh rows sit on the probe page, or when a
drain spends its 100-commit budget with such rows left. Maintenance already re-offers marked
owners; `release_hold` now keeps the marker while the owner's last drain in that process left
ready fresh rows, and clears a re-offer marker after a drain that finds none. Each marker written for this
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

Bounds on the re-offer. The marker written for this reason carries `reoffer: fresh`; maintenance
clears it on any visit after which the process has no ready fresh row waiting for the owner,
whatever the projection depth. A depth-hold marker has no such field and keeps its rule; an owner
holding a re-offer marker that reaches the depth cap gets a depth-hold marker instead.

- A row inside its head wait: kept until the wait ends and the row commits.
- An owner with more ready rows than one drain commits: every visit commits rows, so it ends.
- An owner whose probe page is 32 unready rows with ready rows behind: the page shows no ready
  row, so no marker is written for this reason and one already held is cleared on the next visit.
  (That owner still does not drain; see below.)
- An owner whose strict transaction was fenced is not marked. A row-level privacy refusal does not
  stop the marker.
- Anything that leaves a ready fresh row on the page without a commit: the process stops keeping
  the marker once the owner has gone the head wait plus 30 minutes without a commit
  (`event=batch_merge outcome=fresh_reoffer_gave_up`); a later commit, or 10 minutes without
  seeing the owner, starts the clock again. The clock is per process. Its table holds 4,096
  owners and evicts only owners not seen for 10 minutes; when it is full, a further owner is
  not tracked and not marked (`fresh_reoffer_table_full`).
- A failed marker write is logged (`fresh_reoffer_mark_retry`) and never stops the drain.
- A transient error on the probe query keeps or writes the marker, under the same bound: the call
  could not see whether rows wait. The marker transaction is not throttled per process, because
  another process may have cleared the marker.
- Cost of a visit: the marker listing reads the owner's first pending row, then one drain of up to
  100 commit attempts (each a strict transaction, the probe query, and a second transaction when
  a row commits; a visit that commits nothing is one attempt). Maintenance visits at most 50
  markers a pass.
- Concurrency. Drains run on a shared executor. The per-process table and the set of owners left
  waiting are read and written only under one lock, which is never held across a store call or a
  log call.

## What it does not do

- It does not make a held unit ready, and it does not see past the probe's one page of 32 (see the
  earlier note). A pick made inside the transaction, and a discovery cursor that reaches every
  ready row, are requirements of the metered release work.
- The clock that bounds the re-offer is per process: a restart, or a second process draining the
  same owner, starts its own.

## Off switch

`BATCH_PIPELINE_FRESH_REOFFER_MARKER_ENABLED=false` stops new marker writes for this reason;
re-offer markers already written are cleared on their owner's next maintenance visit. The marker is written only on the fresh-probe path, that is when the
owner's head is catch-up or held backlog. The settle-instant pick has no switch
of its own: `BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED=false` removes it together with the
rest of provider merge membership.
