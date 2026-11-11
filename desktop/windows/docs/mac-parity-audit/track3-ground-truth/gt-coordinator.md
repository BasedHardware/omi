# Ground Truth: Mac `AssistantCoordinator` Framework

Mac reference: `desktop/macos/` @ frozen v0.12.72 (`C:/Users/chris/projects/omi/.worktrees/mac-ref/desktop/macos/`)

Files:
- `Desktop/Sources/ProactiveAssistants/Core/AssistantCoordinator.swift`
- `Desktop/Sources/ProactiveAssistants/Core/AssistantProtocol.swift`
- `Desktop/Sources/ProactiveAssistants/Core/ContextDetection.swift`
- `Desktop/Sources/ProactiveAssistants/Core/ProactiveAssistantOrchestrationPolicy.swift`
- `Desktop/Sources/ProactiveAssistants/ProactiveAssistantsPlugin.swift`
- `Desktop/Sources/ProactiveAssistants/Services/AssistantSettings.swift`
- `Desktop/Sources/ProactiveAssistants/Services/NotificationService.swift`

## 1. Shared analysis loop

`ProactiveAssistantsPlugin` (singleton, `@MainActor`) owns the capture timer and feeds
`AssistantCoordinator.shared` (also `@MainActor` singleton), which fans frames out to all
registered `ProactiveAssistant`s. There is no per-assistant timer — one shared capture loop,
one shared distribution/backpressure layer, four registered assistants (Focus, Task, Insight,
Memory) subscribe to the same frame stream.

**Capture cadence** (`ProactiveAssistantsPlugin.swift:436-445`, `restartCaptureTimer`):
```swift
let interval = RewindSettings.shared.effectiveCaptureInterval(isOnBattery: PowerMonitor.shared.isOnBattery)
captureTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { ... captureFrame() }
```
- Base interval: `RewindModels.swift:410` — `self.captureInterval = defaults.object(forKey: "rewindCaptureInterval") as? Double ?? 3.0` (default **3.0s**, user-adjustable via Rewind settings UI, key `rewindCaptureInterval`).
- On-battery multiplier: `RewindModels.swift:360,430-432` — `static let batteryCaptureIntervalMultiplier = 3.0`; `effectiveCaptureInterval` returns `captureInterval * 3.0` while on battery (so 3s → **9s** on battery by default).
- Timer restarts automatically on power-source change (`setupPowerAwareCaptureTimer`, line 412-434) — flushes the in-flight Rewind video chunk first, then reschedules with the new interval.
- Recovery mode uses a different fixed cadence: `recoveryInterval: TimeInterval = 5.0` (line 118), up to `maxRecoveryRetries = 30`. Background-poll fallback after that: fixed `60`s (`ProactiveAssistantsPlugin.swift:1453`).

**Master toggle — `screenAnalysisEnabled`** (`AssistantSettings.swift:22,37,53,105-111`):
```swift
private let screenAnalysisEnabledKey = "screenAnalysisEnabled"
private let defaultScreenAnalysisEnabled = true
var screenAnalysisEnabled: Bool {
    get { UserDefaults.standard.bool(forKey: screenAnalysisEnabledKey) }
    set { UserDefaults.standard.set(newValue, forKey: screenAnalysisEnabledKey); NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil) }
}
```
Default **true** (registered via `UserDefaults.standard.register(defaults:)`). This is the single
master switch: UI (`SidebarView.swift`, `RewindPage.swift`, `DashboardPage.swift`, `OmiApp.swift`)
reads/writes it to start/stop `ProactiveAssistantsPlugin` monitoring entirely — it does not gate
individual frames inside the loop; when off, `isMonitoring` is false and `captureTimer` never
fires at all. Synced from backend via `SettingsSyncManager.swift:54-55,123` (`screen_analysis_enabled` key), with a one-time local-default guard (`shouldKeepLocalScreenAnalysisDefault`).

**Per-assistant cooldown / cadence gate** — there is no fixed "cooldown" duration in the
coordinator itself; each assistant decides per-frame via the protocol hook:
```swift
func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool  // default: true (AssistantProtocol.swift:64-66)
```
`AssistantCoordinator.distributeFrame` (line 134-172) computes `timeSinceLastAnalysis` from
its own `lastAnalysisTime[identifier]` dict (seeded to `.distantPast` at registration, line 33)
and passes it to `shouldAnalyze` — the assistant itself owns its throttle policy (e.g. Focus vs
Task assistants can have different per-type cadences), the coordinator only tracks/reports elapsed time and updates the timestamp AFTER a `true` decision (line 158-160).

