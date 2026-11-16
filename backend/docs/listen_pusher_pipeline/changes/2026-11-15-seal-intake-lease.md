# Preserve intake claims when waking a repaired seal

The seal repair must not cancel an intake replica's archive/staging lease.
Both a retry delay and a claim use `available_at`, so a future value alone is
insufficient evidence that waking the job is safe.

Intake now records `record_intake_retry_at` only when it releases its own claim
into a deferred retry, with exactly the same value as `available_at`. Claiming
removes that marker. The seal transaction reads the current job and wakes it
only if it is already due or its future clock matches the certified retry.
Waking clears the marker atomically. This adds scheduling metadata, not a new
pipeline state, and preserves the seal's existing proof and privacy checks.

The comparison excludes these two scheduling fields from seal approval, but
the wake decision always uses the live transaction snapshot. A claim acquired
between planning and commit therefore seals safely without being reset.
During a rolling upgrade, an old claimant changes `available_at` and thereby
invalidates any previous retry marker too. An unmarked future value is left
alone conservatively; it can be retried normally after that value expires.

Rollback: disable `recordSealRepair.freshEnabled` to stop repair wake writes.
The retry marker can remain stored when reverting code; older readers ignore it.
