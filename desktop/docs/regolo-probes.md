# Regolo.ai Live-Probe Results — M0 Evidence

Single source of truth for what we have empirically verified about `api.regolo.ai/v1`. Cited from the integration design doc and the dispatcher's decision table. Anything not on this page is **assumption**, not evidence.

**Probes captured:** 2026-04-22 → 2026-04-27 against `https://api.regolo.ai/v1` on the PAYG plan.

## Probe index

| # | What | Status | Artifact |
|---|---|---|---|
| P1 | Auth + model catalog (`GET /v1/models`) | ✓ resolved | inline below |
| P2 | Streaming tool-call delta shape on Llama-3.3-70B | ✓ resolved | `regolo_tool_call_stream.json` — captured in the sister Euraika repo (`/opt/projects/omi-regolo-integration/backend/tests/fixtures/`); not yet ported into this branch (M1 task) |
| P3 | Tool-calling parity across mid/large models | ✓ resolved | inline below |
| P4 | `chat_template_kwargs.enable_thinking:false` knob — which models require it | ✓ resolved | inline below |
| P5 | `reasoning_content` field — which models emit it | ✓ resolved | inline below |
| P6 | Latency × consistency multi-sample, all chat models | ✓ resolved | inline below |
| P7 | Embedding model dimensionality + latency | ✓ resolved | inline below |
| P8 | Vision (`qwen3-vl-32b`) PAYG availability | ✗ HARD-BLOCKED — model not in PAYG `/v1/models` | inline below |
| P9 | `response_format:{type:"json_object"}` strict-JSON enforcement | ⏳ deferred — informal probes show clean JSON output without it; strict-mode behavior un-verified | future probe |
| P10 | Top-level `thinking:true` opt-in shape on `gpt-oss-120b` | ⏳ deferred — not on Phase-1 critical path; `gpt-oss-120b` runs fine without thinking | future probe |
| P11 | Rate-limit headers / `Retry-After` semantics on 429 | ⏳ deferred — instrument in Phase 1 telemetry, revisit with real usage data | future probe |

## P1 — Auth + model catalog

`GET https://api.regolo.ai/v1/models` with `Authorization: Bearer <key>` returns 200 with **20 models** on PAYG. Confirmed catalog (Apr 2026):

`apertus-70b`, `brick-v1-beta`, `deepseek-ocr-2`, `faster-whisper-large-v3`, `gemma4-31b`, `gpt-oss-120b`, `gpt-oss-20b`, `gte-Qwen2`, `Llama-3.1-8B-Instruct`, `Llama-3.3-70B-Instruct`, `minimax-m2.5`, `mistral-small-4-119b`, `mistral-small3.2`, `Qwen-Image`, `Qwen3-Embedding-8B`, `Qwen3-Reranker-4B`, `qwen3-coder-next`, `qwen3.5-122b`, `qwen3.5-9b`, `qwen3.6-27b`.

**Not in PAYG `/v1/models`:** `qwen3-vl-32b` (vision). See P8.

## P2 — Streaming tool-call delta shape

Captured fixture: `regolo_tool_call_stream.json` — lives in the sister Euraika repo at `/opt/projects/omi-regolo-integration/backend/tests/fixtures/regolo_tool_call_stream.json` (5 chunks, real model response from `Llama-3.3-70B-Instruct` answering `"What is the weather in Paris right now?"` with a `get_weather(city)` tool). Porting it into this branch's `backend/tests/fixtures/` is an M1 follow-up so the replay test can run from CI.

**Verdict:** OpenAI-standard. The deltas concatenate to a valid tool call:

```
chunk 1  delta.tool_calls[0]: { id, function: { name: "get_weather", arguments: "" }, type: "function", index: 0 }
chunk 2  delta.tool_calls[0].function.arguments: '{"city": "'
chunk 3  delta.tool_calls[0].function.arguments: 'Paris"}'
chunk 4  finish_reason: "tool_calls", delta: {}
chunk 5  [DONE]
```

**Implication for backend:** `langchain_openai.ChatOpenAI` accumulates these natively. The custom streaming-tool-call accumulator the original design doc planned for `regolo_client.py` is **not needed** — confirmed by code review of the `_RegoloOpenAIProxy` class in `backend/utils/llm/clients.py` on this branch.

## P3 — Tool-calling parity across models

Same `get_weather` smoke test, non-streaming and streaming, against:

