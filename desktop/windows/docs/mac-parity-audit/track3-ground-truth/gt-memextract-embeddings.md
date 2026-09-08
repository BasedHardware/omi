# Ground Truth: Continuous Memory Extraction + Embeddings Service

Sources (frozen Mac reference v0.12.72):
- `desktop/macos/Desktop/Sources/ProactiveAssistants/Assistants/MemoryExtraction/MemoryAssistant.swift`
- `.../MemoryExtractionModels.swift`
- `.../MemoryAssistantSettings.swift`
- `desktop/macos/Desktop/Sources/ProactiveAssistants/Services/EmbeddingService.swift`
- `desktop/macos/Desktop/Sources/Rewind/Core/{ActionItemStorage,MemoryStorage}.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/MemoriesPage.swift` (pagination-rule reference site — not in the original file list but is where the raw-vs-filtered offset rule lives)

Windows checked: `desktop/windows/src/renderer/src/lib/{memoryExtract,memoryRank,memoriesBulk,appMemories}.ts`, `src/renderer/src/hooks/useMemories.ts`, `src/main/ipc/memoryCleanup.ts`, `src/main/memoryCleanup/bulkDelete.ts`.

---

## A. Continuous AI Memory Extraction (Mac)

**Actor**: `MemoryAssistant`, identifier `memory-extraction`, conforms to `ProactiveAssistant`. Uses `GeminiClient` (Flash, vision+text, no tool loop).

**Gating**: `isEnabled` requires BOTH `MemoryAssistantSettings.shared.isEnabled` AND `.notificationsEnabled` — notifications off (default) means the Gemini vision call never fires at all, not just that the toast is suppressed.

**Loop** (`processLoop`, driven by an `AsyncStream<Void>` signal, buffering-newest-1):
1. Every incoming frame just overwrites `pendingFrame` and yields a signal (`analyze(frame:)` — always returns nil, never analyzes inline).
2. The loop wakes on signal, and if `timeSinceLastAnalysis < extractionInterval`, sleeps out the remainder.
3. Re-reads `pendingFrame` after the sleep (may have changed/cleared), clears it, stamps `lastAnalysisTime = Date()`, then calls `processFrame(frame)`.
- **`extractionInterval` default = 600s (10 minutes)**, `UserDefaults` key `memoryExtractionInterval`, register-defaults pattern (falls back to default if stored value is `<= 0`).
- App exclusion checked at `analyze(frame:)` time (before even queuing): `MemoryAssistantSettings.shared.isAppExcluded(frame.appName)` = built-in excluded apps (`TaskAssistantSettings.builtInExcludedApps`) **OR** user's custom `excludedApps` **OR** `RewindSettings.shared.isAppExcluded(appName)` (Rewind privacy exclusions).

**Model call** (`extractMemories(from:appName:)`): builds a prompt embedding the last-20 `previousMemories` ("RECENTLY EXTRACTED MEMORIES (do not re-extract these or semantically similar ones)") so the model self-dedupes; system prompt comes from `MemoryAssistantSettings.shared.analysisPrompt` (user-customizable, defaults to `defaultAnalysisPrompt`).

**Strict JSON response schema** (Gemini `responseSchema`, verified field names):
```json
{
  "has_new_memory": "boolean",
  "memories": [
    {
      "content": "string (max 15 words)",
      "category": "string enum [system, interesting]",
      "source_app": "string",
      "confidence": "number 0.0-1.0"
    }
  ],  // 0-3 max in schema description, but hard-capped to 1 downstream
  "context_summary": "string",
  "current_activity": "string"
}
```
All four top-level keys `required`; per-memory `content`/`category`/`source_app`/`confidence` all `required`.

**"Extract at most 1" rule**: enforced in `handleResultWithScreenshot` — `guard let memory = memoryResult.memories.first else { return }` — only the FIRST array element is ever used even though the schema nominally allows up to 3. Empty `memories`/`hasNewMemory == false` is the expected common case ("Many screenshots will result in 0 memories - this is NORMAL and EXPECTED" — from the prompt itself).

