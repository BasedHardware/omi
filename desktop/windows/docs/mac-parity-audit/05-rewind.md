# Mac→Windows Parity Audit — Rewind (depth delta)

> Re-audited 2026-08-22 against current `main`. Supersedes the 2026-08-20 pass, which had
> gone stale on several major items — in one case (semantic search) describing a gap that had
> already been closed for five weeks. Every claim below was re-verified against current source
> (file/line citations throughout) and against `git log` dates, not carried over from the prior
> file. Scope unchanged: continuous screen recording, OCR, semantic search, timeline UI, action
> items, and transcription integration. Windows baseline checked: `desktop/windows/src/main/rewind/*`,
> `desktop/windows/src/main/ocr/*`, `desktop/windows/src/main/assistants/tasks/*`,
> `desktop/windows/src/main/ipc/{db.ts,dbRecovery.ts,rewind.ts}`, `desktop/windows/src/main/crashSentinel.ts`,
> `desktop/windows/src/renderer/src/{pages/Rewind.tsx,hooks/useRewind.ts,components/rewind/*}`,
> `desktop/windows/src/shared/{rewindExclusions,types}.ts`.

## Changed since the 2026-08-20 audit

The prior file described a Windows Rewind that was largely a dumb screenshot-timeline with a
dead search UI. That was never quite true (`TRACK4-PLAN.md`, ground-truthed 2026-07-14, already
called out the `showSearch` claim as wrong) — and it is now flatly wrong on most of the biggest
items, because a large "Track 4" landing (`feat/win-rewind-shell`, PRs 0–4 in `TRACK4-PLAN.md`)
shipped **2026-07-14 through 2026-07-20**, five to six weeks before the prior audit's stated date.
Everything below shipped and was already in `main` when the 2026-08-20 audit was written; none of
this is new work done since then.

1. **Semantic search is not absent — it's a full hybrid FTS+vector implementation.** The prior
   audit called this "the single largest capability gap in Rewind." It is not a gap:
   `embeddingService.ts`, `embedQueue.ts`, `embedVector.ts`, `embeddingClient.ts`, and
   `vectorSearchMerge.ts` implement Gemini `gemini-embedding-001` embeddings (3072-dim,
   L2-normalized), 100-item/60s batching with content-hash dedup, a launch backfill, and an
   FTS-leads/vector-adds-recall merge at a 0.5 cosine threshold — a close behavioral port of
   Mac's `OCREmbeddingService.swift`. Landed 2026-07-14 (`54d4f36e56`, `a0bc573388`, `a613350996`,
   `45348cb989`), hardened 2026-07-14–2026-07-21 (`c424337117`, `532a64f4c2`).
2. **Search UI reachability was already fixed before the prior audit, contra its own claim.**
   `showSearch` / `pages/Rewind.tsx` in the form the prior audit cited (`useState(false)`, dead
   toggle) no longer exists — that file was rewritten. The current `Rewind.tsx` keeps the search
   field permanently visible in the top bar with Ctrl/Cmd+F focus and Escape to back out
   (`Rewind.tsx:19-176`). `TRACK4-PLAN.md` had already flagged this as a non-task; this audit
   confirms it against current source.
3. **Full-text search is FTS5/BM25, not `LIKE`.** `rewindSearchQuery.ts` builds a BM25-ranked
   `MATCH` expression with camelCase/digit-boundary query expansion; `rewind_frames_fts`
   (`db.ts:518`) is a real FTS5 virtual table with sync triggers. The `LIKE`-based query the prior
   audit cited no longer exists in `rewindSearchQuery.ts`.
4. **OCR bounding boxes now exist and back an on-image highlight overlay.** `rewind_frames.ocr_lines_json`
   (`db.ts:682`) persists per-line boxes from the OCR helper; `rewindOverlay.ts` maps them onto
   the displayed frame and `RewindPlayer.tsx` renders the highlight. The prior audit's "structural
   gap, needs a schema change" framing is now moot — the schema change happened.
5. **Date navigation exists.** `RewindDatePicker.tsx` + a day-scoped `useRewind.ts` (landed
   2026-07-14, `f4f5ded4f3`) replaced the fixed-last-24h window the prior audit described.
6. **Frame dedup now includes the 30s keyframe anchor**, and **battery-aware capture cadence
   (3× multiplier) now exists**, matching the Mac constants documented in `TRACK4-PLAN.md`
   (`captureDecision.ts:13`, `captureDirective.ts:20`). Both were "Absent" in the prior audit.
7. **Database corruption recovery now exists, and exceeds Mac's scope.** `ipc/dbRecovery.ts` is a
   ~1,100-line reactive-detection + staged-copy + table-agnostic salvage implementation, plus
   `crashSentinel.ts` for crash-vs-clean-exit detection across launches. Unlike Mac (which
   salvages only the `screenshots` table), Windows salvages every table with per-row isolation.
   This was "Absent" in the prior audit; it is now arguably ahead of Mac (see the note at the
   bottom of that section).
