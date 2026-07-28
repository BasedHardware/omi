# Track 3 Ground-Truth Inventory — Windows App

Generated 2026-07-14 against `desktop/windows` in worktree `track3-proactive`. Purpose: give
the orchestrator an exact "what exists today" baseline for Track 3's owned surface (memories,
goals, tasks, insights, integrations) plus the three shared schema files, so an additive-only
schema PR can be planned without guessing.

All paths below are relative to `desktop/windows/src/` unless stated otherwise.

---

## TASK 1 — Owned-path inventory

### `renderer/src/lib/*`

| Path | Exists | Lines | Status | What it does today |
|---|---|---|---|---|
| `lib/goals.ts` | yes | 55 | complete (small, single-purpose) | Onboarding "pick one goal" helpers: builds the LLM prompt (`buildGoalPrompt`), parses a numeric target out of the goal sentence (`parseTargetValue`, defaults to 1 since `POST /v1/goals` 422s without `target_value`), calls the agent LLM (`generateGoal`), and persists via `POST /v1/goals` (`createGoal`). No goal-advice/suggest logic lives here — that's inline in `Goals.tsx`/`QuickGoalsWidget.tsx` (see below). |
| `lib/memoryExtract.ts` | yes | 139 | complete | LLM-based memory-log import (ChatGPT/Claude paste), a faithful port of macOS's `OnboardingMemoryLogImportService`. Sends the pasted export + existing memories to `desktopApi.post('/v2/chat/completions', ...)` using the `claude-haiku-4-5-20251001` synthesis model, parses JSON, dedupes against existing memories (exact-match after normalization). Also re-exports `extractJSONObject` from `./extractJson` for backward compat. |
| `lib/memoriesBulk.ts` | yes | 120 | complete | Three bulk operations: `fetchAllMemories()` (paginates `GET /v3/memories`, dedupes by id, documents the backend's forced-limit-5000-at-offset-0 quirk), `postMemoriesBatched()` (chunks into `MEMORIES_IMPORT_BATCH_SIZE=100` and POSTs `/v3/memories/batch`), `deleteMemoriesPaced()` (renderer-side paced single-delete loop honoring 429/Retry-After — note there is ALSO a main-process bulk-delete path, `main/ipc/memoryCleanup.ts`, which is the one actually wired to the Settings UI's bulk-delete button; this renderer version may be legacy/unused-by-UI, worth flagging but out of scope here). |
| `lib/memoryCleanup.ts` | yes | 94 | complete | Pure, read-only "app-index memory" detection: regexes to identify memories synthesized by the (removed) local app/file-index pipeline (`APP_INDEX_TAG`, `USES_TEMPLATE`, `LOCAL_INDEX_STEM`, `INDEX_SENTENCES`), plus `summarizeMemories()` for the maintenance UI (groups by tag, flags app-index candidates for deletion). No network/mutation — this is the "analyze" half; deletion is `memoriesBulk.ts`/`memoryCleanup` IPC. |
| `lib/memoryRank.ts` | yes | 69 | complete | Pure token-overlap ranking (`rankMemories`) used to correlate a folder/project name or a question against saved memories; stop-word list tuned for folder-slug tokens. No I/O. |
| `lib/insight*.ts` | yes (4 files, no single `insightEngine` prefix miss) | `insightActivity.ts` 39, `insightEngine.ts` 95, `insightGate.ts` 16, `insightPrompt.ts` 69 (+ 3 matching `.test.ts` files) | complete | The Proactive Insights feature (Rewind OCR → Gemini → acrylic toast), independent of macOS's memory pipeline: `insightActivity.ts` groups Rewind frames into an OCR text summary; `insightPrompt.ts` builds the Gemini prompt/schema and parses the response into `InsightPayload`; `insightGate.ts` applies confidence threshold + headline-dedupe; `insightEngine.ts` is the orchestrator (self-rescheduling timer, calls `window.omi.rewindFrames`, `window.omi.insightGetSettings/insightAdd/insightRecent`, Gemini `generate()`). This is a **separate concern from Track 3's memory/goals/tasks scope** — no `embeddings*.ts` exists (see next row) and this pipeline doesn't touch memories at all. |
| `lib/embeddings*.ts` | **MISSING** | — | absent | No embeddings-related lib file exists anywhere under `renderer/src/lib`. Confirmed via glob — nothing to inventory. |
| `lib/clientDevice.ts` | **MISSING** | — | absent | Confirmed absent — matches the brief's note that macOS commit `a4c50bcb4` (client-device reporting) has not been cherry-picked to Windows yet. |
</br>
| `lib/userProfile.ts` | yes | 27 | complete (narrow scope) | NOT the AI/memory profile (`get_ai_profile`/`update_ai_profile`) — this is the onboarding-wizard identity sync: `syncLanguage()` (`PATCH /v1/users/language`), `syncRecordingConsent()` (`POST /v1/users/store-recording-permission`, raw boolean body), `setDisplayName()` (Firebase `updateProfile`, since there is no backend "set my name" endpoint). No AI-profile read/write logic exists in this file or anywhere else in `renderer/src/lib` — `get_ai_profile`/`update_ai_profile` only exist as generated-client functions (see Task 2) with no caller yet. |

