# Indexed device capture

The portable device upload adapter implements the React Native recording wire
against the existing PostgreSQL Listen capture authority. Firebase identity is
resolved through the existing account/application binding and the exact
`listen.capture.write` grant. An ID token alone does not grant capture access.
Every database operation rechecks current account, credential, grant, lifecycle,
activated epoch, and released database generation in the sealed transaction.
Upload context expiry is checked again against the database clock before commit,
so a delayed write rolls back rather than committing after its authority expires.

Before the first captured byte, native recording obtains `GET /v1/device-sessions/ownership`
using its current authenticated backend transport. The response is
`{ownership:{ownerKey,receipt}}`. The opaque owner key identifies the actual canonical
account and authority epoch; it is not derived from the Firebase UID. Native stores
this response with its capture UUID, configured backend origin and login generation,
and supplies `X-Omi-Capture-Ownership` from that journal on every subsequent session
mutation. JavaScript must not select or replace the owner or receipt. Read-only session
and transcript requests use current account authorization without a receipt or an ownership
preflight; historical reads do not require a configured ownership signing key.

The receipt is a purpose-separated HMAC constraint under the configured codec key,
not an authorization grant. Every request still verifies current Firebase identity,
binding and exact capture grant. A valid receipt for another account or epoch returns
409 `capture_ownership_changed` on mutations; malformed or missing mutation receipts return 400. Receipts
have no authorization lifetime and contain no credentials. Recovery first obtains
fresh ownership and compares the stable owner key before refreshing the signature;
signing-key rotation therefore does not require retagging a journal. An owner-key or
backend-origin mismatch must quarantine the journal rather than replay it elsewhere.

Migration 0051 binds new capture rows to their actual creation epoch. Even a fresh
receipt cannot resume a capture created under an earlier epoch. Historical rows
without a recorded creation epoch remain available to authorized read-only queries,
but replay, uploads, completion and new transcription fail with the explicit ownership
recovery error. No historical epoch is inferred or backfilled. Receipt refresh is not
part of capture idempotency: a lost initial acknowledgement still replays the original
capture UUID and immutable device fields exactly once within its original ownership.

The Worker currently has no canonical account-epoch authority and returns 503
nested `{error:{code:"capture_ownership_unavailable",retryable:false,action:"none"}}`
for this endpoint. Its existing D1/R2 routes and data remain available, but
receipt-backed native journaling cannot silently fall back to them. A paired canonical capture and conversation migration is still required there.
Production without a configured ownership signing key uses that same nested
non-retryable 503 and omits `retry-after`; it still does not invent a receipt.
Authorize and identity-verification outages stay `{error:{code:"unavailable"}}`
with `retry-after: 1`. Historical session and transcript GETs still do not require
the signing key.
The production memory shell mounts `GET /v1/device-sessions/ownership` as its own
door so `ownership` is not treated as a UUID session id.

| Request | Result |
| --- | --- |
| `GET /v1/device-sessions/ownership` | 200 `{ownership:{ownerKey,receipt}}` after `listen.capture.write`; 401/403 for missing admission; 503 nested `{error:{code:"capture_ownership_unavailable",retryable:false,action:"none"}}` without a signing key and without `retry-after`. Authorize or identity-verification 503s stay `{error:{code:"unavailable"}}` with `retry-after: 1`. |
| `POST /v1/device-sessions` with `captureId`, `deviceId`, optional `deviceName` and `capturedAtMs`, and numeric `codec` | 201 `{session}`; UUID-v4 `captureId` is stable client retry identity, and the server chooses the session ID |
| `POST /v1/device-sessions/:id/audio` with `{chunks:[{chunkIndex,bytesBase64},...]}` | 200 `{session}` after every indexed packet in the batch is durable; exact full or prefix replay does not increment counters twice |
| `POST /v1/device-sessions/:id/complete` | 200 `{session}` after upload completion commits; exact replay retains the original completion timestamp |
| `GET /v1/device-sessions/:id` | 200 `{session}`, or 404 for an unknown session in the authenticated account |
| Bodyless `POST /v1/device-sessions/:id/transcribe` | 202 `{transcription}` while queued/running; 200 for completed/failed; requires a fresh authenticated request and sealed upload |
| `GET /v1/device-sessions/:id/transcript` | 200 `{transcription}` showing durable processing status without starting paid work |

Changed immutable creation fields, different bytes at an existing index, skipped
indices, and new bytes after completion return 409. Matching chunk replay remains
valid after completion. A batch contains 1–128 consecutive packets, at most 1 MiB
of decoded audio in total, and at most 2 MiB of encoded JSON. The session retains
the 8-MiB limit and 65,536 contiguous zero-based packet indices. Invalid
JSON, noncanonical base64, substituted transcript fields, and invalid UUIDs fail
before mutation. Errors retain the client `{error:{code}}` envelope. Session `startedAt` and `endedAt`, and transcript `updatedAt`, are Unix
milliseconds. Migration 0054 corrects the portable session JSON units to match the
existing Worker and app wire; PostgreSQL timestamps and processing durations are unchanged.

