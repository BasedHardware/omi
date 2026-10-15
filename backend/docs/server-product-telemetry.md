# Server product analytics

`utils/product_telemetry.py` owns one lazy server capture SDK per process.
Integration, hosted MCP, conversation memory extraction, and product/billing
emitters all use `emit_product_event`. No client construction or I/O occurs on
import. Ordinary delivery uses the owned postprocess executor with at most
1,000 pending deliveries; billing and the daily MCP success marker retain
synchronous capture in their existing background workers. Failure is optional
telemetry degradation and cannot change the owning operation's response.

Capture configuration selects the first valid public `phc_` token from
`POSTHOG_PROJECT_API_KEY`, `POSTHOG_EVENTS_API_KEY`, `POSTHOG_BILLING_API_KEY`,
`POSTHOG_API_KEY`. All supplied aliases must refer to the same project. This
replaces separate billing and MCP capture credentials; flag evaluation never
uses the capture fallback chain. JIT, free-tier, proactivity and maintenance
flag SDKs remain read-only (`send=False`), with their own admission contracts.

Every server event has `emitter=server`, `environment`, boolean `test` and
closed `source_platform=macos|ios|android|windows|web|mcp|server|unknown`.
Explicit originating context wins over request metadata. The existing HTTP
BYOK middleware propagates `X-App-Platform` and `X-Build-Channel` (also
`X-App-Build-Channel` / `X-Release-Channel`) to sync/async handlers and executor
work. The async listen auth dependency binds the WebSocket headers. This is
analytics metadata, never an authorization signal. No server OS, viewer's
last-used device, or user-agent inference is used. Stored conversation
`client_platform` is supplied for task/memory extraction. Missing provenance
stays unknown; background jobs must explicitly supply their originating source.

`build_channel` is emitted only for a supplied closed channel; missing or
unrecognized channels are omitted. Owner-supplied comma-separated
`POSTHOG_INTERNAL_UIDS` / `POSTHOG_TEST_UIDS` rosters mark known staff/test
identities. Absence from these incomplete rosters does not imply external:
`internal` is omitted unless known. Exact `omi-release-probe` and `cfc_*`
principals have `test=true`. TestFlight alone never marks a person as test.
These rosters need an approved owner and runtime configuration before they
cover staff accounts; do not infer membership from email domains.

Emitters retain closed property dictionaries. The common boundary additionally
removes raw identity/content fields and `*_id` / `*_ids` properties; the existing
hashed billing `$insert_id` is retained for idempotency. Existing code-owned
experiment names remain closed enum dimensions under `experiment_id`; raw
person/device/conversation IDs are never exempted. Identity goes only in
`distinct_id`. Do not add free text, tool arguments, results, or raw IDs.

## Hosted MCP success

`MCP Tool Use Succeeded` is unsampled and scheduled only after an authenticated,
authorized application-successful registered tool invocation. Empty successful
reads count. Initialize, list, notifications, validation/auth/rate-limit errors,
JSON-RPC failures and tool `isError` outcomes do not claim the day.

Closed properties are `surface=mcp`, registry `tool`, `client` from the tool
message's `clientInfo` (including protocol `_meta`), `initiator`,
`schema_version=1`, `source_platform=mcp`, and shared defaults. This stateless
server cannot recover clientInfo sent only on a prior initialize request, so
clients should repeat it in per-message metadata. User-Agent is not a marker
client source. No present authenticated workflow signal verifies initiation;
the transport always uses `initiator=unknown`. Do not trust an arbitrary header
or tool argument to assert `user` or `scheduled_agent`.

The orchestrator's current dashboard interpretation qualifies `user` and
`unknown`; `scheduled_agent` does not qualify. This interpretation is pending
David's review, not a new ratified ruling. `MCP_QUALIFYING_INITIATORS` is the
single policy set. Explicitly classified scheduled automation does not consume
the daily qualifying marker; its detailed tool call remains a diagnostic.

Deduplication is UID × successful-call UTC day, captured before scheduling.
Redis SET NX claims for 60 seconds across workers/instances. After synchronous
capture acceptance, compare-and-set settles the claim for 48 hours. Rejection
releases the claim; Redis failures skip telemetry and retry on later qualifying
calls. A crash expires the lease. A deterministic UID/day event UUID protects
capture-success / settlement-failure retries; it is not a property or a raw ID.
Redis plus PostHog ingestion cannot form a transaction: this is unsampled
best-effort delivery, not a durable outbox or proof of ingestion. Monitor
fallbacks and verify live coverage after deployment before changing dashboards.

`MCP Tool Call` remains the stable 25%-per-UID sampled diagnostic; `MCP Active`
remains authenticated transport presence and never qualifies by itself.

## Non-Python library labels

`posthog-capture-v1-internal` comes from PostHog's own Django internal capture
client, whose `SDK_INFO` and `PostHog-Sdk-Info` header use that label:
[PostHog capture source](https://github.com/PostHog/posthog/blob/master/posthog/api/capture.py).
It publishes events on behalf of customer projects. No Omi backend emitter
constructs this library. The aggregate library label alone cannot identify
which PostHog job/workflow submitted the observed events; inspect those event
names and project-side jobs before assigning them to a product surface.

Other repository HTTP capture paths live in web share analytics (including
server-side preview bot analytics) and the Windows client; they do not use the
Python SDK. They need source-owned defaults and bot/exclusion handling in their
own lanes. No historical records are rewritten by this change.
