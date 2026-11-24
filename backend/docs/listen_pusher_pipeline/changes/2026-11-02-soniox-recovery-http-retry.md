# Soniox recovery retries and closed failure diagnostics

Soniox recovery used to settle a second-recognizer error immediately. After
Modulate returned empty, the shared recovery failure still read `empty_asr`,
and the Soniox HTTP class was lost. A transient upload, status-poll or
transcript-read failure could therefore leave audio held after one request.

Both recovery adapters now allow at most three HTTP attempts with 1s / 2s
backoff, inside the existing 120s overall deadline. They retry 429 responses,
and retry 5xx / transport timeouts for upload and reads. Polls and transcript
reads keep the same transcription id. Async waits hold neither the HTTP
semaphore nor a shared executor slot.

A paid transcription POST is retried only after an explicit 429 refusal.
Transport loss or a 5xx from that POST is uncertain and stays held; an accepted
transcription is never resubmitted. Authentication, credit refusal, malformed
responses and provider-reported terminal job errors do not trigger a new paid
transcription. Exhaustion remains an error receipt with retained speech/audio,
never evidence of an independent empty response. Spent recovery intents still
require a separately approved operator route; this change does not redrive them.

`soniox_batch_request_failure` records only a closed operation/kind, bounded
numeric HTTP status, attempt and retry boolean. `soniox_batch_failure` retains
the final kind/status and whether a paid transcription may exist. Neither log
includes provider bodies, resource ids, paths, audio, user ids or credentials.
The synchronous adapter now preserves the same typed error fields as async.

This ships on with no new flag, environment variable, workflow or data change.
Rollback is to redeploy the previous backend source. Backend-sync (including
the recovery Cloud Tasks handler) needs the release; this is not a worker fix.
The live WebSocket adapter is unchanged. Source contract:
[independent recovery](../../listen_pusher_pipeline.mdx#independent-language-guarded-batch-recovery).

Synthetic HTTP and recovery tests cover eventual success, bounded exhaustion,
credit refusal, uncertain paid submission and retention after failure. They do
not prove vendor health, credit balance or delivery of the three historical
held units. Those require separate runtime evidence and operator authorization.
