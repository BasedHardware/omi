# Device sessions wire

Account-scoped capture ingest for the Cloudflare backend-worker. Bytes are stored in the bound `ATTACHMENTS` R2 bucket. Metadata is stored in D1. The route does not transcribe, OCR, or invent conversation rows.

Auth matches every other `/v1/*` route: `Authorization: Bearer` plus a validated `x-omi-client-id` partition. The client does not supply an account id in the body.

| Route | Verb | Success | Purpose |
| `/v1/device-sessions` | `POST` | `201` JSON | Open one capture session and receive its id. |
| `/v1/device-sessions/:id/audio` | `POST` | `200` JSON | Append one codec-payload chunk to the session object prefix. |
| `/v1/device-sessions/:id/complete` | `POST` | `200` JSON | Mark the session complete. Idempotent once complete. |
| `/v1/device-sessions` | `GET` | `200` JSON | List this account's sessions. Metadata only; no object bytes. |

Missing `DB` or `ATTACHMENTS` is `503 service_unavailable`. A session owned by another `x-omi-client-id` is `404`. Responses never include a transcript field.
