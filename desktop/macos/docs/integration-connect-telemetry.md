# macOS Integration Connect telemetry

Privacy-safe PostHog instrumentation for the macOS integration connect lifecycle
(Calendar, Gmail, Apple Notes, Local Files, X, and the ChatGPT/Claude memory-log
connectors). Closes the macOS half of a gap the Flutter app already covers:
Flutter emits `Integration Connect Attempted/Succeeded/Failed`
(`app/lib/utils/analytics/analytics_manager.dart`) but the macOS Swift app
previously emitted **nothing** for any connector connect/import outcome, so the
connect funnel was unmeasurable by build cohort on macOS.

## Contract owner

- Value-type namespace: `Sources/Integrations/IntegrationConnectTelemetry.swift`
- Facade + test seam: `AnalyticsManager.integrationConnectAttempted/Succeeded/Failed`
- This doc + the namespace are the single source of truth for event names and
  dimensions. Do not add a parallel convention.

## Events (mirror Flutter byte-for-byte)

| Event | Emitted at | Owner |
|---|---|---|
| `Integration Connect Attempted` | Start of a user-initiated connect | `ConnectorImportRunner.start` (Apps tab, all 7 connectors); onboarding `connectContext` (Calendar/Gmail verify probe) |
| `Integration Connect Succeeded` | Terminal success | `ConnectorImportRunner.finish(.success)`; onboarding verify probe `.connected` |
| `Integration Connect Failed` | Terminal failure | `ConnectorImportRunner.finish(.failure)`; onboarding verify probe `.needsSignIn`/`.error` |

Event-name strings are stable and MUST stay byte-identical with Flutter so
PostHog aggregates the connect funnel across iOS/Android/macOS.

## Dimensions (closed schema)

Every payload is built by `IntegrationConnectTelemetry.*Payload(...)` and passed
through an allow-list filter, so a caller cannot leak an undeclared key.

| Key | Type | Source |
|---|---|---|
| `integration_name` | String | Display name matching Flutter (`Google Calendar`, `Gmail`, …) — cross-platform aggregation key |
| `connector_id` | String | macOS internal id (`calendar`, `email`, `apple-notes`, …) |
| `surface` | closed enum | `apps` · `onboarding` |
| `stage` | closed set | `import` (Apps runner) · `verify` (onboarding probe) |
| `error_class` | closed enum (Failed only) | Union of `GmailFailureClass`/`CalendarFailureClass` raw values + `PostHogManager.diagnosticErrorClass` outputs |
| `reconnect_required` | Bool (Failed only) | Derived from `error_class` — true for reauth-needed classes |
| `duration_bucket` | closed enum (terminal, optional) | `0_1s` `1_3s` `3_10s` `10_30s` `30_60s` `60s_plus` |
| `source_count_bucket` | closed enum (Succeeded, optional) | `0` `1_10` `11_50` `51_200` `201_500` `500_plus` |
| `memory_count_bucket` | closed enum (Succeeded, optional) | as above |
| `was_first_sync` | Bool | true when no prior successful sync existed for this connector+user |

**Context dims are NOT in the payload.** `platform`, `app_version`,
`app_build`, and `update_channel` are attached automatically to every event by
PostHog super-properties registered once at `PostHogManager.initialize()`. Do
not re-add them (the Auth Flow helper's per-event re-addition is redundant).

## Privacy boundary

Payloads carry **only** the bounded dimensions above. Never emit tokens,
cookies, OAuth credentials, email/calendar/note content, account IDs, URL query
strings, raw exception text, local file paths, or browser profile names.
`error_class` is always a closed-enum value derived from the connector-native
failure enum or `PostHogManager.diagnosticErrorClass` — never the raw
`message`/`errorDescription`/`localizedDescription` (those stay in `RunState`
for the UI). The allow-list filter is defense-in-depth, mirroring the
content-key denylist in `DesktopDiagnosticsManager`.

## Denominators (per integration, per build cohort = `app_version` + `app_build`)

- **attempts** = `count(Integration Connect Attempted)`
- **initial-sync successes** = `count(Integration Connect Succeeded where surface=apps)`
- **verified connections** = `count(Integration Connect Succeeded where surface=onboarding, stage=verify)`
- **terminal failures** = `count(Integration Connect Failed where error_class not in {no_content})` — exclude `no_content` (a memory-log parse that produced nothing durable is a successful no-op, not a connect failure; surfaced as Failed only to carry UI guidance)
- **reconnect-required users** = `countDistinct(Integration Connect Failed where reconnect_required=true)`
- **degraded (transient) failures** = `count(Integration Connect Failed where error_class in {network, unknown})`
- **configuration failures** = `count(Integration Connect Failed where error_class=configuration)` (Calendar API key missing/invalid — previously silent)
- **connect-success rate** = `succeeded / (attempted)` (per surface)
- **distinct users** = PostHog `uniqueDistinctId()` over `Attempted`
- **latency** = `duration_bucket` distribution

## Channel discipline

These are product-funnel events routed `AnalyticsManager` →
`PostHogManager.track`. They are DISTINCT from
`DesktopDiagnosticsManager.recordFallback` (`desktop_health_event` /
`fallback_triggered`), which is reserved for fail-open resilience. A connect
MODE change (e.g. OAuth↔cookie fallback) should additionally call
`recordFallback`; the two streams are complementary, not duplicative. Do not
route connect outcomes through `recordFallback` (they are user-initiated actions
with explicit terminal outcomes, matching the `Auth Flow *` channel, not
fail-open resilience).

## Semantic-truth rules (enforced by tests)

1. Every real attempt resolves to exactly one terminal (Succeeded **or**
   Failed). No orphan Attempted, no double-terminal — `ConnectorImportRunner`
   deduplicates starts and run-token-guards finishes.
2. No-op ≠ failure: a background reverify that succeeds never emits Failed.
3. `reconnect_required` is derived from the classified `error_class`, so
   reauth-needed users are a queryable subset of Failed, not a separate event.
4. Cancelled/deduplicated starts emit nothing (the `tasks[connectorID] == nil`
   guard in `start` suppresses duplicate attempts).

## Out of scope (deferred)

- `Integration Disconnected` (Flutter has it) — no disconnect action exists for
  the cookie-based connectors on macOS today; deferred until a real disconnect
  owner exists.
- Notion / Memory-bank MCP connectors (`NotionMCPConnector`,
  `MemoryBankConnector`) — separate OAuth/MCP owners; each needs its own bounded
  event. Deferred.
- The Settings → Gmail Reader surface and the legacy onboarding background
  insights path (`OnboardingPagedIntroCoordinator`) — separate call sites for
  the same providers; deferred to avoid double-counting the same funnel.
