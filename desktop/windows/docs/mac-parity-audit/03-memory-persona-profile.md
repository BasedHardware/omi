# Mac→Windows Parity Audit — Memory, Persona & AI Profile

> Scope: AI-driven memory extraction, the AI User Profile synthesis layer, the Persona (AI clone) feature, embeddings, and connector-based memory imports. Windows baseline checked (NOT reported as gaps): `desktop/windows/src/renderer/src/pages/Memories.tsx`, `src/renderer/src/hooks/useMemories.ts`, `src/renderer/src/lib/{memoriesBulk,memoryCleanup,memoryExtract}.ts`, `src/main/{memoryExport,memoryImport,memoryCleanup}/*`, `src/main/ipc/{memoryExport,memoryImport,memoryCleanup,kg,kgWorker}.ts`, `src/renderer/src/components/graph/BrainGraph.tsx`, `src/renderer/src/lib/knowledgeGraph*`. Knowledge-graph/file-index internals are another agent's area — cross-ref only.

## Summary table

| Feature | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Continuous AI memory extraction (screen-capture driven) | `ProactiveAssistants/Assistants/MemoryExtraction/MemoryAssistant.swift`, `MemoryExtractionModels.swift` | **Absent** | H |
| Memory extraction settings + custom prompt editor | `MemoryAssistantSettings.swift`, `UI/MemoryPromptEditorWindow.swift` | **Absent** | M |
| AI User Profile (daily synthesized "about the user" doc) | `Services/AIUserProfileService.swift` | **Absent** | H |
| Persona (public AI clone others can chat with) | `MainWindow/Pages/PersonaPage.swift` | **Absent** | M |
| Embeddings / semantic similarity index | `Services/EmbeddingService.swift` | **Absent** | M |
| Connector imports that *generate* memories (Gmail, Calendar, Apple Notes, X) | `MainWindow/Pages/ConnectorImportOperations.swift`, `ConnectorImportRunner.swift` | **Absent** | H |
| Paste-based memory-log import (ChatGPT/Claude export) | (part of the connector sheet) `OnboardingMemoryLogImportService` | Present (ported) — `src/renderer/src/lib/memoryExtract.ts` | — (parity) |
| Live/MCP export + agent memory-bank connectors (Claude Code, Codex, OpenClaw, Hermes, hosted MCP, "Let Omi do it") | `MemoryExportDestinationSheet.swift`, `MemoryBankConnector.swift` | **Absent** — Windows has 3 static one-shot writers only (Notion, Obsidian, plain `.md`) | M |
| `<about_user>` context card injected into chat | `FloatingControlBar/AboutUserCard.swift` | **Absent** | M |
| Bidirectional assistant-settings sync (incl. memory settings) | `Services/SettingsSyncManager.swift` | **Absent** (nothing to sync — no proactive extraction exists) | L |
| Memory data model richness (tiers, confidence, reasoning, device provenance, read/dismiss state) | `Rewind/Core/MemoryModels.swift`, `MemoryStorage.swift` | **Present-but-weaker** — flat model, see below | M |

---

## Continuous AI memory extraction

**What it is:** A background assistant that periodically looks at the user's screen and extracts durable facts ("memories") without any user action — the core of how Mac desktop builds up its memory store passively, as opposed to memories only coming from conversation transcripts.

**Where (Mac):** `ProactiveAssistants/Assistants/MemoryExtraction/MemoryAssistant.swift` (the actor/loop), `MemoryExtractionModels.swift` (result schema), `MemoryAssistantSettings.swift` (config).

**How it works:** `MemoryAssistant` is one of several "proactive assistants" fed periodic screen captures. It buffers the latest captured frame, waits for `extractionInterval` (default 600s/10min) to elapse since the last analysis, then sends the JPEG frame + a long curated system prompt to Gemini Flash (vision) with a strict JSON response schema (`has_new_memory`, up to 3 candidate `memories[]` each with `content`/`category`/`source_app`/`confidence`, plus `context_summary`/`current_activity`). Only the single highest-value memory is kept per analysis (explicit "extract at most 1" instruction; empty result is the expected common case). The prompt enforces a hard categorization test — **system** (a fact about the user) vs **interesting** (external wisdom *with attribution*, e.g. "Paul Graham (article): ...") — and bans hedging language, current-activity descriptions, and trivial/generic facts. The last 20 extracted memories are fed back into the prompt each cycle so the model avoids semantic re-extraction. A confidence threshold (default 0.7) filters low-confidence hits. Apps can be excluded (built-in list + user custom list + Rewind privacy exclusions). On acceptance: saved to local SQLite first (`MemoryStorage.insertLocalMemory`, local-first), then synced to the backend (`APIClient.createMemory`) and the local record updated with the backend id; optionally a system notification is sent; an analytics event fires.

