# Ground Truth: Insight Assistant — Mac two-phase depth vs Windows current engine

Sources: Mac `Desktop/Sources/ProactiveAssistants/Assistants/Insight/{InsightAssistant,InsightStorage,InsightAssistantSettings}.swift`, `Desktop/Sources/APIClient.swift`; Windows `src/renderer/src/lib/{insightEngine,insightActivity,insightPrompt,insightGate}.ts`, `src/main/insight/{state,notification,toastWindow}.ts`, `src/main/ipc/{insight,db}.ts`, `src/renderer/src/components/insight/InsightToast.tsx`; backend `routers/memories.py`.

## Mac: two-phase extraction flow (`InsightAssistant.runAdviceExtraction`)

**Trigger:** `InsightAssistant` is a `ProactiveAssistant` fed by the shared screen-capture pipeline. Every captured frame calls `analyze(frame:)`, which just stores `pendingFrame` and signals a `frameSignal` async stream (excluded apps checked here via `InsightAssistantSettings.isAppExcluded`). A separate `processLoop()` waits for `extractionInterval` (Settings-configurable) to elapse since `lastAnalysisTime`, then pulls the latest pending frame and calls `processFrame`. So Mac is timer + latest-frame-since-last-run, same shape as Windows' setTimeout loop, but interval-gated inside the assistant itself rather than a hard 15-min setTimeout.

**Prompt build (`runAdviceExtraction`):** app name, window title, formatted time, an `ACTIVITY SUMMARY` built by `buildActivitySummary(from:to:)` (SQL query grouping `screenshots` by `appName, windowTitle` over the lookback window — `SELECT appName, windowTitle, COUNT(*), MIN(timestamp), MAX(timestamp) FROM screenshots WHERE timestamp BETWEEN ? AND ? GROUP BY appName, windowTitle ORDER BY count DESC LIMIT 30`), the user's `AIUserProfileService` profile text, and up to 30 previous insights (from an in-memory dedup window seeded from `MemoryStorage` at startup) for "do not repeat" instructions. Ends with an explicit instruction to scan OCR from the top 3-5 apps (skip apps with <10 screenshots) and either call `request_screenshot` or `no_advice`.

**Phase 1 — text-only SQL investigation loop** (`buildPhase1Tools`, up to 7 iterations, `forceToolCall` on iteration 0, 120s timeout per call, `thinkingBudget: 1024`):
- Tools: `execute_sql` (SELECT-only against `screenshots(id, timestamp, appName, windowTitle, ocrText, focusStatus)`, auto-limited to 200 rows), `request_screenshot` (args `screenshot_id`, `findings`), `no_advice` (args `context_summary`, `current_activity`).
- Loop appends model `functionCall`/`functionResponse` turns and continues on `execute_sql`; breaks the labeled `phase1Loop` on `request_screenshot` (capturing `chosenScreenshotId` + `investigationFindings`), returns early with `hasInsight:false` on `no_advice`, and hard-breaks on any unrecognized tool call. If Phase 1 exhausts 7 iterations without `request_screenshot`, returns `(nil, sqlCount)` — no insight.