8. **Action-item extraction from screen now exists as a full pipeline.** `assistants/tasks/`
   (`taskAssistant.ts`, `create.ts`, `loop.ts`, `toolBackends.ts`, `prompt.ts` — landed
   2026-07-15/16) is a faithful port of Mac's `TaskAssistant.swift`: `screenshotId`, `sourceApp`,
   `windowTitle`, `confidence`, `contextSummary`, `currentActivity` all flow from a `RewindFrame`
   through Gemini extraction into a `staged_tasks` promotion pipeline. The prior audit called
   this "zero equivalent hook" at High value — it is now close to full parity, and is arguably the
   single most consequential correction in this rewrite alongside the semantic-search one.
9. **A Windows-specific orphaned-JPEG sweep and rebuild-from-disk path were added** (`orphanSweep.ts`,
   `rebuildIndex.ts`) — not present at all in the prior audit's model of the retention system, and
   not something Mac needs (its capture path doesn't have the write-then-insert race Windows does).
10. **Keyboard navigation is partially present now** (Ctrl/Cmd+F, Escape), not "Absent" — but
    arrow-key frame stepping and scroll-to-scrub, the items the prior audit was actually most
    concerned with, are still genuinely missing. Net: still a real, if narrower, gap.

11 of the old file's 16 graded rows changed status (8 Absent→Present or Present-but-weaker→Present,
1 partial improvement, 1 new Windows-only addition not previously modeled, 1 downgrade-in-scope
correction). Five items were re-verified and found essentially unchanged: frame storage format,
playback controls, screen observations (context tracking), transcription/live-notes integration,
and the "spotted outside scope" callouts (sensitive-title filtering, OCR helper internals).

## Summary table

| Rewind capability | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Frame storage format | `VideoChunkEncoder.swift` | Present-but-weaker (raw per-frame JPEGs, not video) — **unchanged** | H |
| OCR pipeline | `RewindOCRService.swift` | Present-near-parity (external helper binary; bounding boxes now persisted and used) — **improved** | M |
| OCR semantic/embedding search | `OCREmbeddingService.swift` | Present (Gemini hybrid FTS+vector search, 0.5 cosine floor) — **was "Absent," now near-parity** | — |
| Full-text search engine | `RewindDatabase.swift` (FTS5) | Present (FTS5 + BM25 + query expansion) — **was "Present-but-weaker (LIKE)," now near-parity/ahead** | — |
| Search UI reachability | `RewindPage.swift` (always-on unified search bar) | Present (always-visible search bar, Ctrl/Cmd+F, Escape) — **was "Absent," now near-parity** | — |
| Date navigation (browse any day) | `RewindPage.swift` `datePickerControls` | Present (calendar day picker, day-scoped load) — **was "Absent," now near-parity** | — |
| Search-result grouping | `RewindModels.swift` `groupedByContext` | Present-equivalent (`rewindGrouping.ts`), now actually reachable | — |
| Frame dedup + periodic anchor | `RewindOCRService.swift` + `RewindIndexer.swift` | Present (30s keyframe anchor added, matches Mac constant) — **was "Present-but-weaker," now near-parity** | — |
| Battery/power-aware capture cadence | `PowerMonitor.swift` + `VideoChunkEncoder.swift` | Present (3× multiplier + sleep/lock reinit) — **was "Absent," now near-parity** | — |
| OCR bounding boxes / on-image highlight | `RewindOCRService.swift`, `SearchHighlightOverlay` | Present (`ocr_lines_json` + overlay) — **was "Absent," now near-parity** | — |
| Database corruption recovery | `RewindDatabase.swift` (WAL cleanup, backup, `.recover`, rebuild-from-video) | Present, broader scope than Mac — **was "Absent," now ahead in table coverage** | — |
| Orphaned-JPEG FS sweep + rebuild-from-disk | (no Mac equivalent — Windows-only durability need) | Present (`orphanSweep.ts`, `rebuildIndex.ts`) — **new, not modeled in prior audit** | M |
| Playback controls (speed, skip-to-end) | `RewindTimelinePlayerView.swift` | Present-but-weaker (fixed 700ms play, no speed/skip) — **unchanged** | L |
| Keyboard navigation | `RewindPage.swift` (arrows, esc, scroll-to-scrub) | Partially present (Ctrl/Cmd+F, Escape); arrow-step and scroll-to-scrub still absent — **improved but still a real gap** | L-M |
| Action-item extraction from screen | `ActionItemModels.swift` (`screenshotId`, `sourceApp`, agent fields) | Present (`assistants/tasks/*`, staged-task promotion pipeline) — **was "Absent," now the largest single correction alongside semantic search** | — |
| Screen observations (context tracking) | `ObservationRecord.swift` | Still largely absent as a durable per-frame log; `contextSummary`/`currentActivity` now exist but only attached to Memory/Task extraction events, not every analysis pass — **re-verified, essentially unchanged** | M |
| Transcription/live-notes tied to Rewind page | `RewindPage.swift` `expandedTranscriptView` | Absent from the Rewind surface — **re-verified, unchanged** | M |
| Retention cleanup granularity | `RewindIndexer.runCleanup` (chunk-orphan aware) | Present-equivalent, now with an added Windows-specific orphan-file sweep — **improved** | — |

