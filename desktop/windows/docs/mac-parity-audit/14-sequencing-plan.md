# Mac→Windows Parity — Sequencing & Effort Plan

> This is the planning pass the audit (files 00–13) explicitly deferred: "This audit does not
> rank, sequence, or estimate. That is the next session's job." It does that job.
>
> **Method.** Every item below traces to a specific finding in files 01–13 (cited inline as
> `[file#]`). Effort is a rough relative size, not a calendar commitment: **XS** (< 1 day), **S**
> (2–4 days), **M** (1–2 weeks), **L** (3–5 weeks), **XL** (multi-month / its own initiative).
> Sizes assume one engineer familiar with the relevant subsystem; parallel workstreams shrink
> wall-clock time but not total effort. No velocity data exists for this codebase, so treat sizes
> as ordering signal ("is this bigger or smaller than that"), not a committed schedule.
>
> **Scope note.** "Windows" here means the single Electron codebase that ships both Windows and
> Linux builds (`LINUX.md`, `dist/linux-arm64-unpacked`) — every item below lands on both
> platforms at once.

## TL;DR — recommended order

1. **Wave 0 (quick wins)** first, always — days of work, no architectural risk, immediate visible payoff.
2. **Wave 1 (assistant coordinator framework)** next — nothing else in the proactive cluster should be built without it, or you end up with a second ad-hoc timer loop next to `insightEngine.ts`.
3. **Waves 2–4 (Focus, Task extraction + Insight upgrade, Memory extraction + AI Profile)** in parallel once Wave 1 lands — they're siblings on the same coordinator, not a dependency chain on each other.
4. **Waves 6–7 (Chat/UI richness, Voice/PTT depth)** can run concurrently with 2–4 on a separate team — independent surfaces, no shared blocking infra.
5. **Waves 9–11 (Onboarding intelligence, Rewind depth, App shell/pages)** are opportunistic/parallel tracks — pick up as capacity allows, no cross-dependencies on the above.
6. **Wave 8 (ACP coding-agent runtime)** is a separate large initiative — decide on it independently of this proactive-features roadmap; don't let it block Waves 1–4.
7. **Wave 12 (BLE/wearables + offline WAL)** stays deferred until product un-defers Phase 7 — everything in it is blocked on BLE regardless of sequencing choices here.

---

## Wave 0 — Quick wins (no new infrastructure)

Everything here needs *connection*, not construction. Do these first regardless of what else gets prioritized — cheapest payoff in the whole audit.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| Wire `AI User Profile` backend endpoints (get/update) — zero callers today | S | [03] | Endpoints + generated client already exist |
| Wire `GET /v1/goals/{id}/advice` into Goals UI | S | [02] | Backend version is richer than Mac's local one |
| Feed `GET /v1/goals/suggest` full context (memories+conversations+tasks) instead of ~20 truncated memories | S | [02] | Same endpoint Windows already calls |
| Reachable Rewind search UI — flip `showSearch` gate, wire existing `RewindSearchBar`/`SearchResultsFilmstrip` | S | [05] | Fully built, just dead-code-gated |
| BrainGraph interactivity — flip `interactive={false}`→`true` at call sites, add a standalone viewer route | S | [11] | `OrbitControls` already implemented |
| Re-enable `localAgent.ts` chat local-context pre-step | S/M | [11] | Currently off for latency reasons; needs budget tuning, not a rebuild |
| Expand `fileIndex/scanRules.ts` `SKIP_DIRS` (4→21 entries: venv, target, dist, build, .next, etc.) | XS | [11] | One-line data fix, cuts index noise |
| Audit/fix `--accent: #5b02e0` raw-purple CSS leak (10+ call sites) | XS | [13] | Live `INV-UI-1` compliance risk, not just cosmetic |

**Total: ~1–2 weeks.** No dependencies on anything else in this plan.

---

## Wave 1 — Proactive assistant coordinator (the enabler)

**Why first:** files 01–03 independently converge on the same finding — Mac's Focus, Task, Insight, and Memory assistants are four thin classes plugged into one shared framework (`AssistantCoordinator` + `ContextDetection` + `ProactiveAssistantOrchestrationPolicy`: context-switch detection, per-assistant backpressure, capture-pause/throttle gates, notification throttling). Windows has one hand-rolled `insightEngine.ts` timer loop and nothing else. Building Focus/Task/Memory on top of *that* means either duplicating the timer-loop pattern three more times or building the coordinator now.