Migration 0054 and Worker migration `0009_device_capture_time.sql` store optional
`capturedAtMs`: the native app receipt time of the first audio packet, as a safe
integer from 0 through 8,640,000,000,000,000 Unix milliseconds. Null, fractional,
and out-of-range request values are rejected. Historical or omitted values remain
unknown and are omitted from session responses; neither recovery nor migration
substitutes the current time. Presence and value are immutable capture metadata:
replaying the same capture ID with a changed or newly omitted timestamp returns 409.
Conversation projections expose the optional value without changing ordering,
pagination, server start/end times, decoded duration, or billing. This is display
provenance, not trusted device chronology or an authorization input.

Migration 0048 attaches immutable device metadata and bytea chunks to canonical
`listen_capture_sessions`. Application credentials receive fixed operations,
not direct table access. Raw audio is stored in PostgreSQL rather than external
object storage, so no separately acknowledged object write can race completion.
PostgreSQL storage encryption, backups, and operator access remain deployment
responsibilities. Both added tables participate in the existing `staged_results`
account-deletion surface and its dependency-ordered cleanup.

`session.state = complete` means all accepted upload bytes are durably sealed.
It does not mean transcription, conversation processing, or memory formation has
completed. The portable transcription path uses the shared BLE WAV/Ogg assembler
and an explicitly configured Deepgram prerecorded source. The Worker accepts the
same explicit request using its existing Whisper queue and lease. Missing provider
configuration returns 503. Neither path treats a completed upload as recognized
speech.

Migration 0049 stores the portable transcription claim and validated provider
result under the same account/session ownership and deletion surface. A 180-second
lease permits one provider attempt, bounded to 120 seconds. Retryable provider
failures wait 30 seconds; at most five attempts are accepted. A stale lease cannot
replace another attempt's result. Successful provider text is persisted before
canonical publication; interruption after persistence resumes from that exact
result without invoking the provider again. Publication uses batches of up to 128
canonical segments and the existing atomic finalizer/outbox. Segment IDs and
timestamps remain stable on replay. Speech is not attributed to the account owner
without speaker evidence (`is_user` remains false). This seals a genuine formation
input; it does not claim downstream memory processing has run.

Validation enforces the existing canonical limit of 1,000,000 UTF-8 text bytes as
well as the code-unit and segment limits before saving any provider result. NUL
and unpaired UTF-16 surrogates are rejected because PostgreSQL cannot persist
them. Text is never silently truncated to fit.

The request reauthorizes before each storage/publication boundary, and each
transaction checks the database clock before committing. No Firebase bearer is
stored for a background worker. Expired tokens, revoked grants, account changes,
and cancellation stop processing. Once a complete valid paid response has arrived,
its durable save has a separate ten-second deadline and still requires fresh
same-account Firebase authorization and current database authority. A client
disconnect therefore does not discard an already received response when that
bounded save succeeds. Original cancellation stops canonical publication; a later
authenticated request may resume it. If authorization expires after the provider
has charged but before its result can be stored, another provider call may be
necessary; exact paid-call deduplication is not guaranteed across that boundary.
There is no autonomous post-signout transcription worker in this composition.
The app explicitly starts processing after upload and may resume with a fresh
credential. Successful no-speech returns `completed`, empty text/segments, and no
error, without inventing a canonical transcript or formation.

The provider uses the service-owned `OMI_TRANSCRIPTION_API_KEY`, explicit
`OMI_TRANSCRIPTION_MODEL`, and Deepgram's `mip_opt_out=true`. Raw WAV/Ogg is sent
only to the fixed HTTPS prerecorded endpoint; errors expose sanitized codes.
[Deepgram prerecorded API](https://developers.deepgram.com/reference/speech-to-text/listen-pre-recorded)
defines the timed utterance response. The model adapter and container tests do not
by themselves prove live provider credentials, physical-device audio, or deployed
end-to-end transcription.

The listener must accept the encoded batch request (up to 2,097,152 bytes);
the route independently bounds its streamed JSON body and propagates cancellation
to the serializable database operation. Runtime composition must retain the same
readiness, concurrency, and shutdown gates as the other deployed routes.

Migration 0052 accepts each portable packet batch in one authorized transaction;
an error in a later packet rolls back earlier packets and counters in that batch.
Worker claims every batch index atomically before writing its separate R2 objects.
Partial R2 failure leaves the claims pending, blocks completion, and permits exact
retry; no different bytes can replace a claimed index. Both paths preserve each
original BLE packet for the shared audio assembler. The client retains its batch
until the server response and native journal acknowledgment succeed. Batching
reduces per-packet HTTP and authorization overhead, but sustained queue drain and
recording throughput still require measurement with real hardware and network latency.
