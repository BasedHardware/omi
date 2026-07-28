# Omi Agent — Research & Experiment Findings

_Consolidated record of the agent research, live experiments, and changes shipped in the July 2026 agent-performance/churn program. All numbers are measured unless flagged as inferred. Realistic-synthetic data = real PostHog usage distributions with seeded rows; live = against production api.omi.me or a real model._

---

## TL;DR — what we found and what to do

1. **Latency, not the database, is the churn driver.** At 600K rows every data tool is <130ms; a full recap is 175ms. The pain is model/tool round-trips, and it hits the *median* user (a trivial query is ~30s), not just the power-user tail.
2. **The model frontier is Sonnet, not Opus.** Opus 4.6 (current one-shot default) is strictly worse than Sonnet 4.6 on accuracy, latency, and cost. Dropping the researcher subagent is the cut that breaks accuracy.
3. **Sonnet 5 needs effort tuning to pay off.** At default `effort=high` it costs the same as Sonnet 4.6 and runs slower; accuracy holds at every effort level, but the cost signal is noisy at n=1.
4. **Connectors are two disjoint planes.** Connecting locally (desktop) never reaches the cloud agent (server-side OAuth). A real one-click OAuth link already exists in the backend and the agent can now hand it over.
5. **Long sessions used to die into amnesia.** A non-destructive condenser now reseeds context on restart.

---

## The agent stack (three lanes)

| Lane | What it is | Where the work landed |
|---|---|---|
| **Desktop kernel** | macOS Swift + Node ACP/pi-mono daemon; SQLite conversation journal, run/attempt state machines, tool-capability broker, startup reconciliation. Wraps Claude Code via ACP. | cascade-cancel, spawn-time tool allowlist, AgentErrorClassifier |
| **Cloud VM agent** | `agent-cloud/agent.mjs` — a Claude Agent SDK `query()` loop on a per-user GCE VM, over a 600K-row SQLite of screenshots/tasks/memories. Full bash/file/browser. | researcher subagent, streaming, batch SQL, connect-link, condenser, two-plane errors |
| **Mobile proxy** | `backend/agent-proxy` — WebSocket bridge mobile ↔ VM agent. | circuit breaker, connect retries (parallel PR) |

---

## Deep Research: Patterns to Adopt

Three deep-research runs (broad-frontier, recency-constrained, and production-harness) fed an adversarial verification pass — headline numbers that failed the 0–3 / 1–2 vote are flagged as REFUTED below and must not be cited as findings.

### Run 1 — Broad frontier: durable state, orchestration, context, tool registry
_(25 claims verified → 19 confirmed, 6 killed)_

The frontier beyond Claude Code's flat append-only transcripts converges on one theme: **layer higher-order projections (snapshots, abstractions, summaries, control flow) over an immutable raw log** rather than mutating the log.

Confirmed: **LangGraph checkpointers** (snapshot-per-super-step keyed by `thread_id` → O(1) resume/fork/time-travel; 3-0) · **append-only forking** via `update_state()` (3-0) · **Temporal** append-only Event History + deterministic replay, crash-transparent (3-0; holds only for deterministic code) · **MemGPT/Letta virtual context** (arXiv:2310.08560, OS-style paging; 3-0) · **HiMem** two-layer episode+note (arXiv:2601.06377; cite architecture only — LoCoMo win REFUTED 0-3) · **context rot / compaction lossy-by-design** (Anthropic; 3-0) · **verbatim beats summarized memory** (arXiv:2601.00821: +15.9 LoCoMo, +22.0 LongMemEval-S, 77-pt constraint probe; **medium, 2-1 headline**, single churning preprint) · **sub-agent isolation as compression** (1–2K-token distilled returns; 3-0) · **CaMeL** control/data-flow separation (arXiv:2503.18813; 3-0 — but two adjacent CaMeL claims REFUTED 0-3, re-read before importing).

REFUTED: Letta filesystem-beats-Mem0 (1-2), "simple tools win" (1-2), "extraction never beats RAG" (1-2), HiMem LoCoMo superiority (0-3), CaMeL dual-LLM + per-tool capability claims (0-3).

### Run 2 — Recency-constrained (May–Jul 2026): memory + tool security
_(25 verified → 20 confirmed, 5 killed)_

**Angle A (memory) has genuine new work; Angle B (tool least-privilege) yielded almost nothing post-2026-04-21 — an important negative result.** All sources are arXiv preprints except LongMemEval-V2; every number is author self-reported.

