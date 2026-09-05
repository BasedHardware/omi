@preconcurrency import AVFoundation
import Cocoa
import Combine
@preconcurrency import CoreAudio
import OmiSupport
import VoiceTurnDomain

struct PTTSilentMicRecoveryPolicy {
  enum RecoveryOutcome: String, Equatable {
    case succeeded
    case failed
  }

  struct DiscardedTurnDecision: Equatable {
    let shouldRebuildCapture: Bool
    let recoveryOutcome: RecoveryOutcome?
  }

  static let deadMicPeakThreshold = 5
  static let minDeadTurnSeconds: TimeInterval = 0.25
  static let consecutiveDeadTurnThreshold = 2
  /// The first dead turn of a session rebuilds on its own. Waiting for a second
  /// one assumes the user will press again, and on a fresh install they mostly
  /// do not: the first press is the one that fails, it fails silently as
  /// "Hold longer to record", and the recovery that exists for exactly this
  /// never runs. Once a rebuild has been issued, the ordinary two-turn threshold
  /// applies again so a genuinely broken mic cannot spin.
  static let firstRecoveryDeadTurnThreshold = 1

  private(set) var consecutiveDeadMicTurns = 0
  private var awaitingRecoveryOutcome = false
  /// Set once this policy has issued a capture rebuild. Gates the lower
  /// first-of-session threshold above.
  private(set) var hasRequestedRecovery = false

  /// - Parameters:
  ///   - holdSec: wall time the user held the key. Judgeability is measured on
  ///     the press, not on delivered audio: a capture that never became
  ///     operational reports zero seconds, which read as "too short to judge"
  ///     and made the dead-mic evidence for the worst failure class invisible.
  ///   - totalSec: audio the capture actually delivered.
  mutating func recordDiscardedTurn(
    holdSec: TimeInterval,
    totalSec: TimeInterval,
    peak: Int
  ) -> DiscardedTurnDecision {
    let recoveryOutcome: RecoveryOutcome?
    let shouldRebuildCapture: Bool
    let judgeableSeconds = Swift.max(holdSec, totalSec)

    if peak > Self.deadMicPeakThreshold {
      // Audible input proves the mic is alive, so a pending rebuild succeeded.
      // It does not clear a dead-turn streak: a turn that was audible and still
      // discarded is not evidence that capture is healthy for a whole turn, and
      // clearing here is what let the observed fresh-install sequence (dead,
      // audible, audible, dead) never reach the rebuild threshold. Only a turn
      // that actually committed proves that, and that goes through
      // `recordSuccessfulTurn`.
      recoveryOutcome = resolveRecoveryOutcome(.succeeded)
      shouldRebuildCapture = false
    } else if judgeableSeconds >= Self.minDeadTurnSeconds {
      recoveryOutcome = resolveRecoveryOutcome(.failed)
      consecutiveDeadMicTurns += 1
      let threshold =
        hasRequestedRecovery ? Self.consecutiveDeadTurnThreshold : Self.firstRecoveryDeadTurnThreshold
      shouldRebuildCapture = consecutiveDeadMicTurns >= threshold
      if shouldRebuildCapture {
        // Arm the outcome before issuing the side effect. This prevents a third
        // consecutive turn from asking for a second rebuild while the first awaits
        // its next judgeable turn.
        consecutiveDeadMicTurns = 0
        awaitingRecoveryOutcome = true
        hasRequestedRecovery = true
      }
    } else {
      // A press too short to judge carries no evidence either way — an accidental
      // tap that released before CoreAudio could deliver a frame. It must not
      // erase a dead-mic streak or resolve a pending rebuild.
      recoveryOutcome = nil
      shouldRebuildCapture = false
    }
    return DiscardedTurnDecision(
      shouldRebuildCapture: shouldRebuildCapture,
      recoveryOutcome: recoveryOutcome)
  }

  mutating func recordSuccessfulTurn() -> RecoveryOutcome? {
    consecutiveDeadMicTurns = 0
    return resolveRecoveryOutcome(.succeeded)
  }

  /// Bluetooth silent-mic fallback only needs the dead-mic streak cleared. It must
  /// not arm `capture_rebuild` outcomes — that recovery uses `switch_to_built_in_mic`.
  mutating func recordCaptureRebuild() {
    consecutiveDeadMicTurns = 0
  }

  /// Arm truthful success/failure reporting for a CoreAudio capture rebuild. Used by
  /// both the dead-mic threshold path and the mid-turn silent-mic watchdog rebuild.
  mutating func armCaptureRebuildOutcome() {
    consecutiveDeadMicTurns = 0
    awaitingRecoveryOutcome = true
    hasRequestedRecovery = true
  }

  private mutating func resolveRecoveryOutcome(_ outcome: RecoveryOutcome) -> RecoveryOutcome? {
    guard awaitingRecoveryOutcome else { return nil }
    awaitingRecoveryOutcome = false
    return outcome
  }
}

/// Routes a shortcut press through the reveal decision. Both PTT entry points call this,
/// so injecting `reveal`/`start` in a test exercises the shipping ordering rather than a
/// restatement of it.
///
/// The bar used to swallow the very press that revealed it, which cost the start sound,
/// the listening animation and — a double tap being two presses — locked mode. That bit
/// every press on a second display, where following the cursor re-places the window so it
/// is routinely not yet visible.
enum PushToTalkBarRevealPolicy {
  /// Reveals the bar when it is hidden, then *always* starts the turn.
  static func startPress(
    barVisible: Bool,
    reveal: () -> Void,
    start: () -> Void
  ) {
    if !barVisible { reveal() }
    start()
  }
}

/// Modifier-only shortcuts (Option, Fn, etc.) overlap with normal text editing:
/// Option-arrow navigation and dead-key entry first emit `flagsChanged`, then a
/// normal key-down. Do not let that first modifier event barge into an active
/// spoken reply before the accompanying editing key arrives.
///
/// The gate deliberately has no timing policy. `PushToTalkManager` supplies the
/// short hold delay, while this model makes the admission/cancellation contract
/// deterministic and independently testable.
struct ModifierOnlyPTTActivationGate {
  enum Action: Equatable {
    case scheduleStart
    case cancelPendingStart
    /// The modifier was released before the activation delay elapsed and no other
    /// key was pressed with it: a deliberate quick tap. No turn was started (an
    /// accidental brush of the modifier must stay inert), but the tap is real
    /// input and is offered to the double-tap detector.
    case cancelPendingStartAsQuickTap
    case releaseStartedTurn
    case none
  }

  private(set) var hasPendingStart = false
  private(set) var hasStartedTurn = false

  mutating func modifierStateChanged(isShortcutActive: Bool) -> Action {
    if isShortcutActive {
      guard !hasPendingStart, !hasStartedTurn else { return .none }
      hasPendingStart = true
      return .scheduleStart
    }

    if hasPendingStart {
      hasPendingStart = false
      return .cancelPendingStartAsQuickTap
    }
    guard hasStartedTurn else { return .none }
    hasStartedTurn = false
    return .releaseStartedTurn
  }

  mutating func nonModifierKeyPressed() -> Action {
    guard hasPendingStart else { return .none }
    hasPendingStart = false
    return .cancelPendingStart
  }

  mutating func consumePendingStart() -> Bool {
    guard hasPendingStart else { return false }
    hasPendingStart = false
    hasStartedTurn = true
    return true
  }

  mutating func cancelPendingStart() {
    hasPendingStart = false
  }

  mutating func reset() {
    hasPendingStart = false
    hasStartedTurn = false
  }
}

extension Notification.Name {
  static let coreAudioCaptureRecoveryRequested = Notification.Name("coreAudioCaptureRecoveryRequested")
}

#if DEBUG
  struct PTTOwnerBoundarySnapshot: Equatable {
    let activeTurnID: VoiceTurnID?
    let hasCaptureDriver: Bool
    let captureStartInFlight: Bool
    let hasTranscriptionDriver: Bool
    let hasOmniDriver: Bool
    let captureGeneration: UInt64
  }
#endif

/// One delegate instance belongs to one reducer-issued transcription effect.
/// Retiring the proxy when its physical service stops prevents a late callback
/// from service A from reading service B's current turn identity.
@MainActor
private final class VoiceTurnOmniDelegateProxy: RealtimeOmniServiceDelegate {
  weak var owner: PushToTalkManager?
  let identity: VoiceEffectIdentity

  init(owner: PushToTalkManager, identity: VoiceEffectIdentity) {
    self.owner = owner
    self.identity = identity
  }

  func omniDidConnect() { owner?.omniDidConnect(identity: identity) }
  func omniDidReceiveInputTranscript(_ text: String, isFinal: Bool, itemID: String?) {
    owner?.omniDidReceiveInputTranscript(
      text, isFinal: isFinal, itemID: itemID, identity: identity)
  }
  func omniDidReceiveAudio(_ pcm24k: Data) {
    owner?.omniDidReceiveAudio(pcm24k, identity: identity)
  }
  func omniDidFinishTurn() { owner?.omniDidFinishTurn(identity: identity) }
  func omniDidError(_ message: String) { owner?.omniDidError(message, identity: identity) }
}

/// Push-to-talk manager for voice input via the Option (⌥) key.
///
/// State machine:
///   idle → [Option down] → listening → [Option up] → finalizing → sends query → idle
///   idle → [Quick tap] → pendingLockDecision → [tap again within 400ms] → lockedListening
///   pendingLockDecision → [timeout] → finalizing → sends query → idle
@MainActor
class PushToTalkManager: ObservableObject {
  static let shared = PushToTalkManager()

  /// An automation turn drives provider/reducer boundaries itself;
  /// it has no physical capture buffer for this manager to silence-gate. Let the
  /// reducer reach `.finalizing`, then leave the exact commit to the harness.
  nonisolated static func shouldFinalizeCapturedInputPhysically(
    turnIntent: VoiceTurnIntent?
  ) -> Bool {
    turnIntent != .automation
  }

  /// Whether a shortcut-down may begin a fresh capture generation. The reducer
  /// owns supersession: response phases are deliberately admitted here so its
  /// `.start` event can atomically interrupt the old turn before mic capture
  /// for the new turn begins. Recording/finalizing phases remain exclusive to
  /// their existing physical capture lifecycle.
  nonisolated static func admitsListeningStart(
    activeTurnID: VoiceTurnID?,
    phase: VoiceTurnPhase?
  ) -> Bool {
    guard activeTurnID != nil else { return true }
    switch phase {
    case .pendingLockDecision, .awaitingResponse, .awaitingTools, .awaitingJournal, .playing:
      return true
    case .idle, .recording, .lockedRecording, .finalizing, .terminal, .none:
      return false
    }
  }

  private let voiceTurnCoordinator = VoiceTurnCoordinator.shared
  private var voiceTurnSnapshotObservation: VoiceTurnSnapshotObservation?

  /// A projection of the authoritative reducer. This manager owns microphone and
  /// provider I/O only; it never stores a second logical lifecycle state.
  var phase: VoiceTurnPhase? { voiceTurnCoordinator.activeTurn?.phase }
  private var currentVoiceTurnID: VoiceTurnID? { voiceTurnCoordinator.activeTurnID }
  private var isIdle: Bool { currentVoiceTurnID == nil }

  // MARK: - Private Properties

  private var globalMonitor: Any?
  private var localMonitor: Any?
  private var modifierOnlyActivationGate = ModifierOnlyPTTActivationGate()
  private var modifierOnlyShortcutStartWorkItem: DispatchWorkItem?
  /// Give text-editing chords (Fn-arrow, Option-letter, etc.) enough time to
  /// deliver their accompanying key-down before treating a modifier-only press
  /// as an intentional PTT barge-in. This is below perceptual PTT latency.
  private static let modifierOnlyShortcutActivationDelay: TimeInterval = 0.08
  private var barState: FloatingControlBarState?
  private var automationBarState: FloatingControlBarState?
  private var automationCaptureBypass = false
  /// The ordinary bridge start/stop probe intentionally avoids providers. This
  /// opt-in lane exercises the same manager routing and controller admission as
  /// a physical hold, while injecting PCM rather than opening CoreAudio.
  private var automationExercisesRealtimePath = false

  // Double-tap detection
  private var lastOptionDownTime: TimeInterval = 0
  private var lastOptionUpTime: TimeInterval = 0
  /// Uptime of the last modifier-only quick tap that did not start a turn.
  private var lastModifierQuickTapTime: TimeInterval = 0
  private let doubleTapThreshold: TimeInterval = 0.4
  /// Longest hold that still counts as a tap and opens the tap-to-lock window.
  /// Read by the discard judgement's tests: a tap this short must always be a
  /// short tap, never a late capture, and that only holds while the hold is
  /// latched at key-up rather than at the lock deadline.
  nonisolated static let tapToLockMaxHoldDuration: TimeInterval = 0.22

  // Transcription
  private var transcriptionService: TranscriptionService?
  // Realtime omni STT (replaces Deepgram). Connects through the omi backend relay.
  private var realtimeOmniService: RealtimeOmniService?
  private var omniDelegateProxy: VoiceTurnOmniDelegateProxy?
  // Realtime-as-hub (Phase 1): when active, the realtime model is THE hub — it does
  // in-session STT + reasoning + routing (tool choice) + speaks the reply. Mic PCM is
  // streamed to RealtimeHubController; there is no transcript→router→ChatProvider hop.
  // Mic chunks captured before the relay finishes connecting (raw 16k PCM),
  // flushed once the service exists so the user's first words aren't clipped.
  private var omniPreconnectBuffer: [Data] = []
  // True once the omni model returned any transcript this turn — gates the
  // Batch-STT fallback so a benign trailing socket error doesn't trigger it.
  private var audioCaptureService: AudioCaptureService?
  private var micCaptureStartInFlight = false
  private var silentMicRecoveryPolicy = PTTSilentMicRecoveryPolicy()
  /// Privacy-bounded capture-lifecycle correlation for each PTT attempt and any
  /// recovery it triggers. Fed from the same seams as the late silent-turn
  /// snapshot; emits one classified `ptt_audio_capture_lifecycle` event.
  private let pttLifecycle = PTTAttemptLifecycleRecorder()
  private var micCaptureGeneration: UInt64 = 0
  private var transcriptSegments: [String] = []
  // Stable provider item ids of finals already appended this turn. Dedup relay
  // re-deliveries by id, never by text (INV-6: never dedupe by user text), so a
  // legitimately repeated phrase within a turn is not silently dropped. Reset
  // wherever transcriptSegments is reset.
  private var seenFinalSegmentIDs: Set<String> = []
  private var lastInterimText: String = ""
  /// Owns the "type <text>" branch of a turn: whether this utterance dictates
  /// into the focused app instead of asking Omi, and the paste if it does.
  private let voiceTypeSession = VoiceTypeSession()
  /// 60s of 16 kHz mono s16le.
  private var hasMicPermission: Bool = false
  private var isCurrentSessionFollowUp = false
  private var currentContextSnapshot: PTTContextSnapshot?

  /// OCR text of this turn's pre-overlay frame, waiting briefly for the in-flight OCR when the
  /// realtime model escalates before it finished. Nil when no turn is capturing.
  func visibleScreenText(timeout: TimeInterval) async -> String? {
    let deadline = Date().addingTimeInterval(timeout)
    while currentVoiceTurnID != nil {
      if let snapshot = currentContextSnapshot { return snapshot.visibleText }
      if Date() >= deadline { return nil }
      try? await Task.sleep(nanoseconds: 100_000_000)
    }
    return nil
  }
  private var contextCaptureTask: Task<Void, Never>?

  // Batch mode: accumulate raw audio for post-recording transcription
  private var batchAudioBuffer = Data()
  private let batchAudioLock = NSLock()
  /// Hard cap on a single turn's buffered PCM (16 kHz mono int16) so a runaway
  /// (>~4.5 min) dictation can't grow RSS without bound. Kept just under the
  /// backend's ~5-min limit (HTTP 413) so we surface a client-side warning before
  /// buffering forever and failing at submit. 4.5 min × 16000 Hz × 2 bytes.
  nonisolated static let maxBatchAudioBytes = Int(4.5 * 60) * 16_000 * 2
  /// Set once per turn when the buffer hits the cap, so the warning fires once.
  private var batchAudioOverflowSignaled = false

  private static let hubWarmGraceSeconds: TimeInterval = 1.0

  private var activeVoiceRoute: VoiceTurnRoute? {
    voiceTurnCoordinator.activeTurn?.route
  }

  private var isOmniSTT: Bool {
    activeVoiceRoute == .omniSTT
  }

  private var isWaitingForHub: Bool {
    activeVoiceRoute == .hubWarmWait
  }

  private var isOnDeviceASR: Bool {
    activeVoiceRoute == .onDeviceASR
  }

  private var isHubMode: Bool {
    if case .hub = activeVoiceRoute { return true }
    return false
  }

  private init() {}

  // MARK: - Setup / Teardown

  func setup(barState: FloatingControlBarState) {
    self.barState = barState
    configureVoiceTurnCoordinator(barState: barState)
    hasMicPermission = AudioCaptureService.checkPermission()
    warmPTTInputRouting()
    installEventMonitors()
    // Realtime hub: wire it to the bar and warm the WS if it's enabled + BYOK-keyed,
    // so the persistent socket is ready before the first PTT (and stays warm after).
    RealtimeHubController.shared.setup()
    // Hermetic local harness has no Firebase SDK and no live realtime providers.
    if !DesktopLocalProfile.isEnabled {
      RealtimeHubController.shared.ensureWarm(userInitiated: true)
    }
    log("PushToTalkManager: setup complete, micPermission=\(hasMicPermission)")
  }

  func configureVoiceTurnCoordinator(barState: FloatingControlBarState) {
    voiceTurnCoordinator.configure(barState: barState)
    voiceTurnCoordinator.setEffectHandler { [weak self] effect in
      self?.handleVoiceTurnEffect(effect)
    }
    voiceTurnSnapshotObservation?.cancel()
    voiceTurnSnapshotObservation = voiceTurnCoordinator.observeSnapshots { [weak self] _ in
      self?.objectWillChange.send()
    }
  }

  func cleanup() {
    stopListening()
    voiceTurnCoordinator.reset()
    audioCaptureService = nil
    resetModifierOnlyShortcutActivation()
    removeEventMonitors()
    log("PushToTalkManager: cleanup complete")
  }

  // MARK: - Event Monitors

  private func installEventMonitors() {
    // Remove any existing monitors to make setup() safely re-entrant
    removeEventMonitors()

    let monitorMask: NSEvent.EventTypeMask = [.flagsChanged, .keyDown, .keyUp]

    // Global monitor — fires when OTHER apps are focused
    globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: monitorMask) {
      [weak self] event in
      Task { @MainActor in
        self?.handleShortcutEvent(event)
      }
    }

    // Local monitor — fires when THIS app is focused
    localMonitor = NSEvent.addLocalMonitorForEvents(matching: monitorMask) { [weak self] event in
      Task { @MainActor in
        self?.handleShortcutEvent(event)
      }
      return event
    }