### `renderer/src/hooks/*`

| Path | Exists | Notes |
|---|---|---|
| `hooks/useMemories.ts` | yes, 169 lines, complete | The one hook for memories. Module-level cache + pub/sub (`subscribers: Set`) so every mounted instance stays in sync across pages (Memories page, Settings importer, etc). `fetchMemories()` calls `GET /v3/memories?limit=500&offset=0`, sorts client-side by `created_at desc` (server doesn't sort). `createMemory` POSTs `/v3/memories`. `editMemory`/`setMemoryVisibility` both go through `patchMemoryOptimistic()`, which PATCHes `/v3/memories/{id}` or `/v3/memories/{id}/visibility` with the new value sent as a **query param** (`{ params: { value } }`), matching the backend's actual `value: str` function-arg contract (see Task 2) — optimistic update with rollback-on-failure. `refresh()` re-pulls and broadcasts. |
| `hooks/useTasks*.ts` | **does not exist** | Tasks has no dedicated hook. `pages/Tasks.tsx` (613 lines) does everything inline: module-level cache, `fetchAllActionItems()` (pages `GET /v1/action-items` following `has_more`, `TASKS_PAGE_SIZE=100`), plus a best-effort `GET /v1/conversations` fetch to label each task's source conversation. `components/home/QuickTaskWidget.tsx` duplicates a simpler independent fetch of the same endpoint (own auth-gated `useEffect`, own cache-free state) — no shared hook between the page and the widget. |
| `hooks/useGoals*.ts` | **does not exist** | Same pattern as Tasks: no hook. `pages/Goals.tsx` (662 lines) does everything inline — module cache, `fetchAll()` hits `GET /v1/goals/all` (single endpoint returns both active+completed, split client-side by `is_active`), completion logic (`isCompleted`/`progressPct`/`progressLabel`) duplicated verbatim in `components/home/QuickGoalsWidget.tsx`, which also independently calls `GET /v1/goals/suggest` + `POST /v1/goals` for the one-tap "Generate a goal" affordance. **Both Goals.tsx and QuickGoalsWidget.tsx re-derive the same completion/progress logic with no shared helper** — a real duplication (noted for Leave-It-Better scope, not fixed here). |

### `main/*` directories

| Path | Exists | Contents / status |
|---|---|---|
| `main/assistants/**` | **MISSING** | No such directory. Confirmed via directory listing. |
| `main/integrations/**` | yes, complete | `google.ts`, `googleMap.ts(+test)`, `oauth.ts`, `oauthPkce.ts(+test)`, `stickyNotes.ts`, `stickyNotesPath.ts(+test)`, `stickyNotesText.ts(+test)`, `syncState.ts`, `syncStateLogic.ts(+test)`, `tokenStore.ts`. Full Google OAuth (Gmail/Calendar) + Windows Sticky Notes reader, all with unit tests alongside. |
| `main/memoryExport/**` | yes, complete | `format.ts(+test)`, `io.test.ts`, `notion.ts`, `obsidian.ts`, `plainFile.ts` — three export targets (Notion page, Obsidian vault folder, plain markdown file). |
| `main/memoryImport/**` | yes, complete but thin | `parse.ts(+test)` only — a pure text-dump parser (`parseMemoryDump`). The actual LLM-based extraction path lives in renderer's `lib/memoryExtract.ts`, not here; this directory is the fallback/heuristic splitter. |
| `main/memoryCleanup/**` | yes, complete but thin | `bulkDelete.ts(+test)` — pure helpers (`classifyStatus`, `backoffMs`) consumed by `main/ipc/memoryCleanup.ts`'s worker pool. |
| `main/usage/**` | yes, complete | Full foreground-app-usage tracking subsystem: `category.ts(+test)`, `foregroundMonitor.ts`, `nativeForeground.ts`, `usageAccumulator.ts(+test)`, `usageDay.ts(+test)`, `usageRetention.ts(+test)`, `usageSettings.ts`, `userAssist.ts(+test)`, `userAssistRegistry.ts`, `userAssistSeed.ts`. Not part of Track 3's memory/goals/tasks scope but shares the `app_usage` table with the local-KG synthesis pipeline. |
| `main/insight/{notification,state}.ts` | yes, both present, complete | `notification.ts` (17 lines): `fireNativeInsight()` — shows an `InsightPayload` as a native Windows `Notification`, best-effort/no-op if unsupported. `state.ts` (46 lines): `getInsightSettings()`/`updateInsightSettings()` — JSON-file-backed (`insights.json` in userData) settings store with an in-memory cache and `DEFAULTS` (`enabled: true, intervalMin: 15, notificationStyle: 'omi', denylist: [], lastRunAt: null`). There's also a third file in this directory, `toastWindow.ts` (not in the brief's list), which owns the shared acrylic toast window. |
| `main/ipc/memoryExport.ts` | yes, 47 lines, complete | Registers 3 ipcMain handlers (`memoryExport:obsidian/file/notion`); obsidian/file open native dialogs then delegate to `main/memoryExport/*`. |
| `main/ipc/memoryImport.ts` | yes, 8 lines, complete (deliberately thin) | Single handler `memoryImport:parse` delegating to `parseMemoryDump`. Comment clarifies the renderer does the actual `POST /v3/memories` itself since it owns the Firebase token. |
| `main/ipc/memoryCleanup.ts` | yes, 102 lines, complete | Registers `memories:bulkDelete` — a 4-way-concurrent worker pool using Electron's `net.fetch` (not renderer axios) with per-id retry/backoff (`MAX_ATTEMPTS=6`), streams progress via `memories:deleteProgress`. This — not `lib/memoriesBulk.ts`'s `deleteMemoriesPaced` — is the path wired to the bulk-delete UI (needs confirming against the calling component if the orchestrator needs that link, not verified in this pass). |