Confirmed: **verbatim retention replicates convergently** (arXiv:2603.02473; 2606.24775 SJTU/Tsinghua, 12 systems × 11 datasets, "Late Filtering Principle"; 3-0) · **LongMemEval-V2** (arXiv:2605.12493, the only peer-reviewed item; 25M–115M-token benchmark — nuance: structured memory beats verbatim *slices alone*, winner is coding-agent-over-raw-files → "keep the raw, organize access"; 3-0 bench, 2-1 ordering) · **MEMIR** typed memory atoms (arXiv:2605.25869; 3-0) · **MEMTIER** tiered consolidation (arXiv:2605.03675; 3-0, but 72h-decay sub-claim REFUTED 0-3) · **Context Window Lifecycle** dependency-graph eviction (arXiv:2606.11213; 3-0 mechanism, 2-1 no-degradation) · **Decision-Aware Memory Cards** (arXiv:2606.08151; medium, thin eval) · **rate-distortion theory of compaction** (arXiv:2607.08032; medium; predicts irreversible-summary error grows super-linearly, reversible retrieval stays flat).

**Governance Decay (arXiv:2606.22528) — the finding that bridges memory to tool security:** compaction silently strips safety/policy constraints (0% visible → 30% avg, up to 59% after compaction; causal), and a Compaction-Eviction Attack defeats every optimized-attacked model (incl. Claude-Sonnet-4.6 65%). **Direct omi lesson: authorization/policy that lives only in-context can be evicted — least-privilege must be enforced OUTSIDE the compactable context.** (3-0 attack + causal; 2-1 on the headline figures; single lab.)

REFUTED: attention/recency-fails-identically (0-3), exact retrieval/write point-spread (1-2), COMPACT-Bench results delivered (0-3), LightMem summaries-drop (1-2), MEMTIER 72h decay (0-3).

### Run 3 — Production harness engineering (Claude Code, Codex, OpenHands, Cline, Aider, LangGraph)
_(25 verified → 25 confirmed, 0 killed — all primary source code / docs / lab blogs)_

Confirmed: **OpenHands durable state** (arXiv:2511.03690, `conversation/state.py`: two-tier `base_state.json` + append-only `EventLog`, resume via `create()` with `agent.verify()` tool-set check; crash recovery ~7.4ms median; 3-0 — **directly fixes omi's reconnect amnesia**) · **LangGraph resume-by-`thread_id`** (3-0) · **OpenHands EXCEEDS Claude Code on isolation** (Docker container sandbox + SecurityAnalyzer/ConfirmationPolicy gate; 3-0/2-1) · **Codex structured least-privilege** (scoped-permission requests, sandbox only its own shell tool → MCP tools self-guard; 3-0) · **Cline CVE-2026-52025** (auto-approve trusts the LLM's own `requires_approval` flag, no arg parsing — self-authorization; 3-0; **lesson: never delegate the danger judgment to the model that authored the command**) · **single-registry enforcement** (Cline `ClineDefaultTool` enum throws on unknown; Codex unified `tools` list; 3-0) · **Cline file-based YAML subagent registry** (hot-reloaded; 2-1) · **OpenHands non-destructive Condenser** (summarize but preserve the entire event log; ~2× cost cut; 3-0) · **Aider repo map** (tree-sitter symbol graph + PageRank under a token budget; 3-0) · **Codex stateless-prefix** (no `previous_response_id`; the opposite tradeoff — reference only for a ZDR/provider-agnostic lane; 3-0).

Caveats: Cline citations use stale paths (repo restructured to `apps/vscode/`); the 2× Condenser figure is self-cited; CVE-2026-52025 may be patched; all Claude-Code-baseline comparisons are analyst synthesis.

### Synthesis — patterns recurring across all three runs

1. **Durable, key-addressed session state over an immutable log** (LangGraph/Temporal → OpenHands base_state+EventLog). The one pattern all three runs point at; the fix for reconnect amnesia. → _shipped: session survival across reconnects + non-destructive condenser reseed._
2. **Non-destructive condensation — compact as an applied view, never delete the log** (Anthropic + CWL + rate-distortion → OpenHands Condenser). → _shipped: `conversation-condenser.mjs`._
3. **Verbatim-over-summary retrieval** — the most-replicated memory finding (2601.00821 → 2603.02473 + 2606.24775, reconciled by LongMemEval-V2 "keep raw, organize access"). → _reflected in the condenser: recent turns kept verbatim, archive retained._
4. **One tool registry, many derivations** (Cline enum + Codex unified list). → _open: #9030 Swift/TS/prompt drift._
5. **Capability confinement enforced OUTSIDE the model and outside compactable context** (CaMeL + Governance Decay + OpenHands/Codex; Cline CVE as anti-pattern). → _permissions are by-design full-access in omi's single-tenant VM; the load-bearing lesson (policy not in compactable context) is respected._