    log("PushToTalkManager: event monitors installed")
  }

  private func removeEventMonitors() {
    resetModifierOnlyShortcutActivation()
    if let monitor = globalMonitor {
      NSEvent.removeMonitor(monitor)
      globalMonitor = nil
    }
    if let monitor = localMonitor {
      NSEvent.removeMonitor(monitor)
      localMonitor = nil
    }
  }

  private func handleVoiceTurnEffect(_ effect: VoiceTurnEffect) {
    switch effect {
    case .stopCapture(let turnID, let captureID):
      _ = stopMicCapture(captureID: captureID)
      _ = turnID
    case .finalizeCapturedInput(let turnID):
      guard voiceTurnCoordinator.activeTurnID == turnID else { return }
      guard
        Self.shouldFinalizeCapturedInputPhysically(
          turnIntent: voiceTurnCoordinator.activeTurn?.intent)
      else {
        log("PushToTalkManager: local automation turn owns synthetic captured-input finalization")
        return
      }
      continueFinalization()
    case .commitClaimedHubInput(let turnID):
      RealtimeHubController.shared.commitClaimedHubInput(turnID: turnID)
    case .prepareHubInput(let turnID, _):
      guard voiceTurnCoordinator.activeTurnID == turnID else { return }
      resolveRealtimeHubWarmWait(ready: true)
    case .transcriptionFinalizationTimedOut(let turnID, let mode):
      guard voiceTurnCoordinator.activeTurnID == turnID,
        voiceTurnCoordinator.activeTurn?.phase == .finalizing
      else { return }
      switch mode {
      case .omni:
        log("PushToTalkManager: omni finalization timeout — falling back to backend batch STT")
        fallBackToBatchTranscription(reason: "timeout")
      case .live:
        log("PushToTalkManager: live finalization timeout — sending transcript")
        sendTranscript(turnID: turnID)
      }
    case .screenEvidenceProtocolExpired(let turnID, let token):
      RealtimeHubController.shared.expireScreenEvidenceProtocol(turnID: turnID, token: token)
    case .finalizeJournal(let turnID, let identity):
      guard voiceTurnCoordinator.activeTurnID == turnID else { return }
      if Self.isHubRoute(voiceTurnCoordinator.activeTurn?.route ?? .undecided) {
        RealtimeHubController.shared.finalizeJournal(turnID: turnID, identity: identity)
      }
    case .cancelHub(let turnID, let route):
      if Self.isHubRoute(route) {
        _ = RealtimeHubController.shared.cancelTurn(turnID: turnID)
      }
    case .fallbackToTranscription(let turnID, let reason):
      guard voiceTurnCoordinator.activeTurnID == turnID else { return }
      RealtimeHubController.shared.abandonInputPreparation(turnID: turnID)
      // A dictation has already left the hub behind; the warm deadline firing
      // under it must not start the omni cascade over a turn that types.
      guard !voiceTypeSession.claimsTurn else {
        log("PushToTalkManager: hub warm deadline ignored — turn is a dictation")
        return
      }
      recordBackupTranscriptionFallback(reason: reason)
      resolveRealtimeHubWarmWait(ready: false)
    case .stopPlayback(let lease):
      if lease.lane == .nativeRealtime {
        _ = RealtimeHubController.shared.stopNativePlayback(lease: lease)
      } else {
        _ = FloatingBarVoicePlaybackService.shared.interruptCurrentResponse(leaseID: lease.id)
      }
    case .terminal(let record):
      RealtimeHubController.shared.voiceTurnDidTerminate(turnID: record.turnID)
      performTerminalCleanup(
        discardBufferedAudio: record.reason == .ownerChanged,
        parkWarm: Self.terminalReasonKeepsWarmCapture(record.reason))
    case .scheduleDeadline, .cancelDeadline, .cancelAllDeadlines,
      .staleEventDropped, .invalidTransition:
      break
    }
  }

  nonisolated static func isHubRoute(_ route: VoiceTurnRoute) -> Bool {
    switch route {
    case .hub, .hubWarmWait:
      return true
    case .undecided, .omniSTT, .deepgramBatch, .deepgramLive, .onDeviceASR:
      return false
    }
  }

  // MARK: - Shortcut Handling

  private func handleShortcutEvent(_ event: NSEvent) {
    guard ShortcutSettings.shared.pttEnabled else { return }
    let shortcut = ShortcutSettings.shared.pttShortcut

    switch event.type {
    case .flagsChanged:
      guard shortcut.modifierOnly else { return }
      handleModifierOnlyShortcutStateChanged(
        isShortcutActive: shortcut.matchesFlagsChanged(event))
      return
    case .keyDown:
      if shortcut.modifierOnly {
        if modifierOnlyActivationGate.nonModifierKeyPressed() == .cancelPendingStart {
          cancelPendingModifierOnlyShortcutStart()
        }
        return
      }
      guard !event.isARepeat else { return }
      handleKeyShortcutDown(isShortcutActive: shortcut.matchesKeyDown(event))
    case .keyUp:
      guard !shortcut.modifierOnly else { return }
      if shortcut.matchesKeyUp(event) {
        handleShortcutUp()
      }
    default:
      return
    }
  }

  private func handleModifierOnlyShortcutStateChanged(isShortcutActive: Bool) {
    switch modifierOnlyActivationGate.modifierStateChanged(isShortcutActive: isShortcutActive) {
    case .scheduleStart:
      scheduleModifierOnlyShortcutStart()
    case .cancelPendingStart:
      cancelPendingModifierOnlyShortcutStart()
    case .cancelPendingStartAsQuickTap:
      cancelPendingModifierOnlyShortcutStart()
      handleModifierOnlyQuickTap()
    case .releaseStartedTurn:
      handleShortcutUp()
    case .none:
      break
    }
  }

  private func scheduleModifierOnlyShortcutStart() {
    guard modifierOnlyShortcutStartWorkItem == nil else { return }
    let workItem = DispatchWorkItem { [weak self] in
      guard let self, self.modifierOnlyActivationGate.consumePendingStart() else { return }
      self.modifierOnlyShortcutStartWorkItem = nil
      self.handleKeyShortcutDown(isShortcutActive: true)
    }
    modifierOnlyShortcutStartWorkItem = workItem
    DispatchQueue.main.asyncAfter(
      deadline: .now() + Self.modifierOnlyShortcutActivationDelay,
      execute: workItem)
  }

  /// A modifier-only shortcut released inside `modifierOnlyShortcutActivationDelay`
  /// never starts a turn — that delay is what keeps an accidental brush of the
  /// modifier (or the modifier held as part of another shortcut) from recording.
  /// A *pair* of such taps is unambiguous intent, so it drives locked mode, and a
  /// tap while already locked sends, matching "Tap again to send".
  private func handleModifierOnlyQuickTap() {
    guard ShortcutSettings.shared.doubleTapForLock else { return }
    let now = ProcessInfo.processInfo.systemUptime
    if phase == .lockedRecording {
      lastModifierQuickTapTime = 0
      finalize()
      return
    }
    guard (now - lastModifierQuickTapTime) < doubleTapThreshold else {
      // First tap: stay completely inert. Nothing records, nothing is shown.
      lastModifierQuickTapTime = now
      return
    }
    lastModifierQuickTapTime = 0
    // Same reveal rule as a held press: the lock must happen even when the bar was not
    // showing on this display yet, or the double tap is lost on a second monitor.
    PushToTalkBarRevealPolicy.startPress(
      barVisible: FloatingControlBarManager.shared.isVisible,
      reveal: { FloatingControlBarManager.shared.show() },
      start: {
        log("PushToTalkManager: modifier-only double tap — entering locked listening")
        self.enterLockedListening()
      })
  }

  private func cancelPendingModifierOnlyShortcutStart() {
    modifierOnlyShortcutStartWorkItem?.cancel()
    modifierOnlyShortcutStartWorkItem = nil
    modifierOnlyActivationGate.cancelPendingStart()
  }

  private func resetModifierOnlyShortcutActivation() {
    modifierOnlyShortcutStartWorkItem?.cancel()
    modifierOnlyShortcutStartWorkItem = nil
    modifierOnlyActivationGate.reset()
  }

  private func handleKeyShortcutDown(isShortcutActive: Bool) {
    guard isShortcutActive else { return }

    // Let the first shortcut press reveal the compact bar instead of requiring it
    // to already be visible. This keeps onboarding step 3 quiet on entry while
    // still allowing the user to trigger the bar by pressing the key.
    PushToTalkBarRevealPolicy.startPress(
      barVisible: FloatingControlBarManager.shared.isVisible,
      reveal: {
        FloatingControlBarManager.shared.show()
        log("PushToTalkManager: revealed the bar for this press — starting the turn")
      },
      start: { self.handleShortcutDown() })
  }

  private func handleShortcutDown() {
    let now = ProcessInfo.processInfo.systemUptime

    switch phase {
    case .idle, .awaitingResponse, .awaitingTools, .awaitingJournal, .playing, .terminal, .none:
      // Check for double-tap: if last Option-up was recent, enter locked mode
      // A first tap can arrive either as a completed turn (`lastOptionUpTime`) or, on a
      // modifier-only key, as a quick tap that never started one. Either counts, so a
      // double tap locks even when the two taps differ in speed.
      let recentFirstTap = max(lastOptionUpTime, lastModifierQuickTapTime)
      if ShortcutSettings.shared.doubleTapForLock && (now - recentFirstTap) < doubleTapThreshold {
        lastOptionUpTime = 0
        lastModifierQuickTapTime = 0
        enterLockedListening()
      } else {
        lastOptionDownTime = now
        startListening()
      }

    case .recording:
      // Already listening (hold mode), ignore repeated flagsChanged
      break

    case .pendingLockDecision:
      stopListening(endInterjectHold: false)
      enterLockedListening()

    case .lockedRecording:
      // Tap while locked → finalize
      finalize()

    case .finalizing:
      break
    }
  }

  private func handleShortcutUp() {
    let now = ProcessInfo.processInfo.systemUptime

    switch phase {
    case .recording:
      let holdDuration = now - lastOptionDownTime
      // The key is up: latch the hold here, not at finalization. Finalization can
      // be a whole `lockDecision` window (0.4 s) later on the tap-to-lock path —
      // which is on by default — and a second or more later on a cold realtime
      // hub. Either wait would otherwise be counted as part of the user's press,
      // and every sub-220 ms tap would be reported as a capture failure.
      //
      // The modifier-only chord starts its attempt `modifierOnlyShortcutActivationDelay`
      // after the physical key-down, so the hold under-reports by that much. That
      // is the safe direction: it can only turn a capture failure into "hold
      // longer", never the reverse, so it cannot contaminate the
      // `capture_never_operational` measurement.
      pttLifecycle.noteRelease()

      if ShortcutSettings.shared.doubleTapForLock && holdDuration < Self.tapToLockMaxHoldDuration {
        lastOptionUpTime = now
        lastModifierQuickTapTime = 0
        enterPendingLockDecision()
      } else {
        lastOptionUpTime = 0
        // Long hold released — finalize immediately
        finalize()
      }

    case .pendingLockDecision:
      break

    case .lockedRecording:
      // In locked mode, Option-up is ignored (we finalize on next Option-down)
      break

    case .idle, .finalizing, .awaitingResponse, .awaitingTools, .awaitingJournal, .playing,
      .terminal, .none:
      break
    }
  }

  // MARK: - Listening Lifecycle

  /// True iff the user is on the Omi account (not BYOK) and has hit the monthly free-tier
  /// chat-question limit. PTT turns count toward that limit (desktop_chat_realtime), so they
  /// must be gated by it too — same as typed chat (ChatProvider / floating bar). Without this,
  /// a free user over 30 questions could keep talking for free. Posts the same usage-limit
  /// popup and returns true so the caller early-returns.
  private func isBlockedByUsageLimit() -> Bool {
    guard isPushToTalkUsageLimitBlocked else { return false }
    log("PushToTalkManager: PTT blocked — monthly free-tier chat limit reached")
    NotificationCenter.default.post(
      name: .showUsageLimitPopup, object: nil, userInfo: ["reason": "ptt"])
    return true
  }

  private func startListening() {
    guard Self.admitsListeningStart(activeTurnID: currentVoiceTurnID, phase: phase) else {
      log("PushToTalkManager: startListening ignored — phase=\(String(describing: phase))")
      return
    }
    if isBlockedByUsageLimit() { return }
    _ = voiceTurnCoordinator.begin(intent: .hold)
    RealtimeHubController.shared.prefetchVoiceContextSnapshotIfNeeded()
    warmPTTInputRouting()
    // Reset the overflow flag under the buffer lock so it's atomic w.r.t. the
    // audio thread's appendBatchAudioBounded (fresh turn → allow the warning again).
    batchAudioLock.lock()
    batchAudioOverflowSignaled = false
    batchAudioLock.unlock()
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
    if ShortcutSettings.shared.pttMuteSystemAudio {
      SystemAudioMuteController.shared.muteForListening()
    }
    startActiveTracer()
    isCurrentSessionFollowUp = barState?.showingAIResponse == true
    transcriptSegments = []
    seenFinalSegmentIDs.removeAll()
    lastInterimText = ""
    voiceTypeSession.begin()
    resetVoiceTypingSources()
    voiceTypingLastOutcome = VoiceTypingOutcome()
    currentContextSnapshot = nil

    // Play start-of-PTT sound
    if ShortcutSettings.shared.pttSoundsEnabled {
      let sound = NSSound(named: "Funk")
      sound?.volume = 0.3
      sound?.play()
    }

    let mode = currentPTTMode()
    AnalyticsManager.shared.floatingBarPTTStarted(mode: mode)
    DesktopDiagnosticsManager.shared.recordPTTStarted(
      mode: mode,
      hubActive: RealtimeHubController.shared.isTransportReady,
      micPermissionGranted: refreshedMicPermission())
    pttLifecycle.beginAttempt(
      mode: mode,
      hubActive: RealtimeHubController.shared.isTransportReady,
      micPermissionGranted: refreshedMicPermission())
    let preOverlayImage = captureTurnScreenEvidence()
    updateBarState()
    FloatingControlBarManager.shared.interjectPushToTalkDidStart()

    captureContextAndStartAudio(preOverlayImage: preOverlayImage)
    log("PushToTalkManager: started listening (mode=\(mode))")
  }

  func enterLockedListening() {
    if isBlockedByUsageLimit() { return }
    RealtimeHubController.shared.prefetchVoiceContextSnapshotIfNeeded()
    warmPTTInputRouting()
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
    if ShortcutSettings.shared.pttMuteSystemAudio {
      SystemAudioMuteController.shared.muteForListening()
    }
    if let turnID = currentVoiceTurnID, Self.locksExistingTurn(phase: phase),
      voiceTurnCoordinator.activeTurnID == turnID
    {
      voiceTurnCoordinator.publish(.lock(turnID: turnID))
    } else {
      _ = voiceTurnCoordinator.begin(intent: .locked)
    }
    isCurrentSessionFollowUp = barState?.showingAIResponse == true

    // Play start-of-PTT sound for locked mode
    if ShortcutSettings.shared.pttSoundsEnabled {
      let sound = NSSound(named: "Funk")
      sound?.volume = 0.3
      sound?.play()
    }

    let mode = currentPTTMode()
    AnalyticsManager.shared.floatingBarPTTStarted(mode: mode)
    DesktopDiagnosticsManager.shared.recordPTTStarted(
      mode: mode,
      hubActive: RealtimeHubController.shared.isTransportReady,
      micPermissionGranted: refreshedMicPermission())
    pttLifecycle.beginAttempt(
      mode: mode,
      hubActive: RealtimeHubController.shared.isTransportReady,
      micPermissionGranted: refreshedMicPermission())

    // If we were already listening from the first tap, keep going.
    // Otherwise start fresh.
    if transcriptionService == nil {
      if activeTracer == nil { startActiveTracer() }
      transcriptSegments = []
      seenFinalSegmentIDs.removeAll()
      lastInterimText = ""
      voiceTypeSession.begin()
      resetVoiceTypingSources()
      voiceTypingLastOutcome = VoiceTypingOutcome()
      currentContextSnapshot = nil
      let preOverlayImage = captureTurnScreenEvidence()
      captureContextAndStartAudio(preOverlayImage: preOverlayImage)
    }

    updateBarState()
    FloatingControlBarManager.shared.interjectPushToTalkDidStart()
    log("PushToTalkManager: entered locked listening mode (mode=\(mode))")
  }

  private func enterPendingLockDecision() {
    guard phase == .recording else { return }
    guard let turnID = currentVoiceTurnID else { return }
    voiceTurnCoordinator.publish(.openLockWindow(turnID: turnID))
    stopMicCapture()
    updateBarState()
  }

  private func stopListening(endInterjectHold: Bool = true) {
    if endInterjectHold {
      FloatingControlBarManager.shared.interjectPushToTalkDidCancel()
    }
    if let turnID = currentVoiceTurnID,
      voiceTurnCoordinator.activeTurnID == turnID
    {
      voiceTurnCoordinator.publish(.cancel(turnID: turnID, reason: .cancelled))
      return
    }
    performTerminalCleanup()
  }

  /// Benign turn endings keep the warm capture parked for the keep-alive reuse
  /// window — success, too-short, silent-rejected, and barge-in all make an
  /// immediate follow-up turn likely. Cancellations, owner changes, and every
  /// failure fully release the microphone: an explicitly ended or unhealthy
  /// session must never leave it open.
  ///
  /// `captureNotReady` is in the keep list precisely because it is the retry:
  /// the capture that missed the press is running by the time the turn ends, and
  /// parking it is what makes the "hold again" the hint asks for actually work.
  static func terminalReasonKeepsWarmCapture(_ reason: VoiceTurnTerminalReason) -> Bool {
    switch reason {
    case .success, .tooShort, .silentRejected, .interruptedByBargeIn, .captureNotReady:
      return true
    default:
      return false
    }
  }

  private func performTerminalCleanup(discardBufferedAudio: Bool = false, parkWarm: Bool = false) {
    // Always restore audio on teardown (cancel, error, cleanup) so we never leave it muted.
    SystemAudioMuteController.shared.restore()
    contextCaptureTask?.cancel()
    contextCaptureTask = nil
    micCaptureStartInFlight = false
    stopAudioTranscription(discardBufferedAudio: discardBufferedAudio, parkWarm: parkWarm)
    // A dictation is delivered before its turn terminates, so there is nothing
    // in flight to protect here: a terminal that arrives mid-pipeline (owner
    // change, explicit cancel) is exactly the case where nothing may be pasted.
    voiceTypeSession.abandon()
    resetVoiceTypingSources()
    transcriptSegments = []
    seenFinalSegmentIDs.removeAll()
    lastInterimText = ""
    currentContextSnapshot = nil
    batchAudioLock.lock()
    batchAudioBuffer = Data()
    batchAudioLock.unlock()
    isCurrentSessionFollowUp = false
    // Abandoned session (cancel / silent turn) — drop its tracer unsent so it
    // doesn't leak into the next PTT turn. No trace is written for these.
    activeTracer = nil
    automationCaptureBypass = false
    automationExercisesRealtimePath = false
  }

  /// Drain every previous-owner voice authority before the defaults/auth owner
  /// mutation becomes visible. Logical termination enters through the reducer;
  /// the remaining calls close idle/warm physical resources that have no active
  /// turn and therefore cannot be represented by a reducer effect.
  func quiesceForEffectiveOwnerTransition(
    previousOwnerID: String?,
    cleanupCapability: RuntimeOwnerTransitionCleanupCapability
  ) async {
    guard
      RuntimeOwnerIdentity.authorizesTransitionCleanup(
        cleanupCapability,
        previousOwnerID: previousOwnerID)
    else {
      assertionFailure("Push-to-talk owner cleanup capability mismatched")
      return
    }
    let captureBeingStopped = audioCaptureService
    _ = voiceTurnCoordinator.terminateForEffectiveOwnerTransition(
      previousOwnerID: previousOwnerID)
    // Setup is intentionally lazy. If no effect handler was installed, there
    // cannot be a legitimate active capture, but fail closed and clear every
    // driver anyway.
    performTerminalCleanup(discardBufferedAudio: true)
    FloatingBarVoicePlaybackService.shared.stop()
    await captureBeingStopped?.waitForPhysicalStop()
    // A warm capture opened for the previous owner must not still be starting
    // when the defaults/auth mutation becomes visible. A longer bound than the
    // press path — this is fencing, not latency — but still bounded: see
    // `drainInFlightWarmCapture`.
    await drainInFlightWarmCapture(timeout: Self.ownerTransitionWarmCaptureWaitSeconds)
    await RealtimeHubController.shared.quiesceForEffectiveOwnerTransition(
      previousOwnerID: previousOwnerID,
      cleanupCapability: cleanupCapability)
  }

  #if DEBUG
    var ownerBoundarySnapshot: PTTOwnerBoundarySnapshot {
      PTTOwnerBoundarySnapshot(
        activeTurnID: currentVoiceTurnID,
        hasCaptureDriver: audioCaptureService != nil,
        captureStartInFlight: micCaptureStartInFlight,
        hasTranscriptionDriver: transcriptionService != nil,
        hasOmniDriver: realtimeOmniService != nil,
        captureGeneration: micCaptureGeneration)
    }

  #endif

  /// Cancel PTT without sending — used when conversation is closed mid-PTT.
  func cancelListening() {
    guard !isIdle else { return }
    log("PushToTalkManager: cancelling listening")
    stopListening()
  }

  // MARK: - Automation (headless PTT for the desktop bridge)

  private func ensureAutomationBarConfigured() {
    if barState == nil {
      let state = FloatingControlBarState()
      automationBarState = state
      barState = state
      configureVoiceTurnCoordinator(barState: state)
    }
  }

  /// Begin a push-to-talk capture exactly as the shortcut key-down does
  /// (`handleShortcutDown` → `startListening`), so the automation bridge can drive
  /// MIC-01 without synthetic key events. `startListening()`'s own guard makes this a
  /// no-op when PTT is busy; the returned state lets the caller confirm. Pairs with
  /// `endPushToTalkForAutomation()`.
  @discardableResult
  func beginPushToTalkForAutomation() -> [String: String] {
    ensureAutomationBarConfigured()
    automationCaptureBypass = true
    automationExercisesRealtimePath = false
    startListening()
    let isRecording = voiceTurnCoordinator.activeTurn?.phase.isRecording == true
    if !isRecording { automationCaptureBypass = false }
    return ["state": VoiceTurnCoordinator.phaseLabel(phase ?? .idle), "listening": isRecording ? "true" : "false"]
  }

  /// Starts the manager's actual realtime admission path without opening a
  /// physical microphone. Pair with `injectRealtimePTTAutomationAudio(_:)`
  /// and `endPushToTalkForAutomation()` to exercise routing, warm buffering,
  /// and controller replay through the same public PTT lifecycle used by a
  /// shortcut hold.
  @discardableResult
  func beginRealtimePushToTalkForAutomation() -> [String: String] {
    ensureAutomationBarConfigured()
    automationCaptureBypass = true
    automationExercisesRealtimePath = true
    let admission = RealtimeHubController.shared.pttAdmission
    startListening()
    let isRecording = voiceTurnCoordinator.activeTurn?.phase.isRecording == true
    if !isRecording {
      automationCaptureBypass = false
      automationExercisesRealtimePath = false
    }
    return [
      "state": VoiceTurnCoordinator.phaseLabel(phase ?? .idle),
      "listening": isRecording ? "true" : "false",
      "admission": admission == .immediate ? "immediate" : "capture_and_buffer",
    ]
  }

  /// Injects raw 16kHz PCM into the active manager route through the same
  /// per-chunk path as `AudioCaptureService`'s production callback — hub feed,
  /// warm buffering, and the voice-typing pipeline included — kept behind the
  /// non-production automation bridge so tests never depend on microphone
  /// permission or device routing.
  @discardableResult
  func injectRealtimePTTAutomationAudio(_ pcm16k: Data) -> Bool {
    guard automationCaptureBypass,
      automationExercisesRealtimePath,
      !pcm16k.isEmpty,
      let turnID = currentVoiceTurnID,
      phase?.isRecording == true
    else { return false }
    // Every route a physical hold can land on, including the omni/batch
    // fallbacks the reducer picks when the hub is not warm, so a harness hold
    // follows the same routing a real one does.
    guard
      isHubMode || isWaitingForHub || isOnDeviceASR || isOmniSTT || voiceTypeSession.claimsTurn
        || ShortcutSettings.shared.effectivePTTTranscriptionMode == .batch
    else { return false }
    ingestMicChunk(
      pcm16k,
      generation: micCaptureGeneration,
      turnID: turnID,
      batchMode: ShortcutSettings.shared.effectivePTTTranscriptionMode == .batch)
    return true
  }

  /// Harness-visible state of the voice-typing pipeline for the current or
  /// most recent turn. Bounded scalars only.
  func voiceTypingAutomationDiagnostics() -> [String: String] {
    [
      "voice_typing_claimed": voiceTypeSession.claimsTurn ? "true" : "false",
      "voice_typing_delivery": voiceTypingLastOutcome.delivery,
      "voice_typing_typed_chars": "\(voiceTypingLastOutcome.characters)",
      "voice_typing_transcriber": voiceTypingLastOutcome.transcriber,
      "voice_typing_polished": voiceTypingLastOutcome.polished ? "true" : "false",
      "voice_typing_probes": "\(voiceTypingLastOutcome.probes)",
      "voice_typing_hub_released": voiceTypingLastOutcome.hubReleased ? "true" : "false",
    ]
  }

  /// Release an in-progress push-to-talk capture the same way a long-hold key-up does
  /// (`handleShortcutUp` .listening branch → `finalize`), producing the final
  /// transcript. Releasing with no captured audio exercises the empty-batch path,
  /// which must end the turn with a hint rather than hang. No-op unless a capture is
  /// active.
  @discardableResult
  /// Mirrors one *quick tap* of a modifier-only shortcut: the release lands inside
  /// `modifierOnlyShortcutActivationDelay`, so no turn starts. Two of these inside the
  /// double-tap window must lock, which is what the physical key does and what no other
  /// automation entry point can express (`ptt_stop` mirrors a long-hold release).
  func quickTapPushToTalkForAutomation() -> [String: String] {
    ensureAutomationBarConfigured()
    handleModifierOnlyQuickTap()
    return [
      "state": VoiceTurnCoordinator.phaseLabel(phase ?? .idle),
      "locked": phase == .lockedRecording ? "true" : "false",
    ]
  }

  func endPushToTalkForAutomation() -> [String: String] {
    let wasActive = voiceTurnCoordinator.activeTurn?.phase.isRecording == true
    if wasActive { finalize() }
    return ["state": VoiceTurnCoordinator.phaseLabel(phase ?? .idle), "finalized": wasActive ? "true" : "false"]
  }

  private var finalizedMode: String = "hold"

  private func currentPTTMode() -> String {
    let baseMode = phase == .lockedRecording ? "locked" : "hold"
    return isCurrentSessionFollowUp ? "follow_up_\(baseMode)" : baseMode
  }

  private func refreshedMicPermission() -> Bool {
    hasMicPermission = AudioCaptureService.checkPermission()
    return hasMicPermission
  }

  // MARK: - QueryTracer

  /// Tracer for the current PTT session. Created when recording starts and
  /// handed off to the floating-bar query (via QueryTracerContext) in sendQuery,
  /// so a single trace spans recording → transcription → LLM → playback.
  private var activeTracer: QueryTracer?

  private func startActiveTracer() {
    // The floating bar's STT is always the realtime omni model (startOmniTranscription
    // is unconditional; Deepgram batch/live is only an on-failure fallback), so label
    // the turn accordingly rather than by the legacy pttTranscriptionMode preference.
    let tracer = QueryTracer(query: "(ptt recording)", inputMode: .voicePTTOmni)
    activeTracer = tracer
    tracer.begin("ptt_recording")
  }

  /// Minimum total / voiced audio a PTT turn needs before we trust STT with it.
  /// STT models hallucinate short phrases (often in random languages, e.g.
  /// "¿Qué es el número de cuenta?") when given silence instead of returning
  /// empty — so silent turns must be dropped before transcription, not after.
  nonisolated static let minTurnAudioSeconds: Double = 0.35
  nonisolated private static let minVoicedSeconds: Double = 0.2
  /// RMS threshold (int16 samples) above which a 20ms frame counts as voiced.
  /// ~-41 dBFS: comfortably above quiet-room mic noise, far below soft speech.
  nonisolated private static let voicedRMSThreshold: Double = 300
  // Hub admission is stricter than raw energy: realtime models will answer noise
  // if we commit a no-speech turn. Strong speech-like frames pass immediately,
  // while Silero remains available as a quiet-speech fallback.
  nonisolated private static let hubSpeechLikeRMSThreshold: Double = 260
  nonisolated private static let hubMaxSpeechZeroCrossingRate: Double = 0.24
  nonisolated private static let hubMinTurnAudioSeconds: Double = 0.35
  nonisolated private static let hubMinSpeechLikeSeconds: Double = 0.16
  nonisolated private static let hubShortTurnMaxAudioSeconds: Double = 0.75
  nonisolated private static let hubShortTurnMinSpeechLikeSeconds: Double = 0.22
  nonisolated private static let hubShortTurnMinSpeechLikeRatio: Double = 0.45

  /// Returns (totalSeconds, voicedSeconds) for raw PCM16 mono 16kHz audio,
  /// where voiced = 20ms frames whose RMS exceeds `rmsThreshold`.
  static func voicedAudioSeconds(pcm16k data: Data, rmsThreshold: Double = voicedRMSThreshold) -> (
    total: Double, voiced: Double
  ) {
    let sampleCount = data.count / 2
    guard sampleCount > 0 else { return (0, 0) }
    let frameSamples = 320  // 20ms at 16kHz
    var voicedFrames = 0
    var totalFrames = 0
    data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
      let samples = raw.bindMemory(to: Int16.self)
      var i = 0
      while i + frameSamples <= sampleCount {
        var sumSquares: Double = 0
        for j in i..<(i + frameSamples) {
          let s = Double(samples[j])
          sumSquares += s * s
        }
        let rms = (sumSquares / Double(frameSamples)).squareRoot()
        if rms > rmsThreshold { voicedFrames += 1 }
        totalFrames += 1
        i += frameSamples
      }
    }
    return (Double(sampleCount) / 16000.0, Double(voicedFrames) * 0.02)
  }

  /// Returns (totalSeconds, speechLikeSeconds) for PCM16 mono 16kHz audio.
  /// A frame must have enough RMS and a plausible voiced-speech zero-crossing
  /// rate. This rejects broadband white noise that clears a simple energy gate.
  static func speechLikeAudioSeconds(
    pcm16k data: Data,
    rmsThreshold: Double = hubSpeechLikeRMSThreshold,
    maxZeroCrossingRate: Double = hubMaxSpeechZeroCrossingRate
  ) -> (total: Double, speechLike: Double) {
    let sampleCount = data.count / 2
    guard sampleCount > 0 else { return (0, 0) }
    let frameSamples = 320  // 20ms at 16kHz
    var speechLikeFrames = 0
    data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
      let samples = raw.bindMemory(to: Int16.self)
      var i = 0
      while i + frameSamples <= sampleCount {
        var sumSquares: Double = 0
        var zeroCrossings = 0
        var previous = Int(samples[i])
        for j in i..<(i + frameSamples) {
          let current = Int(samples[j])
          let s = Double(current)
          sumSquares += s * s
          if j > i, (previous < 0 && current >= 0) || (previous >= 0 && current < 0) {
            zeroCrossings += 1
          }
          previous = current
        }
        let rms = (sumSquares / Double(frameSamples)).squareRoot()
        let zcr = Double(zeroCrossings) / Double(frameSamples - 1)
        if rms > rmsThreshold && zcr <= maxZeroCrossingRate {
          speechLikeFrames += 1
        }
        i += frameSamples
      }
    }
    return (Double(sampleCount) / 16000.0, Double(speechLikeFrames) * 0.02)
  }

  // Real speech detector for the hub gate (Silero VAD, on-device). Energy ≠ speech:
  // a cough/click/keyboard clack is loud but not speech, and a too-loose amplitude
  // gate lets those through (model answers a non-question) while a too-tight one
  // drops real speech. Silero classifies speech directly — the same client-side
  // pre-commit decision Clicky makes (speech → commit; else → input_audio_buffer.clear).
  private static let hubVAD: SileroVADModel? = SileroVADModel()

  /// True when the turn contains sustained real speech. Falls back to the amplitude
  /// gate if the VAD model isn't available (ONNX missing) so we never silently drop
  /// every turn.
  /// Peak (0–32767) and mean RMS of a PCM16 buffer — used to log WHY a turn was
  /// dropped: peak≈0 → mic returned silence (dead capture); high peak + gate-fail →
  /// classifier misfire; low-but-nonzero → genuinely quiet/far mic.
  static func audioEnergy(pcm16k data: Data) -> (peak: Int, rms: Int) {
    let n = data.count / 2
    guard n > 0 else { return (0, 0) }
    var peak = 0
    var sumSq = 0.0
    data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
      let s = raw.bindMemory(to: Int16.self)
      for i in 0..<n {
        let v = Int(s[i])
        if abs(v) > peak { peak = abs(v) }
        sumSq += Double(v) * Double(v)
      }
    }
    return (peak, Int((sumSq / Double(n)).squareRoot()))
  }

  static func hubTurnHasSpeech(pcm16k data: Data) -> Bool {
    let count = data.count / 2
    guard Double(count) / 16000.0 >= hubMinTurnAudioSeconds else { return false }  // too short
    // Speech-like energy gate FIRST: clear/audible speech must pass without
    // waiting on model inference, but broadband noise/clicks should not.
    let (total, speechLike) = speechLikeAudioSeconds(pcm16k: data)
    if total < hubShortTurnMaxAudioSeconds {
      let coverage = total > 0 ? speechLike / total : 0
      if speechLike >= hubShortTurnMinSpeechLikeSeconds
        && coverage >= hubShortTurnMinSpeechLikeRatio
      {
        return true
      }
    } else if speechLike >= hubMinSpeechLikeSeconds {
      return true
    }
    // Softer speech that didn't clear the energy bar: a lenient Silero pass as a fallback
    // (only to catch quiet speech — it must never be the sole gate that drops loud speech).
    guard let vad = hubVAD, count >= 512 else { return false }
    var floats = [Float](repeating: 0, count: count)
    data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
      let s = raw.bindMemory(to: Int16.self)
      for i in 0..<count { floats[i] = Float(s[i]) / 32768.0 }
    }
    vad.resetStates()
    var maxRun = 0
    var run = 0
    var speechFrames = 0
    var i = 0
    while i + 512 <= count {
      let p = vad.predict(Array(floats[i..<(i + 512)]))
      if p > 0.4 {
        speechFrames += 1
        run += 1
        maxRun = max(maxRun, run)
      } else {
        run = 0
      }
      i += 512
    }
    // Each Silero frame is 512 samples = 32ms. Short turns need denser evidence so
    // clicks, clipped starts, and half-syllables do not become realtime tool calls.
    if total < hubShortTurnMaxAudioSeconds {
      return maxRun >= 5 || speechFrames >= 8
    }
    return maxRun >= 3 || speechFrames >= 6
  }

  func finalize() {
    FloatingControlBarManager.shared.interjectPushToTalkDidEnd()
    guard phase?.isRecording == true else { return }
    guard let turnID = currentVoiceTurnID else { return }
    voiceTurnCoordinator.publish(.finalize(turnID: turnID))
  }

  /// Start batch STT immediately while the already-frontloaded screen/OCR task
  /// continues in parallel. Context is correction-only and opportunistic: it
  /// may update `currentContextSnapshot` before `sendTranscript`, but a slow or
  /// hung screen capture must never hold the completed transcription hostage.
  /// The manager retains ownership of `contextTask` and cancels it at the normal
  /// turn-cleanup fence; this helper deliberately does not create an orphan
  /// observer or await an unbounded OCR operation.
  @MainActor
  static func runBatchTranscriptionBeforeContext(
    contextTask: Task<Void, Never>?,
    transcribe: @escaping () async throws -> TranscriptionService.BatchTranscriptionResult
  ) async throws -> TranscriptionService.BatchTranscriptionResult {
    _ = contextTask
    return try await transcribe()
  }

  private func continueFinalization() {
    guard let turnID = currentVoiceTurnID,
      voiceTurnCoordinator.activeTurnID == turnID,
      voiceTurnCoordinator.activeTurn?.phase == .finalizing
    else { return }
    lastOptionUpTime = 0
    // Backstop for the endings that do not come from a key-up — locked recording
    // finalized by the next chord press, the mic button, the automation bridge.
    // `noteRelease` is idempotent, so a hold already latched at key-up wins.
    pttLifecycle.noteRelease()
    // Dictation is over — restore any audio we muted so the track resumes immediately.
    SystemAudioMuteController.shared.restore()
    finalizedMode = currentPTTMode()

    // The reducer emitted stopCapture before entering this effect continuation.
    activeTracer?.end("audio_capture")
    activeTracer?.end("ptt_recording")

    // Where a dictation will be pasted is fixed now, at release, on every
    // route: the seconds the recognizer takes must not move the target.
    voiceTypeSession.noteRelease()

    // A dictation closes the same way on every route: the key came up, so the
    // whole turn is transcribed once and pasted, and nothing is asked of any
    // model. Decided before the route branches, because the reducer may have
    // moved the route under a long hold (warm-wait timeout, hub ready) and
    // none of those transitions change what a typing turn does at key-up.
    if voiceTypeSession.claimsTurn {
      activeTracer = nil
      finishVoiceTypingTurn(turnID: turnID, audio: nil, knownTranscript: nil)
      return
    }

    if isWaitingForHub {
      voiceTurnCoordinator.publish(.responseWaitingChanged(turnID: turnID, active: true))
      updateBarState()
      log("PushToTalkManager: finalizing while realtime hub warms — holding buffered audio")
      return
    }

    // Offline: nothing remote will ever transcribe this turn, so it is closed
    // from the on-device decode rather than handed to a provider. Only a
    // dictation can complete; a question ends with no provider to answer it.
    if isOnDeviceASR {
      activeTracer = nil
      finishVoiceTypingTurn(turnID: turnID, audio: nil, knownTranscript: nil)
      return
    }

    // Realtime hub: silence-gate the turn first. An accidental ⌥ tap (or a hold
    // with nothing said) records near-silence — committing it makes the model
    // answer anyway (often a generic "looking at your screen"). Drop those before
    // committing, exactly like the omni/batch paths.
    if isHubMode {
      activeTracer = nil
      batchAudioLock.lock()
      let turnAudio = batchAudioBuffer
      batchAudioBuffer = Data()
      batchAudioLock.unlock()
      let totalSec = Double(turnAudio.count / 2) / 16000.0
      if !Self.hubTurnHasSpeech(pcm16k: turnAudio) {
        let (peak, rms) = Self.audioEnergy(pcm16k: turnAudio)
        let dev = audioCaptureService?.currentDeviceDescription ?? "?"
        let resolution = resolveDiscardedTurn(totalSec: totalSec)
        let recoveryDecision = silentMicRecoveryPolicy.recordDiscardedTurn(
          holdSec: judgeableHoldSeconds ?? totalSec, totalSec: totalSec, peak: peak)
        recordSilentMicRecoveryOutcome(recoveryDecision.recoveryOutcome)
        DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
          source: "hub",
          mode: finalizedMode,
          audioSeconds: totalSec,
          voicedSeconds: nil,
          peak: peak,
          rms: rms,
          deviceDescription: dev,
          micPermissionGranted: hasMicPermission,
          hubActive: true,
          recoveryAction: recoveryDecision.shouldRebuildCapture ? "capture_rebuild" : "none",
          recoveryResult: recoveryDecision.shouldRebuildCapture ? "attempted" : "not_attempted")
        if recoveryDecision.shouldRebuildCapture {
          // Record the recovery trigger before terminate so the snapshot carries
          // recovery_triggered=true and the correlation id. Without this, the
          // triggering turn's snapshot is emitted with recovery_triggered=false
          // and the next-turn recovery outcome cannot be joined back.
          pttLifecycle.recoveryTriggered(action: .captureRebuild)
        }
        pttLifecycle.terminate(
          disposition: resolution.disposition,
          source: "hub",
          peak: peak,
          rms: rms,
          turnAudioSeconds: totalSec,
          voicedAudioSeconds: nil,
          judgeable: resolution.judgeable,
          captureStartedLate: resolution.captureStartedLate)
        log(
          "PushToTalkManager: discarding hub turn — audio \(String(format: "%.2f", totalSec))s "
            + "peak=\(peak)/32767 rms=\(rms) device=[\(dev)] "
            + "(peak≈0 ⇒ dead mic; high peak ⇒ classifier misfire; low ⇒ quiet/far mic) — not committing"
        )
        if recoveryDecision.shouldRebuildCapture {
          requestCoreAudioCaptureRecovery(
            reason: "repeated dead-mic PTT turns", restartPTT: false, batchMode: false, recoveryAlreadyTriggered: true)
        }
        _ = RealtimeHubController.shared.cancelTurn(turnID: turnID)
        AnalyticsManager.shared.floatingBarPTTEnded(
          mode: finalizedMode, committed: false, transcriptLength: nil)
        // Too short to have captured anything (fast tap / capture not ready) — hint
        // the user to hold longer instead of clearing silently. A longer hub turn
        // that simply had no speech keeps the quiet reset.
        switch resolution.judgement {
        case .shortTap:
          finishTooShortPTTTurnWithHint(reason: "hub, \(String(format: "%.2f", totalSec))s")
        case .captureStartedLate:
          finishCaptureNotReadyPTTTurn(reason: "hub, \(String(format: "%.2f", totalSec))s")
        case .audioJudgeable:
          voiceTurnCoordinator.publish(.finish(turnID: turnID, reason: .silentRejected))
        }
        return
      }
      // The probes are advisory and can lose the wake word — observed live:
      // "type what is on my calendar tomorrow" decoded without its first word,
      // so the turn was committed and the model spawned an agent to do the
      // typing itself. Decide from the turn's opening before letting the model
      // act on it.
      gateHubCommitOnFinalDictationCheck(turnID: turnID, turnAudio: turnAudio) { [weak self] in
        self?.commitHubTurn(turnID: turnID, turnAudio: turnAudio, totalSec: totalSec)
      }
      return
    }

    // Silence gate — an accidental tap (or a hold with nothing said) records
    // near-silence. Drop the turn here instead of letting STT hallucinate a
    // phrase from it. Applies to the omni and batch paths, which retain the
    // raw turn audio; live-Deepgram streams without buffering and already
    // returns empty on silence.
    let isBatch = ShortcutSettings.shared.effectivePTTTranscriptionMode == .batch
    if isOmniSTT || isBatch {
      batchAudioLock.lock()
      let turnAudio = batchAudioBuffer
      batchAudioLock.unlock()
      let (totalSec, voicedSec) = Self.voicedAudioSeconds(pcm16k: turnAudio)
      if totalSec < Self.minTurnAudioSeconds || voicedSec < Self.minVoicedSeconds {
        let (peak, rms) = Self.audioEnergy(pcm16k: turnAudio)
        let resolution = resolveDiscardedTurn(totalSec: totalSec)
        // A dead mic (peak≈0 for a real hold) leaves omni/batch users stuck on
        // repeated silent turns with no recovery. Mirror the hub path: rebuild the
        // CoreAudio capture after consecutive dead-mic turns.
        let recoveryDecision = silentMicRecoveryPolicy.recordDiscardedTurn(
          holdSec: judgeableHoldSeconds ?? totalSec, totalSec: totalSec, peak: peak)
        recordSilentMicRecoveryOutcome(recoveryDecision.recoveryOutcome)
        DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
          source: isOmniSTT ? "omni_stt" : "batch_stt",
          mode: finalizedMode,
          audioSeconds: totalSec,
          voicedSeconds: voicedSec,
          peak: peak,
          rms: rms,
          deviceDescription: audioCaptureService?.currentDeviceDescription,
          micPermissionGranted: hasMicPermission,
          hubActive: false,
          recoveryAction: recoveryDecision.shouldRebuildCapture ? "capture_rebuild" : "none",
          recoveryResult: recoveryDecision.shouldRebuildCapture ? "attempted" : "not_attempted")
        pttLifecycle.terminate(
          disposition: resolution.disposition,
          source: isOmniSTT ? "omni_stt" : "batch_stt",
          peak: peak,
          rms: rms,
          turnAudioSeconds: totalSec,
          voicedAudioSeconds: voicedSec,
          judgeable: resolution.judgeable,
          captureStartedLate: resolution.captureStartedLate)
        log(
          "PushToTalkManager: discarding silent turn (audio \(String(format: "%.2f", totalSec))s, voiced \(String(format: "%.2f", voicedSec))s) — not transcribing"
        )
        AnalyticsManager.shared.floatingBarPTTEnded(
          mode: finalizedMode, committed: false, transcriptLength: nil)
        if recoveryDecision.shouldRebuildCapture {
          requestCoreAudioCaptureRecovery(reason: "repeated dead-mic PTT turns", restartPTT: false, batchMode: isBatch)
        }
        // A too-short turn means the release beat capture (or the user tapped
        // instead of holding). Give visible feedback instead of a silent clear;
        // longer holds that were merely quiet keep the quiet reset.
        switch resolution.judgement {
        case .shortTap:
          finishTooShortPTTTurnWithHint(
            reason: "\(isOmniSTT ? "omni" : "batch"), \(String(format: "%.2f", totalSec))s")
        case .captureStartedLate:
          finishCaptureNotReadyPTTTurn(
            reason: "\(isOmniSTT ? "omni" : "batch"), \(String(format: "%.2f", totalSec))s")
        case .audioJudgeable:
          stopListening()
        }
        return
      }
    }

    // Past the silence gate — a real turn will be transcribed and answered. Show
    // the "thinking" indicator through the transcription/first-token gap; it hands
    // off to the conversation surface (or voice glow) the moment output arrives.
    recordSilentMicRecoveryOutcome(silentMicRecoveryPolicy.recordSuccessfulTurn())
    voiceTurnCoordinator.publish(.transcriptionStarted(turnID: turnID))

    // Realtime omni: commit the turn and wait for the final transcript.
    if isOmniSTT {
      // The relay already died this turn (omniDidError nilled it) — don't wait on a dead
      // socket; transcribe the buffered turn audio through routed batch STT now so PTT still answers.
      if realtimeOmniService == nil {
        log("PushToTalkManager: omni relay unavailable — transcribing turn through backend batch STT")
        fallBackToBatchTranscription(reason: "other")
        return
      }
      // QueryTracer: the omni provider's post-commit finalization (VAD close +
      // final STT inference + round-trip) — closed at the top of sendTranscript().
      activeTracer?.begin(
        "omni_transcribe", metadata: ["provider": RealtimeOmniSettings.shared.effectiveProvider.displayName])
      realtimeOmniService?.commitInputTurn()
      log("PushToTalkManager: finalizing (omni STT) — waiting for final transcript")
      voiceTurnCoordinator.publish(
        .transcriptionFinalizationStarted(turnID: turnID, mode: .omni))
      return
    }

    let isBatchMode = ShortcutSettings.shared.effectivePTTTranscriptionMode == .batch

    if isBatchMode {
      // Batch mode: send accumulated audio to pre-recorded API
      log("PushToTalkManager: finalizing (batch) — mic stopped, transcribing recorded audio")
      batchAudioLock.lock()
      let audioData = batchAudioBuffer
      batchAudioBuffer = Data()
      batchAudioLock.unlock()

      // Stop streaming service (was not used in batch mode, but clean up)
      stopAudioTranscription()

      guard !audioData.isEmpty else {
        // Backstop: the silence gate above normally catches an empty turn first, but
        // if a turn ever reaches here with no audio, hint rather than send nothing.
        // A zero-byte buffer behind a real hold is a capture that never delivered,
        // so it takes the same judgement as every other discard path.
        let resolution = resolveDiscardedTurn(totalSec: 0)
        if resolution.captureStartedLate {
          finishCaptureNotReadyPTTTurn(reason: "batch, empty buffer")
          return
        }
        finishTooShortPTTTurnWithHint(reason: "batch, empty buffer")
        return
      }

      voiceTurnCoordinator.publish(.transcriptChanged(turnID: turnID, text: VoiceTurnUICopy.transcribingProgress))

      Task {
        do {
          guard self.voiceTurnCoordinator.activeTurnID == turnID else { return }
          let language = AssistantSettings.shared.effectiveTranscriptionLanguage
          let audioSeconds = Double(audioData.count) / (16000.0 * 2.0)
          log(
            "PushToTalkManager: batch audio \(audioData.count) bytes (\(String(format: "%.1f", audioSeconds))s), pttLanguage=\(language), selectedLanguage=\(AssistantSettings.shared.transcriptionLanguage), autoDetect=\(AssistantSettings.shared.transcriptionAutoDetect)"
          )

          self.activeTracer?.begin("batch_transcribe", metadata: ["method": "TranscriptionService.batchTranscribe"])
          var batchResult = try await Self.runBatchTranscriptionBeforeContext(
            contextTask: self.contextCaptureTask
          ) {
            try await TranscriptionService.batchTranscribe(
              audioData: audioData,
              language: language,
              contextKeywords: self.currentContextSnapshot?.keywords ?? []
            )
          }
          guard self.voiceTurnCoordinator.activeTurnID == turnID else { return }

          if (batchResult.transcript == nil || batchResult.transcript?.isEmpty == true)
            && language != "en" && language != "multi" && audioSeconds < 5.0
          {
            log("PushToTalkManager: selected language returned empty on short audio, retrying with 'en'")
            batchResult = try await TranscriptionService.batchTranscribe(
              audioData: audioData,
              language: "en",
              contextKeywords: self.currentContextSnapshot?.keywords ?? []
            )
            guard self.voiceTurnCoordinator.activeTurnID == turnID else { return }
          }
          self.activeTracer?.end("batch_transcribe")
          log(
            "PushToTalkManager: batch STT selected provider=\(batchResult.provider ?? "unknown") "
              + "model=\(batchResult.model ?? "unknown")")

          if let transcript = batchResult.transcript, !transcript.isEmpty {
            self.transcriptSegments = [transcript]
          } else {
            log("PushToTalkManager: transcription returned empty after retry")
          }
        } catch {
          logError("PushToTalkManager: batch transcription failed", error: error)
          let (batchPeak, batchRMS) = Self.audioEnergy(pcm16k: audioData)
          self.pttLifecycle.terminate(
            disposition: .committed,
            source: "batch_stt",
            peak: batchPeak,
            rms: batchRMS,
            turnAudioSeconds: Double(audioData.count / 2) / 16000.0,
            voicedAudioSeconds: nil,
            judgeable: true)
          self.voiceTurnCoordinator.publish(
            .transcriptionFailed(turnID: turnID, message: error.localizedDescription))
          return
        }
        self.sendTranscript(turnID: turnID)
      }
    } else {
      // Live mode: flush remaining audio and wait for final transcript from Deepgram
      transcriptionService?.finishStream()
      log("PushToTalkManager: finalizing (live) — mic stopped, waiting for final transcript")
      voiceTurnCoordinator.publish(
        .transcriptionFinalizationStarted(turnID: turnID, mode: .live))
    }
  }

  /// A PTT turn that ended too short to have captured usable audio — typically a
  /// press+release faster than capture spins up (or a tap instead of a hold). This
  /// happens in every mode (hub / omni / batch), so it is shared across their
  /// discard paths. Surface a hint and reset the bar after a beat instead of
  /// clearing it silently, so the user knows to hold the key longer. Callers have
  /// already logged the discard and reported analytics.
  private func finishTooShortPTTTurnWithHint(reason: String) {
    log("PushToTalkManager: too-short PTT turn (\(reason)) — showing hold-longer hint")
    activeTracer = nil
    guard let turnID = currentVoiceTurnID else { return }
    voiceTurnCoordinator.publish(.finish(turnID: turnID, reason: .tooShort))
  }

  /// A hold long enough to speak into whose capture only became operational near
  /// the end of it. Telling this user to hold longer is wrong — they held for
  /// nearly a second — so say the microphone was not ready, and make the retry
  /// real by warming a capture behind the message.
  private func finishCaptureNotReadyPTTTurn(reason: String) {
    log("PushToTalkManager: capture was not ready for this press (\(reason)) — warming for the retry")
    activeTracer = nil
    if let turnID = currentVoiceTurnID {
      voiceTurnCoordinator.publish(.finish(turnID: turnID, reason: .captureNotReady))
    }
    // After the reducer's terminal effect has run, so this either adopts the
    // capture the turn just parked or opens one the rebuild released.
    schedulePTTCaptureWarmup(trigger: .captureNotReady)
  }

  /// The hold, but only when there was a capture start whose latency could have
  /// eaten it. A turn that never requested one — the automation bridge drives
  /// real PTT turns with the microphone deliberately bypassed — has no latency to
  /// charge, and its "hold" is however long the harness took between two HTTP
  /// calls. Judging that would make a synthetic turn's disposition depend on
  /// localhost round-trip time.
  private var judgeableHoldSeconds: Double? {
    pttLifecycle.captureWasRequested ? pttLifecycle.holdSeconds : nil
  }

  private func resolveDiscardedTurn(totalSec: Double) -> PTTDiscardedTurnResolution {
    PTTDiscardedTurnResolution(
      PTTTurnDiscardJudgement.judge(
        holdSeconds: judgeableHoldSeconds,
        deliveredAudioSeconds: totalSec,
        minTurnAudioSeconds: Self.minTurnAudioSeconds))
  }

  /// Append a mic chunk to the per-turn buffer under the lock, capped at
  /// `maxBatchAudioBytes`. Called from the audio thread. Once the cap is hit the
  /// buffer stops growing (bounded RSS) and the user is warned once; the buffered
  /// (~4.5 min) audio still transcribes normally when the turn is released.
  private func appendBatchAudioBounded(_ audioData: Data, turn: UInt64) {
    batchAudioLock.lock()
    // Append while under the cap (the chunk that reaches it is kept, so the warning
    // fires exactly at the crossing). Set the once-flag atomically under the lock so
    // the warning is enqueued exactly once, not on every subsequent chunk.
    let decision = Self.batchAudioCapDecision(
      bufferedBytes: batchAudioBuffer.count,
      chunkBytes: audioData.count,
      alreadySignaled: batchAudioOverflowSignaled
    )
    if decision.append { batchAudioBuffer.append(audioData) }
    if decision.warn { batchAudioOverflowSignaled = true }
    batchAudioLock.unlock()
    if decision.warn { showBatchAudioOverflowWarning(turn: turn) }
  }

  /// Pure cap decision behind `appendBatchAudioBounded` (MIC-04): should this mic
  /// chunk be appended, and does it cross the cap (warn exactly once)?
  ///
  /// Extracted so the bounding guarantee — RSS stays bounded past ~4.5 min and the
  /// user is warned once, not per chunk — is unit-testable without driving the audio
  /// thread. The live-mic path can't reach this cap from the automation bridge (the
  /// PTT actions drive the realtime hub, not the batch buffer), so this is the
  /// criterion's real test seam. Keep in lockstep with `appendBatchAudioBounded`.
  nonisolated static func batchAudioCapDecision(
    bufferedBytes: Int,
    chunkBytes: Int,
    cap: Int = maxBatchAudioBytes,
    alreadySignaled: Bool
  ) -> (append: Bool, warn: Bool) {
    // At or over the cap the buffer stops growing entirely — bounded RSS.
    guard bufferedBytes < cap else { return (append: false, warn: false) }
    // Under the cap: keep the chunk. If it crosses the cap, warn once.
    let crosses = (bufferedBytes + chunkBytes) >= cap
    return (append: true, warn: crosses && !alreadySignaled)
  }

  /// Surface the one-time "recording too long" warning when the turn buffer is
  /// capped. Hops to main (called from the audio thread) and reuses the rendered
  /// `pttHintText` surface (the legacy `voiceTranscript` error field is unrendered).
  /// `turn` guards against a stale warning painting a *newer* turn if this turn
  /// ended before the block ran. Self-clears after a beat (like the too-short hint)
  /// so it doesn't linger on the bar after the capped turn is submitted.
  private func showBatchAudioOverflowWarning(turn: UInt64) {
    DispatchQueue.main.async { [weak self] in
      guard let self, self.micCaptureGeneration == turn else { return }
      log("PushToTalkManager: turn audio hit \(Self.maxBatchAudioBytes)-byte cap — bounding buffer, warning user")
      if let turnID = self.currentVoiceTurnID {
        self.voiceTurnCoordinator.publish(
          .hintChanged(turnID: turnID, text: "Recording too long — keep it under 5 min"))
      }
    }
  }

  private func sendTranscript(turnID: VoiceTurnID) {
    guard voiceTurnCoordinator.activeTurnID == turnID,
      voiceTurnCoordinator.activeTurn?.phase == .finalizing
    else {
      log("PushToTalkManager: dropping stale transcript completion turn=\(turnID)")
      return
    }
    guard voiceTurnCoordinator.requireCurrentOwner(for: turnID) != nil else {
      log("PushToTalkManager: dropping transcript after authenticated owner changed")
      return
    }
    if voiceTurnCoordinator.activeTurn?.transcriptionFinalizationMode != nil {
      voiceTurnCoordinator.publish(.transcriptionFinalizationCompleted(turnID: turnID))
    }
    // QueryTracer: close the omni finalization span opened in finalize() (no-op on
    // the batch/live fallback paths, which never opened it).
    activeTracer?.end("omni_transcribe")
    stopAudioTranscription()

    // Use final segments if available, fall back to last interim text
    var query = transcriptSegments.joined(separator: " ").trimmingCharacters(
      in: .whitespacesAndNewlines)
    if query.isEmpty {
      query = lastInterimText.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    let contextKeywords = currentContextSnapshot?.keywords ?? []
    // Context improves lexical correction but is no longer needed once this
    // transcript is ready. Cancel any still-running OCR before clearing the
    // snapshot so a late callback cannot repopulate state for this turn or the
    // next one between transcription and terminal cleanup.
    contextCaptureTask?.cancel()
    contextCaptureTask = nil
    if !query.isEmpty {
      query = PTTTranscriptContextualCorrector.correct(query, keywords: contextKeywords)
    }
    let hasQuery = !query.isEmpty
    let wasFollowUp = isCurrentSessionFollowUp
    // "Type <text>" dictates into whatever app owns the caret. Decided here,
    // before the terminal bookkeeping, because a dictation's analytics and
    // lifecycle snapshot are owned by `finishVoiceTypingTurn` — emitting them
    // here too recorded every backend-transcribed dictation twice.
    let dictates = hasQuery && voiceTypeSession.claim(transcript: query)

    if dictates {
      // Bookkeeping deferred to the dictation close.
    } else if hasQuery {
      AnalyticsManager.shared.floatingBarPTTEnded(
        mode: finalizedMode,
        committed: true,
        transcriptLength: query.count
      )
      DesktopDiagnosticsManager.shared.recordPTTCommitted(mode: finalizedMode, hubActive: false)
      pttLifecycle.terminate(
        disposition: .committed,
        source: isOmniSTT ? "omni_stt" : "batch_stt",
        // The turn's PCM was consumed before finalization reached this point, so
        // these are genuinely unknown here rather than zero.
        peak: nil,
        rms: nil,
        turnAudioSeconds: nil,
        voicedAudioSeconds: nil,
        judgeable: true)
    } else {
      AnalyticsManager.shared.floatingBarPTTEnded(mode: finalizedMode, committed: false, transcriptLength: 0)
      // Empty transcript after the turn reached finalization (e.g. a live-Deepgram
      // turn that returned nothing). The recorder's tracked capture state
      // (first-audio / first-usable-frame) classifies it; this resolves any pending
      // recovery exactly once instead of skipping the lifecycle emit.
      pttLifecycle.terminate(
        disposition: .committed,
        source: isOmniSTT ? "omni_stt" : "batch_stt",
        // The turn's PCM was consumed before finalization reached this point, so
        // these are genuinely unknown here rather than zero.
        peak: nil,
        rms: nil,
        turnAudioSeconds: nil,
        voicedAudioSeconds: nil,
        judgeable: true)
    }

    isCurrentSessionFollowUp = false

    transcriptSegments = []
    seenFinalSegmentIDs.removeAll()
    lastInterimText = ""
    currentContextSnapshot = nil

    guard hasQuery else {
      log("PushToTalkManager: no transcript to send")
      voiceTurnCoordinator.publish(.finish(turnID: turnID, reason: .silentRejected))
      return
    }

    voiceTurnCoordinator.publish(.transcriptionFinal(turnID: turnID, text: query))

    // This route's transcript already came from the backend, so it is the one
    // pasted: the turn asks Omi nothing, so no query is dispatched and no
    // response is awaited.
    if dictates {
      log("PushToTalkManager: voice typing consumed turn (\(query.count) chars)")
      finishVoiceTypingTurn(turnID: turnID, audio: nil, knownTranscript: query)
      return
    }

    // Dropped the Gemini ASR-cleanup round-trip (~0.5s on the critical path): the
    // transcript is already locally corrected against screen-OCR keywords above
    // (PTTTranscriptContextualCorrector), and Claude tolerates minor ASR typos.
    // Send straight through (sendTranscript already runs on the main actor).
    activeTracer?.mark("transcript_cleanup")
    sendQuery(query, wasFollowUp: wasFollowUp, turnID: turnID)
  }

  private func sendQuery(_ query: String, wasFollowUp: Bool, turnID: VoiceTurnID) {
    guard voiceTurnCoordinator.requireCurrentOwner(for: turnID) != nil else {
      log("PushToTalkManager: refusing provider dispatch after authenticated owner changed")
      return
    }
    // QueryTracer: hand the PTT tracer to the floating-bar query via TaskLocal so
    // routing, the LLM call, and TTS all record into this same trace. Ownership
    // moves out of activeTracer here; the unstructured Task spawned inside
    // openAIInputWithQuery / sendFollowUpQuery inherits the bound value.
    let tracer = activeTracer
    activeTracer = nil
    let dispatch = {
      if wasFollowUp {
        log("PushToTalkManager: sending follow-up query (\(query.count) chars)")
        FloatingControlBarManager.shared.sendFollowUpQuery(
          query,
          fromVoice: true,
          voiceTurnID: turnID)
      } else {
        log("PushToTalkManager: sending query (\(query.count) chars)")
        FloatingControlBarManager.shared.openAIInputWithQuery(
          query,
          fromVoice: true,
          voiceTurnID: turnID)
      }
    }
    if let tracer {
      tracer.updateQuery(query)
      QueryTracerContext.$current.withValue(tracer) {
        dispatch()
      }
    } else {
      dispatch()
    }
  }

  // MARK: - Audio Transcription (Dedicated Session)

  private func captureContextAndStartAudio(preOverlayImage: CGImage? = nil) {
    guard let turnID = currentVoiceTurnID else { return }
    contextCaptureTask?.cancel()
    // QueryTracer: audio capture runs until finalize; context OCR runs in
    // parallel (the `parallel_with` marker + overlapping start/end windows make
    // the concurrency visible in the trace).
    activeTracer?.begin("audio_capture")
    startAudioTranscription()
    activeTracer?.begin("context_ocr", metadata: ["parallel_with": "audio_capture"])
    let captureStartedAt = Date()
    contextCaptureTask = Task { [weak self] in
      let snapshot = await PTTContextVocabularyProvider.capture(at: captureStartedAt, preOverlayImage: preOverlayImage)
      await MainActor.run {
        guard let self, !Task.isCancelled else { return }
        guard self.currentVoiceTurnID == turnID,
          self.voiceTurnCoordinator.activeTurnID == turnID
        else { return }
        guard self.phase?.isRecording == true || self.phase == .finalizing else { return }
        self.currentContextSnapshot = snapshot
        let version = VoiceContextSnapshotVersion(
          "\(Int64(snapshot.capturedAt.timeIntervalSince1970 * 1_000)):\(snapshot.sourceCount)")
        self.voiceTurnCoordinator.publish(
          .contextResolved(turnID: turnID, outcome: .captured(version)))
        self.activeTracer?.end("context_ocr")
      }
    }
  }

  /// Captures one in-memory visual evidence object before Omi expands its PTT overlay.
  /// The realtime hub may later deliver these exact pixels only through the authorized
  /// screenshot tool; it must never take a second, pointer-selected screen capture.
  private func captureTurnScreenEvidence() -> CGImage? {
    guard let turnID = currentVoiceTurnID else { return nil }
    let evidence = RealtimeScreenEvidenceCapture.capture(for: turnID)
    RealtimeHubController.shared.installScreenEvidence(evidence)
    return evidence.preOverlayImage
  }

  /// Non-production PTT probes use the same pre-overlay capture path as a physical shortcut
  /// press. The turn ID is supplied by the controller harness because it deliberately bypasses
  /// the floating overlay, but it still captures once, before `beginTurn` can send provider
  /// input. This makes current-screen regressions reproducible without synthetic screenshots.
  func captureScreenEvidenceForAutomation(turnID: VoiceTurnID) -> Bool {
    guard voiceTurnCoordinator.activeTurnID == turnID else { return false }
    let evidence = RealtimeScreenEvidenceCapture.capture(for: turnID)
    RealtimeHubController.shared.installScreenEvidence(evidence)
    return evidence.preOverlayImage != nil
  }

  private func startAudioTranscription() {
    if automationCaptureBypass, let turnID = currentVoiceTurnID {
      micCaptureGeneration &+= 1
      voiceTurnCoordinator.publish(
        .captureStarted(turnID: turnID, captureID: VoiceCaptureID(micCaptureGeneration)))
      if automationExercisesRealtimePath {
        startRealtimePTTRoute(startMicrophoneCapture: false)
      }
      return
    }
    // Always re-check permission (it can be granted at any time via System Settings)
    hasMicPermission = AudioCaptureService.checkPermission()

    // A denied grant is spent — `requestAccess` never resurfaces it — so end the
    // turn instead of re-running the same dead request on every press.
    if MicrophoneCaptureAuthorizationPolicy.action(for: AudioCaptureService.authorizationStatus())
      == .surfacePermissionAlert
    {
      log("PushToTalkManager: microphone permission denied — ending turn without a re-request")
      if let turnID = currentVoiceTurnID {
        voiceTurnCoordinator.publish(.finish(turnID: turnID, reason: .permissionDenied))
      }
      return
    }
    guard hasMicPermission else {
      log("PushToTalkManager: no microphone permission, requesting")
      let permissionTurnID = currentVoiceTurnID
      Task { @MainActor [weak self] in
        guard let self else { return }
        let granted = await AudioCaptureService.requestPermission()
        guard self.voiceTurnCoordinator.activeTurnID == permissionTurnID,
          let permissionTurnID
        else { return }
        self.hasMicPermission = granted
        if granted {
          log("PushToTalkManager: microphone permission granted")
          guard self.voiceTurnCoordinator.activeTurn?.phase.isRecording == true else { return }
          self.startAudioTranscription()
        } else {
          log("PushToTalkManager: microphone permission denied")
          self.voiceTurnCoordinator.publish(
            .finish(turnID: permissionTurnID, reason: .permissionDenied))
        }
      }
      return
    }

    startRealtimePTTRoute(startMicrophoneCapture: true)
  }

  /// A connected socket is not necessarily admitted for this turn's immutable
  /// kernel context. Capture starts in either case; only an exact binding earns
  /// direct ingress, otherwise the controller buffers through its one handoff.
  private func startRealtimePTTRoute(startMicrophoneCapture: Bool) {
    let decision = PTTRoutePolicy.decide(
      isOnline: NetworkReachability.shared.isOnline,
      admitsImmediately: RealtimeHubController.shared.pttAdmission == .immediate)
    switch decision {
    case .onDeviceDictation:
      startOnDeviceDictation(startMicrophoneCapture: startMicrophoneCapture)
    case .hubImmediate:
      if let turnID = currentVoiceTurnID {
        voiceTurnCoordinator.publish(.selectRoute(turnID: turnID, route: .hub(sessionID: nil)))
      }
      _ = startRealtimeHubCapture(bufferWhileWarming: !startMicrophoneCapture)
    case .hubWarmWait:
      startRealtimeHubWarmWait(startMicrophoneCapture: startMicrophoneCapture)
    }
  }

  @discardableResult
  private func startRealtimeHubCapture(bufferWhileWarming: Bool) -> Bool {
    if !bufferWhileWarming {
      batchAudioLock.lock()
      batchAudioBuffer = Data()
      batchAudioLock.unlock()
    }
    let preparation: RealtimeInputPreparationResult
    if RealtimeHubController.shared.hasPendingInputPreparation(for: currentVoiceTurnID) {
      preparation = .accepted
    } else {
      preparation = RealtimeHubController.shared.beginTurn(turnID: currentVoiceTurnID)
    }
    guard preparation == .accepted else {
      log("PushToTalkManager: realtime transport was ready but context admission was rejected")
      if bufferWhileWarming {
        // `hubReady` already cancelled the warm deadline. Route the rejection
        // through the reducer so a released turn cannot remain parked forever in
        // finalizing + hubWarmWait while the socket idles out.
        if let turnID = currentVoiceTurnID {
          voiceTurnCoordinator.publish(.hubAdmissionRejected(turnID: turnID))
        }
      } else {
        _ = startOmniTranscription(captureAlreadyRunning: false)
      }
      return false
    }
    if bufferWhileWarming {
      batchAudioLock.lock()
      let bufferedAudio = batchAudioBuffer
      batchAudioLock.unlock()
      if !bufferedAudio.isEmpty {
        RealtimeHubController.shared.feedAudio(bufferedAudio, turnID: currentVoiceTurnID)
      }
      log(
        "PushToTalkManager: realtime hub became ready — flushed "
          + "\(String(format: "%.2f", Double(bufferedAudio.count / 2) / 16000.0))s buffered audio")
    }
    // Bluetooth output: opening a BT mic forces the device into 16 kHz HFP mode,
    // which drops the OUTPUT rate too and chops the spoken reply (the A2DP↔HFP
    // flap). So when output is Bluetooth, capture from the built-in mic instead.
    if !bufferWhileWarming {
      if let builtIn = preferredPTTInputOverrideDeviceID() {
        log("PushToTalkManager: hub on Bluetooth output — capturing from built-in mic to keep A2DP")
        startMicCapture(overrideDeviceID: builtIn)
      } else {
        startMicCapture()
      }
    }
    log("PushToTalkManager: realtime hub capture admitted — model is the voice hub")
    return true
  }

  /// Runs a turn with no network at all: mic into the batch buffer, decoded by
  /// the on-device Parakeet model, typed as it is spoken.
  ///
  /// Only dictation can complete here. A question needs a cloud model to answer
  /// it, and no on-device fallback replaces that — such a turn ends cleanly
  /// rather than pretending to be in flight.
  private func startOnDeviceDictation(startMicrophoneCapture: Bool) {
    batchAudioLock.lock()
    batchAudioBuffer = Data()
    batchAudioLock.unlock()
    if let turnID = currentVoiceTurnID {
      voiceTurnCoordinator.publish(.selectRoute(turnID: turnID, route: .onDeviceASR))
    }
    log("PushToTalkManager: no network — dictating with the on-device model")
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "ptt_cascade",
      from: "hub",
      to: "on_device_asr",
      reason: "network",
      outcome: .recovered)
    guard startMicrophoneCapture else { return }
    if let builtIn = preferredPTTInputOverrideDeviceID() {
      startMicCapture(batchMode: true, overrideDeviceID: builtIn)
    } else {
      startMicCapture(batchMode: true)
    }
  }

  private func startRealtimeHubWarmWait(startMicrophoneCapture: Bool = true) {
    batchAudioLock.lock()
    batchAudioBuffer = Data()
    batchAudioLock.unlock()
    if let turnID = currentVoiceTurnID {
      voiceTurnCoordinator.publish(.selectRoute(turnID: turnID, route: .hubWarmWait))
      // Establish the reducer-owned input boundary before any warm attempt.
      // This lets a retry join cancellation/context handoff rather than waiting
      // behind a global fence with no captured-turn owner.
      _ = RealtimeHubController.shared.beginTurn(turnID: turnID)
    }
    RealtimeHubController.shared.ensureWarm(userInitiated: true)
    guard startMicrophoneCapture else { return }
    if let builtIn = preferredPTTInputOverrideDeviceID() {
      log("PushToTalkManager: waiting for realtime hub — buffering built-in mic audio")
      startMicCapture(batchMode: true, overrideDeviceID: builtIn)
    } else {
      log("PushToTalkManager: waiting for realtime hub — buffering mic audio")
      startMicCapture(batchMode: true)
    }
    // VoiceTurnCoordinator owns the warm deadline. hubDidConnect resolves it
    // with a typed session ID; expiry emits fallbackToTranscription.
  }

  private func resolveRealtimeHubWarmWait(ready: Bool) {
    guard phase?.isRecording == true || phase == .finalizing else {
      return
    }
    // A dictation never hands its audio to the hub, however late the hub wakes.
    if voiceTypeSession.claimsTurn {
      log("PushToTalkManager: realtime hub \(ready ? "ready" : "timed out") under a dictation — ignored")
      return
    }
    if ready {
      let accepted = startRealtimeHubCapture(bufferWhileWarming: true)
      if accepted, phase == .finalizing {
        commitBufferedRealtimeHubTurn()
      }
      return
    }

    if phase == .finalizing {
      log("PushToTalkManager: realtime hub warm wait timed out after release — transcribing buffered audio")
      transcribeBufferedWarmWaitAudio()
    } else {
      log("PushToTalkManager: realtime hub warm wait timed out — using omni STT")
      _ = startOmniTranscription(captureAlreadyRunning: true)
    }
  }

  /// Preserve fallback observability without adding progress copy to PTT chrome.
  private func recordBackupTranscriptionFallback(reason: VoiceTurnTerminalReason) {
    let toLane = phase == .finalizing ? "batch_stt" : "omni"
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "ptt_cascade",
      from: "hub",
      to: toLane,
      reason: "timeout",
      outcome: .degraded,
      extra: [
        "user_visible": false,
        "terminal_reason": reason.rawValue,
      ])
  }

  private func commitBufferedRealtimeHubTurn() {
    guard isHubMode else { return }
    activeTracer = nil
    batchAudioLock.lock()
    let turnAudio = batchAudioBuffer
    batchAudioBuffer = Data()
    batchAudioLock.unlock()
    let totalSec = Double(turnAudio.count / 2) / 16000.0
    if !Self.hubTurnHasSpeech(pcm16k: turnAudio) {
      let (peak, rms) = Self.audioEnergy(pcm16k: turnAudio)
      let dev = audioCaptureService?.currentDeviceDescription ?? "?"
      let resolution = resolveDiscardedTurn(totalSec: totalSec)
      // Mirror the primary hub path: repeated dead-mic turns must trip capture
      // recovery here too, otherwise users whose turns land on the buffered
      // warm-wait path get recovery_action=none forever (issue #9081).
      let recoveryDecision = silentMicRecoveryPolicy.recordDiscardedTurn(
        holdSec: judgeableHoldSeconds ?? totalSec, totalSec: totalSec, peak: peak)
      recordSilentMicRecoveryOutcome(recoveryDecision.recoveryOutcome)
      DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
        source: "buffered_hub",
        mode: finalizedMode,
        audioSeconds: totalSec,
        voicedSeconds: nil,
        peak: peak,
        rms: rms,
        deviceDescription: dev,
        micPermissionGranted: hasMicPermission,
        hubActive: true,
        recoveryAction: recoveryDecision.shouldRebuildCapture ? "capture_rebuild" : "none",
        recoveryResult: recoveryDecision.shouldRebuildCapture ? "attempted" : "not_attempted")
      pttLifecycle.terminate(
        disposition: resolution.disposition,
        source: "buffered_hub",
        peak: peak,
        rms: rms,
        turnAudioSeconds: totalSec,
        voicedAudioSeconds: nil,
        judgeable: resolution.judgeable,
        captureStartedLate: resolution.captureStartedLate)
      log(
        "PushToTalkManager: discarding buffered hub turn — audio \(String(format: "%.2f", totalSec))s "
          + "peak=\(peak)/32767 rms=\(rms) device=[\(dev)] — not committing")
      if let turnID = currentVoiceTurnID {
        _ = RealtimeHubController.shared.cancelTurn(turnID: turnID)
      }
      if recoveryDecision.shouldRebuildCapture {
        requestCoreAudioCaptureRecovery(reason: "repeated dead-mic PTT turns", restartPTT: false, batchMode: false)
      }
      AnalyticsManager.shared.floatingBarPTTEnded(
        mode: finalizedMode, committed: false, transcriptLength: nil)
      if resolution.captureStartedLate {
        finishCaptureNotReadyPTTTurn(reason: "buffered hub, \(String(format: "%.2f", totalSec))s")
      } else if let turnID = currentVoiceTurnID {
        voiceTurnCoordinator.publish(.finish(turnID: turnID, reason: resolution.terminalReason))
      }
      return
    }
    guard let turnID = currentVoiceTurnID else { return }
    if voiceTypeSession.claimsTurn {
      finishVoiceTypingTurn(turnID: turnID, audio: turnAudio, knownTranscript: nil)
      return
    }
    // Same dictation check as the primary hub path: a wake word the probes
    // missed while the hub warmed must not reach the model either.
    gateHubCommitOnFinalDictationCheck(turnID: turnID, turnAudio: turnAudio) { [weak self] in
      self?.commitBufferedHubTurnAfterDictationCheck(turnAudio: turnAudio, totalSec: totalSec)
    }
  }

  private func commitBufferedHubTurnAfterDictationCheck(turnAudio: Data, totalSec: Double) {
    guard isHubMode else { return }
    let commitResult = RealtimeHubController.shared.commitTurn()
    if commitResult == .rejectedNoSession {
      log("PushToTalkManager: buffered hub commit rejected — falling back to buffered transcription")
      batchAudioLock.lock()
      batchAudioBuffer = turnAudio
      batchAudioLock.unlock()
      recordBackupTranscriptionFallback(reason: .hubWarmTimeout)
      transcribeBufferedWarmWaitAudio()
      return
    }
    if commitResult == .alreadyOwned {
      log("PushToTalkManager: buffered hub commit is already owned — skipping duplicate fallback")
      return
    }
    recordSilentMicRecoveryOutcome(silentMicRecoveryPolicy.recordSuccessfulTurn())
    DesktopDiagnosticsManager.shared.recordPTTCommitted(mode: finalizedMode, hubActive: true)
    let (committedPeak, committedRMS) = Self.audioEnergy(pcm16k: turnAudio)
    pttLifecycle.terminate(
      disposition: .committed,
      source: "buffered_hub",
      peak: committedPeak,
      rms: committedRMS,
      turnAudioSeconds: totalSec,
      voicedAudioSeconds: nil,
      judgeable: true)
    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: finalizedMode, committed: true, transcriptLength: nil)
    log(
      "PushToTalkManager: buffered hub turn "
        + "\(commitResult == .accepted ? "committed" : "deferred until its realtime session is ready") after warm wait")
  }

  private func transcribeBufferedWarmWaitAudio() {
    batchAudioLock.lock()
    let audio = batchAudioBuffer
    batchAudioLock.unlock()
    let (totalSec, voicedSec) = Self.voicedAudioSeconds(pcm16k: audio)
    guard totalSec >= Self.minTurnAudioSeconds, voicedSec >= Self.minVoicedSeconds else {
      let (peak, rms) = Self.audioEnergy(pcm16k: audio)
      let resolution = resolveDiscardedTurn(totalSec: totalSec)
      // Same dead-mic recovery as the primary omni/batch path — the warm-wait
      // fallback was previously the one silent-turn exit with no recovery (#9081).
      let recoveryDecision = silentMicRecoveryPolicy.recordDiscardedTurn(
        holdSec: judgeableHoldSeconds ?? totalSec, totalSec: totalSec, peak: peak)
      recordSilentMicRecoveryOutcome(recoveryDecision.recoveryOutcome)
      DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
        source: "warm_wait_fallback",
        mode: finalizedMode,
        audioSeconds: totalSec,
        voicedSeconds: voicedSec,
        peak: peak,
        rms: rms,
        deviceDescription: audioCaptureService?.currentDeviceDescription,
        micPermissionGranted: hasMicPermission,
        hubActive: false,
        recoveryAction: recoveryDecision.shouldRebuildCapture ? "capture_rebuild" : "none",
        recoveryResult: recoveryDecision.shouldRebuildCapture ? "attempted" : "not_attempted")
      pttLifecycle.terminate(
        disposition: resolution.disposition,
        source: "warm_wait_fallback",
        peak: peak,
        rms: rms,
        turnAudioSeconds: totalSec,
        voicedAudioSeconds: voicedSec,
        judgeable: resolution.judgeable,
        captureStartedLate: resolution.captureStartedLate)
      log(
        "PushToTalkManager: discarding warm-wait fallback turn (audio \(String(format: "%.2f", totalSec))s, voiced \(String(format: "%.2f", voicedSec))s)"
      )
      AnalyticsManager.shared.floatingBarPTTEnded(
        mode: finalizedMode, committed: false, transcriptLength: nil)
      if recoveryDecision.shouldRebuildCapture {
        requestCoreAudioCaptureRecovery(reason: "repeated dead-mic PTT turns", restartPTT: false, batchMode: true)
      }
      if resolution.captureStartedLate {
        finishCaptureNotReadyPTTTurn(
          reason: "warm-wait fallback, \(String(format: "%.2f", totalSec))s")
      } else if let turnID = currentVoiceTurnID {
        voiceTurnCoordinator.publish(.finish(turnID: turnID, reason: resolution.terminalReason))
      }
      return
    }
    recordSilentMicRecoveryOutcome(silentMicRecoveryPolicy.recordSuccessfulTurn())
    guard let turnID = currentVoiceTurnID else { return }
    voiceTurnCoordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
    voiceTurnCoordinator.publish(.transcriptionStarted(turnID: turnID))
    Task { @MainActor [weak self] in
      guard let self, self.voiceTurnCoordinator.activeTurnID == turnID else { return }
      do {
        let language = AssistantSettings.shared.effectiveTranscriptionLanguage
        self.activeTracer?.begin("batch_transcribe", metadata: ["reason": "hub_warm_timeout"])
        let batchResult = try await TranscriptionService.batchTranscribe(
          audioData: audio,
          language: language,
          contextKeywords: self.currentContextSnapshot?.keywords ?? []
        )
        guard self.voiceTurnCoordinator.activeTurnID == turnID else { return }
        self.activeTracer?.end("batch_transcribe")
        log(
          "PushToTalkManager: warm-wait batch STT selected provider=\(batchResult.provider ?? "unknown") "
            + "model=\(batchResult.model ?? "unknown")")
        let provider = batchResult.provider ?? "unknown"
        let model = batchResult.model ?? "unknown"
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "ptt_cascade",
          from: "hub",
          to: provider,
          reason: "timeout",
          outcome: .recovered,
          extra: [
            "stt_provider": provider,
            "stt_model": model,
            "user_visible": true,
          ])
        if let transcript = batchResult.transcript, !transcript.isEmpty {
          self.transcriptSegments = [transcript]
        }
      } catch {
        logError("PushToTalkManager: warm-wait fallback transcription failed", error: error)
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "ptt_cascade",
          from: "hub",
          to: "batch_stt",
          reason: "timeout",
          outcome: .exhausted,
          extra: [
            "stt_provider": "unknown",
            "stt_model": "unknown",
            "user_visible": true,
          ])
        self.voiceTurnCoordinator.publish(
          .transcriptionFailed(turnID: turnID, message: error.localizedDescription))
        return
      }
      self.sendTranscript(turnID: turnID)
    }
  }

  var parkedMicCapture: (service: AudioCaptureService, lease: MicCaptureLease, overrideID: AudioDeviceID?)?
  private var parkedMicExpiryTask: Task<Void, Never>?
  /// Generation watermark set by a terminal (parkWarm: false) stop. A capture
  /// start still in flight at that moment cannot be stopped yet; when it
  /// completes late it must be released, not parked — an explicitly cancelled
  /// turn may never leave the microphone open for the keep-alive window. A
  /// watermark (not a flag) so a newer turn starting before the old start
  /// resolves cannot accidentally clear the older generation's terminal fate.
  private var discardLateStartsThroughGeneration: UInt64 = 0
  private var activeMicLease: MicCaptureLease?
  private var activeMicOverrideID: AudioDeviceID?
  /// Route class noted at the last successful capture start. A parked capture's
  /// physical route cannot change while its IOProc stays open, so warm adoption
  /// reuses this instead of re-reading the HAL (currentDeviceDescription walks
  /// the device list; the warm path must stay instant on the main actor).
  private var lastNotedInputRouteClass: PTTAttemptLifecycleRecorder.InputRouteClass?
  private static let parkedMicKeepAliveSeconds: UInt64 = 120

  private func parkMicCapture(_ service: AudioCaptureService, lease: MicCaptureLease, overrideID: AudioDeviceID?) {
    parkedMicExpiryTask?.cancel()
    if let old = parkedMicCapture, old.service !== service {
      old.service.stopCapture()
    }
    lease.setParked(true)
    parkedMicCapture = (service, lease, overrideID)
    parkedMicExpiryTask = Task { @MainActor [weak self] in
      try? await Task.sleep(nanoseconds: Self.parkedMicKeepAliveSeconds * 1_000_000_000)
      guard let self, !Task.isCancelled else { return }
      if let parked = self.parkedMicCapture {
        parked.service.stopCapture()
        self.parkedMicCapture = nil
        log("PushToTalkManager: warm mic keep-alive expired — capture released")
      }
    }
  }

  private func discardParkedMicCapture() {
    _ = releaseParkedMicCapture()
    // Not awaited: this runs from terminal cleanup and capture rebuilds, which
    // have no async boundary. The handle stays on the manager, so whoever does
    // have one — the next press, ambient transcription, the owner transition —
    // still waits for the teardown this release started.
    releaseInFlightWarmCapture()
  }

  /// Release the parked warm capture (if any) and hand it back so the caller
  /// can await its HAL teardown before opening the same device. Used by the
  /// ambient transcription start path to guarantee the two capture owners'
  /// IOProcs never overlap on one device.
  func releaseParkedMicCapture() -> AudioCaptureService? {
    parkedMicExpiryTask?.cancel()
    parkedMicExpiryTask = nil
    guard let parked = parkedMicCapture else { return nil }
    parkedMicCapture = nil
    parked.service.stopCapture()
    return parked.service
  }

  /// The per-frame routing every PTT capture uses, built against `lease` so the
  /// closures installed on a capture at open time keep working after a later turn
  /// adopts it out of the warm park (`MicCaptureLease.renew`). Extracted so a
  /// prewarmed capture is byte-for-byte the same capture a turn would have opened
  /// — a second, subtly different frame path is exactly how a warm capture would
  /// start leaking frames into the wrong turn.
  private func micAudioChunkHandler(lease: MicCaptureLease) -> AudioCaptureService.AudioChunkHandler {
    { [weak self] audioData in
      // Snapshot before scheduling so a frame emitted during the previous
      // turn or the parked interval keeps that authority even if a warm
      // adoption renews the lease before this Task runs.
      guard let leased = lease.snapshotIfActive() else { return }
      Task { @MainActor [weak self] in
        guard let self else { return }
        guard self.micCaptureGeneration == leased.generation,
          self.voiceTurnCoordinator.activeTurnID == leased.turnID,
          self.shouldKeepMicCaptureAlive
        else { return }
        self.ingestMicChunk(
          audioData, generation: leased.generation, turnID: leased.turnID, batchMode: leased.batchMode)
      }
    }
  }

  /// One mic chunk through the route it belongs to. Everything a PTT turn does
  /// with audio while the key is held goes through here — the physical capture
  /// callback and the automation bridge's injected hold alike — so a harness
  /// exercises the same branches a real hold does.
  private func ingestMicChunk(
    _ audioData: Data, generation: UInt64, turnID: VoiceTurnID, batchMode: Bool
  ) {
    pttLifecycle.ingestAudioChunk(audioData)
    // Once the turn is a dictation, the microphone only records: the whole
    // turn is transcribed and pasted at key-up, and no model is asked anything
    // meanwhile. Route transitions the reducer makes from here on (warm-wait
    // timeout, hub ready) do not reach the audio, which is what lets a hold
    // run for as long as the user likes.
    if voiceTypeSession.claimsTurn {
      appendBatchAudioBounded(audioData, turn: generation)
      return
    }
    // Every route, unconditionally: the wake-word probe listens on the hub's
    // warm-wait as much as on the hub itself. Scheduled by voiced audio, and
    // run after this chunk has joined the turn buffer below.
    let probeDue = voiceTypingProbeSchedule.observe(chunk: audioData)
    defer { if probeDue { probeVoiceTypingWakeWord(turnID: turnID) } }
    if isWaitingForHub {
      appendBatchAudioBounded(audioData, turn: generation)
      return
    }
    if isHubMode {
      // Lifecycle admission and provider commit are serialized on the
      // main actor. A chunk queued behind finalization observes the
      // closed capture token and cannot leak into the next turn.
      RealtimeHubController.shared.feedAudio(audioData, turnID: turnID)
      appendBatchAudioBounded(audioData, turn: generation)
      return
    }
    if isOnDeviceASR {
      // Offline: the on-device decode at key-up is the only transcript there
      // is, so every byte is kept for it.
      appendBatchAudioBounded(audioData, turn: generation)
      return
    }
    if isOmniSTT {
      if let svc = realtimeOmniService {
        svc.sendAudio(resampleForOmni(audioData))
      } else {
        omniPreconnectBuffer.append(audioData)
      }
      appendBatchAudioBounded(audioData, turn: generation)
    } else if batchMode {
      appendBatchAudioBounded(audioData, turn: generation)
    } else {
      transcriptionService?.sendAudio(audioData)
    }
  }

  private func micAudioLevelHandler(lease: MicCaptureLease) -> AudioCaptureService.AudioLevelHandler {
    { [weak self] level in
      guard let leased = lease.snapshotIfActive() else { return }
      Task { @MainActor [weak self] in
        guard let self else { return }
        guard self.micCaptureGeneration == leased.generation,
          self.voiceTurnCoordinator.activeTurnID == leased.turnID,
          self.shouldKeepMicCaptureAlive
        else { return }
        // Feed the floating-bar mic waveform (VoiceWaveformBars). Throttled to ~5 Hz
        // inside the monitor; used only for visualization.
        AudioLevelMonitor.shared.updateMicrophoneLevel(level)
      }
    }
  }

  /// Installs the watchdog and route-change observers a PTT capture needs. Shared
  /// with the prewarm path for the same reason as the frame handlers above.
  private func configureMicCaptureObservers(_ capture: AudioCaptureService, lease: MicCaptureLease) {
    // Silent-mic watchdog: Bluetooth inputs can return zeros during A2DP/HFP conflicts,
    // and stale CoreAudio routes can do the same even when the selected device is built-in.
    capture.resetSilentMicWatchdog()
    capture.detectSilentMicOnAnyTransport = true
    capture.onSilentMicDetected = { [weak self] detection in
      // Snapshot before scheduling: a warm adoption renewing the lease must not
      // re-authorize an event emitted under the previous turn's authority.
      guard let leased = lease.snapshotIfActive() else { return }
      Task { @MainActor in
        guard let self else { return }
        guard self.micCaptureGeneration == leased.generation,
          self.voiceTurnCoordinator.activeTurnID == leased.turnID
        else { return }
        self.handleSilentMicDetection(detection, batchMode: leased.batchMode)
      }
    }
    capture.onInputRouteChanged = { [weak self] in
      guard let leased = lease.snapshotIfActive() else { return }
      Task { @MainActor in
        guard let self else { return }
        guard self.micCaptureGeneration == leased.generation,
          self.voiceTurnCoordinator.activeTurnID == leased.turnID
        else { return }
        self.pttLifecycle.noteRouteChanged()
      }
    }
  }

  /// The warm capture whose CoreAudio start has not resolved yet, together with
  /// the work that finishes it. A reference, not a flag: an in-flight warm
  /// capture has already registered in the active-capture registry and is about
  /// to own an IOProc, so every path that gives up a *parked* capture has to be
  /// able to give up this one too.
  private var warmCapture: (service: AudioCaptureService, start: Task<Void, Never>)?

  var warmCaptureInFlight: AudioCaptureService? { warmCapture?.service }

  /// The teardown of a warm capture somebody gave up, kept on the manager rather
  /// than handed to one caller. Cleared by the warm start's own completion.
  private var warmTeardown: Task<Void, Never>?

  /// How long a press will wait for a displaced warm teardown before opening the
  /// device anyway. A CoreAudio start has no timeout and no cancellation — after
  /// wake from sleep `coreaudiod` can take seconds to answer — and a warm-up that
  /// exists to take latency *out* of the press must never be what holds one up.
  private static let displacedWarmCaptureWaitSeconds: TimeInterval = 0.5

  /// The owner transition waits longer than a press: an account switch may stall
  /// a little, but it must not stall indefinitely on a wedged CoreAudio start.
  private static let ownerTransitionWarmCaptureWaitSeconds: TimeInterval = 3

  /// A warm capture is either still starting or still tearing down. Both hold the
  /// device, and the second state is the whole point of keeping the handle — a
  /// press that only looked at `warmCapture` would sail past a teardown
  /// `discardParkedMicCapture` had already started.
  var hasWarmCaptureToDrain: Bool { warmCapture != nil || warmTeardown != nil }

  /// Give up a warm capture whose start has not resolved.
  ///
  /// Neither `stopCapture()` nor `waitForPhysicalStop()` is a boundary here.
  /// `AudioCaptureService.stopCapture` returns immediately while `isCapturing` is
  /// false, and `isCapturing` only flips at the *end* of the HAL setup — so for
  /// the whole ~900 ms window this warm-up exists to hide, a stop is a no-op and
  /// `waitForPhysicalStop` degrades into "wait for the start to finish", handing
  /// the caller a capture that is now running. Clearing the reference is what
  /// tells the start's own completion to stop and drain the capture instead of
  /// parking it, and `drainInFlightWarmCapture` is how a caller waits for that.
  ///
  /// Idempotent, and it keeps the handle rather than returning it: terminal
  /// cleanup and capture rebuilds have no async boundary to await on, and if
  /// releasing there consumed the handle it would disarm the wait every *other*
  /// caller makes — including the owner-transition drain.
  func releaseInFlightWarmCapture() {
    guard let warm = warmCapture else { return }
    warmCapture = nil
    warmTeardown = warm.start
  }

  /// Release a warm capture and wait for its teardown.
  ///
  /// `timeout: nil` waits as long as it takes. Nothing uses it: even the owner
  /// transition takes a bound, because the thing being protected is weaker than
  /// the risk. A warm lease is created parked and is never renewed, so it cannot
  /// admit a frame into any turn under any owner — the INV-AUTH-1 exposure is "an
  /// IOProc is briefly open", not "the previous owner's audio reaches the next
  /// one" — while an unbounded wait sits on a `startCapture` that has no timeout
  /// at all and would freeze an account switch behind a wedged `coreaudiod`.
  /// A warm capture that outlives any of these waits is still stopped by its own
  /// completion; only the overlap guarantee is given up.
  ///
  /// Waits on the handle rather than `Task.value` under a bound because awaiting
  /// a non-throwing task ignores cancellation, so it cannot be given a deadline.
  func drainInFlightWarmCapture(timeout: TimeInterval? = displacedWarmCaptureWaitSeconds) async {
    releaseInFlightWarmCapture()
    guard let teardown = warmTeardown else { return }
    guard let timeout else {
      await teardown.value
      return
    }
    let deadline = Date().addingTimeInterval(timeout)
    // `Task.isCancelled` in the condition: a cancelled task's `Task.sleep` throws
    // immediately, and `try?` would turn this into a hot main-actor loop until the
    // wall-clock deadline. `reconcileCapture` can cancel the ambient caller.
    while warmTeardown != nil, !Task.isCancelled, Date() < deadline {
      try? await Task.sleep(nanoseconds: 20_000_000)
    }
    if warmTeardown != nil {
      // A start wedged in CoreAudio never clears this, which silently refuses
      // every later warm-up for the life of the process. Benign — presses still
      // open their own capture — but it must be visible in the log.
      log("PushToTalkManager: warm capture teardown outran its wait — opening the device anyway")
    }
  }

  /// Ask for a warm capture on the next main-actor hop. Used from paths that are
  /// still inside a turn's teardown, where opening the device now would race the
  /// terminal cleanup that is about to release it.
  func schedulePTTCaptureWarmup(trigger: PTTWarmCaptureAdmission.Trigger) {
    Task { @MainActor [weak self] in
      self?.prewarmMicCapture(trigger: trigger)
    }
  }

  /// Open a microphone capture *before* the user's first press and park it in the
  /// existing keep-alive, so the press adopts a running IOProc instead of paying
  /// CoreAudio's start latency inside the hold.
  ///
  /// This is the 0→1 fix: on a fresh install the first hold after onboarding is
  /// the one that gets `capture_start_outcome=requested` and never `accepted`,
  /// and it is reported back to the user as "Hold longer to record". There is no
  /// second mechanism here — it opens exactly the capture `startMicCapture` would
  /// have opened and hands it to `parkMicCapture`, so the adoption path, the
  /// keep-alive expiry, and the device-contention rules are the ones already in
  /// production.
  ///
  /// Nothing the user did is behind this, which is why admission is stricter than
  /// a press: it refuses unless routing has resolved a device that is safe to
  /// hold open unattended (never an explicit microphone choice, never Bluetooth —
  /// see `unattendedWarmCaptureRoute`), it re-checks the device it actually
  /// opened before keeping it, and it never raises a permission prompt.
  ///
  /// INV-VOICE-1: no turn events are published and no lifecycle authority is
  /// taken. The lease is created parked, so every frame the device delivers
  /// before a real turn adopts it is dropped inside `snapshotIfActive()`.
  func prewarmMicCapture(trigger: PTTWarmCaptureAdmission.Trigger) {
    hasMicPermission = AudioCaptureService.checkPermission()
    let ownerID = RuntimeOwnerIdentity.currentOwnerId()
    // Cheap gates first: resolving the route kicks a HAL read as a side effect,
    // and a signed-out or push-to-talk-off install should not pay for one.
    guard ShortcutSettings.shared.pttEnabled, hasMicPermission, ownerID != nil else { return }
    let route = unattendedWarmCaptureRoute()
    let admission = PTTWarmCaptureAdmission.Input(
      pttEnabled: true,
      micPermissionGranted: true,
      onboardingComplete: UserDefaults.standard.bool(forKey: .hasCompletedOnboarding),
      isSignedIn: true,
      routeIsSafeToWarmUnattended: route != .refused,
      hasActiveTurn: voiceTurnCoordinator.activeTurnID != nil,
      hasCaptureAlready: parkedMicCapture != nil || audioCaptureService != nil
        || micCaptureStartInFlight || warmCapture != nil || warmTeardown != nil)
    guard PTTWarmCaptureAdmission.admits(admission),
      case .device(let overrideDeviceID) = route
    else { return }

    let capture = overrideDeviceID.map(AudioCaptureService.init(overrideDeviceID:)) ?? AudioCaptureService()
    // A lease that starts parked: the capture is running, nothing may consume it.
    // `batchMode` and `turnID` are placeholders — the adopting turn overwrites
    // both through `renew` before a single frame is admitted.
    let lease = MicCaptureLease(
      generation: micCaptureGeneration, batchMode: false, turnID: VoiceTurnID())
    lease.setParked(true)
    configureMicCaptureObservers(capture, lease: lease)
    let onAudioChunk = micAudioChunkHandler(lease: lease)
    let onAudioLevel = micAudioLevelHandler(lease: lease)

    let start = Task { @MainActor [weak self] in
      // Runs on every exit below. Admission refuses a second warm capture while
      // either reference is set, so this can only ever clear its own handle.
      defer { self?.warmTeardown = nil }
      do {
        try await capture.startCapture(onAudioChunk: onAudioChunk, onAudioLevel: onAudioLevel)
      } catch {
        capture.stopCapture()
        if self?.warmCapture?.service === capture { self?.warmCapture = nil }
        // Deliberately silent to the user and to remote telemetry: nobody asked
        // for this capture, and the press that follows still runs its own start
        // with its own error handling — and emits its own lifecycle snapshot, so
        // a warm-up that never works remains visible as the `capture_start_outcome`
        // of real attempts rather than needing an event of its own.
        logError("PushToTalkManager: warm capture failed (\(trigger.rawValue))", error: error)
        return
      }
      // Past this point the capture is physically running, so `stopCapture()` is
      // finally real — and every exit below must take it unless the capture is
      // handed to `parkMicCapture`.
      guard let self, self.warmCapture?.service === capture else {
        // Somebody released this warm capture while its start was in flight.
        // Stopping it here is the teardown they are awaiting.
        capture.stopCapture()
        await capture.waitForPhysicalStop()
        log("PushToTalkManager: warm capture (\(trigger.rawValue)) superseded before parking — stopped")
        return
      }
      self.warmCapture = nil
      let routeClass = PTTAttemptLifecycleRecorder.InputRouteClass.from(
        deviceDescription: capture.currentDeviceDescription,
        isBluetooth: capture.isCurrentDeviceBluetoothTransport)
      // The snapshot decided whether to try; the device actually opened decides
      // whether to keep. `.device(nil)` follows the system default, which can
      // become a headset between the snapshot landing and the device opening —
      // and holding a Bluetooth input open unattended is what flips the user's
      // headset out of A2DP for the whole keep-alive window.
      //
      // Residual: opening the device is itself the flip, so that race still costs
      // the user a start-and-stop of HFP rather than 120 s of it. Pinning
      // `.device(defaultInputDeviceID)` instead would close it, but the parked
      // capture's `overrideID` would then stop matching the press-time `nil`
      // override and no turn would ever adopt it — which is the whole feature.
      guard routeClass != .bluetooth, !capture.isCurrentDeviceBluetoothTransport else {
        capture.stopCapture()
        log("PushToTalkManager: warm capture (\(trigger.rawValue)) opened a Bluetooth input — stopped")
        return
      }
      // The owner can change while a HAL start is in flight. A capture opened for
      // the previous owner must never be left running under the next one.
      guard RuntimeOwnerIdentity.currentOwnerId() == ownerID,
        self.voiceTurnCoordinator.activeTurnID == nil,
        self.audioCaptureService == nil, self.parkedMicCapture == nil,
        !self.micCaptureStartInFlight
      else {
        capture.stopCapture()
        log("PushToTalkManager: warm capture (\(trigger.rawValue)) no longer admissible — stopped")
        return
      }
      self.lastNotedInputRouteClass = routeClass
      self.parkMicCapture(capture, lease: lease, overrideID: overrideDeviceID)
      log("PushToTalkManager: warm capture parked ahead of the first press (\(trigger.rawValue))")
    }
    warmCapture = (capture, start)
  }

  private func startMicCapture(
    batchMode: Bool = false,
    overrideDeviceID: AudioDeviceID? = nil,
    diagnosticRecoveryAction: String? = nil
  ) {
    // Above the guard: a start that is a no-op because one is already running is
    // still a turn that asked for a capture, and `judgeableHoldSeconds` keys on
    // that. Recording it below would let a turn that re-entered here with a
    // capture already alive be judged as though it had no microphone to wait for.
    // Idempotent — `captureStartRequested` refuses to overwrite a resolved outcome.
    pttLifecycle.captureStartRequested()
    guard !micCaptureStartInFlight && !(audioCaptureService?.capturing ?? false) else {
      log("PushToTalkManager: mic capture start ignored — already active")
      if let diagnosticRecoveryAction {
        DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged(
          recoveryAction: diagnosticRecoveryAction,
          recoveryResult: "ignored_already_active")
      }
      return
    }
    micCaptureStartInFlight = true
    micCaptureGeneration &+= 1
    let generation = micCaptureGeneration
    guard let turnID = currentVoiceTurnID else {
      micCaptureStartInFlight = false
      return
    }
    let captureID = VoiceCaptureID(generation)

    if let parked = parkedMicCapture, parked.overrideID == overrideDeviceID, parked.service.capturing {
      parkedMicExpiryTask?.cancel()
      parkedMicExpiryTask = nil
      parkedMicCapture = nil
      parked.lease.renew(generation: generation, batchMode: batchMode, turnID: turnID)
      parked.service.resetSilentMicWatchdog()
      audioCaptureService = parked.service
      activeMicLease = parked.lease
      activeMicOverrideID = overrideDeviceID
      micCaptureStartInFlight = false
      pttLifecycle.captureStartResolved(outcome: .accepted, statusClass: .ok)
      pttLifecycle.noteInputRoute(
        class: lastNotedInputRouteClass ?? .unknown,
        source: overrideDeviceID == nil ? .default : .override)
      voiceTurnCoordinator.publish(.captureStarted(turnID: turnID, captureID: captureID))
      if let diagnosticRecoveryAction {
        DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged(
          recoveryAction: diagnosticRecoveryAction,
          recoveryResult: "succeeded_warm_reuse")
      }
      log("PushToTalkManager: mic capture adopted from warm keep-alive (batch=\(batchMode))")
      return
    }
    // A parked capture on a different route is displaced, not adopted. Its HAL
    // teardown is awaited inside the start Task below so the replacement can
    // never open while the displaced IOProc is still physically alive (the two
    // could even resolve to the same device, e.g. nil-override on the built-in
    // default vs. an explicit built-in override).
    let displacedParkedCapture = releaseParkedMicCapture()
    // A warm capture whose start has not resolved holds the same device just as
    // surely as a parked one, and cannot be stopped from here — waiting for its
    // own completion is the only real boundary. See `releaseInFlightWarmCapture`.
    // Released synchronously so a warm start already in flight learns it is
    // superseded before this turn's own start is queued behind it.
    let displacedWarmCapture = hasWarmCaptureToDrain
    releaseInFlightWarmCapture()

    let capture = overrideDeviceID.map(AudioCaptureService.init(overrideDeviceID:)) ?? AudioCaptureService()
    let lease = MicCaptureLease(generation: generation, batchMode: batchMode, turnID: turnID)
    activeMicLease = lease
    activeMicOverrideID = overrideDeviceID
    audioCaptureService = capture

    configureMicCaptureObservers(capture, lease: lease)

    Task { @MainActor [weak self] in
      guard let self else { return }
      if displacedWarmCapture { await self.drainInFlightWarmCapture() }
      if displacedWarmCapture || displacedParkedCapture != nil {
        await displacedParkedCapture?.waitForPhysicalStop()
        // The turn may have been cancelled — and another started — while the
        // displaced teardown was in flight. Revalidate before opening the
        // device so a stale start can never overlap a newer turn's capture.
        guard self.micCaptureGeneration == generation, self.shouldKeepMicCaptureAlive else {
          if self.audioCaptureService === capture {
            self.audioCaptureService = nil
          }
          if self.micCaptureGeneration == generation {
            self.micCaptureStartInFlight = false
          }
          log("PushToTalkManager: turn ended while displaced capture teardown was awaited — not opening")
          return
        }
      }
      do {
        try await capture.startCapture(
          onAudioChunk: self.micAudioChunkHandler(lease: lease),
          onAudioLevel: self.micAudioLevelHandler(lease: lease)
        )
        let isCurrentGeneration = self.micCaptureGeneration == generation
        guard isCurrentGeneration, self.shouldKeepMicCaptureAlive else {
          if self.audioCaptureService === capture {
            self.audioCaptureService = nil
          }
          if isCurrentGeneration {
            self.micCaptureStartInFlight = false
          }
          // Never park beside a live capture: if a newer turn already owns a
          // running (or starting) service, parking this stale one would leave
          // two open IOProcs — possibly on the same Bluetooth device. Parking
          // is only for the quiet gap between turns.
          if generation <= self.discardLateStartsThroughGeneration || self.audioCaptureService != nil
            || self.parkedMicCapture != nil
          {
            capture.stopCapture()
            if let diagnosticRecoveryAction {
              DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged(
                recoveryAction: diagnosticRecoveryAction,
                recoveryResult: "ignored_turn_ended")
            }
            log("PushToTalkManager: mic capture start completed after terminal cleanup — stopped")
            return
          }
          if let diagnosticRecoveryAction {
            DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged(
              recoveryAction: diagnosticRecoveryAction,
              recoveryResult: "ignored_turn_ended_parked_warm")
          }
          self.parkMicCapture(capture, lease: lease, overrideID: overrideDeviceID)
          log("PushToTalkManager: mic capture start completed after turn ended — parked warm")
          return
        }
        self.micCaptureStartInFlight = false
        self.pttLifecycle.captureStartResolved(outcome: .accepted, statusClass: .ok)
        let routeClass = PTTAttemptLifecycleRecorder.InputRouteClass.from(
          deviceDescription: capture.currentDeviceDescription,
          isBluetooth: capture.isCurrentDeviceBluetoothTransport)
        self.lastNotedInputRouteClass = routeClass
        self.pttLifecycle.noteInputRoute(
          class: routeClass,
          source: overrideDeviceID == nil ? .default : .override)
        self.voiceTurnCoordinator.publish(
          .captureStarted(turnID: turnID, captureID: captureID))
        if let diagnosticRecoveryAction {
          DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged(
            recoveryAction: diagnosticRecoveryAction,
            recoveryResult: "succeeded")
        }
        log("PushToTalkManager: mic capture started (batch=\(batchMode))")
      } catch {
        guard self.micCaptureGeneration == generation else {
          log("PushToTalkManager: stale mic capture start failed after turn ended: \(error.localizedDescription)")
          return
        }
        self.micCaptureStartInFlight = false
        self.pttLifecycle.captureStartResolved(
          outcome: .failed,
          statusClass: .from(error: error))
        // Emit the lifecycle snapshot so capture_start_outcome=failed is
        // observable. The reducer terminal effect (performTerminalCleanup)
        // does not call terminate(), so without this the exact scenario this
        // PR exists to diagnose never produces a lifecycle event.
        self.pttLifecycle.terminate(
          disposition: .silentRejected,
          source: "capture_start",
          // Capture never started, so zero samples is a measured fact here, not a
          // placeholder: it is what distinguishes a failed start from an unknown.
          peak: 0,
          rms: 0,
          turnAudioSeconds: 0,
          voicedAudioSeconds: nil,
          judgeable: false)
        if let diagnosticRecoveryAction {
          DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged(
            recoveryAction: diagnosticRecoveryAction,
            recoveryResult: "failed")
        }
        logError("PushToTalkManager: mic capture failed", error: error)
        self.voiceTurnCoordinator.publish(
          .captureFailed(
            turnID: turnID,
            captureID: captureID,
            message: error.localizedDescription))
      }
    }
  }

  /// Recover when the silent-mic watchdog detects a capture that is running but
  /// returning zeros. Bluetooth profile conflicts can usually be fixed by pinning
  /// to the built-in mic. Non-Bluetooth silence points to a stale CoreAudio route,
  /// so rebuild the whole capture stack instead.
  @MainActor
  private func handleSilentMicDetection(_ detection: AudioCaptureService.SilentMicDetection, batchMode: Bool) {
    guard phase?.isRecording == true else {
      return
    }
    if detection.suggestedAction == .fallbackToBuiltIn,
      let builtInID = AudioCaptureService.findBuiltInMicDeviceID(),
      builtInID != detection.deviceID
    {
      log("PushToTalkManager: silent-mic fallback — switching to built-in mic (deviceID=\(builtInID))")
      silentMicRecoveryPolicy.recordCaptureRebuild()
      pttLifecycle.recoveryTriggered(action: .switchToBuiltInMic)
      stopMicCapture(parkWarm: false)
      clearBufferedTurnAudio()
      startMicCapture(
        batchMode: batchMode,
        overrideDeviceID: builtInID,
        diagnosticRecoveryAction: "switch_to_built_in_mic")
      return
    }

    if detection.suggestedAction == .fallbackToBuiltIn {
      log("PushToTalkManager: silent-mic detected but no built-in mic to fall back to")
      DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged(
        recoveryAction: "switch_to_built_in_mic",
        recoveryResult: "no_built_in_mic")
    }

    requestCoreAudioCaptureRecovery(
      reason: "silent PTT mic on \(detection.deviceDescription)",
      restartPTT: true,
      batchMode: batchMode
    )
  }

  private func requestCoreAudioCaptureRecovery(
    reason: String, restartPTT: Bool, batchMode: Bool,
    recoveryAlreadyTriggered: Bool = false
  ) {
    log("PushToTalkManager: requesting CoreAudio capture rebuild — \(reason)")
    // Arm here (not in recordCaptureRebuild) so Bluetooth built-in fallback cannot
    // mislabel switch_to_built_in_mic results as capture_rebuild outcomes, while the
    // silent-mic watchdog CoreAudio path still gets a next-turn success/failure.
    silentMicRecoveryPolicy.armCaptureRebuildOutcome()
    if !recoveryAlreadyTriggered {
      pttLifecycle.recoveryTriggered(action: .captureRebuild)
    }
    stopMicCapture(parkWarm: false)
    clearBufferedTurnAudio()
    NotificationCenter.default.post(
      name: .coreAudioCaptureRecoveryRequested,
      object: nil,
      userInfo: ["reason": "PushToTalkManager: \(reason)"]
    )
    if restartPTT {
      startMicCapture(batchMode: batchMode, overrideDeviceID: preferredPTTInputOverrideDeviceID())
    }
  }

  private func recordSilentMicRecoveryOutcome(_ outcome: PTTSilentMicRecoveryPolicy.RecoveryOutcome?) {
    guard let outcome else { return }
    DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged(
      recoveryAction: "capture_rebuild",
      recoveryResult: outcome.rawValue)
  }

  private func clearBufferedTurnAudio() {
    batchAudioLock.lock()
    batchAudioBuffer = Data()
    batchAudioLock.unlock()
  }

  private var shouldKeepMicCaptureAlive: Bool {
    phase == .recording || phase == .lockedRecording
  }

  @discardableResult
  private func stopMicCapture(
    captureID expectedCaptureID: VoiceCaptureID? = nil,
    parkWarm: Bool = true
  ) -> Bool {
    if let expectedCaptureID,
      expectedCaptureID != VoiceCaptureID(micCaptureGeneration)
    {
      log("PushToTalkManager: ignored stale stopCapture id=\(expectedCaptureID)")
      return false
    }
    micCaptureGeneration &+= 1
    micCaptureStartInFlight = false
    if parkWarm, let service = audioCaptureService, service.capturing, let lease = activeMicLease {
      parkMicCapture(service, lease: lease, overrideID: activeMicOverrideID)
    } else {
      audioCaptureService?.stopCapture()
      if !parkWarm {
        discardParkedMicCapture()
        // An in-flight startCapture cannot be stopped from here — watermark
        // every generation up to the bump so its late completion releases the
        // capture instead of parking it warm.
        discardLateStartsThroughGeneration = micCaptureGeneration
      }
    }
    audioCaptureService = nil
    activeMicLease = nil
    activeMicOverrideID = nil
    return true
  }

  private func stopAudioTranscription(discardBufferedAudio: Bool = false, parkWarm: Bool = true) {
    stopMicCapture(parkWarm: parkWarm)
    transcriptionService?.stop(discardBufferedAudio: discardBufferedAudio)
    transcriptionService = nil
    realtimeOmniService?.stop()
    realtimeOmniService = nil
    omniDelegateProxy = nil
    omniPreconnectBuffer.removeAll()
  }

  // MARK: - Voice typing

  /// When the opening of the hold is decoded for the wake word. Advisory: the
  /// closing transcript decides the turn on its own.
  private var voiceTypingProbeSchedule = VoiceTypeWakeWordProbeSchedule()
  private var voiceTypingProbeInFlight = false
  /// Set once a dictation has released its hub turn, so key-up does not
  /// cancel it a second time.
  private var voiceTypingReleasedHubTurn = false

  /// Harness-visible record of the last dictation. Bounded scalars only.
  private struct VoiceTypingOutcome {
    var delivery = "none"
    var characters = 0
    var transcriber = "none"
    var polished = false
    var probes = 0
    var hubReleased = false
  }
  private var voiceTypingLastOutcome = VoiceTypingOutcome()

  private func resetVoiceTypingSources() {
    voiceTypingProbeSchedule.reset()
    voiceTypingProbeInFlight = false
    voiceTypingReleasedHubTurn = false
  }

  /// Everything the microphone has heard this turn. Every route that can end
  /// as a dictation appends its chunks to the shared turn buffer, so this is
  /// the one recording the closing transcription reads.
  private func voiceTypingTurnAudio() -> Data {
    batchAudioLock.lock()
    defer { batchAudioLock.unlock() }
    return batchAudioBuffer
  }

  /// Decodes the opening seconds of the hold on-device, once or twice per
  /// turn, to hear whether it began with the wake word.
  ///
  /// Nothing is typed from this. Its job is to release the realtime hub before
  /// it has streamed a whole dictation to a model whose answer will be
  /// cancelled, and to tell the user the wake word was heard. A probe that
  /// misses is harmless: the closing transcript makes the same decision from
  /// the whole turn, with the better recognizer.
  private func probeVoiceTypingWakeWord(turnID: VoiceTurnID) {
    guard !voiceTypingProbeInFlight else { return }
    let clip = VoiceTypeAudioTrim.opening(
      of: voiceTypingTurnAudio(), maxBytes: VoiceTypeWakeWordProbeSchedule.maxProbeBytes)
    // Below ~0.4 s the decoder has nothing to say.
    guard clip.count >= 12_800 else { return }
    // The slot is spent here, not when it fell due: a decode still running
    // from the last probe keeps it owed until the decoder is free.
    voiceTypingProbeSchedule.beginProbe()
    voiceTypingProbeInFlight = true
    Task { @MainActor [weak self] in
      let started = Date()
      let text = await PTTLanguageIdentifier.shared.transcribe(pcm16k: clip)
      guard let self else { return }
      self.voiceTypingProbeInFlight = false
      guard self.voiceTurnCoordinator.activeTurnID == turnID, self.phase?.isRecording == true else { return }
      // The text, not just its length: a probe that loses the wake word is
      // indistinguishable from one that heard it when all you have is a count.
      log(
        "PushToTalkManager: wake-word probe \(String(format: "%.1f", Double(clip.count / 2) / 16_000))s "
          + "→ \(text.map { "\"\($0.prefix(48))\"" } ?? "nil") in \(Int(Date().timeIntervalSince(started) * 1000))ms")
      guard let text else { return }
      // Lenient: the on-device probe mishears "type" as "Two"/"Tie"/"Typed"
      // from a short opening clip, and a strict match left the turn white for
      // the whole hold. The closing decode still governs the pasted text.
      if self.voiceTypeSession.claim(transcript: text, lenient: true) {
        self.voiceTypingProbeSchedule.decide()
        self.voiceTypingDidArm(turnID: turnID)
      } else if case .rejected = VoiceTypeCommandParser.decide(text) {
        // Not a viable prefix of any wake word or mishearing — a later probe of
        // a longer opening cannot change that. The closing transcript still
        // gets a lenient second opinion at key-up.
        self.voiceTypingProbeSchedule.decide()
      }
    }
  }

  /// The turn has just become a dictation. Whatever model the reducer routed
  /// it to at key-down is released now, not at key-up: a hold can run for
  /// minutes, and streaming those minutes to a realtime model whose answer
  /// will be cancelled is spend for nothing — and its socket's lifetime would
  /// become the dictation's. The user is told the wake word landed; the bar
  /// clears the hint on its own.
  private func voiceTypingDidArm(turnID: VoiceTurnID) {
    if phase?.isRecording == true {
      voiceTurnCoordinator.publish(.dictationRecognized(turnID: turnID))
    }
    guard !voiceTypingReleasedHubTurn, isHubMode || isWaitingForHub else { return }
    voiceTypingReleasedHubTurn = true
    log("PushToTalkManager: dictation armed — releasing the realtime hub turn")
    _ = RealtimeHubController.shared.cancelTurn(turnID: turnID)
  }

  /// Decides from the opening of the whole turn whether this was a dictation,
  /// and only then lets the realtime model have it.
  ///
  /// The mid-hold probes are advisory and can miss the wake word — "type"
  /// opens on a quiet /t/ burst that the trim's pre-roll does not always
  /// preserve. Committed as an ordinary question, the model, hearing "type …",
  /// spawned an agent to do the typing itself: not a missed dictation but an
  /// unrequested action. So every hub commit pays one on-device decode of the
  /// opening (~100–200 ms) first. It is paid at key-up, never while the user
  /// is speaking.
  private func gateHubCommitOnFinalDictationCheck(
    turnID: VoiceTurnID, turnAudio: Data, commit: @escaping () -> Void
  ) {
    let opening = VoiceTypeAudioTrim.opening(of: turnAudio, maxBytes: VoiceTypeWakeWordProbeSchedule.maxProbeBytes)
    guard opening.count >= 12_800 else {
      commit()
      return
    }
    Task { @MainActor [weak self] in
      let started = Date()
      let decoded = await PTTLanguageIdentifier.shared.transcribe(pcm16k: opening)
      let decodeMs = Int(Date().timeIntervalSince(started) * 1000)
      guard let self, self.voiceTurnCoordinator.activeTurnID == turnID else { return }
      // Lenient, like the probes: this is the same on-device model reading the
      // same opening, and it mishears "type" the same ways ("Tie", "Typed").
      // A strict test here would re-open exactly the gap the probes' lenient
      // test closes. The false-positive cost is the one already accepted
      // mid-hold — a rare question opening "tap …" is pasted rather than
      // answered — and the false-negative cost is the model acting on
      // "type …" as an instruction, which was observed live.
      if let decoded, self.voiceTypeSession.claim(transcript: decoded, lenient: true) {
        log(
          "PushToTalkManager: closing decode (\(decodeMs)ms) caught a dictation the probes missed — not committing")
        self.finishVoiceTypingTurn(turnID: turnID, audio: turnAudio, knownTranscript: nil)
        return
      }
      // The one serial cost every committed hub turn pays; logged so the
      // latency is measurable from a real turn rather than estimated.
      log("PushToTalkManager: closing decode (\(decodeMs)ms) heard no wake word — committing")
      commit()
    }
  }

  /// Hands the turn to the realtime model. Reached only once the turn is known
  /// not to be a dictation.
  private func commitHubTurn(turnID: VoiceTurnID, turnAudio: Data, totalSec: Double) {
    // Real speech — commit. The hub speaks the reply and dispatches tools
    // itself; no transcript/router/LLM hop here.
    let commitResult = RealtimeHubController.shared.commitTurn()
    if commitResult == .rejectedNoSession {
      log("PushToTalkManager: realtime hub rejected commit — falling back to buffered transcription")
      batchAudioLock.lock()
      batchAudioBuffer = turnAudio
      batchAudioLock.unlock()
      voiceTurnCoordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
      transcribeBufferedWarmWaitAudio()
      return
    }
    if commitResult == .alreadyOwned {
      log("PushToTalkManager: realtime hub already owns this pending commit — skipping duplicate fallback")
      return
    }
    recordSilentMicRecoveryOutcome(silentMicRecoveryPolicy.recordSuccessfulTurn())
    DesktopDiagnosticsManager.shared.recordPTTCommitted(mode: finalizedMode, hubActive: true)
    // Committed turns must report the same measurements as rejected ones. While
    // this reported a literal 0, admitted and rejected energy were on different
    // scales and the speech gate could not be tuned against its own traffic.
    let (committedPeak, committedRMS) = Self.audioEnergy(pcm16k: turnAudio)
    pttLifecycle.terminate(
      disposition: .committed,
      source: "hub",
      peak: committedPeak,
      rms: committedRMS,
      turnAudioSeconds: totalSec,
      voicedAudioSeconds: nil,
      judgeable: true)
    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: finalizedMode, committed: true, transcriptLength: nil)
    log(
      "PushToTalkManager: hub turn "
        + "\(commitResult == .accepted ? "committed" : "deferred until its realtime session is ready")")
  }

  /// The recognizers a dictation is transcribed with, in order: the backend's
  /// pre-recorded model with the on-screen vocabulary, then the on-device
  /// model. Each switch is recorded, so a backend that keeps losing turns to
  /// the fallback is visible.
  private func makeDictationTranscriber(
    keywords: [String], language: String, allowNetwork: Bool
  ) -> DictationTranscriber {
    DictationTranscriber(
      isOnline: allowNetwork && NetworkReachability.shared.isOnline,
      backend: { audio in
        try await TranscriptionService.batchTranscribe(
          audioData: audio, language: language, contextKeywords: keywords
        ).transcript
      },
      onDevice: { audio in
        // A breath after the last word is not a word, and decoding it invents one.
        guard VoiceTypeAudioTrim.speechBytes(in: audio) >= VoiceTypeAudioTrim.minimumDecodableSpeechBytes
        else { return nil }
        return await PTTLanguageIdentifier.shared.transcribe(
          pcm16k: VoiceTypeAudioTrim.trimmingLeadingSilence(audio))
      },
      didFallBack: { reason in
        await MainActor.run {
          log("PushToTalkManager: backend dictation transcription unavailable (\(reason)) — decoding on-device")
          DesktopDiagnosticsManager.shared.recordFallback(
            area: "voice_typing",
            from: DictationTranscriber.Source.backend.rawValue,
            to: DictationTranscriber.Source.onDevice.rawValue,
            reason: reason == "timeout" ? "timeout" : "other",
            outcome: .degraded)
        }
      })
  }

  /// What one pass of the dictation pipeline produced. Bounded scalars plus
  /// the texts, for the closing turn and for the automation bridge alike.
  struct DictationRun {
    var transcript: String?
    var transcriber = "none"
    /// True when the closing transcript did not read as a dictation (only
    /// the offline route can reach the pipeline unclaimed).
    var notADictation = false
    var text = ""
    var polished = false
    var completion: VoiceTypeSession.Completion = .none
    /// Set when the turn was superseded between steps; nothing was delivered.
    var abandoned = false
  }

  /// The dictation pipeline proper: transcribe once, correct, format, polish,
  /// paste. Shared by the closing turn and by the automation bridge, so a
  /// harness exercises exactly the code a key-up runs.
  ///
  /// - Parameter isCurrent: consulted between steps; a false answer abandons
  ///   the run before anything reaches the focused app.
  private func runDictationPipeline(
    audio: Data,
    knownTranscript: String?,
    keywords: [String],
    language: String,
    appName: String?,
    allowNetwork: Bool,
    isCurrent: () -> Bool
  ) async -> DictationRun {
    var run = DictationRun()
    if let knownTranscript {
      run.transcript = knownTranscript
      run.transcriber = "route"
    } else if let result = await makeDictationTranscriber(
      keywords: keywords, language: language, allowNetwork: allowNetwork
    ).transcribe(audio) {
      run.transcript = result.text
      run.transcriber = result.source.rawValue
    }
    guard isCurrent() else {
      run.abandoned = true
      return run
    }
    guard let transcript = run.transcript else { return run }
    // The chat corrector (`PTTTranscriptContextualCorrector`) deliberately does
    // not run here. Its greeting rule treats the first word of "<word>, …" as a
    // name to respell from the screen: live it turned "So, this is a test" into
    // "Sil, this is a test" and "hello there" into "hello then". Dictation is
    // free text; spelling of names is the polisher's job, with hints.
    guard let payload = voiceTypeSession.payload(from: transcript) else {
      run.notADictation = true
      return run
    }
    var text = DictationFormatter.format(payload, language: language)
    if !text.isEmpty, allowNetwork, NetworkReachability.shared.isOnline,
      let client = try? GeminiClient(model: ModelQoS.Gemini.dictation, workload: .interactive)
    {
      let context = DictationPolisher.Context(
        appName: appName, keywords: DictationPolisher.spellingHints(from: keywords), language: language)
      do {
        if let polished = try await DictationPolisher.polish(text, context: context, using: client) {
          text = polished
          run.polished = true
        } else {
          log("PushToTalkManager: dictation polish rejected — keeping the formatted transcript")
          DesktopDiagnosticsManager.shared.recordFallback(
            area: "voice_typing", from: "llm_polish", to: "local_format", reason: "policy", outcome: .degraded)
        }
      } catch {
        let timedOut = (error as? DictationPolisher.PolishError) == .timedOut
        log(
          "PushToTalkManager: dictation polish \(timedOut ? "timed out" : "failed") — keeping the formatted transcript")
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "voice_typing", from: "llm_polish", to: "local_format",
          reason: timedOut ? "timeout" : "other", outcome: .degraded)
      }
      guard isCurrent() else {
        run.abandoned = true
        return run
      }
    }
    run.text = text
    run.completion = voiceTypeSession.deliver(text)
    return run
  }

  /// How long the bar stays up after a dictation had to be copied rather than
  /// pasted, so the hint saying so can be read. Terminating the turn clears
  /// every hint with it.
  nonisolated static let voiceTypingCopiedHintSeconds: TimeInterval = 1.5
  /// How long the closing turn waits for the journal to accept the dictation
  /// before ending anyway. The paste has already landed; this only bounds
  /// how long the bar keeps showing the turn as in progress.
  nonisolated static let voiceTypingJournalWaitSeconds: TimeInterval = 3

  /// Closes a dictation on any route: the key came up, the whole turn is
  /// transcribed once with the best recognizer that can be reached, cleaned
  /// up, and pasted in one piece. The turn ends without ever having asked a
  /// model to answer anything.
  ///
  /// The reducer stays in `.finalizing` (the bar shows it thinking) until the
  /// paste lands, exactly as it does for a batch-transcribed question. Every
  /// path below ends the turn: `.success` is not available from `.finalizing`
  /// — it requires the provider / tool / journal completion fences, and a
  /// dictation deliberately never reaches a provider — so the turn terminates
  /// the way an intentional Stop does, never as an error, unless nothing could
  /// be transcribed at all.
  ///
  /// - Parameters:
  ///   - audio: the turn's recording, when the caller already drained it from
  ///     the shared buffer; otherwise it is read from there.
  ///   - knownTranscript: a transcript the route already produced (omni STT,
  ///     batch STT after a warm-wait), so the audio is not transcribed twice.
  private func finishVoiceTypingTurn(turnID: VoiceTurnID, audio: Data?, knownTranscript: String?) {
    let turnAudio = audio ?? voiceTypingTurnAudio()
    let totalSec = Double(turnAudio.count / 2) / 16_000
    let keywords = currentContextSnapshot?.keywords ?? []
    let language = AssistantSettings.shared.effectiveTranscriptionLanguage
    let appName = NSWorkspace.shared.frontmostApplication?.localizedName
    let wasClaimed = voiceTypeSession.claimsTurn
    let offlineRoute = isOnDeviceASR
    if isHubMode || isWaitingForHub {
      voiceTypingDidArm(turnID: turnID)
    }
    voiceTypingLastOutcome = VoiceTypingOutcome()
    voiceTypingLastOutcome.probes = voiceTypingProbeSchedule.probesTaken
    voiceTypingLastOutcome.hubReleased = voiceTypingReleasedHubTurn
    log(
      "PushToTalkManager: closing dictation — \(String(format: "%.1f", totalSec))s of audio, "
        + "transcript \(knownTranscript == nil ? "pending" : "from the route")")
    Task { @MainActor [weak self] in
      guard let self else { return }
      let started = Date()
      let run = await self.runDictationPipeline(
        audio: turnAudio,
        knownTranscript: knownTranscript,
        keywords: keywords,
        language: language,
        appName: appName,
        // The route latched offline at key-down stays offline: connectivity
        // that returned mid-hold does not send a turn the user began with no
        // network to the backend.
        allowNetwork: !offlineRoute,
        isCurrent: { [weak self] in self?.voiceTurnCoordinator.activeTurnID == turnID })
      guard !run.abandoned, self.voiceTurnCoordinator.activeTurnID == turnID else { return }
      self.voiceTypingLastOutcome.transcriber = run.transcriber
      // Every outcome below terminates the capture lifecycle exactly once, so
      // a dictation that could not be delivered is still a classified attempt
      // rather than a hole in the telemetry.
      guard run.transcript != nil else {
        log("PushToTalkManager: dictation produced no transcript from any recognizer")
        self.voiceTypeSession.abandon()
        AnalyticsManager.shared.floatingBarPTTEnded(mode: self.finalizedMode, committed: false, transcriptLength: nil)
        self.terminateVoiceTypingLifecycle(disposition: .silentRejected, totalSec: totalSec)
        let reason: VoiceTurnTerminalReason =
          wasClaimed ? .transcriptionFailed : (offlineRoute ? .noNetwork : .silentRejected)
        self.voiceTurnCoordinator.publish(.finish(turnID: turnID, reason: reason))
        return
      }
      if run.notADictation {
        // Only the offline route reaches here unclaimed: its closing transcript
        // is the first anyone has read. Nothing offline can answer a question,
        // and the turn says so rather than reporting a provider that failed.
        log("PushToTalkManager: offline turn was not a dictation — no provider to answer it")
        AnalyticsManager.shared.floatingBarPTTEnded(mode: self.finalizedMode, committed: false, transcriptLength: nil)
        self.terminateVoiceTypingLifecycle(disposition: .cancelled, totalSec: totalSec)
        self.voiceTurnCoordinator.publish(.finish(turnID: turnID, reason: .noNetwork))
        return
      }
      self.voiceTypingLastOutcome.polished = run.polished
      let elapsed = Int(Date().timeIntervalSince(started) * 1000)
      switch run.completion {
      case .none:
        log("PushToTalkManager: dictation had nothing to paste (\(elapsed)ms)")
        AnalyticsManager.shared.floatingBarPTTEnded(mode: self.finalizedMode, committed: false, transcriptLength: nil)
        self.terminateVoiceTypingLifecycle(disposition: .cancelled, totalSec: totalSec)
        self.voiceTurnCoordinator.publish(.cancel(turnID: turnID, reason: .cancelled))
        return
      case .pasted(let delivered):
        self.voiceTypingLastOutcome.delivery = "pasted"
        self.voiceTypingLastOutcome.characters = delivered.count
      case .copied(let delivered):
        self.voiceTypingLastOutcome.delivery = "copied"
        self.voiceTypingLastOutcome.characters = delivered.count
      }
      log(
        "PushToTalkManager: dictation \(self.voiceTypingLastOutcome.delivery) — "
          + "\(self.voiceTypingLastOutcome.characters) chars via \(run.transcriber)"
          + "\(run.polished ? ", polished" : "") in \(elapsed)ms")
      AnalyticsManager.shared.floatingBarPTTEnded(
        mode: self.finalizedMode, committed: true, transcriptLength: self.voiceTypingLastOutcome.characters)
      self.terminateVoiceTypingLifecycle(disposition: .committed, totalSec: totalSec)
      // The journal write is awaited before the turn ends, so a lifecycle
      // change at turn end cannot drop it; the wait is bounded so a slow
      // bridge cannot hold the bar, and the write itself is not cancelled
      // at the bound — it finishes in the background.
      let utterance = run.transcript ?? ""
      let completion = run.completion
      let journal = Task { @MainActor in
        await self.recordVoiceTypingExchange(utterance: utterance, completion: completion, turnID: turnID)
      }
      let journaled =
        (try? await DeadlinedOperation.run(seconds: Self.voiceTypingJournalWaitSeconds) { await journal.value })
        ?? false
      if !journaled {
        log("PushToTalkManager: voice typing exchange not confirmed journaled before the turn ended")
      }
      guard self.voiceTurnCoordinator.activeTurnID == turnID else { return }
      if case .copied = run.completion {
        self.voiceTurnCoordinator.publish(.hintChanged(turnID: turnID, text: "Copied — press ⌘V to paste"))
        try? await Task.sleep(nanoseconds: UInt64(Self.voiceTypingCopiedHintSeconds * 1_000_000_000))
        guard self.voiceTurnCoordinator.activeTurnID == turnID else { return }
      }
      self.voiceTurnCoordinator.publish(.cancel(turnID: turnID, reason: .cancelled))
    }
  }

  private func terminateVoiceTypingLifecycle(
    disposition: PTTAttemptLifecycleRecorder.TurnDisposition, totalSec: Double
  ) {
    pttLifecycle.terminate(
      disposition: disposition,
      source: "voice_typing",
      peak: nil,
      rms: nil,
      turnAudioSeconds: totalSec,
      voicedAudioSeconds: nil,
      judgeable: true)
  }

  /// Runs the dictation pipeline on a recording without a voice turn, for the
  /// automation bridge: the same transcription, cleanup, and paste a key-up
  /// performs, into whatever application is frontmost. Refused while a real
  /// turn is active, and abandoned — before anything reaches the focused app —
  /// if one starts while the recording is being transcribed or polished, so
  /// it can never paste into the middle of a real turn. The real turn's
  /// `begin()` owns the session from that moment; the automation neither
  /// claims nor resets it afterwards.
  func dictateForAutomation(pcm16k: Data, allowNetwork: Bool) async -> [String: String] {
    guard currentVoiceTurnID == nil else { return ["error": "a voice turn is active"] }
    voiceTypeSession.begin()
    voiceTypeSession.noteRelease()
    let started = Date()
    let run = await runDictationPipeline(
      audio: pcm16k,
      knownTranscript: nil,
      keywords: [],
      language: AssistantSettings.shared.effectiveTranscriptionLanguage,
      appName: NSWorkspace.shared.frontmostApplication?.localizedName,
      allowNetwork: allowNetwork,
      isCurrent: { [weak self] in self?.currentVoiceTurnID == nil })
    guard !run.abandoned, currentVoiceTurnID == nil else {
      return ["error": "a voice turn started while the recording was being transcribed — nothing was pasted"]
    }
    voiceTypeSession.abandon()
    let delivery: String
    switch run.completion {
    case .none: delivery = "none"
    case .pasted: delivery = "pasted"
    case .copied: delivery = "copied"
    }
    return [
      "accessibility_trusted": AXIsProcessTrusted() ? "true" : "false",
      "online": (allowNetwork && NetworkReachability.shared.isOnline) ? "true" : "false",
      "transcript": run.transcript ?? "",
      "transcriber": run.transcriber,
      "not_a_dictation": run.notADictation ? "true" : "false",
      "text": run.text,
      "polished": run.polished ? "true" : "false",
      "delivery": delivery,
      "elapsed_ms": "\(Int(Date().timeIntervalSince(started) * 1000))",
    ]
  }

  /// Puts a dictated turn in the chat transcript as `Typed: <text>`.
  ///
  /// A dictation is still something the user said to Omi, so it belongs in the
  /// same journal as a spoken question: without it the next turn cannot refer
  /// back to what was just written. This goes through the ordinary journal
  /// exchange the realtime voice surface already uses, so the record persists
  /// and enters conversation context exactly like every other voice turn. The
  /// continuity key is derived from the turn, so a retry cannot write a second
  /// copy.
  /// Returns whether the journal accepted the exchange.
  private func recordVoiceTypingExchange(
    utterance: String, completion: VoiceTypeSession.Completion, turnID: VoiceTurnID
  ) async -> Bool {
    guard let delivered = completion.text?.trimmingCharacters(in: .whitespacesAndNewlines), !delivered.isEmpty
    else { return false }
    let assistantText: String
    if case .copied = completion {
      assistantText = "Copied to clipboard: \(delivered)"
    } else {
      assistantText = "Typed: \(delivered)"
    }
    let manager = FloatingControlBarManager.shared
    // `realtime_voice`, not a voice-typing origin of its own: the journal
    // runtime accepts a closed set of origins (agent/src/index.ts), and a
    // dictation is a realtime voice turn — one that types instead of asking.
    // The "Typed:" prefix is what distinguishes it in the transcript.
    let recorded = await manager.recordExchange(
      surface: manager.realtimeVoiceSurfaceReference(),
      userText: utterance,
      assistantText: assistantText,
      origin: "realtime_voice",
      continuityKey: "voice-typing-\(turnID)")
    if !recorded {
      log("PushToTalkManager: voice typing exchange not journaled")
    }
    return recorded
  }

  private func handleTranscriptSegments(_ segments: [TranscriptionService.BackendSegment]) {
    guard
      phase?.isRecording == true || phase == .finalizing
    else { return }

    for segment in segments {
      transcriptSegments.append(segment.text)
    }
    lastInterimText = ""

    // In finalizing state, segments mean backend is done — send immediately
    if phase == .finalizing {
      log("PushToTalkManager: received transcript during finalization — sending now")
      if let turnID = currentVoiceTurnID {
        sendTranscript(turnID: turnID)
      }
    }
  }

  // MARK: - Bar State Sync

  private func updateBarState(skipResize: Bool = false) {
    _ = skipResize
    voiceTurnCoordinator.refreshPresentation()
  }
}