**Windows status:** Absent. Windows has no screen-capture pipeline feeding a memory extractor at all — no equivalent of the Mac "proactive assistants" concept (Memory/Focus/Task/Insight) exists on Windows for memory specifically. `src/renderer/src/lib/memoryExtract.ts` on Windows is *not* this — it is a one-shot LLM extraction over a **user-pasted** ChatGPT/Claude "what do you remember about me" export (see the "paste-based import" row below), not a recurring autonomous screen-derived extractor.

**Value/notes:** High — this is the single biggest driver of Mac's memory store growing without user effort. Cross-ref: Windows' capture+VAD pipeline exists for conversation/meeting purposes per the stated baseline, but nothing consumes screen frames for memory extraction.

---

## Memory extraction settings & prompt editor

**What it is:** User-facing controls for the above (enable/disable, interval, confidence threshold, notifications, excluded apps) plus a raw system-prompt editor so power users can rewrite the extraction instructions.

**Where (Mac):** `MemoryAssistantSettings.swift` (UserDefaults-backed settings singleton with a ~150-line default prompt baked in), `UI/MemoryPromptEditorWindow.swift` (a dedicated `NSWindow` with a monospaced `TextEditor`, unsaved-changes indicator, reset-to-default confirmation).

**How it works:** All settings persist to `UserDefaults`, broadcast `.assistantSettingsDidChange` on write, and round-trip through `SettingsSyncManager` to the backend (server value wins on pull).

**Windows status:** Absent — no settings surface exists because there is no extraction assistant to configure.

**Value/notes:** Medium — meaningful only once/if extraction itself is ported; tracked together with it.

---

## AI User Profile (`AIUserProfileService`)

**What it is:** A once-daily, LLM-synthesized "here is what we know about this user" document — distinct from the raw memories list. It's explicitly built to be re-injected as grounding context into *other* AI pipelines (task/goal/memory extraction), i.e. it's infrastructure, not just a UI feature.

**Where (Mac):** `Services/AIUserProfileService.swift`.

**How it works:** An actor (`AIUserProfileService.shared`) checks `shouldGenerate()` (>24h since the last stored profile). On generation it fetches five data sources in parallel via `APIClient`: memories (last 100), action items/tasks (last 50), active goals, conversations from the past 7 days, and recent AI chat messages (last 30). It builds a data-dump prompt and calls Gemini (stage 1) with a strict system prompt: output is a flat bullet list of *only* facts directly evidenced in the data, third person, no adjectives/personality claims, no hallucinated names/emails/contacts, capped at 2000 characters. Stage 2 then consolidates that fresh profile against up to 5 past stored profiles (oldest→newest) so the profile *accumulates* stable knowledge (name, role, company, tech stack, key relationships) while dropping stale/completed items — again capped at 2000 chars, again hallucination-guarded. The result is stored in a local GRDB table (`ai_user_profiles`: `profileText`, `dataSourcesUsed`, `generatedAt`, `backendSynced`) so **full history** is kept, and fire-and-forget synced to the backend (`APIClient.syncAIUserProfile`). The service also supports manual edits to a stored profile (`updateProfileText`), deleting individual profiles, deleting all profiles, and saving an ad-hoc "exploration" (chat-generated) text directly as a new profile record when none exists yet.

**Windows status:** Absent. `src/renderer/src/lib/userProfile.ts` on Windows is unrelated — it's onboarding-wizard identity plumbing (sync display name to Firebase Auth, sync language preference, sync recording consent), not a synthesized "about the user" doc. Backend support exists and is even present in the generated OpenAPI client (`omiApi.generated.ts`: `AIUserProfileResponse`, `UpdateAIUserProfileRequest`, `get_ai_profile_v1_users_ai_profile_get`, `update_ai_profile_v1_users_ai_profile_patch`), but grep confirms **zero callers** of those functions anywhere in the Windows app — the client is generated but unused.

**Value/notes:** High — this is a distinct, load-bearing layer (context-for-context) that nothing else in the codebase substitutes for; the backend endpoint being ready but wired up nowhere on Windows makes it a comparatively cheap, high-value gap to close relative to porting the vision-extraction pipeline.

---

## Persona (AI clone)

**What it is:** A separate product surface from personal memory: the user builds a public-facing "AI clone" of themselves — name, username, avatar, description, and a generated chat prompt — that *other people* can converse with to learn about the user. Built exclusively from memories the user has explicitly marked **public**.

