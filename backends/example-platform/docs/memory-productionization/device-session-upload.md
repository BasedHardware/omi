# Indexed device capture

The portable device upload adapter implements the React Native recording wire
against the existing PostgreSQL Listen capture authority. Firebase identity is
resolved through the existing account/application binding and the exact
`listen.capture.write` grant. An ID token alone does not grant capture access.
Every database operation rechecks current account, credential, grant, lifecycle,
activated epoch, and released database generation in the sealed transaction.
Upload context expiry is checked again against the database clock before commit,
so a delayed write rolls back rather than committing after its authority expires.

| Request | Result |
| --- | --- |
| `POST /v1/device-sessions` with `captureId`, `deviceId`, optional `deviceName`, and numeric `codec` | 201 `{session}`; UUID-v4 `captureId` is stable client retry identity, and the server chooses the session ID |
| `POST /v1/device-sessions/:id/audio` with `chunkIndex` and `bytesBase64` | 200 `{session}` after the exact indexed bytes and counters commit together |
| `POST /v1/device-sessions/:id/complete` | 200 `{session}` after upload completion commits; exact replay retains the original completion timestamp |
| `GET /v1/device-sessions/:id` | 200 `{session}`, or 404 for an unknown session in the authenticated account |

Changed immutable creation fields, different bytes at an existing index, skipped
indices, and new bytes after completion return 409. Matching chunk replay remains
valid after completion. Limits match the existing client/Worker protocol: 1 MiB
per chunk, 8 MiB per recording, and 65,536 contiguous zero-based chunks. Invalid
JSON, noncanonical base64, substituted transcript fields, and invalid UUIDs fail
before mutation. Errors retain the client `{error:{code}}` envelope. Timestamps
are Unix seconds.

Migration 0048 attaches immutable device metadata and bytea chunks to canonical
`listen_capture_sessions`. Application credentials receive fixed operations,
not direct table access. Raw audio is stored in PostgreSQL rather than external
object storage, so no separately acknowledged object write can race completion.
PostgreSQL storage encryption, backups, and operator access remain deployment
responsibilities. Both added tables participate in the existing `staged_results`
account-deletion surface and its dependency-ordered cleanup.

`session.state = complete` means all accepted upload bytes are durably sealed.
It does not mean transcription, conversation processing, or memory formation has
completed. The canonical Listen session remains available for genuine transcript
segments and its existing finalizer; this adapter never writes transcript text or
fabricates a formation result. A deployed transcription consumer and its existing
capture authority must be composed before claiming end-to-end speech processing.
The Worker already has a real Whisper inference port and a pure BLE WAV/Ogg
assembler; those are separate from its Cloudflare-specific storage/claim loop.

The listener must accept the encoded 1-MiB audio request (up to 1,398,256 bytes);
the route independently bounds its streamed JSON body and propagates cancellation
to the serializable database operation. Runtime composition must retain the same
readiness, concurrency, and shutdown gates as the other deployed routes.

The current client sends one HTTP request per BLE packet and awaits its indexed
acknowledgment. Each request rechecks Firebase/account authorization and commits a
PostgreSQL transaction. Durable retry tests do not prove sustained device upload
throughput across network latency; queue growth and drain require a real-device
measurement. Future batching must preserve every packet boundary and index,
because the audio assembler consumes distinct BLE packets rather than a joined
byte stream. No packet batching is implemented in this increment.
