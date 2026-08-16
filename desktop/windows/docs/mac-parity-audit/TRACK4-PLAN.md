# Track 4 — Rewind, Conversations & Capture: Master Plan

> Orchestrator working doc for `feat/win-rewind-shell`. Ground truth extracted 2026-07-14 from
> current Windows source (`.worktrees/track4-rewind-conv`), Mac reference (`.worktrees/mac-ref` @
> `v0.12.72+12072-macos`), and the current `main` backend. Binding UI ruling (Chris): match Mac
> layout/IA/content/copy/flow/brand incl. **purple ports as-is** (userBubble `#43389F`, speaker
> colors incl. dark-purple), but render with clean Windows-native (Fluent) components — no SwiftUI
> chrome clones. Bar/orb overlay EXEMPT. See mac-ui-port/05 + charter/01-04.

## Ground-truth CORRECTIONS to the brief/specs (verified, do not chase ghosts)

1. **`showSearch` is NOT a dead flag.** `pages/Rewind.tsx:17` — it actively toggles search vs
   timeline view (Ctrl/Cmd+F, Escape, buttons). Search UI already works. "Un-gating" is a
   non-task. Real Rewind work = FTS5, semantic, bounding-box overlay, Mac day-scoped redesign.
2. **C3 (action-item 422) already FIXED.** `ConversationDetail.tsx:245-262` sends
   `{items_idx:[idx], values:[next]}` — matches backend `SetConversationActionItemsStateRequest`.
   KEEP Windows' interactive toggle (Mac renders read-only). Don't touch the contract.
3. **`ConversationMutationResponse{status,conversation}` does NOT exist on `main` backend.** Only
   in the unmerged mac-ref snapshot. Current backend + current generated client both use bare
   `{status}` (title/starred) / `FolderMutationResponse{status}` (folder). **No omiApi regen for
   this.** Generated client already has folders/merge/assign-bulk/people types.
4. **No platform-header divergence.** Every conversations/folders/merge/action-item/speaker
   endpoint ignores `X-App-Platform` for logic; telemetry maps `windows→desktop`. Nothing to fix
   server-side.
5. **C7 OCR-helper dispose already FIXED** (`main/index.ts:910` on `will-quit`).
6. **`lifecycle.ts` does not exist** — crash/quit/launch-at-login logic lives in `main/index.ts`.
   Create `main/lifecycle.ts` for new shell logic; keep `index.ts` edits minimal (hotspot).
7. **`skippedForBattery` is legacy on Mac** — battery savings are cadence-only (3× interval), no
   OCR deferral. Do NOT port the skipped-for-battery column/backfill machinery.

## Current Windows state (baseline)

- **Capture**: renderer `getUserMedia` 1fps (`RewindCaptureHost.tsx`), JPEG q0.6, aHash dedup
  (`frameHash.ts`, hamming ≤4 = dup). Per-day dirs `<userData>/rewind/YYYY-MM-DD/<epochms>.jpg`.
  Gating: locked / idle≥60s / excluded-app / sensitive-title / dup. **No** 30s keyframe anchor,
  **no** battery cadence, **no** sleep/suspend handling (lock IS handled), **no** orphan sweep,
  **no** corruption recovery.
- **OCR**: C# helper (`main/ocr/`), length-prefixed stdio. Hot path (`captureService.refreshCurrentScreen`)
  + backfiller (`ocrService.ts`, 5/4s). `OcrResult.lines` (boxes) computed but only flattened
  `ocr_text` persisted. **No embeddings.**
- **Search**: SQL `LIKE` over `ocr_text/window_title/app` (unindexed → full scan),
  `rewindSearchQuery.ts`. No FTS5, no vector, no bounding-box overlay, no list/timeline toggle.
- **Timeline**: continuous break-collapsing pannable bar (`RewindTimelineBar.tsx`, PX_PER_HOUR=140,
  30-min break→16px zigzag). Static frame viewer + optional 700ms auto-advance (`useRewind.ts`).
  No date picker, not day-scoped. → **REPLACE with Mac day-scoped model** (ruling).
