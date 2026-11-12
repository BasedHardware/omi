# 2026-11-12 — Deletion fence settles as a policy latch on every custody path

## What changed

`routers/pusher.py`: the account-deletion fence
(`DestructiveOperationInProgress`) is now latched session-wide on the
durable custody commit path, exactly like the encoded-batch uploader
already latched it. The session-scoped `upload_fenced` latch moved to the
endpoint scope so both commit paths share it, and:

- `commit_durable_window` re-raises the fence without latching
  `durable_commit_unresolved` (a pre-write policy refusal leaves no
  unknown remote outcome to protect);
- `_queue_private_cloud_chunk` catches the fence on the window commit,
  drops the window as a policy drop (same counter, same fallback record,
  same warning shape as the encoded latch), and fast-refuses every later
  flush at enqueue;
- the durable record-close scan retires pending closes instead of
  attempting the recording-finish write against the fenced account;
- `finish_receive` computes `tail_committed` as
  `durable_audio and not upload_fenced`, so a fence-latched tail books no
  inline finish.

The session ends close 1000, journey `success`, one warning naming the
fence — no traceback, no `window_tail` booking, no would-drop, no
reconnect hold. Real storage failures keep every loud behavior they had.

## Why

While an account deletion wipe owns the storage authority's gate, every
owner-scoped GCS write for that account is refused — permanently, for as
long as the wipe runs (hours). The durable custody path treated the
refusal as an application fault: the receive loop's catch-all closed the
session 1011 with `Could not process audio`, the shutdown tail logged a
`finish_receive`-named traceback through its generic arm (booking a
`window_tail` failure for a commit the fence refused before dispatch),
and the pre-write refusal latched the custody-unresolved fence even
though nothing had been dispatched. The client reconnected into the same
permanent fence and burned the refusal again — the prod traceback shape
the sensor counts on `finish_receive → _queue_private_cloud_chunk`.

## Contract notes

Nothing client-visible changes for healthy accounts: the fence only
affects sessions whose account writes are already refused. For those, the
socket stays healthy to the peer (frames answered, clean close 1000)
instead of erroring, and uncommitted windows are dropped as policy drops
(the wipe's purge verification owns any stray media object from a window
whose manifest call was fenced after its media call landed). The encoded
uploader's landed latch behavior is unchanged, and non-fence failures
(availability, precondition, deterministic writer errors) keep the loud
1011 / traceback / hold settlements.

Failure-Class: FC-account-deletion-fence-refusal-classified-as-custody-commit-failure

Details: `backend/docs/pusher-deletion-fence-custody-settlement.md`.
Tests: `backend/tests/unit/test_pusher_deletion_fence_custody_settlement.py`
and the generated settlement grids
(`backend/tests/unit/test_deletion_fence_settlement_grid_*.py`).
