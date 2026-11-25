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

`CONVERSATIONS_V3_CAPTURE_CONTINUITY` (default `on`, live builder only):

- **A reconnect gap is not silence.** Two recordings are one continuing capture when the rows prove
  a reconnect (`outline.reconnected`): the same capture origin (`external_data.recording_origin_id`), a
  different `recording_session_id`, and the same `client_device_id` whenever both rows name one. The
  unrecorded interval between them, up to 10 minutes (`outline.CAPTURE_GAP_LIMIT`, twice the default
  silence gap), no longer counts toward the silence gap. Recorded silence inside either recording
  still counts. Another device, a reused origin without a new session, or a longer gap is ordinary
  silence.
- **The cut waits for speech that joins it.** A manual-end cut is held while one of these still has
  no transcript (`policy.awaiting_batch_transcript`: a batch lane owner, sealed, no
  `record_projection_revision`, no segments, no failure receipt):
  - its own recording, or
  - a batch recording that starts before the Finish recording, was sealed at or before the Finish
    recording's seal (`record_sealed_at`), and joins the finished speech, either within the silence
    gap of it or as the capture the Finish recording reconnects.

  A recording that starts after the Finish recording, or that the gap rule separates from the
  finished speech, never holds the cut.
- **A held cut stays a boundary.** The cut is not dropped while it waits:
  - the window it closes stays open (not locked, not finished, no notes) whatever its age, so the
    ordinary lock delay cannot settle it early;
  - speech at or after the cut is not planned yet, so a later Finish's window never joins it;
  - the awaited recordings' audio spans keep their place in the grouping (they are never emitted as
    lines), so the speech on either side of a pending recording stays one window.

  The recordings it holds stay pending with `v3_pending_since` at the end of the wait. When the
  transcript lands, its write wakes the builder and the cut applies to all of the speech at once. If
  it never lands, the wait ends `policy.FINISH_WAIT` (5 minutes) after the cut: the builder has a wake
  queued for then, and the cut applies to whatever has landed.
- **The loader finds predecessors it did not load**
  (`database/conversations_v3_finish_predecessors.attach`). It runs only for a loaded manual-end
  recording with a capture origin whose cut is within the wait and not yet settled into a locked
  manual-end conversation. It reads the recordings of the same capture origin that start before the
  Finish recording and end within `CAPTURE_GAP_LIMIT` of its start, nearest first, through the
  existing sync lineage composite index (`conversations_recording_lineage`). The read is limited to
  8 documents and projected to 16 metadata fields. Rows still awaiting a transcript go to the planner.
  They are never loaded as sources.

A single-recording Finish whose transcript has landed is unchanged: nothing is pending, so the cut
applies on the same pass and notes start at once. Backfill and re-derive passes do not use the switch.

Counter: `omi_conversations_v3_finish_held_total` (builder passes that kept a cut open).

### Cost

- **Reads.**
  - Per builder pass: one indexed query per loaded fresh, unsettled manual-end recording, returning
    at most 8 metadata documents. A query that matches nothing is billed one read.
  - Per Finish: the query repeats on each pass until the cut settles or the 5-minute wait ends.
    Within the wait a Finish is woken by its own landings, the per-minute named reconcile tasks and
    the hold-expiry wake (at most 7 task names). Each task runs at most 3 passes. The worst case is
    therefore 7 x 3 x 8 = 168 documents per Finish. The usual case is 2-3 passes (the Finish landing,
    the predecessor landing, then the cut settles), so 2-24 documents.
  - Two fresh Finishes loaded together each add their own query.
- **Writes.** No new fields. The held recordings keep `v3_pending`, with `v3_pending_since` at the end
  of the wait, so the ordinary deferred-wake path wakes them. The builder enqueues one extra named
  task for the hold's end.
- **Model calls.** None new. The Finish window's notes run once over all of its speech.

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
- The pipeline lab scenarios (synthetic, #26303 plus its origin follow-up) reproduce the production
  split on `main` and show one Finish conversation with this change. This covers the incident, a
  6-minute reconnect gap (longer than the 5-minute silence gap) and a Finish whose own transcript never
  lands. A single-recording Finish is unchanged.
- Known limit: a device-sync fragment that lands, already older than the lock delay, before the
  Finish recording's cut is stored can still lock by the ordinary lock rule. The hold starts only
  once the cut is stored.

See the [v3 pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3).
