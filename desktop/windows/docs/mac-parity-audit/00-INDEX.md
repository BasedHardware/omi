# Omi Mac → Windows Parity Audit — Master Index

> **What this is.** A documentation-only survey of features, capabilities, behaviors, and enhancements the **macOS** Omi desktop app has that the **Windows** app does not (or does more weakly). It exists to feed a later planning session — **no fixes, plans, sequencing, or effort estimates are proposed here.** Each entry says *what the feature is, where it lives (files + symbols), how it works, and the exact Windows status*.
>
> **How it was produced.** A fleet of 13 parallel research agents, one per macOS subsystem, each read the Swift/TS source deeply (several ran their own sub-fleets of line-by-line deep-reads), then verified the Windows side by reading and grepping `desktop/windows/` before declaring any gap. Every "Absent/Partial" claim is grounded in a specific file check, not assumption.
>
> **Scope of the baseline.** Windows has already shipped Phases 0–6 (tray lifecycle, hidden-capture-window + AudioWorklet + VAD, conversation sync, top-edge bar + orb, meeting detection, realtime voice, OAuth, backend chat). Those are **not** reported as gaps. BLE/wearables (Phase 7) and the ACP coding-agent runtime are known-absent.
>
> **Shared backend caveat.** Both apps call the same Python backend and desktop Rust backend, so some "Mac features" are backend-driven and already reachable from Windows — several already have generated API clients with **zero callers** (see *Quick Wins*). Local-only-to-Mac features (proactive assistants, on-device embeddings/VAD, CoreBluetooth) are flagged as such.

**~200 distinct items documented across 13 areas.** Detail lives in the per-area files below; this index is the map + the cross-cutting synthesis.

---

## The 13 area files

| # | File | Area | Items | Headline |
|---|------|------|:---:|----------|
| 01 | [`01-proactive-focus-insight.md`](01-proactive-focus-insight.md) | Proactive engine — Focus & Insight | 16 | The entire screen-context proactive framework (attention judging, glow overlay, daily score, backend-synced insights) is absent |
| 02 | [`02-proactive-tasks-goals.md`](02-proactive-tasks-goals.md) | Tasks & Goals AI engine | 20 | Screen-based task extraction, per-task "Investigate" chat, autonomous task-agents, auto daily goal generation — all absent |
| 03 | [`03-memory-persona-profile.md`](03-memory-persona-profile.md) | Memory extraction, Persona, AI profile | 11 | Continuous AI memory extraction, AI User Profile, Persona/AI-clone, semantic embeddings — absent |
| 04 | [`04-chat-agent-runtime.md`](04-chat-agent-runtime.md) | Chat + ACP agent runtime | ~24 | Full coding-agent runtime (Claude/Hermes/OpenClaw over ACP), kernel, agent pills, control plane — absent (feat/win-agents PRs port a slice) |
| 05 | [`05-rewind.md`](05-rewind.md) | Rewind depth delta | 17 | Video-chunk storage, OCR **embeddings/semantic search**, a **built-but-unreachable search UI**, action items — missing |
| 06 | [`06-floating-bar-ask-ptt.md`](06-floating-bar-ask-ptt.md) | Floating bar / Ask AI / PTT | 17 | TTS read-aloud, image screen-context, vocabulary boosting, language ID, usage limiter — missing from the bar |
| 07 | [`07-realtime-voice.md`](07-realtime-voice.md) | Realtime voice depth | 10 | In-session tool-calling (voice-as-router), warm-hub PTT, voice-turns-in-history, auto model select — missing |
| 08 | [`08-bluetooth-wearables.md`](08-bluetooth-wearables.md) | Bluetooth / wearables | 17 | Entire BLE stack absent (Phase 7 deferred): 7 device types, codecs, GATT, audio pipeline |
| 09 | [`09-wal-sync-offline.md`](09-wal-sync-offline.md) | WAL / offline / storage sync | 7 | Offline audio buffering + `/v2/sync-local-files` reconciliation absent (prereq is BLE); one realtime-STT resilience note |
| 10 | [`10-onboarding.md`](10-onboarding.md) | Onboarding intelligence | 26 | Web research, data-source reading + AI synthesis, file-scan entity extraction, exports/MCP setup — missing |
| 11 | [`11-fileindex-knowledge-graph.md`](11-fileindex-knowledge-graph.md) | File index / KG / memory graph | 10 | Onboarding LLM entity extraction, **BrainGraph interactivity built but hardcoded off**, incremental scan — missing |
| 12 | [`12-app-shell-pages-system.md`](12-app-shell-pages-system.md) | App shell / pages / system | 13 | LiveNotes (auto meeting-minutes), speaker naming, Apps marketplace, Permissions/Help pages — missing |
| 13 | [`13-ui-components-visual.md`](13-ui-components-visual.md) | UI components & visual layer | 18 | Tool-call/agent cards, markdown tables, typing indicator, citation cards, glow effects — missing |

