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
for its language and writes the result with `update_conversation_segments`. That
write marks the recording pending and wakes reconcile, so notes start without
the batch merge and delivery wait.

- The cut: a single-unit recording is already cut by admission. For several
  units the pass stores the cut (`changed(manual_end=True)`) only after the
  whole-recording transcript is written, so a failed or refused write never
  leaves a cut on a partial transcript.
- The batch record projection owns the canonical transcript. `replace_record`
  replaces the provisional segments inside each unit span, and the writer
  refuses the fast write once `record_projection_revision` is set.
- The row is re-read before any audio is sent to the provider and again just
  before the write: a delete, discard, lock, privacy change or canonical
  projection wins.
- Each unit's first and last provisional line is padded by at most two seconds
  and never past that unit's audio, so the batch transcript's edge lines stay
  inside the locked window and every provisional line keeps its midpoint
  inside the unit that replaces it.
- Provisional segments carry no speaker number, so canonical speaker numbering
  starts where it would have.
- Bounds: recordings up to 20 minutes and 8 units (one provider request per
  unit), one pass per recording and two passes at a time per process. Partial
  records, custom STT, locked, discarded and private rows are skipped.
- `CONVERSATIONS_V3_BATCH_MANUAL_END=off` also stops the pass: without a stored
  manual-end request there is nothing for it to act on.

Known limits, to settle before `on`: notes written from the provisional
transcript are not rewritten when the canonical one lands; a recording with
speech groups more than five minutes apart inside one unit has inner window
edges that are not padded; a multi-unit recording that the pass skips or fails
keeps the silence and lock timers.

Readback: `omi_conversations_v3_batch_manual_end_total{outcome}`,
`omi_conversations_v3_fast_finish_total{outcome}` and
`omi_conversations_v3_fast_finish_seconds{stage}`; on the cohort account, seconds
from the finish request to the derived row reaching `tile_state=done`.
