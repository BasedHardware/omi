# A user finish inside the first archive window is admitted

Mobile captures are server-batch-only. The listen session marks
`server_batch_audio_received` at the first audio frame and writes `has_content`
only when a 60-second archive window commits. A Finish, End, Wrap Up or pendant
double-tap before that commit reached finalization admission with no transcript
and no content marker, was answered `no_content` and returned the recording
unchanged. The recording then stayed open until the socket closed or the quiet
timer fired. A pendant keeps streaming, so the app showed Processing with no
result.

Production readback, 2026-11-24, one test account, synthetic speech over
`/v4/listen` followed by `POST /v1/conversations` with the socket held open:

| Recording | Answer to the finish | Finalization job |
| --- | --- | --- |
| 37 s | `in_progress` (ignored) | `capture_end`, created only when the socket closed 20 s later |
| 77 s | `processing` | `client_finalize`, created with the request |

For the 77 s recording the session rolled over at once, committed the tail in
2.8 s and the record sealed 4.4 s after the request. Those rows carried no
reconnect producer: the serving listen image predates
`LISTEN_BATCH_RECONNECT_ENABLED`.

## The change

- Admission (`_create_or_get_finalization_intent_txn`): a `client_finalize` of
  a batch-owned row with `server_batch_audio_received` true, no committed
  audio, an open archive, no reconnect producer and at least 10 seconds of age
  is admitted. Every other trigger, and every other row, keeps `no_content`.
- Worker (`finalize_persisted_conversation`): for that job it re-reads the row
  every 0.5 s for at most 30 s until the session has committed the audio, then
  registers the recording and closes the capture as before. A row that never
  gains audio keeps the existing `ServerBatchArchiveNotClosed` retry.

No new write: the session's existing rollover commit supplies the audio bounds.
At most 60 extra row reads per early finish.

## Rollout and rollback

It rolls out with the fast first transcript: `CONVERSATIONS_V3_FAST_FINISH`
(default `cohort`, the `v3-fast-finish` runtime rollout cohort; `on` admits
every owner; `off` stops it). `CONVERSATIONS_V3_BATCH_MANUAL_END=off` also
stops it. A job admitted before either switch still completes.

## Known limits, to settle before `on`

- A row with a reconnect producer is not admitted early.
  `note_server_batch_audio` and `close_server_batch_audio` refuse a producer
  row once its status leaves `in_progress`, so the session could not commit the
  audio. When the listen image ships with `LISTEN_BATCH_RECONNECT_ENABLED`,
  mobile rows carry a producer and this change stops applying to them until
  that fence lets the owning token write while the row is `processing`. The
  same fence would then refuse the tail of a finish after the first window.
- The session commits with the next frame after the rollover, at the 60-second
  window or at teardown; it does not commit on seeing the row leave
  `in_progress` (`PUSHER_RECORD_CLOSE_NOTIFY_ENABLED` is off). If frames stop
  while the socket stays open, the audio commits only at teardown and the job
  spends its retry budget meanwhile.
- A `POST /v1/conversations` sent again more than 10 seconds after a finish
  can cut the successor recording.
