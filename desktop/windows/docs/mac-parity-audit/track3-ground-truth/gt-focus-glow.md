# Ground Truth: Focus Assistant + Glow Overlay (Mac v0.12.72)

Source root: `desktop/macos/Desktop/Sources/ProactiveAssistants/` in the FROZEN mac-ref
worktree (`C:/Users/chris/projects/omi/.worktrees/mac-ref/desktop/macos/`). All paths
below are relative to that root unless stated otherwise.

## 1. Capture pipeline (shared with all proactive assistants)

Focus Assistant does **not** run its own screenshot loop. It receives frames from the
shared Rewind capture loop in `ProactiveAssistantsPlugin.swift`:

- Capture cadence: `RewindSettings.shared.effectiveCaptureInterval(isOnBattery:)`
  (`Rewind/Core/RewindModels.swift:430-432`). Default `captureInterval = 3.0` seconds
  (`RewindModels.swift:410`, key `rewindCaptureInterval`); on battery it's multiplied by
  `batteryCaptureIntervalMultiplier = 3.0` (`RewindModels.swift:360`) → 9s on battery.
- `restartCaptureTimer` (`ProactiveAssistantsPlugin.swift:436-441`) drives a
  `Timer.scheduledTimer` at that interval that calls `captureFrame()`.
- Every captured frame is offered to `FocusAssistant.analyze(frame:)`
  (`FocusAssistant.swift:150-180`), but the assistant applies its own smart filter
  (§2) before actually calling Gemini — so the *effective* analysis rate is far
  lower than 1/3s in steady state.

## 2. Per-frame gating before a Gemini call (`FocusAssistant.shouldSkipAnalysis`, lines 187-254)

Skip analysis if, in order:
1. **Error backoff active** (`errorBackoffEndTime`) — set on exceptions, exponential:
   `min(5.0 * 2^(consecutiveErrorCount-1), 300.0)` → 5s, 10s, 20s, 40s… capped at 5 min
   (line 608).
2. No `lastStatus` yet → always analyze (cold start).
3. **Context changed** (app or normalized window title differs from last analyzed
   context, via `ContextDetection.didContextChange`) → **always analyze**, bypassing
   cooldown.
4. **Cooldown active** (`analysisCooldownEndTime`, set only after a *distraction*
   detection) → skip unless context changed.
5. **`lastStatus == .focused`** and same context → skip (no re-analysis while calmly
   focused on the same app/window).
6. Otherwise (distracted or edge case) → analyze.

Also hard-skipped regardless of the above: `loginwindow` / `ScreenSaverEngine`
(lock/login screen, line 152-155), and any app in
`FocusAssistantSettings.shared.isAppExcluded()` (built-in excluded apps ∪ user-added
exclusions ∪ Rewind privacy exclusions, `FocusAssistantSettings.swift:145-149`).

Cooldown length after a distraction: `FocusAssistantSettings.shared.cooldownIntervalSeconds`
= `cooldownInterval (minutes) * 60`, default **10 minutes**
(`FocusAssistantSettings.swift:19,87-101`).

Analysis runs in parallel, backpressure-limited to `maxPendingTasks = 3`
(`FocusAssistant.swift:38,118-120`); stale-frame results (an older frame's response
arriving after a newer one was processed) are discarded (`frame.frameNumber >
lastProcessedFrameNum` check, line 460).

## 3. What is sent to Gemini

- Model: `GeminiClient(apiKey: nil, fallbackModel: "gemini-2.5-flash")`
  (`FocusAssistant.swift:82`). Primary model comes from `ModelQoS.Gemini.proactive`
  (`ModelQoS.swift:75-78`): `gemini-2.5-flash` on the "premium" tier, `gemini-2.5-pro`
  on "max" tier. So Pro→Flash fallback only matters on the max tier; premium tier is
  Flash→Flash (no-op fallback).
