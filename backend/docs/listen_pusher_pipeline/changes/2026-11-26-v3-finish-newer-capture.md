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
documents). A capture qualifies when it is a sealed Listen capture that ended
after the window's `finished_at`, is not one of the window's sources, and
passes `_capture_ineligible` like the recording fallback: sealed within
`RECENT_FINISH_AGE`, unclaimed, not marked for another window, not private,
deleted, discarded, locked, merged, a partial archive or a failed upload. One
such capture takes the recording-scoped cut through `_finish_capture`. That is
the same write, batch request and empty resolution the fallback uses, and the
response names the capture. When `_finish_capture` declines (for example a
silent live-lane capture with no landed speech), the window-tail cut runs as
before; it never writes before declining. The tail cut keeps its own rule that
an older overlapping source never cuts through visible speech: a qualifying
capture is strictly newer than the window.

- Two or more qualifying captures: `recording_ambiguous`, nothing written,
  as the unnamed fallback does.
- Retry: a newer capture that an earlier recording-scoped Finish marked
  (`v3_finish_no_pointer_recording`) answers the retry through `_finish_capture`
  (`already_cut`, `already_requested`, `already_empty`, `consumed`), even after
  a window claimed it between taps. Unmarked captures older than that mark do
  not qualify. If B joined A's window in between, B is the tail and the
  window-tail path answers. A is never cut as well.
- A full scan whose oldest row is still newer than the window keeps the tail
  cut and logs, rather than guessing.

Reads per live-window Finish with the switch on: one query, at most 8 documents
(one billed read when it is empty). A batch capture that moves the cut swaps the
tail's ledger read for its own. With the switch off, nothing extra is read.
Writes are unchanged: at most one recording per transaction.

New `omi_conversations_v3_finish_no_pointer_total` outcomes are
`newer_recording_cut` and `newer_recording_requested`. Retries and declines use
the existing labels. `CONVERSATIONS_V3_FINISH_NEWER_CAPTURE=off` restores the
window-tail cut and skips the scan. Cuts already stored stay.
[Pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