**Discipline note:** treat HiMem (0-3), the CaMeL adjacent claims (0-3), the verbatim-wins headline (2-1, single preprint), and Governance Decay's 0→30/59% figures (2-1, single lab) as directional evidence, not settled fact. Recent tool-registry least-privilege work is a genuine research gap.

---

## Experiments (measured)

### E6 — Data tools at churned-user scale (600K screenshots)
Deterministic inflation to 600K rows; every query shape the agent issues, timed.

| Query | p50 | max |
|---|---|---|
| activityCounts (1 day) | 0.1ms | 0.1ms |
| appUsageMatrix (30 days) | 126ms | 133ms |
| topWindows (7 days) | 106ms | 109ms |
| FTS keyword search | 0.1–1ms | — |
| **Full 7-day recap assembly** | **175ms** | 182ms |

**Result: SQL is not the churn driver.** The covering `idx_screenshots_timestamp` serves every range query (EXPLAIN: SEARCH). A dead `date(timestamp,'localtime')` index attempt (failed on every DB open) was removed. Reproducible via `scripts/inflate-db.mjs` + `scripts/bench-data-tools.mjs`.

### E7 — Batch tool shape (multi-query `execute_sql`)
`execute_sql` now takes a `queries[]` array run in one call with per-query error isolation. A 3-range comparison prompt collapsed **6 sequential tool round-trips → 2 calls of 3 statements**, correct, 44s. (Prompt-level batching was a prior *negative* result — the tool-shape lever is what works.)

### E8 — Median-user simulation (real average user)
Grounded in the PostHog profile (below): median DB (4,500 screenshots, 7 memories, 31 tasks), the real common queries.

| Query | wall | tools | cost | correct |
|---|---|---|---|---|
| open tasks | 35.4s | 2 | $0.196 | ✓ |
| yesterday recap | 28.0s | 2 | $0.179 | ✓ |
| memory recall | 35.6s | 5 | $0.092 | ✓ |
| dedup count | 27.5s | 3 | $0.185 | ✓ |

**Result: the latency problem hits the average user.** A trivial "what are my open tasks?" waits ~30s, dominated by the ToolSearch tax + Opus, not SQL.

### Ablation — cost/latency/accuracy frontier (mini, real models)
Cut knobs progressively until accuracy breaks. 6-query battery, ground truth from the DB.

| Variant | Cuts | Accuracy | Median wall | Total cost | Avg tools |
|---|---|---|---|---|---|
| base | Opus 4.6, full tools+prompt, browser | 5/6 | 29.5s | $0.86 | 2.2 |
| no_browser | − Playwright | 5/6 | 26.2s | $0.61 | 2.3 |
| min_tools | + strip built-in tools | 5/6 | 27.4s | $0.76 | 2.5 |
| min_prompt | + terse prompt | 5/6 | 25.6s | $0.65 | 2.5 |
| **sonnet (4.6)** | **+ Opus→Sonnet** | **6/6** | **20.4s** | **$0.65** | 2.7 |
| haiku | + Sonnet→Haiku | 5/6 | 22.9s | **$0.31** | 5.0 |
| haiku_nosub | + drop researcher | **4/6** | 20.7s | $0.30 | 5.3 |

**Findings:**
- **Sonnet 4.6 is the frontier** — beats base Opus on all three axes (accuracy 6/6 vs 5/6, −31% latency, −25% cost). Base is over-modeled.
- **Haiku flails** (avg 5 tools/turn; one query took 12 tools/69s) — cheap but high variance.
- **Dropping the researcher subagent is the break** (4/6; a `yesterday_recap` took 197s, a `top_app` took 20 tools/72s and was still wrong). Delegation is load-bearing.
- The recurring `open_tasks` "miss" is the agent *correctly* de-duplicating near-identical tasks (answers 30 vs raw-count 31) — arguably right, a ground-truth quibble.
- `min_prompt` is the only prompt cut that hurt (memory recall drops on weak models) — the memory guidance earns its tokens.

**Recommended frontier: Sonnet + no browser + researcher kept.** 6/6, ~20s, ~$0.65 — cheaper *and* faster *and* more accurate than shipped base.

