# Gemini generation on reserved capacity only

Company-paid Gemini text and vision generation may use only the active model of
the declared Vertex Provisioned Throughput order, with
`X-Vertex-AI-LLM-Request-Type: dedicated`. Inactive, unknown, malformed or
conflicting reservation state selects Luna (`gpt-6-luna`). A dedicated attempt
that returns the provisioned-throughput capacity error also falls back to Luna.
No company-paid generation request retries Gemini with `shared`, through AI
Studio, or through OpenRouter.

This policy supersedes the former shared Flash-Lite overflow ladder and the
blanket Gemini ban proposed in #20881. The prepaid reservation remains usable.
This source change does not deploy services or change any operator controls.

## Routes and boundaries

| Request or lane | Active unambiguous Flash order | Inactive, unknown, or exhausted capacity |
| --- | --- | --- |
| Desktop screen extractor (`gemini-3.8-flash` alias) | Active reservation model, dedicated | Luna |
| Desktop legacy Flash (`gemini-2.5-flash` alias) | Active reservation model, dedicated | Luna, subject to legacy refusal below |
| Desktop Flash-Lite (2.5 / 3.1 aliases) | Active reservation model, dedicated | Luna |
| Desktop Pro (`gemini-2.5-pro` alias) | Active reservation model, dedicated | Luna |
| Explicit desktop `gpt-6-luna` alias | Luna | Luna |
| Backend former Flash-Lite utilities and OpenRouter Gemini features | Luna feature auto lanes | Luna feature auto lanes |
| Gemini BYOK | Requested Gemini model on the user's AI Studio key | Same BYOK route; no company-funded fallback |

The accepted Gemini model names are compatibility aliases. Clients choose a
feature and send their existing Gemini JSON; the BFF and gateway choose the
serving model. The Windows screen-task pipeline performs local OCR, a Jev gate,
and at most one structured extraction request to the BFF. It has no provider
fallback loop. Existing macOS pipeline flags and client consent remain in force.

`routers/desktop_proxy.py` remains the authentication, trial/paywall, plan,
metering, cancellation and body-limit boundary. Company-paid single/batch
embeddings and generation always cross the gateway, including when the old
`OMI_LLM_GATEWAY_FEATURE_MODE` setting is off or invalid. A gateway outage does
not restore direct company-paid Gemini. `_upstream` rejects company-paid direct
inference and preserves the BYOK transport.

`desktop_gemini_gateway.py` translates Gemini text, inline images, schemas,
function histories and SSE into the gateway's OpenAI contract and back. It
preserves thought signatures for dedicated Gemini; the gateway removes Google
options and signature extensions when dispatching the Luna fallback. Desktop
managed output is capped at 2048 tokens; BYOK keeps its historical 8192 ceiling.

The gateway generates `omi:auto:desktop-vertex-*` compatibility lanes with a
reserved-only Gemini primary and an explicit OpenAI Luna fallback. The Vertex
adapter selects the active reservation model at each request. Luna fallback is
executed by the gateway, so provider attempts, usage and selected provider/model
remain visible in its accounting. Generic project 429s and invalid requests do
not qualify as capacity exhaustion. The declared routes also allow Luna fallback
on timeout before output and provider 5xx. Streaming fallback happens only before
any provider output is exposed; a later failure terminates that stream.

At config load, every company-paid generation primary and fallback is validated,
including inactive and last-known-good artifacts. Gemini is permitted only as a
native Vertex primary on a declared desktop alias with
`reserved_capacity_only: true` and the Luna fallback contract. Shared Gemini
fallbacks and OpenRouter Gemini generation are rejected. BYOK configurations and
embedding routes retain their separate contracts. Runtime adapter checks also
refuse a non-dedicated generation attempt.

## Reservation evidence and location

`config/vertex_reservations.py` declares one exclusive order, `flash-5-gsu`, for
`gemini-2.5-flash` in `us-central1` and the migration target `gemini-3.8-flash`.
The recorded purchase is 5 GSU through approximately May 2027. The registry is a
routing declaration; it does not establish the currently fulfilled model.

`vertex_reservation_state.py` shares content-free evidence through configured
Redis, or keeps it process-local when Redis is absent. Store faults produce
unknown state, with fresh local positive evidence retained. Unknown state sends
customer inference to Luna. Globally leased synthetic probes use dedicated
requests with the fixed prompt `Reply OK.`; they never contain customer content
and never retry shared. Completed successful responses must explicitly report
`usageMetadata.trafficType=PROVISIONED_THROUGHPUT` to establish active evidence.

A capacity 429 cannot distinguish an absent order from a full order. Automatic
inactivity additionally requires sustained capacity failures and fresh positive
evidence on another model of the same exclusive order. Two active models are
ambiguous and customer inference goes to Luna until evidence or an operator
declaration resolves the conflict. Before buying concurrent or split orders,
declare distinct order identities and review the selector; do not reuse the
exclusive order key.

Dedicated 2.5 Flash stays on the regional reservation endpoint. Dedicated target
Flash uses `OMI_VERTEX_PT_TARGET_LOCATION` (default `us`). A regional, US or
global location must describe the actual order; the code never discovers global
as an inference fallback. Global residency requires the existing operator
approval. A dedicated publisher-model 404 or explicit absent-capacity response
selects Luna; it does not retry the target on a shared endpoint.

## Legacy-client refusal

The #20363 refusal policy remains before metering and gateway routing. Confirmed
inactive 2.5 Flash can refuse only identified macOS legacy task loops with the
complete five-tool signature, extraction attribution, and
`7000 <= build < OMI_VERTEX_LEGACY_TASK_MIN_CAPABLE_MACOS_BUILD`.

The minimum-capable control has no default and must identify the first release
containing the #20374 fixes. Unset or invalid means no refusal. Observe mode
counts `would_refuse` and serves through the reserved/Luna route. Enforce mode
returns the existing JSON/SSE `no_task_found` terminal response with refusal
headers, invokes no provider, and consumes no metering. BYOK, Windows,
unidentified/conflicting builds and modern one-call extractors remain exempt.
The policy does not inspect prompt content or infer tasks from an image.

## Existing operator controls

No new environment knob is introduced.

| Control | Generation behavior |
| --- | --- |
| `OMI_VERTEX_RESERVATION_STATES` | JSON model states: `active`, `inactive`, `unknown`, `auto`; per-model overrides win; invalid JSON becomes unknown. |
| `OMI_VERTEX_PT_MODEL` | Declares the active reservation model; only the two registered reservation models are accepted for serving. Non-reservation pins fail closed. |
| `OMI_VERTEX_PT_TARGET_LOCATION` | Dedicated migration-target location; no automatic global fallback. |
| `OMI_VERTEX_LEGACY_TASK_MODE` | Existing enforce/observe admission control. |
| `OMI_VERTEX_LEGACY_TASK_MIN_CAPABLE_MACOS_BUILD` | Arms the existing narrowly scoped legacy refusal. |
| `OMI_GEMINI_OVERFLOW_MODEL`, `OMI_GEMINI_OVERFLOW_ENABLED` | Retired generation ladder controls; cannot select shared Gemini or disable required Luna capacity fallback. |
| `OMI_LLM_GATEWAY_FEATURE_MODE` | Does not disable mandatory company-paid feature or desktop routing. |

Embeddings, realtime/audio and TTS retain their own funding and transport
contracts. Desktop single/batch Gemini embeddings use gateway embedding lanes;
BYOK embeddings remain direct. Synthetic unit tests prove routing and wire
behavior, not live order fulfillment, provider compatibility or release health.