## Screen capture: storage format

**What it is:** How captured frames are persisted to disk.

**Where (Mac):** `Desktop/Sources/Rewind/Core/VideoChunkEncoder.swift`

**How it works:** Mac buffers frames and encodes them into 60-second H.265 (HEVC) video chunks via
`AVAssetWriter`/`VideoToolbox`. Screenshots reference a `videoChunkPath` + `frameOffset` rather than
storing a standalone image.

**Windows status (re-verified, unchanged):** Present-but-weaker. `captureService.ts`
`ingestRewindFrame` (`src/main/rewind/captureService.ts:112-176`) writes each captured frame as an
individual JPEG to `<userData>/rewind/<day>/<ts>.jpg` (`paths.ts:23`). `rewind_frames.image_path`
(`db.ts:498-510`) stores the path directly per row. No video encoding, chunking, or
resolution/bitrate management exists in `rewind/*` today.

**Value / notes:** High, unchanged from the prior audit. This is a real storage-density gap, not
merely a feature gap.

## OCR pipeline

**What it is:** Extracting searchable text (and its position) from each captured frame.

**Where (Mac):** `Desktop/Sources/Rewind/Core/RewindOCRService.swift` — Apple Vision
(`VNRecognizeTextRequest`, `.accurate`, `en-US`), per-block bounding boxes, dHash-based OCR skip,
every-3rd-frame throttle, battery OCR deferral.

**Windows status (materially improved since 2026-08-20):** Present-near-parity. OCR still runs via
an external C# WinRT helper process (`src/main/ocr/`, `helperProcess.ts`), invoked both on the hot
capture path (`captureService.ts` `refreshCurrentScreen`, single-flight) and via a 4s/5-frame
backfill loop for anything the hot path skipped (`ocrService.ts:1-80`). What changed: the helper
now returns per-line boxes (`result.lines`), and `persistFrameOcr` (`ocrPersist.ts:35-43`) writes
them to `rewind_frames.ocr_lines_json` (`db.ts:682`, `ensureColumn`) alongside the flat text — the
prior audit's "no bounding-box column" claim is no longer true. `getRewindFrameOcrLines`
(`db.ts:1547-1556`, exposed via `ipc/rewind.ts:122-124` as `rewind:frameOcrLines`) feeds the
renderer's highlight overlay (see the dedicated section below). `ocrPersist.ts`'s own doc comment
documents a real prior bug it fixes: the two OCR writers (hot path vs backfill) used to diverge on
whether they queued a frame for embedding, so "the great majority of frames were OCR'd and then
never embedded at all" — now both writers funnel through one function.

Mac's dHash-based *OCR* skip (as distinct from the capture-level dedup) and its every-3rd-frame
throttle have no direct Windows analog — Windows instead OCRs nearly every captured frame inline,
which is a *stronger* behavior (fresher OCR, more helper-process load) rather than a gap, and is
explicitly a deliberate Windows deviation per `TRACK4-PLAN.md` item 7 (battery-driven OCR deferral
on Mac is "legacy," not something to port).