There IS a separate, generic **notification cooldown** (distinct from analysis cadence) in
`AssistantSettings`:
```swift
private let cooldownIntervalKey = "assistantsCooldownInterval"
private let defaultCooldownInterval = 10 // minutes
var cooldownIntervalSeconds: TimeInterval { TimeInterval(cooldownInterval * 60) }
```
(lines 19,34,66-81) — this is a legacy/available setting; the notification throttle actually
enforced at send-time is the frequency-level throttle in `NotificationService` (§4 below), not
this cooldown value directly (no direct read of `cooldownIntervalSeconds` found gating
`sendNotification`; grep shows it's exposed for UI/legacy but the enforced gate is frequency-based).

## 2. Context-switch detection

**Signal**: app name (bundle-resolved display name) + normalized window title. No pixel/visual
diffing — purely window-manager metadata (`WindowMonitor.getActiveWindowInfoAsync()`).

**Algorithm** — `ContextDetection.didContextChange` (`ContextDetection.swift:61-80`):
```swift
static func didContextChange(fromApp: String?, fromWindowTitle: String?, toApp: String?, toWindowTitle: String?) -> Bool {
    if fromApp != toApp { return true }
    let normalizedFrom = normalizeWindowTitle(fromWindowTitle)
    let normalizedTo = normalizeWindowTitle(toWindowTitle)
    if normalizedFrom != normalizedTo { return true }
    return false
}
```
`normalizeWindowTitle` (lines 8-57) strips cosmetic noise before comparing, so noisy title
churn doesn't look like a context switch:
- Braille spinner glyphs (U+2800-U+28FF)
- A fixed set of spinner/progress chars (`✳ ↻ ◐ ◑ ⠋ ⠙ ⣾ ◴ ▖ …`)
- Timer patterns: regex `\b\d{1,2}:\d{2}(:\d{2})?\b` (e.g. "12:34", "1:23:45")
- Terminal dimension patterns: regex `\b\d+[×x]\d+\b` (e.g. "80×24")
- Parenthetical/bracketed unread counts: `\(\d+\)`, `\[\d+\]`
- Collapses whitespace; empty result → `nil`

**Trigger point** — `AssistantCoordinator.checkContextSwitch(newApp:newWindowTitle:)`
(`AssistantCoordinator.swift:76-123`), called from `ProactiveAssistantsPlugin.captureFrame()`
on EVERY capture tick (`ProactiveAssistantsPlugin.swift:689-693`), i.e. gated by the capture
timer interval (3s default), not by window-focus events directly (though `onAppActivated`
also exists as a separate NSWorkspace-driven legacy app-switch path, line 562-606, calling
`AssistantCoordinator.notifyAppSwitch` — a different/legacy `onAppSwitch` callback, not the
context-switch path).

On a detected switch:
1. Coordinator updates `lastTrackedApp`/`lastTrackedWindowTitle` immediately.
2. Fires `Task { await TaskContextualResurfacingService.shared.observe(matched) }` for
   task-context resurfacing IF signed in and the app isn't Rewind-excluded (privacy gate,
   lines 98-109) — "context is an input to canonical re-evaluation, never permission to notify."
3. Fires `assistant.onContextSwitch(departingFrame:newApp:newWindowTitle:)` on every registered
   assistant via its own `Task {}` (fire-and-forget, parallel — no ordering guarantee across
   assistants), passing the **departing frame** (last frame captured before the switch).
4. Returns `true` to the caller.

**Gating effect on assistant runs — the analysis delay**: when `checkContextSwitch` returns
`true` and the plugin isn't already `isInDelayPeriod`, it starts a one-shot delay timer of
`AssistantSettings.shared.analysisDelay` seconds (`ProactiveAssistantsPlugin.swift:694-714`):
```swift
private let analysisDelayKey = "assistantsAnalysisDelay"
private let defaultAnalysisDelay = 60 // seconds (1 minute)
```
(`AssistantSettings.swift:21,36,92-102`) — default **60s**, user-configurable
(0 = instant, 60 = 1 min, 300 = 5 min per the doc comment). During the delay
(`isInDelayPeriod = true`): `AssistantCoordinator.clearAllPendingWork()` is called immediately
(cancels queued work per-assistant), and subsequent frames route to
`distributeFrameDuringDelay` instead of the normal `distributeFrame` path (only assistants
with `needsFrameDuringDelay == true` — default `false`, AssistantProtocol.swift:74-77 — receive
frames at all during the delay; used for time-sensitive detections like refocus tracking).
When the delay timer fires, `isInDelayPeriod = false` and normal distribution resumes.