- Image: current frame's JPEG data, sent as `inline_data` with **mime type
  `image/webp`** (note: mislabeled — the field is literally `mimeType: "image/webp"`
  regardless of actual encoding, `GeminiClient.swift:501`), base64-encoded.
  `thinkingBudget: 0` (Flash's minimum, no extended reasoning) unless overridden.
- Request goes through the Rust backend proxy `/v1/proxy/gemini/models/{model}:generateContent`
  (never a raw Gemini key on device), Firebase Bearer auth (`GeminiClient.swift:335-357`).
- Retries: up to 2 retries (3 total attempts) for transient errors, backoff 2s then 8s
  (`GeminiClient.swift:464-469,489`).
- Prompt text = context block + history block + `"Now analyze this new screenshot:"`
  (`FocusAssistant.swift:687-701`). Context block (`refreshContext()`, lines 615-685,
  cached 120s) includes: AI user profile text, current date/time, up to 10 active
  goals, up to 50 tasks (by priority), up to 50 "core" category recent memories.
  History block = up to `maxHistorySize = 10` most recent analyses, formatted
  `"N. [status] app_or_site: description"` + optional message line (`formatHistory()`,
  lines 435-446).

## 4. JSON response schema (exact, `FocusAssistant.swift:707-716`)

```
type: object
required: [status, app_or_site, description]
properties:
  status:      string, enum ["focused", "distracted"]
  app_or_site: string   (the app or website visible)
  description: string   (brief description of what's on screen)
  message:     string   (optional; coaching message)
```
Decoded into `ScreenAnalysis` (`FocusModels.swift:12-37`), which is also
`AssistantResult`-conforming. `FocusStatus` enum is exactly `focused` / `distracted`
(`FocusModels.swift:5-8`) — there is no "neutral"/"idle" state.

## 5. System prompt — key rules (full text: `FocusAssistantSettings.swift:23-51`, prompt
version 2, user-customizable, resettable)

- Persona: "You are a focus coach." Judge the **PRIMARY/MAIN window**, not log/terminal
  text mentioning other things (explicit anti-hallucination instruction: text in a
  terminal that says "YouTube" does not mean the user is on YouTube).
- Context-aware: given active goals/tasks/memories/time/history, but told not to let
  context override obvious distractions.
  - If screen activity clearly relates to active goals/tasks → **focused**.
  - Use history to notice patterns / vary responses (avoid repetitive coaching text).
- **distracted** if primary window is: YouTube/Twitch/Netflix/TikTok (actual video,
  not just text), casual social feeds (Twitter/X, Instagram, Facebook, Reddit), news/
  entertainment/games, or any content consumption with no clear work purpose.
- **focused** if primary window is: code editors/IDEs/terminals, documents/
  spreadsheets/slides/design tools, email/work chat (Slack/Teams)/research, or
  work-related browsing (Stack Overflow, docs, PRs, Jira).
- Tie-break rule: **"When in doubt, lean toward distracted"** — the bias is toward
  over-nudging rather than silently letting drift continue.
- Always include a coaching `message`, **max 100 characters** (fits the notification
  banner): varied/playful/direct/motivational nudge if distracted; varied
  acknowledgement (not literally "Nice focus!" every time) if focused.

Prompt is versioned (`currentPromptVersion = 2`); bumping it wipes any saved custom
prompt override so all users pick up prompt changes automatically
(`migratePromptIfNeeded`, lines 66-73).

## 6. Nudge / notification generation and throttling

State-change-only notification: notifications only fire on a **transition**, not on
every distracted/focused frame result, guarded by `lastNotifiedState`
(`FocusAssistant.swift:483,554`) — this dedupes across the up-to-3 parallel in-flight
analyses.

