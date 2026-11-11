# Mac→Windows Parity Audit — Memory, Persona & AI Profile

> **Re-audit stamp: 2026-08-22.** This file replaces the 2026-08-20 version in place. That version is materially stale: it was written against a Windows checkout that predates a five-week porting effort (`track3-ground-truth/gt-memextract-embeddings.md`, `gt-connectors.md`, `gt-coordinator.md`) which shipped a full proactive-assistant framework, continuous memory extraction, the AI User Profile, an embeddings index, three real connector-memory pipelines, and an MCP export/agent-connector system — all between **2026-07-14 and 2026-07-19**, i.e. four to five weeks *before* the old audit was written. Every "Absent" verdict below has been re-checked against current source with `git log` dates; see the callout immediately below for what changed.
>
> Scope: AI-driven memory extraction, the AI User Profile synthesis layer, the Persona (AI clone) feature, embeddings, and connector-based memory imports. Windows baseline checked (NOT reported as gaps, still true as of 2026-08-22): `desktop/windows/src/renderer/src/pages/Memories.tsx`, `src/renderer/src/hooks/useMemories.ts`, `src/renderer/src/lib/{memoriesBulk,memoryCleanup,memoryExtract}.ts`, `src/main/{memoryExport,memoryImport,memoryCleanup}/*`, `src/main/ipc/{memoryExport,memoryImport,memoryCleanup,kg,kgWorker}.ts`, `src/renderer/src/components/graph/BrainGraph.tsx`, `src/renderer/src/lib/knowledgeGraph*`. Knowledge-graph/file-index internals are another agent's area — cross-ref only.

## Changed since the 2026-08-20 audit

All eleven rows were re-verified; **seven of eleven changed status**, six of them from "Absent" to "Present" (fully or substantially). This is not new work done between the two audits — every item below was already in the repo on 2026-08-20 and had simply been missed or checked against a stale tree.

| Row | Old verdict (2026-08-20) | Corrected verdict (2026-08-22) | Shipped |
|---|---|---|---|
| Continuous AI memory extraction | Absent | **Present** — full port, coordinator-driven | 2026-07-15 (`f73c65e2`), interval retuned 2026-08-18 |
| Memory extraction settings & prompt editor | Absent | **Partial** — on/off toggle present, interval/confidence/excluded-apps/prompt editor still absent | toggle: 2026-07-15 |
| AI User Profile | Absent | **Present** — 5-source fetch, two-stage synthesis, full history, Settings CRUD UI | 2026-07-14 (`b1cc80a3`), synthesis moved server-side 2026-08-09 |
| Persona (AI clone) | Absent | **Absent** — unchanged, still no code anywhere | — |
| Embeddings / semantic similarity | Absent entirely | **Present** — two indexes (Rewind-OCR + task/action-item), faithful port incl. the 5000-vector cap | 2026-07-14/15 |
| Connector imports (Gmail/Calendar/Notes/X) | Absent for all four | **Present** for Gmail, Calendar, Windows Sticky Notes (the Apple-Notes analog), and X; smaller per-run scope than Mac | 2026-07-15 – 2026-07-17 |
| Live/MCP export & agent connectors | Absent — "3 static one-shot writers only" | **Present** — hosted MCP key, Claude Code/Codex/OpenClaw/Hermes config writers, ChatGPT/Claude cloud OAuth cards, Gemini/ChatGPT/Claude memory-pack rows | 2026-07-15 |
| `<about_user>` chat context card | Absent — "grep... returns nothing" | **Present** — a literal port (`lib/voice/aboutUser.ts`) for the voice/realtime surface, plus an architecturally-updated per-turn `<user_context>` block for main chat | 2026-07-14 and 2026-08-06 |
| Bidirectional assistant-settings sync | Absent (no-op consequence) | **Absent** — unchanged verdict, but now a real independent gap: there is extraction/profile state worth syncing, and Windows still only broadcasts settings locally across its own windows, never to the backend | — |
| Memory data model richness | Present-but-weaker (flat model) | **Present, materially richer** — `Memory` now carries tier/layer, capture-device provenance, confidence, `manually_added`, headline; still missing read/dismissed flags and a wired "this device" UI toggle | 2026-06-11 base + 2026-07-31 provenance fix |
| Paste-based memory-log import | Present (parity) | **Present (parity)** — unchanged | — |

