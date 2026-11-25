# V3 Finish keeps a predecessor whose transcript lands after the cut

Finish means "finish what I was just saying". A user who talks without a pause can still end up with
two recordings: the phone loses the stream, reconnects, and the server opens a new recording of the
same capture origin (`external_data.recording_origin_id`, new `recording_session_id`). When the user
then taps Finish, the second recording's fast-finish provisional transcript lands within seconds and its
stored `v3_manual_end` cuts and locks the window. The first recording's batch transcript lands later.
Its speech then fell before a locked window, `preserve_finished_windows` kept it out, and it became its
own finished, non-manual card. That card sat under the Home word floor and was hidden. The Finish
conversation held only the reconnected tail and any sync fragment.

A reconcile that runs before the Finish recording's own transcript lands could also lock the window
around an earlier fragment alone (for example a device-sync fragment that lands first).

## Change

`CONVERSATIONS_V3_CAPTURE_CONTINUITY` (default `on`, builder only):

- **The cut waits for pending speech.** A manual-end cut is held while one of these still has no
  transcript: its own recording, or a batch recording that precedes it and was sealed at or before
  the Finish recording's seal (`record_sealed_at`). The predecessor must be in the same capture origin
  or within the silence gap of the finished speech. "No transcript" means `policy.awaiting_batch_transcript`:
  a batch lane owner, sealed, no `record_projection_revision`, no segments, no failure receipt.
  - While held, the stretch is planned as if the cut had not arrived yet, so it stays an open window.
  - When the transcript lands, its write wakes the builder and the cut applies to all of the speech at once.
  - The wait ends `policy.FINISH_WAIT` (5 minutes) after the cut, and the builder schedules a wake for
    that moment. A Finish therefore never settles later than the same speech would at the default lock
    delay without a Finish.
- **A stream gap is not silence.** Between two recordings of one capture origin, the unrecorded interval
  (up to 30 minutes, `outline.CAPTURE_GAP_LIMIT`) no longer counts toward the silence gap. Recorded
  silence inside either recording still counts.
- **The loader finds predecessors it did not load.** For a fresh cut (within the wait) it reads at most
  8 metadata-only documents: the recordings that started up to an hour before the Finish recording,
  nearest first. It hands the ones still awaiting a transcript to the planner. They are never loaded
  as sources.

A single-recording Finish whose transcript has landed is unchanged: nothing is pending, so the cut
applies on the same pass and notes start at once. Backfill and re-derive passes do not use the switch.

Counter: `omi_conversations_v3_finish_held_total` (builder passes that kept a cut open).

## Rollout and rollback

Default on. Set `CONVERSATIONS_V3_CAPTURE_CONTINUITY=off` on the v3 builder service to restore the
previous cut and silence rules and skip the predecessor read. Rows already written keep their boundaries.

## Evidence

- `tests/unit/test_conversations_v3_finish_late_predecessor.py` replays the incident order (sync
  fragment, then the fast-finish tail with the cut, then the batch predecessor). It runs the real
  `service.reconcile` and `commit_projection` at 300/300 and 900/3600 timing, with landings
  reconciled one at a time and together.
  - Before the change, the result is the production shape: the predecessor is a hidden
    `below_word_minimum` card and the tail is the manual-end card.
  - With the per-landing order, the fragment alone became the manual-end card.
  - After the change, there is one manual-end, visible conversation with all three recordings.
- The pipeline lab (synthetic v3 day, same timeline) reproduces the production split on `main` and
  shows one Finish conversation with this change. This holds when the predecessor's sealed row exists
  before its transcript lands.

See the [v3 pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3).
