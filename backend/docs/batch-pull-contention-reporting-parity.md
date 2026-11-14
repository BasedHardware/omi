# Pull-lane contention reporting parity

The batch GPU ring loses transaction-contention races by design: Firestore
aborts concurrent writers on the hot shard and owner rows, the bounded chain
replays, and the scheduler spaces its next pull after the storm the store's
damper measured. Losing is not a fault — the recovery is the design. The
ring's reporting, however, still booked two of those designed outcomes on the
ERROR fault channel, so every pull storm reached the production error sensor
twice and every handed-off pull reached it once.

## The contract

- `FirestoreStore.run` stamps the label that burned its contention budget
  onto the raised `FirestoreContentionExhausted.operation` — the same
  ride-along contract as `retry_after`. A caller reporting the loss names the
  exact operation (`batch_pull shard=scheduler_NN`, `batch_fail`,
  `batch_merge_commit`, ...) instead of an anonymous chain. A bare engine
  raise (no labeled store run) carries `operation=None`.
- The scheduler pull lane reports its designed outcomes on their honest
  channels:
  - `event=batch_pull outcome=backoff` — the counted, storm-aligned pause
    the next pull cycle clears with no lost work — logs at **INFO**,
    carrying `failures`, `retry_after_ms`, the losing `operation=` label
    when one was stamped, and the raise `site=`.
  - `event=batch_pull outcome=partial` — committed leases handed to the
    caller after a later shard failed, instead of stranding them until
    lease expiry — logs at **WARNING** with `leased`, `exception_type` and
    `site=`. It fires only for non-contention faults; a contention loss
    after leases takes the backoff branch.
- The retry engine's `firestore_transaction_contention ... outcome=exhausted`
  line keeps its ERROR channel: it is the one true storm signal. The
  scheduler's backoff line is the response to that signal, not a second one.
- The label field never interpolates unvalidated text: a missing, foreign or
  off-vocabulary `operation` shape reports nothing.

## Why the sensor volume halves without hiding storms

Before this change a single pull storm booked two ERROR lines (the engine's
exhaustion plus the scheduler's backoff response), and a pull that handed off
committed leases booked a third. After it, a storm books the engine's line
once; the response and the handoff stay observable at their honest severities
with strictly more diagnostic content (the losing shard label was previously
absent from the response line entirely).

Failure-Class: FC-pull-storm-response-and-lease-handoff-booked-as-production-errors