**Confidence threshold**: `minConfidence` default **0.7**, key `memoryMinConfidence`, same register-defaults + `>0` fallback pattern. Memories below threshold are logged and dropped (`"Filtered: ..."`), never saved/synced.

**Categorization test** (from `MemoryAssistantSettings.defaultAnalysisPrompt`, quoted structure):
- Q1: "Is this wisdom/advice FROM someone else the user can learn from?" → YES = `interesting` (must have attribution: who/what source). NO → Q2.
- Q2: "Is this a fact ABOUT the user - their opinions, realizations, network, or preferences?" → YES = `system`. NO → don't extract.
- Explicit ban: "NEVER put the user's own realizations or opinions in INTERESTING. INTERESTING is ONLY for external wisdom from others."
- `interesting` requires: external source, attribution ("Source: actionable insight" format), actionable advice/framework — examples given are all attributed (Paul Graham, Slack msg from Sarah, LinkedIn/Naval, etc.)
- Hard exclusions: current activity ("user is writing/browsing/coding"), trivial content (notifications, tab counts), generic/obvious facts, news/current events.
- Banned language: hedging ("likely", "possibly", "seems to", "may be", "might"), filler ("indicating a...", "suggesting a..."), transient verbs ("is working on", "is browsing").
- Format: max 15 words/memory, no vague time references (timeless, not "Thursday"/"next week"), use real names when visible.
- Bias: "DEFAULT TO EMPTY LIST — only extract if the memory is truly exceptional"; "Better to extract 0 memories than to include low-quality ones."

**Dedup**: `previousMemories` array, max 20 (`maxPreviousMemories`), inserted at index 0 and trimmed from the end (`removeLast()`) — i.e. most-recent-first, oldest dropped. Fed back into the prompt every call (not persisted across app restarts — in-memory only on the actor).

**Save flow** (`handleResultWithScreenshot`):
1. Confidence gate (see above).
2. Push into in-memory `previousMemories`.
3. `saveMemoryToSQLite` → `MemoryStorage.shared.insertLocalMemory(record)` — **local SQLite first**, `MemoryRecord(backendSynced: false, content, category, source: "desktop", screenshotId, confidence, sourceApp, windowTitle, contextSummary)`.
4. `syncMemoryToBackend` → `APIClient.shared.createMemory(content:visibility:"private":category:confidence:sourceApp:contextSummary:windowTitle:)`.
5. On backend success, `MemoryStorage.shared.markSynced(id: recordId, backendId: backendId)` updates the local row with the backend id.
6. `AnalyticsManager.shared.memoryExtracted(memoryCount: 1)`.
7. Notification only if `notificationsEnabled` (title "Wisdom Captured" for `interesting`, "Memory Saved" for `system`).
8. `sendEvent("memoryExtracted", ...)` to Flutter/UI bridge.

---

## B. Embeddings Service (Mac)

**`EmbeddingService`** (actor, singleton). `embeddingDimension = 3072`. Model name from `ModelQoS.Gemini.embedding` (indirection — actual string not in this file).

**Endpoints** (via the desktop backend proxy, `OMI_DESKTOP_API_URL`):
- Single: `POST {proxyBase}v1/proxy/gemini/models/{model}:embedContent`
- Batch (≤100/call per doc comment): `POST {proxyBase}v1/proxy/gemini/models/{model}:batchEmbedContents`
- Both attach Firebase `Authorization` header via `AuthService.shared.getAuthHeader()`.
- Both **normalize to unit length** (`normalize()`, vDSP) before returning/storing, so `searchSimilar`'s dot product is a valid cosine similarity (`cosineSimilarity` just does `vDSP_dotpr`, no re-normalization at search time — relies on stored vectors already being unit vectors).

**In-memory index**: `[TaskEmbeddingKey: [Float]]`, cap **`maxIndexSize = 5000`** (~12KB/embedding × 5000 ≈ 60MB). Indexes **`action_items` + `staged_tasks`** tables only (task/action-item semantic search, NOT the memories table — memories have no embedding index in this codebase). `loadIndex()` fills action_items first (`rows.suffix(maxIndexSize)` = newest by id), then fills remaining capacity from staged_tasks.

### Bug fix 1 — source-namespaced composite key (id-collision fix)

