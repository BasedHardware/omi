# v3 bounded pending batches (SCA-2918)

The live builder retries seed-driven closure overflow with eight oldest pending
seeds, then one. Each retry loads the full closure for its seeds and commits
with the existing revision, lease, claim and deletion fences. The final
projection commit remembers a successful smaller page on the builder lease so
the next bounded pass starts there. A successful full-size commit clears it.

Before projection loading, a live builder scans the oldest 50 pending rows
using the existing index. It clears only pending fields on discarded or
deleted recordings whose revisions still match under the builder lease and
account-deletion fences. This works even when the projection still parks.
Each attempt reads at most 50 query rows and re-reads at most 50 recordings
plus the lease and deletion marker in the cleanup transaction. On a parked
owner, terminal rows behind 50 still-pending nonterminal rows remain owed.

An old budget or document-size park gets one early attempt. A document-size
retry starts at one seed. A failed bounded retry observes normal backoff.

**Follow-up: bounded unlocked-window reconciliation.** The full builder commit
replaces the unlocked index with its plan's unlocked IDs. A partial load
would drop omitted previews' lock obligations. A follow-up must preserve
unvisited IDs under the builder lease, schedule their lock deadlines
independently of pending seeds, and load each selected window's complete
claim and source closure. Recover those owners by draining that paged index
with the new worker, then replaying live reconciliation. A one-seed closure
that exceeds budget still requires separate ownership-closure repair.

Set `CONVERSATIONS_V3_BOUNDED_PENDING=off` to restore the fixed page and
disable pre-load cleanup. Track age and pending counts for seed-driven
closures that fit after shrinking, and terminal markers in the oldest page.
Report surviving owner-wide count and byte overflows separately.
