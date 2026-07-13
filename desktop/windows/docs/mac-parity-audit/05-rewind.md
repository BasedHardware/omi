# Mac→Windows Parity Audit — Rewind (depth delta)

> Scope: depth comparison of continuous screen recording, OCR, semantic search, timeline UI, action items, and transcription integration. Windows baseline checked: `desktop/windows/src/main/rewind/*`, `desktop/windows/src/main/ocr/*`, `desktop/windows/src/renderer/src/{pages/Rewind.tsx,hooks/useRewind.ts,components/rewind/*}`, `desktop/windows/src/main/ipc/db.ts` (rewind_frames schema), `desktop/windows/src/shared/{rewindExclusions,timelineGeometry}.ts`.

## Summary table

| Rewind capability | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Frame storage format | `VideoChunkEncoder.swift` | Present-but-weaker (raw per-frame JPEGs, not video) | H |
| OCR pipeline | `RewindOCRService.swift` | Present-but-weaker (external helper binary, no bounding boxes) | H |
| OCR semantic/embedding search | `OCREmbeddingService.swift` | Absent | H |
| Full-text search engine | `RewindDatabase.swift` (FTS5) | Present-but-weaker (SQL `LIKE`, no FTS) | M |
| Search UI reachability | `RewindPage.swift` (always-on unified search bar) | Absent (built but dead-code gated, unreachable) | H |
| Date navigation (browse any day) | `RewindPage.swift` `datePickerControls` | Absent (fixed last-24h window only) | M |
| Search-result grouping | `RewindModels.swift` `groupedByContext` | Present-equivalent (`rewindGrouping.ts`) | — |
| Frame dedup + periodic anchor | `RewindOCRService.swift` + `RewindIndexer.swift` | Present-but-weaker (dedup only, no anchor) | M |
| Battery/power-aware capture cadence | `PowerMonitor.swift` + `VideoChunkEncoder.swift` | Absent | M |
| OCR bounding boxes / on-image highlight | `RewindOCRService.swift`, `SearchHighlightOverlay` | Absent | M |
| Database corruption recovery | `RewindDatabase.swift` (WAL cleanup, backup, `.recover`, rebuild-from-video) | Absent | M |
| Playback controls (speed, skip-to-end) | `RewindTimelinePlayerView.swift` | Present-but-weaker (fixed 700ms play, no speed/skip) | L |
| Keyboard navigation | `RewindPage.swift` (arrows, esc, scroll-to-scrub) | Absent | L |
| Action-item extraction from screen | `ActionItemModels.swift` (`screenshotId`, `sourceApp`, agent fields) | Absent | H |
| Screen observations (context tracking) | `ObservationRecord.swift` | Absent | M |
| Transcription/live-notes tied to Rewind page | `RewindPage.swift` `expandedTranscriptView` | Absent | M |
| Retention cleanup granularity | `RewindIndexer.runCleanup` (chunk-orphan aware) | Present-equivalent (simpler, but correct for JPEG-per-frame model) | — |

## Screen capture: storage format

**What it is:** How captured frames are persisted to disk.

**Where (Mac):** `Desktop/Sources/Rewind/Core/VideoChunkEncoder.swift`

**How it works:** Mac buffers frames and encodes them into 60-second H.265 (HEVC) video chunks via `AVAssetWriter`/`VideoToolbox` (first chunk is a 5s "fast start" so the UI shows frames within seconds of launch). Output resolution is capped at 3000px on the long edge, bitrate is estimated from resolution × framerate (350kbps–8Mbps), and aspect-ratio changes are debounced (2s stability window) before starting a new chunk to avoid encoder churn from rapid app switching. A staleness timer finalizes a chunk if no new frame arrives within `chunkDuration + 10s`, releasing the hardware encoder. Frame rate is derived from the effective capture interval (`RewindSettings.effectiveCaptureInterval`). Screenshots reference a `videoChunkPath` + `frameOffset` (frame index) rather than storing a standalone image; frames are decoded on demand via `AVAssetReader` (with an `ffmpeg` fallback for corrupted/legacy chunks).

