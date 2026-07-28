# Ground Truth: Windows-side seams for the proactive assistant port

Extracted 2026-07-14 from the live Windows source (`desktop/windows/src/**`) + the Rust desktop
backend. These are the facts the Track-3 coordinator / Focus assistant build on. Verified by
three independent extractors; cite these rather than re-deriving.

---

## DECISION: assistants are hosted in **MAIN**, not the renderer

Earlier working assumption was renderer-hosted (because "only the renderer holds the Firebase
token"). **That constraint is dead** — P1 proved main can hold a relayed session
(`configureAiProfileSession` → `net.fetch` with `Authorization: Bearer <token>`). Everything
else Focus needs is natively in main:

| Need | Main | Renderer |
|---|---|---|
| Foreground app + window title | native (`nativeForeground.ts`), and also stored on every frame row | needs a new IPC broadcast (none exists) |
| Screen frames | `latestRewindFrame()` in-process; JPEG readable off disk | poll `rewindFrames` over IPC, base64 per frame |
| `focus_sessions` writes | direct `db.ts` call | IPC round-trip |
| Glow windows | owns `BrowserWindow` | IPC anyway |
| Gemini call | `net.fetch` + relayed session | `geminiClient.generate()` |

Main-hosted is also the **faithful** port — Mac runs these assistants in-process.

**Accepted risk:** main's cached token goes stale if the renderer dies (`onIdTokenChanged` is
what refreshes it). Mitigated: the app already depends on a live renderer for proactive work
(`insightEngine` runs there), and main must treat a 401 as "request a fresh session", not as a
silent degrade.

**Consequence:** the per-assistant session cache in `aiUserProfile/service.ts` gets generalized
into ONE shared `main/assistants/core/session.ts` that every main-side assistant reads. One
renderer relay, many assistants.

---

## 1. Screen capture (Track 4's — DO NOT EDIT `src/main/rewind/**`)

- **Acquisition is in a hidden renderer window** (`#/capture`, `RewindCaptureHost.tsx`): one
  persistent `getUserMedia` desktop stream → canvas → JPEG → `rewind:saveFrame` → main.
- **Main persists every frame** via `ingestRewindFrame` (`captureService.ts:80-162`): it resolves
  the foreground app/title itself and writes the row + JPEG to disk.
- **Cadence: flat `intervalMs`, default 1000ms**, user-selectable 1s/2s/5s/10s
  (`rewindSettings.ts:11-16`). **There is NO battery/power multiplier on Windows** — a full grep
  found none. Mac's "3.0s base × 3.0 on battery" has no Windows equivalent.
- **There is NO frame-captured push signal.** No event, no emitter, no IPC broadcast. The only
  `webContents.send` in the Rewind path is the settings broadcast.

### How the coordinator consumes frames (no Track-4 edits)
`latestRewindFrame(): RewindFrame | null` — `db.ts:1038-1043`, **main-process only, no IPC**.
Poll it on the coordinator's own tick. The row already carries the context signal:

```ts
RewindFrame = {
  id?: number; ts: number            // epoch ms
  app: string                        // "Google Chrome" (friendly name)
  windowTitle: string                // may be ''
  processName: string                // "chrome"
  ocrText: string                    // '' AT INSERT — filled async by the 4s backfiller
  imagePath: string                  // absolute JPEG path under rewindRoot()
  width: number; height: number; indexed: number  // 0 = not yet OCR'd
}
```
Read the JPEG straight off `imagePath` with `fs` — do NOT round-trip through
`rewind:frameImage` (that IPC exists for the renderer and returns a `data:image/jpeg;base64,…`
string; main has no reason to pay for it).

⚠️ `ocrText` is **empty at insert time**. A coordinator polling immediately after capture will
often see `ocrText: ''` / `indexed: 0`. Focus judges the *image*, so this is fine — but don't
build anything that assumes OCR text is present on a fresh frame.

### Capture-time gating already applied (frames you see are pre-filtered)
`captureDecision.ts:45-59` `shouldCaptureFrame()` already drops: lock-screen, busy, idle
(≥60s), excluded apps (built-in ∪ user list), **sensitive window titles**
(`src/shared/rewindExclusions.ts`), and near-duplicates (16×9 average-hash, Hamming ≤ 4).

### Additional privacy filter the coordinator MUST still apply
The renderer's `insightEngine` applies a *second* filter that capture does not:
`isPrivateWindow(windowTitle)` (incognito/private browsing) and `isDeniedContext({app,
windowTitle, processName})` (password managers, banks, login/sign-in pages) —
`renderer/src/lib/screenRedact.ts:2-22`. **Focus sends a full screenshot to a cloud model, so
this filter is more important for Focus than it is for Insight.** These predicates are pure;
lift them to `src/shared/` so main can import them (have `screenRedact.ts` re-export, so
existing callers and tests are unchanged).

---

## 2. Gemini vision — fully unblocked, zero new transport code

- The proxy is on the **Rust desktop backend** (`VITE_OMI_DESKTOP_API_BASE`), NOT the Python
  backend (grep of `backend/` for `proxy/gemini` → zero hits).
- Route: `POST /v1/proxy/gemini/models/{model}:generateContent`
  (`desktop/macos/Backend-Rust/src/routes/proxy.rs:1085`).
- Auth: Firebase Bearer token + paywall check (`PaywalledAuthUser`). The server holds the
  Gemini key; no key ever on device.