**Most significant correction:** the old audit's own words called continuous screen-driven memory extraction "the single biggest driver of Mac's memory store growing without user effort" and then marked it entirely absent on Windows. It has existed, working, coordinator-gated, confidence-filtered, and dual-writing to SQLite + the backend, since **2026-07-15** — five weeks before the audit that called it missing was written. The same porting wave also shipped the embeddings index, the AI profile, and the MCP export system the same audit called absent, so this was not an isolated miss.

**A Mac-side citation that also turned out stale:** the old audit described Mac's `AIUserProfileService` doing its own two-stage Gemini synthesis locally in Swift, and Mac's `MemoryAssistant` defaulting to a 600s interval on Gemini Flash. Both are now wrong for Mac too, not just for the Windows comparison: Mac's synthesis moved behind the shared `POST /v1/users/ai-profile/synthesize` backend endpoint on 2026-08-09 (`AIUserProfileService.swift:249-253`, `92f2f331` — Windows calls the identical endpoint), and Mac's own memory-extraction default moved from 600s to 1800s on 2026-08-17 (`e40951a2d1`, three days before the old audit shipped) and from Gemini Flash to Flash-Lite. The old audit's Mac citations were current for neither platform by the time it was published.

---

## Summary table

| Feature | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Continuous AI memory extraction (screen-capture driven) | `ProactiveAssistants/Assistants/MemoryExtraction/MemoryAssistant.swift` | **Present** — `src/main/assistants/memory/memoryAssistant.ts` + `gemini.ts`/`models.ts`/`persist.ts`/`prompt.ts` | H (closed) |
| Memory extraction settings + custom prompt editor | `MemoryAssistantSettings.swift`, `UI/MemoryPromptEditorWindow.swift` | **Partial** — master toggle only, no interval/confidence/excluded-apps UI, no prompt editor | M |
| AI User Profile (daily synthesized "about the user" doc) | `Services/AIUserProfileService.swift` | **Present** — `src/main/assistants/aiUserProfile/{service,synthesis,orchestrate}.ts`, `AiProfileCard.tsx` | H (closed) |
| Persona (public AI clone others can chat with) | `MainWindow/Pages/PersonaPage.swift` | **Absent** | M |
| Embeddings / semantic similarity index | `Services/EmbeddingService.swift` | **Present** — `src/main/rewind/embeddingService.ts` (OCR text) + `src/main/tasks/taskEmbeddingService.ts` (action items/staged tasks) | M (closed) |
| Connector imports that *generate* memories (Gmail, Calendar, Sticky Notes, X) | `ConnectorImportOperations.swift`, `ConnectorImportRunner.swift` | **Present**, smaller per-run scope — `googleSync.ts`, `gmailExtract.ts`/`calendarExtract.ts`, `stickyNotesImport.ts`, `xConnector.ts`. No Apple Notes analog (Windows has none of that app; Sticky Notes fills the "local notes app" slot instead) | H (mostly closed) |
| Paste-based memory-log import (ChatGPT/Claude export) | (part of the connector sheet) `OnboardingMemoryLogImportService` | Present (ported) — `src/renderer/src/lib/memoryExtract.ts` | — (parity) |
| Live/MCP export + agent memory-bank connectors (Claude Code, Codex, OpenClaw, Hermes, hosted MCP, "Let Omi do it") | `MemoryExportDestinationSheet.swift`, `MemoryBankConnector.swift` | **Present** for the config-writer + hosted-MCP + cloud-OAuth + memory-pack tiers (`src/main/mcp/*`, `src/shared/mcpExports.ts`). **Absent**: the "Execute — let Omi do it" agent-task tier | M (mostly closed) |
| `<about_user>` context card injected into chat | `FloatingControlBar/AboutUserCard.swift` | **Present** — `src/renderer/src/lib/voice/aboutUser.ts` (literal port, voice surface) and `src/main/agentKernel/desktopChatPrompt.ts` + `src/main/ipc/mainChatPersonalization.ts` (per-turn equivalent, main chat) | M (closed) |
| Bidirectional assistant-settings sync (incl. memory settings) | `Services/SettingsSyncManager.swift` | **Absent** — settings broadcast locally across windows (`src/main/ipc/assistantSettings.ts`) but never round-trip to the backend | L |
| Memory data model richness (tiers, confidence, reasoning, device provenance, read/dismiss state) | `Rewind/Core/MemoryModels.swift`, `MemoryStorage.swift` | **Present, materially richer than the 2026-08-20 audit found** — see below | M |

---

## Continuous AI memory extraction

**What it is:** A background assistant that periodically looks at the user's screen and extracts durable facts ("memories") without any user action.