### Sonnet 5 + effort sweep
Sonnet 5 (`claude-sonnet-5`) is real (released after Jan-2026 cutoff). Effort defaults to `high`.

| Effort | Accuracy | Median latency | Total cost (6q) |
|---|---|---|---|
| low | 6/6 | 18.7s | $1.27 |
| medium | 6/6 | 19.8s | $0.98 |
| high | 6/6 | 17.4s | $1.15 |

- **Accuracy holds at every effort level (6/6)** — you can run the cheapest/fastest effort without losing correctness. This is the solid result.
- **Cost is too noisy to call at n=1** — per-query cost swings 5–7× run-to-run (e.g. `absent_data`: $0.27 / $0.04 / $0.05 across efforts), larger than the effort effect. `low` came out *most* expensive, which is noise, not signal.
- At default effort, Sonnet 5 ≈ Sonnet 4.6 cost but slower (effort=high thinking cancels the intro discount).
- **Honest caveat:** single-run cost numbers (incl. earlier "$0.56 vs $0.65") are within the noise band; a trustworthy cost verdict needs N=3–5 averaged runs.

---

## Model landscape & pricing (from Anthropic docs, 2026-07)

| Model | API ID | Input / Output per MTok | omi use |
|---|---|---|---|
| Fable 5 | `claude-fable-5` | $10 / $50 | — |
| Opus 4.8 | `claude-opus-4-8` | $5 / $25 | — |
| **Sonnet 5** | `claude-sonnet-5` | **$3 / $15 ($2 / $10 intro to Aug 31 2026)** | candidate |
| Haiku 4.5 | `claude-haiku-4-5-20251001` | $1 / $5 | researcher subagent |
| Opus 4.6 (legacy) | `claude-opus-4-6` | $5 / $25 | **current one-shot path** |
| Sonnet 4.6 (legacy) | `claude-sonnet-4-6` | $3 / $15 | persistent path + ablation-best |

**Action:** the one-shot path is over-modeled on Opus 4.6 — Sonnet is the free win; the persistent path already uses Sonnet.

---

## Real-usage profile (PostHog, project 302298, 30 days, via Composio)

- **Median chat user: 3 messages/month, 0 tool calls/message** (p90=2.3, p99=43 — the churn is the p99 tail).
- **Voice ≈ half of all chat** (25,137 voice vs 25,720 text events).
- **Chat is mobile-dominated** (iOS 27K + Android 20K vs macOS 3.6K); errors are desktop (bridge/pi-mono/acp).
- **Tool mix**: `bash` 13K, `search_memories` (597 users — widest reach), `execute_sql`, `spawn_agent` 832/154 users, **`ToolSearch` 355 calls/44 users** (the SDK schema-defer tax, visible in prod).
- **Error corpus (raw strings; `error_code` null in prod — taxonomy not shipped yet):** "Response stopped." 616/296 (a user-stop, not a failure), bridge 448, opaque "Something went wrong" 290, free-plan-limit ~79, config-mode ~121, auth 35, tool-schema 40.

Full profile: `experiments/user-profile.json`. Median-user sim: `experiments/median-user-sim.md`.

---

## Connector Investigation: Local vs Cloud Planes

Omi has **two separate connector planes that do not share state**. Connecting a service in one plane leaves the other seeing it as "not connected" — the root cause of the cloud agent reporting "Google Calendar is not connected" even after the user connected calendar/gmail in the desktop beta app.

| | CLOUD plane | LOCAL plane |
|---|---|---|
| Used by | Cloud VM agent, mobile app | Desktop beta app (macOS) |
| Runs where | Backend server | User's own machine |
| Storage | Firestore `users/{uid}/integrations/{app_key}` | Nothing server-side; live browser-cookie reads |
| Auth model | Server-side OAuth (stored `access_token` + `connected==True`) | User's **browser session cookies** (Chrome/Arc/Brave/Edge) |
| Calendar impl | `get_calendar_events_tool` → Google Calendar API with stored token | `CalendarReaderService.swift` → reads `calendar.google.com` **via browser cookies** |
| Gmail impl | (none — no cloud provider) | `GmailReaderService.swift` → reads Gmail via browser cookies |
| Failure mode | `"Google Calendar is not connected. Please connect from settings"` | `noBrowserFound` / `noGmailCookies` / `notSignedIn` |
| Reachable by cloud VM? | Yes | **No** — the VM cannot touch the user's browser cookies |