- **Distracted transition** (`lastNotifiedState != .distracted` → becomes
  `.distracted`): records analytics (`distractionDetected`), persists to SQLite +
  memories + backend (§7), updates `FocusStorage` UI state, fires red glow
  (`onDistraction?()`), starts the cooldown, and — if `message` non-empty and
  `FocusAssistantSettings.notificationsEnabled` — sends
  `NotificationService.sendNotification(title: "Focus", message: "\(appOrSite) -
  \(message)", assistantId: "focus", sound: .none, context:...)` (lines 483-553).
- **Focused transition from distracted** (`wasDistracted` true): persists similarly,
  fires green glow (`onRefocus?()`), and — if message + notifications enabled — sends
  a "Back on track" notification with just `message` as the body (lines 554-604).
  A focused transition from *nil* (cold start, no prior distraction) persists data
  but does **not** fire glow or a notification (`if wasDistracted` gate, line 568).
- **Master gate for the assistant itself**: `FocusAssistant.isEnabled` requires BOTH
  `FocusAssistantSettings.isEnabled` AND `FocusAssistantSettings.notificationsEnabled`
  — "no notification setting, no Gemini call at all" (lines 10-19). So disabling
  notifications fully stops screen analysis, not just the banner.
- **Delivery-layer throttle** (`NotificationService.sendNotification`,
  `Services/NotificationService.swift:250-353`), applies on top of the above:
  - Snooze: suppressed entirely if `FloatingControlBarManager.shared.isSnoozed`.
  - Master toggle: suppressed if `notifications_enabled` (backend-synced) is off.
  - **Frequency throttle** (`minInterval(forLevel:)`, lines 506-515), keyed by both
    per-assistant and global last-send timestamp:
    - 0 = Off → `.infinity` (drop everything)
    - 1 = Minimal → 60 min
    - 2 = Low → 30 min
    - 3 = Balanced → 10 min
    - 4 = High → 3 min
    - 5 = Maximum → no throttle (`nil`)
  - Default frequency level is **0 (Off)** — proactive notifications are opt-in
    (`defaultFrequencyLevel = 0`, one-time off-by-default migration, lines 90-93,
    462-482).
  - Delivery is **floating-bar only by default** (`deliverSystemBanner: false`);
    Focus never passes `deliverSystemBanner: true`, so it never produces a native
    macOS system banner — only the in-app floating-bar popup
    (`FloatingControlBarManager.shared.showNotification`).
  - Sound: Focus explicitly passes `sound: .none` for both alert types (custom
    `.focusLost` / `.focusRegained` AIFF sounds exist in `NotificationSound` but
    Focus does not use them for its own notifications).

## 7. Session model & persistence

- **A "focus session" record = one analysis result**, not a continuous span with
  start/end timestamps. Each Gemini call that produces a state (focused or
  distracted) is one `focus_sessions` row; "session duration" is *derived* later as
  the time between consecutive rows (see below), not stored as start/end at write
  time.
- Nothing "starts"/"ends" a focus session explicitly — there's no separate opt-in
  intent capture UI. Activation = `FocusAssistantSettings.isEnabled` (default `true`)
  AND `notificationsEnabled` (default `true`) AND the Rewind capture loop running
  (screen-recording permission). There is no user-specified "goal" required to
  activate Focus — it runs ambiently whenever notifications are on, though the
  system prompt gives extra credit to activity matching the user's *existing* Goals/
  Tasks from `GoalStorage`/`ActionItemStorage`.
- **SQLite table `focus_sessions`** (migration 4, `Rewind/Core/RewindDatabase.swift:1120-1141`;
  migration 26 adds `windowTitle`, line 1690-1694):
  ```
  id              INTEGER PK autoincrement
  screenshotId    INTEGER  (FK -> screenshots, cascade delete)
  status          TEXT NOT NULL   -- "focused" | "distracted"
  appOrSite       TEXT NOT NULL
  description     TEXT NOT NULL
  message         TEXT
  durationSeconds INTEGER
  backendId       TEXT
  backendSynced   BOOLEAN NOT NULL DEFAULT false
  createdAt       DATETIME NOT NULL
  windowTitle     TEXT            -- added migration 26
  ```
  Indexes: `createdAt`, `status`, `screenshotId`, `backendSynced`.
