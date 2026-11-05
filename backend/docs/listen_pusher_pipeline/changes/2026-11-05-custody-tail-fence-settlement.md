# 2026-11-05 — Custody tail fence settlement

## What changed

`routers/pusher.py`: the `durable_commit_unresolved` fence refusal now
raises a typed `CustodyCommitUnresolved(RuntimeError)` (same message), and
`finish_receive` settles it in a dedicated arm: close 1011, observation
reason `application_error`, the recording hold, producer unacknowledged —
but no `window_tail` failure booking, no would-drop counter, and no
traceback. One warning line names the fence. A fresh tail-commit failure
keeps the loud generic arm unchanged.

## Why

A mid-session custody commit failure latches the fence, so the shutdown
tail's flush is refused without any storage operation. Because the refusal
was a bare `RuntimeError`, it landed in the tail's generic failure arm and
was booked as a fresh `window_tail` commit failure plus a
`finish_receive`-named traceback — the Loop S sensor's `finish_receive →
_queue_private_cloud_chunk` signature — even though the tail attempted no
commit and dropped no audio. One producer-visible failure produced two
loud failure records, and the traceback misattributed the refusal to the
tail. Under a storage outage this added one misleading traceback per
active durable session.

## Contract notes

Nothing client-visible changes: the close code (1011), the hold, and the
unacknowledged-producer replay contract are identical. Only the failure
accounting for the refusal is corrected. The generic arm still books
`window_tail` loudly for a tail commit that actually fails.

Details: `backend/docs/pusher-custody-tail-fence-settlement.md`.
Tests: `backend/tests/unit/test_pusher_custody_tail_fence_settlement.py`.
