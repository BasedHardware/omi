# llmgateway

The finalization adapter sends a single guarded, non-streaming POST to
`/v1/chat/completions`. The caller owns prompt construction, parsing and
persistence. These calls accept text messages and return the first choice's text
in memory. Agentic turns, streaming previews and screen-image inputs are outside
this adapter.

| Call | Gateway lane | Response format |
| --- | --- | --- |
| Conversation notes | `omi:auto:conv-structure` | Prompt-parsed text |
| Imported text structure | `omi:auto:external-structure` | Prompt-parsed text or caller-provided JSON schema |
| Background v3 notes | `omi:auto:conversation-v3-summary` | Prompt-parsed text |
| Discard classification | `omi:auto:conv-discard` | Prompt-parsed text |
| Standalone tasks | `omi:auto:conv-action-items` | Prompt-parsed text |
| Folder classification | `omi:auto:conv-folder` | Prompt-parsed text |
| App selection | `omi:auto:conv-app-select` | Caller-provided JSON schema when used |
| App result | `omi:auto:conv-app-result` | Prompt-parsed text |
| Legacy memories | `omi:auto:memories` | Prompt-parsed text |
| L1 memories | `omi:auto:memory-l1` | Prompt-parsed text |
| Structure pilot bundle | `omi:auto:chat-structured` | Strict `ConversationStructureExtraction` schema |
| Action-items pilot bundle | `omi:auto:chat-structured` | Strict `ActionItemsExtraction` schema |

Python's `utils/llm/clients.py` and `utils/llm/gateway_client.py` supply the route
and envelope. The binary supplies the token that Python resolves from
`OMI_LLM_GATEWAY_SERVICE_TOKEN` with `LLM_GATEWAY_SERVICE_TOKEN` as a fallback.
Requests use bearer auth and caller `backend`. Accounting uses the guarded tenant,
the usage feature and a recognized app platform when present. L1 uses `memories`.
Background v3 notes and imported text structure use `conv_structure`.
The pilot bundles use the gateway's strict JSON schema envelope and Python's
feature, prompt-version and parser-version metadata. The caller supplies the
schema and validates the resulting text against its output contract.

A BYOK caller may forward a matching key for a gateway-supported provider using
the existing provider key header. Gemini developer keys, the managed-only v3
lane and BYOK on the pilot bundles are rejected locally. Python's direct-provider
BYOK branches have no equivalent here. Each Go call uses one gateway request
with redirects and automatic replay disabled.

## Operation identity and recovery

Every call in the table uses the same protocol. Give each logical call a stable
job step, distinct even when two calls use the same feature. The adapter derives
a canonical UUID from `g.Operation(step)` and sends it as `X-Omi-Request-Id`.
The gateway replaces raw `op_…` values with random UUIDs. Its middleware accepts
the derived UUID, echoes it and passes it to accounting. The completion route
executes each POST independently. The accounting ledger deduplicates an immutable
attempt row by invocation UUID and ordinal, and each POST gets a fresh invocation
UUID. The ledger stores usage and contains no completion. Gateway prompt
caching can lower token cost while each invocation still executes independently.

`Recover` returns `ErrNotCommitted` without a network call. The current gateway
can charge a replay after a lost response, worker crash or takeover. Keep this
adapter off the paid finalization path until the gateway supports durable
replay and recovery. The proposed gateway contract is in the draft PR.

## Failure classes and tests

Register `Causes()` in the finalization kind declaration before wiring the client.

| Queue cause | Meaning | Outcome |
| --- | --- | --- |
| `llm_gateway_transient` | Transport, timeout, reserved capacity or gateway/server failure | Retry |
| `llm_gateway_rejected` | Bad request, route/config rejection, service auth, safety refusal or unusable completion | Fail |
| `llm_gateway_quota` | Managed provider throttle or unclassified HTTP 429 | Retry |
| `llm_gateway_byok` | Missing, invalid or unsupported user key | Fail |
| `llm_gateway_byok_quota` | User key out of quota | Fail |
| `llm_gateway_byok_rate_limit` | Temporary user-key throttle | Retry |

Retry honors a valid `Retry-After`. Queue outcomes classify the failure. The
production caller still needs the gateway replay contract before repeating paid
work. An expired guard or canceled context returns the guard or context error.

| Rule | Test |
| --- | --- |
| Feature routes, bearer auth, guarded owner and accounting fields match Python | `TestCompleteSendsFeatureLaneAndAccounting` |
| Pilot bundle versions and strict schema use the structured lane | `TestStructuredBundlesUseStrictSchemaAndVersionMetadata` |
| A retry or takeover sends the same canonical UUID, distinct across steps and jobs | `TestOperationIDSurvivesReplayAndSeparatesJobsAndSteps` |
| Recover, missing guards and invalid requests send no POST | `TestRecoverAndInvalidRequestsDoNotCallGateway` |
| A rejected forwarded key produces one request without fallback | `TestBYOKEnvelopeDoesNotRetryOrFallBack` |
| Python error envelopes, completed refusals and retry delays map to closed queue causes without leaking bodies | `TestGatewayFailureEnvelopesMapToQueueOutcomes` |
| A connection lost before a response is transient | `TestTransportFailureIsTransient` |