| Item | Effort | Source |
|---|:---:|---|
| Shared assistant protocol (`shouldAnalyze`/`analyze`/`onContextSwitch`/backpressure) | M | [01] |
| Context-switch detection (app/window-title change, spinner/counter normalization) — Windows already has the primitive via `nativeForeground.ts` | S | [01] |
| Orchestration policy gates (pause on screenshot apps, throttle on video calls, debounce on context change) | S | [01] |
| Per-assistant + global notification throttle (0–5 levels) | S | [01] |
| Bidirectional assistant-settings sync (server-authoritative) | S | [03] |

**Total: ~2–3 weeks.** Blocks Waves 2, 3, and 4's extraction pieces (not their UI-only pieces).

---

## Wave 2 — Focus assistant

The other headline proactive feature alongside Insight; real-time behavioral nudging with no Windows equivalent at all.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| Focused/distracted screen classification (Gemini vision call, reuses Rewind capture) | M | [01] | Cooldown + context-switch skip logic to bound Gemini cost |
| Glow overlay (green/red animated border around active window) | M | [01][13] | **Platform-novel**: needs Win32 layered + click-through + always-on-top windows tracking a foreign window's bounds (`WS_EX_LAYERED`/`WS_EX_TRANSPARENT` + `SetWinEventHook`/`SetWindowPos`) — no direct analogue to Mac's Accessibility-API frame lookup. Size this generously; it's the single most novel piece of platform work in Waves 1–4. |
| Session history/stats + dashboard page | S | [01] | Pure CRUD + a stats page once the classifier exists |
| Coaching notifications (distraction/refocus, cooldown) | S | [01] | Reuses existing `toastWindow.ts` delivery path |

**Total: ~3–4 weeks.** Depends on Wave 1.

---

## Wave 3 — Task extraction + Insight upgrade

Two features, same shared infra (screen capture → Gemini → structured extraction), audited separately but naturally paired.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| Screen-based AI task extraction (whitelisted apps, tool-calling loop, dedup TTL) | L | [02] | Largest single Tasks gap; ~170-line system prompt + 5-tool loop to port/redesign |
| Staged-task deduplication (hourly semantic pass) | M | [02] | Only matters once extraction produces near-duplicates |
| Task relevance prioritization (ties into AI Profile from Wave 4) | M | [02] | |
| Insight upgrade: add vision (not just OCR text) + tool-calling SQL investigation loop + cross-reference-before-advising | M | [01] | Scaffolding (Gemini client, Rewind frames, toast delivery) already exists — this is a quality upgrade to `insightEngine.ts`, not a rebuild |
| Insight → backend sync (currently local-only dead end) | S | [01] | Makes insights visible in chat/RAG/mobile |
| Insight history/browse UI | S | [01] | Mostly "a filtered memories view" once backend-synced |

**Total: ~4–5 weeks.** Depends on Wave 1. Can run in parallel with Wave 2 (different engineers, shares only the coordinator).

---

## Wave 4 — Memory extraction + AI Profile infrastructure

