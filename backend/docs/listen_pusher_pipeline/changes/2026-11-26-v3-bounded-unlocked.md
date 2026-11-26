# v3 bounded unlocked windows (SCA-2918)

The live builder seeds reconciliation with up to eight builder-lease unlocked
windows, falling to one on the smallest pending retry. The existing source,
claim, row and byte closure checks still apply to each attempt. A cursor in
the builder lease rotates selection when an earlier preview stays unlocked.
The final transaction preserves the indexed IDs outside the loaded closure
and replaces the visited portion with the planned unlocked windows.

A paged pass schedules a next-minute continuation for the omitted windows
even when no pending recording or selected group needs a wake. The selected
groups keep their normal lock deadlines. The continuation is queued before
the lease cursor advances, under a task name keyed by the pass's lease token,
so an earlier same-minute wake cannot swallow it. If the pass outlasts that
wake, which then finds the lease busy, it queues one more after release.
Each attempt reads the existing builder lease and at most eight indexed seed
documents, plus the existing pending reads and the full bounded closure.
The cursor and retained IDs share the existing final lease write.

Set `CONVERSATIONS_V3_BOUNDED_PENDING=off` to restore the whole unlocked-index
load and fixed pending page. Reconcile affected owners and verify that the
count parked on unlocked-index overflow reaches zero. A single window's
ownership closure can still exceed the budgets and require repair. Owners
without an outstanding wake need a replay to enter the new path.