**Value / notes:** Medium (down from the prior audit's High) — the structural bounding-box gap
that drove the High rating is closed. What remains is the external-process architecture itself
(not separately audited in depth here, per the prior audit's own scope note, which still holds).

## OCR embeddings + semantic search

**What it is:** Vector-similarity search over screen history in addition to keyword search.

**Where (Mac):** `Desktop/Sources/Rewind/Services/OCREmbeddingService.swift`, `RewindDatabase.swift`.

**Windows status (was "Absent" — this is wrong, and was already wrong on 2026-08-20):** Present.
`embeddingClient.ts` calls Gemini `gemini-embedding-001` via the desktop backend's proxy
(`/v1/proxy/gemini/models/...`), `RETRIEVAL_DOCUMENT` for stored OCR text vs `RETRIEVAL_QUERY` for
a search box (`embeddingClient.ts:1-138`), L2-normalized 3072-float vectors. `embedQueue.ts`
batches at 100 items or 60s, whichever first (`EMBED_BATCH_SIZE=100`, `EMBED_FLUSH_INTERVAL_MS=60_000`,
`embedQueue.ts:25-28`) — 100 is a hard provider ceiling, not a tuning knob, per the file's own
comment — and content-hash dedups via a 5,000-entry LRU (`RecentHashCache`, `embedQueue.ts:55-92`).
`embeddingService.ts` is the impure runner: `enqueueRewindEmbedding` (line 161) is fire-and-forget
from the OCR hot path, a 5s tick flushes due batches (`TICK_MS`, line 32), and a capped
(`BACKFILL_MAX_PER_LAUNCH=5000`, line 35), paced launch backfill sweeps pre-existing frames that have
OCR text but no vector (`runBackfill`, line 334). `vectorSearchMerge.ts` implements the exact Mac
merge contract: FTS leads and keeps its BM25 order unconditionally; a vector hit is appended only if
it clears `VECTOR_SIM_THRESHOLD = 0.5` (line 18) **and** names a frame FTS didn't already return;
vector failure is non-fatal (empty list, keyword-only). `ipc/rewind.ts`'s `rewind:search` handler
(lines 90-113) wires this as a genuine two-phase response: FTS results return synchronously so
keyword search never blocks on the network, and semantic hits are pushed later on
`rewind:search-results` if — and only if — they resolve before a newer query supersedes them
(monotonic `searchSeq`, line 63).

This whole subsystem landed 2026-07-14 (`54d4f36e56` Gemini client, `a613350996` app-context
embedding, `a0bc573388` the hybrid merge, `45348cb989` the backfill indexer) and was hardened
through 2026-07-21 (`532a64f4c2` fixed a real sign-out data leak: the queue could hold ~40 frames of
a signed-out user's OCR text that would otherwise drain under the next user's bearer token; the
current `forgetSession()` — `embeddingService.ts:110-119` — closes that). None of this is new since
the 2026-08-20 audit date; it was five to six weeks old when that audit was written and reachable
end-to-end.

**Value / notes:** This is the single largest correction in this rewrite. The prior audit called
this gap High-value and "the single largest capability gap in Rewind" — it does not exist. What
remains genuinely different from Mac: Windows' embedding source is a backend Gemini proxy (network
round-trip, retried on 429/503) vs Mac's on-device-adjacent call; and Windows adds its own
`MIN_EMBED_TEXT_LEN` floor (10 chars) that Mac doesn't have (documented as a deliberate Windows-only
cost-control addition in `embedQueue.ts:33-40`, not a parity gap).

## Full-text search engine

**What it is:** The keyword-search backend.

**Where (Mac):** `Desktop/Sources/Rewind/Core/RewindDatabase.swift` (FTS5, `unicode61`, BM25).