The exact same delay/gating logic is duplicated for the legacy `onAppActivated` NSWorkspace
path (lines 576-606) as well as the per-capture-tick `checkContextSwitch` path (lines 694-714)
— both feed the same `analysisDelayTimer`.

## 3. Backpressure / overlap avoidance

Two independent backpressure layers:

**(a) Per-assistant in-flight guard** — `AssistantCoordinator.isAnalyzing: Set<String>`
(`AssistantCoordinator.swift:21`, `distributeFrame` lines 134-172,
`distributeFrameDuringDelay` lines 176-210):
```swift
guard !isAnalyzing.contains(identifier) else { continue }   // skip this assistant entirely
isAnalyzing.insert(identifier)
Task { [weak self] in
    defer { Task { @MainActor in self?.isAnalyzing.remove(identifier) } }
    guard await assistant.isEnabled else { return }
    guard await assistant.shouldAnalyze(...) else { return }
    ...
    if let result = await assistant.analyze(frame: frame) { await assistant.handleResult(result) { ... } }
}
```
If assistant A is still processing frame N when frame N+1 arrives, A is simply skipped for
N+1 (no queueing) — comment: "Prevents Task closures from accumulating CapturedFrame JPEG
data when analyze() is slow" (line 19-20). Each assistant is independent — one being busy
does not block others from running on the same frame.

**(b) Change-gated frame distribution** (separate from per-assistant analysis) —
`ProactiveFrameDistributionGate` / `ProactiveAssistantOrchestrationPolicy.distributionDecision`
(`ProactiveAssistantOrchestrationPolicy.swift:73-101,166-226`), driven from
`ProactiveAssistantsPlugin.distributeFrameIfChanged` (`ProactiveAssistantsPlugin.swift:931-957`):
- First frame ever → `.flushNow` (immediate).
- Context changed (app or normalized title, via the same `ContextDetection.didContextChange`)
  → `.scheduleDebounce`: restart a **3.0s** debounce timer (`Timer.scheduledTimer(withTimeInterval: 3.0, ...)`, line 949) so rapid switches settle before distributing — only the LATEST frame (`latestCapturedFrame`) is flushed when the timer fires, older superseded frames are dropped.
- No change → `.skip`, UNLESS the fallback interval has elapsed since last distribution:
  `distributionFallbackInterval: TimeInterval = 60` (line 73) generally, or
  `messagingDistributionFallbackInterval: TimeInterval = 15` (line 74) for a fixed
  `messagingFastPathApps` set (`Telegram, Messages, iMessage, WhatsApp, Signal, Slack, Discord, Messenger` — lines 78-81) where new content can arrive without a context change.
- Purpose per comment (line 67-68): "Eliminates continuous polling when the user stays on
  the same app/window."

**(c) Rewind-frame encoder backpressure** (adjacent, not assistant-specific) —
`isProcessingRewindFrame` bool (line 39) drops (not queues) a frame for the video/Rewind
indexer if the previous one is still encoding (`droppedFrameCount` counter, lines 40, 815-835).

**(d) Video-call throttle** — `ProactiveVideoCallThrottleGate` (`ProactiveAssistantOrchestrationPolicy.swift:140-164`), `videoCallThrottleFactor = 5` (`ProactiveAssistantsPlugin.swift:58`): captures only 1 of every 5 frames (~5s effective interval at 1s capture) while a conferencing app is frontmost, to reduce GPU/CPU contention with the call app's own screen share/encoding.

**(e) Screenshot-app yield** — `ProactiveScreenshotCaptureGate` (`ProactiveAssistantOrchestrationPolicy.swift:104-138`): capture is paused entirely (not just throttled) while a known screenshot/recording app (CleanShot, Shottr, Loom, OBS, etc. — `screenshotAppBundleIDs` set, lines 92-112) is frontmost, plus a `screenshotAppBackoffDuration: TimeInterval = 10`s backoff after it resigns, to avoid WindowServer lock contention that could freeze the other app's UI for 20-60s.

