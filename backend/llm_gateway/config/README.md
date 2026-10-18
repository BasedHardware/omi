# LLM Gateway Route Configuration

`lanes.yaml`, `route_artifacts.yaml`, and `feature_bundles.yaml` define explicit gateway routes.

`generated_route_overrides.yaml` changes only the gateway routes that are otherwise generated from
`backend/utils/llm/model_config.py`. It must not be used to change legacy product routing: edits here
are applied after the legacy profile is read and affect only `omi:auto:*` gateway lanes.

Each override names one configured feature, selects its gateway provider/model, and may set
provider request options such as `reasoning_effort` or Anthropic `effort`.

Generated lanes use `openai.chat_completions`, including `chat_agent`, which is pinned to the OpenAI-compatible Luna
route. Anthropic Messages remains a separate provider surface for lanes that explicitly select Anthropic.

## Runtime credential and readiness contract

The managed Anthropic `/v1/messages` path is active when an active generated route uses an Anthropic primary. In
that state, authenticated `GET /ready` returns 503 unless `ANTHROPIC_API_KEY` is present. Both gateway Helm values
files reference that key through the shared backend ExternalSecret, and the deployment validator requires the
binding before Helm runs. Kubernetes readiness uses an authenticated exec probe against `/ready`; liveness and
startup remain on the public `/health` process check.

Do not add a provider key to this contract just because a generated lane names that provider. First verify that the
secret exists in every target project and decide whether absence should block the whole service or only mark the lane
unavailable. In particular, Perplexity is intentionally not wired by the current readiness change because the dev
secret is absent.

## Streaming terminal telemetry contract

Streaming `success` means the gateway observed the provider's protocol terminal marker: OpenAI-compatible
`data: [DONE]` or Anthropic `event: message_stop`. A clean EOF without that marker is an error, and failures before
versus after the first non-empty chunk are separate bounded phases. Provider completion does not prove that the
client received the terminal chunk.

`llm_gateway_requests_total` and `llm_gateway_request_latency_seconds` include bounded `api_surface`, `streaming`,
`phase`, `credential_source`, and `provider_rejection` labels. The provider-rejection label is parsed from only an
allowlisted set of upstream error codes and parameter roots; unknown values collapse to `other_4xx`, and provider
messages, request values, and raw bodies never become labels or terminal-log fields. Provider 4xx responses that
describe unsupported parameters remain `capability_mismatch`; invalid requests such as
`context_length_exceeded` use the separate `provider_invalid_request` failure class. These remain ineligible for LKG failover.
The only within-route exception is an Omi-paid reserved Gemini primary with an explicit Luna fallback: a
pre-output invalid request may try Luna once under both route and credential policies.
`llm_gateway_stream_ttfb_seconds` measures time to the first non-empty chunk. Request IDs are opaque UUIDs emitted
only in response headers and structured logs, never as Prometheus labels. Pre-route contract failures use
`llm_gateway_request_rejections_total{api_surface,error_class}`; service authentication failures use
`llm_gateway_auth_rejections_total{reason}`.

`route_serving_class` is a closed `active|canary|lkg|actual_fallback` contract. `fallback_used=true` requires a
prior eligible provider failure and a subsequent successful provider/route; merely selecting LKG for shadow,
disabled, 0%, or an out-of-bucket canary request is `route_serving_class="lkg"` with `fallback_used="false"`.
Bounded from/to route artifact labels and a non-`none` `fallback_reason` identify real failover without request or
user identifiers. `llm_gateway_config_info` separately publishes the immutable image tag plus active/LKG route
artifact IDs and SHA-256 content digests, avoiding build/config identity labels on the high-volume request counter.

## Usage accounting ledger

Every managed and BYOK provider attempt that reaches a gateway provider is scheduled for best-effort delivery to the
backend-owned `llm_gateway_attempts` Firestore collection. A successfully delivered event is immutable and idempotent
by gateway invocation/attempt ID; bounded queue overflow is measured as `delivery=dropped`, never hidden as zero cost.
It holds attribution (`user_uid`, caller, low-cardinality feature, and a subscription-tier snapshot), route/provider
metadata, normalized token units, cache status, and an integer micro-USD cost estimate. It never stores prompts,
completion text, raw provider bodies, headers, or credentials.