**Windows status (was "Present-but-weaker (LIKE)" — also wrong on 2026-08-20):** Present.
`rewind_frames_fts` (`db.ts:518-536`) is a real external-content FTS5 virtual table over
`rewind_frames`, kept in sync by `AFTER INSERT/DELETE/UPDATE` triggers. `searchRewindFrames`
(`db.ts:1485-1502`) queries it with `MATCH`, ordered `bm25(rewind_frames_fts) ASC, ts DESC` — BM25
ranking, not a full scan. `rewindSearchQuery.ts` builds the `MATCH` expression: each whitespace
token is split on camelCase and digit/non-digit boundaries (mirroring Mac's `expandSearchQuery`),
every part becomes a quoted, prefix-matched (`*`) FTS5 term, parts OR'd within a token and tokens
AND'd across the query (`buildRewindFtsMatch`, `rewindSearchQuery.ts:107-113`). Windows additionally
hardens Mac's version by quoting every part as a literal FTS5 phrase so user input can never break
`MATCH` syntax (`ftsPrefixTerm`, line 69) — a robustness improvement, not a gap.

**Value / notes:** No longer a gap; if anything the query-expansion + phrase-quoting is slightly
more defensive than what the prior audit described for Mac.

## Search UI reachability

**What it is:** Whether the Rewind search feature can actually be invoked by a user.

**Where (Mac):** `Desktop/Sources/Rewind/UI/RewindPage.swift` — always-visible search field, 300ms
debounce into `performSearch`.

**Windows status (was "Absent, dead-gated" — TRACK4-PLAN.md had already flagged this as wrong
before the prior audit; this rewrite confirms it against current source):** Present. The
`pages/Rewind.tsx` the prior audit cited (with a `showSearch` state stuck at `false`) does not
exist in this form any more — the current file (`Rewind.tsx:19-176`) keeps the search input
permanently in the top bar. Typing debounces 300ms (`SEARCH_DEBOUNCE_MS`, line 14) into
`useRewind().search()`. Ctrl/Cmd+F focuses the field; Escape backs out of a drill-down, then the
results list, then clears the query (lines 62-76) — a closer keyboard-driven match to Mac's
always-on bar than "absent" implies. A search-mode/timeline-mode toggle (`ViewModeToggle`, lines
181-206) and a drill-down mini-timeline per result group (`openGroup`, lines 78-81, using `jumpTo`
to load the hit's day first — a real fix for what would otherwise be an empty-player bug) round out
the UI. `useRewind.ts` backs this with a two-phase result flow matching the IPC handler's
FTS-then-vector split (lines 176-190).

**Value / notes:** Not a gap. Windows Rewind search is reachable today via a persistent search bar,
a keyboard shortcut, and Escape — the opposite of the prior audit's "0% reachable" framing.

## Date navigation

**What it is:** Browsing Rewind history for an arbitrary past day.

**Where (Mac):** `RewindPage.swift` `datePickerControls`.

**Windows status (was "Absent" — now present, landed 2026-07-14):** Present.
`RewindDatePicker.tsx` renders a calendar picker (`Rewind.tsx:116`, `r.selectedDate`/`r.selectDate`).
`useRewind.ts` is day-scoped end to end: `selectedDate` (local-midnight ms) drives `loadDay`
(lines 78-97), which fetches through `rewind:framesSampled` — a day's frames evenly down-sampled to
~500 (`ipc/rewind.ts:72-74`, `listRewindFramesSampled`) — rather than a fixed trailing-24h window.
Only "today" silently auto-refreshes on a 3s cadence (`TODAY_REFRESH_MS`, line 8); past days are
static, matching Mac's model.

**Value / notes:** Not a gap. Landed as part of the same 2026-07-14 Track 4 shell work
(`f4f5ded4f3` "day-scope the timeline with a calendar picker (macOS parity)").

## Frame dedup + periodic anchor frames

**What it is:** Avoiding wasted storage/OCR on unchanged screens, while still keeping the timeline
populated during long static periods.

**Where (Mac):** `RewindOCRService.dHash`/`shouldSkipOCR` + `RewindIndexer.shouldSkipFrameForDedupe`/
`frameDedupeMaxInterval` (30s).

**Windows status (was "Present-but-weaker, no anchor" — now closed):** Present.
`captureDecision.ts` still computes a 16×9 average-hash and skips a frame within
`DUP_HAMMING_THRESHOLD = 4` of the last captured hash (line 5) — but now only *within*
`KEYFRAME_ANCHOR_MS = 30_000` (line 13) of the last **stored** frame's timestamp
(`lastCapturedAtMs`, `captureService.ts:27-29`); past that window a still-identical screen is
force-captured as a periodic anchor (`shouldCaptureFrame`, lines 57-76). This is an exact port of
Mac's `frameDedupeMaxInterval = 30.0` (cited in `TRACK4-PLAN.md` as ground-truthed against
`RewindIndexer.swift:26/165`).

**Value / notes:** Not a gap. A screen that never changes for an hour now gets periodic anchor
frames every 30s on Windows too, closing exactly the timeline-completeness hole the prior audit
described.

## Battery/power-aware capture cadence

**What it is:** Reducing capture frequency (and, on Mac, OCR work) on battery to save power.

**Where (Mac):** `Services/PowerMonitor.swift` + `RewindSettings.effectiveCaptureInterval` (3×
multiplier on battery); `RewindIndexer` skips OCR entirely on battery (documented in
`TRACK4-PLAN.md` as legacy/dead code on Mac — not something to port).

**Windows status (was "Absent" — now closed):** Present. `captureDirective.ts` is a small
pure-reducer + impure-controller pair: `BATTERY_CAPTURE_INTERVAL_MULTIPLIER = 3` (line 20),
`computeCaptureDirective` (lines 66-71) derives `intervalMs = baseIntervalMs * (onBattery ? 3 : 1)`
and a `paused` flag from suspend/lock state, pushed to the renderer over
`rewind:capture-directive`. It also implements the sleep/lock half of Mac's contract that the
prior audit didn't call out separately: `RESUME_SETTLE_MS = 1500` on wake (matching Mac's 1.5s
settle) vs an immediate restart on unlock, and a 1s lock/unlock debounce
(`shouldApplyLockTransition`, lines 86-96) — both bound to `powerMonitor`'s `suspend`/`resume`/
`lock-screen`/`unlock-screen`/`on-battery`/`on-ac` events (`startCaptureDirective`, lines 160-177).
Per `TRACK4-PLAN.md` item 7, Windows deliberately does **not** port Mac's OCR-deferral-on-battery,
since that path is dead on Mac itself.

**Value / notes:** Not a gap. Matches the exact Mac constants documented as ground truth in
`TRACK4-PLAN.md`.

## OCR bounding boxes / on-image highlight

**What it is:** Highlighting exactly where in a screenshot a search match occurred.