**Evidence chain (cloud):** `get_calendar_events_tool` (`utils/retrieval/tools/calendar_tools.py:529`) → `prepare_access`/`get_integration_checked` (`utils/retrieval/tools/integration_base.py:34,45`) and router path `_get_google_calendar_token` (`routers/google_calendar.py:42,48–50`) → `users_db.get_integration(uid,'google_calendar')` (`database/users.py:1651,1663`) reads Firestore `users/{uid}/integrations/{app_key}`, requiring `connected==True` + `access_token`. Absent → "not connected."

**Evidence chain (local):** `GmailReaderService.swift:14,27` and `CalendarReaderService.swift:43,55` read Gmail/Calendar from the user's **signed-in browser cookies** — no Firestore write. (Correction to the earlier read: calendar is browser-cookie-based, *not* Mac EventKit.)

**Consequence:** connecting locally never populates the server-side integration, and the cloud VM physically can't reach the browser cookies — so the cloud agent is *correctly* "not connected" while the desktop indicator is *correctly* "connected." Different planes.

**The real fix already exists (with a Gmail gap):** `routers/integrations.py:42` `AUTH_PROVIDERS` has exactly one provider (`google_calendar`); `GET /v1/integrations/{app_key}/oauth-url` (`integrations.py:341`) returns a real clickable Google consent URL (verified live, HTTP 200), callback `/v2/integrations/google-calendar/callback` writes the Firestore integration the cloud plane checks. **Gmail is NOT in `AUTH_PROVIDERS`** — it's local-plane-only until a `gmail` provider entry + callback are added. The shipped `get_connect_link` tool surfaces this real URL to the user (live-verified).

---

## Reliability recon (desktop kernel + cloud)

Mechanisms that exist: startup reconciliation (`sqlite-store.ts`), attempt retry (`maxAttempts`), no-progress idle timeout (`acp.ts`), permission gating (by design — not changed), tool-invocation ledger, cooperative cancellation, delegation depth/budget.

Gaps found (ranked): **no tool-call cap per attempt** (the p99 43-tools/13-min runaway — now bounded by `maxTurns: 10` on the cloud lane), **no wall-clock budget**, **no verify-after-act** (agent trusts tool self-report), idempotency policy recorded-not-enforced, `outcome_unknown` not recovered, no per-run resource budget. Parent-cancel did not cascade to delegated children (**fixed** on desktop). Permissions are full-access **by design** (single-tenant VM sandbox) — the security-gate findings were deliberately not adopted.

---

## What shipped (this program)

**Cloud lane:** researcher subagent (Haiku, row-heavy routing, context isolation) · real token streaming + subagent progress · session survival across reconnects · reshaped data tools (date ranges, authoritative empties, app-usage matrix) · batch `execute_sql` · **`get_connect_link`** tool (hands the user the real OAuth URL — live-verified) · **non-destructive conversation condenser** (reseeds context on session death instead of amnesia) · hermetic WS e2e suite. Two-plane error handling + circuit breaker + `maxTurns` ceiling + queue-of-1 supersede (parallel PR).

**Desktop:** cascade-cancel to delegated children · spawn-time tool allowlists · `AgentErrorClassifier` fixed against the live error corpus (976/1759 events now classified with honest retryability, incl. the free-plan-limit retry-storm).

**Parked (measured dead-on-arrival):** the typed inter-agent result *wire event* — the live run proved the SDK hides subagent results/text from our stream, so the interception approach can't fire in production. The tested parser primitive remains for the desktop-kernel `DelegateAgentResult` consumer (where results are code-consumed).

---

## Open recommendations (priority order)

1. **Flip the one-shot default Opus 4.6 → Sonnet 4.6/5** — free win (cheaper/faster/more accurate).
2. **Kill the ToolSearch tax** — trim/tier the registered tool pool below the SDK defer threshold; ~2 wasted turns per conversation hit every query, incl. the median user.
3. **Single canonical tool registry** — collapse the Swift/TS/prompt drift (#9030, 16 vs 7 entries) to one manifest; throw on unknown. Kills the P4 schema errors.
4. **Wire Gmail's one-click OAuth** — add a `gmail` entry to `AUTH_PROVIDERS` so the connect-link tool covers it (calendar already works).
5. **Proactive in-session condensation** — the death-recovery reseed ships; add a proactive "condense at turn N" trigger once the real token budget is measurable on a long live session.
6. **Averaged Sonnet-5 effort/cost run** (N=3–5) to settle the cost verdict.
