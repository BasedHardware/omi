# A user finish of an audio-only recording keeps its manual end

SCA-3024. Mobile captures are server-batch-only: when the user taps Finish or
double-taps the pendant, the recording has audio and no transcript. The
finalization worker closes it through `complete_server_batch_capture` and never
reaches the transcript path that calls `changed(manual_end=True)`. The batch
transcript then landed as ordinary speech. The window waited for five minutes of
silence and the lock delay, stayed live while the pendant kept recording, and a
short window was hidden from Home because it carried no manual end.

The terminal transaction now stores `v3_manual_end` on the recording when the
finalization job's trigger is `client_finalize`. It adds one field to an existing
write and no read. If the transcript landed before the commit, the same write
re-arms `v3_pending` and a reconcile is enqueued after the commit.

Rollback: `CONVERSATIONS_V3_BATCH_MANUAL_END=off` on `backend`.

Readback: `omi_conversations_v3_batch_manual_end_total` rises with manual finishes,
and the recordings it counts produce a derived row with `manual_end` set.
