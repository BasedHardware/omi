# Hosted MCP analytics

The hosted Streamable HTTP `tools/call` boundary emits one fail-open PostHog
event named `MCP Tool Call` per attempted tool call. It is the source for MCP
adoption and retrieval dashboards; do not rename its properties without a
dashboard migration.

| Property | Values / meaning |
| --- | --- |
| `tool` | Allowlisted MCP tool name, otherwise `unknown`. |
| `operation` | Closed retrieval grouping such as `memory_search`, `memory_list`, `conversation_get`, or the connector-ready `memory_conversation_search` / `memory_conversation_fetch`. |
| `client` | `chatgpt`, `claude`, `other_registered`, `api_key`, or `unknown`; never the raw OAuth client ID. |
| `transport` | `hosted_oauth`, `api_key`, or `unknown`. |
| `outcome` | `success` or `error`. |
| `authorization_outcome` | `allowed`, `denied`, or `not_applicable`. |
| `error_category` | `none`, `authorization_denied`, `validation`, `unknown_tool`, or `internal`. |
| `duration_ms` | Tool execution duration, capped at 60,000 ms; use it for p50/p95. |
| `result_count` | Top-level result cardinality, capped at 1,000. |

PostHog's distinct ID is the server-side user ID so unique-user counts are
available. Event properties intentionally exclude tool arguments, query text,
memory and conversation content/IDs, OAuth/API-key credentials, raw client IDs,
email, and IP address.
