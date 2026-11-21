# Batch capture joins its episode at admission

A `batch_live_v1` capture used to have no episode for the whole recording. The
server attached it only at audio close (`attach_closed_batch_capture`), so Home
painted it as its own row for the capture duration and then folded it into the
episode. Measured on one account: median 8.5 minutes, p90 50 minutes standalone.

Admission now attaches the capture to the live/adjacent episode immediately,
through the same fenced `attach_recorded` transaction the audio-close path uses.
The recorded start is known at admission; the end is not, so the member joins
with a one-second provisional window and `pending_transcription=True`. The
audio-close attach then writes the real end and never renews the pending
deadline. Home projects the member as "Transcribing…" from its first appearance.

Two admission boundaries call it, both metadata-only and fail-open:

- `routers/listen/conversations.py` after a `server_batch_only` conversation is
  created (the dominant class), off the request path.
- `routers/listen/preview_custody.py` when a local preview is promoted to batch
  custody.

If the completed window belongs to a different occasion than the admission
episode, the close path detaches the provisional member through the
recorded-timeline fence (`episode_timeline.detach_recorded`) before re-placing
it. Only a member that is still pending transcription, with no projected
transcript, and whose episode keeps at least one other member may be detached;
a transcribed member never moves and an episode is never left empty.

The admission call is scheduled in the background, so it may run after the
audio close committed. Its transaction therefore re-reads the member and
returns `closed` without writing once the archive is closed or a real
`server_batch_audio_end` exists; a replayed admission also treats that closed
membership as already placed. The close-time end and `state_version` are never
rewritten by the late task.

Kill switch: `EPISODE_BATCH_ADMISSION_ATTACH_ENABLED`, default on. Off restores
the pre-admission behaviour exactly: the capture stays standalone and joins at
audio close. `EPISODE_BATCH_CLOSE_ATTACH_ENABLED` still governs the close path.

New state and its exit: a provisionally attached member is bounded by the
existing `episode_transcription_deadline_at` (2h SLA) and the automatic
"Couldn't transcribe" terminal projection; the audio-close attach finalizes the
end, and the transcript projection clears the pending presentation. A failed
admission attach leaves the capture standalone and the finalize-time attach
remains the repair path.

Regression coverage: `tests/unit/test_episode_batch_audio_close.py` covers
admission attach, close finalize without deadline renewal, boundary move and
detach, the transcribed-member refusal, the kill switch, and retry idempotency.
No env, wire, payload, workflow, or production data changes. Server only; no app
release.
