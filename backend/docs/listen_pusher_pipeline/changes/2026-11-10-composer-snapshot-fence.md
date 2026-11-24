# Fence composer writes against newer members

The single-member shortcut and empty-result clearing now validate every retained
member's canonical Firestore document revision inside the episode CAS transaction.
The episode must also retain the state version read before computing the notes.
A newer finalize, visibility change, member arrival, membership change, or replica
compose therefore refuses stale output without stamping its fingerprint current.
The window-only fallback retains both guards. A member revision refusal returns
`superseded` immediately; normal read/finalize recomputation picks up the change.
No model call is made by the shortcut, and no flags or defaults change.

Regression coverage lives in `test_episode_single_member_compose.py`, exercising
the real episode persistence helper with the strict Firestore transaction fixture.
It covers newer replica notes surviving, member-only changes, empty snapshots,
missing-member arrival, fallback refusal, and successful writes/recomputation.
The fixture checks transaction read ordering; it does not model contention retries.

Paid multi-member writes now also pass the canonical revisions from the post-call
`_members` fingerprint snapshot to the same transaction, including the window-only fallback.
The original paid members are checked even when a processing member makes the
fresh member list empty. Any missing or hidden original member refuses output
unconditionally, including a hide during the final visibility pass itself.
Visibility rereads only compare against the fingerprint snapshot: a different
revision or an original member absent from that snapshot refuses publication.
They never replace or add expected revisions. Both write variants validate the
unchanged snapshot revision map inside the transaction.
A later document revision change or deletion refuses publication atomically;
removal from retained episode membership is fenced by the episode CAS guard.
The refused paid result is discarded without replacing notes or stamping its
fingerprint. Lease release remains token guarded. Visible evidence that changed
during the model call can still use the existing keep-paid pending policy, but
only while the post-call fingerprint snapshot remains current through visibility
checking and publication.

`test_episode_paid_member_fence.py` exercises real episode persistence with the
strict transaction fixture: deletion, soft deletion, discard, merge-away and
revision changes between the final reads and write leave the paid content absent.
It also covers visible notes changing between fingerprinting and the final
visibility read, unchanged writes, and the window-only fallback. Refusals return
`superseded` immediately and reuse existing recompose scheduling: background work
with settling enabled buys one call, then waits for the quiet-window timer;
settling rollback retains the existing three-attempt scheduler cap. No new retry
loop, flag, model call or scheduler is introduced. The fixture enforces transaction
read ordering, not contention/retry semantics.

Other pre-read compose writes inspected for the same pattern:

- `defer_late_compose` reads the first member title before its episode write and
  guards only the composed fingerprint. That provisional title can lag a concurrent
  summary until the first-open compose; it does not stamp composed evidence current.
- The unchanged branches' `_trigger_stamp` and `_observe_evidence` write scheduling
  metadata derived from pre-read members. They can lag a concurrent member update,
  but do not replace notes or advance `composed_fingerprint`.

These remaining metadata/provisional paths are listed explicitly for the L8b
review disposition. No production calls or live data are needed to validate the
write fences.
