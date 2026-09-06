# Device sessions wire

Account-scoped capture ingest for the Cloudflare backend-worker. Bytes are stored in the bound `ATTACHMENTS` R2 bucket and metadata in D1. Verified completion queues transcription; processing results become private conversation records.

Auth matches every other `/v1/*` route: a verified Firebase bearer owns its Firebase account partition; the shared staging bearer may select a validated non-Firebase `x-omi-client-id`. The client cannot supply an account id in the body.

| Route | Verb | Success | Purpose |
| --- | --- | --- | --- |
| `/v1/device-sessions` | `POST` | `201` JSON | Open or replay a capture session and receive its server id. |
| `/v1/device-sessions/:id/audio` | `POST` | `200` JSON | Append or retry a packet by stable index. |
| `/v1/device-sessions/:id/complete` | `POST` | `200` JSON | Complete only when every claimed packet is stored. Idempotent once complete. |
| `/v1/device-sessions` | `GET` | `200` JSON | List this account's session metadata. |
| `/v1/device-sessions/:id/transcript` | `GET` | `200` JSON | Read this account's processing state and full transcript. |

Creation requests require a native-minted lowercase UUID v4 `captureId` plus device ID, optional device name and codec. Retrying the same capture ID and immutable metadata returns the same server session, including after completion. Reusing it with different metadata returns 409. Capture IDs are account-scoped; they do not choose the server session ID. Persist this identity with a future offline queue before sending creation requests.

Audio requests contain `{ "chunkIndex": 0, "bytesBase64": "..." }`. Indexes start at zero and are contiguous. Advance only after acknowledgment. Retrying an existing index with identical bytes succeeds without incrementing counters, including after completion; different bytes at the same index return 409. A new packet cannot be added to a completed session. Storage failures leave the reserved packet pending so identical retries can recover it. The successful-upload counter changes only once per packet and prevents completion while storage is pending. Requests without an index are rejected; all in-tree clients send it.

The maximum session input is 8 MiB across 65,536 packets. A packet is at most 1 MiB. Retrying does not consume this budget twice. Historical packets without the retry ledger cannot be overwritten or claimed by a new retry.

Missing `DB` or `ATTACHMENTS` is `503 service_unavailable`. An unknown or differently owned session is `404`. Session metadata responses do not include transcript text. The separate transcript response is `{ transcription: { sessionId, state, text, segments, language, discardedLeadingPackets, errorCode, updatedAt } }`; state is queued, running, completed, or failed. Missing processing records return 404, including historical completed sessions that were not queued retroactively.
