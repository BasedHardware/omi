# Inbound content screening

omi feeds a model that holds the user's authority and can call tools with material
nobody vouched for: transcripts, screen activity, web results, email, calendar
invites, attachments, and the output of tools the assistant ran itself. `utils/security/`
is the boundary on that path. It is a port of the MIT-licensed
[`yc-software/qm`](https://github.com/yc-software/qm) security layer
(`src/security/security-posture.ts`, `src/security/security-screener.ts`).

## Shape

- `utils/security/posture.py` — the `dangerous`/`auto`/`strict` triad, the policy each
  resolves to, and `compose_security_posture`, which is monotonic: a narrower scope may
  raise the posture above the configured floor but can never lower it.
- `utils/security/screen.py` — the provenance taxonomy, payload assembly, chunking,
  verdict parsing, and the retrying/cancellable `SecurityScreener`. Pure; the classifier
  is injected.
- `utils/security/tool_results.py` — the classifier bound to `get_llm('security_screen')`
  (`gpt-5-nano`), and `screen_tool_result`, the function the agentic chat loop calls. In
  gateway mode, `security_screen` is generated as the registered
  `omi:auto:security-screen` lane with the `route.security_screen.model_config.001` artifact;
  `test_security_screen_feature_resolves_to_registered_gateway_lane` guards that registration.

## Two load-bearing properties

**Fails closed on the verdict.** `parse_security_screen_verdict` accepts exactly
`{"decision":"auto"}`. Anything else that parses — a missing decision, a non-string one,
`dangerous`, an unknown word — is `strict`. `dangerous` is not representable as a
classifier verdict at all: a classifier reading untrusted text may tighten a turn, never
loosen it.

**Never fails open on availability.** When the classifier cannot be reached the content
still reaches the model, but prefixed with `unscreened_notice()` marking it unchecked and
to be treated as data. Silently dropping the screen would make an outage the cheapest way
to bypass it.

## Provenance labels

The classifier prompt reasons about these labels directly, so an inaccurate label is a
security bug rather than a cosmetic one.

| Label | Meaning |
| --- | --- |
| `direct_human` | The user's own words. Not screened — it is the authority the screen protects. |
| `tool_result:<name>` | Output of a tool the assistant already ran. |
| `external:<origin>` | Web pages, search results, email, screen activity. |
| `attachment:<name>` | A file the user supplied. |
| `prior_turn` | The assistant's own earlier output. |
| `ambient:<speaker>` | Pendant or meeting audio not addressed to the assistant. |

The taxonomy is complete even though the wired chokepoint only constructs
`tool_result:<name>`, so a caller adding a new inbound path picks a label the prompt
already understands rather than inventing one.

## What is wired today

One chokepoint: `_execute_tool` in `utils/retrieval/agentic.py`, immediately after
`preserve_chat_memory_tool_result_boundary`. That is the sharpest surface in the backend —
`utils/retrieval/tools/` returns web search results, Gmail message bodies, and calendar
invite text as strings that go straight back to the model as `tool_result.content`, and
the model can call more tools in response. On a `strict` verdict the result is prefixed
with a framing that tells the model to treat it as inert data and report the attempt.

## What is not wired

These paths reach an LLM with untrusted content and are **not** screened by this change:

- `utils/llm/conversation_processing.py:_build_conversation_context` — transcripts, photo
  descriptions, and calendar meeting title/notes/participants, inserted into a *system*
  message by `get_transcript_structure`. Labels would be `ambient:<speaker>` and
  `external:calendar`.
- `utils/llm/chat.py:_get_qa_rag_prompt` — retrieved context and app-author-supplied
  `plugin.name`/`plugin.description`.
- `utils/app_integrations.py:_process_proactive_notification` — the third-party app's
  webhook response is used as the prompt verbatim.
- `utils/llm/memories.py` — memory and learning extraction over transcript text.
- `utils/llm/external_integrations.py` — imported third-party message bodies.

Each is a separate wiring diff against the same module; the taxonomy already has a label
for every one of them.

Posture is not yet propagated to the surrounding turn. A `strict` verdict frames the
offending tool result but does not currently gate the agent's subsequent tool calls;
`render_security_policy_prompt` exists for that follow-up and is unwired.

Server-authored recovery controls such as asking for an action-item lookup or a calendar event ID are carried
separately from the result body. Only the result body is classified, so a strict frame cannot suppress a valid
next-step instruction while still protecting the model from untrusted result data.

## Configuration

| Variable | Default | Effect |
| --- | --- | --- |
| `OMI_SECURITY_POSTURE` | `auto` | `dangerous` disables screening; `auto` screens external content; `strict` skips the classifier because everything inbound is already distrusted. Unset or unparseable values fall back to `auto`. |
| `OMI_SECURITY_SCREEN_TIMEOUT_SECONDS` | `8.0` | Per-classifier-call deadline. Non-positive or unparseable values fall back to the default. |
| `OMI_SECURITY_SCREEN_TOTAL_TIMEOUT_SECONDS` | `15.0` | Total deadline for screening all content chunks, including retries and backoff. Non-positive or unparseable values fall back to the default. |

The defaults are registered in `backend/deploy/runtime_env.yaml` for the Cloud Run backend and GKE
`backend-listen` surfaces, and in both backend-listen Helm values files.

## Bounds

Total screened content is capped at 16,000 characters, truncated through the middle rather
than the tail so an injection hidden at the end of a long page is still seen. The payload
is split into 1,600-character chunks with 256 characters of overlap, classified two at a
time, and the strictest chunk verdict wins. Each chunk retries on a 250ms/1s/4s ladder;
exhaustion makes the whole screen unavailable. Classifier responses over 64KiB are
rejected. Cancellation is checked before every call and interrupts the backoff.

## Tests

`tests/unit/test_security_posture.py`, `tests/unit/test_security_screen.py`,
`tests/unit/test_security_tool_result_screen.py`.
