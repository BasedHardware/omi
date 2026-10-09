# Dream canary Vertex schema audit

Current finding: the owner reproduced a Vertex grammar-state rejection with the
real Plan and isolated it to array bounds. The follow-up evidence and fix below
remove generation bounds while retaining caller validation and bounded dream
output. Both llm-gateway and backend require redeployment.

The initial offline audit below used base `f4f50c515768` (includes #21071), without
production access. At that stage, the fallback line could not identify the rejected
construct; valid local translation alone did not prove provider acceptance.

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

The initial diagnostics change required only **llm-gateway** redeployment. The
follow-up fix below also changes backend dream transport. Canary configuration
and routing policy remain unchanged.

## Follow-up: live array-bound bisection (2026-10-10)

This evidence supersedes the earlier offline-only complexity hypothesis above.
The owner reported a 19:00:03Z deployed canary rejection on
`omi:auto:dream-reasoning`, `gemini-2.5-flash`, HTTP 400 / `INVALID_ARGUMENT`.
They reproduced it live in **based-hardware-dev**, using synthetic text,
`thinkingBudget: 0`, and
`responseJsonSchema: vertex_response_json_schema(Plan.model_json_schema())`.
Vertex replied:

> The specified schema produces a constraint that has too many states for serving.

The message lists long array length limits, especially when nested, among typical
causes. The owner's bisection establishes the failing construct for this Plan:
removing only `minItems`/`maxItems` gave HTTP 200; removing string lengths, numeric
bounds and formats while retaining array bounds still gave HTTP 400. Removing
only `maxItems` above 50, 20, 10 or 5 still failed. This is owner-supplied live
evidence, not a new provider call from this worktree. It does not establish a
universal numeric acceptance threshold. The
[Vertex structured-output guide](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output)
also identifies nested array bounds as a schema-complexity factor.

`vertex_response_json_schema` now omits **only the two array-bound keywords in
addition to its existing projection**. Numeric bounds, formats, enums, refs and
all other previously retained keywords remain unchanged. Property names and enum
values are still data. The original schemas remain on the caller and on Luna
fallback requests; only the Vertex generation projection is relaxed.

Dream transport trims each array to the original Pydantic schema's `maxItems`
before validating the response, retaining its ordered prefix. This covers Plan's
six bounded arrays, Triage clusters/refs, nested evidence and aliases, and optional
referenced ReviewItem payloads. Minimum lengths, extra fields, scalar bounds, types
and model validators still fail validation normally. Token usage is accounted
before normalization/validation, as before. No extra model turn is purchased.
The real seed/read/transport/gateway canary test covers oversized outputs through
both Vertex success and Luna recovery; transport tests assert the retained bounds.

The reason classifier emits fixed `schema_too_many_states` for the supplied
message, before generic schema/thinking classification. Existing attempt metadata
and privacy protections remain; no raw provider message is logged. A malformed or
truncated JSON preview can still produce `unknown`.

### Other company-paid bounded structured callers

Audited current generated feature overrides, desktop reserved text lanes and
in-tree schema producers (including literal `maxItems` and Pydantic list bounds):

| Caller | Bounds / strict enforcement |
|---|---|
| macOS screen-task extraction (`ScreenTaskPrompt`, through the Gemini proxy and reserved gateway text lane) | `tasks <= 8`, `tags <= 3`. `ScreenTaskResponse.results` rejects an entire response with more than eight valid tasks; it discards individual items with more than three tags. It enforces these bounds strictly, without dream-style truncation. |
| Backend `Memories`, `Learnings`, `JudgmentOutput`, memory-ingestion and other bounded Pydantic outputs | Current company-paid feature overrides route these to Luna, not reserved Gemini. Their Pydantic parsers / structured-output adapters validate strictly; they are not affected by this Vertex projection. |
| Translation (`LunaTranslationBatch` / viewed batch) | Currently Luna and no schema `maxItems`; the adapter also checks batch length against inputs. |
| Local conversation-summary schemas (`LocalSummaryDraft`) | Contain array bounds but run only on local inference; never a cloud Gemini caller. |

Other desktop Gemini response schemas use unbounded arrays or scalar constraints;
the desktop BFF transports arbitrary caller schemas and does not itself validate
all response-schema bounds. The concrete bounded company-paid screen-task caller
above validates at the client. No caller contract outside dream is changed.

Both **llm-gateway** (schema projection and reason label) and **backend** (dream
transport normalization) need redeployment to apply this fix. This PR does not
merge or deploy them.