**Phase 2 — single vision call with cross-reference** (`buildPhase2Tools`, up to 5 iterations):
- Loads the chosen screenshot from `RewindDatabase`/`RewindStorage` (skips if it's still in the actively-encoding video chunk), compresses it (max 1280px wide, JPEG q=0.4) via `compressForGemini`.
- Prompt: Phase 1 findings + the image + instruction to cross-reference via `execute_sql` (check if resolved later, whether user moved on, verify timestamp relevance) before deciding.
- Tools: `execute_sql` (same schema, for cross-referencing), `provide_advice` (args: `advice`, `headline` (≤5 words), `reasoning`, `category` enum `productivity|communication|learning|other`, `source_app`, `confidence` 0-1, `context_summary`, `current_activity`), `no_advice`.
- Returns `parseProvideAdvice(toolCall)` → `InsightExtractionResult(hasInsight:true, insight: ExtractedInsight, contextSummary, currentActivity)` on `provide_advice`; `no_advice`/exhaustion → no insight.

**Result schema (`ExtractedInsight`):** `insight` (advice text), `headline`, `reasoning`, `category` (`InsightCategory`: productivity/health/communication/learning/other — health only appears via `InsightStorage`'s `CaseIterable`, not a Phase-2 tool enum value), `sourceApp`, `confidence` (Double 0-1). Confidence gating happens in `handleResultWithScreenshot` against `InsightAssistantSettings.shared.minConfidence` (Settings-configurable threshold) — below threshold, the result is dropped before storage/sync/notification.

## Mac: backend sync as searchable memory

`syncInsightToBackend` (called from `handleResultWithScreenshot`) calls:
```swift
APIClient.shared.createMemory(
  content: insight.insight,
  visibility: "private",
  category: .interesting,
  confidence: insight.confidence,
  sourceApp: insight.sourceApp,
  contextSummary: insightResult.contextSummary,
  tags: ["tips", categoryTag],       // categoryTag = insight.category.rawValue.lowercased()
  reasoning: insight.reasoning,
  currentActivity: insightResult.currentActivity,
  source: "screenshot",
  windowTitle: windowTitle,
  headline: insight.headline
)
```
→ `POST v3/memories` (backend `routers/memories.py:create_memory`, `@router.post('/v3/memories', response_model=MemoryDB)`). Request body fields (snake_case over the wire): `content, visibility, category, confidence, source_app, context_summary, tags, reasoning, current_activity, source, window_title, headline`. Backend `Memory` model defaults `category` to `interesting`; `manually_added` is derived as `category == manual`, so insight memories (`category="interesting"`) are NOT flagged manually-added — they get written as normal auto-extracted memories via `MemoryService.write`, tagged `["tips", "<category>"]`.

**Local SQLite first, then backend, then reconcile:** `handleResultWithScreenshot` saves to local SQLite via `MemoryStorage.shared.insertLocalMemory` (a `MemoryRecord` with `backendSynced:false`, `category:"system"`, the same `tagsJson: ["tips","<cat>"]`, plus `screenshotId`, `confidence`, `reasoning`, `sourceApp`, `windowTitle`, `contextSummary`, `currentActivity`, `headline`) BEFORE calling the backend. On backend success it calls `MemoryStorage.shared.markSynced(id:backendId:)` to reconcile the local row with the server-assigned id. Local dedup-window (`previousInsights`, max 50) is also seeded at startup via `MemoryStorage.shared.getLocalMemories(limit:50, category:"system", tags:["tips"])`.

## Mac: surfacing + history

- **UI cache**: `InsightStorage` (MainActor singleton) — `addInsight` appends a `StoredInsight` to `@Published insightHistory` (max 100, UserDefaults-cached under key `omi.advice.history`), independent of the backend sync in `InsightAssistant`.
- **Backend as source of truth for history UI**: `InsightStorage.syncFromBackend()` calls `APIClient.shared.getMemories(limit:100, tags:["tips"], includeDismissed:true)` and rebuilds `insightHistory` from `ServerMemory` (i.e., insights are stored AND re-read as tagged memories — no dedicated insight-history endpoint/table server-side). `StoredInsight(from: ServerMemory)` decodes category from `tags.first(where: { $0 != "tips" })`.
- Read/dismiss/delete operations (`markAsRead`, `dismissInsight`, `deleteInsight`, `markAllAsRead`) optimistically update local state then call `APIClient.updateMemoryReadStatus` / `deleteMemory` per-id (bulk mark-all-read route was removed; done via per-item task group).
- **Notification**: on success (confidence above threshold, notifications enabled), `sendInsightNotification` posts via `NotificationService` with `headline` as the title/body, and a `FloatingBarNotificationContext` carrying `contextSummary`/`currentActivity`/`reasoning`/full `detail` for the expanded card.
- **No separate local "insight history" table on Mac** — `MemoryStorage`'s general local-memory SQLite table (tagged `tips`) IS the local insight history/dedup store; there's no Mac equivalent of Windows' dedicated `insights` table.

## Windows: current path (verified in full)

**Trigger** — `insightEngine.ts`: `maybeStartInsightEngine()` self-reschedules a plain `setTimeout` (first run ~60s after launch, then `max(1, intervalMin) * 60_000` per settings, default 15 min from `state.ts` `DEFAULTS.intervalMin`). No per-frame signaling, no interval check against last-analysis-time inside the run — the timer itself IS the interval.

**Data** — `runInsightOnce()`:
1. Checks `insight.enabled` (settings) and `rewind.captureEnabled` — bails if either is off.
2. Pulls frames via `window.omi.rewindFrames(now - 60min, now)` (fixed 1-hour lookback, not Settings-configurable, no db-side GROUP BY summary query — pulls raw frame rows over IPC then processes in-renderer).
3. Filters private/denied windows (`isPrivateWindow`, `isDeniedContext`), redacts fields (`redactFrameFields`).
4. `summarizeActivity(frames, 12_000 chars)` — pure string concatenation grouping consecutive frames by app+window into `## App — Title\n<dedup'd OCR lines>` blocks, budget-capped (first block always included even if it alone exceeds budget; subsequent blocks appended only if they fit) — no ranking by frequency/duration, just chronological order and a hard char budget.
5. Pulls up to 30 recent stored insight headlines from local SQLite (`window.omi.insightRecent(30)`) for a dedup instruction list.

**LLM** — single Gemini call, TEXT-ONLY, single-shot (no tool loop, no SQL investigation, no vision/screenshot):
- `generate({ model: 'gemini-2.5-flash' (default), parts: [{ text: buildInsightPrompt(summary, recentHeadlines) }], responseSchema: INSIGHT_RESPONSE_SCHEMA })` — structured-output JSON schema (`has_insight`, `insight.{headline, advice, reasoning, category, source_app, confidence}`), not a function-calling tool loop.
- `buildInsightPrompt` is a static instruction block + "already-given insights" (recent headlines) + the activity-summary text. No user profile injection, no per-category app-count filtering instruction, no forced "scan top 3-5 apps" behavior (there's nothing to scan — no SQL access, no image).
- `selectInsight()` (insightGate.ts) applies `THRESHOLD = 0.85` (hardcoded, described in a comment as matching Mac's minConfidence — Mac's is Settings-configurable, not hardcoded) and headline-based dedup (normalized string match against recent headlines) — no semantic/fuzzy dedup.

**Store** — on accept: `window.omi.insightAdd(insight)` → IPC `insight:add` → `insertInsight(p)` (`db.ts`) — a single local SQLite `INSERT` into the local-only `insights` table (`id, ts, headline, advice, reasoning, category, source_app, confidence, dismissed`). **No backend call anywhere in the Windows insight path** — no `createMemory`, no `/v3/memories` POST, no tags, no sync. `insightSetSettings({ lastRunAt: now })` persists the last-run timestamp to `insights.json` (state.ts) regardless of outcome.

**Surface** — `window.omi.insightShow(insight)` → IPC `insight:show` → `deliverInsight()` (`ipc/insight.ts`) picks `native` (Windows toast via `fireNativeInsight`, `main/insight/notification.ts`) or `omi` (in-app acrylic toast via `showInsightToast`, `main/insight/toastWindow.ts`) based on `notificationStyle` setting. `InsightToast.tsx` (renderer component) + `insight-toast.css` render the in-app style; hover pauses auto-dismiss (`insight:hoverStart/hoverEnd`).

**History** — `recentInsights(limit)` reads straight from the local `insights` table (`id, ts, headline, advice, reasoning, category, sourceApp, confidence, dismissed`); `dismissed` column exists in schema but no IPC handler was found wiring a "mark dismissed" mutation in `insight.ts` — dismiss appears local-toast-only (`insight:dismiss` just hides the toast window), not persisted per-row.

## Delta: Windows → Mac two-phase depth + backend-sync-as-memory + history UI

1. **No two-phase pipeline** — Windows does one text-only structured-output call. Mac's Phase 1 (agentic SQL investigation loop, up to 7 iterations, `execute_sql`/`request_screenshot`/`no_advice` tools) and Phase 2 (single vision call over the chosen screenshot + up to 5 cross-reference iterations, `execute_sql`/`provide_advice`/`no_advice`) have no Windows equivalent. To reach parity: add a Gemini function-calling tool loop with `execute_sql` against `rewind_frames` (Windows' `screenshots` analog — columns differ, see `db.ts`), a `request_screenshot`/vision phase 2 that loads and downsizes the actual frame image and re-calls Gemini with the image attached, and a cross-reference SQL step before finalizing.
2. **No backend sync** — Windows never calls any backend endpoint for insights; they are 100% local (`insights` table). Mac POSTs `v3/memories` with `category:"interesting"`, `tags:["tips","<category>"]`, `source:"screenshot"`, plus `context_summary`/`current_activity`/`reasoning`/`window_title`/`headline`. Parity requires: (a) a Windows APIClient equivalent for `POST v3/memories` with this exact payload shape, (b) calling it after local insert, (c) reconciling/marking the local row synced with the returned backend id (Windows' local `insights` table has no `backend_id`/`synced` column at all — schema addition needed), and (d) seeding the in-memory/DB dedup window from backend-tagged memories at startup (or continuing to use the local table, which is simpler but diverges from Mac's dual-write dedup source).
3. **History UI is backend-authoritative on Mac, local-only on Windows** — Mac's `InsightStorage.syncFromBackend()` re-reads `GET /v3/memories?tags=tips` as the source of truth for the insight history list (cross-device via memories, not just this machine); Windows' `recentInsights()` only ever reads its own local SQLite. No cross-device history without wiring a Windows equivalent of `syncFromBackend`/read-status update endpoints (`updateMemoryReadStatus`, `deleteMemory`).
4. **Confidence threshold not user-configurable** — Windows hardcodes `THRESHOLD = 0.85` in `insightGate.ts`; Mac reads `InsightAssistantSettings.shared.minConfidence` from Settings.
5. **Activity summary is a naive char-budget concatenation, not a ranked SQL aggregate** — Windows' `summarizeActivity` walks frames in chronological order and stops once the character budget is hit (first block wins regardless of size); Mac's `buildActivitySummary` runs `GROUP BY appName, windowTitle ORDER BY count DESC LIMIT 30` so the highest-signal apps always make it in regardless of chronological position. Windows also uses a fixed 1-hour lookback with no interval-since-last-run anchoring (Mac anchors lookback to `previousAnalysisTime` capped at 1 hour).
6. **No user-profile injection, no min-screenshot-count-per-app filter, no "scan top 3-5 apps" instruction** — these are prompt-level richness features unique to Mac's Phase 1 investigation prompt; Windows' single-shot prompt has neither the profile text nor an equivalent per-app screenshot-count filter (moot without SQL access anyway).
7. **Category enum drift** — Mac's Phase-2 `provide_advice` tool enum is `productivity|communication|learning|other` (no `health` at the tool-call level, though `InsightCategory` itself has `health` for history display purposes); Windows' schema includes `health` directly in the generation schema (`insightPrompt.ts` `CATEGORIES`). Minor but worth normalizing if payloads are ever compared/merged.
8. **Windows `dismissed` column has no write path** — `insights.dismissed` exists in the schema but `ipc/insight.ts` never mutates it (only hides the toast window); Mac's `dismissInsight`/`markAsRead` persist per-item state both locally and to backend. Needs IPC handlers + `recentInsights` filtering by `dismissed` if history parity is pursued.