**Where (Mac):** `ProactiveAssistants/Assistants/MemoryExtraction/MemoryAssistant.swift`, `MemoryExtractionModels.swift`, `MemoryAssistantSettings.swift`.

**Where (Windows) — now present:** `src/main/assistants/memory/memoryAssistant.ts` (the `MemoryAssistant` class, a peer registered with the shared proactive-assistant coordinator — `src/main/assistants/core/coordinator.ts`, added 2026-07-14, `2ebe4586`), `src/main/assistants/memory/models.ts` (response schema + parse), `gemini.ts` (the model call), `prompt.ts` (system prompt), `persist.ts` (dual-write). First shipped 2026-07-15 (`f73c65e2`, "MemoryAssistant — faithful single-shot vision extraction port"); last touched 2026-08-18 (`88ae032c7b`, interval default retune).

**How it works today:** The coordinator (`coordinator.ts`) polls the latest captured Rewind frame on a tick and offers it to every registered assistant (Focus, Insight, Tasks, Goals, Memory), each independently gated. Memory's `isEnabled()` (`memoryAssistant.ts:52-55`) checks only the `memoryEnabled` setting (default **off** — opt-in, matching Mac's net off-by-default), decoupled from `notificationFrequency` on purpose: memory writes durable facts the user browses on the Memories page regardless of whether a toast ever fires, so gating it on the notification dial (which defaults to 0) would have silently starved the whole feature. `shouldAnalyze()` (`memoryAssistant.ts:57-66`) gates on a fixed extraction interval — `memoryExtractionIntervalMin`, now defaulting to **30 minutes** (`appSettings.ts:301`, retuned from 10 in `88ae032c7b` on 2026-08-18, three days after Mac made the identical change on 2026-08-17 in `e40951a2d1`). On a hit, `runPipeline()` (`memoryAssistant.ts:98-187`) pins the session epoch, reads the frame image, pulls the last 20 locally-stored memories as an in-prompt dedup list (`recentMemories(20)`, surviving app restarts unlike Mac's in-memory ring), and calls Gemini `2.5-flash-lite` (`gemini.ts:19` — matching Mac's own current model choice per `ModelQoS.Gemini.lightweight`, not the Flash model the old audit's Mac citation named) with a strict JSON response schema (`models.ts:29-54`, verbatim Mac shape: `has_new_memory`, `memories[]` with `content`/`category`/`source_app`/`confidence`, `context_summary`/`current_activity`). Only `memories[0]` is ever used (Mac's hard cap of 1); a bad `category` enum is dropped rather than coerced (`models.ts:63-73`). A confidence gate (`memoryMinConfidence`, default 0.7) filters low-confidence hits (`memoryAssistant.ts:147-155`) before any write. `MEMORY_SYSTEM_PROMPT` (`prompt.ts:9`) is the ~150-line curated categorization prompt ported line-for-line from `MemoryAssistantSettings.swift`, including the system-vs-interesting categorization test and the identity-verification rules. On acceptance, `persistMemory()` (`persist.ts:99-119`) writes a local `memories` SQLite row first (`ipc/db.ts:645-657` — `content, category, source_app, window_title, context_summary, confidence, screenshot_id, backend_id, backend_synced, created_at`), then fire-and-forget POSTs to `/v3/memories` with `source: 'desktop'` (`persist.ts:40-91`); `window_title` is deliberately never sent to the backend (raw titles are unfiltered PII), a deliberate Windows deviation from Mac (which does send it). A session-epoch guard, re-checked with no intervening `await`, prevents a memory formed under one signed-in user from landing in another's data across a sign-out mid-analysis. No notification ever fires for this assistant — it is silent by design.

**Deviations from Mac (all intentional, documented in-source):** memory extraction is gated on its own `memoryEnabled` toggle rather than piggybacking on `notificationsEnabled`; the dedup list is DB-backed rather than an in-memory ring; `window_title` is withheld from the backend sync.

**Value/notes:** Was High and reported Absent; is High and closed. The one remaining piece of this area (below) is the settings/prompt-editor surface, not the extraction pipeline itself.

---

## Memory extraction settings & prompt editor

**What it is:** User-facing controls for the extractor (enable/disable, interval, confidence threshold, notifications, excluded apps) plus a raw system-prompt editor.

**Where (Mac):** `MemoryAssistantSettings.swift`, `UI/MemoryPromptEditorWindow.swift`.