### Pages

| Path | Exists | Lines | Status |
|---|---|---|---|
| `renderer/src/pages/Memories.tsx` | yes | 479 | complete |
| `renderer/src/pages/Tasks.tsx` | yes | 613 | complete |
| `renderer/src/pages/Goals.tsx` | yes | 662 | complete |

All three are full-featured pages with their own module-level caches, optimistic-update patterns, and error handling — not stubs. (Full line-by-line read was not performed beyond the first ~80 lines of Tasks/Goals; the header/import/cache-setup sections confirm completeness and match the API surface documented under Task 2.)

### Components

| Path | Exists | Status |
|---|---|---|
| `components/insight/InsightToast.tsx` (+ `insight-toast.css`) | yes, 154 lines, complete | Renders three toast kinds in the shared acrylic toast window: proactive insight, meeting-detection notice, and post-update "what's new" — NOT memory/goals/tasks related, this is the Rewind/Insight feature's UI. |
| `components/home/QuickTaskWidget.tsx` | yes, 150 lines, complete | Home-screen preview card for open tasks (top 2 by due date), own independent fetch of `/v1/action-items` (auth-gated, refetch-on-focus/route-change). No shared hook with `Tasks.tsx`. |
| `components/home/QuickGoalsWidget.tsx` | yes, 179 lines, complete | Home-screen preview card for active goals with progress bars, own independent fetch of `/v1/goals/all` plus the one-tap `/v1/goals/suggest` → `POST /v1/goals` generate flow. Duplicates `isCompleted`/`progressPct` logic from `Goals.tsx` (no shared helper). |
| `components/settings/tabs/IntegrationsTab.tsx` | yes, complete (only first 100 of the file read, but structure is clear) | Two integrations wired: Windows Sticky Notes (read via `window.omi.readStickyNotes()`, LLM-extract via `lib/stickyNotesExtract`, import as tagged memories) and Google (Gmail/Calendar sync via `lib/googleSync`, gated behind `VITE_ENABLE_GOOGLE_INTEGRATION` or a dev localStorage flag). Both write memories through `useMemories()`. |