- Every saved session is **also** written to the unified `memories` table
  (`saveFocusToMemoriesTable`, lines 782-826) with `category: "system"`, `source:
  "desktop"`, content `"Focused on X: desc"` / `"Distracted on X: desc"`, and tags
  `["focus", "focused"|"distracted", "app:{appOrSite}"]` (+`"has-message"` if a
  coaching message exists) — this is what makes focus events searchable/filterable
  alongside other memories.
- Backend sync: `syncFocusSessionToBackend` (lines 829-860) posts the same content/
  tags as a generic **memory** via `APIClient.shared.createMemory(...)` —
  **there is no dedicated `/v1/focus/*` backend endpoint.** `FocusStatsResponse` /
  `CreateFocusSessionRequest` / `FocusSessionResponse` structs exist in
  `FocusStorage.swift:371-435` but are dead/legacy — grep confirms no call sites
  construct or fetch them. Focus data lives purely in local SQLite + the generic
  memories sync; there is no backend focus-stats API to port.
- Deletion: `FocusStorage.deleteSession` removes the SQLite row (or, if synced, the
  backend memory) — same dual-table cleanup pattern.

## 8. Score / stats aggregation formula (`FocusStorage.swift`, `computeStats`, lines
162-221; UI: `MainWindow/Components/FocusSummaryWidget.swift`)

Sessions are stored **newest-first**. Since a raw row has no explicit duration, the
duration for session *i* is derived from the timestamp of the *next more recent*
session (or "now" for the very latest):
```
for i in 0..<sessions.count:
  endTime = (i == 0) ? now : sessions[i-1].createdAt
  duration = max(0, endTime - sessions[i].createdAt)   // seconds
  if status == focused:    focusedSeconds    += duration
  if status == distracted: distractedSeconds += duration; tally into topDistractions[appOrSite]
```
`FocusDayStats`:
```
focusedMinutes    = focusedSeconds / 60
distractedMinutes = distractedSeconds / 60
sessionCount, focusedCount, distractedCount
topDistractions   = top 5 apps by totalSeconds, tuple (appOrSite, totalSeconds, count)
focusRate (computed) = focusedMinutes / (focusedMinutes + distractedMinutes) * 100   // 0 if total is 0
```
`todayStats` = same formula filtered to `sessions` where `Calendar.isDate(createdAt,
inSameDayAs: today)`; `allTimeStats` = same formula over the full `sessions` array
(capped at `maxStoredSessions = 500`, oldest trimmed). **This is the only "daily
score"** — a percentage (focus rate), not a points/gamification score. The
`FocusSummaryWidget` UI (Today/Total tabs) surfaces exactly these four numbers:
Focus Time (min), Distracted (min), Focus Rate (%), Sessions (count) — plus (not
wired into the widget shown) `topDistractions`.

## 9. Excluded apps / activation conditions

- No dedicated "start a focus session" UX / intent capture — Focus is an always-on
  ambient assistant once enabled+notifications-on (see §7). It leans on **existing**
  Goals/Tasks for context, not a fresh per-session goal.