**Windows status:** Present-but-weaker. `captureService.ts` (`ingestRewindFrame`) writes each captured frame as an individual JPEG file to `<userData>/rewind/<day>/<ts>.jpg` (`paths.ts`). There is no video encoding, no chunking, no resolution/bitrate management, and no `ffmpeg`/decoder dependency — but also no storage-density benefit: N screenshots means N full JPEG files instead of a compressed multi-frame stream. `rewind_frames` table (`db.ts:160`) stores `image_path` directly per row.

**Value / notes:** High. At Mac's default 1 frame/~1–3s cadence with H.265 chunking, a day of Rewind history is a fraction of the size of a day of discrete JPEGs at the same cadence (H.265 exploits inter-frame redundancy of a mostly-static desktop; JPEG-per-frame does not). This is a storage/disk-I/O scalability gap, not just a feature gap — Windows retention (`retentionRunner.ts`) has to delete far more files far more often to stay within the same disk budget.

## OCR pipeline

**What it is:** Extracting searchable text (and its position) from each captured frame.

**Where (Mac):** `Desktop/Sources/Rewind/Core/RewindOCRService.swift`

**How it works:** Uses Apple's on-device Vision framework (`VNRecognizeTextRequest`, `.accurate` level, language correction on, `en-US`). Every result includes per-block bounding boxes (`OCRTextBlock`: normalized x/y/width/height + confidence), not just flat text, so exact match locations can be highlighted on the displayed screenshot. A perceptual dHash (9×8 downscale, 64-bit) with a Hamming-distance-≤5 threshold skips OCR for perceptually-identical frames (cursor blink, spinner) — `RewindIndexer` additionally throttles to every 3rd frame (`ocrEveryNthFrame`) even when content changes, and skips OCR outright while on battery (backfilled later when AC reconnects, via `PowerMonitor.onACReconnected`).

**Windows status:** Present-but-weaker. `src/main/ocr/` wraps a separate C# WinRT helper process (`win-ocr-helper/Program.cs`, built via `pnpm run build:ocr-helper`, a manual/postinstall step — not guaranteed present at runtime; `helperProcess.ts` logs "OCR / screen-reading is DISABLED" and fails fast if the binary is missing). OCR runs as an async backfill loop (`ocrService.ts` `startRewindOcr`, every 4s / 5 frames per batch) against `unindexedRewindFrames`, plus a best-effort synchronous "current screen" OCR on each captured frame (`captureService.ts` `refreshCurrentScreen`, single-flight, feeds `currentScreen.ts` for chat context — this itself has no Mac equivalent, see below). Results are flat `ocr_text` strings only — the schema (`db.ts:160`) has no bounding-box/JSON column, so there is no way to highlight *where* in the frame a match occurred, and no per-block confidence.

**Value / notes:** High. The missing bounding-box data is a structural gap (not just "could be added later easily" — it requires a schema change and a different OCR result shape from the WinRT API), and it's what powers Mac's on-image search highlighting (`ScreenshotThumbnailView`/`SearchHighlightOverlay`, not separately audited here but consumes `OCRTextBlock`).

## OCR embeddings + semantic search

**What it is:** Vector-similarity search over screen history in addition to keyword search.

**Where (Mac):** `Desktop/Sources/Rewind/Services/OCREmbeddingService.swift`, `RewindDatabase.swift` (embedding columns/migrations on `screenshots`).

**How it works:** Screenshot OCR text (prefixed with `[AppName] WindowTitle`) is embedded via a Gemini embedding model (`EmbeddingService`, `RETRIEVAL_DOCUMENT` task type), batched (60s flush window or 100-item cap) and content-hash deduplicated to cut API calls ~20x. Embeddings (3072 floats, stored as BLOB) are searched with disk-based cosine similarity (`vDSP_dotpr` via Accelerate) in 5000-row batches — no in-memory ANN index, keeps a running top-K. `RewindViewModel.performSearch` runs FTS and vector search **in parallel** and merges results (FTS first, then vector-only hits above a 0.5 similarity threshold), so a query like "the meeting about pricing" can match without the literal words appearing on screen. A background backfill (capped 5000 items/launch) embeds historical screenshots that predate the feature or were skipped.

**Windows status:** Absent. No embedding generation, no vector column, no similarity search anywhere in `rewind/*`. `rewindSearchQuery.ts` builds a pure SQL `LIKE`-based query (see next section) — that is the *entire* search capability.