**Why bundled:** the AI User Profile (Wave 0's quick win only wires the *existing* backend profile read/write — this wave builds the *local daily-synthesis service* that produces genuinely Windows-native profiles) is consumed by Task prioritization (Wave 3) and Goal generation (Wave 5), so it's worth landing early even though its own UI footprint is small.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| Continuous AI memory extraction (screen → Gemini → confidence-gated memory) | M | [03] | Biggest driver of Mac's memory store growing without user effort |
| AI User Profile daily synthesis (2-stage: extract → consolidate against history) | S | [03] | Wave 0 already wired the transport; this is the generation logic |
| Embeddings/semantic similarity index (Gemini 3072-dim cosine, currently lexical-only on Windows) | M | [03] | Backs task/memory "find related" and future dedup |
| `<about_user>` chat context card | S | [03][06] | Small, local-only, improves chat grounding latency |

**Total: ~3–4 weeks.** Depends on Wave 1. Can run in parallel with Waves 2–3.

---

## Wave 5 — Goals automation

Depends on Wave 4's AI Profile existing (goal generation prompt is grounded by it on Mac).

| Item | Effort | Source |
|---|:---:|---|
| Automatic daily goal generation (conversation-triggered, full-context, dedup vs. history) | M | [02] |
| Stale-goal auto-completion (no progress in 3+ days) | S | [02] |
| Goal progress auto-extraction from conversations/chat | S | [02] |

**Total: ~1–2 weeks.**

---

## Wave 6 — Chat & UI richness (independent track)

No dependency on Waves 1–5 — this is chat-surface work, not proactive-assistant work. Can run on a separate team concurrently.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| Structured chat content blocks (tool-call/thinking/discovery/agent cards) | L | [04][13] | Largest single UI-component gap by surface area; partially downstream of Wave 8 (agent pills) for the *agent*-card variants, but tool-call cards can ship against today's `localAgent.ts` tool calls |
| Chat sessions sidebar (multi-thread: date-grouped, starred, searchable, rename) | M | [04][13] | Architectural, not cosmetic — Windows chat has no session concept in its data layer at all |
| Markdown GFM tables | S | [13] | Windows' markdown renderer has no table support |
| Typing indicator (replace literal `…`) | XS | [13] | |
| Citation cards | S | [13] | Contingent on confirming the backend sends citation data to Windows at all |
| Rating (thumbs)/share-link, message metadata popover, chat avatars | S | [06][13] | Bundle as one pass |

**Total: ~4–6 weeks.**

---

## Wave 7 — Voice/PTT depth (independent track)

Also independent of Waves 1–5; can run concurrently.

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| In-session tool-calling (voice-as-router, ~20 tools) | L | [07] | Single largest realtime-voice gap — replaces a pure audio-conversation loop with model-driven tool dispatch |
| System-wide warm-hub PTT (global hotkey, per-provider barge-in, idle/wake reconnect) vs. today's page-bound continuous session | M | [07] | Reach gap as much as a mechanics gap — Mac's hub is available from anywhere, Windows' is one button in one page |
| Voice turns recorded into shared chat history (incl. barge-in partials) | M | [07] | Needed for "what did we just talk about" continuity |
| TTS read-aloud of AI replies + barge-in (bar flow) | M | [06] | |
| PTT vocabulary boosting (screen OCR + recent activity → STT correction) | M | [06] | Directly affects everyday transcription accuracy |
| PTT spoken-language auto-detection | S | [06] | Lower priority — monolingual users see no difference |

**Total: ~4–6 weeks.**

---

## Wave 8 — Coding-agent / ACP runtime (separate large initiative)

**Flag this as its own roadmap decision, not a line item in the proactive-features plan.** The `feat/win-agents-1..4` PR stack (issue #9302) already ports the adapter core (#9304); the kernel, control plane, agent-pill UX, and settings/OAuth do not exist as PRs yet.

| Item | Effort | Source | PR coverage |
|---|:---:|---|:---:|
| ACP adapter core + adapter registry | — | [04] | ✅ #9304 |
| Kernel (sessions/runs/attempts/artifacts, SQLite) | XL | [04] | ❌ |
| Agent control-plane tools (~18 tools) + desktop coordinator | L | [04] | ❌ |
| Floating-bar agent pills + delegation UX | L | [04] | ❌ |
| Multi-provider picker + Claude OAuth (needs Windows Credential Manager/DPAPI vs. macOS Keychain) | M | [04] | ⚠️ partial |

**Total: multi-month.** Do not let this block Waves 1–7; it competes for the same engineering capacity but solves a different problem (delegate-to-coding-agent vs. ambient proactive intelligence).

---

## Wave 9 — Onboarding intelligence (opportunistic track)

| Item | Effort | Source |
|---|:---:|---|
| File-scan entity extraction (projects/tech/folders, not just app names) via LLM `execute_sql` exploration | M | [10][11] |
| Web research (search user by name/email/org → enrich profile) | M | [10] |
| Data Sources step (Gmail/Calendar read + AI synthesis) — Apple Notes has no Windows equivalent, skip | M | [10] |
| Enrichment synthesis (merge scan+email+calendar+web → profile + KG entities + goal ideas) | S | [10] |
| Exports step (Notion/Obsidian/ChatGPT/Claude + agent MCP setup) | M | [10][12] |

**Total: ~3–4 weeks.** No dependency on Waves 1–8, though it's meaningfully more valuable once Wave 4's AI Profile exists to receive the enrichment output.

---

## Wave 10 — Rewind depth (opportunistic track)

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| OCR embedding / semantic search (vs. keyword `LIKE` only) | M | [05] | Single largest Rewind capability gap |
| OCR bounding boxes (schema + WinRT OCR result shape change) | M | [05] | Prerequisite for on-image search-match highlighting |
| Video-chunk storage (H.265) vs. raw per-frame JPEGs | L | [05] | Storage-scalability problem, not just a feature — needs an `ffmpeg`-equivalent encode/decode path |
| Action-item + observation extraction from screen | M | [05] | |
| Full-screen timeline player (transport controls) | S | [13] | |
| Battery-aware capture cadence, DB corruption recovery, date navigation | S | [05] | Bundle as polish pass |

**Total: ~3–5 weeks.**

---

## Wave 11 — App shell & pages (opportunistic track)

| Item | Effort | Source | Notes |
|---|:---:|---|---|
| LiveNotes (word-threshold AI meeting-minutes during recording) | M | [12] | Distinctive marketed differentiator, zero Windows footprint |
| Speaker naming (live + post-hoc, person picker/create/retro-tag) | M | [12] | Core usability for multi-person conversations |
| Apps marketplace — Imports hub (Gmail/Calendar rows; enable behind existing flag) | S | [12] | Google integration already exists behind `VITE_ENABLE_GOOGLE_INTEGRATION`, currently off |
| Apps marketplace — Exports/MCP hub (Claude/Codex/OpenClaw/Hermes) | M | [03][12] | |
| Settings section inventory (Notifications, Shortcuts, Plan&Usage, About — 6→11 sections) | M | [12] | Largest single gap by count in this wave |
| Permissions repair page (denied/stale/broken states with Grant/Reset/Fix) | S | [12] | |

**Total: ~3–4 weeks.**

---

## Wave 12 — BLE/wearables + offline WAL (deferred, hardware-gated)

Explicitly deferred per project baseline ("Phase 7... revisit after the rest ships"). Listed here only so it isn't lost, and so anything above that seems adjacent (e.g. Storage Sync UI) isn't mistakenly pulled forward.

| Item | Effort | Source |
|---|:---:|---|
| CoreBluetooth-equivalent scan/discovery + GATT registry (→ WinRT BLE, new native-integration surface) | L | [08] |
| Device connection base class + 7 device-type subclasses | XL | [08] |
| BLE audio pipeline (frame reassembly + Opus/AAC/µ-law/LC3 decode) | L | [08] |
| WAL raw-audio buffering + `/v2/sync-local-files` reconciliation | M | [09] |
| BLE SD-card storage sync + WiFi sync | M | [09] |

**Total: multi-month.** Do not schedule until product un-defers Phase 7 — nothing here is separable from BLE support existing first.

---

## Dependency graph (informal)

```
Wave 0 (quick wins) ─── no dependencies, do immediately

Wave 1 (coordinator) ──┬── Wave 2 (Focus)
                        ├── Wave 3 (Task extraction + Insight upgrade)
                        └── Wave 4 (Memory extraction + AI Profile) ── Wave 5 (Goals automation)

Wave 6 (Chat/UI richness) ─── independent (partial soft-link to Wave 8 for agent cards)
Wave 7 (Voice/PTT depth)  ─── independent

Wave 8 (ACP runtime) ─── independent, separate initiative, own roadmap decision

Wave 9  (Onboarding)  ─── independent (stronger payoff once Wave 4 exists)
Wave 10 (Rewind depth) ─── independent
Wave 11 (App shell)    ─── independent (Exports hub soft-links to Wave 4's memory-export gap)

Wave 12 (BLE/offline) ─── blocked on product un-deferring Phase 7, independent of everything else
```

## What this plan deliberately does not do

- **No calendar commitment.** Sizes are relative-effort signals for sequencing decisions, not sprint estimates — there's no historical velocity data for this codebase to calibrate against.
- **No headcount/team-assignment recommendation.** Waves 2–4 parallelize cleanly across engineers once Wave 1 lands; Waves 6–11 are independent tracks that can be staffed opportunistically. How many of these run concurrently is a staffing decision, not an engineering-sequencing one.
- **No re-litigating "Windows-ahead" areas.** Per [00]'s "Windows-ahead" list (PTT waveform, local KG sophistication, one-shot UI-automation planner, markdown link-safety, tray icon states) — none of that is touched here; naively porting those Mac patterns would be a regression.
- **No product-scope calls.** A few items in the source audit are flagged as "confirm with product before treating as a gap" (Trial/paywall absence, Help/Crisp support chat, Windows-only `BackgroundPrivacyStep`) — those are out of this plan until product confirms intent.