- Exclusions (`FocusAssistantSettings.isAppExcluded`, lines 145-149): union of
  `TaskAssistantSettings.builtInExcludedApps` (shared built-in list with the Task
  assistant), user-added `excludedApps` (persisted `focusExcludedApps` UserDefaults
  array), and `RewindSettings.shared.isAppExcluded` (global privacy exclusions —
  excluded apps still aren't screenshotted at all, so Focus never even sees them).
  Users manage the Focus-specific list via `excludeApp(_:)` / `includeApp(_:)`.
- Hard-coded skip regardless of settings: `loginwindow`, `ScreenSaverEngine` (§2).

## 10. Glow overlay — mechanics

Current implementation is **4 separate edge windows** (top/bottom/left/right)
surrounding the target window, NOT one window over the whole screen and NOT a
border drawn on the target window itself. This is deliberate — avoids stealing
hover/click events from the target window's content area (`GlowEdgeWindow.swift:12-14`).
An older, unused single-window class `GlowOverlayWindow.swift` still exists (same
mechanics as below) but `OverlayService` only instantiates `GlowEdgeWindow`.

- **Trigger**: `OverlayService.shared.showGlowAroundActiveWindow(colorMode:)`
  (`Services/OverlayService.swift:18-32`), called from `ProactiveAssistantsPlugin`'s
  `FocusAssistant` callbacks:
  - `onRefocus` → `showGlowAroundActiveWindow(colorMode: .focused)` (green)
  - `onDistraction` → `showGlowAroundActiveWindow(colorMode: .distracted)` (red)
  (`ProactiveAssistantsPlugin.swift:322-331`; only fired on the *transitions*
  described in §6, not on every analysis).
- **Target window frame**: the frontmost app's focused window via Accessibility API
  (`AXUIElementCopyAttributeValue` for position+size), falling back to the largest
  window in `CGWindowListCopyWindowInfo` for that PID if AX fails
  (`OverlayService.swift:109-219`). Windows under 100×100 are ignored.
- **Window mechanics** (`GlowEdgeWindow.swift:24-55`): `styleMask: .borderless`,
  `isOpaque = false`, `backgroundColor = .clear`, `hasShadow = false`,
  **`level = .popUpMenu`** (floats above normal app/panel windows, below true
  system-alert level), **`ignoresMouseEvents = true`** (fully click-through),
  `collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]` (shows on
  every Space, doesn't participate in Mission Control / app-switcher cycling),
  `animationBehavior = .none` (avoids Core Animation crash on rapid close).
- **Geometry**: `glowThickness = 20pt` (extends outward from the target window's
  edge), `overlap = 4pt` (extends inward into the target window for a seamless
  look) — computed per-edge by `SpatialOverlayGeometry.glowEdgeFrame`.
- **Enable gate**: `AssistantSettings.shared.glowOverlayEnabled`
  (`Services/AssistantSettings.swift:20,84-90`, UserDefaults key
  `assistantsGlowOverlayEnabled`), checked before every show (bypassable only via
  the internal `isPreview` flag used by a settings-page preview button).
- **Auto-dismiss**: 3.5s after show (`Task.sleep(nanoseconds: 3_500_000_000)`,
  `OverlayService.swift:77-86`), or immediately replaced if a new glow is triggered
  before it finishes (`dismissOverlay()` cancels the pending dismiss task and
  `orderOut`s the 4 windows, clearing subviews first to stop animations).

## 11. Glow overlay — colors and animation (`GlowEdgeWindow.swift` / `GlowBorderView.swift`)

There is **no single fixed hex color** — the glow is an animated multi-stop
mesh/angular gradient built from HSB math around a base hue, not a solid color.

- **Color mode base hues** (`GlowColorMode`, `GlowBorderView.swift:4-23`):
  - `.focused`: `baseHue = 0.38` (green), animated hue range `0.33...0.45`
    (green → cyan)
  - `.distracted`: `baseHue = 0.0` (red), animated hue range `0.95...1.05` (red →
    orange, wrapping past hue 1.0)
  - Approximate representative colors at rest (`Color(hue:, saturation: 0.9,
    brightness: 0.9)`): focused ≈ `#17E63D`-ish spring green, distracted ≈
    `#E61717`-ish red (HSB 0.9/0.9, not literal hex constants in source — do not
    invent a single "the" hex; the palette is a 7–9 stop gradient with each stop's
    hue jittered by up to ±0.07 and saturation/brightness varying 0.7–1.0, see
    `meshColors(phase:)` lines 160-179 / `GlowEdgeWindow.swift:204-219`).
- **Rendering**: macOS 15+ uses `MeshGradient(width: 3, height: 3, points:,
  colors:)` with a 3×3 control grid whose center point wobbles
  (`sin/cos(phase * 2π) * 0.05`); macOS <15 falls back to a 7-stop `AngularGradient`
  rotating with `phase`. Two layers are composited: a `blur(radius: 8)` soft outer
  glow and a `blur(radius: 2)`, `opacity(0.8)` sharper inner definition line.
  Per-edge fade mask (`edgeFadeMask`, lines 104-133): a linear white→clear gradient
  so the glow fades toward the window interior (e.g. top edge: white at top,
  transparent by the bottom of the edge strip).
- **Animation timing** (`startAnimation()`, `GlowEdgeWindow.swift:222-242`, identical
  in `GlowBorderView.swift:197-218`):
  1. Fade in: `opacity 0 → 1`, `easeIn`, **0.3s**.
  2. Mesh/gradient phase animates `0 → 1.0` with
     `.easeInOut(duration: 1.5).repeatCount(3, autoreverses: true)` — i.e. 3
     back-and-forth cycles, ~1.5s each leg ("breathing"/pulsing motion, not a
     single pulse).
  3. Fade out: scheduled via `DispatchQueue.main.asyncAfter(deadline: .now() +
     2.5)`, `easeOut`, **0.5s** — so total visible life ≈ 3.0s of animation content,
     matching the ~3.5s window auto-dismiss in `OverlayService`.
- **Corner radius**: border mask uses `cornerRadius: 12` (matched to typical macOS
  window corner radius) for the (unused) whole-border variant; the edge-window
  variant doesn't need a corner mask since each edge is a separate rectangle.

## 12. What triggers show/hide/color, summarized

| Event | Color | Fires when |
|---|---|---|
| Distraction detected | `.distracted` (red) | `lastNotifiedState` transitions to `.distracted` (first distracted frame after being focused/unknown) |
| Refocus | `.focused` (green) | `lastNotifiedState` transitions from `.distracted` back to `.focused` — **only** when `wasDistracted` was true; a cold-start "focused" result does not glow |
| Manual test trigger | either | `ProactiveAssistantsPlugin.triggerGlow(colorMode:)` (line 995-998) — dev/test hook, and `FocusTestRunnerWindow.swift` / `GlowDemoWindow.swift` for manual QA of the effect |
| Hide | — | 3.5s auto-timer, or immediately superseded by the next `showGlow` call (old windows torn down before new ones show) |

---

# What exists on Windows vs. what must be built

Checked: `desktop/windows/src/**` (renderer + main). Grepped `Focus`, `focus_session`,
`distracted`, `GlowBorder`, `GlowEdge`, `glowOverlay`, `FocusPage`, `FocusStorage`,
`nudge` (case-insensitive) — **zero matches** for anything Focus/Glow-specific.

**Exists but unrelated — do not conflate:**
- `src/main/insight/` (`state.ts`, `notification.ts`, `toastWindow.ts`) — a *different*,
  already-existing "Insight" proactive-nudge system (interval-based, denylist,
  `notificationStyle: 'omi'`, own toast window). This is a separate assistant, not
  Focus. It's a plausible sibling/reference for "how Windows already does a
  proactive toast," but it is not the Focus glow and must not be repurposed as if it
  were.
- `src/main/overlay/` (`shortcut.ts`, `ipc.ts`) and `src/main/bar/` — these back the
  **floating-bar/orb overlay**, which per the task brief is a different UI surface
  and explicitly **exempt** from this restyle/port work. Do not touch or reuse this
  overlay's window for the glow.
- `src/renderer/src/lib/overlayShortcut.ts` — floating-bar shortcut wiring, same
  exemption as above.

**Nothing exists for:**
- A Focus assistant (screenshot-judging loop, Gemini call, JSON schema, system
  prompt, session/score model) — 0% ported.
- A Glow overlay window (click-through, colored, animated border around the active
  window) — 0% ported. Windows has no `BrowserWindow`-based click-through edge-glow
  equivalent anywhere in the codebase today.

## Build list for Windows parity (Electron/TypeScript equivalents)

1. **Capture reuse**: Windows already has `src/main/rewind/captureService.ts` (the
   Rewind screenshot loop) — Focus should subscribe to that cadence the same way Mac's
   `FocusAssistant` subscribes to `ProactiveAssistantsPlugin`'s frames, not spin up a
   second capture loop. Confirm actual interval/battery-multiplier parity with
   `captureDecision.test.ts` before wiring (out of scope for this doc; flag as an
   open question for whoever builds this).
2. **Focus judging service** (new, main process): port `shouldSkipAnalysis` gating
   logic (context-change bypass, cooldown, error backoff w/ exponential capped-at-5min
   backoff), the exact JSON schema in §4, and the system prompt in §5 verbatim (it's
   product copy, not Mac-specific — should be identical wording on Windows). Route
   through whatever Windows uses for its Gemini/LLM proxy calls (check parity with
   the backend proxy contract — same `/v1/proxy/gemini/models/*:generateContent`
   endpoint should work cross-platform since it's server-side).
3. **Settings**: mirror `FocusAssistantSettings` (isEnabled, notificationsEnabled as
   an AND-gate on running analysis at all, cooldownInterval minutes default 10,
   excludedApps, versioned prompt with reset-on-bump migration).
4. **Persistence**: a `focus_sessions` table (better-sqlite3, matching the column
   list in §7) + write-through to whatever unified "memories" local table/sync
   Windows already has (tags `["focus","focused"|"distracted","app:X"]`) — do NOT
   build a dedicated backend focus API; Mac doesn't have one either, sync via the
   existing generic create-memory call.
5. **Score/stats**: port `computeStats` exactly (§8) — derive duration from
   consecutive-row timestamp deltas, not stored start/end; `focusRate =
   focusedMinutes/(focusedMinutes+distractedMinutes)*100`.
6. **Notification throttle**: port the frequency-level table in §6 verbatim
   (0=off default, 1=60min...5=no-throttle) plus the per-assistant + global
   last-sent dedup, and the state-transition-only firing rule (not on every
   analysis).
7. **Glow overlay** (new Electron BrowserWindows): 4 separate always-on-top,
   click-through, transparent, frameless windows positioned around the active
   window's bounds (Windows equivalent of AX API: `active-win` package or Win32
   `GetForegroundWindow`/`GetWindowRect`), each with the animated gradient border
   described in §11. Electron equivalents of the Mac window flags:
   `transparent: true`, `frame: false`, `alwaysOnTop: true` (with a level comparable
   to `.popUpMenu`, i.e. above normal windows), `setIgnoreMouseEvents(true)`,
   `skipTaskbar: true`, and per-monitor/Space visibility (`visibleOnAllWorkspaces`
   equivalent). Match thickness (20px), overlap (4px), animation timing (0.3s fade
   in, 3×1.5s easeInOut pulse, 0.5s fade out, ~3.5s total lifetime), and the
   hue-jittered gradient (not a flat hex) — implement via CSS `@keyframes` on a
   `conic-gradient`/multi-stop `radial-gradient` inside a transparent
   `BrowserWindow`, or Canvas/WebGL if smoother animation is needed. Reuse the same
   base hues (green ≈ hue 0.38, red ≈ hue 0.0, HSB 0.9/0.9) rather than picking new
   brand colors — this is a Focus-specific feature color, not subject to the
   no-purple brand rule but also not an excuse to invent new hex values.
8. **Wiring**: on distraction-transition → red glow + throttled notification; on
   refocus-from-distracted-transition → green glow + throttled notification;
   cold-start focused → persist only, no glow/notification. Keep this transition
   logic in the judging service (not the UI layer) to match Mac's dedup-by-
   `lastNotifiedState` behavior exactly.