**Value / notes:** High — this is the single largest capability gap in Rewind. Mac's Rewind search can find content by meaning; Windows can only find content that contains the exact typed substring.

## Full-text search engine

**What it is:** The keyword-search backend.

**Where (Mac):** `Desktop/Sources/Rewind/Core/RewindDatabase.swift` (`screenshots_fts`, later normalized `ocr_texts_fts` — SQLite FTS5 virtual tables with `unicode61` tokenizer, kept in sync via triggers).

**How it works:** FTS5 gives tokenized, ranked, prefix-capable search over `ocrText`, `windowTitle`, and `appName`, with a normalized `ocr_texts`/`ocr_occurrences` schema (migration 9) that deduplicates identical OCR text blocks across screenshots (smaller index, supports per-occurrence bounding boxes).

**Windows status:** Present-but-weaker. `rewindSearchQuery.ts` tokenizes the query (max 8 tokens, 512 chars), escapes each token, and ANDs together `LIKE '%token%'` clauses across `ocr_text`, `window_title`, `app` (`db.ts` `searchRewindFrames`). This works for substring matches but has no tokenization-aware ranking, no stemming/prefix matching, and `LIKE '%...%'` can't use an index — it's a full table scan of `rewind_frames`, which will degrade as history grows (no LIMIT-aware pagination beyond a flat 500-row cap).

**Value / notes:** Medium. Functionally works for the common case (exact word present), but won't scale as gracefully and lacks the ranking/ordering FTS5 gives Mac's results.

## Search UI reachability

**What it is:** Whether the Rewind search feature can actually be invoked by a user.

**Where (Mac):** `Desktop/Sources/Rewind/UI/RewindPage.swift` — the search field (`unifiedTopBar` → `searchField`) is always visible at the top of the Rewind page; typing immediately debounces (300ms) into `performSearch`.

**Windows status:** Absent in practice. `pages/Rewind.tsx` gates the entire search UI (search bar + `SearchResultsFilmstrip`) behind `const [showSearch, setShowSearch] = useState(false)`, with the comment *"Search hidden for now (keeps the search view code in place behind showSearch, which stays false)"*. There is no button, keyboard shortcut, or any other code path in `Rewind.tsx` that ever calls `setShowSearch(true)`. `RewindSearchBar.tsx`, `SearchResultsFilmstrip.tsx`, `useRewind().search()`, `rewindSearchQuery.ts`, and `searchRewindFrames()` are all fully implemented and wired end-to-end — but the only UI entry point to reach them is dead.

**Value / notes:** High. This means Windows Rewind search is currently **0% reachable from the UI**, independent of the semantic-search gap above — a user cannot search their screen history at all today, only scrub the timeline manually or use the separate chat "current screen" cache (which only covers the single most recent frame, see below).

## Date navigation

**What it is:** Browsing Rewind history for an arbitrary past day.

**Where (Mac):** `RewindPage.swift` `datePickerControls` (a `DatePicker` popover bound to `viewModel.selectedDate`, calls `filterByDate`).

**Windows status:** Absent. `useRewind.reload()` always computes `to = bounds.max ?? Date.now()` and `from = to - DAY_MS` — i.e. it always shows the most recent 24 hours of captured frames. There is no date picker or other UI/state in `Rewind.tsx`/`useRewind.ts` to request a different day.

**Value / notes:** Medium. Combined with the retention window (default 14 days on Windows vs. 7 on Mac), history exists on disk but is unreachable in the timeline UI beyond the last 24h.

## Frame dedup + periodic anchor frames

**What it is:** Avoiding wasted storage/OCR on unchanged screens, while still keeping the timeline populated during long static periods.

**Where (Mac):** `RewindOCRService.dHash`/`shouldSkipOCR` (skips *OCR*, not capture) + `RewindIndexer.shouldSkipFrameForDedupe`/`frameDedupeMaxInterval` (skips *encoding+DB insert* for a perceptually-identical frame, but only for up to 30s — after that a fresh anchor frame is written even if nothing changed, so a long static screen still produces timeline coverage).

**Windows status:** Present-but-weaker. `captureDecision.ts` computes an average-hash (16×9) and skips the entire frame (`reason: 'duplicate'`) when Hamming distance ≤4 from the last *captured* hash, with no time-boxed anchor override — `lastHash` only updates on an actual capture (`captureService.ts`), so a screen that never changes will never re-arm the dedup gate and will produce **zero** frames in the timeline for that entire span, however long it lasts.