```swift
/// Which table an embedding-index entry came from. `action_items` and
/// `staged_tasks` are separate SQLite tables whose autoincrement rowids both
/// start at 1, so a raw-`Int64`-keyed index silently collides low ids across the
/// two tables. Carrying the source makes the key unique and lets search results
/// be resolved against the correct table deterministically.
enum TaskEmbeddingSource: String, Sendable {
  case actionItem
  case staged
}

/// Composite key for the in-memory task-embedding index (source + row id).
struct TaskEmbeddingKey: Hashable, Sendable {
  let source: TaskEmbeddingSource
  let id: Int64
}
```
`index: [TaskEmbeddingKey: [Float]]` (not `[Int64: [Float]]`). `searchSimilar` returns `(source, id, similarity)` tuples so callers resolve against the correct table instead of guessing.

### Bug fix 2 — batch-count guard before zipping

```swift
// Gemini returns embeddings 1:1 in request order. Callers zip results back to
// their input texts by position (backfill, OCR indexing), so a dropped or
// extra entry would silently persist an embedding onto the WRONG task. Fail
// the batch on any count mismatch or malformed entry instead of compactMap-ing
// (which would shift every subsequent embedding by one).
guard embeddings.count == texts.count else {
  throw EmbeddingError.invalidResponse
}
return try embeddings.map { embedding in
  guard let values = embedding["values"] as? [Double] else {
    throw EmbeddingError.invalidResponse
  }
  return normalize(values.map { Float($0) })
}
```
(In `embedBatch`, `EmbeddingService.swift` lines ~155-169.)

**`searchSimilar(query:topK:)`**: linear scan over the whole in-memory index (`for (key, stored) in index`), computes cosine sim via `vDSP_dotpr`, sorts descending, takes `prefix(topK)` (default 10). No ANN/vector-db — a flat scan capped by `maxIndexSize`.