// MARK: - Realtime Omni STT integration
//
// When "Realtime Voice" is enabled, one omni model (Gemini 3.1 Flash Live or
// GPT Realtime 2) transcribes the PTT turn instead of Deepgram. The final
// transcript flows through the unchanged sendTranscript() → ChatProvider path,
// so agents, tools, memory, vision, and the text input all keep working.
extension PushToTalkManager {

  /// Starts realtime omni STT via the omi backend relay. Always returns true
  /// (omni is the floating bar's STT); on auth failure it stops the turn.
  @discardableResult
  fileprivate func startOmniTranscription(captureAlreadyRunning: Bool = false) -> Bool {
    guard let startingTurnID = currentVoiceTurnID else { return false }
    guard let identity = voiceTurnCoordinator.reserveEffectIdentity() else { return false }
    voiceTurnCoordinator.publish(
      .transcriptionProviderStartedScoped(turnID: startingTurnID, identity: identity))
    guard voiceTurnCoordinator.activeTurn?.transcriptionEffectIdentity == identity else {
      return false
    }
    let delegateProxy = VoiceTurnOmniDelegateProxy(owner: self, identity: identity)
    omniDelegateProxy = delegateProxy
    let provider = RealtimeOmniSettings.shared.effectiveProvider
    if let turnID = currentVoiceTurnID {
      voiceTurnCoordinator.publish(.selectRoute(turnID: turnID, route: .omniSTT))
    }
    if captureAlreadyRunning {
      batchAudioLock.lock()
      let bufferedAudio = batchAudioBuffer
      batchAudioLock.unlock()
      omniPreconnectBuffer = bufferedAudio.isEmpty ? [] : [bufferedAudio]
      log(
        "PushToTalkManager: omni STT reusing "
          + "\(String(format: "%.2f", Double(bufferedAudio.count / 2) / 16000.0))s buffered audio")
    } else {
      omniPreconnectBuffer.removeAll()
      // Keep a copy of the whole turn so we can fall back to Deepgram if the relay
      // is unreachable (e.g. backend not yet on prod) — PTT must never break.
      batchAudioLock.lock()
      batchAudioBuffer = Data()
      batchAudioLock.unlock()
      startMicCapture(overrideDeviceID: preferredPTTInputOverrideDeviceID())  // route PTT input override (user mic / Bluetooth built-in fallback)
    }
    Task { @MainActor [weak self] in
      guard let self, self.isOmniSTT,
        self.voiceTurnCoordinator.activeTurnID == startingTurnID,
        self.voiceTurnCoordinator.activeTurn?.transcriptionEffectIdentity == identity,
        self.omniDelegateProxy === delegateProxy
      else { return }
      do {
        let authHeader = try await AuthService.shared.getAuthHeader()
        guard self.voiceTurnCoordinator.activeTurnID == startingTurnID,
          self.voiceTurnCoordinator.activeTurn?.transcriptionEffectIdentity == identity,
          self.omniDelegateProxy === delegateProxy
        else { return }
        let base = DesktopBackendEnvironment.pythonBaseURL()
        let service = RealtimeOmniService(
          provider: provider, relayBaseURL: base, authHeader: authHeader, sttOnly: true,
          delegate: delegateProxy)
        self.realtimeOmniService = service
        // Flush anything captured while we were fetching auth.
        for raw in self.omniPreconnectBuffer { service.sendAudio(self.resampleForOmni(raw)) }
        self.omniPreconnectBuffer.removeAll()
        service.start()
        log("PushToTalkManager: started omni STT (\(provider.displayName)) via backend relay")
      } catch {
        logError("PushToTalkManager: omni auth failed", error: error)
        guard self.voiceTurnCoordinator.activeTurnID == startingTurnID,
          self.voiceTurnCoordinator.activeTurn?.transcriptionEffectIdentity == identity,
          self.omniDelegateProxy === delegateProxy
        else { return }
        self.voiceTurnCoordinator.publish(
          .transcriptionFailed(turnID: startingTurnID, message: error.localizedDescription))
      }
    }
    return true
  }

