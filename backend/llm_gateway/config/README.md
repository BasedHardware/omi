# LLM Gateway Route Configuration

`lanes.yaml`, `route_artifacts.yaml`, and `feature_bundles.yaml` define explicit gateway routes.

`generated_route_overrides.yaml` changes only the gateway routes that are otherwise generated from
`backend/utils/llm/model_config.py`. It must not be used to change legacy product routing: edits here
are applied after the legacy profile is read and affect only `omi:auto:*` gateway lanes.

Each override names one configured feature, selects its gateway provider/model, and may set
provider request options such as `reasoning_effort` or Anthropic `effort`.

Generated lanes normally use `openai.chat_completions`. The `chat_agent` Anthropic override is the explicit
exception: it uses `anthropic.messages` and advertises streaming + tools because `/v1/messages` preserves the native
Anthropic agentic contract. The OpenAI-compatible resolver rejects that surface, and the Messages router rejects
OpenAI-compatible lanes; this prevents the same lane from silently claiming two incompatible protocols.

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
`context_length_exceeded` use the separate, non-fallback `provider_invalid_request` failure class.
`llm_gateway_stream_ttfb_seconds` measures time to the first non-empty chunk. Request IDs are opaque UUIDs emitted
only in response headers and structured logs, never as Prometheus labels. Pre-route contract failures use
`llm_gateway_request_rejections_total{api_surface,error_class}`; service authentication failures use
`llm_gateway_auth_rejections_total{reason}`.

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

Set `LLM_GATEWAY_ACCOUNTING_ENABLED=true` only for a gateway identity with Firestore read/write access to the backend
project (normally `roles/datastore.user`). Ledger writes are detached from the response path,
`LLM_GATEWAY_ACCOUNTING_WRITE_TIMEOUT_SECONDS` bounds each non-fatal Firestore write and the orderly-shutdown drain,
and `LLM_GATEWAY_ACCOUNTING_MAX_PENDING_TRACES` (default `1000`) bounds in-memory work. Delivery failures and drops
increment the bounded `llm_gateway_accounting_events_total` metric but do not fail or extend a model request. Local
development leaves accounting disabled unless explicitly enabled.
