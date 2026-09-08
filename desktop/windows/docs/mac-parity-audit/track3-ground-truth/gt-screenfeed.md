# Track 3 ground truth: existing screen-capture / window-title / insight feed (Windows)

Scope: what Track 4 (Rewind) already exposes that Track 3 (Focus/Memory/Insight
proactive assistants) could subscribe to, without owning or editing Track 4's files.
All paths relative to `desktop/windows/`.

## 1. Screen-capture pipeline

Capture *acquisition* lives in the **renderer**, not main — deliberate, to avoid
Electron's `desktopCapturer` full-res thumbnail path, which froze the system when
polled (see comment at `src/main/rewind/captureService.ts:70-76`).

- `src/renderer/src/components/rewind/RewindCaptureHost.tsx` — mounted app-wide.
  Opens one persistent `getUserMedia({ video: { chromeMediaSource: 'desktop', ... }})`
  stream (720p, **maxFrameRate: 1**) into a hidden `<video>`, then on a **self-pacing
  `setTimeout` loop** (default `intervalMs = 1000`, i.e. **1s**, configurable in Rewind
  settings — not Mac's 3s/×3-on-battery) draws the frame to a canvas, JPEG-encodes it
  (`quality 0.6`, longest edge capped at 1600px, line 6-7), and calls
  `window.omi.rewindSaveFrame(new Uint8Array(...))` (line 70).
- IPC: `rewind:saveFrame` handler in `src/main/ipc/rewind.ts:55-57` → calls
  `ingestRewindFrame(Buffer.from(data))` in `src/main/rewind/captureService.ts:78`.
- `ingestRewindFrame` (captureService.ts:78-160):
  1. Reads foreground app/title/processName (see §2).
  2. Decodes the JPEG via `nativeImage`, computes a 16×9 average-hash, and runs
     `shouldCaptureFrame()` (`captureDecision.ts`) — gates on locked/idle
     (60s)/excluded-app/duplicate-hash. Returns `{captured:false, reason}` if skipped.
  3. If captured: writes the **raw JPEG bytes** to disk at
     `rewindFramePath(ts)` = `<userData>/rewind/<YYYY-MM-DD>/<ts>.jpg`
     (`src/main/rewind/paths.ts:22-24`), then `insertRewindFrame()` into SQLite.
  4. Fires-and-forgets (not awaited) `refreshCurrentScreen(id, jpeg)` (line 154) which
     OCRs the same JPEG via the helper process and updates the in-memory
     "current screen" text cache (§3) — this is the only place OCR happens synchronously
     with capture; a **separate backfill timer** (`ocrService.ts`, every 4s, batches of 5)
     mops up any frame that arrives un-OCR'd.

**Format:** raw JPEG `Buffer` end-to-end inside the main process (never base64 until
served to a renderer for display). Base64 only appears at `rewind:frameImage` in
`src/main/ipc/rewind.ts:28-36` (`data:image/jpeg;base64,...`, for the Rewind timeline UI).

**Cadence:** 1 frame/sec sampled (renderer timer), but many are *dropped* before
persistence by `shouldCaptureFrame()` (idle/lock/dup-hash/excluded-app gates) — so
persisted-frame cadence is variable, not fixed.

**Persistence:** yes, on every frame that passes the gates — SQLite table
`rewind_frames` (schema in `src/main/ipc/db.ts:161-174`: `id, ts, app, window_title,
process_name, ocr_text, image_path, width, height, indexed`) plus the JPEG file on disk
at `image_path`. Read helpers: `listRewindFrames(from,to)`, `latestRewindFrame()`,
`unindexedRewindFrames(limit)`, `setRewindFrameOcr(id,text)` — all in
`src/main/ipc/db.ts:814-869`.

## 2. Active-window / foreground-app + title source

`src/main/usage/nativeForeground.ts` — koffi bindings over `user32.dll`/`kernel32.dll`
(no C# helper needed for this part):
- `getForegroundExePath()` — `GetForegroundWindow` + `GetWindowThreadProcessId` +
  `OpenProcess`/`QueryFullProcessImageNameW` → absolute exe path.
- `getForegroundWindowTitle()` — `GetWindowTextW` → window title string.
- `getForegroundWindowInfo()` — HWND + exePath + window class in one call.
- `getForegroundWindowRect()` — physical-px rect + class + exe (used by the bar's
  fullscreen-suppression logic).
- **`subscribeForegroundChange(cb)`** (line 283-291) — event-driven via
  `SetWinEventHook(EVENT_SYSTEM_FOREGROUND, ...)`, filtered to `OBJID_WINDOW`/`idChild===0`
  top-level changes. Returns an unsubscribe function. **This already exists and is
  exactly the "context-switch detection" primitive Track 3 needs** — it is not
  currently consumed by captureService (which just polls foreground synchronously
  per captured frame) but is a real, working, already-built API any new main-process
  module can call directly.

In `captureService.ts:86-113`, the actual per-frame app/title resolution order is:
1. Try the C# OCR helper's `windowInfo()` (`helperProcess.windowInfo()`) — richer
   "friendly app name" (e.g. "Google Chrome") — but the helper is often not running
   (comment: "OCR is shelved").
2. Fallback: `getForegroundExePath()` → derive a display name from the exe basename.
3. Title fallback: `getForegroundWindowTitle()` if the helper gave nothing.

So today's *effective* primary source for app+title is the koffi/user32 functions in
`nativeForeground.ts`, with the C# helper as an occasionally-available enrichment.
This is the same source `app_usage` tracking uses elsewhere in the codebase.

The app-exclusion list is `src/shared/rewindExclusions.ts` (`BUILT_IN_EXCLUDED_APPS`)
merged with user-configured `RewindSettings.excludedApps`, both consumed inside
`shouldCaptureFrame()` — reusable as-is for a Track 3 exclusion list.

## 3. Existing insight assistant's screen-context path (closest analog)

**Important finding: `src/main/insight/**` (`notification.ts`, `state.ts`,
`toastWindow.ts`) is DISPLAY-ONLY** — native notification / acrylic toast rendering
and settings persistence. It does not touch screen data at all.

The actual trigger→data→LLM engine lives in the **renderer**, not main:
`src/renderer/src/lib/insightEngine.ts`. Full path:

1. `maybeStartInsightEngine()` (line 81-94) — idempotent, self-rescheduling
   `setTimeout` loop. First run ~60s after launch, then reschedules using the
   **user's configured `intervalMin`** read fresh each cycle (default 15 min; Settings
   offers 15/20/30/60) — no fixed interval hardcoded, unlike Mac's fixed capture timer.
2. `runInsightOnce()` (line 28-74):
   - Checks `insightGetSettings().enabled` and `rewindGetSettings().captureEnabled`
     (no-op if either is off — insight literally cannot run without Rewind capturing).
   - Pulls **`window.omi.rewindFrames(now - 1hr, now)`** — i.e. an IPC call to
     `rewind:frames` (`src/main/ipc/rewind.ts:21`) → `listRewindFrames(from,to)` — a
     **DB poll over the last hour of already-persisted frames**, each carrying
     `app`, `windowTitle`, `ocrText` (text only — **no JPEG/image data is ever sent
     to the LLM**).
   - Filters out private/denied windows (`screenRedact.ts`), then
     `summarizeActivity()` (`insightActivity.ts`) groups consecutive frames by
     app+title and concatenates distinct OCR lines into a capped-length plain-text
     summary (12,000 char budget).
   - Builds a **text-only** prompt (`buildInsightPrompt`, includes recent headlines
     to avoid repeats) and calls `generate()` (`geminiClient.ts`, Gemini 2.5 Flash)
     — no vision call, no image input.
   - `selectInsight()` (`insightGate.ts`) applies a confidence threshold (0.85) +
     dedup against recent headlines.
   - On success: `insightAdd()` (persists to `insights` SQLite table) +
     `insightShow()` (IPC to main → `deliverInsight()` in `src/main/ipc/insight.ts:16`
     → toast or native notification).

**Conclusion: the existing "insight" assistant is a periodic TEXT summarizer over
OCR'd Rewind history, not a live per-frame vision analyzer.** It is not wired to
receive individual freshly-captured frames or raw JPEGs at all — it batches an hour
of history once per `intervalMin`. This is a weaker analog for Track 3's stated need
("periodically analyze a SCREEN FRAME (JPEG/base64) with app/window title") than the
brief assumed; Track 3 will need to either (a) build its own per-frame subscription
(see §5) or (b) adapt this batched-OCR-summary pattern instead of true per-frame vision.

## 4. OCR text feed

`src/main/ocr/helperProcess.ts` — a supervised, long-running C# helper subprocess
(`win-ocr-helper`, source in `src/main/ocr/win-ocr-helper/`), single-flight FIFO
request queue, 5s per-request timeout, capped-backoff auto-restart on crash.
Exposes (via `helperProcess.ocr(jpegBuffer): Promise<OcrResult>` and
`helperProcess.windowInfo(): Promise<WindowInfo>`) an OCR-on-demand API — you hand it
a JPEG buffer, it returns `{ok, fullText}`. It is **not** a push feed; it's a
request/response call any main-process code can make directly (same call
`captureService.ts` and `ocrService.ts` already use). Two things key OCR to "the
latest frame" today:
- `currentScreen.ts` — an in-memory `{text, ts}` singleton, refreshed by
  `captureService.ts`'s `refreshCurrentScreen()` on every newly-ingested frame
  (single-flight-guarded so OCR never stacks). `getCurrentScreen()` /
  `screenCacheFresh(now)` (30s freshness window) are the read API — this is what
  chat's "read the screen" feature uses for a zero-latency answer
  (`src/main/ipc/screen.ts:38-75`).
- The `ocr_text` column on each `rewind_frames` row (backfilled async by
  `ocrService.ts`'s 4s-interval batch-of-5 loop for any frame OCR didn't reach yet).

Both are read-only for a consumer: `getCurrentScreen()` (import from
`../rewind/currentScreen`) or a `listRewindFrames`/`latestRewindFrame` DB read.

## 5. IPC/event pattern for "new frame captured" — DOES ONE EXIST?

**No.** Checked explicitly (grepped `EventEmitter`, `emit(`, `webContents.send('rewind`,
`newFrame`, `frame-captured` across `src/main/`) — the only `rewind:*` broadcast to
renderers is `rewind:settings` (a settings-change push, `rewind.ts:44`), not a
frame-availability event. `ingestRewindFrame()` returns `{captured, reason}` to its
IPC caller (the renderer capture host) and does nothing else — no in-process
`EventEmitter`, no `webContents.send` fan-out, no pub/sub of any kind after a frame is
persisted. The existing insight engine avoids needing one by polling the DB on its
own multi-minute timer instead of subscribing to individual frames.

## Verdict: clean subscription seam EXISTS for polling; NONE exists for push-per-frame

**Read-only polling seam already works today, without touching Track 4 files:**
a new Track 3 main-process module can call `getCurrentScreen()`
(`src/main/rewind/currentScreen.ts`, exported, no changes needed) for the hot ~1s-fresh
OCR text, or `listRewindFrames`/`latestRewindFrame` (`src/main/ipc/db.ts`, exported) for
JPEG path + app/title/ocrText history, entirely by importing existing modules — this
requires zero edits to any `rewind/**` or `ocr/**` file.

**A true "new frame + window title" push subscription does NOT exist** and would
require either:
- **(a) Track 3 polls instead of subscribes** — cheapest, zero Track-4 changes: a
  `setInterval` (e.g. every 3-5s to match Track 3's own cadence) that calls
  `latestRewindFrame()` and diffs `id`/`ts` against the last-seen frame, then
  `readFileSync(frame.imagePath)` for the JPEG bytes + `frame.app`/`frame.windowTitle`.
  Example:
  ```ts
  // src/main/proactive/frameFeed.ts (NEW file — no Track 4 files touched)
  import { latestRewindFrame } from '../ipc/db'
  import { readFileSync } from 'fs'

  let lastSeenId: number | null = null

  export function pollForNewFrame(): { jpeg: Buffer; app: string; windowTitle: string } | null {
    const f = latestRewindFrame()
    if (!f || f.id == null || f.id === lastSeenId) return null
    lastSeenId = f.id
    return { jpeg: readFileSync(f.imagePath), app: f.app, windowTitle: f.windowTitle }
  }
  ```
  Caveat: this only sees frames that passed `shouldCaptureFrame()`'s dedup/idle
  gates — during a static screen (no visual change) `latestRewindFrame()` can go
  stale for the full idle/dup window, same limitation the existing insight engine has.

- **(b) Track 4 publishes an event** (if Track 3 needs true "every capture, including
  gated-out attempts" or lower latency than DB-poll) — minimal ask: one line in
  `ingestRewindFrame()` (captureService.ts:78) after the `insertRewindFrame()` call,
  e.g. `rewindEvents.emit('frame', { id, ts, app: win.app, windowTitle: win.title, jpeg })`
  where `rewindEvents` is a small new `EventEmitter` Track 4 exports from
  `src/main/rewind/events.ts`. This is a Track-4-owned file change, not something
  Track 3 can do unilaterally without editing rewind/** — flag to Track 4 if (a)'s
  polling latency (matches capture interval, ~1s, but gated frames can be stale up
  to 60s on idle) is insufficient for Track 3's UX.

**Recommendation:** start with (a) — it needs no coordination with Track 4 and no
edits to any `rewind/**`/`ocr/**` file, satisfying the "without owning Track 4's
files" constraint directly. Only escalate to (b) if Track 3's design requires
sub-second latency or visibility into gated (idle/dup/excluded) frames that (a)
cannot see.
