# Settle one terminal disposition when a durable commit outcome is unknown

After one durable audio commit failed or was cancelled before its receipt, the
pusher set `durable_commit_unresolved` and then raised
`RuntimeError('custody commit unresolved; producer fence retained')` from
`_queue_private_cloud_chunk` on every later flush, including the shutdown tail.
The socket therefore ended in a second unhandled exception record per tail,
which is what Error Reporting grouped as `CIzGga-6sdmoZQ` (167/24 h) and
`CKH8ltvctYioaQ` (81/24 h at capture; both counted from the
`finish_receive` -> `_queue_private_cloud_chunk` frames, SCA-2668).

The fence itself was correct and stays: an unknown storage operation is never
rerun. What changed is its outcome. The first failed/cancelled dispatch now
closes the fence with **one** terminal disposition, and later flushes and the
shutdown tail observe it and return instead of raising:

- `durable_commit_unresolved` is still set when no receipt was observed.
- `durable_commit_disposition` is set once per socket to `unresolved`; the
  settle helper records it once and is idempotent thereafter.
- The retained window, its PCM and its frame checkpoints stay in
  `refused_windows`; the producer token stays held (`hold_recording`) so the
  client's WAL must replay. No receipt or opcode-203 ACK is produced.
- The record is a structured warning naming no message or args:
  `event=durable_custody_commit_disposition disposition=unresolved
  stage=commit|window_tail exception_type=<class> raised_by=<frame>`.
  `stage=commit` is a live flush failure; `stage=window_tail` is the
  shutdown-tail first failure or a fault outside the dispatch. The settlement
  adds exactly one `omi_audio_custody_would_drop_total{stage}` (pre-durability
  loss) and never touches `omi_audio_custody_failures_total`: the storage
  helper (`utils/other/audio_outbox.commit_capture`) already records the
  dispatch failure as `stage="commit"` before re-raising, so counting it again
  here would double one disposition. Cancellations and faults that never
  reached the storage helper are counted only as would-drop, plus the
  disposition line.
- No `logger.exception` is emitted from the tail path, so a fenced socket is one
  recorded outcome rather than one Error Reporting event per tail. The socket
  still fails closed: `1011` on the first unknown outcome, or the existing tail
  failure close. The client sees one terminal close.

Every caller of `_queue_private_cloud_chunk` and `finish_receive` that could
observe the raise is unchanged in behaviour for known outcomes:

- `_queue_private_cloud_chunk` callers are all inside `process_frame`: header
  103 conversation switch, header 104 close-v2 abort/commit and the
  process-conversation request, and header 101 gap, framed-boundary, window-cap
  and size-boundary flushes. Each raise still propagates through `process_frame`
  to `receive_tasks`, whose `except Exception` records
  `event=pusher_receive_failed` and closes `1011`.
- `finish_receive` is called only from the `receive_tasks` finally. Its tail now
  skips storage when the disposition is already settled and, if it is the first
  fault, settles it once before closing `1011`.
- `_websocket_util_trigger` and `_run_websocket_util_trigger` observe only the
  existing CancelledError/Exception split; no new exception type escapes.

Unchanged: the custody/privacy guards, the producer fence's purpose, retention
and deletion behaviour, per-socket byte-budget accounting, the refusal path's
no-error-close behaviour, and the wire protocol (no new frame or close code).
Committed windows are never re-committed: the failing window is not popped and
already-receipted windows are unaffected.

The disposition is socket-local. It is not persisted and no other service reads
it. Kill switch: revert this commit; the raise-per-tail behaviour and both error
groups return unchanged, with no data migration.

Coverage in `backend/tests/unit/test_audio_durable_outbox.py`:
`test_one_failed_durable_commit_settles_once_and_the_tail_never_raises`,
`test_cancelled_durable_commit_settles_once_and_the_tail_never_reruns`,
`test_refused_durable_tail_retains_the_fence_without_raising`,
`test_normal_durable_tail_commits_once_without_a_disposition`, and
`test_real_storage_failure_counts_one_commit_failure_and_settles_once` (live
and tail variants through the real storage helper). Runbook:
`backend/docs/runbooks/audio-durable-outbox.md`.
