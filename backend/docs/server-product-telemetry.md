# Server product analytics

`utils/product_telemetry.py` owns the shared `emit_product_event` seam for
integration, hosted MCP, conversation memory extraction, and product/billing
emitters. It lazily constructs at most one SDK per admitted family (product,
billing, MCP). No client construction or I/O occurs on import. Product and MCP
capture enqueue without blocking onto independent SDK queues (1,000 events
each); consumer failures report privacy-safe fallback telemetry. Queue rejection
is observable and cannot change the owning operation's response.

Credential admission remains scoped to each emitter family. Product, integration
and memory extraction use `POSTHOG_PROJECT_API_KEY`, with the legacy
`POSTHOG_API_KEY` only when the project setting is absent. A present invalid
project setting such as `disabled` remains disabled even if a legacy key exists.
Billing uses only `POSTHOG_BILLING_API_KEY`; MCP uses only
`POSTHOG_EVENTS_API_KEY`. Missing/invalid keys disable their family. There is no
cross-family fallback: Cloud Run's `project=disabled` plus a valid billing token
never enables product/integration/extraction or MCP events.

Each SDK retains its own construction-time key; no capture mutates credentials
or holds a process-wide lock over network I/O. Key rotation requires a process
restart. Flag SDKs stay read-only with their separate admission contracts.
Billing alone uses synchronous capture, in its existing post-response worker:
its durable webhook delivery record must observe capture acceptance/failure
before settling or retrying. Its deterministic insert ID and timestamp remain
unchanged. Product and MCP queued acceptance is not proof of ingestion; queues
are best effort and can lose pending events on process termination.

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

`MCP Tool Use Succeeded` schema **2** emits on **every** authenticated,
authorized application-successful registered `tools/call`, unsampled. Empty
successful reads and registered list tools count. Protocol initialize,
`tools/list`, notifications, validation/auth/rate-limit errors, JSON-RPC failures
and tool `isError` outcomes emit no success event.

Closed properties are `surface=mcp`, registry `tool`, `op_type` in
`list|read|search|write|other`, `client` from the tool message's `clientInfo`
(including protocol `_meta`), `initiator`, `schema_version=2`,
`source_platform=mcp`, and shared defaults. Operation class comes from the
registry's operation/write metadata. Identity is only `distinct_id`; no content,
arguments, or result payloads are emitted. The SDK timestamp is captured at
application success in UTC; there is no daily claim or deterministic daily UUID.
The success event has no Redis dependency. The independent SDK queue preserves
per-call events and timestamps for threshold and cadence queries.

This stateless server cannot recover clientInfo sent only on a prior initialize
request, so clients should repeat it in per-message metadata. User-Agent is not
a marker client source. No present authenticated workflow signal verifies
initiation; transport always uses `initiator=unknown`. Do not trust an arbitrary
header or tool argument to assert `user` or `scheduled_agent`.

The orchestrator's **2026-10-15 threshold ruling** qualifies a person's UTC day at
**at least 2** successful authorized registered calls with `initiator=user` or
`unknown`, excluding `scheduled_agent` and cadence-flagged unattended streams.
`MCP_QUALIFYING_INITIATORS` and `MCP_QUALIFYING_CALLS_PER_UTC_DAY` live together in
`utils/mcp_analytics.py` as the dashboard policy source. Unknown counts until a
trusted initiator exists. This explicit ruling supersedes the earlier evidence
recommendation of one call and user-only qualification. Scheduled-agent
successes remain in the raw stream; apply policy and cadence exclusions in the
dashboard before grouping by person and UTC date. The server does not infer
cadence or human intent. Changing qualification requires no instrumentation
change. Verify deployed identity, ingestion and coverage before metric cutover;
unsampled best-effort delivery is not a durable outbox or proof of ingestion.

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