- **Conversations**: flat list, filters all/chat/recording, client-side search, sync badges
  (pending/failed/not-synced), backfill banner, multi-select delete + clipboard "share". **No**
  folders/starred/date-filter/merge/date-grouping/drawer/speaker-naming. Detail = stacked cards
  (summary/action-items/transcript), interactive action items (fixed). Speaker chips = hashed
  glass palette (emerald/sky/teal/amber/rose/neutral, no purple), `SPEAKER_00→S00`, no avatars,
  no tap-to-name.
- **File index**: `SKIP_DIRS` = 4 (`.Trash,node_modules,.git,__pycache__`), MAX_DEPTH 3, 500MB
  cap. **No periodic re-scan** (manual/onboarding only). **Fail-open deletion bug**: `readDir`
  returns `[]` on any error → `clearIndexedFiles()`+`replaceIndexedFiles()` wholesale replace →
  transiently-unreadable dir = all its files purged from index; clear+reinsert not atomic.
- **KG**: `local_kg_nodes/edges` superset (summary/aliases_json/source_refs). Write via
  worker_thread, wholesale-replace atomic. `terminate()` drops coalesced `pendingGraph` on quit.
  BrainGraph: `interactive` prop default true, both call sites pass `interactive={false}`
  (Memories.tsx:292 [Stream 3], Onboarding.tsx:280). No standalone viewer route. nodeColor
  `thing=#ff375f` pink (INV-UI-1). Local KG rebuild button in AdvancedTab.
- **Shell**: crash.log + uncaughtException/render-process-gone/child-process-gone handlers,
  Sentry opt-in (`sentry.ts`). **No** `lastSessionCleanExit`, **no** `PRAGMA integrity_check`.
  Launch-at-login opt-in/off, user-toggle-only (`index.ts:800-810`). Updater: electron-updater,
  autoDownload+autoInstallOnAppQuit, 45s+4h checks (`updater.ts`).
- **DB**: single `omi.db` (better-sqlite3, WAL). Two migration mechanisms: additive
  `CREATE TABLE IF NOT EXISTS`/`ensureColumn` in `db.ts get()` + versioned `dbMigrations.ts`
  (`PRAGMA user_version`, append-only, next=v2). New user tables also go in `USER_DATA_TABLES`
  (`dbWipe.ts`). Section style `// --- <label> ---`.

## Mac reference constants (behavioral contract to port)

- **Keyframe anchor** = the dedup gate itself: `frameDedupeMaxInterval=30.0`. Skip identical
  frame only if within 30s of last-encoded; >30s forces a write. Pre-encode gate.
- **Battery**: `batteryCaptureIntervalMultiplier=3.0`; `effective = onBattery ? base*3 : base`
  (base 3s Mac). On power flip: flush chunk + restart timer. Cadence-only.
- **Suspend/resume**: willSleep→pause; didWake→reinit capture + 1.5s settle + restart;
  screenLock→pause (no reinit); screenUnlock→reinit + immediate restart. Separate flags
  sleep-vs-lock.
- **Dedup**: OCR dHash threshold 5 (9×8 grayscale) + every-3rd-frame gate (`ocrEveryNthFrame=3`).
- **OCR/semantic**: VN accurate en-US. Embeddings Gemini **dim 3072**, format
  `"[appName] windowTitle\nocrText"`, minTextLen 20, fire-and-forget batched (60s or 100 items),
  SHA256 dedup, taskType RETRIEVAL_DOCUMENT (index)/RETRIEVAL_QUERY (search), cosine via
  normalized dot, topK 50, sim>0.5 (applied by caller). FTS+vector in parallel, vector failure
  non-fatal.