**Windows status — partial, corrected from "Absent":** A real on/off toggle exists: Settings → Notifications → "Extract memories from your screen" (`src/renderer/src/components/settings/tabs/NotificationsTab.tsx:123-137`), wired through the scoped `assistantSettings` IPC (`src/main/ipc/assistantSettings.ts:24-29`, whose `WRITABLE_KEYS` whitelist includes `memoryEnabled`) to `memoryAssistant.isEnabled()`. There is a dev-only force-run + gate-inspection IPC pair (`memory:analyzeNow`, `memory:debugIsEnabled`) in `register.ts:20-42`, non-prod only. What is still genuinely absent: `memoryExtractionIntervalMin`, `memoryMinConfidence`, and `memoryExcludedApps` (`appSettings.ts:106-113`) are real settings with sane Mac-parity defaults, but **no Settings UI reads or writes any of the three** — they can only be changed by hand-editing the settings store. There is also no `promptStore.ts` for Memory (Focus and Insight each have one at `assistants/{focus,insight}/promptStore.ts`; Memory does not), and grepping the whole renderer for a memory prompt editor returns nothing — the ~150-line curated prompt is a fixed constant with no user-facing edit surface, matching Mac's *content* but not its *editability*.

**Value/notes:** Medium, as before — the master toggle closing the "no way to turn this on" problem is the load-bearing half; the granular tuning UI and the prompt editor remain a real, still-open gap, now much smaller in scope than before.

---

## AI User Profile (`aiUserProfile/service.ts`)

**What it is:** A once-daily, LLM-synthesized "here is what we know about this user" document, re-injected as grounding context into other AI pipelines (chat, task/goal extraction) — not a raw memories list.

**Where (Mac):** `Services/AIUserProfileService.swift`.

**Windows status — corrected from "Absent" to Present:** `src/main/assistants/aiUserProfile/service.ts` (orchestration), `synthesis.ts` (pure cadence/cap helpers), `orchestrate.ts` (the pure generation core), `src/main/ipc/aiUserProfile.ts` (IPC surface: `aiProfile:setSession`, `:getLatest`, `:generateNow`, `:updateText`, `:delete`, `:deleteAll` — `ipc/aiUserProfile.ts:42-83`), and `src/renderer/src/components/settings/tabs/AiProfileCard.tsx` (Settings → Advanced preview/regenerate/inline-edit/delete UI). First shipped 2026-07-14 (`b1cc80a3`, "AI User Profile service (enabler)").

**How it works today:** `generateNow()` (`service.ts:320-353`) fetches five data sources in parallel over `net.fetch` against the backend (memories last-100, action items last-50, active goals, conversations from the past 7 days, and up to 30 recent AI-chat messages — `service.ts:162-234`), pins a session epoch so a sign-out mid-generation discards the result rather than writing a departed user's dossier into the freshly-wiped DB, and calls `runSynthesis()` (`service.ts:248-274`). Unlike the 2026-08-20 audit's description of Mac doing a local two-stage Gemini call, **synthesis is no longer client-side on either platform**: as of 2026-08-09 (`92f2f331`, "SSOT AI user profile synthesis for Mac and Windows") both apps POST the five source arrays plus up to 5 past profiles (oldest-first) to `POST /v1/users/ai-profile/synthesize` (`backend/routers/users.py:2116-2149`, which itself calls Haiku) and the backend returns the finished `profile_text`. The result (capped at `MAX_PROFILE_CHARS = 10000` locally, `synthesis.ts:16`) is stored in a local table with full history (`insertAiUserProfile`) and fire-and-forget synced back via `PATCH /v1/users/ai-profile` (`service.ts:283-314`). `shouldGenerate()` gates on >24h since the last successful generation (`synthesis.ts:32-35`); a 6-hour re-check timer plus a 6-hour minimum-attempt floor (`service.ts:48-62`) bound the retry rate for a persistently-failing account without needing exponential backoff. The Settings UI (`AiProfileCard.tsx`) supports Generate Now, inline edit + save, and delete (lines 37-43, 98-176) — full CRUD parity with what the old audit described on Mac, minus one narrow piece: Mac can also save an ad-hoc onboarding-exploration chat transcript directly as a profile record when none exists yet; grepping Windows for that specific path (`onboardingExploration`/`saveExploration`) finds nothing, so that one seed-path is still Mac-only.

**Value/notes:** Was High and reported Absent (with the backend client "generated but unused"); is High and closed — the backend client is now called, and the whole loop (generate → store → sync → edit/delete) is live.

---

## Persona (AI clone)

**What it is:** A separate product surface: the user builds a public-facing "AI clone" of themselves — name, username, avatar, description, and a generated chat prompt — built exclusively from memories explicitly marked public, that *other people* can converse with.