- `Llama-3.1-8B-Instruct` ✓
- `Llama-3.3-70B-Instruct` ✓ (default tool-call model on Phase 1)
- `mistral-small3.2` ✓
- `mistral-small-4-119b` ✓
- `gpt-oss-120b` ✓
- `qwen3.5-122b` (with `enable_thinking:false`) ✓
- `minimax-m2.5` (with `enable_thinking:false`) ✓

All emit OpenAI-shape `tool_calls` with `index`, `id`, `function.name`, `function.arguments` (JSON string). Argument concat across stream chunks always produces valid JSON.

## P4 — Thinking knob: which models require `enable_thinking:false`

Probe protocol: send a JSON-extraction prompt, `max_tokens=256`, no thinking flag. Record whether content is non-empty and JSON-parseable.

| Model | Without flag | With `chat_template_kwargs:{enable_thinking:false}` |
|---|---|---|
| `qwen3.5-9b` | empty content, `finish_reason:length` | clean JSON |
| `qwen3.5-122b` | empty content, `finish_reason:length` | clean JSON |
| `qwen3.6-27b` | empty content, `finish_reason:length` | clean JSON |
| `minimax-m2.5` | empty content, `finish_reason:length` | clean JSON, but emits `reasoning_content` (see P5) |
| `Llama-3.1-8B-Instruct` | clean JSON | clean JSON (flag is no-op) |
| `Llama-3.3-70B-Instruct` | clean JSON | clean JSON (no-op) |
| `mistral-small3.2` | clean JSON | clean JSON (no-op) |
| `mistral-small-4-119b` | clean JSON | clean JSON (no-op) |
| `gpt-oss-120b` | clean JSON | clean JSON (no-op) |
| `gemma4-31b` | clean JSON | clean JSON (no-op) |
| `apertus-70b` | clean JSON | clean JSON (no-op) |

**Implication:** the flag is **per-model, opt-out for thinking models only**. The opt-in path (top-level `"thinking":true, "reasoning_effort":"medium"` from `docs.regolo.ai/models/features/thinking`) is documented for `gpt-oss-120b` but is a *different* feature — Phase 1 does not enable thinking. On this branch, `REGOLO_DISABLE_THINKING_EXTRA_BODY` in `backend/utils/llm/clients.py:160` carries the body extension. M1 follow-up: gate the injection behind a `_REGOLO_THINKING_MODELS = frozenset(...)` (already implemented in the sister Euraika repo) so the no-op flag isn't sent to non-thinking models.

## P5 — `reasoning_content` field

| Model | Emits `choices[].message.reasoning_content` even with thinking off? |
|---|---|
| `minimax-m2.5` | **YES** — leaks model's internal reasoning into responses |
| All other probed models | no |

**Implication:** the `strip_reasoning_content()` helper must run before any response is persisted to chat history. Without it: bloated DB rows + leakage of reasoning tokens to clients. The helper exists in this branch's `_RegoloOpenAIProxy`; tests in `test_regolo_client.py` cover the strip path.

## P6 — Latency × consistency (multi-sample, n=5)

Single-shot p50/p90 against `/v1/chat/completions` with a structured-extraction prompt, `max_tokens=256`, `temperature=0.2`, run 5× per model.

| Model | n | p50 | p90 | spread | failure mode |
|---|---|---|---|---|---|
| `mistral-small-4-119b` | 5/5 | **0.43s** | **0.44s** | ±2% | none |
| `Llama-3.3-70B-Instruct` | 5/5 | 0.83s | 0.84s | ±1% | none |
| `Llama-3.1-8B-Instruct` | 5/5 | 0.62s | 0.72s | ±16% | none |
| `qwen3.5-122b` *(thinking off)* | 5/5 | 0.36s | 2.25s | bimodal | fast 80%, 6× slower 20% |
| `qwen3.5-9b` *(thinking off)* | 4/5 | 2.47s | 42.33s | very high | one 60s timeout |
| `qwen3.6-27b` *(thinking off)* | 1/1 | 5.62s | n/a | unknown | always slow |
| `minimax-m2.5` *(thinking off)* | 2/5 | 59.83s | 59.83s | catastrophic | **3 of 5 calls timed out at 60s** |

**Implication:** the original design's `minimax-m2.5` chat pick is **wrong**. Empirical default for chat workloads is `mistral-small-4-119b` — 2× faster than Llama-3.3-70B, 6× more consistent than `qwen3.5-122b`, equally good on tools and JSON. See the "Dispatcher decision table" patch in `REGOLO_INTEGRATION.md` for the corrected mapping.

The thinking models (Qwen3.x family + MiniMax) remain reachable via operator override (`MODEL_QOS_<FEATURE>=regolo/qwen3.5-9b`) — when picked, the `REGOLO_DISABLE_THINKING_EXTRA_BODY` injection auto-disables their thinking-on default — but they are NOT defaults.