## 4. Orchestration policy — run order, priority, result dispatch

**Order**: `assistants: [String: any ProactiveAssistant]` is a plain `Dictionary`
(`AssistantCoordinator.swift:10`) — iteration order over `for (identifier, assistant) in assistants` is **unordered/undefined** (Swift Dictionary has no guaranteed order). There is no explicit priority field or ordering policy in the coordinator; all four assistants (Focus, Task, Insight, Memory) are treated as peers, each independently gated by its own `isEnabled`/`shouldAnalyze`, and each fired in its own detached `Task` — so in practice they run **concurrently**, not sequentially, with no cross-assistant priority arbitration at the coordinator level. (Any de-facto priority - e.g. one assistant's notification winning over another's when both fire close together - is handled downstream by `NotificationService`'s per-assistant + global frequency clocks, §5, not by the coordinator.)

**Result dispatch**: each assistant's `analyze(frame:)` returns `AssistantResult?`
(protocol: `AssistantProtocol.swift:4-7`, single method `toDictionary() -> [String: Any]`).
If non-nil, `assistant.handleResult(result, sendEvent:)` is called (assistant-owned — decides
whether/how to notify, log, or emit events) with a `sendEvent` closure that hops back to
`@MainActor` and calls `AssistantCoordinator.sendEvent(type:data:)` →
`eventCallback?(type, data)` — a single coordinator-level callback registered via
`setEventCallback` (lines 58-67), used to bridge events to the Swift UI / Flutter layer (single
fan-in point for all assistants' events, not per-assistant channels).

## 5. Plugin / registration contract (`ProactiveAssistant` protocol)

`AssistantProtocol.swift:10-59` (`protocol ProactiveAssistant: Actor`) — every assistant is
its own actor (independent isolation domain from the coordinator and from each other):

| Member | Signature | Default (extension, lines 62-81) |
|---|---|---|
| `identifier` | `var identifier: String { get }` | none — required |
| `displayName` | `var displayName: String { get }` | none — required |
| `isEnabled` | `var isEnabled: Bool { get async }` | none — required |
| `shouldAnalyze` | `func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool` | `true` (analyze every frame) |
| `analyze` | `func analyze(frame: CapturedFrame) async -> AssistantResult?` | none — required |
| `handleResult` | `func handleResult(_ result: AssistantResult, sendEvent: @escaping (String, [String: Any]) -> Void) async` | none — required |
| `onAppSwitch` | `func onAppSwitch(newApp: String) async` | no-op |
| `onContextSwitch` | `func onContextSwitch(departingFrame: CapturedFrame?, newApp: String, newWindowTitle: String?) async` | no-op |
| `needsFrameDuringDelay` | `var needsFrameDuringDelay: Bool { get async }` | `false` |
| `clearPendingWork` | `func clearPendingWork() async` | no-op |
| `stop` | `func stop() async` | none — required |

Registration: `AssistantCoordinator.register<T: ProactiveAssistant>(_ assistant: T)` (lines
29-36) is itself async-dispatched (`Task { let id = await assistant.identifier; ... }`),
storing into `assistants[id]` and seeding `lastAnalysisTime[id] = .distantPast`.
`registerDefaultAssistants()` (lines 245-249) is currently a stub (commented out — the four
concrete assistants are registered elsewhere, presumably `ProactiveAssistantsPlugin` init,
not shown in this file).

## 6. Notification throttling (`NotificationService.swift`)

Confirms the known model (freq 0-5, per-assistant + global clocks, suppression order,
floating-bar-only, sound none) with exact code:

**Frequency levels** (`currentFrequencyLevel`, `minInterval(forLevel:)`, lines 494-515):
```swift
static func currentFrequencyLevel() -> Int {
    guard UserDefaults.standard.object(forKey: Self.frequencyDefaultsKey) != nil else {
        return Self.defaultFrequencyLevel   // 0
    }
    let raw = UserDefaults.standard.integer(forKey: Self.frequencyDefaultsKey)
    return max(0, min(5, raw))
}
private static func minInterval(forLevel level: Int) -> TimeInterval? {
    switch level {
    case 0: return .infinity   // Off
    case 1: return 60 * 60     // Minimal:  1 per hour
    case 2: return 30 * 60     // Low:      1 per 30 min
    case 3: return 10 * 60     // Balanced: 1 per 10 min
    case 4: return 3 * 60      // High:     1 per 3 min
    default: return nil        // Maximum:  no throttle
    }
}
```
Default level `0` = **Off** (`private static let defaultFrequencyLevel = 0`, line 93) — matches
the one-time `migrateToOffByDefaultIfNeeded()` migration (lines 468-482) that forces existing
users to Off once, then never re-disables. Key: `notification_frequency`
(`frequencyDefaultsKey`, line 77), synced from backend, clamped `[0,5]`.

**Per-assistant vs global clock storage** (lines 102-108, 517-544):
```swift
private var lastNotificationAt: [String: Date] = [:]       // per-assistantId
private var lastNotificationAtGlobal: Date?                 // global across all assistants

private func isProactiveNotificationEligible(assistantId: String, now: Date) -> Bool {
    let level = Self.currentFrequencyLevel()
    guard let interval = Self.minInterval(forLevel: level) else { return true }   // Maximum
    if interval == .infinity { return false }                                     // Off
    if let last = lastNotificationAtGlobal, now.timeIntervalSince(last) < interval { return false }
    if let last = lastNotificationAt[assistantId], now.timeIntervalSince(last) < interval { return false }
    return true
}
private func shouldAllowProactiveNotification(assistantId: String) -> Bool {
    let now = Date()
    guard isProactiveNotificationEligible(assistantId: assistantId, now: now) else { return false }
    lastNotificationAt[assistantId] = now
    lastNotificationAtGlobal = now
    return true
}
```
Both clocks are checked (global first, then per-assistant) and BOTH updated together on
allow — i.e. the two limits combine as one shared budget: "Per-assistant + global limits
combine so a chatty assistant cannot starve another" (doc comment, line 519). There is no
separate per-assistant-only rate; the global clock alone is often the binding constraint since
it's updated by every assistant's successful send.

**Suppression order in `sendNotification` (lines 250-353)** — exact sequence, first match wins:
1. **Screen-capture-reset dedup** (lines 273-278) — one-per-episode guard, unrelated to
   frequency, checked first: `if title == Self.screenCaptureResetTitle && UserDefaults...(screenCaptureResetShownKey) { return }`.
2. **Snooze** (lines 280-285): `if FloatingControlBarManager.shared.isSnoozed { ...; return }` —
   "Honor the floating-bar snooze for both the in-bar preview and the native macOS banner."
3. **Master toggle** (lines 287-295): `if respectFrequency && !Self.areNotificationsEnabled() { ...; return }`.
4. **Frequency throttle** (lines 297-303): `if respectFrequency && !shouldAllowProactiveNotification(assistantId:) { ...; return }`.

So the confirmed order is **dedup → snooze → master-enabled → frequency**, matching the
brief's expected "snooze → master → frequency" with the screen-capture-reset dedup as an
additional assistant-specific special case ahead of all three. Both master-toggle and
frequency gates are skippable via `respectFrequency: false` (functional/system notifications:
Crisp replies, screen-recording permission repair, onboarding test) — snooze and the dedup
gate are NEVER skippable, even for functional notifications.

**Master toggle read** (lines 484-492): `masterEnabledDefaultsKey = "notifications_enabled"`,
defaults to `true` when absent (`guard UserDefaults...object(forKey:) != nil else { return true }`).

**Delivery is floating-bar-only by default** (lines 241-249, 312-324):
```swift
func sendNotification(..., deliverSystemBanner: Bool = false, ...) {
    ...
    FloatingControlBarManager.shared.showNotification(title:message:assistantId:sound:context:action:screenshotData:)
    guard deliverSystemBanner else { return }   // native macOS banner only if explicitly requested
    ...
}
```
Comment (lines 243-249): proactive AI notifications are floating-bar only because users who
disabled the floating bar got confused clicking the system banner with no conversation
context; only functional notifications (Crisp support replies, permission-repair prompts)
pass `deliverSystemBanner: true`.

**Sound**: `NotificationSound.none` case exists (line 10) mapping `unSound` to `nil`
(line 20-22) — i.e. proactive notifications can be sent with no system sound; `.focusLost`/
`.focusRegained` play custom `.aiff` files manually via `NSSound` (lines 25-48) rather than
through `UNNotificationSound`, because SPM-bundled resources aren't discoverable via
`UNNotificationSound(named:)`.

## Summary (≈30 lines)

- **Loop cadence**: one shared `ProactiveAssistantsPlugin` capture timer feeds
  `AssistantCoordinator.shared`, which fans out to all registered `ProactiveAssistant`s.
  Base interval 3.0s (`rewindCaptureInterval`, `RewindModels.swift:410`), ×3 on battery
  (`batteryCaptureIntervalMultiplier`, `RewindModels.swift:360`) via
  `effectiveCaptureInterval(isOnBattery:)`. Recovery-mode cadence 5.0s
  (up to 30 retries), background-poll fallback 60s. Master toggle
  `AssistantSettings.screenAnalysisEnabled` (default `true`) starts/stops monitoring
  entirely (`AssistantSettings.swift:37,105-111`) — it's an on/off for the whole loop, not a
  per-frame gate.
- **Context-switch detection**: `ContextDetection.didContextChange` compares app name
  (exact) + window title (normalized — strips spinners, timers `\d{1,2}:\d{2}(:\d{2})?`,
  terminal dims `\d+[×x]\d+`, unread-count brackets). Checked every capture tick via
  `AssistantCoordinator.checkContextSwitch` (`AssistantCoordinator.swift:76-123`). On switch:
  fires `onContextSwitch` on all assistants (parallel `Task`s), then starts a one-shot
  `analysisDelay` timer (default 60s, `AssistantSettings.swift:36`) during which
  `clearAllPendingWork()` runs and only `needsFrameDuringDelay`-opted-in assistants
  (default `false`) get frames, via `distributeFrameDuringDelay`.
- **Backpressure**: (a) per-assistant `isAnalyzing: Set<String>` skips (not queues) a busy
  assistant for the next frame (`AssistantCoordinator.swift:19-21,134-172`); (b) a separate
  change-gated distribution layer (`ProactiveFrameDistributionGate`) only pushes frames to
  assistants when app/title context changed, with a 3.0s debounce
  (`ProactiveAssistantsPlugin.swift:949`) and 60s/15s(messaging apps) periodic fallback;
  (c)-(e) adjacent gates: Rewind-encoder frame drop, 1-in-5 video-call throttle, full
  capture pause + 10s backoff when a screenshot/recording app is frontmost.
  All policy decision functions are pure/static in
  `ProactiveAssistantOrchestrationPolicy` (testable in isolation from the plugin).
- **Orchestration/priority**: assistants stored in an unordered `[String: ProactiveAssistant]`
  dict — no explicit run order or priority; all fire concurrently in independent `Task`s,
  gated individually by `isEnabled`/`shouldAnalyze`. Results dispatch through
  `assistant.handleResult(result, sendEvent:)`, which funnels into one coordinator-level
  `sendEvent` callback (single Swift-UI/Flutter bridge point).
- **Plugin contract** (`ProactiveAssistant: Actor`): required `identifier`, `displayName`,
  `isEnabled`, `analyze(frame:) -> AssistantResult?`, `handleResult`, `stop`; optional (defaulted)
  `shouldAnalyze` (default: analyze every frame), `onAppSwitch`/`onContextSwitch` (no-op),
  `needsFrameDuringDelay` (`false`), `clearPendingWork` (no-op). `AssistantResult` protocol =
  single `toDictionary()` method.
- **Notification throttle** (confirmed): frequency 0-5 → interval `[.infinity, 60m, 30m, 10m,
  3m, nil(no throttle)]`; per-assistant (`lastNotificationAt[id]`) AND global
  (`lastNotificationAtGlobal`) clocks BOTH gate and BOTH update together (shared budget, not
  independent). Suppression order in `sendNotification`: screen-capture-reset dedup → snooze
  (`FloatingControlBarManager.isSnoozed`, never bypassable) → master `notifications_enabled`
  toggle (bypassable via `respectFrequency: false`) → frequency gate (also bypassable).
  Delivery is floating-bar-only by default (`deliverSystemBanner: false`); native macOS banner
  only for opted-in functional notifications. `NotificationSound.none` exists for silent sends.