**Where (Mac):** `MainWindow/Pages/PersonaPage.swift`.

**Windows status — unchanged, confirmed still Absent as of 2026-08-22:** Grepping the current Windows source for `createPersona`/`getPersona`/`updatePersona`/`deletePersona`/`regeneratePersonaPrompt` returns nothing. The Windows generated OpenAPI client still carries only a stray `persona_prompt` field (`omiApi.generated.ts:255`) with zero callers — no persona routes were ever generated against. (One thing worth flagging precisely, since the old audit's grep for "persona" was noisy: the current codebase's many other "persona" hits — `chatApps.ts`, `ChatAppPicker.tsx`, `useChatApps.ts` — are the **App Store chat-app picker's** "chat OR persona capability" filter, an unrelated concept: picking an installed marketplace app to converse with, not building the user's own public clone. Don't mistake that subsystem for progress on this row; it isn't.)

**Value/notes:** Medium, unchanged — a genuinely separable, still-missing feature; not a dependency of anything else in this file.

---

## Embeddings / semantic similarity

**What it is:** Gemini-embedding-backed semantic similarity substrate: batch embedding generation, an in-memory cosine-similarity index, and a launch backfill for items missing a vector.

**Where (Mac):** `Services/EmbeddingService.swift`.

**Windows status — corrected from "Absent entirely" to Present:** Windows actually ships **two** embedding indexes, both faithful ports, both shipped 2026-07-14/15:
- `src/main/rewind/embeddingService.ts` + `embedVector.ts` + `embeddingClient.ts` + `embedQueue.ts` — indexes Rewind OCR text (the screen-history corpus), fed by a fire-and-forget enqueue on OCR completion, a 100-item/60s flush policy, and a capped, paced launch backfill (`BACKFILL_MAX_PER_LAUNCH = 5000`). This is Mac-parity for the *screen-history* half of embeddings, which is technically adjacent to (not identical to) Mac's `EmbeddingService` — Mac's service indexes tasks, not OCR text — but the primitives (`embedVector.ts`'s L2-normalize + dot-product cosine, the Gemini embedContent proxy call) are shared with the port below.
- `src/main/tasks/taskEmbeddingService.ts` — the direct port of Mac's `EmbeddingService` (the task half): an in-memory `Map`-based cosine index over `action_items` + `staged_tasks` vectors, capped at `MAX_INDEX_SIZE = 5000` (`taskEmbeddingService.ts:48`, matching Mac exactly), asymmetric `RETRIEVAL_DOCUMENT`/`RETRIEVAL_QUERY` embedding types, and the same oldest-evicted-first cap policy. It is wired into real callers, not dead code: `assistants/tasks/create.ts` and `assistants/tasks/toolBackends.ts` both call into it (confirmed via `searchSimilar`/`taskEmbeddingService` callers grep), for task-creation dedup-by-meaning and a semantic "find related tasks" tool path.

Both indexes are inert until the renderer relays a Firebase session, matching the same main/renderer token-split constraint the AI-profile service documents.

**Value/notes:** Was Medium and reported entirely absent (with `memoryRank.ts`'s lexical overlap offered as "the closest analog"); is Medium and closed — the semantic layer Mac's task/dedup features depend on now exists on Windows in the same shape.

---

## Connector imports that generate memories (Gmail, Calendar, Sticky Notes, X)

**What it is:** One-click "pull my data from an external source and turn it into memories" imports, distinct from *exporting* Omi memories elsewhere. Mac's pattern per connector: raw read → save-as-memories → an LLM synthesis pass for higher-level "follow-up insight" memories.

**Where (Mac):** `MainWindow/Pages/ConnectorImportOperations.swift`, `ConnectorImportRunner.swift`.

**Windows status — corrected from "Absent for all four" to Present for three of four, with a smaller per-run scope than Mac:**

- **Gmail** — two independent connectors now exist. An OAuth lane (`src/main/integrations/{oauth,google}.ts`, `oauth.ts`/`google.ts` reading Gmail metadata — Subject/From/snippet only, never bodies) drives `runGoogleSync()` (`src/renderer/src/lib/googleSync.ts:12-38`), which fetches up to 25 unprocessed emails from the last 7 days (`google.ts:24-39`), runs them through `extractGmailMemories()` → the shared backend "connector-synthesis SSOT" endpoint (`gmailExtract.ts:1-18`, `connectorSynthesis.ts`), dedups against existing memories, and posts each result to `/v3/memories` tagged `gmail/import/note`. A second lane, "Gmail (session)" (`src/main/integrations/gmailSession*.ts`), replays the user's own signed-in Google web session's cookies (no OAuth scopes) to read recent mail — currently wired to a manual "Fetch recent" action in Settings → Integrations rather than the synthesis pipeline. Both surfaces are visible in `IntegrationsTab.tsx` and the Home Hub Connections panel. Scope is materially smaller than Mac's (25 emails/7 days vs. Mac's 300 emails/365 days).
- **Calendar** — `fetchCalendar()` (`google.ts:41-59`) reads the next 14 days, up to 50 events (vs. Mac's 365-back/30-forward, 500-event window); `syncCalendar()` (`googleSync.ts:46-73`) runs them through `extractCalendarTasks()` and writes deduped `/v1/action-items` rows, not memories — a deliberate Windows framing difference (calendar → tasks, not calendar → memories) noted in the "Connect" copy itself ("Turn recent email... into memories and upcoming events into tasks" — `IntegrationsTab.tsx:200`).
- **Windows Sticky Notes** (the Apple-Notes analog; there is no Notes-app equivalent on Windows, so this fills the same "local notes app" role) — `src/main/integrations/stickyNotes.ts` (reader) + `src/renderer/src/lib/stickyNotesImport.ts` (`readAndExtractStickyNotes()`/`importStickyMemories()`) generate a synthesized profile blurb plus a reviewable list of candidate memories before import (`IntegrationsTab.tsx:16-62`), matching Mac's raw-read-then-synthesize shape closely, including a user-facing review step before commit.
- **Google connector background behavior**: `useGoogleConnection.ts` runs sync-on-connect plus a 15-minute background auto-resync as a module-scope singleton shared across every mount (Settings tab + Home Hub card), so a connected account keeps ingesting without the Settings page staying open — closer to Mac's always-on connector model than a one-shot manual import.
- **X (Twitter)** — `src/main/integrations/xConnector.ts`, shipped 2026-07-15 (`a5cb0cd9`): backend-mediated OAuth exactly as the old audit described for Mac, with the UI polling live `postCount`/`memoryCount` (`xConnector.ts:26,57-65`) until the backend's ingest finishes — the backend performs the actual ingest, matching Mac's design.

What remains genuinely absent: **Apple Notes has no Windows analog** (unchanged — no macOS Notes app exists on Windows to read), and there is no local-file-rescan-delta connector.

**Value/notes:** Was High and reported entirely absent; is High and mostly closed. The real remaining gap is scope (email/event windows are far smaller than Mac's, and the session-based Gmail lane isn't yet wired to memory synthesis), not existence.

---

## Live/MCP export & agent "memory-bank" connectors

**What it is:** Beyond static file export, Mac exposes Omi memory as a **live** data source other tools/agents can query continuously, via a hosted MCP server plus deterministic local config-file wiring for coding-agent CLIs, plus an "Execute — let Omi do it" autonomous-agent tier.

**Where (Mac):** `MainWindow/Pages/MemoryExportDestinationSheet.swift`, `MemoryBankConnector.swift`.

**Windows status — corrected from "Absent — 3 static one-shot writers only" to Present for two of three tiers:** An entire `src/main/mcp/` subsystem (11 files: `mcpExportsService.ts`, `claudeConfig.ts`, `cliConnectors.ts`, `cloudConnectors.ts`, `mcpKeyStore.ts`, `mcpMintClient.ts`, `memoryPack.ts`, `atomicWrite.ts`, `cliPresence.ts`) plus `src/shared/mcpExports.ts` shipped 2026-07-15 (`2a8e7393`, `2f56f314`). Confirmed present:
- **Hosted MCP key + config writers** — `MCP_SERVER_KEY = 'omi-memory'` (`mcpExports.ts:12`) written into Claude Code's `~/.claude.json` (with backup/pruning, `claudeConfig.ts`) and, via `cliConnectors.ts`, into Codex (`codex mcp add omi-memory -- npx -y mcp-remote ...`), OpenClaw (`~/.openclaw/openclaw.json` + `openclaw mcp reload` + a `SOUL.md` note, `cliConnectors.ts:100-181`), and Hermes (`~/.hermes/config.yaml` + its own `SOUL.md` note, `cliConnectors.ts:110,183-185`) — all four of the CLIs the old audit named on Mac, gated behind an on-disk CLI-presence check (`cliPresence.ts`) exactly as Mac gates them.
- **Cloud OAuth connector cards** — `cloudConnectors.ts` + `McpCloudConnectorCard.tsx` for ChatGPT/Claude, per the 2026-07-15 commit title "cloud assisted connectors (ChatGPT/Claude OAuth cards)".
- **Memory-pack (manual copy) tier** — `memoryPack.ts`, covering Gemini/ChatGPT/Claude copy-paste rows, closing the old audit's specific complaint that Windows had "not even the manual-copy tier."
- **UI surface** — a full Home Hub → Connections panel (`components/home/hub/connections/{McpConfigConnectorRow,McpCloudConnectorCard,McpExportDetail,ExportsConnector}.tsx`), driven by `useMcpExports.ts` — this is the Windows equivalent of Mac's `MemoryExportDestinationSheet`.

What is still absent: grepping this whole subsystem for anything resembling Mac's **"Execute — let Omi do it"** tier (handing the entire MCP setup off to an autonomous Omi agent task) returns nothing — that one tier of the three Mac offers has no Windows equivalent.

Separately, the original three-writer file the old audit cited (`src/main/ipc/memoryExport.ts` — Notion/Obsidian/plain-`.md`) is untouched since the 2026-06-11 initial import; it appears to be a distinct, still-valid feature (the original static export destinations) that coexists with, rather than having been replaced by, the new MCP subsystem.

**Value/notes:** Was Medium and reported entirely absent; is Medium and mostly closed — Windows users doing agentic coding work now do have a path to live Omi-memory access from their CLI agents. The one remaining tier (autonomous "let Omi do it" setup) is a real but narrower gap than before.

---

## `<about_user>` chat context card

**What it is:** A small, local-only, no-network context block — name, top memory facts, task counts — pre-rendered and injected into an AI chat surface's grounding context, so the assistant has baseline user grounding without a tool call on every turn.

**Where (Mac):** `FloatingControlBar/AboutUserCard.swift`.

**Windows status — corrected from "grep returns nothing" to Present, in two forms:**

1. **A literal, near line-for-line port for the voice/realtime surface**: `src/renderer/src/lib/voice/aboutUser.ts`, shipped 2026-07-14 (`0f31c6b9`, "rich session system instructions + about_user card [Track 2 A9]"). `renderAboutUserCard()` (`aboutUser.ts:31-49`) emits a `<about_user>` block — name, up to 8 memory facts truncated to 120 chars each (`MAX_FACTS`/`FACT_MAX_CHARS`, lines 17-18), and an overdue/due-today task-count line — ending in the same tool-deferral hedge Mac uses ("this is a quick snapshot — for the exact or current list, call get_action_items", adapted to the tools Windows' voice surface actually advertises). It is cached per-uid with a 5-minute TTL and refreshed off the hot path (`getAboutUserCard()`/`refreshAboutUserCard()`, lines 107-164), exactly mirroring Mac's cached-ivar, warmed-off-hot-path design. `lib/voice/systemInstruction.ts` cites and depends on it directly for the voice model's grounding and its "answer from `<about_user>`, don't call a tool" routing rule.
2. **A per-turn equivalent for the main desktop chat**, architecturally different from a literal about_user tag but delivering the same substance: `src/main/agentKernel/desktopChatPrompt.ts`'s `buildDesktopChatPersonalization()` (lines 264-304) renders a `<user_context>` block with `<user_facts>` (30 most-recent memories), `<user_tasks>` (20 active tasks with priority/due/category), and `<ai_user_profile>` (the latest AI User Profile text) — explicitly a faithful port of Mac's `ChatProvider.swift` formatters, deliberately delivered per-turn rather than baked into the system prompt (unlike Mac) so the system-prompt hash stays stable across a chat session and the underlying `pi` subprocess binding doesn't restart every message (rationale documented at `desktopChatPrompt.ts:166-194`). `src/main/ipc/mainChatPersonalization.ts` (`readTurnPersonalization()`) assembles the impure reads and feeds `mainChat.ts`, which prepends the block to every turn (`mainChat.ts` around lines 90-100). Shipped 2026-08-06.

**Value/notes:** Was Medium and reported entirely absent; is Medium and closed on substance for both chat surfaces the app has. Worth flagging precisely for whoever re-audits chat/voice next: the voice-surface port is a literal tag-for-tag match; the main-chat version is a deliberate architectural adaptation (per-turn vs. system-prompt) that a future auditor should not mistake for a gap just because the mechanism differs from Mac's.

---

## Bidirectional assistant-settings sync

**What it is:** Server-authoritative two-way sync of all proactive-assistant settings (shared cooldown/analysis-delay toggles, plus per-assistant Focus/Task/Insight/Memory settings) between local storage and the backend.

**Where (Mac):** `Services/SettingsSyncManager.swift`.

**Windows status — confirmed still Absent, but the reasoning has changed:** `src/main/ipc/assistantSettings.ts` is real and does keep every open window's Settings UI in lock-step with the tray checkbox (`projectAssistantSettings()`, a whitelisted local broadcast over `WRITABLE_KEYS`), but this is **local multi-window sync only** — there is no call anywhere in Windows source to a backend `assistant-settings`/`assistant_settings` endpoint (confirmed by grep across `src/main` and `src/renderer`); `omiApi.generated.ts` carries the field names as unused strings only, same as the old audit found. The old audit filed this as a non-independent consequence of "there's no proactive-assistant framework to have settings for." That framing no longer holds: the framework (Focus/Insight/Tasks/Goals/Memory, all coordinator-registered) now fully exists on Windows, with real settings worth syncing (`memoryEnabled`, `memoryExtractionIntervalMin`, `aiProfileEnabled`, etc.) — so this is now a standalone gap in its own right, not a shadow of a bigger missing feature.

**Value/notes:** Low, as before — the value tier is unchanged, but the framing is: this is no longer "nothing to sync," it's "something to sync, still not synced across devices/backend."

---

## Memory data model richness

**What it is:** How much information a stored memory carries beyond its text.

**Where (Mac):** `Rewind/Core/MemoryModels.swift`, `MemoryStorage.swift`.

**Windows status — corrected from "flat model" to materially richer, still short of full parity:** The old audit's citation (`useMemories.ts`'s `Memory` type) is the right file but was read at a stale revision. As of `a1ea7b12e8` (2026-07-31, "preserve memory provenance") the type (`hooks/useMemories.ts:7-32`) carries: `layer`/`memory_tier` (the canonical lifecycle tier — short_term/long_term/etc. — derived from the backend's `memory_tier` field, with the same "null for legacy/untiered rows, badge hidden unless the server advertises tier exposure" rule Mac uses for `tierIsExplicit`), `primary_capture_device` + `capture_device_ids` (multi-device provenance), `manually_added`, `capture_confidence`, `app_id`, and an `evidence` array with `source_type`. The Memories page (`pages/Memories.tsx`) has a working `layer` filter (lines 167, 299-322, gated on `canonicalLifecycleExposed` exactly like Mac gates its tier badge) and a `filterMemories()` helper (`lib/memoryFilters.ts:139-160`) that already implements this-device matching (`matchesThisDevice()`, checking both `primary_capture_device` and `capture_device_ids`) — separately from the backend-fetched list, the **locally-extracted** `memories` SQLite table populated by the Memory assistant (`ipc/db.ts:645-657`) independently carries `confidence`, `source_app`, `context_summary`, and `screenshot_id`, i.e. exactly the extraction-provenance fields the old audit said were "meaningless without the extraction pipeline that populates them" — that pipeline now exists and populates them.

What is still genuinely missing relative to Mac: no `isRead`/`isDismissed` status flags anywhere in the Windows type or schema; and while the filter *logic* for "this device only" exists and is tested, the Memories page's actual call site hardcodes `thisDeviceOnly: false` (`Memories.tsx:318`) — there is no wired UI toggle/chip exposing it to the user, so the capability is built but not reachable.

**Value/notes:** Medium, downgraded in severity from the old audit — most of the richness gap (tier, device provenance, confidence, manually-added) is closed; the read/dismiss flags and the missing "this device" UI toggle are the real remainder.

---

## Spotted outside my scope

- File index / knowledge graph internals (`src/main/ipc/kg*.ts`, `BrainGraph.tsx`, `knowledgeGraphClient.ts`) — another agent's area; unchanged from the prior audit's note.
- Backend moderation pipeline implied by Persona's `under-review`/`rejected` status badge on Mac — still unverified, still out of scope, and now moot for Windows sequencing since Persona itself remains wholly unbuilt there.
- The Gmail "session" (cookie-replay) connector currently reads mail but does not yet feed the memory-synthesis path the OAuth lane uses — worth a follow-up check by whoever owns Windows integrations next, since it's a small gap to close given the OAuth lane's synthesis code already exists and could likely be shared.
- Whether the `track2-groundtruth`/`track3-ground-truth` planning docs in this same directory describe further scoped-down work Windows hasn't caught up on yet (e.g. `gt-memextract-embeddings.md` may specify more than what shipped) — worth a diff pass, but out of scope for this re-audit, which verified only against current source.
