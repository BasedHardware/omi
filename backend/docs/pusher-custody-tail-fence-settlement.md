# The custody fence refusal settles quietly at the shutdown tail

Shipped 2026-11-05. One producer-visible custody failure used to book two
loud failure records: the mid-session boundary that actually failed, and a
second `finish_receive`-named traceback at the shutdown tail for a commit
the tail never attempted.

## Root cause (prod evidence)

The Loop S prod-log sensor carries a ~100-per-30-minutes pusher signature
shaped `Traceback … File routers/pusher.py … in finish_receive … await
_queue_private_cloud_chunk()`. It is the shutdown tail's
"Durable audio window tail commit failed at shutdown" traceback family. The
transient-availability cause of that family was removed by the
custody-commit shed (`docs/audio-custody-commit-transient-shed.md`), but
one structural cause remained: the custody fence.

The `durable_commit_unresolved` fence exists so a session whose window
commit failed with an unknown remote outcome never runs another storage
operation (`routers/pusher.py`, `commit_durable_window`). The fence raise
was a bare `RuntimeError`, so at the shutdown tail it landed in
`finish_receive`'s generic exception arm — the arm built for a tail commit
that actually failed. That arm books `record_failure('window_tail')` +
`record_would_drop('window_tail')` and logs `logger.exception` with a
traceback naming `finish_receive` → `_queue_private_cloud_chunk`, exactly
the sensor's signature shape. For a fence refusal that accounting is
false: the tail attempted no commit, nothing dropped (the producer stays
unacknowledged and replayable), and the real failure was already settled at
its own boundary — close 1011, the custody layer's commit-failure counter,
and one application-error log from the receive loop. Under a storage
outage, every active durable session produced this second, misleading
traceback on top of its real error.

## The change

- `routers/pusher.py` adds `CustodyCommitUnresolved(RuntimeError)` and the
  fence site raises it. The message is unchanged and the `RuntimeError`
  ancestry is unchanged, so every mid-session handler behaves exactly as
  before.
- `finish_receive` gains a typed arm ahead of the generic exception arm.
  It keeps the fail-closed settlement — close code 1011, observation reason
  `application_error`, the recording hold (the only hold site for a
  mid-session failure), the producer unacknowledged — and replaces the
  duplicate failure metrics and the traceback with one warning line naming
  the fence. A fresh tail-commit failure still takes the generic loud arm
  unchanged.

Failure-Class: FC-custody-fence-refusal-rebooks-tail-commit-failure

## Tests

`backend/tests/unit/test_pusher_custody_tail_fence_settlement.py` pins, for
every transient and deterministic commit-failure class: the fence latch,
the quiet tail settlement (no `window_tail` booking, no would-drop, one
fence warning, no traceback, hold applied, 1011, unacknowledged producer),
the exactly-one application-error invariant, and the single storage attempt
(the tail never re-attacks); the loud generic-arm parity for a fresh
tail-commit failure; the latch-vs-receipt boundary (a post-receipt queue
failure never latches); latch behavior at every mid-session flush site
(window boundary, size boundary, conversation switch, process request,
pre-ID audio); the custody-integrity invariants (replay after reconnect
commits the refused window exactly once, content-addressed, no duplicate
objects); and the typed-contract surface.
