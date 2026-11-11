# 08 — Reconnect / Device-Change / Silent-Mic Ground Truth

Scope: (A) realtime idle/wake reconnect + mid-session provider failover, (B) audio
device-change handling in the capture stack, (C) silent-mic detection + recovery
escalation (PTT + continuous transcription). Mac paths cited from
`.worktrees/mac-ref/desktop/macos/`, Windows paths from
`.worktrees/track2-voice-bar/desktop/windows/`.

---

## A. Realtime idle/wake reconnect + mid-session provider failover (Mac)

All in `Desktop/Sources/FloatingControlBar/RealtimeHubController.swift` unless noted.
`RealtimeHubSession.swift` and `VoiceTurnCoordinator.swift` were checked directly —
neither owns reconnect/failover logic. `RealtimeHubSession.swift` is a lower-level
socket wrapper (comments at L227, L298, L396 reference reconnect but the controller
drives it). `VoiceTurnCoordinator.swift` is a pure state-machine/presentation layer
that only *receives* `.finish(turnID:reason:.providerFailed)` events from the
controller (confirmed by grep — no reconnect/failover/wake symbols in that file).

### A.1 Idle-close → re-warm

- Idle-close classification threshold: `RealtimeHubCloseClassifier.idleTeardownThreshold = 60`
  seconds (L36). A WebSocket-1008 close with no active turn and `aliveFor >= 60`
  is classified `.expectedIdleTeardown` (L58) — logged locally only, **not** sent to
  Sentry (`shouldReportToSentry` returns `false` for this category, L62-64).
  Comment (L22-26): "Gemini can idle-close warm sessions with WebSocket 1008 after
  the socket has lived for a while... should re-warm quietly rather than page
  Sentry."
- Re-warm is **reactive by default** (on `hubDidError`/close, not a proactive
  keepalive timer), but proactive in two other cases:
  - `systemDidWake()` (L993-995) — see A.3.
  - `reconnectWarmSessionIfSeedStale()` (L1345) — see A.4.
- "Re-warm" concretely = `teardownSession()` (drop the dead session object) +
  `ensureWarm()` (L1113) which lazily reconnects a fresh warm socket when idle.
  `ensureWarm()` is called from ~15 call sites (app-foreground, settings changes,
  provider changes, after failed sends, etc.) — it's the single idempotent entry
  point, not a dedicated "idle-close" path.

### A.2 Reconnect strike budget

