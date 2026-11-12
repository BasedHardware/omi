# Deletion fence custody settlement (pusher listen sessions)

The storage authority fences every owner-scoped GCS write while an
account deletion wipe (or another destructive operation) owns the
account gate: `database.legal_holds.DestructiveOperationInProgress`,
raised by `utils.other.storage.owner_storage_write_gate` **before** the
upload call. The refusal is permanent for as long as the wipe runs —
hours — and carries no unknown remote outcome: nothing was written.

Pusher listen sessions commit captured audio through two paths, and both
settle the fence as one session-wide policy latch (`upload_fenced`):

- **Encoded batch uploader** (`.batch.enc` batches): the upload task
  latches the fence, drops the batch as a policy drop, and fast-refuses
  later batches.
- **Durable custody windows** (`audio_custody=1`): the window commit is
  refused pre-dispatch, the window drops as a policy drop, later flushes
  fast-refuse at enqueue, pending record closes retire without a finish
  attempt, and the shutdown tail books no inline finish.

## Settlement contract for a fenced session

| Boundary                | Settlement                                                        |
| ----------------------- | ----------------------------------------------------------------- |
| Window commit refused   | policy drop: budget released, buffer reset, counter +1, one warning |
| Later flushes           | fast-refused at enqueue (no writer calls, no repeated warnings)   |
| Record close            | retired (no recording-finish write against the fenced account)    |
| Shutdown tail           | no `window_tail` booking, no hold, no traceback, no inline finish |
| Session close           | close 1000, journey `success`, not an application fault           |

The refusal is never retried: `DestructiveOperationInProgress` is absent
from both transient classifiers (the commit shed's availability set and
the admission shed's transient set), so it keeps the loud first-attempt
arm everywhere else.

## Why not fail closed

A fenced account's canonical identity is being destroyed; the wipe's
purge verification owns any stray media object (a window whose manifest
call was fenced after its media call landed). Booking an application
failure, a producer hold, or a replay debt against that account only
creates a reconnect loop: the client reconnects into the same permanent
fence and burns the refusal again — the traceback shape the prod sensor
counts on `finish_receive → _queue_private_cloud_chunk`.

## Non-fence failures are unchanged

Availability failures (`ServiceUnavailable` and the rest of the
commit-shed set), precondition conflicts, and deterministic writer
errors keep the loud settlements: close 1011, `Could not process audio`
mid-session, `window_tail` booking plus the traceback and the reconnect
hold at the tail, and the custody-unresolved latch for commits whose
remote outcome is genuinely unknown.

Failure-Class: FC-account-deletion-fence-refusal-classified-as-custody-commit-failure

Tests: `backend/tests/unit/test_pusher_deletion_fence_custody_settlement.py`
(hand-written settlement matrix) and
`backend/tests/unit/test_deletion_fence_settlement_grid_*.py` (generated
per-position settlement and parity grids).
