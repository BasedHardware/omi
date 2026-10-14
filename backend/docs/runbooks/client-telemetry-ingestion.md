# Client telemetry ingestion

Collector for `POST /v1/telemetry/client/batches` and admin
`GET /v1/telemetry/client/aggregates`. The frozen contract is
`docs/finops/telemetry-transport-contract.md`. This runbook is operational
only. It does not enable transport, the admin reader, or PostHog retirement.

## Flags

| Env | Default | Effect of turning it on |
|---|---|---|
| `CLIENT_TELEMETRY_TRANSPORT` | `off` | Transport shadow gate. The collector accepts authenticated batches either way so a canary does not need a second backend deploy. |
| `CLIENT_TELEMETRY_READER` | `off` | Admin consumer may switch to this API. Independent of transport. |
| `CLIENT_TELEMETRY_RETIREMENT` | `off` | PostHog infrastructure events stay until a documented parity receipt. Independent of the reader. |

## What is durable

- Dedup key is `(authenticated owner, event_id)`, kept at least 48 hours. The same key with a different payload is HTTP 409 and does not increment counters.
- Raw observations are kept 30 days. UTC day aggregates are kept 90 days. Queries hide expired days even if a document is still physically present.
- Upload conservation, histograms and voice rows (physical and floating, with the authenticated actor id) are updated in the same transaction as the dedup claim.
- A UTC day is not a healthy empty feed until a rollup receipt seals it. Sealing is explicit. A recent accepted event does not seal the day.
- Store failures and responses over 50,000 rows return HTTP 503 (`telemetry_unavailable` or `telemetry_query_truncated`). They are not empty 200s.
- Per-owner limit is 10 batches per minute, counted in the same durable store. `Retry-After` is at most 60 seconds.

## Auth

- Batches use the existing Firebase bearer token. The account id is never taken from the body.
- Aggregates require `X-Admin-Key` equal to `ADMIN_KEY`, the same backend gate `fair_use_admin` and `feedback_admin` use. A user bearer token is HTTP 403. The admin proxy must call `verifyAdmin` and then attach the key server-side.

## Coverage the admin read does not invent

`channel_by_actor` is the existing admin actor/channel classification. The HTTP route does not have that map yet, so any read that contains voice rows is `partial`. A mismatch is dropped from `voice_rows` and the response stays partial. Generic metric rows keep the client-reported build channel. Do not infer a channel when the classification is missing.

## Drops and stale ingest

| Outcome | HTTP | Meaning |
|---|---|---|
| `invalid` | 422 | Unknown keys, bad enums, non-finite or negative numbers, future >5 minutes, older than 24 hours, or one bad observation. Nothing in the batch is stored. |
| `too_large` | 413 | Body over 128 KiB, rejected before JSON decode. A single observation over 4 KiB is 422. |
| `conflict` | 409 | Same owner and event id, different canonical content. Permanent. Counters stay as they were. |
| `rate_limited` | 429 | Eleventh batch in the current minute for that owner. |
| `unavailable` | 503 | Transaction or read failed. Do not draw the gap as zero. |
| `stale` | 200 partial | An unsealed day has had no accept for 15 minutes. Rows already stored are still returned. |

Process-local `omi_client_telemetry_ingest_events_total` is a pod signal only. Grafana for accepted volume must read the aggregate API or the `client_telemetry_days` documents. Existing server HTTP metrics stay in place beside this collector.

## Integration still open

- Lane 2 and Lane 3 own the client outbox and the shadow flag. This service does not change upload, capture, drain, or model pacing.
- Lane 4 owns rendered parity. Fixtures: `backend/tests/fixtures/client_telemetry/`.
- Actor/channel classification has to be passed into `query_is_stale` before a voice window can be `partial=false`.
- Live canary days, the 1% dedup receipt, and flag activation belong to the parent. They are not done here.