- `RealtimeHubController.maxReconnectStrikes = 5` (L552, `private static let`).
- Strike consumption (`hubDidError`, L3588-3595):
  ```swift
  guard !reconnectPending, hubReconnectStrikes < Self.maxReconnectStrikes else { return }
  hubReconnectStrikes += 1
  reconnectPending = true
  DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
    guard let self else { return }
    self.reconnectPending = false
    if self.session == nil { self.ensureWarm() }
  }
  ```
  Fixed 1.5s delay per attempt (not exponential backoff). `reconnectPending` guards
  against overlapping retry timers. Once `hubReconnectStrikes >= 5`, `hubDidError`
  silently stops re-warming (PTT falls back to the STT cascade — no user-facing error,
  per the L3577-3580 comment: "Gemini idle-closes the socket... managed users have
  no BYOK key, so once `session` is nil `isActive` is false and PTT silently falls
  back to omni STT").
- **Reset condition** (L3583-3587): a socket that lived **> 60s** before closing is
  treated as a normal idle-close, not a failure — resets the whole state:
  ```swift
  if aliveFor > 60 {
    hubReconnectStrikes = 0
    fallbackProvider = nil
    pendingFailoverReason = nil
  }
  ```
  So the strike budget only depletes on *fast* repeated failures (aliveFor ≤ 60s);
  a session that survives past the idle window resets strikes AND clears any
  active provider failover (returns to Auto pick).

### A.3 `systemDidWake` — zombie-socket drop

```swift
// L987-995
/// System woke from sleep — proactively replace a possibly-stale socket so the first PTT
/// after sleep doesn't hit a zombie session (commit → no reply → no fallback → hang).
/// Only acts when idle: a live session exists and we're neither mid-reply nor mid-mint, so
/// this never interrupts an active turn or races a connect already in flight. ...
@objc private func systemDidWake() {
  requestSessionRefresh(reason: "system_wake")
}
```
Registered via `NotificationCenter` at L792-796 (NSWorkspace wake notification).
`requestSessionRefresh` (L1022-1032):
```swift
private func requestSessionRefresh(reason: String) {
  guard session != nil else { return }
  guard RealtimeHubLifecyclePolicy.canReplaceSession(lifecycleSnapshot) else {
    pendingSessionRefreshReason = reason  // defer until active turn ends
    return
  }
  teardownSession()
  ensureWarm()
}
```
So: **unconditional drop-and-rebuild of the existing socket** (no staleness check
beyond "a session exists"), but only when idle — if a voice turn is active or a
mint is in flight, the refresh is deferred (`pendingSessionRefreshReason`) and
applied later via `applyPendingSessionRefreshIfIdle()` (L1034) once the turn ends.
This is exactly the "zombie socket" fix: after sleep, a socket that looks alive
but is actually dead gets torn down proactively rather than discovered on the
next PTT commit (which would hang with no reply).

### A.4 `reconnectWarmSessionIfSeedStale` — content-based, not time-based

```swift
// L1343-1358
private func reconnectWarmSessionIfSeedStale() {
  guard session != nil else { return }
  let current = voiceSessionSeedContext()
  guard current != sessionVoiceSeedContextSnapshot else { return }
  guard !hasActiveVoiceTurn, !inputTurnInProgress else {
    pendingSessionRefreshReason = "voice_seed_changed"
    return
  }
  teardownSession()
}
```
"Stale" = the kernel-projected voice seed context (baked into the realtime
session's system instructions at connect time) no longer matches what's currently
projected — i.e. new typed main-chat turns changed what PTT's system context
should contain. It's a **content diff**, not an age/duration threshold. On staleness
it tears down the session (next `ensureWarm()` reconnects with the fresh seed);
if a turn is active/in-flight it defers the same way as A.3.

### A.5 `hubDidError` → `CredentialHealthManager.classifyProviderClose`

`hubDidError(_:source:)` at L3471. Classification enum
(`CredentialHealthManager.swift` L8-18, `CredentialFailureClass`):
```swift
enum CredentialFailureClass: Equatable {
  case backendUnauthorized
  case requiresLogin
  case paywalled
  case byokEnrollmentMismatch(provider: BYOKProvider?)
  case providerAuthFailed(provider: RealtimeHubProvider, mode: CredentialAuthMode)
  case providerQuotaExceeded(provider: RealtimeHubProvider)
  case backendTransient(statusCode: Int?)
  case providerTransient(provider: RealtimeHubProvider)
  case providerPolicyClose(provider: RealtimeHubProvider)
  case unknown
}
```
`classifyProviderClose(message:provider:)` (L242-257+) pattern-matches the close
message text: `"insufficient_quota"|"quota"|"resource exhausted"|"429"` →
`.providerQuotaExceeded`; provider-auth signal strings → `.providerAuthFailed`;
`"websocket closed (1008)"|"policy"` → `.providerPolicyClose`; else falls through
further checks (not fully read past L257, but the enum above is the full closed set).

Separately, `RealtimeHubCloseClassifier.category(...)` (top of file, L27-33) buckets
closes into `expectedIdleTeardown | providerAuthFailed | providerQuotaExceeded |
providerPolicyCloseFast | providerTransient` for telemetry/Sentry-noise purposes
(only fires for `"websocket closed (1008)"` messages; else returns `nil`, L45).

### A.6 `failoverToAlternateProvider` — trigger conditions + telemetry

Provider set: `RealtimeHubProvider` = `openai | gemini` (`RealtimeHubSettings.swift`
L17-19), `.alternate` toggles openai↔gemini (L54-59).

Trigger sites in `hubDidError` (L3565-3576):
```swift
teardownSession()
if case .providerAuthFailed = credentialFailureClass {
  if aliveFor < 10, failoverToAlternateProvider(reason: "auth") { return }
  return
}
if case .providerQuotaExceeded = credentialFailureClass {
  if failoverToAlternateProvider(reason: "quota") { return }
  return
}
```
- `providerAuthFailed` only triggers failover if the socket died **fast** (`aliveFor
  < 10s`) — a longer-lived socket that then hits an auth error does NOT fail over
  (comment L3566-3568: "transient fast closes re-warm the same provider... only
  switch for stable credential/quota classes").
- `providerQuotaExceeded` **always** triggers failover (no `aliveFor` gate).
- Any other failure class (`backendUnauthorized`, `requiresLogin`, `paywalled`,
  `byokEnrollmentMismatch`, `backendTransient`, `providerTransient`,
  `providerPolicyClose`, `unknown`) does **not** failover — falls through to the
  strike-budget re-warm path (A.2) on the same provider.

`failoverToAlternateProvider(reason:)` (L632-659):
```swift
private func failoverToAlternateProvider(reason: String = "other") -> Bool {
  guard fallbackProvider == nil else {
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "realtime_hub", from: effectiveProvider.rawValue, to: "cascade",
      reason: reason, outcome: .exhausted, extra: ["user_visible": false])
    return false  // already on the alternate → give up, PTT uses Claude cascade
  }
  let primary = RealtimeHubSettings.shared.provider
  fallbackProvider = primary.alternate
  pendingFailoverReason = reason
  DesktopDiagnosticsManager.shared.recordFallback(
    area: "realtime_hub", from: primary.rawValue, to: primary.alternate.rawValue,
    reason: reason, outcome: .degraded, extra: ["user_visible": false])
  teardownSession()
  ensureWarm()
  return true
}
```
**Limit: exactly one hop.** `fallbackProvider` is nil→alternate only once per
chain; if the alternate ALSO fails, the guard at top fires (`fallbackProvider !=
nil`) and it reports `outcome: .exhausted`, `to: "cascade"` and gives up —
PTT then falls back to the legacy Claude/STT cascade path, not a second realtime
provider. The strike reset at A.2 (`aliveFor > 60` clears `fallbackProvider = nil`)
is the only way the chain resets back to the primary.

A third failover call site exists for barge-in specifically:
`failoverBargeInReplacement(from:reason:)` (L673-696) — same
`recordFallback(area: "realtime_hub", ..., outcome: .degraded)` shape, used when a
provider dies mid-barge-in-replacement rather than at generic `hubDidError` time.

### A.7 `DesktopDiagnosticsManager.recordFallback` — full contract

Defined `Desktop/Sources/DesktopDiagnosticsManager.swift` L379-400:
```swift
func recordFallback(
  area: String,
  from: String,
  to: String,
  reason: String,
  outcome: DesktopFallbackOutcome,
  extra: [String: Any] = [:]
) {
  var properties: [String: Any] = [
    "area": bucketFallbackArea(area),
    "from": safeFallbackLabel(from, default: "none"),
    "to": safeFallbackLabel(to, default: "none"),
    "reason": bucketFallbackReason(reason),
    "outcome": outcome.rawValue,
  ]
  for (key, value) in sanitized(extra) { if properties[key] == nil { properties[key] = value } }
  record(.fallbackTriggered, properties: properties, trackRemotely: true)
}
```
`DesktopFallbackOutcome` (L22-26): `recovered | degraded | exhausted`.
Values are **bucketed into a closed allowlist**, unmatched → `"other"`
(`bucketFallbackArea`/`bucketFallbackReason`, L786-794):
- `allowedFallbackAreas` (L730-746, partial dump — includes): `sync_dispatch`,
  `pusher`, `stt_selection`, `vad`, `audio_merge`, `webhook`, `realtime_hub`,
  `ptt_cascade`, `gemini_model`, `gemini_proxy`, `gemini_stream_proxy`,
  `redis_ratelimit`, **`silent_mic`**, `wal_persistence`, `wal_upload`, (+ more not
  captured in this read window).
- `allowedFallbackReasons` (L756-771+): `timeout`, `provider_5xx`, `provider_429`,
  `enqueue_failed`, `config_incomplete`, `circuit_open`, `capability_mismatch`,
  `auth`, `quota`, `local_heal`, `policy`, `dispatch_disabled`, `byok`, `other`,
  `none` (+ more). **Note:** `"provider_unavailable"` (used by Windows'
  `voiceController.ts` L231) is NOT in this Mac allowlist — it would bucket to
  `"other"` server-side if Mac ever emitted it. Not blocking for this topic, but
  worth flagging for whoever owns the Windows↔Mac reason-string alignment.

Call sites specifically in `RealtimeHubController.swift` (grep, all
`area: "realtime_hub"`): L634, L646, L686, L2557, L2640, L2695, L2705, L3144 (8
total — this doc details L634/L646/L686, the provider-failover ones; the L2557+
sites are other realtime-hub degradation paths not covered by this brief).

`recordRealtimeProviderClose` (separate call, `DesktopDiagnosticsManager.swift`
L437-467) — NOT the fallback helper, used for close-category/Sentry breadcrumb
telemetry alongside (not instead of) `recordFallback`:
```swift
func recordRealtimeProviderClose(
  provider: String, category: String?, aliveFor: TimeInterval, activeTurn: Bool,
  authMode: CredentialAuthMode?, failureClass: CredentialFailureClass?
)
```
Called at `hubDidError` L3524-3530, unconditionally on every close (not gated by
outcome) — separate concern from the fallback telemetry contract.

---

## B. Audio device-change handling (Mac) — `Desktop/Sources/AudioCaptureService.swift`

This is a **CoreAudio IOProc-based** capture service (deliberately not
`AVAudioEngine` — comment L5-8: AVAudioEngine's implicit aggregate device creation
degrades Bluetooth A2DP output quality). Listens directly to two CoreAudio
property notifications.

### B.1 Listeners registered

- `kAudioHardwarePropertyDefaultInputDevice` (default input device changed) — via
  `AudioObjectAddPropertyListenerBlock` on `kAudioObjectSystemObject`
  (`updateDefaultDeviceListener`/`defaultDeviceListenerBlock`, referenced L63,
  L711-726 for the removal counterpart).
- `kAudioDevicePropertyStreamFormat` (format changed on the current device) — via
  `AudioObjectAddPropertyListenerBlock` on the device itself (L691-703,
  `installDeviceFormatListener`/`deviceFormatListenerBlock`).
  Both listener blocks dispatch onto `listenerQueue` → `audioQueue.async {
  handleConfigurationChange() }` (L691-694) — i.e. both device-swap AND
  format-change funnel into the **same** rebuild path; the code does not
  distinguish "route changed" from "format changed" beyond which property fired.

### B.2 Rebuild + retry (L745-864)

```swift
private func handleConfigurationChange() {
  guard isCapturing, !isReconfiguring else { return }
  isReconfiguring = true
  // Stop IOProc on old device, remove old format listener
  audioQueue.asyncAfter(deadline: .now() + 0.3) { [weak self] in   // let hardware settle
    self?.reconfigureAfterChange(retryCount: 0)
  }
}

private static let maxRetries = 3

private func reconfigureAfterChange(retryCount: Int) {
  // resolve new input device → get new stream format → rebuild AVAudioConverter
  // → create new IOProc → AudioDeviceStart
  // any failure at any step → retryOrGiveUp(retryCount: retryCount)
  // success → updateDefaultDeviceListener() + installDeviceFormatListener(); isReconfiguring = false
}

private func retryOrGiveUp(retryCount: Int) {
  if retryCount < Self.maxRetries {
    let delay = Double(retryCount + 1) * 1.0  // 1s, 2s, 3s backoff
    audioQueue.asyncAfter(deadline: .now() + delay) { [weak self] in
      self?.reconfigureAfterChange(retryCount: retryCount + 1)
    }
  } else {
    logError("AudioCapture: Giving up after \(retryCount + 1) attempts")
    isReconfiguring = false
  }
}
```
**Exact numbers:** 0.3s settle delay before the first rebuild attempt, then up to
`maxRetries = 3` retries with linear backoff **1s, 2s, 3s** (not exponential) — 4
total attempts (1 initial + 3 retries), ~6.3s worst case before giving up silently
(no user-facing error, no `recordFallback` call on this specific path — it's a
local `logError` only).

### B.3 Windows equivalent (recommendation, not yet implemented)

Windows PTT mic acquisition lives in
`desktop/windows/src/renderer/src/capture/pttGraph.ts` (`createGraph`,
`acquireMicStream` from `lib/audio.ts`) — **confirmed no
`navigator.mediaDevices.addEventListener('devicechange', …)` listener anywhere in
`capture/` or `lib/capture/`** (grepped both directories, zero matches). The one
`devicechange` listener that exists at all is narrowly scoped to the **realtime
voice session** (not PTT): `lib/voice/voiceController.ts` L126-128, L278
(`onDeviceChange` → `refreshHeadsetState()` only — re-checks whether a
Bluetooth/USB headset is connected for echo-gating purposes; it does **not**
rebuild the audio graph, does not retry, does not touch `pttGraph.ts`). A Mac-parity
device-change handler for `pttGraph.ts` would need: (1) subscribe to
`navigator.mediaDevices.ondevicechange` while a warm graph exists, (2) on fire,
`destroyGraph(warmGraph)` + `createGraph(true)` (mirroring `handleConfigurationChange`
→ `reconfigureAfterChange`), (3) linear-backoff retry (Mac's 1s/2s/3s, cap 3) on
`acquireMicStream()` rejection, matching `retryOrGiveUp`. No native WASAPI
`IMMNotificationClient`/`MMDeviceEnumerator` surface exists in
`src/main/` today (grepped — only a comment reference to WASAPI *loopback* via
Electron's `getDisplayMedia` at `src/main/index.ts` L499-504, unrelated to
device-change notifications); `navigator.mediaDevices.ondevicechange` (Chromium/
Electron renderer API) is sufficient and is the same mechanism Electron itself
uses under the hood — no new native module needed.

---

## C. Silent-mic detection + escalation (Mac) — TWO separate mechanisms

### C.1 Mechanism 1 — real-time watchdog during active capture (`AudioCaptureService.swift`)

Fires **while capturing**, independent of PTT turn boundaries.
```swift
// L106-114
private let silentMicWindowThreshold: Int = 2       // consecutive ~1s windows of near-zero peak
private let silentMicRecoveryCooldown: CFAbsoluteTime = 3.0   // seconds before re-arming after a fire
private let maxSilentMicFiresPerSession: Int = 3     // hard cap per capture session
```
`evaluateSilentMicWindow(peak:isBluetooth:now:)` (L166-201): peak ≤ 5 (≈ -76 dBFS)
for `silentMicWindowThreshold = 2` consecutive ~1s windows → fires
`SilentMicDetection`, provided the watchdog isn't in cooldown and hasn't hit
`maxSilentMicFiresPerSession = 3` for this session. By default (`detectSilentMicOnAnyTransport
= false`) only Bluetooth transports are watched; PTT explicitly opts into
all-transport detection (`PushToTalkManager.swift` L1546:
`capture.detectSilentMicOnAnyTransport = true`).

`SilentMicDetection.suggestedAction` (`AudioCaptureService.swift` L30-32):
```swift
var suggestedAction: SilentMicRecoveryAction {
  isBluetoothTransport ? .fallbackToBuiltIn : .rebuildCoreAudioStack
}
```
Escalation ladder (`PushToTalkManager.handleSilentMicDetection`, L1651-1681):
1. If Bluetooth AND a different built-in mic device exists → **switch device**:
   `stopMicCapture()` + `startMicCapture(overrideDeviceID: builtInID)` (no full
   CoreAudio teardown, just re-open on a different device). Telemetry:
   `recordPTTDeviceRouteChanged(recoveryAction: "switch_to_built_in_mic",
   recoveryResult: "succeeded"|"failed"|"no_built_in_mic"|"ignored_turn_ended")`.
2. Else (non-Bluetooth, or Bluetooth with no built-in fallback available) →
   **full CoreAudio capture-stack rebuild**: `requestCoreAudioCaptureRecovery`
   (L1683-1696) posts `NotificationCenter` `.coreAudioCaptureRecoveryRequested`
   and restarts PTT capture.

Separately, continuous transcription (`AppState+Transcription.swift`
`handleSilentMicFallback`, L586-609) uses the SAME `AudioCaptureService.onSilentMicDetected`
signal but only implements step 1 (Bluetooth→built-in swap) and emits the
**shared fallback telemetry** (not `recordPTTDeviceRouteChanged`):
```swift
DesktopDiagnosticsManager.shared.recordFallback(
  area: "silent_mic", from: "bluetooth", to: "built_in",
  reason: "local_heal", outcome: .recovered, extra: ["user_visible": false])
```
This is the canonical example call for the `silent_mic` allowlisted area.

### C.2 Mechanism 2 — post-hoc turn-level dead-turn detection (`PushToTalkManager.swift`)

Fires **after** a PTT turn ends, from the captured PCM buffer's peak amplitude —
independent of mechanism 1's live watchdog.
```swift
// L7-30
struct PTTSilentMicRecoveryPolicy {
  static let deadMicPeakThreshold = 5
  static let minDeadTurnSeconds: TimeInterval = 0.25
  static let consecutiveDeadTurnThreshold = 2
  private(set) var consecutiveDeadMicTurns = 0
  mutating func recordDiscardedTurn(totalSec: TimeInterval, peak: Int) -> Bool {
    if totalSec >= Self.minDeadTurnSeconds && peak <= Self.deadMicPeakThreshold {
      consecutiveDeadMicTurns += 1
    } else {
      consecutiveDeadMicTurns = 0
    }
    return consecutiveDeadMicTurns >= Self.consecutiveDeadTurnThreshold
  }
  mutating func recordSuccessfulTurn() { consecutiveDeadMicTurns = 0 }
  mutating func recordCaptureRebuild() { consecutiveDeadMicTurns = 0 }
}
```
Used identically on both the hub path (L863-897) and the omni/batch path
(L927-968): every discarded turn (empty/near-silent) calls
`recordDiscardedTurn(totalSec:peak:)`; after **2 consecutive** turns with
`totalSec ≥ 0.25s` and `peak ≤ 5`, `attemptRecovery` is true and
`requestCoreAudioCaptureRecovery(reason: "repeated dead-mic PTT turns",
restartPTT: false, ...)` fires the SAME full-rebuild path as mechanism 1 step 2.
Every discarded turn (regardless of whether recovery fires) is logged via:
```swift
DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
  source: "hub"|"omni_stt"|"batch_stt", mode:, audioSeconds:, voicedSeconds:,
  peak:, rms:, deviceDescription:, micPermissionGranted:, hubActive:,
  recoveryAction: attemptRecovery ? "capture_rebuild" : "none",
  recoveryResult: attemptRecovery ? "attempted" : "not_attempted")
```
`recordPTTSilentTurn` itself ALSO tracks a third, independent counter
(`DesktopDiagnosticsManager.swift` L277-322): `pttWatchdogThreshold = 3`
consecutive near-zero turns (`peak ≤ 5 && rms ≤ 5`, `watchdogEligible =
audioSeconds >= 0.35`) → fires `recordPTTWatchdogTriggered` (Sentry warning +
`recovery_action: "prompt_restart"`, `recovery_result: "not_attempted"`, L659-677) —
this is a **user-facing "please restart" escalation tier above the automatic
rebuild**, distinct from the 2-turn auto-rebuild trigger. So Mac's full ladder is:
turn 1 dead → log only; turn 2 dead → auto capture rebuild (mechanism 2's own
2-turn threshold) AND counts toward; turn 3 dead (of the *DesktopDiagnosticsManager*'s
separately-tracked, coarser `peak≤5 && rms≤5` counter) → Sentry alert suggesting
the user restart. These two counters (`consecutiveDeadMicTurns` in
`PTTSilentMicRecoveryPolicy` vs `consecutiveNearZeroPTTTurns` in
`DesktopDiagnosticsManager`) are separate state, reset independently
(`recordSuccessfulTurn`/`recordCaptureRebuild` for the former;
`recordPTTCommitted` or a loud turn for the latter).

**Too-short vs dead-mic distinction:** if `totalSec < minTurnAudioSeconds (0.35)`
the turn is classified "too short" (release beat capture) and gets a plain hint
(`finishTooShortPTTTurnWithHint`) WITHOUT counting toward the dead-mic escalation —
only turns that ran ≥ 0.25s (mechanism 2) / ≥ 0.35s watchdog-eligible (the
Diagnostics counter) with near-zero peak count as "dead mic" specifically.

### C.3 Windows current state — detection matches Mac's thresholds exactly, zero escalation

`desktop/windows/src/renderer/src/lib/ptt/constants.ts`:
```ts
export const MIN_TOTAL_AUDIO_SEC = 0.35   // = Mac minTurnAudioSeconds (PushToTalkManager.swift L665)
export const MIN_VOICED_SEC = 0.2         // = Mac minVoicedSeconds (PushToTalkManager.swift L666)
export const VOICED_RMS_THRESHOLD = 300   // = Mac voicedRMSThreshold (PushToTalkManager.swift L669)
export const VOICED_FRAME_SAMPLES = 320   // 20ms @ 16kHz, matches Mac's 20ms frame
export const DEAD_MIC_PEAK = 5            // = Mac deadMicPeakThreshold (PushToTalkManager.swift L8)
```
`lib/ptt/gate.ts` `gateDecision(stats)` (L60-64):
```ts
export function gateDecision(stats: AudioStats): GateDecision {
  if (stats.totalSec < MIN_TOTAL_AUDIO_SEC) return 'too-short'
  if (stats.voicedSec < MIN_VOICED_SEC) return stats.peak < DEAD_MIC_PEAK ? 'dead-mic' : 'silent'
  return 'ok'
}
```
This is a **single-turn, stateless** decision — confirmed no consecutive-turn
counter exists anywhere in `lib/ptt/` (only `gateDecision` computes the category;
nothing accumulates it across turns). `lib/ptt/machine.ts` L119-124 on `DRAINED`:
```ts
const decision = gateDecision(e.stats)
if (decision === 'too-short' || decision === 'dead-mic') {
  return { state: { ...s, phase: 'idle' }, effects: [{ kind: 'stopStream' }, { kind: 'showHint', hint: decision }, { kind: 'captureEnded' }] }
}
```
Only effect emitted: `showHint`. `hooks/usePushToTalk.ts` L75-82 maps it to UI text:
```ts
'dead-mic': {
  text: 'Mic heard nothing — check your input device in Windows sound settings',
  ms: TOO_LONG_HINT_MS   // 4000ms, same duration as the too-long hint
}
```
**Confirmed: no telemetry is emitted for `dead-mic` anywhere** — grepped
`machine.ts` for `trackEvent`/`recordFallback`/`showHint`; the only match is the
effect definition and its two dispatch sites. No `capture_rebuild`, no
`fallback_triggered`, no consecutive-turn tracking, no `pttGraph.ts` teardown/rebuild
call. Every single dead-mic hold — first, second, tenth in a row — produces the
identical 4-second hint and nothing else.

### C.4 Where to add escalation on Windows (files owned by this track)

- **State/counter:** add a Mac-parity consecutive-dead-turn counter next to
  `gateDecision` in `desktop/windows/src/renderer/src/lib/ptt/gate.ts` (or a new
  `deadMicPolicy.ts` beside it, mirroring `PTTSilentMicRecoveryPolicy`: threshold
  2 consecutive turns with `totalSec >= 0.25` — Windows doesn't currently define
  a `minDeadTurnSeconds` constant; Mac's is 0.25s, distinct from `MIN_TOTAL_AUDIO_SEC
  = 0.35`).
- **Trigger point:** `lib/ptt/machine.ts` L119-124, the `decision === 'dead-mic'`
  branch — this is the exact Windows analogue of Mac's L933-968 discard block. A
  new effect kind (e.g. `{ kind: 'rebuildCapture' }`) would need to be added to
  the `Effect` union (L62 area) and handled by `hooks/usePushToTalk.ts`.
- **Rebuild target:** `desktop/windows/src/renderer/src/capture/pttGraph.ts` —
  `warmGraph` teardown (`destroyGraph`) + re-`createGraph(true)`, since that's
  where the live `MediaStream`/`AudioContext`/`ScriptProcessorNode` graph lives
  (mirrors Mac's `requestCoreAudioCaptureRecovery` → stop/rebuild IOProc).
- **Telemetry:** call the Windows fallback-telemetry pattern (see D below) with
  `component: 'silent_mic'` (Mac's allowlisted area name), `from`/`to` describing
  the device/graph transition, `reason: 'local_heal'` (matches Mac's continuous-
  transcription silent-mic call) or a new bounded reason, `outcome: 'recovered'`
  on successful rebuild / `'exhausted'` if giving up after retries — no such call
  exists today anywhere in `lib/ptt/` or `capture/`.

---

## D. Windows `recordFallback` — no dedicated helper; established call-site pattern

**There is no `recordFallback()` function in the Windows codebase.** Confirmed by
grep across `desktop/windows/src/` for `recordFallback`/`desktop_health_event` — zero
hits for a definition. `billing.ts` L89-93 explicitly says so in a comment: *"a
loud, structured console.error (**no renderer-side recordFallback exists**) plus a
one-shot Sentry capture."*

Instead, every fallback/degradation site calls the shared analytics primitive
`trackEvent` (`lib/analytics.ts` L11-25, PostHog HTTP capture, no SDK) directly
with a hand-rolled but **consistently-shaped** payload matching the AGENTS.md
fallback contract field names (`component`/`from`/`to`/`reason`/`outcome`):
```ts
trackEvent('fallback_triggered', {
  component: 'realtime_mint',      // voiceController.ts L228
  from: provider,
  to: other,
  reason: 'provider_unavailable',
  outcome: 'recovered'
})
```
Five existing call sites establish this as the de facto Windows signature:

| File:line | component | from → to | reason | outcome |
|---|---|---|---|---|
| `lib/voice/voiceController.ts:79` | `voice_echo_gate` | `gated`→`released` | `watchdog_max_hold` | `degraded` |
| `lib/voice/voiceController.ts:227` | `realtime_mint` | `<provider>`→`<other>` | `provider_unavailable` | `recovered` |
| `lib/voice/voiceController.ts:439` | `voice_tts` | `openai_tts`→`system_voice` | `provider_unavailable` | `degraded` |
| `lib/capture/loopbackMusicFilter.ts:31` | `loopback_classifier` | `yamnet`→`passthrough` | `model_load_failed` | `degraded` |
| `lib/capture/captureEngine.ts:49` | `pcm_pipeline` | `worklet`→`script_processor` | (dynamic `reason`) | `degraded` |
| `lib/capture/captureEngine.ts:86` | `vad_gate` | `gated`→`passthrough` | (dynamic `reason`) | `degraded` |

**Recommended signature for the escalation work in this track** (matches the
existing pattern exactly, no new helper needed unless the team wants to formalize
one — that decision is out of scope for this doc):
```ts
trackEvent('fallback_triggered', {
  component: 'silent_mic',   // or 'ptt_cascade' for the STT-cascade-adjacent case
  from: string,               // e.g. 'default_device' | '<deviceId>'
  to: string,                 // e.g. 'rebuilt' | 'built_in_mic' | 'none'
  reason: string,              // e.g. 'local_heal' | 'device_unavailable'
  outcome: 'recovered' | 'degraded' | 'exhausted'
})
```
Note the field name mismatch vs Mac: Mac's helper param is named `area`, Windows'
established convention uses `component` — both map to the same closed-enum
concept in AGENTS.md's contract table (`component` / `area`). Use `component` to
match existing Windows call sites; do not introduce `area` as a second key.

**Caveat carried over from A.7:** Mac's server-side `allowedFallbackAreas` includes
`silent_mic` and `ptt_cascade` explicitly — reuse those exact strings for
`component` so cross-platform dashboards bucket Windows and Mac events together
instead of Windows falling into `"other"`.

---

## Summary of open items for the implementer

1. No auto-reconnect/failover/wake-handling exists on Windows for the realtime
   voice session (`sessionMachine.ts` `'fail'` → terminal `error` state only,
   confirmed no retry/reconnect symbols anywhere in `lib/voice/`).
2. Windows silent-mic *detection* already has exact Mac-parity thresholds
   (`DEAD_MIC_PEAK=5`, `MIN_TOTAL_AUDIO_SEC=0.35`, `MIN_VOICED_SEC=0.2`,
   `VOICED_RMS_THRESHOLD=300`) but zero escalation (no consecutive-turn counter,
   no capture rebuild, no telemetry) — Mac's is a 2-turn auto-rebuild + 3-turn
   Sentry-alert ladder plus a fully separate real-time Bluetooth/any-transport
   watchdog with its own 2-window/3-fire/3s-cooldown budget.
3. No device-change listener exists in Windows' PTT capture path at all
   (`capture/pttGraph.ts`); the only `devicechange` listener in the codebase is
   narrowly scoped to headset detection in the realtime voice session and does
   not rebuild anything.
4. No dedicated `recordFallback` helper exists on Windows — the established
   pattern is a direct `trackEvent('fallback_triggered', {component, from, to,
   reason, outcome})` call; five existing sites define the convention to follow.