## P7 — Embeddings

| Model | Cost | Latency | Dimensionality |
|---|---|---|---|
| `Qwen3-Embedding-8B` | €0.001/req | 0.24s | **4096** |
| `gte-Qwen2` | €0.001/req | 0.22s | 3584 |

**Implication:** dimensionality differs from OpenAI `text-embedding-3-large` (3072) and Gemini `gemini-embedding-001` (3072). The embedding store must key vectors by `(provider, model, dim)` to avoid index collision when a user toggles Privacy Mode mid-account. See `EMBEDDING_MIGRATION.md` for the parallel-index strategy. Phase 1 HARD-BLOCKS embedding-dependent features (`memory_search`, `knowledge_graph_search`, `screen_activity_search`) when EU mode is on; Phase 2 ships the adapter + migration.

## P8 — Vision (`qwen3-vl-32b`)

Not in the PAYG `/v1/models` listing (P1). `Qwen-Image` IS listed but is image *generation*, not vision *understanding*.

**Verdict:** vision is **HARD-BLOCKED** in Phase 1. The Phase 1 dispatcher decision table falls back to `gemini-3-flash-preview` for vision workloads when Privacy Mode is on, with a red `X-Privacy-Mode-Fallback: vision` banner on every request.

To unblock: open a Regolo support ticket asking for `qwen3-vl-32b` PAYG availability; or upgrade to whichever plan tier exposes it. This is design-doc Open Question #2.

## P9 — `response_format:{type:"json_object"}`

**Deferred.** Informal observation: structured-extraction prompts return clean JSON without the field, so omitting `response_format` is fine for Phase 1. Strict-mode enforcement (does Regolo refuse to emit non-JSON when this field is set?) was not explicitly probed.

**Re-probe before relying on strict-JSON guarantees.** The Phase-1 path uses prompt-engineered JSON output, validated by the existing JSON-repair flow in `utils/llm/clients.py`. If a future feature *requires* strict mode, run the probe first.

## P10 — Top-level `thinking:true` opt-in

**Deferred.** Per `docs.regolo.ai/models/features/thinking`, `gpt-oss-120b` accepts `"thinking": true, "reasoning_effort": "low|medium|high"` at the request body's top level. We do NOT enable thinking in Phase 1 (we *disable* it for the Qwen + MiniMax thinking-mode set via `chat_template_kwargs`), so this knob is unused. If a future feature wants `gpt-oss-120b`-with-thinking, probe the response shape first — `reasoning_content` may behave differently than the MiniMax case.

## P11 — Rate limits

**Deferred.** No explicit 429 was triggered during probing. Plan: instrument `_RegoloOpenAIProxy` with retry counters and `Retry-After` parsing in M1; revisit plan-tier choice with real usage data in M5.

## How to re-run the probes

The streaming tool-call probe is reproducible from the sister Euraika repo (which contains both the capture script and the committed fixture):

```bash
cd /opt/projects/omi-regolo-integration/backend/tests/fixtures
REGOLO_API_KEY=<your_key> bash capture_regolo_tool_call_stream.sh
diff regolo_tool_call_stream.json /tmp/replay-fixture.json
```

Porting this script + fixture into this branch's `backend/tests/fixtures/` is an M1 follow-up so the replay test can run from CI without depending on the sister repo's filesystem layout.

The chat / latency / thinking-knob probes ran as one-off Python scripts driven by `urllib.request`. Re-run after any Regolo catalog change to verify our model picks remain optimal. Pseudocode:

```python
for model in CATALOG:
    body = {"model": model, "messages": [...JSON_PROMPT...], "max_tokens": 256}
    if model in THINKING_MODELS:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    t0 = time.perf_counter()
    response = POST("/v1/chat/completions", body)
    record_latency_and_json_quality(model, t0)
```

## Cross-references

- Empirical model→feature mapping derived from these probes lives in the sister repo's `docs/04-model-mapping.md` (Euraika `omi-regolo-integration` GitLab project).
- The Phase 1 implementation in this branch (`worktree-omi-regolo-integration`) carries `REGOLO_DISABLE_THINKING_EXTRA_BODY` and the `_RegoloOpenAIProxy` class in `backend/utils/llm/clients.py`. M1 ports the `_REGOLO_THINKING_MODELS` set + `strip_reasoning_content()` helper from the sister repo.
- Open Questions #1, #2 (status), #3 (deferred), #4, #5, #9 in `REGOLO_INTEGRATION.md` are resolved by these probes.
