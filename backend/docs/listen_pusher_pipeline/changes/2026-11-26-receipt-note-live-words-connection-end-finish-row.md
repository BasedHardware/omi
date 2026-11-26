# Receipt wait reads only finished jobs; live words keep their connection; a stored End finds its row

Three follow-ups to `2026-11-25-reliability-rollouts-per-account.md`. Each sits behind a per-account
flag of that note and changes nothing for an account the flag is off for.

## `receipt_finished_note` (new flag, with `receipt_long_poll`)

As first built, `POST /v2/sync-local-files/receipts/wait` re-read every listed job when a wait started,
on every wake and when it expired after 20 s. On a test phone that was several job-status reads per
wait, nearly all for uploads that were not finished, which is several times the reads of the status
polling the wait replaces.

Now a finished job leaves a note in Redis (`sync_receipt_done:<uid>:<job>`, one hour) before its wake
is published (`database/sync_jobs.py` `leave_receipt_note`, also from the batch projection). The wait
makes one `MGET` when it starts and reads job state only for a job a note or a wake names; an expired
wait answers empty without reading anything, and a noted job whose state is not final goes back as
`fallback`. The app status-polls a job the wait covers once it is a minute old, at most once a minute,
as a backstop. On the test phone this brought the reads from waits down to one per finished upload.

Not covered: a failed upload leaves no note and no wake (the backstop poll finds it). A lost note,
Redis being down and the phone in the background are not tested.

Admit an account to `receipt_long_poll` only together with this flag.

## `vendor_recognizer_on_opened_app`: silence keeps the connection

A `/v4/live-words` connection used to close after 20 s without audio and the phone opened a new one on
the next audio. A pendant sends nothing while it is quiet, so the phone reconnected after every pause,
and the listen service counts new connections per signed-in user, shared with the capture connection.

Now only the provider stream is closed after 20 s without audio (it gets 3 s to deliver its last
words) and the next audio dials a new one on the same connection. Lines stay timed in seconds of audio
from the connection's first frame. A lost stream is replaced the same way; three failures in a row
without a word still end the connection, which otherwise closes after 10 minutes without audio.

Before a wide ramp: the load balancer needs a path rule for `/v4/live-words` (without it the path is
served by the main backend service), the display stream has no plan-allowance check, and the server's
one-connection-per-install map is per process.

## `end_open_conversation`: a stored End finds its conversation

When End is pressed before the server has a conversation for the speech since the previous End, the
End is answered `X-Omi-End-Accepted: pending`. The app kept its Processing row until its 20-minute
deadline, because the row could only be handed to a conversation that named the listening session's
recording, and on the phone-file route none does.

The conversation an End closed already carries that End's instant (`v3_manual_cut_at`). Conversation
reads now serve it (hidden from the published schema, absent unless the flag wrote it), and the app
matches its row to the conversation whose cut equals the End time it sent. A pending acceptance keeps
the 2-minute expiry, which clears the row and makes Home read its list once.

Limits: the 2-minute removal (no speech before the End) is covered by tests only. When the server
replaces an implausible phone End time with its own, nothing matches and the row goes at 2 minutes.

## Rollout and rollback

No rule exists for any of these flags at deploy. Rollback is deactivating the rule.

## Evidence

`tests/unit/test_reliability_experiment_receipt_finished_note.py`,
`tests/unit/test_reliability_experiment_live_words.py`,
`tests/unit/test_reliability_experiment_end_answer.py`, and in the app
`test/unit/receipt_waiter_test.dart`, `test/unit/sync_poll_storm_test.dart`,
`test/providers/end_stored_finish_row_test.dart`.