---

## Executive summary — the shape of the gap

The Windows app has faithfully ported the **capture-and-sync core** (audio in, transcription, conversations, meeting detection, a bar+orb, basic chat). What it is missing is almost entirely the **intelligence and agentic layer that sits on top of that core** — the things that make the Mac app feel proactive and alive rather than a recorder with a chat box. Five clusters dominate:

1. **The proactive-assistant framework (largest single gap).** Mac has a generalized `AssistantCoordinator` that runs Focus, Insight, Memory, and Task assistants on a shared context-detection + orchestration + notification-throttling substrate (files 01, 02, 03). Windows has *none* of this framework — it has one ad-hoc insight toast and a dumb time-tracker. Everything downstream (attention judging, screen→memory extraction, screen→task extraction, daily score, glow overlay) is absent because the framework underneath is absent. **This is the highest-leverage architectural gap: one framework unlocks four features.**

2. **The AI "understanding of the user."** A daily-regenerated **AI User Profile** (file 03) grounds task prioritization, goal generation, and chat. **Persona/AI-clone**, **semantic embeddings** (Mac uses Gemini 3072-dim cosine; Windows has only lexical token-overlap ranking), and the local **`<about_user>` chat card** are all absent. Notably, the AI-profile and goal-advice **backend endpoints already exist in Windows' generated API client with zero callers** (see Quick Wins).

