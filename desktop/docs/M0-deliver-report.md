# M0 Deliver Report — Regolo.ai Integration

**Milestone:** M0 — Pre-flight probes + design-doc corrections.
**Branch:** `worktree-omi-regolo-integration`.
**Status:** ✅ Ready to merge into `main` after PR review.
**Scope:** docs only — no code changes, no test runs.

## Scope shipped

| Commit | File | Change | Verdict |
|---|---|---|---|
| `1f9c1f836` | `desktop/docs/regolo-probes.md` (NEW) | +165 LOC | Single source of truth for empirical Regolo probe data (P1–P11). |
| `3695fa713` | `desktop/docs/REGOLO_INTEGRATION.md` | +22/-18 LOC | Corrects model count, chat default, thinking-knob scope, vision status, Open Questions table. |
| `052124702` | both above | +17/-15 LOC | Code-review fixes (see "Validation findings" below). |

Total: **~150 net LOC** of design-doc corrections; **0 LOC** of executable code.

## Evidence links

- **Empirical multi-sample latency probe** (n=5 per model, structured-extraction prompt) → `regolo-probes.md` § P6.
- **Streaming tool-call delta fixture** → captured in sister Euraika repo at `/opt/projects/omi-regolo-integration/backend/tests/fixtures/regolo_tool_call_stream.json` (5 chunks, `Llama-3.3-70B-Instruct`, `get_weather` tool). M1 task: port into this branch's `backend/tests/fixtures/`.
- **Sister-repo model→feature mapping** → `/opt/projects/omi-regolo-integration/docs/04-model-mapping.md` (full table of Omi feature names → Regolo model picks, justified by the latency × consistency data).
- **This branch's existing implementation** → `backend/utils/llm/clients.py` lines 151–160 (Regolo constants) + 506 (`_get_or_create_regolo_llm`) + `_RegoloOpenAIProxy` class.

## What changed in the design

Six material corrections to the prior spec:

1. **Model count**: 19 → 20 on PAYG (`/v1/models` returned 20 distinct models).
2. **Default chat model**: `minimax-m2.5` → `mistral-small-4-119b`. P6 found MiniMax timed out on **3 of 5** calls at the 60s budget (p50 59.83s among working calls). Mistral-Small-4-119B clocked p50 0.43s / p90 0.44s with ±2% spread — 2× faster than Llama-3.3-70B and 6× more consistent than `qwen3.5-122b`.
3. **`enable_thinking:false` knob is per-model**: applies only to the Qwen3.5-9b/122b, Qwen3.6-27b, MiniMax-m2.5 set. No-op on Llama / Mistral / gpt-oss / gemma / apertus. The blanket "all non-reasoning calls inject" wording in F5 was empirically wrong.
4. **`reasoning_content` leak is MiniMax-only**: previously the spec implied multiple models leaked reasoning content. Probes show only `minimax-m2.5` does. The `strip_reasoning_content()` helper is mandatory before persistence for that one model.
5. **Vision is HARD-BLOCKED**: `qwen3-vl-32b` is not in PAYG `/v1/models`. Phase 1 falls back to Gemini with the red `X-Privacy-Mode-Fallback` banner. Was previously listed as "uncertain."
6. **Streaming tool-call shape is OpenAI-standard**: previous Open Question #9 ("first Phase 1 dev task is a live probe of regolo's streaming delta shape") is resolved by the captured fixture. `langchain_openai.ChatOpenAI` accumulates deltas natively — no custom accumulator needed in `_RegoloOpenAIProxy`.

## What was consciously deferred (and why)

| Probe | Why deferred | When to do |
|---|---|---|
| P9 — `response_format:{type:"json_object"}` strict-mode enforcement | Phase 1 path uses prompt-engineered JSON output validated by the existing JSON-repair flow. Strict mode is unnecessary unless a future feature needs it. | Re-probe the day a feature *requires* strict-JSON guarantees. |
| P10 — Top-level `thinking:true` opt-in on `gpt-oss-120b` | Phase 1 *disables* thinking for the Qwen+MiniMax set. Opting INTO thinking is a different feature we don't use. | Re-probe if a feature wants `gpt-oss-120b` reasoning. |
| P11 — Rate-limit headers / `Retry-After` semantics | No 429 was triggered during probing; instrumenting `_RegoloOpenAIProxy` with retry counters in M1 will surface real data. | M1 telemetry → revisit plan tier in M5 with usage data. |