**Value / notes:** Medium. This is a real timeline-completeness gap: e.g. someone reading a single static PDF page for an hour would show as a total blank gap on Windows, vs. periodic anchor frames every 30s on Mac.

## Battery/power-aware capture cadence

**What it is:** Reducing capture frequency and OCR work on battery to save power.

**Where (Mac):** `Services/PowerMonitor.swift` (IOKit power-source monitoring) + `RewindSettings.effectiveCaptureInterval(isOnBattery:)` (3× interval multiplier on battery) + `RewindIndexer` skips OCR entirely on battery, backfilling via `PowerMonitor.onACReconnected`.

**Windows status:** Absent. `captureService.ts` only checks `powerMonitor` for lock-screen state and `getSystemIdleTime()` for idle — there is no battery/AC-power branch anywhere in `rewind/*`, so capture cadence and OCR run identically regardless of power source. (This is a laptop-specific gap; irrelevant on desktop Windows machines.)

**Value / notes:** Medium — real but narrower in blast radius than the other gaps (only affects battery-powered Windows laptops).

## Database corruption recovery / crash resilience

**What it is:** Recovering the Rewind index if the SQLite database is corrupted (crash, disk I/O error, unclean shutdown).

**Where (Mac):** `RewindDatabase.swift` — extensive: unclean-shutdown detection via a running-flag file, stale/empty WAL cleanup, `quick_check` integrity verification, full corruption recovery via `sqlite3 .recover` piped into a fresh DB (falling back to direct `screenshots` table extraction), timestamped backups (keeps last 5), and a user-facing "Database Recovered" banner in `RewindPage.swift` with a **"Rebuild Index"** action that re-scans all video chunk files on disk and reconstructs the database from them (`RewindIndexer.rebuildFromVideoFiles`).

**Windows status:** Absent (Rewind-specific). No corruption detection, backup, or rebuild-from-frames path exists in `rewind/*`. (General `db.ts` may have its own generic error handling not scoped to this audit, but there is no Rewind-specific recovery UI or "rebuild from disk" path — and since Windows doesn't retain a video-chunk stream, a from-scratch rebuild would only be able to recover file paths/timestamps, not re-derive OCR text without re-running OCR on every JPEG.)

**Value / notes:** Medium. Lower urgency than the search gaps, but a corrupted `rewind_frames` table on Windows today has no recovery path other than losing the index (the JPEGs on disk would survive, but nothing rebuilds pointers to them).

## Playback controls

**What it is:** Auto-playing through captured frames like a video scrubber.

**Where (Mac):** `RewindTimelinePlayerView.swift` — play/pause, previous/next frame, skip-to-start/end, and a playback-speed menu (0.5×/1×/2×/4×/8×, adjusts the timer interval).

**Windows status:** Present-but-weaker. `Rewind.tsx` has a single Play/Pause toggle; `useRewind.ts` advances the cursor on a fixed 700ms interval with no speed control, no skip-to-start/end, and no previous/next-frame stepping buttons.

**Value / notes:** Low — a nice-to-have, not core to the feature's usefulness.

## Keyboard navigation

**What it is:** Arrow-key frame stepping, Escape to exit search/modes, scroll-wheel scrubbing.

**Where (Mac):** `RewindPage.swift` — `.onKeyPress(.leftArrow/.rightArrow/.upArrow/.downArrow/.escape)` plus a global scroll-wheel monitor (`onScrollWheel`) that moves the playhead directly.

**Windows status:** Absent. No `onKeyDown`/arrow-key handling found in `Rewind.tsx` or `useRewind.ts`. `RewindTimelineBar.tsx` does translate vertical mouse-wheel into horizontal *pan* (`onWheel` → `scrollLeft`) but that pans the view, it does not move the playhead/cursor the way Mac's scroll-to-scrub does.

**Value / notes:** Low-medium — reduces efficient power-user navigation but doesn't block core functionality (click-to-seek on the timeline bar still works).

## Action-item extraction from screen

**What it is:** Automatically detecting tasks/to-dos visible in screen content and turning them into tracked action items.

**Where (Mac):** `Core/ActionItemModels.swift` (`ActionItemRecord` — has `screenshotId`, `sourceApp`, `windowTitle`, `confidence`, `contextSummary`, `currentActivity`, agent-session fields for launching a Claude coding agent against a detected task, plus a `staged_tasks` promotion pipeline).

**Windows status:** Absent. No `screenshotId`/`sourceApp`/`windowTitle`/agent fields anywhere in the Windows schema tied to a rewind frame; no extraction pipeline reads `rewind_frames.ocr_text` to produce tasks. (Windows may have some other, unrelated task/action-item feature elsewhere in the app — out of scope here; the point is nothing in `rewind/*` feeds it.)

**Value / notes:** High. This is a core "Rewind → automatically surfaces actionable work" capability on Mac that has zero equivalent hook on Windows.

## Screen observations (context tracking)

**What it is:** A background record of *every* screen analysis pass (not just ones that found a task), used for chat context / activity summaries.

**Where (Mac):** `Core/ObservationRecord.swift` (`observations` table: `appName`, `contextSummary`, `currentActivity`, `hasTask`, `sourceCategory`/`sourceSubcategory`).

**Windows status:** Absent — no equivalent table or pipeline in `rewind/*` or `db.ts`. Windows' closest analog is the single-slot `currentScreen.ts` cache (most-recent-frame OCR text only, 30s freshness, used for chat's "what's on my screen right now" — not a history of observations).

