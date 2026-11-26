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

Now, when Finish resolves to a live window (empty body or the named live
window), the `request_finish` transaction also runs the existing recent-source
scan (`_recent_finish_sources`, newest first, at most `RECENT_FINISH_LIMIT` = 8
documents). A capture qualifies when it:

- is a sealed Listen capture that ended after the window's `finished_at`;
- is not one of the window's sources;
- carries `has_content` (a projection that landed empty clears it);
- passes `_capture_ineligible` like the recording fallback: sealed within
  `RECENT_FINISH_AGE`, unclaimed, not marked for another window, and not
  private, deleted, discarded, locked, merged, a partial archive or a failed
  upload.

The newest qualifying capture wins, as in `_latest_capture`. After the same
account-deletion check as the recording fallback, it takes the recording-scoped
cut through `_finish_capture`: the same write, batch request and empty
resolution the fallback uses, and the response names the capture.

The window-tail cut runs as before when:

- no capture qualifies;
- two captures tie exactly on `finished_at` (a 404 here would read as "already
  closed" to the app and cut nothing);
- the scan is full and its oldest row is still newer than the window;
- `_finish_capture` declines or finds the capture already empty (a silent
  live-lane capture, or a batch record that completed as silence). It writes
  nothing in those cases.

A qualifying capture is strictly newer than the window, so the tail cut's rule
that an older overlapping source never cuts through visible speech still holds.

Retries: a newer capture that an earlier recording-scoped Finish marked
(`v3_finish_no_pointer_recording`) answers the retry through `_finish_capture`,
even after a window claimed it between taps. A is never cut as well.

- If the marked capture has since become private, locked, deleted, discarded,
  merged, a partial archive or a failed upload, the retry writes nothing
  (`newer_recording_ineligible`).
- If that Finish resolved empty (`v3_manual_end_requested` false, no cut), the
  mark no longer holds the Finish: the window's speech is the last speech
  again, so the tail is cut.
- Unmarked captures older than an active mark do not qualify.
- If B joined A's window in between, B is the tail and the window-tail path
  answers.

Known gap: for a server-batch capture, `has_content` comes from audio custody
(`note_server_batch_audio`) once audio samples commit, not from speech. A
pending batch capture that holds only silence therefore still takes the first
Finish. When its whole record completes as silence, `_v3_finish_update` clears
the request and A's window closes on its silence timer instead of the cut. A
second tap then cuts A (the resolved-empty rule above). Cutting A at that
completion would need a fallback-window write in the batch projection
transaction; that is a separate design.

Reads per live-window Finish with the switch on: one query, at most 8 documents
(one billed read when it is empty). A Finish that moves to a newer capture also
reads the account-deletion marker. A batch capture swaps the tail's ledger read
for its own. With the switch off, nothing extra is read. Writes are unchanged:
at most one recording per transaction.

Every outcome of the moved Finish is counted with a `newer_` prefix in
`omi_conversations_v3_finish_no_pointer_total`, apart from the tail path's
outcomes. The labels are `newer_recording_cut`, `newer_recording_requested`,
`newer_already_cut`, `newer_already_requested`, `newer_already_empty`,
`newer_resolved_empty`, `newer_consumed`, `newer_recording_ineligible`,
`newer_batch_unavailable` and `newer_batch_disabled`; all are pre-initialised.
`CONVERSATIONS_V3_FINISH_NEWER_CAPTURE=off` restores the window-tail cut and
skips the scan. Cuts already stored stay.

The pipeline lab's batch lane now writes `has_content` with
`server_batch_audio_end` at seal, as production's audio custody does in the same
transaction.
[Pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
