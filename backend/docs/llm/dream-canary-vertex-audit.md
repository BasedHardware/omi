# Offline dream canary Vertex audit

Audited against base `f4f50c515768` (includes #21071), without production access.
The rejected production construct cannot be identified from the supplied fallback
line. A valid local translation is not evidence that Vertex accepted the request.

## Replay

`test_real_canary_requests_through_gateway_vertex_contract` in
`tests/unit/test_dream_canary.py` runs the real seed, encrypted record read, prompt
framing, shaped loop, `dream_transport.model_turn`, local gateway HTTP endpoint,
route resolution, provider request options and Vertex `model_payload` translation.
Only database IO, reservation evidence, token supply and upstream HTTP are faked.
Triage returns a synthetic spelling cluster referencing the canary conversation;
its production output is unavailable, so reasoning's evidence selection cannot be
claimed byte-identical to the lost production turn. Both success and a mocked
Vertex 400 recovered by Luna complete the encrypted shadow report.

In this configuration **triage is Luna; reasoning is reserved Gemini**. The test
also translates triage's real request through the Vertex translator for comparison.
It asserts that reasoning's audited payload equals the actual adapter HTTP body.

Run from the repository root (all backend tests use the approved runner):

```bash
printf '%s\n' tests/unit/test_dream_canary.py tests/unit/test_reserved_capacity_only.py \
  tests/unit/test_llm_gateway_vertex_schema.py tests/unit/test_vertex_attempt_diagnostics.py \
  > /tmp/dream-vertex-tests.txt
BACKEND_UNIT_TEST_FILE_LIST=/tmp/dream-vertex-tests.txt bash backend/test.sh
```

## Full request contract

| Field | Replayed shape / assessment |
|---|---|
| Messages | One nonempty system text part in `systemInstruction`, one nonempty user text part in `contents`; roles and text placement conform to [Vertex content definitions](https://github.com/googleapis/googleapis/blob/master/google/cloud/aiplatform/v1/content.proto). |
| Input budget | The real byte-based `input_ceiling` includes schema/messages/framing and leaves completion headroom within the canary's at-most-16,000 budget, far below the Flash context limit. No tokenizer or live countTokens call is used. |
| Stream | `false`; adapter uses `generateContent`. |
| Completion cap | `max_completion_tokens=256` becomes `maxOutputTokens=256`, within the [Gemini 2.5 Flash output limit](https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash). |
| Thinking | Route options become `thinkingConfig.thinkingBudget=0`; [Flash allows disabling thinking](https://cloud.google.com/vertex-ai/generative-ai/docs/thinking). No `thinkingLevel` or conflicting config. |
| Sampling | Temperature, topP, topK, candidateCount and stop sequences absent; provider defaults apply. |
| Format | `responseMimeType=application/json` plus `responseJsonSchema`; `responseSchema` absent. The [Vertex v1 proto](https://github.com/googleapis/googleapis/blob/master/google/cloud/aiplatform/v1/content.proto) documents this pairing. |
| Tools | No tools, toolConfig or tool history; no response-format/tool combination or thought-signature requirement. |
| Schema | Independent shared contract fixture checks supported keywords, enum value types, local resolvable acyclic refs, no non-$ ref siblings, required-property membership and valid propertyOrdering when present. Caller still enforces omitted constraints. |
| propertyOrdering | Absent in both schemas, which is allowed; neither prompt contains a response-schema/example whose ordering conflicts. Triage clusters in reasoning are input evidence. |
| Capacity | Actual reasoning request carries `X-Vertex-AI-LLM-Request-Type: dedicated`; no shared Vertex fallback. |

Schema measurements use `len(json.dumps(schema).encode())`. Expanded measurements
traverse referenced schemas at their use sites and exclude unused definitions.

| Schema | Raw bytes | Translated bytes | Definitions | Expanded nodes / depth | Largest enum | Largest maxItems | Optional properties |
|---|---:|---:|---:|---:|---:|---:|---:|
| Triage | 553 | 553 | 1 | 7 / 5 | 5 | 20 | 1 |
| Plan | 8,492 | 7,990 | 14 | 146 / 9 | 7 | 100 | 33 |

The [structured-output guide](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output)
documents complexity-related 400s from combinations of array bounds, nested
structure, optional properties and enums, without a numeric size/depth/enum
acceptance threshold. Plan complexity is a plausible hypothesis, **not a reproduced
provider rejection**. No speculative schema relaxation is shipped.

## Attempt evidence after gateway redeployment

The existing `vertex_provider_rejection` JSON stdout line now contains
`request_id`, `lane`, `route`, `provider`, actual serving `model`, `failure_class`,
HTTP `status`, fixed `reason`, allowlisted Google RPC `vertex_status`, and
`vertex_field` reduced to fixed API prefixes. It is emitted at the failed HTTP
attempt, before fallback, for streaming and nonstreaming calls. No additional
fallback counter or duplicate attempt log is added.

For example, a mocked schema-complexity rejection records `lane=omi:auto:dream-reasoning`,
`route=route.dream_reasoning.001`, `model=gemini-2.5-flash`,
`failure_class=provider_invalid_request`, `status=400`, `reason=schema_complexity`,
`vertex_status=INVALID_ARGUMENT`, `vertex_field=generationConfig.responseJsonSchema`
and the canonical gateway UUID. Luna recovery retains its existing fallback event.

`reason` is a fixed semantic category derived from the bounded provider preview;
status is allowlisted and field paths stop before property/definition/tool names.
Missing, malformed or truncated JSON gives unknown metadata. Messages, bodies,
violation descriptions, user IDs and arbitrary field names are never emitted.
Concurrent attempt scopes reset on exit. The next rejection can distinguish
schema complexity/reference/keyword, thinking config, signature, or unknown reasons;
it cannot recover a raw construct omitted by Vertex or its bounded preview.

Only **llm-gateway** requires redeployment for these diagnostics. Backend callers,
canary configuration and routing policy are unchanged. This change does not merge
or deploy itself.