- Guards: action allowlist (`generateContent` ✓), model allowlist (**`gemini-2.5-flash` ✓**,
  `gemini-2.5-pro` ✓), **5 MB body limit** whose source comment reads *"Normal app payloads are
  300-600 KB (base64 JPEG + prompt)"* — the image path is the designed use. `thinkingBudget`
  defaults to 1024 if absent (Mac's Focus sets it to 0).
- **✅ NO `X-App-Platform` handling anywhere in the Rust backend** (grep: zero matches). It does
  not branch on, gate, or reject platform `windows`. The prior "backend doesn't recognize
  platform 'windows'" bug was the *Python* backend's plan catalog and **does not apply here**.

**A Gemini client already exists on Windows** — `renderer/src/lib/geminiClient.ts` — hitting that
exact URL, and its `GeminiPart` type **already includes `inlineData: { mimeType, data }`**. But
**no image has ever been sent**: both callers (`screenSynthesis.ts`, `insightEngine.ts`) pass
text-only parts. Focus would be the first vision call.

Main-side Focus should mirror `aiUserProfile/service.ts`'s pattern:
```ts
await net.fetch(`${session.desktopApiBase}/v1/proxy/gemini/models/gemini-2.5-flash:generateContent`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${session.token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ contents: [{ role: 'user', parts: [{ text }, { inlineData: { mimeType: 'image/jpeg', data: b64 } }] }],
                         systemInstruction, generationConfig: { responseMimeType, responseSchema, thinkingConfig } }),
  signal
})
```
(Mac labels the image `image/webp` regardless of actual encoding — that's a Mac bug, not a
contract. Send the true `image/jpeg`.)

---

## 3. Foreground window (`src/main/usage/nativeForeground.ts` — Track 3 owns this)

- `subscribeForegroundChange(cb: () => void): () => void` — `:283-291`. SetWinEventHook
  (`EVENT_SYSTEM_FOREGROUND`). Callback takes **no args** ("something changed, go read it").
  Never throws. Three modules already subscribe independently; more is fine.
- `ForegroundWindowInfo` (`:13-19`) has only **`handle` / `exePath` / `className`** — **no window
  title, no app display name, no pid.** Title is a separate call: `getForegroundWindowTitle()`
  (`:253-261`).
- `getForegroundWindowRect()` (`:265-277`) → `{ rect, className, exePath }`, **rect in PHYSICAL
  pixels** — must be converted to DIPs (`screen.screenToDipRect`) before `setBounds`.
- **Nothing broadcasts foreground changes to the renderer today** (grep of `src/preload/` for
  `foreground` → zero matches). Irrelevant now that assistants live in main.

---

## 4. Notification throttle — **does not exist on Windows. Build it.**

Grep for `throttle|snooze|frequency|quietHours|cooldown|lastNotifiedAt` across `src/` found **no
notification-throttle module**. Mac's shared `NotificationService` model has zero Windows
counterpart:
- frequency levels 0–5 → `[∞(off), 60m, 30m, 10m, 3m, no-throttle]`, **default 0 = Off**
- a **global** clock AND a **per-assistant** clock — both gate, both update on allow (shared
  budget, so a chatty assistant can't starve another)
- suppression order: dedup → **snooze** (never bypassable) → **master toggle** → **frequency**

What Windows has instead is ad-hoc per-feature gating. Existing emitters to route through the
new throttle later: `deliverInsight()` (`main/ipc/insight.ts:30`) and `showMeetingToast()`.
Settings pattern to copy: `main/insight/state.ts` (file-backed JSON in `userData/insights.json`,
cached).

---

## 5. Glow overlay — use the BAR window template, not the toast

- ❌ `main/insight/toastWindow.ts` is the WRONG template: it is deliberately **`focusable: true`**
  (or Chromium won't route mouse input to it) and **`transparent: false`** (uses DWM
  acrylic/mica backdrop). Both are wrong for a click-through glow.
- ✅ `main/bar/window.ts:178-207` is the right one: `transparent: true`, `frame: false`,
  `focusable: false`, `hasShadow: false`, `skipTaskbar: true`,
  `setAlwaysOnTop(true, 'screen-saver')`, `setIgnoreMouseEvents(true, { forward: true })`.
- Worth stealing from the toast anyway: lazy-singleton window, `showInactive()` (never `show()`,
  so it can't steal focus), armed-dismiss timer, and **pull-on-mount** for the payload (a push
  between `did-finish-load` and React's effect subscription silently vanishes — the toast solves
  this with `getCurrentMeetingToast()`-style handlers).
- Toast positions only on `screen.getPrimaryDisplay()` — no multi-monitor logic. The glow must do
  better: position from the *target window's* rect.

---

## 6. Renderer proactive bootstrap

`maybeStartInsightEngine()` — `renderer/src/lib/insightEngine.ts:81-94`. Idempotent via a
module-scope `started` flag set **synchronously before any await** (so React StrictMode
double-mount can't start two loops). Called from `pages/Home.tsx:254` in a `useEffect(…, [])`,
alongside `maybeStartScreenSynthesis()` and `maybeStartRetentionSweep()`. This is the seam the
renderer-side session relay hooks into — it only runs once Home has mounted.

---

## 7. Defect found in passing (Track 3 owns `insightEngine.ts` — fix in the Insight-depth PR)

`InsightSettings.denylist` is user-editable in Settings (`RewindTab.tsx:325-328`) and persisted,
but **`insightEngine.filter()` never consults it** — it only calls `isDeniedContext`, which uses
the *hardcoded* `DEFAULT_DENYLIST` in `screenRedact.ts:2-6` and takes no extra list. **The
user-configured Insight denylist is silently ignored.** This is a real privacy bug: a user who
adds an app to the denylist still has its screen content summarized and sent to Gemini.
