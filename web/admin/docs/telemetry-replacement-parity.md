# Telemetry replacement parity receipt

Fixture evidence for the admin reliability reader and fallback triage. This is
not production parity.

Live seven-day canary comparison and the consumer switch are **pending**. The
parent owns that gate. Fixture equality does not prove it.

## Reader

- `GET /v1/telemetry/client/aggregates` is read server-side after `requireScope`,
  with `X-Admin-Key` and `X-Admin-User`. The browser token is not forwarded.
- `RELIABILITY_REPLACEMENT_READER` defaults off. It turns on only with the
  exact value `on` and a valid `RELIABILITY_REPLACEMENT_CUTOVER` UTC day.
- Population defaults to `physical_shortcut`. `RELIABILITY_REPLACEMENT_POPULATION=floating_voice`
  selects the other population explicitly. A missing physical feed stays
  unavailable.
- Days before the cutover come from PostHog. Days on or after the cutover come
  from the aggregate. A day is never summed from both.
- Chat stays on PostHog.
- Partial, stale, unavailable, and truncated feeds set `partial` and do not
  become a healthy zero. Truncation and store failure do not use the body.
- Actor/channel mismatches and missing actors are excluded and mark coverage
  partial. Channel still comes from the existing `update_channel` classification.
- Shadow and retirement flags are not read here.

The in-tree aggregates route requires `X-Admin-Key` and optional
`X-Admin-User`, the same headers this reader sends after `requireScope`.
A 503 body may be FastAPI `detail.code` (`telemetry_query_truncated` or
`telemetry_unavailable`). Missing key, base URL, or an unusable response
fails closed to unavailable. Live activation stays with the parent.

## Fixture receipt

Built by `buildFixtureParityReceipt()` in `lib/telemetry/parity-receipt.ts`.

| Check | Fixture result |
|---|---|
| Production physical success | 4 |
| Floating rows substituted into the physical series | no |
| Beta physical failures | 2 |
| Cutover success (PostHog day before + aggregate day of cutover, not both) | 8 |
| Fallback recovered / degraded / exhausted | 4 / 2 / 5, equal to the legacy rows |
| Fallback areas | `realtime_hub`, `ptt_cascade`, `screen_task_gate`, `screen_task_extraction`, `other` |
| Mobile disconnect event | Device Disconnected Detailed |
| Mobile unique people vs reconnect volume | 1 person, 3 reconnects |
| macOS disconnect event | Device Disconnected |
| Reader flag default | off |
| Legacy PostHog fallback consumer | still authoritative |
| Live seven-day canary | pending |
| Consumer switch | pending |
| PostHog GCP aggregate | not created |

Tests: `web/admin/lib/__tests__/replacement-reliability.test.tsx` and
`web/admin/lib/__tests__/replacement-reliability-route.test.ts`.

## Warehouse

`lib/services/gcp-billing.ts` still reads the direct BigQuery billing export.
`lib/services/plan-economics.ts` still reads `omi_finops.unit_cost_daily`,
`plan_revenue_daily`, and `unit_cost_reconciliation`. Net remains gross plus
credits. No day/project/service/SKU warehouse was added.