  // Phase 1 key resolution: env (dev) → TODO BYOK / backend-minted token.
  fileprivate func resolveOmniKey(for provider: RealtimeOmniProvider) -> String? {
    let env = ProcessInfo.processInfo.environment
    let raw: String?
    switch provider {
    case .gptRealtime2: raw = env["OPENAI_API_KEY"]
    case .geminiFlashLive, .auto: raw = env["GEMINI_API_KEY"] ?? env["GOOGLE_API_KEY"]
    }
    guard let raw, !raw.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
    return raw
  }

  // Mic is 16kHz PCM16; OpenAI realtime requires ≥24kHz, Gemini wants 16kHz.
  fileprivate func resampleForOmni(_ pcm16k: Data) -> Data {
    guard let target = realtimeOmniService?.requiredInputSampleRate, target != 16000 else { return pcm16k }
    return Self.resamplePCM16(pcm16k, from: 16000, to: target)
  }

  static func resamplePCM16(_ data: Data, from src: Int, to dst: Int) -> Data {
    let count = data.count / 2
    guard count > 1, src != dst else { return data }
    var input = [Int16](repeating: 0, count: count)
    _ = input.withUnsafeMutableBytes { data.copyBytes(to: $0, count: count * 2) }
    let ratio = Double(src) / Double(dst)
    let outCount = max(1, Int(Double(count) / ratio))
    var out = [Int16](repeating: 0, count: outCount)
    for i in 0..<outCount {
      let pos = Double(i) * ratio
      let i0 = Int(pos)
      let i1 = Swift.min(i0 + 1, count - 1)
      let frac = pos - Double(i0)
      let s = Double(input[i0]) * (1 - frac) + Double(input[i1]) * frac
      out[i] = Int16(Swift.max(-32768, Swift.min(32767, s)))
    }
    return out.withUnsafeBytes { Data($0) }
  }

