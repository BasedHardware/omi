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
`phase`, and `credential_source` labels. `llm_gateway_stream_ttfb_seconds` measures time to the first non-empty
chunk. Request IDs are opaque UUIDs emitted only in response headers and structured logs, never as Prometheus
labels. Pre-route contract failures use `llm_gateway_request_rejections_total{api_surface,error_class}`; service
authentication failures use `llm_gateway_auth_rejections_total{reason}`.