The ledger separates `hit`, `partial_hit`, and an explicit cache `miss` from `no_cache_read_observed` and
`not_reported`: a provider reporting zero cached tokens is not called a miss unless this request explicitly attempted
a cache read. Native Vertex usage reports preserve `cachedContentTokenCount` and thought tokens. Provider-rate cards
live in `cost_rate_cards.yaml`; unknown models, non-token units, and cache writes without a documented rate are
recorded as `unpriced`, never as zero cost. The estimate uses marginal token rates and deliberately excludes cache
storage charges and provider request/tool fees.

Dream v2 reasoning enables function tools; its verification lane uses the same
dedicated route and configured non-Gemini fallback, with structured output and no
tools. Nested function schemas use Vertex `parametersJsonSchema`. Session turns
reuse an identical prefix (contract, tools and seed) for Vertex implicit caching.
[Google documents implicit caching on Provisioned Throughput](https://cloud.google.com/blog/products/ai-machine-learning/vertex-ai-context-caching),
so this route does not require an explicit cached-content resource, TTL or delete
call. Cache hits are measured from provider usage, never assumed. Identical
prefixes improve reuse; provider minimum-size and retention constraints still
apply. Other lanes retain their existing capabilities and cache behavior.

Set `LLM_GATEWAY_ACCOUNTING_ENABLED=true` only for a gateway identity with Firestore read/write access to the backend
project (normally `roles/datastore.user`). Ledger writes are detached from the response path,
`LLM_GATEWAY_ACCOUNTING_WRITE_TIMEOUT_SECONDS` bounds each non-fatal Firestore write and the orderly-shutdown drain,
and `LLM_GATEWAY_ACCOUNTING_MAX_PENDING_TRACES` (default `1000`) bounds in-memory work. Delivery failures and drops
increment the bounded `llm_gateway_accounting_events_total` metric but do not fail or extend a model request. Local
development leaves accounting disabled unless explicitly enabled.

## Vertex structured-output contract

OpenAI `response_format: json_schema` is translated to Vertex v1 `responseJsonSchema`
with `responseMimeType: application/json`; `responseSchema` is omitted. The shared
normalizer preserves `$defs`/`$ref`, nullable `anyOf` branches, properties, required
fields, additional-properties rules, numeric/array bounds, and property ordering.
String/numeric `const` becomes a singleton `enum`; boolean/null/container enums
remain caller-enforced because Vertex documents only string/number enums. Unsupported generation constraints
(such as `default`, `minLength`, `maxLength`, and `pattern`) are omitted. Consumers
must validate against the original schema; dream's Pydantic validation, including
`ReviewItem`'s matching-payload validator, remains authoritative. Luna receives the
original OpenAI schema, not Vertex's normalized copy.

Contract checked on 2026-10-09 against Google's
[Vertex v1 GenerationConfig reference](https://cloud.google.com/java/docs/reference/google-cloud-vertexai/latest/com.google.cloud.vertexai.api.GenerationConfig)
and [structured-output guide](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output).
The former lists the JSON Schema keyword subset and prohibits non-`$` siblings on
`$ref`; the normalizer inlines those particular referenced nodes. Optional recursive
references remain compact; Vertex only unrolls cycles to a limited degree and does
not support required cycles. The latter includes Gemini 2.5 Flash and warns that
large/deep schemas, optional fields, enums, and constraints can cause HTTP 400.
There is no universal numerical depth/size limit published there; schema tokens
count toward the model's input budget. Do not invent a fixed safe threshold.

The 2026-10-09 dream incident supplied only a sanitized 400, so its precise Vertex
rejection is not established by local tests. The old translator demonstrably emitted
`Plan`'s unsupported generation fields and expanded its nested review definitions.
The regression executes translation on real `Plan`, `Triage`, and
`LunaTranslationBatch` schemas and checks the documented keyword/reference contract.
This establishes a wire-contract correction, not a production acceptance receipt.

Reserved Gemini invalid-request recovery goes directly to Luna, never shared/paygo
Gemini, and is available only before output. It keeps the gateway's bounded
`fallback_reason=provider_invalid_request` terminal metric and emits the shared
`omi_fallback_total` event (`reason=other`, outcome `recovered` or `exhausted`).
Existing Vertex 4xx JSON logs use fixed reason classes (`schema_keyword`,
`schema_reference`, `schema_complexity`, `schema`, or `unknown`) alongside existing
thought-signature/thinking classes; provider bodies and echoed user values are never
logged. Only the `llm-gateway` service needs redeployment for these changes.

Request counters also expose bounded `upstream_http_status` (common rejection/error codes, status classes, or `none`). The latency histogram omits that label. Use it with `provider_rejection` and `fallback_reason` when diagnosing a failing lane; old series without this label cannot supply a retrospective status breakdown. See `backend/docs/runbooks/stale-queues-and-desktop-vertex.md`.

## Prompt caching

`cache_policies.yaml` owns defaults after model resolution: agent/session and
long static prompt lanes use `explicit`; short or unique prompts use `implicit`
or `off`. Existing caller opt-outs win. OpenAI-compatible routes retain
`prompt_cache_options` and part breakpoints. Keys are additionally hashed with
the authenticated owner at the provider boundary. BYOK does not acquire a
Vertex cache; requests without an authenticated owner never create one.
Provider-scoped entries override lane and prefix defaults when a provider
fallback shares a lane ID, such as the OpenAI attempt on a desktop-Vertex lane.

Vertex explicit caching moves `systemInstruction`, tools, tool configuration,
and leading contents through the marked seed boundary into `cachedContents`.
The continuation uses `cachedContent` and omits those cached fields. Cache keys
include owner, model, region/project and complete stable prefix; handles are
process-local, bounded to 1024 entries, and never logged. Replicas may create
separate billable entries. Expired/invalid handles recreate once, then use the
original uncached request on ordinary lanes. Dream permits exactly one generation
attempt: a rejected cache handle is invalidated for the next pass, without a
second generation call. Control-plane failures degrade to implicit caching;
capacity headers and model routing on inference remain authoritative.

`LLM_GATEWAY_VERTEX_CACHE_TTL_SECONDS` defaults to 1800 seconds (minimum 1800,
maximum 86400), covering a ~28 minute Dream pass. A reuse in the latter half of
the TTL refreshes expiry rather than recreating the prefix. Cache I/O has a
one-second timeout per operation. Explicit eligibility uses a conservative
4096-token prefix estimate; Gemini 3.8 implicit eligibility uses 6144. Estimates
are heuristics; provider minimum validation remains authoritative.

Each attempt emits a content-free `llm_gateway_cache_receipt` with lane,
provider/model, traffic type, prompt/cached tokens, reported flag, mode and
prefix estimate. `llm_gateway_cache_{attempts,eligible_attempts,prompt_tokens,read_tokens}_total`
use only lane/model/mode/reported labels. Missing cache fields remain unknown,
including normalized Vertex streams; reported zero is a distinct receipt.
Dream returns additive `dream_usage.attempt_usage` alongside existing totals.
Harness prefix mutation emits `omi_shaped_agent_cache_prefix_violations_total`.

Cache creation tokens and committed storage token-seconds are recorded
separately from generation input. Rate cards optionally specify
`cache_write_micro_usd_per_million` and
`cache_storage_micro_usd_per_million_token_hours`; missing rates or ambiguous
cache-operation usage produce `unpriced`, never zero. Refresh charges only the
additional committed lifetime. Entries evicted from the local handle map still
expire upstream at their TTL, so already committed storage stays charged.
The cached read rate applies to generation's cached tokens for PT and
on-demand traffic. Cache receipts do not authorize a change of traffic type.

Grafana definitions in `backend/charts/monitoring/pending/llm-cache.json` warn per lane at under 20% cached input or over 20%
unreported cache fields, over at least 100 eligible attempts in 15 minutes.
These are pending admission: the frozen production metric inventory predates
the counters. After the counters ship, verify live series and calibration,
then admit to `alerts/` and the combined import. No alert is enabled by this change.

API references: [create](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-create),
[use](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-use),
[refresh](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-update).
The 3.8 minimums follow the ratified 2026-10-15 launch brief; no live cache or
production-account calls are part of local verification.