  // MARK: RealtimeOmniServiceDelegate

  fileprivate func omniDidConnect(identity: VoiceEffectIdentity) {
    guard ownsOmniEffect(identity) else { return }
    log("PushToTalkManager: omni STT connected")
  }

  fileprivate func omniDidReceiveInputTranscript(
    _ text: String,
    isFinal: Bool,
    itemID: String?,
    identity: VoiceEffectIdentity
  ) {
    guard ownsOmniEffect(identity), let turnID = currentVoiceTurnID else { return }
    guard phase?.isRecording == true || phase == .finalizing else { return }
    if isFinal {
      let finalText = text.isEmpty ? lastInterimText : text
      let trimmed = finalText.trimmingCharacters(in: .whitespacesAndNewlines)
      // Dedup by the provider's stable item id (a relay re-delivering the SAME
      // final), NOT by text — keying on text silently dropped legitimately
      // repeated phrases within a turn ("yes. yes." → "yes"). With no id a final
      // can't be a relay re-delivery, so always keep it (a genuine repeat is
      // never lost) rather than minting a throwaway key.
      if !trimmed.isEmpty {
        if let itemID {
          if seenFinalSegmentIDs.insert(itemID).inserted {
            transcriptSegments.append(trimmed)
          }
        } else {
          transcriptSegments.append(trimmed)
        }
      }
      lastInterimText = ""
      if phase == .finalizing {
        guard claimOmniCompletion(identity) else { return }
        sendTranscript(turnID: turnID)
      }
    } else {
      lastInterimText += text
      voiceTurnCoordinator.publish(.transcriptChanged(turnID: turnID, text: lastInterimText))
    }
  }

