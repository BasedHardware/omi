# Hosted MCP analytics

The hosted Streamable HTTP endpoint (`/v1/mcp`, with `/v1/mcp/sse` as the
permanent compatibility alias) emits two fail-open PostHog events. Both use the
server-side user ID as the distinct ID so unique-user counts are available;
unauthenticated request events use the constant `mcp-anonymous`.

Events are captured through a dedicated PostHog client configured with
`POSTHOG_EVENTS_API_KEY`, falling back to `POSTHOG_PROJECT_API_KEY`. The
separate decision client (feature flags) uses `POSTHOG_PROJECT_API_KEY` only —
the events key is never used for flag evaluation, and the legacy
`POSTHOG_API_KEY` is ignored by both clients. `POSTHOG_EVENTS_API_KEY` is
deployed only on the `backend-integration` surface.

## `MCP Tool Call`

One event per attempted `tools/call`, emitted for successes and errors
including scope denials, rate limits, and unknown tools. It is the source for
MCP adoption and retrieval dashboards; do not rename its properties without a
dashboard migration.

| Property | Values / meaning |
| --- | --- |
| `tool` | Allowlisted MCP tool name from the registry, otherwise `unknown`. |
| `operation` | Closed operation grouping from the registry: `memory_get` (also `get_user_profile`), `memory_list`, `memory_search`, `conversation_get`, `conversation_list`, `conversation_search`, `action_item_list`, `action_item_search`, `x_post_list`, `x_post_search`, `goal_list`, `chat_message_list`, `screen_activity_get`, `people_list`, `daily_summary_list`, or `other` (the write tools). |
| `client` | `chatgpt`, `claude`, `other_registered`, `api_key`, or `unknown`; never the raw OAuth client ID. |
| `transport` | `hosted_oauth`, `api_key`, or `unknown`. |
| `outcome` | `success` or `error`. |
| `authorization_outcome` | `allowed`, `denied`, or `not_applicable`. |
| `error_category` | `none`, `authorization_denied`, `validation`, `unknown_tool`, or `internal`; rate-limited calls report `validation` with `error_code` `rate_limited`. |
| `error_code` | Stable closed enum: `none`, `not_found`, `paid_plan_required`, `invalid_arguments`, `authorization_denied`, `rate_limited`, `unavailable`, `internal`, or `unknown_tool`. `internal` is the fallback for any unrecognized code. |
| `duration_ms` | Tool execution duration, capped at 60,000 ms; use it for p50/p95. |
| `result_count` | Top-level result cardinality, capped at 1,000. |
| `protocol_version` | Supported MCP protocol revision, otherwise `unknown`. |
| `in_batch` | `true` when the call arrived inside a JSON-RPC batch request. |
| `write_operation` | `none` for reads, or `memory_create`, `memory_update`, `memory_delete`, `action_item_create`, `action_item_complete`, `action_item_update`, `action_item_delete` for writes. |
| `sample_rate` | The sample rate applied to this event; `1.0` by default. |

Sampling is controlled by `MCP_TOOL_CALL_EVENT_SAMPLE_RATE` (default `1.0`).
Values are clamped to `[0, 1]`; missing, non-numeric, or non-finite values fall
back to the default. Sampling fails open — a misconfigured sampler never blocks
tool calls.

## `MCP Request`

A sampled envelope event attempted once per POST, including authentication
(`401`/`403`) and admission rate-limit (`429`) failures. It measures endpoint
usage rather than individual tools.

| Property | Values / meaning |
| --- | --- |
| `jsonrpc_methods` | Closed enum list of JSON-RPC method names in the request (e.g. `initialize`, `tools/list`, `tools/call`, `ping`), with any unrecognized method folded to `unknown`; bounded to the accepted batch cap of 20 entries. |
| `message_count` | Number of JSON-RPC messages in the body (1 for a single request, up to 20 for a batch). |
| `is_handshake` | `true` when the request contained an `initialize`. |
| `protocol_version` | Negotiated/declared protocol revision, otherwise `unknown`. |
| `client_name` | Closed enum derived from `clientInfo.name`/User-Agent: `claude_code`, `claude_ai`, `claude_desktop`, `cursor`, `codex`, `chatgpt`, `grok_cli`, `python_sdk`, `node_sdk`, `other`, or `unknown`. |
| `transport` | `hosted_oauth`, `api_key`, or `unknown`. |
| `http_status` | HTTP status returned for the POST. |
| `path` | `canonical` (`/v1/mcp`) or `legacy_sse` (`/v1/mcp/sse`). |
| `duration_ms` | Total request duration, capped at 60,000 ms. |
| `tool` | Registry tool name for the single `tools/call` in the POST, otherwise `unknown` (always present). |
| `sample_rate` | The sample rate applied to this event. |

Sampling is controlled by `MCP_REQUEST_EVENT_SAMPLE_RATE` (default `0.05`),
with the same clamping and fail-open behavior as the tool-call sampler. The
`401`/`403`/`429` attempts share this rate, so auth-failure dashboards should
treat counts as sampled estimates.

## Privacy contract

Event properties and the per-POST Cloud Logging entry intentionally exclude
tool arguments, query text, memory and conversation content, resource/document
IDs, OAuth and API-key credentials, raw OAuth client IDs, IP addresses, user
agents, raw client-supplied protocol strings, and exception text. All
client-controlled strings are normalized against closed allowlists (tool names
via the tool registry, methods via the JSON-RPC method enum, protocol versions
via `SUPPORTED_PROTOCOL_VERSIONS`, client names via the client enum) before
they reach logs or event properties, so a hostile or malformed value collapses
to `unknown` rather than logging attacker-controlled content.

Structured Cloud Logging emits exactly one INFO record per POST with the
sanitized method list, tool, status, duration, client name, and protocol
version — including auth denials and rate limits, which stay at INFO.
Tool-level exceptions log a WARNING with the normalized tool name and the
exception type only; stack traces and exception text never reach logs.