**Where (Mac):** `RewindOCRService.swift` (`OCRTextBlock`), `SearchHighlightOverlay`.

**Windows status (was "Absent, structural gap" — now closed):** Present.
`rewind_frames.ocr_lines_json` (`db.ts:682`) persists the OCR helper's per-line boxes, written by
`persistFrameOcr` (`ocrPersist.ts:35-43`) from both the capture-hot-path OCR and the backfill sweep.
`getRewindFrameOcrLines` (`db.ts:1547-1556`) exposes them over IPC (`rewind:frameOcrLines`,
`ipc/rewind.ts:122-124`). On the renderer side, `rewindOverlay.ts` provides the pure geometry:
`containedImageRect` maps an `object-contain`-letterboxed image to its actual pixel rect, and
`normalizedBoxToRect` maps a normalized OCR box onto it; `highlightTerms`/`lineTextMatches` decide
which lines actually match the current query. `RewindPlayer.tsx` consumes all of this (`highlightQuery`
prop, `normalizedBoxToRect` call) to draw the highlight over matching lines.

**Value / notes:** Not a gap. This was called a "structural gap … requires a schema change" in the
prior audit; the schema change (and the renderer consumer) both already existed when that audit
was written.

## Database corruption recovery / crash resilience

**What it is:** Recovering the Rewind (and broader app) index if SQLite is corrupted.

**Where (Mac):** `RewindDatabase.swift` — WAL cleanup, `quick_check`, `.recover`, timestamped
backups, "Rebuild Index" UI action.

**Windows status (was "Absent" — now present, and broader in scope than Mac):** Present.
`crashSentinel.ts` implements clean-exit detection across launches (a synchronously-written sentinel
file, dirty-on-boot/clean-on-`will-quit`, reporting a Sentry message on a detected crash — no
user-visible banner, matching Mac's `lastSessionCleanExit` design intent per the file's own header
comment). `ipc/dbRecovery.ts` (~1,100 lines) is the larger piece: a reactive corruption
classifier (`isCorruptionError`, lines 128-148 — deliberately narrow so a false positive can never
wipe a healthy DB), atomic archive-never-copy-then-delete backup with 5-backup retention
(`archiveCorruptDb`/`pruneBackups`, lines 174-256), and a table-agnostic, per-row-resilient salvage
engine (`salvage`, lines 444-550) that chunks through each table tolerating individual damaged
pages (measured in the file's own comments at 793/800 rows recovered from a table whose full scan
throws). A `db_corruption_suspected` flag (`markCorruptionSuspected`/`isCorruptionSuspected`,
lines 606-612) is tripped by any live query that raises a corrupt error, and the actual repair runs
at the *next* startup — re-verified against a fresh probe first (`salvageIsAnImprovement`, lines
693-700 — a repair is only ever installed if it recovers at least as many rows as the app can
currently read), capped at `MAX_REPAIR_ATTEMPTS = 3` to avoid a boot loop. `rebuildIndex.ts`
(`rebuildRewindIndexFromDisk`, lines 114-120, surfaced as `rewind:rebuildIndex` — `ipc/rewind.ts:147`
— from a `DbRecoveryNotice` UI component) is the Windows analog of Mac's "Rebuild Index": after a
whole-DB reset, it re-inserts `rewind_frames` rows for JPEGs still on disk (`indexed=0`, so the
existing OCR backfill re-OCRs them).

Landed 2026-07-14 (`d48912e4e7` classifier, `f650deaff7` startup recovery + user notice,
`c8b02c65a9` the runtime trip) through 2026-07-15 (`424589dc56` clean-exit sentinel,
`dd3569cc80` rebuild-from-disk).

**Value / notes:** Not a gap — and worth flagging the other direction, as the prior audit's
"spotted outside my scope" section did for sensitive-title filtering: Windows' salvage covers
*every* table with per-table/per-row isolation, where Mac's `.recover`-based approach (per the prior
audit's own description) salvages only the `screenshots` table and discards everything else on
recovery. If a Windows→Mac direction of this audit exists, this is worth surfacing there.

## Orphaned-JPEG FS sweep (Windows-only addition, not modeled in the prior audit)

**What it is:** Windows' capture path writes a JPEG (`writeFileSync`) and *then* inserts its DB row
(`insertRewindFrame`) — two steps, not atomic. A crash between them orphans the file forever: no row
ever references it, so retention (row-driven) never deletes it. Mac has no equivalent because its
capture is in-process and single-writer.

**Windows status:** Present. `orphanSweep.ts` runs a bounded sweep (60s after startup, then every
6h — `SWEEP_STARTUP_DELAY_MS`/`SWEEP_INTERVAL_MS`, lines 26-28) that finds `<ts>.jpg` files with no
matching `rewind_frames` row and deletes only the ones older than a 60s grace window
(`ORPHAN_GRACE_MS`, `orphanSelection.ts:9`) so an in-flight insert is never raced. The keep-set
window is derived from actual file timestamps (padded a day each side), not the day-dir's
local-midnight name, specifically to survive a DST/TZ offset change between capture and sweep
without false-deleting a still-valid file (`deriveKeepSetWindow`, `orphanSelection.ts:22-39`).