  fileprivate func omniDidReceiveAudio(_ pcm24k: Data, identity: VoiceEffectIdentity) {
    guard ownsOmniEffect(identity) else { return }
    // STT-only: the omni model's own voice is unused; Claude's reply is spoken
    // by the existing FloatingBarVoicePlaybackService.
  }

  fileprivate func omniDidFinishTurn(identity: VoiceEffectIdentity) {
    if phase == .finalizing, let turnID = currentVoiceTurnID,
      ownsOmniEffect(identity)
    {
      guard claimOmniCompletion(identity) else { return }
      sendTranscript(turnID: turnID)
    }
  }

  fileprivate func omniDidError(_ message: String, identity: VoiceEffectIdentity) {
    guard ownsOmniEffect(identity),
      voiceTurnCoordinator.activeTurn?.transcriptionCompletionClaimed == false
    else { return }
    logError("PushToTalkManager: omni STT error: \(message)")
    // Benign ONLY if the turn already completed (final transcript sent). A mid-turn relay
    // death — even after a spurious interim like "Olha olha" that set omniReceivedTranscript
    // — must NOT be ignored, or the turn is lost (garbage/no reply). The full turn audio is
    // always buffered in batchAudioBuffer, so we re-transcribe it through routed batch STT.
    guard phase?.isRecording == true || phase == .finalizing
    else { return }
    // Kill the dead relay so finalize() doesn't wait on it; the mic keeps buffering.
    realtimeOmniService?.stop()
    realtimeOmniService = nil
    // If the user already released, transcribe the buffered turn now. If they're still
    // holding, keep capturing — finalize()'s dead-relay branch falls back to batch STT with
    // the full turn audio (avoids cutting them off mid-sentence).
    if phase == .finalizing {
      fallBackToBatchTranscription(reason: "other")
    }
  }

