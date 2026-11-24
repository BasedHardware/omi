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
2.8 s and the record sealed 4.4 s after the request.

## The change

- Admission (`_create_or_get_finalization_intent_txn`): a `client_finalize` of
  a batch-owned row with `server_batch_audio_received` true, no committed audio
  and an open archive is admitted. Every other trigger, and a row that has
  received no audio, keeps `no_content`.
- Worker (`finalize_persisted_conversation`): for that job it re-reads the row
  every 0.5 s for at most 30 s until the session has committed the audio, then
  registers the recording and closes the capture as before. A row that never
  gains audio keeps the existing `ServerBatchArchiveNotClosed` retry.

No new write: the session's existing rollover commit supplies the audio bounds.
At most 60 extra row reads per early finish.

Rollback: `CONVERSATIONS_V3_BATCH_MANUAL_END=off` on `backend` restores the
`no_content` answer for later finishes. A job admitted before the switch still
completes.