- **FTS5**: `screenshots_fts(ocrText,windowTitle,appName)` unicode61, content-linked + triggers,
  BM25 order, query expansion (camelCase split + digit-boundary split, each part `*`-suffixed,
  OR'd).
- **Retention**: 6h throttle, first-frame-after-launch runs immediately, cutoff today−days,
  options 3/7/14/30 default 7. Orphan video chunks removed reactively on last-row-delete;
  cleanupEmptyDirectories. (No FS-orphan sweep on Mac — Windows needs one because JPEG-write and
  row-insert are non-atomic → crash leaves orphan file. Windows-specific addition, justified.)
- **Corruption recovery** (port universal, skip pool-epoch): stale-WAL cleanup (0-byte only) →
  open-retry ladder → 3-tier salvage (`sqlite3 .recover` → direct-table salvage → fresh DB,
  backup-first, keep 5 backups) → unclean-shutdown flag file (`.omi_running`) → lightweight
  integrity check (page_count + `SELECT count(*) FROM sqlite_master`, NOT full quick_check) →
  IO-error counter (5 consecutive SQLITE_IOERR/CORRUPT) → close-for-recovery. Windows single
  better-sqlite3 connection: skip poolEpoch/initGeneration/configureGeneration plumbing.
- **Conversations detail**: 450pt trailing drawer, state machine locked/empty/loading/bubbles
  (`transcriptPresenceState`). Speaker bubbles: 32px avatar circle (user=purplePrimary, named
  non-user=purplePrimary@0.3, anon=backgroundQuaternary), bubble fill user=`userBubble #43389F`,
  others cycle `speakerColors[speakerId%6]`. Action items READ-ONLY on Mac (Windows keeps
  interactive).
- **speakerColors** (exact): `#2D3748 #1E3A5F #2D4A3E #4A3728 #3D2E4A(dark purple, idx4) #4A3A2D`.
  **userBubble** `#43389F`.
- **Speaker naming**: tap unnamed → NameSpeakerSheet (You / existing Person chips / +Add Person).
  Person is GLOBAL (`POST /v1/users/people`). Assign per-conversation via
  `PATCH /v1/conversations/{id}/segments/assign-bulk` body
  `{segment_ids, assign_type:'is_user'|'person_id', value}` (feeds speech training) OR
  `PATCH /v1/conversations/{id}/assign-speaker/{speaker_id}` (all segments of a speaker_id). Live
  naming buffered locally, persisted at finalization.
- **Folders**: `Folder{id,name,description,color(#6B7280),icon(folder),order,is_default,is_system,
  conversation_count}`. CRUD `GET/POST/PATCH/DELETE /v1/folders` (DELETE `?move_to_folder_id`),
  `POST /v1/folders/reorder`, `POST /v1/folders/{id}/conversations/bulk-move`,
  `GET /v1/folders/{id}/conversations`. Assign `PATCH /v1/conversations/{id}/folder` body
  `{folder_id}`. FolderTabsStrip: All/Starred fixed + chips + "+". Max 50 custom.
- **Merge**: `POST /v1/conversations/merge {conversation_ids(≥2), reprocess:true}` →
  fire-and-forget, returns `{status:'merging', conversation_ids}`, **new id NOT in response**
  (poll/refresh). Confirm alert "combine…delete originals…cannot be undone".
- **Finalization (C2)**: maxRetries=5, backoff `2^n·60s` = 1/2/4/8/16 min. Exhaustion →
  uploadLocalSegments (500-segment proportional compaction) if segments>0, else discard empty
  desktop session. maxLocalFallbackRetries=3.
- **LiveNotes**: `LiveNotesMonitor`+`LiveNotesAccumulator`, `wordThreshold=50` new words →
  Gemini Flash "concise note about what happened", persist to `NoteStorage`(`LiveNoteRecord`:
  sessionId,isAiGenerated,segmentStartOrder/EndOrder,text). Manual notes too. Loaded for crash
  recovery on session start, cleared on end. Displayed in `LiveNotesView` (AI toggle + add-note +
  per-note edit/delete). "Quick Note" just navigates to it.
- **Backend list/detail**: `GET /v1/conversations` limit/offset/statuses/start_date/end_date/
  folder_id/starred; list OMITS transcript_segments. Detail lazy-enriches `deferred` convs
  (returns processing, poll for completed). Action items positional (no id), by index.

## PR sequence (each: DoD, simplify→Opus audit, UI screenshot-verified by skeptical reviewer)

- **PR0 (LAND FIRST)** — Additive DB schema. See TaskCreate #1. Additive-only.
- **PR1** — Rewind FTS5 search: `rewind_frames_fts` + triggers + backfill migration; BM25 order;
  query expansion (camelCase + digit split, `*` prefix); persist `ocr_lines_json`; on-image
  bounding-box highlight overlay (purple stroke per ruling). Replace LIKE. Keep search UI.
- **PR2** — Rewind capture durability (`feat/win-rewind-durability`). GROUND-TRUTHED 2026-07-14 vs
  Mac source (4 extractors) — corrected from stale spec:
  - **30s keyframe anchor** (CONFIRMED Mac `frameDedupeMaxInterval=30.0`, RewindIndexer.swift:26/165):
    force-store a duplicate frame if >30s since last STORED frame. Windows lacks it. Main-side
    (`captureDecision.ts` + `captureService.ts` `lastCapturedAt`).
  - **Battery cadence 3×** (CONFIRMED Mac `batteryCaptureIntervalMultiplier=3.0`): on battery,
    effective interval = base×3. Windows base stays 1s (Mac base is 3s — deliberate divergence, do
    NOT change Windows default; renderer caps fps for a reason). Adapt to Electron: main reads
    `powerMonitor.isOnBatteryPower()` + `on('on-battery'|'on-ac')`, pushes effective interval to the
    renderer; on flip, renderer restarts its loop. NO OCR-defer on battery (Mac `skippedForBattery`
    is DEAD CODE — cadence-only).
  - **Sleep/lock reinit** (Mac: pause timer on sleep+lock; reinit capture + 1.5s settle on WAKE;
    reinit + restart IMMEDIATELY on UNLOCK). Windows: main `powerMonitor` 'suspend'/'resume'/
    'lock-screen'/'unlock-screen' → signal renderer (which owns the getUserMedia stream) to pause
    loop + teardown stream on suspend/lock, reacquire stream + restart on resume(1.5s)/unlock(0s).
  - **Orphaned-JPEG FS sweep** — Mac has NO disk→DB sweep (DB-row-driven retention only). KEEP as a
    Windows-storage-model fix: Windows stores per-frame JPEGs and a crash between writeFileSync and
    insertRewindFrame orphans a file forever. Conservative: delete only `<userData>/rewind/*/…jpg`
    with no matching DB row, past a grace window.
  - **OCR re-backfill parity** — DROPPED. Mac has only dead stubs; Windows already has a working 4s
    backfill loop (`ocrService.ts`). Windows is ahead; nothing to port.
  - **DB corruption recovery** — SPLIT to PR2b (Chris-gated, task #13): wide blast radius on core
    db.ts open path.
- **PR3** — Rewind redesign to Mac day-scoped: date picker (browse any day), list/timeline
  search-result toggle, sampled-to-500/day, keep static frame viewer (NO auto-play transport),
  recovery banner, empty/permission/capture-broken states. RewindTab settings parity
  (Storage/Excluded/Battery/Retention 3/7/14/30). Purple accents per ruling.
- **PR4** — Rewind semantic search (embeddings). DECISION: embedding source (local onnx vs
  backend endpoint) — investigate a client-facing embed endpoint; if none, local MiniLM or PARK.
  `rewind_embeddings` table already in PR0. Merge FTS+vector (sim>0.5), parallel.
- **PR5** — Conversations list redesign: FolderTabsStrip (All/Starred/folders/+), starred toggle
  + date-range filter, multi-select MERGE (confirm alert, poll after), emoji-tile rows, date
  grouping (Today/Yesterday/date), KEEP sync badges + backfill banner + chat/recording filter
  (Windows-ahead). Folders CRUD wired. Fluent components (centered modal dialogs, not sheets).
- **PR6** — ConversationDetail redesign: 450pt slide-in transcript drawer, speaker bubbles (Mac
  colors incl. dark-purple, userBubble, avatars), tap-to-name speaker (NameSpeakerSheet →
  people + assign-bulk), KEEP interactive action items. Wire cloud title/star/folder mutations.
- **PR7** — Capture C2 durability: app-crash-mid-recording rescue buffer (`rescue_segments`
  invisible table, persist live segments as they arrive), Conversations "recovered" filter,
  finalization parity (5 retries, 2^n·60s, exhaustion→local-segments). Coordinate with settled
  capture-core files (request changes, don't edit `liveRescue.ts`/`liveMicSession.ts`).
- **PR8** — LiveNotes: accumulator (50-word threshold), note generation (Gemini via backend),
  `live_notes` table, LiveNotesView panel + manual notes + edit/delete, crash-recovery load,
  "Quick Note" nav.
- **PR9** — File index fixes: SKIP_DIRS 4→~21 (port Mac list), incremental 3h re-scan
  (`file_index_meta` last_scan), **fix fail-open deletion** (don't purge files under a dir that
  errored on read; reconcile don't wholesale-replace; atomic clear+insert), plus KG
  `terminate()` flush fix.
- **PR10** — KG standalone interactive BrainGraph viewer route + rebuild button (my components/
  graph + new route via Track 5 route manifest); keep inline card non-interactive (Mac-faithful).
  Preserve KG superset.
- **PR11** — Shell: crash/clean-exit detection (`.omi_running`-style flag or app_meta +
  integrity trigger + Sentry report on unclean), launch-at-login default migration (flip default
  ON once, packaged-only, respect later user choice, `app_meta` migrated flag). New
  `main/lifecycle.ts`, minimal `index.ts` wiring.

## Parked (decision gates — do not guess)
- **G-F Updater** — deep updater work parked. Current electron-updater state documented above.
- **G-B Meeting-toast content provider** — coordinate with Track 6 (owns toast shell). Park.
- **PR4 embedding source** — park if no cheap client embed endpoint + local model too heavy.

## Additive schema (PR0 exact)
New tables (also add user-scoped ones to `USER_DATA_TABLES` in dbWipe.ts; app_meta stays OUT):
- `rewind_frames_fts` FTS5(ocr_text, window_title, app) content-linked to rewind_frames(id) +
  INSERT/UPDATE/DELETE triggers. **Populate existing rows via dbMigrations v2** (exactly-once).
- `rewind_frames.ocr_lines_json TEXT` (ensureColumn) — per-line boxes for overlay.
- `rewind_embeddings(frame_id INTEGER PRIMARY KEY, dim INTEGER, model TEXT, vec BLOB, created_at INTEGER)`.
- `local_conversation.starred INTEGER NOT NULL DEFAULT 0`, `local_conversation.folder_id TEXT` (ensureColumn).
- `conversation_folders(id TEXT PRIMARY KEY, name TEXT, color TEXT, icon TEXT, order_idx INTEGER, is_system INTEGER DEFAULT 0, conversation_count INTEGER DEFAULT 0, updated_at INTEGER)`.
- `conversation_speaker_names(conversation_id TEXT, speaker_id INTEGER, name TEXT, person_id TEXT, is_user INTEGER DEFAULT 0, PRIMARY KEY(conversation_id, speaker_id))`.
- `live_notes(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, text TEXT NOT NULL, is_ai INTEGER NOT NULL DEFAULT 0, seg_start INTEGER, seg_end INTEGER, created_at INTEGER NOT NULL)` + idx on session_id.
- `rescue_segments(session_id TEXT NOT NULL, seq INTEGER NOT NULL, segment_json TEXT NOT NULL, ts INTEGER NOT NULL, PRIMARY KEY(session_id, seq))`.
- `file_index_meta(key TEXT PRIMARY KEY, value TEXT)` — scan-state (last_scan_at per root).
- `app_meta(key TEXT PRIMARY KEY, value TEXT)` — app-level flags (clean-exit, launch-at-login migrated). NOT user-scoped; NOT in USER_DATA_TABLES.
Plus preload/types additive IPC surface stubs for the above (flat keys on `omi`, `// --- Track 4 ---`).
</content>
</invoke>