  /// Transcribe the buffered turn audio through the backend's selected batch-STT provider.
  fileprivate func fallBackToBatchTranscription(reason: String = "other") {
    guard let identity = voiceTurnCoordinator.activeTurn?.transcriptionEffectIdentity,
      claimOmniCompletion(identity)
    else { return }
    log("PushToTalkManager: omni unavailable — falling back to backend batch STT for this turn")
    realtimeOmniService?.stop()
    realtimeOmniService = nil
    batchAudioLock.lock()
    let audio = batchAudioBuffer
    batchAudioLock.unlock()
    guard let turnID = currentVoiceTurnID,
      voiceTurnCoordinator.activeTurnID == turnID
    else { return }
    if voiceTurnCoordinator.activeTurn?.transcriptionFinalizationMode != nil {
      voiceTurnCoordinator.publish(.transcriptionFinalizationCompleted(turnID: turnID))
    }
    guard !audio.isEmpty else {
      sendTranscript(turnID: turnID)
      return
    }
    voiceTurnCoordinator.publish(.transcriptChanged(turnID: turnID, text: VoiceTurnUICopy.transcribingProgress))
    voiceTurnCoordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
    let capturedReason = reason
    Task { @MainActor [weak self] in
      guard let self, self.voiceTurnCoordinator.activeTurnID == turnID else { return }
      do {
        let language = AssistantSettings.shared.effectiveTranscriptionLanguage
        let batchResult = try await TranscriptionService.batchTranscribe(
          audioData: audio, language: language,
          contextKeywords: self.currentContextSnapshot?.keywords ?? [])
        guard self.voiceTurnCoordinator.activeTurnID == turnID else { return }
        let provider = batchResult.provider ?? "unknown"
        let model = batchResult.model ?? "unknown"
        log("PushToTalkManager: omni batch fallback selected provider=\(provider) model=\(model)")
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "ptt_cascade",
          from: "omni",
          to: provider,
          reason: capturedReason,
          outcome: .recovered,
          extra: ["stt_provider": provider, "stt_model": model, "user_visible": false])
        if let transcript = batchResult.transcript, !transcript.isEmpty { self.transcriptSegments = [transcript] }
      } catch {
        logError("PushToTalkManager: batch-STT fallback failed", error: error)
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "ptt_cascade",
          from: "omni",
          to: "batch_stt",
          reason: capturedReason,
          outcome: .exhausted,
          extra: ["stt_provider": "unknown", "stt_model": "unknown", "user_visible": false])
        self.voiceTurnCoordinator.publish(
          .transcriptionFailed(turnID: turnID, message: error.localizedDescription))
        return
      }
      self.sendTranscript(turnID: turnID)
    }
  }

  private func ownsOmniEffect(_ identity: VoiceEffectIdentity) -> Bool {
    guard let turn = voiceTurnCoordinator.activeTurn else { return false }
    return turn.id.rawValue == identity.generation
      && turn.transcriptionEffectIdentity == identity
      && omniDelegateProxy?.identity == identity
  }

  private func claimOmniCompletion(_ identity: VoiceEffectIdentity) -> Bool {
    guard ownsOmniEffect(identity),
      voiceTurnCoordinator.activeTurn?.transcriptionCompletionClaimed == false,
      let turnID = currentVoiceTurnID
    else { return false }
    voiceTurnCoordinator.publish(
      .transcriptionCompletionClaimedScoped(turnID: turnID, identity: identity))
    return voiceTurnCoordinator.activeTurn?.transcriptionEffectIdentity == identity
      && voiceTurnCoordinator.activeTurn?.transcriptionCompletionClaimed == true
  }
}