**Value / notes:** Medium. Not a parity item (Mac doesn't need this), but a real Windows-specific
durability fix the prior audit's model of the retention system didn't account for.

## Playback controls

**What it is:** Auto-playing through captured frames like a video scrubber.

**Where (Mac):** `RewindTimelinePlayerView.swift` — play/pause, prev/next, skip-to-start/end,
0.5×–8× speed.

**Windows status (re-verified, unchanged):** Present-but-weaker. `Rewind.tsx` still has a single
Play/Pause toggle (line 117-126); `useRewind.ts`'s playback effect (lines 161-174) still advances
the cursor on a fixed 700ms interval with no speed control and no skip/step buttons.

**Value / notes:** Low, unchanged.

## Keyboard navigation

**What it is:** Arrow-key frame stepping, Escape, scroll-wheel scrubbing.

**Where (Mac):** `RewindPage.swift` — arrow keys, Escape, a global scroll-wheel monitor that moves
the playhead.

**Windows status (partially improved, but the core gap remains):** `Rewind.tsx` now handles
Ctrl/Cmd+F (focus search) and Escape (back out of search/drill-down — lines 62-76), which the prior
audit's "no `onKeyDown` handling found" claim missed even at the time (that handler predates the
2026-08-20 audit date; it shipped with the same 2026-07-14 search work). What is genuinely still
absent: arrow-key frame stepping, and scroll-to-scrub. `RewindTimelineBar.tsx`'s wheel handler
(lines 137-139) still only translates vertical wheel into horizontal *pan* (`scrollLeft`), not
playhead movement — confirmed unchanged from the prior audit's description.

**Value / notes:** Low-to-Medium (split from the prior audit's flat "Low-medium, Absent" — the
part that shipped is a minor convenience; the part that's still missing, direct playhead
scrubbing, is the more useful half for a power user reviewing history).

## Action-item extraction from screen

**What it is:** Automatically detecting tasks/to-dos visible in screen content and turning them
into tracked action items.

**Where (Mac):** `Core/ActionItemModels.swift` (`ActionItemRecord` — `screenshotId`, `sourceApp`,
`windowTitle`, `confidence`, `contextSummary`, `currentActivity`, a `staged_tasks` promotion
pipeline).

**Windows status (was "Absent, zero equivalent hook" — this is the second-largest correction in
this rewrite):** Present. `assistants/tasks/` is a full port, landed 2026-07-15/16:

- `taskAssistant.ts` (`TaskAssistant` class, line 82) is a coordinator peer alongside Focus,
  Insight, and Memory. It triggers on a context switch (the departing frame, primary trigger —
  fire-and-forget, re-entrancy-locked against the coordinator's own cadence path), a fallback tick
  (`taskFallbackIntervalMin`, Mac default 600s), and a 15s messaging fast-path
  (`MESSAGING_INTERVAL_MS`, line 39) — mirroring Mac's trigger set per the file's own header.
- `loop.ts` runs the single-phase multi-tool Gemini extraction loop against the frame image;
  `models.ts` parses `extract_task` tool-call args 1:1 from Mac's schema.
- `create.ts` `createStagedTaskFromExtraction` (lines 234-278) gates on confidence
  (`DEFAULT_MIN_CONFIDENCE = 0.75`, matching Mac's `TaskAssistantSettings.defaultMinConfidence`),
  then writes a local `staged_tasks` row carrying `screenshotId: frame.id`, `sourceApp`,
  `windowTitle`, `contextSummary`, `currentActivity` (lines 251-264) — the same field set the prior
  audit cited as missing on Windows — before `POST /v1/staged-tasks`, embedding the title
  (`taskEmbeddingService.ts`), and running `promoteIfNeeded` (a 30s debounce,
  `PROMOTION_DEBOUNCE_MS`, matching Mac's `promotionDebounceInterval`).
- `toolBackends.ts` implements the `search_similar` (vector) and `search_keywords` tool backends
  the extraction loop can call mid-analysis, per `TaskAssistant.swift:1450-1560`.

**Value / notes:** Not a gap in the sense the prior audit meant it (no hook at all). What remains
different from Mac: Windows drops Mac's `candidate_outbox` staging concept (`source: 'screenshot'`
goes straight to the local row and the POST body — a documented, deliberate simplification, not an
oversight, per `create.ts`'s header comment "D6: Windows drops Mac's `candidate_outbox`").

## Screen observations (context tracking)

**What it is:** A background record of *every* screen analysis pass (not just ones that found a
task or memory), used for chat context / activity summaries.

**Where (Mac):** `Core/ObservationRecord.swift` (`observations` table: `appName`, `contextSummary`,
`currentActivity`, `hasTask`, `sourceCategory`/`sourceSubcategory`).

**Windows status (re-verified, essentially unchanged):** Still no `observations`-equivalent table
exists in `db.ts` or anywhere in `rewind/*` — confirmed by grep across `src/main`. What has changed
since the prior audit's framing: `contextSummary`/`currentActivity` are now real fields threaded
through both the Memory assistant (`assistants/memory/models.ts:24-25`) and the Task assistant
(`assistants/insight/models.ts:34-35`, `assistants/tasks/create.ts`) — but they are attached only to
the *outcome* of an extraction pass (a saved memory, a staged task), not persisted as a row for
every pass regardless of outcome. Windows' closest analog to a continuous log is still the
single-slot `currentScreen.ts` cache the prior audit identified (most-recent-frame OCR text only,
used for chat's "what's on my screen right now").

**Value / notes:** Medium, unchanged. This is one of the few items from the prior audit that holds
up essentially as written.

## Transcription/live-notes tied to the Rewind page

**What it is:** Rewind's page hosts the live meeting transcript + AI notes panel inline.

**Where (Mac):** `RewindPage.swift` `expandedTranscriptView`.

**Windows status (re-verified, unchanged):** Absent from the Rewind surface. The current
`Rewind.tsx` (read in full for this rewrite) has no transcript/notes panel, recording bar, or
"Finish Conversation" action — confirming the prior audit's finding still holds. (`TRACK4-PLAN.md`'s
PR8 scopes a `LiveNotesView`/`live_notes` table as future work, not yet landed in `rewind/*` or
wired into the Rewind page as of this audit.)

**Value / notes:** Medium, unchanged — a product-integration gap, since transcription itself likely
exists elsewhere on Windows (not investigated here, same as the prior audit's scope note).

## Search-result grouping (parity)

**What it is:** Clustering consecutive same-app/same-window frames within a time window into one
result.

**Where (Mac):** `RewindModels.swift` `Array<Screenshot>.groupedByContext(timeWindowSeconds: 30)`.

**Windows status:** Present-equivalent, unchanged in algorithm (`rewindGrouping.ts`, 30s window,
same-app/same-window-title clustering) — but the prior audit noted this piece was "currently
unreachable anyway." That caveat no longer applies: search is fully reachable (see above), so this
grouping is now live and user-facing, not just parity-on-paper.

**Value / notes:** Parity, and now actually exercised end-to-end.

## Retention cleanup granularity

**What it is:** Deleting old frames/files once they age past the retention window.

**Where (Mac):** `RewindIndexer.runCleanup` — chunk-orphan aware (removes orphaned video chunks
reactively on last-row-delete).

**Windows status (re-verified, improved):** Present-equivalent, still simpler than Mac's model
because there's no video-chunk concept to orphan — `retentionRunner.ts` deletes rows past
`retentionDays` (default 14, hourly + on-launch) and their JPEGs. New since the prior audit's
framing: the orphaned-JPEG sweep (`orphanSweep.ts`, see its own section above) now also catches the
Windows-specific write-then-insert race, which the "correct for JPEG-per-frame model" note in the
prior audit didn't account for — that race was a real, if narrow, disk-growth gap that has now been
closed with a Windows-only mechanism.

**Value / notes:** Parity for the retention model Windows actually needs; the added sweep closes a
real gap the prior audit didn't know to look for.

## Spotted outside scope

- General (non-Rewind) SQLite corruption/backup handling in `db.ts`/`dbRecovery.ts` now covers far
  more than Rewind (every table) — flagged above as worth surfacing to a Windows→Mac direction of
  this audit, same as the prior file flagged sensitive-title filtering.
- `SENSITIVE_WINDOW_MARKERS`-based login/private-window title filtering
  (`shared/rewindExclusions.ts:41`) still exists and still has no confirmed Mac equivalent — the
  prior audit's callout re-verified as still accurate.
- `desktop/windows/src/main/ocr/win-ocr-helper/Program.cs` internals were not read in depth here
  either — only confirmed (again) that per-line box output now reaches the DB schema, which it did
  not when the prior audit was written (or, per this rewrite's investigation, well before that —
  the prior audit simply hadn't checked).
- Whether Windows has a transcription/meeting-notes feature *elsewhere* in the app was not
  investigated — same scope boundary as the prior audit.
- `assistants/memory/`, `assistants/insight/`, and the wider `agentKernel/` coordinator were only
  read as far as needed to confirm/refute the `ObservationRecord` and action-item claims above; a
  full audit of those assistants is out of scope for this Rewind-focused pass.