**Backfill** (`backfillIfNeeded`): batches of 100, `ActionItemStorage`/`StagedTaskStorage`.`getItemsMissingEmbeddings(limit:)`, `embedBatch`, then per-item `updateEmbedding` + `addToIndex(source:id:embedding:)`, 200ms sleep between batches (rate-limit courtesy). Stops early (logs, doesn't throw) on `EmbeddingError.isExpectedBackendState` (402/429 = product gate / rate limit).

**`ActionItemStorage.getAllEmbeddings()`** (used by `loadIndex`) has **no LIMIT/OFFSET at all** — `SELECT id, embedding FROM action_items WHERE embedding IS NOT NULL` fetches every row; the 5000 cap is applied client-side via `rows.suffix(maxIndexSize)` in Swift, not in SQL.

---

## Memory-cache pagination rule (raw offset, not filtered/visible count)

Found in `MainWindow/Pages/MemoriesPage.swift` (`MemoriesViewModel.loadMore()`), not the embeddings file, but this is the pattern the audit is pointing at. Two independent cursors:
- `currentOffset` — SQLite/local-cache cursor (tier-filtered/visible).
- `rawBackendOffset` — raw backend-page cursor (pre-filter).

```swift
// Pagination state
private var currentOffset = 0
// Tracks the raw backend fetch cursor independently from the visible/SQLite
// cursor (currentOffset). The API returns unscoped/default-scope pages that
// may contain items excluded by the current layer filter. Advancing the
// backend offset by only the visible count would re-request part of the same
// raw page on the next loadMore(), causing overlapping pages and duplicates.
private var rawBackendOffset = 0
```

Local-cache page (raw SQLite rows, no additional filtering beyond the query itself):
```swift
// Advance the SQLite paging cursor by the RAW row count returned by the
// query, not the tier-filtered visible count. getLocalMemories(offset:)
// pages over raw rows, so advancing by the smaller filtered count makes the
// next page re-fetch the filtered-out rows — duplicate/stuck paging once
// hasMoreMemories (below) correctly stays true on a filtered page.
currentOffset += moreFromCache.count
hasMoreMemories = moreFromCache.count >= pageSize
```

Backend API page (filtered client-side by `layerAllowed`):
```swift
memories.append(contentsOf: visibleNewMemories)
currentOffset += visibleNewMemories.count
// Advance the raw backend cursor by the raw page size so the next fetch
// starts after all items in this page, not just the visible subset.
rawBackendOffset += newMemories.count
hasMoreMemories = newMemories.count >= pageSize
```
i.e. **the rule is: advance the cursor that feeds the NEXT request's `offset` by the count of rows the server/DB actually returned (pre-filter), and advance a separate display cursor by the post-filter visible count** — conflating the two causes either re-fetch-and-duplicate (advancing raw offset by filtered count) or skip (the reverse). A third related site: soft-delete backs `currentOffset` off by one immediately (row disappears from `getLocalMemories` before the backend row is gone), while `rawBackendOffset` is only decremented later in `performActualDelete` once the backend row is actually removed (undo window keeps it in the backend page).

---

## Windows delta

**Confirmed**: `lib/memoryExtract.ts` is **NOT** the continuous/screenshot extraction — it's the one-shot **paste importer** (`OnboardingMemoryLogImportService` port): user pastes a ChatGPT/Claude memory-log export, it's sent as one `POST /v2/chat/completions` call (Claude Haiku "synthesis" model, not Gemini vision) with a 40k-char cap, extracts 12-18 memories, dedupes against existing via prompt + exact-match normalize() guard. No screenshot loop, no interval, no confidence score, no category (system/interesting) split, no per-frame anything.

**Confirmed**: `lib/memoryRank.ts` is a pure **lexical/token-overlap ranker** (`rankMemories(memories, query, limit)`) — tokenizes query + memory content, scores by count of shared distinct tokens (stopword-filtered), ties break by recency. No embeddings, no vectors, no cosine similarity — a bag-of-words substitute.

**What must be built for parity** (does not exist on Windows at all):
1. **Continuous memory extraction**: no screen-capture-driven Gemini-vision loop exists. Nothing analogous to `MemoryAssistant`'s frame-buffer/interval/dedup/categorization/confidence pipeline.
2. **Embeddings service**: no `EmbeddingService` equivalent — no Gemini `embedContent`/`batchEmbedContents` proxy calls, no in-memory vector index, no semantic search over action items/staged tasks. `memoryRank.ts`'s lexical scoring is the only "ranking" capability today.

**Pagination bugs — status update (already fixed, not present as described in the brief)**:
- `lib/memoriesBulk.ts` `fetchAllMemories()` **already implements the raw-offset-advance rule correctly**: `offset += page.length` (raw page size, not a filtered/dedup-shrunk count), dedup via `Map<id>`, loop bound `offset < 100_000`, explicit comment citing the backend's forced-5000-at-offset-0 behavior as the reason a fixed `+200` step would be wrong. This matches the Mac pattern.
- `lib/appMemories.ts` `purgeAppMemoriesOnce` → `purgeAppMemories()` **already uses the shared `fetchAllMemories()` pager** (comment: "Uses the shared fetchAllMemories pager (memoriesBulk.ts) so every fetch-all path shares one cap/dedupe implementation instead of drifting independently") — it does NOT miss items past 5000; it pages to the shared 100k cap first, then deletes.
- **The real inconsistency that still exists**: `hooks/useMemories.ts` `fetchMemories()` — used by the Memories page for display — does a **single** `GET /v3/memories?limit=500&offset=0` call and never pages further. Per its own comment, the backend forces `limit=5000` at `offset=0` regardless of the requested value, so this call silently caps at whatever the server returns for the first page (up to 5000) and **never fetches a second page** — unlike `fetchAllMemories` (100k cap, multi-page). `pages/Memories.tsx` additionally clamps rendering to `RENDER_CAP = 400` (`Memories.tsx:14`, `Memories.tsx:135`, `Memories.tsx:470-472`) client-side after that. So an account with >5000 memories: the Memories page will never show the tail past the first ~5000 (no second page requested), while bulk export/purge (via `fetchAllMemories`) will still reach all of them up to 100k. File:line: `desktop/windows/src/renderer/src/hooks/useMemories.ts:43-58` (single-page fetch, comment explicitly says "this single call already returns up to 5000 memories" — no further paging follows).