**Where (Mac):** `MainWindow/Pages/PersonaPage.swift`.

**How it works:** Full CRUD against backend endpoints via `APIClient`: `getPersona`, `createPersona(name:username:)` (with live username-availability checking, 3-30 chars, lowercase+digits+underscore), `updatePersona(name:description:)`, `deletePersona`, and `regeneratePersonaPrompt()` (re-derives the persona's chat prompt from current public memories, reporting `memoriesUsed`). UI shows a status badge (`approved` / `under-review` / `rejected` / other — implying a backend moderation step), a public-memory count stat, and a "Persona Prompt" generated/not-generated stat with a collapsible raw-prompt preview.

**Windows status:** Absent. No persona concept anywhere in Windows source (grep for "persona" only hits an unrelated CDN asset URL `personas.omi.me/omilogo.png` used as a logo image, an unused `persona_prompt` field in the generated OpenAPI types, and comment prose containing the word "personalize" — no actual persona endpoints exist in the Windows generated API client at all, i.e. this client wasn't even generated against persona routes).

**Value/notes:** Medium — a distinct, separable feature (not a dependency of core memory) that some users may not know exists; lower urgency than the AI Profile since it's outward-facing rather than infrastructure other pipelines depend on.

---

## Embeddings / semantic similarity (`EmbeddingService`)

**What it is:** Gemini-embedding-backed (3072-dim) semantic similarity substrate: single/batch embedding generation through the backend proxy, an in-memory cosine-similarity index (Accelerate/vDSP-accelerated, capped at 5000 vectors) built over `action_items` + `staged_tasks`, and a backfill routine that embeds any items missing a vector.

**Where (Mac):** `Services/EmbeddingService.swift`.

**How it works:** `embed(text:taskType:)` / `embedBatch(texts:taskType:)` POST to `v1/proxy/gemini/models/{model}:embedContent(s)` with a Firebase auth header; results are L2-normalized so cosine similarity reduces to a dot product (`vDSP_dotpr`). `loadIndex()` hydrates the in-memory index from SQLite BLOB columns at startup; `searchSimilar(query:topK:)` does linear-scan cosine ranking. Note this indexes **tasks/staged-tasks**, not memories directly — but it's the general-purpose semantic layer the rest of the Mac app (and potentially future memory dedup/search) draws on.

**Windows status:** Absent entirely — no embedding calls, no vector storage, no semantic index anywhere in Windows source (`grep -i embedding` returns nothing outside this audit). The closest Windows analog is `src/renderer/src/lib/memoryRank.ts`, a pure lexical/token-overlap ranker (stopword-filtered token-set intersection, no ML) used to correlate onboarding folder/project names against saved memories — a much cruder heuristic, not a semantic substitute.

**Value/notes:** Medium — no immediate UI depends on it on Mac (it backs task similarity, not a memory-facing feature directly), but it's the missing building block for any future Windows memory/task dedup-by-meaning or "find related" feature.

---

## Connector imports that generate memories (Gmail, Calendar, Apple Notes, X)

**What it is:** One-click "pull my data from an external source and turn it into memories" imports — distinct from *exporting* Omi memories elsewhere. Each connector reads recent data, saves raw items as memories, and additionally runs an LLM synthesis pass to generate higher-level "follow-up insight" memories from that raw data.

**Where (Mac):** `MainWindow/Pages/ConnectorImportOperations.swift` (per-connector logic), `ConnectorImportRunner.swift` (run-state manager so progress/success/failure survive the sheet closing).

**How it works:** Each connector follows the same raw-import + synthesis pattern:
- **Gmail** — reads up to 300 emails from the last 365 days (`GmailReaderService`), saves them as raw memories, then runs an LLM synthesis pass over the batch for higher-level memories.
- **Calendar** — reads events 365 days back / 30 days forward (up to 500), same raw+synthesis pattern (`CalendarReaderService`).
- **Apple Notes** — reads up to 250 recent notes (`AppleNotesReaderService`), with a folder-picker fallback flow when Notes' data folder needs explicit access (macOS-only permission model).
- **X/Twitter** — backend-mediated OAuth (deep-link callback + polling), where the backend itself performs the first ingest; the UI polls `xConnectionStatus()` live for post/memory counts until the backend clears its `syncing` flag.
- **Local file rescan** — re-triggers the file index scan and reports the delta vs. before.

`ConnectorImportRunner` is a small `ObservableObject` that owns in-flight run tasks keyed by connector id, so a run survives the sheet being closed/reopened, dedupes concurrent starts per connector, and retains failure state until acknowledged.

**Windows status:** Absent for Gmail/Calendar/Apple Notes/X. Windows has no Google/Apple account readers, no OAuth-mediated X import, and no raw-import-plus-LLM-synthesis pipeline. The one piece of this area Windows *does* have is the manual paste path: `src/renderer/src/lib/memoryExtract.ts` is an explicit, faithful port of the macOS **paste-a-ChatGPT/Claude-export** flow (`OnboardingMemoryLogImportService`) — same 40k-char cap, same JSON extraction contract, same dedup-against-existing-memories behavior — reachable from Settings, not just onboarding. `src/main/memoryImport/parse.ts` is a local (non-LLM) fallback parser for the same paste flow. This is real, working parity for *that one* import path — it is not a gap.

**Value/notes:** High — Gmail/Calendar/Notes/X are the main "seed my memory automatically" paths beyond conversations; Apple Notes specifically has no Windows equivalent (no direct macOS Notes analog exists, but OneNote/Outlook-equivalent readers are conspicuously absent).

---

## Live/MCP export & agent "memory-bank" connectors

**What it is:** Beyond static file export, Mac exposes Omi memory as a **live** data source other tools/agents can query continuously — via a hosted MCP server plus deterministic local config-file wiring for popular coding-agent CLIs — and an "Execute — let Omi do it" flow that hands the whole setup to an autonomous Omi agent task.

**Where (Mac):** `MainWindow/Pages/MemoryExportDestinationSheet.swift` (UI: MCP setup fields, OAuth connector fields for Claude, "agent setup" combined MCP+CLI prompt, execute/assisted/manual tiers, live connection-status polling), `MemoryBankConnector.swift` (deterministic local writers).

**How it works:** `MemoryExportDestinationSheet` offers, per destination, up to three tiers: (1) **Execute** — "Let Omi do it", which hands off to an Omi agent task via the standard task-execution path; (2) **Live/MCP connection** — hosted MCP server URL + a per-user bearer key (`ensureMCPKey`), with destination-specific setup steps (e.g. Claude gets full "Add custom connector" form fields including OAuth client id); (3) **Memory pack** — the manual copy/paste snapshot fallback (this tier is the parity Windows already has, mapped to Notion/Obsidian/plain-file). Separately, `MemoryBankConnector` does deterministic **local file writes** (no LLM, no agent) to wire MCP into installed coding-agent CLIs it detects on disk: Claude Code (`~/.claude.json` → `mcpServers.omi-memory`, with automatic config backup/pruning), Codex (`codex mcp add omi-memory -- npx mcp-remote ...` via CLI), OpenClaw (`~/.openclaw/openclaw.json` + a "search Omi first" note injected into the agent's `SOUL.md` system prompt), and Hermes (`~/.hermes/config.yaml` `mcp_servers:` block + same `SOUL.md` note pattern). Each connector also runs a post-write verification check (`MemoryExportConnectionDetector`) before reporting success.

**Windows status:** Absent — `src/main/ipc/memoryExport.ts` wires exactly three IPC handlers: `memoryExport:obsidian` (vault file write), `memoryExport:file` (save-as `.md`), `memoryExport:notion` (one-shot API write via token+parent-page-id). No MCP server surface, no bearer-key generation, no agent-CLI config detection/wiring, no "Execute with Omi" task-based setup, and no ChatGPT/Claude/Gemini "memory pack" prompt-copy destinations (Mac has these as manual-pack options; Windows has none of them, not even the manual-copy tier).

**Value/notes:** Medium — this is the mechanism by which a user's coding agents (Claude Code, Codex, etc. — directly relevant given this repo's own agent-heavy workflow) get live access to Omi memory; Windows users doing agentic coding work have no path to this today.

---

## `<about_user>` chat context card

**What it is:** A small, local-only, no-network context block — name, top memory facts, task overdue/due-today counts — pre-rendered and injected into the AI chat's warm system instruction, so the assistant has baseline user grounding without needing a tool call on every turn.

**Where (Mac):** `FloatingControlBar/AboutUserCard.swift`.

**How it works:** `AboutUserCard.build()` pulls the Firebase auth display/given name, the 8 most recent local memories (truncated to 120 chars each, via `MemoryStorage.getLocalMemories`), and task counts (`TasksStore.overdueTasks`/`todaysTasks`), then renders a fixed-format `<about_user>...</about_user>` block that explicitly hedges itself ("this is a quick snapshot — for the exact/current list, call get_tasks / get_action_items") so the model knows to defer to tools for anything precise. `render()` is a pure/unit-testable formatter kept separate from the data-gathering `build()`.

**Windows status:** Absent — grep for `about_user`/`aboutUser` returns nothing in Windows source. Windows chat has no memory-grounded pre-context injection of this kind (whether Windows chat compensates via live tool calls for user/memory context is outside this audit's scope, but this specific low-latency local mechanism does not exist).

**Value/notes:** Medium — small in code size but directly affects chat quality/latency trade-off (avoids a tool round-trip for basic "who is this user" grounding).

---

## Bidirectional assistant-settings sync

**What it is:** Server-authoritative two-way sync of all "proactive assistant" settings (shared cooldown/analysis-delay/screen-analysis toggles, plus per-assistant Focus/Task/Insight/**Memory** settings: enabled, prompt, interval, confidence, notifications, excluded apps) between local UserDefaults and the backend.

**Where (Mac):** `Services/SettingsSyncManager.swift`.

**How it works:** `syncFromServer()` pulls `APIClient.getAssistantSettings()` and applies any non-nil remote field over local state (server wins); `syncToServer()` / `pushPartialUpdate()` push the reverse direction. Includes a lazy-dev-bundle carve-out that keeps a local `false` seed for `screenAnalysisEnabled` regardless of server value, so named test bundles don't silently start screen capture.

**Windows status:** Absent, but only because there is nothing to sync — Windows has no proactive-assistant framework (Memory/Focus/Task/Insight extraction) at all, so this gap is a direct consequence of the "Continuous AI memory extraction" gap above rather than an independent missing feature. Windows source shows `settingsSync`/`assistantSettings` only as unused strings inside the generated OpenAPI client.

**Value/notes:** Low standalone value — tracked only so it isn't forgotten if/when extraction assistants are ported to Windows; do not build this in isolation.

---

## Memory data model richness

**What it is:** How much information a stored memory carries beyond its text.

**Where (Mac):** `Rewind/Core/MemoryModels.swift` (`MemoryRecord`, local GRDB schema), `MemoryStorage.swift` (query/sync layer).

**How it works:** Mac's `MemoryRecord`/`ServerMemory` carries: a lifecycle **tier/layer** (`short_term` / `long_term` / `archive`, with an explicit-vs-implicit flag so legacy untiered rows don't show a stale badge), `confidence` + `reasoning` (extraction provenance), `sourceApp`/`windowTitle`/`contextSummary`/`currentActivity` (what was on screen when extracted), `inputDeviceName` + `primaryCaptureDevice`/`captureDeviceIds` (multi-device provenance, backing the Memories page's "This device" filter), `isRead`/`isDismissed` status flags, `manuallyAdded`, `scoring`, `userReview`, `headline`, and tag-based sub-classification (`insights`, `focus`, etc. on top of the base category). The Memories page (`MemoriesPage.swift`) filters on tier (Default/Short-term/Long-term/Archive), device scope, category, tags, and full-text search, all backed by local SQLite for instant response plus background API sync/reconciliation.

**Windows status:** Present-but-weaker. `src/renderer/src/hooks/useMemories.ts`'s `Memory` type is flat: `id, uid, content, headline, category, visibility, tags, created_at, updated_at, conversation_id`. No tier/layer field (no Short-term/Long-term/Archive concept or filter), no confidence/reasoning/extraction-provenance fields (expected, since there's no local extraction producing them), no per-device capture provenance or "this device" filter, no read/dismissed status. Windows fetches a flat page of up to 500 memories (`/v3/memories`) and sorts client-side; no local SQLite cache/local-first pattern for memories specifically (cross-ref: KG/file-index caching is a different agent's area).

**Value/notes:** Medium — some of this (tier, device provenance) only becomes meaningful once/if the backend's canonical-memory-lifecycle rollout applies to Windows users too; the confidence/reasoning/context fields are meaningless without the extraction pipeline that populates them (tracked with that gap, not independently).

---

## Spotted outside my scope

- File index / knowledge graph internals (`src/main/ipc/kg*.ts`, `BrainGraph.tsx`, `knowledgeGraphClient.ts`) — another agent's area; only touched here to confirm Windows' `useKnowledgeGraph`/`BrainGraph` are unrelated to the AI-profile/persona gap (they are local graph visualization over memories/apps, not an LLM-synthesized profile).
- Backend moderation pipeline implied by Persona's `under-review`/`rejected` status badge — worth checking whether this is a manual admin review queue or automated, but out of scope for a desktop-parity audit.
- Whether Windows chat compensates for the missing `<about_user>` card via live backend tool calls (e.g. does it call `get_memories`/`get_tasks` proactively on session start?) — flagging as a question for whoever owns Windows chat/agent-runtime, not answered here.