## Validation findings

Verification ran 7 checks + a parallel code-review agent.

**Automated checks (all passed):**
- ✅ No API-key-shaped tokens in either committed file or any commit message.
- ✅ All committed cross-references resolve: `EMBEDDING_MIGRATION.md`, sister-repo fixtures, this branch's `_RegoloOpenAIProxy`.
- ✅ Markdown table integrity: 13 tables, 0 ragged rows.
- ✅ No `/v1/responses` references (M0 cleanup goal).

**Code-review findings (all addressed in commit `052124702`):**

| # | Confidence | Issue | Fix |
|---|---|---|---|
| 1 | 100% | Acceptance Criterion #2 still asserted `model=minimax-m2.5` despite the dispatcher table changing to `mistral-small-4-119b`. A QA engineer following the unfixed criterion would have failed correct code. | Updated criterion #2 + #3 to reference `mistral-small-4-119b`. |
| 2 | 90% | `EMBEDDING_MIGRATION.md` cross-reference reported as dangling (reviewer false positive — file does exist in this worktree at `desktop/docs/EMBEDDING_MIGRATION.md`). | Verified existing; no fix needed. |
| 3 | 85% | Bare `backend/tests/fixtures/regolo_*` paths implied the fixture lived in this branch. It only lives in the sister Euraika repo. | All three references qualified as sister-repo with explicit "/opt/projects/omi-regolo-integration/" path + "M1 port" note. |
| 4 | 100% (self-found) | Doc referenced `_REGOLO_THINKING_MODELS` constant. This branch carries `REGOLO_DISABLE_THINKING_EXTRA_BODY` (dict, line 160) — the frozenset gating lives in the sister repo and is a planned M1 port. | F5 + Q5 + probes-doc rephrased to describe actual current code state with M1 refinement noted. |

## Ready-to-merge status

**✅ Approved for PR to `main` from this branch** with the following scope:

- 4 commits ahead of `main` for the M0 work (+ existing 12 commits of Phase-1 backend/desktop scaffolding).
- Docs-only delta: 3 files touched (`regolo-probes.md` new, `REGOLO_INTEGRATION.md` patched, `M0-deliver-report.md` new).
- Zero code changes. Zero test runs needed. Existing Phase-1 backend/desktop commits on this branch already passed their own CI when they landed — no regressions introduced by the doc-only commits.
- No secrets, no PII, no leaked customer data.

**Caveat:** the third fix-up commit (`052124702`) batches edits to both doc files because they share a single root cause (review feedback). Splitting per-file would yield artificial "part 1 / part 2" history.

## Roadmap going forward

Per the Define-phase milestone plan (8.5 days total, ~5–6 calendar days with two engineers in parallel after M1):

| Milestone | Scope | Days | Critical path? |
|---|---|---|---|
| **M0** ✅ | Probes + doc corrections | 0.5 | done |
| **M1** | Backend Phase-1 merge + streaming-tool-call accumulator + reasoning-strip + error mapping + telemetry tagging. Port `_REGOLO_THINKING_MODELS` set + `strip_reasoning_content()` helper from sister repo. Port the streaming fixture for CI replay. | 1.5 | yes — blocks M2/M3/M4 |
| **M2** | Backend embeddings (`Qwen3-Embedding-8B`, 4096-dim) + vector-store `(provider, model, dim)` keying audit. Hard-block `memory_search`/`knowledge_graph_search`/`screen_activity_search` until done. | 1.0 | parallel with M3 |
| **M3** | Desktop: wire `PrivacyModeFallbackBanner` into `MainWindow` via `safeAreaInset`, add Regolo BYOK key entry row in Settings, populate `ModelQoS.swift` with Regolo model IDs, status-bar shield, fallback counter, EU-locale first-run prompt. | 1.5 | parallel with M2/M4 |
| **M4** | Web frontend: stop calling OpenAI from browser, build `/settings` route, Firestore preference schema, header forwarder for `X-BYOK-Regolo`+`X-Privacy-Mode`, sonner toast for fallback signal, navbar privacy shield. | 3.0 | parallel with M3 |
| **M5** | Sign Regolo DPA. Full regression suite + E2E smoke matrix on a single SHA. Telemetry dashboards. Staged rollout. | 1.0 | terminal |

**Next concrete action:** run `/octo:develop` for M1 against this branch (backend Phase-1 hardening).