---

## TASK 2 — Shared schema files

### `main/ipc/db.ts` (903 lines) + `main/ipc/dbMigrations.ts` (99 lines)

**Every `CREATE TABLE`** (all inside one `db.exec(...)` template string in `get()`, guarded by `IF NOT EXISTS`):

1. `caption_event` — conversation captions/OCR overlay text (+ index on `conversation_id, ts`)
2. `local_conversation` — local recordings/chats (+columns added additively below)
3. `indexed_files` — file-index scan results (+ index on `file_type`)
4. `local_kg_nodes` / `local_kg_edges` — the chat-agent local knowledge graph (+ indexes on label/type)
5. `onboarding_kg_nodes` / `onboarding_kg_edges` — separate onboarding brain-map graph
6. `app_usage` — foreground-time tracking, keyed by `exe_path`
7. `rewind_frames` — screen-history timeline (+ indexes on `ts`, `indexed`)
8. `insights` — Proactive Insights records (+ index on `ts`)

**No table exists yet for**: memories (memories are entirely server-side via `/v3/memories`, no local cache table), goals, tasks/action-items, AI profile, or embeddings. Track 3's additive schema PR would be introducing net-new tables/columns, not touching existing ones — low collision risk.

**Two migration mechanisms, in this order inside `get()`:**

1. **Additive-baseline bootstrap** — `ensureColumn(db, table, col, decl)` calls (aliases `addColumnIfMissing` from `dbMigrations.ts`) run unconditionally on every startup, each independently idempotent:
   ```ts
   ensureColumn(db, 'local_conversation', 'kind', "TEXT NOT NULL DEFAULT 'recording'")
   ensureColumn(db, 'local_conversation', 'messages', 'TEXT')
   ensureColumn(db, 'local_conversation', 'title', 'TEXT')
   ensureColumn(db, 'local_kg_nodes', 'aliases_json', 'TEXT')
   ensureColumn(db, 'local_kg_nodes', 'source_refs', 'TEXT')
   ensureColumn(db, 'indexed_files', 'target_path', 'TEXT')
   ```
   This is the **first append point**: a brand-new column on an *existing* table (e.g. adding a `profile`/`embedding` column to some future table) would append one more `ensureColumn(...)` line here, right before `runMigrations(db)`.

2. **Versioned migrations** (`dbMigrations.ts`) — `PRAGMA user_version`-tracked, ordered, append-only, each wrapped in its own transaction (`BEGIN`/`m.up(d)`/`PRAGMA user_version = N`/`COMMIT`, rollback on throw). Currently exactly one migration exists:
   ```ts
   export const MIGRATIONS: Migration[] = [
     {
       version: 1,
       name: 'local_conversation cloud-sync outbox columns',
       up: (d) => {
         addColumnIfMissing(d, 'local_conversation', 'sync_state', "TEXT NOT NULL DEFAULT 'local_only'")
         addColumnIfMissing(d, 'local_conversation', 'segments_json', 'TEXT')
         addColumnIfMissing(d, 'local_conversation', 'cloud_id', 'TEXT')
         addColumnIfMissing(d, 'local_conversation', 'sync_attempts', 'INTEGER NOT NULL DEFAULT 0')
         addColumnIfMissing(d, 'local_conversation', 'sync_error', 'TEXT')
       }
     }
   ]
   ```
   **This is the append point for anything more than "add a column"** — a brand-new table, a backfill, or multi-statement DDL. Track 3 would append a `{ version: 2, name: '...', up: (d) => { d.exec('CREATE TABLE IF NOT EXISTS ...') } }` entry to this array. Rules stated in the file's own header comment: append-only, never renumber/edit a shipped migration, keep each `up` cheaply idempotent, `version` must stay contiguous from 1 (enforced at runtime — `runMigrations` throws if not).

Everything below the schema init in `db.ts` is plain exported functions grouped by feature with `// --- Section ---` banner comments (e.g. `// --- App usage ---`, `// --- Local knowledge graph (M2) ---`, `// --- Rewind: screen-history timeline ---`, `// --- Proactive Insights ---`). **Track 3's own labeled block** (functions for its new tables) should follow this exact convention: a `// --- <Feature Name> ---` banner near the end of the file, after `recentInsights()` (line 903, end of file).