3. **The coding-agent runtime (file 04).** Delegate a task to Claude Code / Hermes / OpenClaw over ACP, streamed into chat as live "agent pills," with a kernel (sessions/runs/artifacts), a desktop control plane, and a multi-provider picker + Claude OAuth. Entirely absent on Windows. **The `feat/win-agents-1..4` PR stack (issue #9302) ports the adapter core (PR #9304) but not the kernel, control plane, pill UX, or settings/OAuth** — so it's a starting slice, not the whole subsystem.

4. **Depth deltas on features Windows already has.** Rewind (file 05): Windows stores raw per-frame JPEGs (no video chunking → a storage-scalability problem), does keyword `LIKE` search instead of **OCR-embedding semantic search**, and its **unified search bar is built but dead-code-gated and unreachable**. Voice/PTT (06, 07): no in-session tool-calling, no TTS read-aloud, no vocabulary boosting or language ID, no system-audio ducking. Onboarding (10): Windows has the steps but none of the *intelligence* (web research, data-source synthesis, file entity extraction). Chat/UI (13): plain bubbles vs tool-call/agent/discovery cards, no markdown tables, no typing indicator.

5. **Hardware + offline (files 08, 09).** The entire BLE/wearable stack (7 device types, codecs, GATT, the WAL offline-buffering + `/v2/sync-local-files` reconciliation that rides on it) is absent because Phase 7 was explicitly deferred. This is a large, self-contained subsystem with a clean macOS-framework → WinRT-BLE porting story.

---

## Consolidated top gaps by theme (cross-area)

Value = impact on the Windows product (H/M/L). "PR" = touched by the `feat/win-agents` stack.

### A. Proactive-assistant framework — *entirely absent; one framework unlocks many features*
| Gap | Area | Value |
|---|---|:---:|
| Pluggable `AssistantCoordinator` (context-switch detection, backpressure, orchestration policy, notification throttling) | 01 | H (enabler) |
| Focus assistant — per-screenshot Gemini attention judging (focused/distracted) + coaching nudges + session history/score | 01 | H |
| Insight assistant depth — two-phase SQL-investigation + vision confirmation, **backend-synced as searchable memory**, history/browse UI | 01 | H |
| Focus **glow overlay** (click-through layered window, green/red animated border) | 01 / 13 | M |
| Screen-based **AI task extraction** (whitelisted apps → Gemini tool-loop → tasks) | 02 | H |
| Continuous **AI memory extraction** (screen → Gemini → confidence-gated memory, ~10 min cadence, dedup) | 03 | H |

### B. AI understanding of the user — *several are backend-ready quick wins*
| Gap | Area | Value |
|---|---|:---:|
| **AI User Profile** (daily 2-stage synthesis of memories+tasks+goals+convos into a grounding "about the user" doc) — *endpoints exist, zero callers* | 03 | H (quick win) |
| **Persona / AI-clone** (public persona from public memories, chat-able by others, moderation) | 03 | M |
| **Semantic embeddings** (Gemini 3072-dim cosine over tasks/memories) vs Windows' lexical-only ranker | 03 | M |
| Local **`<about_user>` chat context card** (name + top memories + task counts, no network) | 03 / 06 | M |
| **Auto daily goal generation** + stale-goal cleanup (full-context, dedup vs existing/abandoned) | 02 | H |
| Goal **advice/insight** ("what to do this week") — *endpoint exists and is richer than Mac's, unused* | 02 | M (quick win) |

### C. Coding-agent / ACP runtime — *feat/win-agents ports a slice*
| Gap | Area | Value | PR |
|---|---|:---:|:---:|
| ACP coding-agent client (spawn Claude/Hermes/OpenClaw over JSON-RPC stdio) | 04 | H | ✅ #9304 |
| Adapter registry / selection + worker pool | 04 | H | ✅ #9304 |
| Kernel (sessions/runs/attempts/turns/artifacts, SQLite store) | 04 | H | ❌ |
| Agent control plane (list/inspect/cancel/spawn/send, desktop awareness, intent router, tool-policy engine) | 04 | H | ❌ |
| Floating-bar **agent pills** (background-agent delegation + status polling + follow-up) | 04 | H | ❌ |
| Multi-provider chat picker + **Claude OAuth** (Keychain → needs DPAPI on Win) | 04 | H | ⚠️ adapters only |
| Structured content blocks (tool-call / thinking / discovery / agent cards) | 04 / 13 | H | ❌ |
| Chat attachments, resources/artifacts, stall detection, error taxonomy | 04 | M | ⚠️ partial |

### D. Rewind depth — *Windows has Rewind, but shallower*
| Gap | Area | Value |
|---|---|:---:|
| **Search UI reachability** — unified search bar fully built but dead-code-gated/unreachable | 05 | H (quick win) |
| **OCR embedding / semantic search** (vs keyword `LIKE` only) | 05 | H |
| Video-chunk storage (H.265) vs raw per-frame JPEGs — *storage-scalability, not just a feature* | 05 | H |
| OCR bounding boxes / on-image match highlight (schema gap) | 05 | M |
| Action-item + observation extraction from screen | 05 | H |
| Battery/power-aware capture cadence; date navigation (browse any day); FTS5 vs LIKE; DB corruption recovery | 05 | M |

### E. Voice / PTT depth
| Gap | Area | Value |
|---|---|:---:|
| **In-session tool-calling** (voice-as-router: ~20 tools — tasks, memories, search, spawn_agent, calendar, screenshot, point_click) | 07 | H |
| Warm-hub **system-wide PTT** (global hotkey, per-provider barge-in, idle/wake reconnect) vs button-only page-bound session | 07 | H |
| Voice turns recorded into shared **chat/kernel history** (incl. barge-in partials) | 07 | H |
| In-turn **screen/vision** context + point_click during voice | 07 | H |
| **TTS read-aloud** of AI replies + barge-in (bar flow) | 06 | H |
| PTT **vocabulary boosting** (screen OCR + recent activity → STT correction) | 06 | H |
| PTT **spoken-language auto-detection** (on-device Parakeet v3 + NLLanguageRecognizer) | 06 | M |
| **System-audio mute/duck** during capture (echo prevention) | 06 / 07 | M |
| Auto "Auto" model selection (daily benchmark pick); rich per-session system instructions | 07 | M |

### F. Chat & UI richness
| Gap | Area | Value |
|---|---|:---:|
| **Chat sessions sidebar** — multi-thread history (date-grouped, starred, searchable, renamable); Windows is single-thread with no session data layer | 13 | H |
| Tool-call / agent-activity / discovery cards | 13 / 04 | H |
| **Markdown tables** (Mac full GFM; Windows minimal parser degrades to plain text) | 13 | H |
| Full-screen Rewind **timeline player** (play/pause/step/speed/seek transport) vs image-pane + lightbox | 13 / 05 | M |
| Typing indicator (rotating comet-ring); citation cards; speaker color-coding in chat | 13 | M |
| Rating (thumbs) + share-link; message metadata popover; chat avatars; long-message truncation | 06 / 13 | M |

### G. Onboarding intelligence — *steps exist, intelligence doesn't*
| Gap | Area | Value |
|---|---|:---:|
| **Web research** (search user by name/email/org → enrich profile) | 10 | H |
| **Data Sources** step (Gmail/Calendar/Apple Notes read + AI synthesis) | 10 | H |
| Enrichment synthesis (LLM merges all sources → profile + KG entities + goal ideas) | 10 | H |
| File-scan **entity extraction** (projects/tech/folders, not just app names) | 10 / 11 | H |
| Exports step (Notion/Obsidian/ChatGPT/Claude/Gemini + agent MCP setup); memory-log import; multi-language select | 10 | M |

### H. App shell & pages
| Gap | Area | Value |
|---|---|:---:|
| **LiveNotes** — AI auto meeting-minutes during recording (word-threshold Gemini generation, live panel) | 12 | H |
| **Speaker naming** (live + post-hoc, person picker/create/retro-tag) | 12 | H |
| **Apps marketplace** — Imports hub (7 connectors) + Exports/MCP hub | 12 | H |
| Settings section inventory (Mac 11 + fuzzy search vs Windows 6 tabs; missing Notifications/Shortcuts/Plan&Usage/About/Transcription) | 12 | H |
| Redesigned Home (stat ribbon, connect-data tray); Permissions repair page; Help/Crisp support; spatial overlay | 12 | M |

### I. Bluetooth / wearables + offline (Phase 7 deferred — entire subsystem)
| Gap | Area | Value |
|---|---|:---:|
| CoreBluetooth scan/discovery + GATT UUID registry + transport abstraction (→ WinRT BLE) | 08 | H |
| 7 device connections (Omi/OpenGlass, Friend, Bee, Fieldy, Limitless, PLAUD, Frame-stub) | 08 | H/M |
| BLE audio pipeline (frame reassembly, Opus/AAC/µ-law/LC3 decode) | 08 | H |
| **WAL offline audio buffering** + `/v2/sync-local-files` upload/reconciliation; BLE SD-card storage sync; WiFi sync | 09 | H/M |

### J. File index / knowledge graph
| Gap | Area | Value |
|---|---|:---:|
| Onboarding **LLM file-exploration → entity extraction** (execute_sql + save_knowledge_graph → 15–40 node graph) | 11 | H |
| **Memory-graph interactivity** — BrainGraph has OrbitControls built in but every call site hardcodes `interactive={false}`; no standalone viewer | 11 | M (quick win) |
| Chat local-context enrichment — macOS-faithful agentic pre-step **fully implemented in `localAgent.ts` but turned OFF** ("Floor-only mode") | 11 | M (quick win) |
| Incremental/auto re-scan (3h diff-based) vs once-at-onboarding; richer scan-policy exclusions (21 dirs vs 4) | 11 | M |

---

## Quick wins — already built, just unwired or disabled

These need *connection*, not construction — flagged repeatedly across the audit:

- **AI User Profile** — backend `get/update_ai_profile` endpoints are in Windows' generated OpenAPI client with **zero callers** (file 03).
- **Goal advice** — `GET /v1/goals/{id}/advice` exists, is **richer than Mac's local version**, and is unused by any Windows UI (file 02).
- **Goal suggestion richness** — same `GET /v1/goals/suggest` endpoint Windows already calls, but fed only ~20 truncated memories vs Mac's full context (file 02).
- **Rewind unified search bar** — fully implemented in the renderer but **dead-code-gated and unreachable** (file 05).
- **BrainGraph interactivity** — `OrbitControls` drag/rotate/zoom already built into `BrainGraph.tsx`; every call site passes `interactive={false}` (file 11).
- **Chat local-context enrichment** — the macOS-faithful `execute_sql` agentic pre-step is fully present in `localAgent.ts` but explicitly disabled ("Flip to true to restore the macOS-faithful agentic pre-step") (file 11).

## Windows-ahead — do NOT regress these when porting

The Windows app is *better* than Mac in a few places; a naive port would be a downgrade:

- **PTT waveform** — Windows' adaptive noise-floor gate + 60fps rAF easing is arguably ahead of Mac's static boost curve (files 06, 13).
- **Local KG** — Windows' KG schema (summary/source/aliases/sourceRefs) + off-thread worker + coalescing write-queue is **more sophisticated** than Mac's (file 11).
- **One-shot UI-automation planner** (`actionPlanner.ts` + native approval dialog) — a real Windows-only capability with no Mac equivalent (file 04).
- **Markdown link safety** — Windows restricts clickable links to http(s)/mailto as a deliberate prompt-injection defense over OCR'd screen content (file 13).
- **Conversation-record sync resilience** — Windows' `outbox.ts` CAS+dedupe is solid (file 09).
- **Tray per-state icon set** (3 states) vs Mac's single static icon (file 13).
- **Design tokens** — Windows' `tailwind.config.ts` already remaps `purple.*` → translucent white (INV-UI-1 compliant); any Mac component leaning on `OmiColors.purplePrimary` needs a **conscious** remap, not a literal color port (file 13).

## Caveats & follow-ups (honest limits of this pass)

- **Rewind search reachability, `localAgent` disable, BrainGraph `interactive` flag** — verified in code as of this audit; confirm they haven't been re-wired before treating as quick wins.
- **Citation metadata** — whether the Windows backend even sends citations to the client is a backend-contract question the UI audit couldn't resolve (files 04, 13).
- **Trial/paywall on Windows** — API types are generated but unused; may be a deliberate product decision (Windows unmetered), not a build gap — confirm before treating as a gap (file 12).
- **UI file 13** left 5 Mac visual files not fully read (CitationCardView, SpeakerBubbleView, AudioLevelWaveformView, Glow*Window mechanics, SpatialOverlayRenderGeometry) — listed in its "Follow-up needed" section; the highest-value items were covered directly.
- **`OMI_BYOK_*` plumbing** in the agent runtime appears unconsumed — possibly not-yet-wired or dead (file 04).
- This audit does **not** rank, sequence, or estimate. That is the next session's job (Fable 5 planning).