/// Routing state the mic-frame closures consult per chunk. Lock-guarded so a
/// parked capture can be leased to a later turn without reinstalling IOProc
/// closures. Deliberately a top-level type: nesting it in the @MainActor
/// manager would inherit that isolation and forbid the lock calls the
/// @Sendable audio closures make off the main actor.
/// @unchecked Sendable: every stored property is read and written under `lock`.
final class MicCaptureLease: @unchecked Sendable {
  private let lock = NSLock()
  private var generation: UInt64
  private var batchMode: Bool
  private var turnID: VoiceTurnID
  private var parked = false

  init(generation: UInt64, batchMode: Bool, turnID: VoiceTurnID) {
    self.generation = generation
    self.batchMode = batchMode
    self.turnID = turnID
  }

  func renew(generation: UInt64, batchMode: Bool, turnID: VoiceTurnID) {
    lock.lock()
    self.generation = generation
    self.batchMode = batchMode
    self.turnID = turnID
    self.parked = false
    lock.unlock()
  }

  /// Marks the lease revoked while its capture idles in the keep-alive park,
  /// so audio callbacks can drop frames synchronously instead of allocating a
  /// main-actor task per buffer for up to the whole park window.
  func setParked(_ value: Bool) {
    lock.lock()
    parked = value
    lock.unlock()
  }

  /// Snapshot for frame authority — nil while parked (frame must be dropped).
  func snapshotIfActive() -> (generation: UInt64, batchMode: Bool, turnID: VoiceTurnID)? {
    lock.lock()
    defer { lock.unlock() }
    if parked { return nil }
    return (generation, batchMode, turnID)
  }

  func snapshot() -> (generation: UInt64, batchMode: Bool, turnID: VoiceTurnID) {
    lock.lock()
    defer { lock.unlock() }
    return (generation, batchMode, turnID)
  }
}
