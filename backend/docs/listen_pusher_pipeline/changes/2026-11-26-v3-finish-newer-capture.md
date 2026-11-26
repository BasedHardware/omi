# Finish cuts a capture that sealed after the live window's last speech

SCA-4434. Recording A seals, then recording B seals a couple of minutes later.
B is a pendant or server-batch capture, so its transcript is still pending and
no window lists it in `v3_recording_ids`. A's derived window is still live (idle
far less than `live.MAX_IDLE`), so the person's Finish resolved to that window
and `request_finish` cut its tail, A. B got neither the manual-end cut nor a
fast finish. When B's projection landed it had no `v3_manual_end`, so a short B
stayed hidden under the Home word floor. The single-recent-capture fallback
(#26288) and the named-window path (#26361) run only when no window is live.
Reproduced by the pipeline-lab scenario `finish_after_second_close`.

## The newer capture

When Finish resolves to a live window (empty body or the named live window),
the `request_finish` transaction also runs the existing recent-source scan
(`_recent_finish_sources`, newest first, at most `RECENT_FINISH_LIMIT` = 8
documents). A capture qualifies when it:

- is a sealed Listen capture that ended after the window's `finished_at`;
- is not one of the window's sources;
- carries `has_content` (a projection that landed empty clears it);
- passes `_capture_ineligible` like the recording fallback: sealed within
  `RECENT_FINISH_AGE`, unclaimed, not marked for another window, and not
  private, deleted, discarded, locked, merged, a partial archive or a failed
  upload.

The newest qualifying capture wins, as in `_latest_capture`. The same
account-deletion check as the recording fallback runs before any write.

## What Finish stores

- **The capture's speech has landed** (`has_finish_content`: a live-lane
  capture, or a batch capture with a provisional transcript): it takes the
  recording-scoped cut through `_finish_capture` instead of the window tail.
  That is the same write, batch request and empty resolution the fallback uses,
  and the response names the capture.
- **A server-batch capture whose speech has not landed.** The session's last
  capture is often only silence: after the quiet timeout the listen loop seals
  A and opens B, then the device stops and seals B. Audio custody sets
  `has_content` on any committed audio, so B qualifies either way. The
  transaction stores both:
  - the window-tail cut on A, exactly as before this change;
  - B's recording-scoped request.

  Both ledger reads (B's, and A's when A is a batch capture) come before either
  write; StrictFirestore enforces that order in the tests. The response names
  A's window, because the cut landed there. If B is silent, its request clears
  at whole-record completion (`_v3_finish_update`) and A's cut already stands.
  If B has speech, the request becomes B's own manual end, so B shows as its
  own card instead of hiding under the word floor.
- **The window-tail cut alone** runs as before when:
  - no capture qualifies;
  - two captures tie exactly on `finished_at` (a 404 here would read as "already
    closed" to the app and cut nothing);
  - the scan is full and its oldest row is still newer than the window;
  - `_finish_capture` declines or finds the capture already empty. It writes
    nothing in those cases.

A qualifying capture is strictly newer than the window, so the tail cut's rule
that an older overlapping source never cuts through visible speech still holds.

## Retries

A retry never cuts A twice. If the window's tail already carries this window's
Finish (the stored-both case), the tail path answers (`already_cut` /
`already_requested`) and B is not touched again.

Otherwise, a newer capture that an earlier recording-scoped Finish marked
(`v3_finish_no_pointer_recording`) answers through `_finish_capture`, even after
a window claimed it between taps:

- If the marked capture can no longer answer (private, locked, deleted,
  discarded, merged, a partial archive, a failed upload, or `_finish_capture`
  declines, for example an unavailable ledger), the window tail is cut. The app
  reads a 404 as "already closed", so a 404 would leave A uncut.
- If that Finish resolved empty (`v3_manual_end_requested` false, no cut), the
  mark no longer holds the Finish: the window's speech is the last speech again,
  so the next tap cuts the tail.
- Unmarked captures older than an active mark do not qualify; the person
  already finished after their speech.
- If B joined A's window in between, B is the tail and the window-tail path
  answers.

## Reads and writes

Reads per live-window Finish with the switch on: one query, at most 8 documents
(one billed read when it is empty). When a capture qualifies, add the
account-deletion marker. In the stored-both case, add B's ledger read; A's ledger
read is the one the tail cut always made. Writes: at most one recording per
transaction, except the stored-both case, which writes two (A's cut and B's
request). With the switch off, nothing extra is read and the transaction is
exactly the tail cut.

## Metrics and switch

Every outcome of a Finish that found a newer capture is counted with a `newer_`
prefix in `omi_conversations_v3_finish_no_pointer_total`, apart from the tail
path's outcomes. All of these labels are pre-initialised:

- Moved to the capture: `newer_recording_cut`, `newer_recording_requested`,
  `newer_already_cut`, `newer_already_requested`, `newer_already_empty`,
  `newer_resolved_empty`, `newer_consumed`, `newer_recording_ineligible`,
  `newer_batch_unavailable`, `newer_batch_disabled`.
- Stored both, by the tail's outcome: `newer_dual_cut`, `newer_dual_requested`,
  `newer_dual_consumed`, `newer_dual_already_cut`, `newer_dual_already_requested`,
  `newer_dual_already_empty`, `newer_dual_resolved_empty`.

`CONVERSATIONS_V3_FINISH_NEWER_CAPTURE=off` restores the window-tail cut and
skips the scan. Cuts already stored stay.

## Lab

The pipeline lab's batch lane now writes `has_content` with
`server_batch_audio_end` at seal, as production's audio custody does in the same
transaction.
[Pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
