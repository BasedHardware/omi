# Hosted MCP analytics

The hosted Streamable HTTP endpoint (`/v1/mcp`, with `/v1/mcp/sse` as the
permanent compatibility alias) produces three telemetry surfaces:

1. A 100% structured `mcp_request` log line per POST — the per-request metrics
   source, consumed through Cloud Logging log-based metrics (not PostHog).
2. A sampled `MCP Tool Call` PostHog event per attempted `tools/call`.
3. A deduplicated `MCP Active` PostHog event marking daily active users.

Request-level volume is deliberately kept out of PostHog: at ~600k POSTs/day,
per-request events are the dominant capture cost, so POST telemetry lives only
in the structured log. PostHog keeps a sampled view of tool calls plus an exact
daily-active marker.

All MCP PostHog events are personless (`$process_person_profile: false`) and
use the server-side user ID as the distinct ID.

MCP events are captured through a dedicated PostHog client configured with
`POSTHOG_EVENTS_API_KEY`; when that key is unset, capture falls back to the
generic event client (`POSTHOG_PROJECT_API_KEY`, then `POSTHOG_API_KEY`). The
events key is scoped to MCP only — non-MCP integration events never use it,
and feature-flag/JIT decisions always use `POSTHOG_PROJECT_API_KEY` directly.

## `mcp_request` structured log

Exactly one JSON record per POST, written at INFO to stdout for Cloud Logging
`jsonPayload` ingestion — including `401`/`403` auth failures and `429`
admission rate limits. There is no sampling: every POST emits exactly one
record with the `message` field `mcp_request`.

| Field | Values / meaning |
| --- | --- |
| `jsonrpc_methods` | Closed enum list of JSON-RPC method names in the request (e.g. `initialize`, `tools/list`, `tools/call`, `ping`), unrecognized methods folded to `unknown`; bounded to the batch cap of 20 entries. |
| `message_count` | Number of JSON-RPC messages in the body (1 for a single request, up to 20 for a batch). |
| `is_handshake` | `true` when the request contained an `initialize`. |
| `protocol_version` | Negotiated/declared protocol revision, otherwise `unknown`. |
| `client_name` | Closed enum derived from `clientInfo.name`/User-Agent: `claude_code`, `claude_ai`, `claude_desktop`, `cursor`, `codex`, `chatgpt`, `grok_cli`, `python_sdk`, `node_sdk`, `other`, or `unknown`. |
| `auth_type` | `hosted_oauth`, `api_key`, or `unknown`. |
| `http_status` | HTTP status returned for the POST. |
| `path` | `canonical` (`/v1/mcp`) or `legacy_sse` (`/v1/mcp/sse`). |
| `duration_ms` | Total request duration, capped at 60,000 ms. |
| `tool` | Registry tool name when exactly one `tools/call` is present, otherwise `unknown`. |

Example Cloud Logging filters for log-based metrics:

```text
# All MCP POSTs
jsonPayload.message="mcp_request"

# Requests on the canonical endpoint, split by status
jsonPayload.message="mcp_request" jsonPayload.path="canonical"

# Auth failures
jsonPayload.message="mcp_request" (jsonPayload.http_status=401 OR jsonPayload.http_status=403)

# Rate-limited requests
jsonPayload.message="mcp_request" jsonPayload.http_status=429

# Per-tool request volume
jsonPayload.message="mcp_request" jsonPayload.tool="search_memories"
```

Define a counter metric on `jsonPayload.message="mcp_request"` with labels for
`path`, `http_status`, `client_name`, and `protocol_version`; a second metric
filtered to `jsonrpc_methods:"tools/call"` labelled by `tool` gives per-tool
traffic without any PostHog spend.

## `MCP Tool Call`

One event per attempted `tools/call` **for users inside the deterministic
sample**, emitted for successes and errors including scope denials, rate
limits, and unknown tools. It is the source for MCP adoption and retrieval
dashboards; do not rename its properties without a dashboard migration.