### `shared/types.ts` (1276 lines)

Single flat file, no namespacing/sub-modules. Organized as: small shared constants at the top (`PCM_PENDING_MAX_BYTES`, `GPU_CONTEXT_LOST_CHANNEL`), then type groups in the rough order features were added, each preceded by a `// ─── <Section> ───` or `// --- <Section> ---` banner comment. The **single big aggregate interface `OmiBridgeApi`** (starts line 470) is the preload-exposed surface — every new main→renderer IPC method's TypeScript signature is added there, grouped under its own `// --- <Feature> ---` comment (e.g. `// --- Proactive Insights (Rewind OCR → Gemini → acrylic toast) ---` at line 1157, `// --- Coding agents ---` at line 774). Payload/record types for a feature (e.g. `InsightPayload`, `InsightSettings`, `InsightRecord`) are declared near the end of the file, close to where they're last referenced, not co-located with `OmiBridgeApi`.

**Append point for Track 3**: two separate edits in this one file —
1. New payload/data types (e.g. a `GoalRecord`/`TaskRecord`/`AIProfileRecord` if any local caching is added) — appended near the end, following the pattern of `InsightPayload`/`InsightRecord`/`InsightSettings` (lines ~1157–1217).
2. New IPC method signatures — appended inside the `OmiBridgeApi` interface body (before its closing brace, currently line 772), under a fresh `// --- <Feature> ---` banner, mirroring how `// --- Local knowledge graph (M2) ---` (line 586) or `// --- Meeting detection (Phase 5) ---` (line 644) group their methods.

### `preload/index.ts` (394 lines)

Three `contextBridge.exposeInMainWorld` calls at the bottom (`omi`, `omiOverlay`, `omiBar`), each backed by a plain object literal implementing the corresponding `shared/types.ts` interface. The `omi` object (implements `OmiBridgeApi`) is overwhelmingly the relevant one for Track 3 — every method is a one-line `ipcRenderer.invoke(...)` (request/response) or `ipcRenderer.send(...)` + `ipcRenderer.on(...)`/`removeListener` pair (fire-and-forget / event subscription), grouped in the same order/banner-comments as `OmiBridgeApi` in `shared/types.ts` (e.g. the insight block starts at line 173: `insightGetSettings`, `insightSetSettings`, `insightAdd`, `insightRecent`, `insightShow`, `insightDismiss`, `insightHoverStart/End`, `insightTest`, `onInsightShow`).

**Append point**: add the new methods to the `omi` object literal (before its closing brace at line 283), in the same relative position as their `OmiBridgeApi` declaration, following the existing `ipcRenderer.invoke('feature:action', ...)` naming convention (colon-namespaced channel names, e.g. `'insight:getSettings'`, `'memoryExport:notion'`).

### Generated API client — `renderer/src/lib/omiApi.generated.ts` (12,369 lines)

Auto-generated from the backend OpenAPI schema — an `interface Paths` block (path → method → `operationId`/`responses`) followed by exported `async function <operationId>(...)` wrappers, one per endpoint, plus every request/response `interface`. Confirmed present/absent:

| Backend feature | Present in generated client? | Function name(s) | Signature notes |
|---|---|---|---|
| Get AI profile | **yes** | `get_ai_profile_v1_users_ai_profile_get(init?)` → `Promise<AIUserProfileResponse \| null>` (line 10702) | No path/query params. `AIUserProfileResponse { data_sources_used?, generated_at?, profile_text? }` (line 8). |
| Update AI profile | **yes** | `update_ai_profile_v1_users_ai_profile_patch(body: UpdateAIUserProfileRequest, init?)` → `Promise<AIUserProfileResponse>` (line 10717) | Takes a JSON **body** (`UpdateAIUserProfileRequest { data_sources_used?, generated_at?, profile_text? }`, line 2611) — this one is body-based, unlike memory edit/visibility below. |
| Memory edit (content) | **yes**, two variants | `edit_memory_v3_memories__memory_id__patch(path: {memory_id}, query: {value: string}, init?)` → `MemoryMutationResponse` (line 12219); also an MCP variant `edit_memory_v1_mcp_memories__memory_id__patch` (line 9968) | **QUERY param**, not a JSON body. **No `MemoryValueRequest` type exists anywhere in the generated client** (confirmed via full-file grep — zero hits). The generated client is NOT stale relative to the current backend: `backend/routers/memories.py` `edit_memory()` (line 815) has `value: str` as a plain function arg (not a Pydantic model), which FastAPI binds as a query param — so client and server agree today. If Track 3's plan calls for migrating this endpoint to a `MemoryValueRequest {value}` JSON body, that is a **backend contract change the client would need regenerating for**, not a client bug. |
| Memory visibility | **yes** | `update_memory_visibility_v3_memories__memory_id__visibility_patch(path: {memory_id}, query: {value: string}, init?)` → `MemoryMutationResponse` (line 12270) | Same query-param pattern, same conclusion — matches `backend/routers/memories.py` `update_memory_visibility()` (line 843, also plain `value: str`). |
| Goal advice (current) | **yes** | `get_current_goal_advice_v1_goals_advice_get(init?)` → `Promise<AdviceResponse>` (line 9278) | `AdviceResponse { advice: string }` (line 85). |
| Goal advice (specific) | **yes** | `get_goal_advice_v1_goals__goal_id__advice_get(path: {goal_id}, init?)` → `Promise<AdviceResponse>` (line 9372) | |
| Goal suggest | **yes** | `suggest_goal_v1_goals_suggest_get(init?)` → `Promise<GoalSuggestionResponse>` (line 9325) | `GoalSuggestionResponse { reasoning, suggested_max?, suggested_min?, suggested_target, suggested_title, suggested_type }` (line 1460). Note: `Goals.tsx`/`QuickGoalsWidget.tsx` currently call this endpoint via raw `omiApi.get('/v1/goals/suggest')` and manually type the response as `{ suggested_title?, suggested_target? }` rather than importing the generated function/type — an inconsistency worth flagging but out of scope to fix here. |
| Staged tasks (create/list/clear/delete/promote/batch-score) | **NO — entirely absent** | none | Confirmed via full-file grep for `staged-tasks`/`staged_task`/`StagedTask` — zero hits in `omiApi.generated.ts`. The backend router (`backend/routers/staged_tasks.py`) fully exists (`POST/GET /v1/staged-tasks`, `DELETE /v1/staged-tasks/{id}`, `/v1/staged-tasks/clear`, `/v1/staged-tasks/promote`, batch-score endpoint) but the generated client has **never been regenerated since staged-tasks was added to the backend** — this is the clearest concrete evidence the client is stale, and Windows has zero staged-tasks UI/plumbing today (no page, no hook, no IPC). |

**Practical implication for the additive schema PR**: the generated client needs a **regeneration pass** (from the current backend OpenAPI schema) as part of or before Track 3's work if staged-tasks support is in scope — it's not a hand-edit target, it's a codegen output (exact regeneration command not located in this pass; check `desktop/windows/package.json` scripts or a `scripts/generate-api*` file if the orchestrator needs it).

---

## TASK 3 — Renderer → main DB IPC pattern

Two distinct data-access patterns coexist, and it matters which one a new Track 3 feature should follow:

### Pattern A — Local SQLite via IPC (main-process owned, e.g. Insights)

Three-hop chain, all fire-and-forget or invoke/response, no direct DB access from the renderer (better-sqlite3 is native, only loadable in main):

