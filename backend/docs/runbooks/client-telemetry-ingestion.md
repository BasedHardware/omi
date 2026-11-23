# Client telemetry ingestion

Collector for `POST /v1/telemetry/client/batches` and admin
`GET /v1/telemetry/client/aggregates`. The frozen contract is
`../telemetry-transport-contract.md`. This runbook is operational
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

## Device Signals migration (SCA-3922)

The `device_signal` observation adds a closed event name and, where relevant,
the predicates `over_age` (>86400 seconds), `over_count` (>720 WALs), and the
wedge block reason (`count_cap`, `disk_reserve`, `missing`, or `other`). A
missing block reason is its own value. The existing desktop `fallback` family
also contributes to the fallback count. No hardware identifiers or raw diagnostic
properties are used as Prometheus labels.

The distinct unit is the authenticated owner, matching the identified-account
population used for PostHog comparison. An owner can contribute once per signal
per UTC event hour, even across installs or retries. Each update shares the
collector's Firestore transaction. Before enrolling clients, configure Firestore
timestamp TTL on `expires_at` for collection groups
`client_telemetry_signal_memberships` (26 hours after the bucket starts) and
`client_telemetry_signal_hour_shards` (nine days after the bucket date).
These settings are part of the Release handoff and must be verified there.

1. Under SCA-3921, record the reviewed revisions, prior settings and stop bounds
   and obtain scoped `RELEASE_GO`. Deploy the accepting backend before any new
   clients. Enable `CLIENT_TELEMETRY_DEVICE_SIGNALS_EXPORT=on` through the reviewed
   backend Cloud Run runtime manifest, with its existing GMP sidecar. The local
   Prometheus datasource receives these gauges through the Cloud Monitoring
   exporter. Confirm Firestore transaction retry and scrape cost at canary scale.
2. Enable mobile telemetry transport on the canary build with
   `OMI_CLIENT_TELEMETRY_MIGRATION=true` and the desktop
   `client_telemetry_transport_shadow` flag for the approved cohort. Keep both
   retirement flags off. Foreground mobile clients emit at most one heartbeat
   per owner and client process per UTC hour. The collector deduplicates across
   clients. Review the reporting-owner count by hour against expected rollout
   coverage. One positive heartbeat only proves some intake.
3. Apply the eight `Device Signals Prometheus` rules via the approved Grafana
   provisioning path. Their UIDs end in `-prom` and use the existing
   `omi-tier-silent` mute. Keep the original eight active. Record the UTC hour
   from `omi_client_device_signal_hour_start_seconds`, intake from
   `omi_client_device_signal_reporting_owners`, and history from
   `omi_client_device_signal_baseline_hours`. Confirm that no heartbeat or an
   unavailable source yields No Data and that a covered zero stays Normal.
4. For seven closed UTC days, compare both sources for the same cohort and
   closed UTC windows. The exporter publishes each last completed hour after
   a 10-minute delivery grace and allows up to five more minutes of source
   propagation before the previous bucket is rejected. The original alerts
   still evaluate rolling hours. For comparison, run their HogQL predicates
   against the exporter's exact UTC window, with the bridge's current sampling
   weights. Record timing and sampling differences, coverage gaps, late delivery,
   and any discrepant firing. The baseline is the median of positive, covered
   buckets in the preceding 167 hours. Verify all eight rules with controlled
   firing cases and require complete coverage before retirement.
5. After the accepted receipt, promote the Prometheus rules and retire the old
   Grafana UIDs through reviewed configuration. Coordinate the route change with
   SCA-3665 and PR #26119. Before dropping routes, confirm the affected admin
   readers are switched or have explicit disposition. Hourly counts alone do
   not replace the rich battery, device-health, and desktop-health readers.
   T3 applies the approved PostHog configuration with a saved rollback. Verify
   zero **new** accepted volume for each retired event over a post-cutover
   window alongside the corresponding PostHog billing readback.

Before retirement, rollback pauses the Prometheus shadow group and restores
the exporter and client settings while the original alerts keep evaluating.
After retirement, restore the saved PostHog routing and original alert
configuration before rolling back the collector. Escalate before the bridge
waiver expires on 2026-12-07 if the live checks or reader dependencies are
still open.