| Property | Values / meaning |
| --- | --- |
| `tool` | Allowlisted MCP tool name from the registry, otherwise `unknown`. |
| `operation` | Closed operation grouping from the registry: `memory_get` (also `get_user_profile`), `memory_list`, `memory_search`, `memories_batch` (`create_memories`), `conversation_get` (singular and `get_conversations_by_ids`), `conversation_list`, `conversation_search`, `action_item_list`, `action_item_search`, `x_post_list`, `x_post_search`, `goal_list`, `chat_message_list`, `screen_activity_get`, `people_list`, `daily_summary_list`, or `other` (the remaining write tools). |
| `client` | `chatgpt`, `claude`, `other_registered`, `api_key`, or `unknown`; never the raw OAuth client ID. |
| `transport` | `hosted_oauth`, `api_key`, or `unknown`. |
| `outcome` | `success` or `error`. |
| `authorization_outcome` | `allowed`, `denied`, or `not_applicable`. |
| `error_category` | `none`, `authorization_denied`, `validation`, `unknown_tool`, or `internal`; rate-limited calls report `validation` with `error_code` `rate_limited`, and HTTP 5xx failures report `unavailable`/`internal`. |
| `error_code` | Stable closed enum: `none`, `not_found`, `paid_plan_required`, `invalid_arguments`, `authorization_denied`, `rate_limited`, `unavailable`, `internal`, or `unknown_tool`. `internal` is the fallback for any unrecognized code. |
| `duration_ms` | Tool execution duration, capped at 60,000 ms; use it for p50/p95. |
| `result_count` | Top-level result cardinality, capped at 1,000. |
| `protocol_version` | Supported MCP protocol revision, otherwise `unknown`. |
| `in_batch` | `true` when the call arrived inside a JSON-RPC batch request. |
| `write_operation` | `none` for reads, or `memory_create`, `memory_update`, `memory_delete`, `action_item_create`, `action_item_complete`, `action_item_update`, `action_item_delete` for writes. |
| `user_sample_rate` | The sampling rate in effect for this event (default `0.25`). Divide counts by it for population estimates. |

Sampling is **per user, deterministic, and stable**: a UID is in the sample
when `int(sha256("omi:mcp-tool-call:user-sample:v1:" + uid)[:8], 16) /
0xffffffff < rate`. A sampled user contributes *all* of their tool calls;
unsampled users contribute none, so per-user journeys inside the sample are
complete. The rate comes from `MCP_TOOL_CALL_USER_SAMPLE_RATE` (default
`0.25`), clamped to `[0, 1]`; missing, non-numeric, or non-finite values fall
back to the default. Sampling fails open — a misconfigured sampler never
blocks tool calls.

## `MCP Active`

At most one event per UID per UTC day, used for DAU/WAU. A Redis marker
`mcp:active:{YYYYMMDD}:{uid}` is claimed with `SET NX EX 172800` (two days, so
a late-UTC-day claim survives into the next day boundary); only the claiming
request emits the event. Redis failures fail open — the marker lookup throws,
the event is skipped, and the request is unaffected.

| Property | Values / meaning |
| --- | --- |
| `client_name` | Same closed enum as `mcp_request`. |
| `transport` | `hosted_oauth`, `api_key`, or `unknown`. |
| `protocol_version` | Supported MCP protocol revision, otherwise `unknown`. |
| `first_tool` | Registry tool name of the first `tools/call` in the claiming POST, or `none`. |

## Privacy contract

Event properties and the per-POST structured log intentionally exclude tool
arguments, query text, memory and conversation content, resource/document IDs,
OAuth and API-key credentials, raw OAuth client IDs, IP addresses, raw user
agents, raw client-supplied protocol strings, and exception text. All
client-controlled strings are normalized against closed allowlists (tool names
via the tool registry, methods via the JSON-RPC method enum, protocol versions
via `SUPPORTED_PROTOCOL_VERSIONS`, client names via the client enum) before
they reach logs or event properties, so a hostile or malformed value collapses
to `unknown` rather than logging attacker-controlled content.

Tool-level exceptions log via `logger.exception` with the normalized tool name
only — arguments and user data never reach the log message; memory-grant
denials log a WARNING carrying only the grant's safe observability reason.

## REST sync/export surface

The REST `/v1/mcp/*` incremental-sync contract — `X-Next-Cursor` pagination,
the `updated_since` feed on action-items, the explicit
`incremental_sync_unsupported` 400 gates on conversations/memories, and
deletion/tombstone semantics — is documented in
[`mcp-rest-sync.md`](./mcp-rest-sync.md). Incremental sync stays permanently
unsupported on those surfaces until first-class revisions exist.
