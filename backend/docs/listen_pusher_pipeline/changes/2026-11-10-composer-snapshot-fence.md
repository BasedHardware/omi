# Fence notes-derived composer writes against newer members

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

Other pre-read compose writes inspected for the same pattern:

- The paid `_compose.finish` path re-reads evidence after the model call, checks
  lease ownership and membership at CAS, and rechecks evidence afterward. It still
  has a member-read/write gap: a change in that gap can temporarily publish old
  paid notes and return `stale`. Keeping superseded paid output pending is the
  existing thrift policy; this change leaves that path intact.
- `defer_late_compose` reads the first member title before its episode write and
  guards only the composed fingerprint. That provisional title can lag a concurrent
  summary until the first-open compose; it does not stamp composed evidence current.
- The unchanged branches' `_trigger_stamp` and `_observe_evidence` write scheduling
  metadata derived from pre-read members. They can lag a concurrent member update,
  but do not replace notes or advance `composed_fingerprint`.

These remaining paths are listed explicitly for the L8b review disposition; L8a
is not changed or merged. No production calls or live data are needed to validate
the notes-derived write fence.