**Value / notes:** Medium.

## Transcription/live-notes tied to the Rewind page

**What it is:** Rewind's page hosts the live meeting transcript + AI notes panel inline (not a separate screen), so screen history and conversation context share one surface.

**Where (Mac):** `RewindPage.swift` `expandedTranscriptView` (split panel: `LiveTranscriptPanel` + `LiveNotesView`, speaker naming sheet, "Finish Conversation" button) — backed by `TranscriptionModels.swift`/`TranscriptionStorage.swift` (crash-safe recording sessions with retry/backoff, structured conversation data, live AI-generated notes).

**Windows status:** Absent from the Rewind surface. `pages/Rewind.tsx` has no transcript/notes panel, no recording bar, no "Finish Conversation" action — it is purely a screenshot timeline + (unreachable) search. (Windows likely has its own separate transcription/meeting UI elsewhere in the app; the gap is specifically that Rewind and live transcription are not the same integrated surface the way they are on Mac.)

**Value / notes:** Medium — a product-integration gap more than a missing subsystem, since transcription itself may exist elsewhere on Windows.

## Search-result grouping (parity)

**What it is:** Clustering consecutive same-app/same-window frames within a time window into one result, so search results aren't one row per near-duplicate frame.

**Where (Mac):** `RewindModels.swift` `Array<Screenshot>.groupedByContext(timeWindowSeconds: 30)`.

**Windows status:** Present-equivalent. `rewindGrouping.ts` `groupFrames` uses the same 30s window (`GROUP_WINDOW_MS`), same-app/same-window-title clustering, and produces a representative frame + snippet, newest-group-first — algorithmically a close match to Mac's approach. Noted here as parity, not a gap, since this piece is currently unreachable anyway (see "Search UI reachability").

## Spotted outside my scope

- General (non-Rewind) SQLite corruption/backup handling in `desktop/windows/src/main/ipc/db.ts` was not audited beyond the `rewind_frames` table.
- Whether Windows has a transcription/meeting-notes feature *elsewhere* in the app (outside the Rewind page) was not investigated — flagging only that it isn't integrated into the Rewind surface itself.
- Whether Windows has any task/action-item feature elsewhere fed by other sources (calendar, chat, etc.) was not investigated — only that nothing in `rewind/*` feeds one.
- `SENSITIVE_WINDOW_MARKERS`-based login/private-window title filtering (`shared/rewindExclusions.ts`) appears to be a Windows capability with **no Mac equivalent** found in the files reviewed (Mac only excludes by app name, not window-title content) — worth flagging to whoever compiles the Windows→Mac direction of this audit, since it wasn't in scope here (Mac-has/Windows-lacks only).
- `desktop/windows/src/main/ocr/win-ocr-helper/Program.cs` internals (the actual WinRT OCR call) were not read in depth — only confirmed it's an external, separately-built process with no bounding-box output surfaced to the DB schema.
