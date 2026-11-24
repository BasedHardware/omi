# A user finish of an audio-only recording keeps its manual end

SCA-3024. Mobile captures are server-batch-only: when the user taps Finish or
double-taps the pendant, the recording has audio and no transcript. The
finalization worker closes it through `complete_server_batch_capture` and never
reaches the transcript path that calls `changed(manual_end=True)`. The batch
transcript then landed as ordinary speech. The window waited for five minutes of
silence and the lock delay, stayed live while the pendant kept recording, and a
short window was hidden from Home because it carried no manual end.

## The marker

The terminal transaction stores `v3_manual_end_requested` on the recording when
the finalization job's trigger is `client_finalize`. That adds one field to an
existing write. The request is inert. Record admission, which knows the
recording's batch units, promotes it to `v3_manual_end`:

- A single unit projects as one transcript, so the cut is stored at admission
  (one read and one write) and the window locks when that transcript lands.
- Several units project one at a time. A cut applied to the first projection
  would lock a partial window and turn the later units into fragment cards, so
  those recordings keep the silence and lock timers unless the fast first
  transcript takes them.

Rollback: `CONVERSATIONS_V3_BATCH_MANUAL_END=off` on `backend` and `backend-integration`.

## The fast first transcript

`CONVERSATIONS_V3_FAST_FINISH` (default `cohort`, the empty `v3-fast-finish`
rollout cohort). After admission commits, `utils/conversations/v3/fast_finish.py`
transcribes every unit of the recording once through the prerecorded provider
for its language, stores the cut, and writes the result with
`update_conversation_segments`. That write marks the recording pending and wakes
reconcile, so notes start without the batch merge and delivery wait.

- The batch record projection owns the canonical transcript. `replace_record`
  replaces the provisional segments inside each unit span, and the writer
  refuses the fast write once `record_projection_revision` is set.
- The row is re-read just before the write: a delete, discard, lock or
  canonical projection during the provider call wins.
- The outer provisional lines are stretched to the audio span, so the batch
  transcript's first and last lines stay inside the locked window.
- Provisional segments carry no speaker number, so canonical speaker numbering
  starts where it would have.
- Skipped: recordings over 20 minutes, partial records, custom STT, locked,
  discarded and private rows. One pass per recording per process.

Known limits, to settle before `on`: notes written from the provisional
transcript are not rewritten when the canonical one lands; a recording with
speech groups more than five minutes apart has inner window edges that are not
stretched; there is no concurrency cap on passes.

Readback: `omi_conversations_v3_batch_manual_end_total{outcome}`,
`omi_conversations_v3_fast_finish_total{outcome}` and
`omi_conversations_v3_fast_finish_seconds{stage}`; on the cohort account, seconds
from the finish request to the derived row reaching `tile_state=done`.