1. **`shared/types.ts`** declares the method signature inside `OmiBridgeApi` (e.g. `insightGetSettings: () => Promise<InsightSettings>`, line 629; `insightAdd: (p: InsightPayload) => Promise<void>`, line 631).
2. **`preload/index.ts`** implements it as a thin `ipcRenderer.invoke('insight:getSettings')` / `ipcRenderer.invoke('insight:add', p)` (lines 173–176), exposed on `window.omi` via `contextBridge.exposeInMainWorld('omi', omi)`.
3. **`main/ipc/*.ts`** (for insights this is wired wherever `insight:getSettings`/`insight:add` handlers are registered — not read in this pass, but by direct analogy with `memoryCleanup.ts`'s `ipcMain.handle('memories:bulkDelete', ...)`) calls into `main/insight/state.ts`'s `getInsightSettings()`/`updateInsightSettings()`, which read/write a JSON file (not SQLite, for this particular feature) — or, for tables like `insights`/`local_kg_nodes`, calls straight into the exported functions in `main/ipc/db.ts` (e.g. `insertInsight()`, `recentInsights()` at the bottom of `db.ts`).
4. **Renderer caller** (`lib/insightEngine.ts`) uses the bridge directly: `await window.omi.insightGetSettings()`, `await window.omi.insightAdd(insight)`, `window.omi.insightShow(insight)` — no React hook wraps this; it's called from a plain async function on a timer.

Concrete example end-to-end for a DB-table-backed read: `window.omi.rewindFrames(from, to)` → preload `ipcRenderer.invoke('rewind:frames', from, to)` → a `main/ipc/*.ts` handler (rewind's IPC file, not opened in this pass) → `db.ts`'s exported `listRewindFrames(from, to)` (line 824), which runs a `prepare(...).all(from, to)` against the `rewind_frames` table and returns typed rows.

**This is the pattern any new Track 3 local table (if one is added) should follow**: declare the method on `OmiBridgeApi`, thin-invoke it in preload, register an `ipcMain.handle` in a `main/ipc/<feature>.ts` file, implement the actual SQL in `db.ts` (or a small helper module main-side), call it from the renderer via `window.omi.<method>()`.

### Pattern B — Direct backend REST via renderer axios (for memories/goals/tasks — the actual pattern in use today)

Memories, goals, and tasks do **NOT** go through main-process SQLite at all — they are server-side resources on the Omi backend, fetched directly from the renderer via `omiApi` (an axios instance in `lib/apiClient.ts`, not read in this pass, that attaches the Firebase auth token). Concrete example: `hooks/useMemories.ts`'s `fetchMemories()` calls `omiApi.get('/v3/memories', { params: { limit: 500, offset: 0 } })` directly — no IPC round-trip, no local table. Same for `Goals.tsx`'s `omiApi.get('/v1/goals/all')` and `Tasks.tsx`'s `omiApi.get('/v1/action-items', ...)`.

The only place main-process IPC gets involved for memories today is for operations that need main-process-only capabilities: file dialogs (`memoryExport.ts`) or survivability-across-navigation + Electron's `net.fetch` (`memoryCleanup.ts`'s bulk-delete, which still hits the same `/v3/memories/{id}` REST endpoint, just from main instead of the renderer, passing the renderer's token through as an IPC argument).

**Implication for planning**: if Track 3's additive schema PR is about the *backend* API surface (new memory/goal/task fields, staged-tasks, AI profile), the relevant "schema" is the generated client + `shared/types.ts` payload shapes, and there is likely **no local SQLite table involved at all** — Pattern B, not Pattern A. Only reach for `db.ts`/`dbMigrations.ts` if the plan requires a local cache/offline store for one of these resources (none exists today).

---

## Summary of notable gaps / stale spots found

- `lib/embeddings*.ts` and `lib/clientDevice.ts` — confirmed absent (matches expectations in the brief).
- `main/assistants/**` — confirmed absent.
- No `useTasks`/`useGoals` hooks exist; both pages (and their Home-widget counterparts) duplicate fetch/cache/completion logic inline. `Goals.tsx` and `QuickGoalsWidget.tsx` in particular duplicate `isCompleted`/`progressPct` verbatim.
- `omiApi.generated.ts` has **no staged-tasks support at all** despite the backend router existing — needs regeneration if staged-tasks is in scope.
- Memory edit/visibility use a **query param** (`value: str`) on both the generated client and the current backend (`backend/routers/memories.py`) — they agree today. A `MemoryValueRequest {value}` JSON-body contract would be a **new backend change**, not something the current client is behind on.
- Two competing memory-bulk-delete implementations exist: `lib/memoriesBulk.ts`'s `deleteMemoriesPaced()` (renderer-driven, single-flight) and `main/ipc/memoryCleanup.ts`'s `memories:bulkDelete` (main-driven, 4-way concurrent, `net.fetch`-based, survives navigation). Which one is actually wired to the Settings UI button was not verified in this pass — worth a quick grep before assuming either is dead code.
- `db.ts` has zero tables for memories/goals/tasks/AI-profile/embeddings — any new local persistence Track 3 needs is a clean net-new addition (low collision risk), appended as a new `Migration` entry in `dbMigrations.ts` plus a new `// --- <Feature> ---` banner section of exported functions at the end of `db.ts`.
