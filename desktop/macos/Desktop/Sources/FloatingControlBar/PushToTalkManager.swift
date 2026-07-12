import AVFoundation
import Cocoa
import Combine
import CoreAudio
import OmiSupport

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

  mutating func recordSuccessfulTurn() {
    consecutiveDeadMicTurns = 0
  }

  mutating func recordCaptureRebuild() {
    consecutiveDeadMicTurns = 0
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
  private var barState: FloatingControlBarState?
  private var automationBarState: FloatingControlBarState?
  private var automationCaptureBypass = false

  // Double-tap detection
  private var lastOptionDownTime: TimeInterval = 0
  private var lastOptionUpTime: TimeInterval = 0
  private let doubleTapThreshold: TimeInterval = 0.4
  private let tapToLockMaxHoldDuration: TimeInterval = 0.22

  // Transcription
  private var transcriptionService: TranscriptionService?
  // Realtime omni STT (replaces Deepgram). Connects through the omi backend relay.
  private var realtimeOmniService: RealtimeOmniService?
  private var omniDelegateProxy: VoiceTurnOmniDelegateProxy?
  // Realtime-as-hub (Phase 1): when active, the realtime model is THE hub — it does
  // in-session STT + reasoning + routing (tool choice) + speaks the reply. Mic PCM is
  // streamed to RealtimeHubController; there is no transcript→router→ChatProvider hop.
  /// When set, the next finalized PTT turn is a voice follow-up to this agent pill:
  /// it uses the realtime omni STT and routes the transcript into the pill's agent
  /// session (RealtimeHub pipeline), NOT the floating bar or the hub model.
  private var followUpPill: AgentPill?
  // Mic chunks captured before the relay finishes connecting (raw 16k PCM),
  // flushed once the service exists so the user's first words aren't clipped.
  private var omniPreconnectBuffer: [Data] = []
  // True once the omni model returned any transcript this turn — gates the
  // Batch-STT fallback so a benign trailing socket error doesn't trigger it.
  private var audioCaptureService: AudioCaptureService?
  private var micCaptureStartInFlight = false
  private var silentMicRecoveryPolicy = PTTSilentMicRecoveryPolicy()
  private var micCaptureGeneration: UInt64 = 0
  private var transcriptSegments: [String] = []
  // Stable provider item ids of finals already appended this turn. Dedup relay
  // re-deliveries by id, never by text (INV-6: never dedupe by user text), so a
  // legitimately repeated phrase within a turn is not silently dropped. Reset
  // wherever transcriptSegments is reset.
  private var seenFinalSegmentIDs: Set<String> = []
  private var lastInterimText: String = ""
  private var hasMicPermission: Bool = false
  private var isCurrentSessionFollowUp = false
  private var currentContextSnapshot: PTTContextSnapshot?
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
    installEventMonitors()
    // Realtime hub: wire it to the bar and warm the WS if it's enabled + BYOK-keyed,
    // so the persistent socket is ready before the first PTT (and stays warm after).
    RealtimeHubController.shared.setup()
    // Hermetic local harness has no Firebase SDK and no live realtime providers.
    if !DesktopLocalProfile.isEnabled {
      RealtimeHubController.shared.ensureWarm()
    }
    log("PushToTalkManager: setup complete, micPermission=\(hasMicPermission)")
  }

  private func configureVoiceTurnCoordinator(barState: FloatingControlBarState) {
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
      continueFinalization()
    case .activateHub(let turnID, _):
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
    case .finalizeJournal(let turnID, let identity):
      guard voiceTurnCoordinator.activeTurnID == turnID else { return }
      if Self.isHubRoute(voiceTurnCoordinator.activeTurn?.route ?? .undecided) {
        RealtimeHubController.shared.finalizeJournal(turnID: turnID, identity: identity)
      }
    case .cancelHub(let turnID, let route):
      if Self.isHubRoute(route) {
        _ = RealtimeHubController.shared.cancelTurn(turnID: turnID)
      }
    case .fallbackToTranscription(let turnID, _):
      guard voiceTurnCoordinator.activeTurnID == turnID else { return }
      resolveRealtimeHubWarmWait(ready: false)
    case .stopPlayback(let lease):
      if lease.lane == .nativeRealtime {
        _ = RealtimeHubController.shared.stopNativePlayback(lease: lease)
      } else {
        _ = FloatingBarVoicePlaybackService.shared.interruptCurrentResponse(leaseID: lease.id)
      }
    case .terminal(let record):
      RealtimeHubController.shared.voiceTurnDidTerminate(turnID: record.turnID)
      performTerminalCleanup(discardBufferedAudio: record.reason == .ownerChanged)
    case .scheduleDeadline, .cancelDeadline, .cancelAllDeadlines,
         .staleEventDropped, .invalidTransition:
      break
    }
  }

  nonisolated static func isHubRoute(_ route: VoiceTurnRoute) -> Bool {
    switch route {
    case .hub, .hubWarmWait:
      return true
    case .undecided, .omniSTT, .deepgramBatch, .deepgramLive, .agentFollowUp:
      return false
    }
  }

  // MARK: - Shortcut Handling

  private func handleShortcutEvent(_ event: NSEvent) {
    guard ShortcutSettings.shared.pttEnabled else { return }
    let shortcut = ShortcutSettings.shared.pttShortcut

    let pttActive: Bool
    switch event.type {
    case .flagsChanged:
      guard shortcut.modifierOnly else { return }
      pttActive = shortcut.matchesFlagsChanged(event)
    case .keyDown:
      guard !shortcut.modifierOnly, !event.isARepeat else { return }
      pttActive = shortcut.matchesKeyDown(event)
    case .keyUp:
      guard !shortcut.modifierOnly else { return }
      pttActive = false
      if shortcut.matchesKeyUp(event) {
        handleShortcutUp()
      }
      return
    default:
      return
    }

    // Let the first shortcut press reveal the compact bar instead of requiring it
    // to already be visible. This keeps onboarding step 3 quiet on entry while
    // still allowing the user to trigger the bar by pressing the key.
    if pttActive, !FloatingControlBarManager.shared.isVisible {
      FloatingControlBarManager.shared.show()
    }

    guard FloatingControlBarManager.shared.isVisible else { return }

    if pttActive {
      handleShortcutDown()
    } else if shortcut.modifierOnly {
      handleShortcutUp()
    }
  }

  private func handleShortcutDown() {
    let now = ProcessInfo.processInfo.systemUptime

    switch phase {
    case .idle, .awaitingResponse, .awaitingTools, .awaitingJournal, .playing, .terminal, .none:
      // Check for double-tap: if last Option-up was recent, enter locked mode
      if ShortcutSettings.shared.doubleTapForLock && (now - lastOptionUpTime) < doubleTapThreshold {
        lastOptionUpTime = 0
        enterLockedListening()
      } else {
        lastOptionDownTime = now
        startListening()
      }

    case .recording:
      // Already listening (hold mode), ignore repeated flagsChanged
      break

    case .pendingLockDecision:
      stopListening()
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

      if ShortcutSettings.shared.doubleTapForLock && holdDuration < tapToLockMaxHoldDuration {
        lastOptionUpTime = now
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
    guard !APIKeyService.isByokActive, FloatingBarUsageLimiter.shared.isLimitReached else { return false }
    log("PushToTalkManager: PTT blocked — monthly free-tier chat limit reached")
    NotificationCenter.default.post(
      name: .showUsageLimitPopup, object: nil, userInfo: ["reason": "ptt"])
    return true
  }

  private func startListening() {
    guard isIdle || phase == .pendingLockDecision else {
      log("PushToTalkManager: startListening ignored — phase=\(String(describing: phase))")
      return
    }
    if isBlockedByUsageLimit() { return }
    _ = voiceTurnCoordinator.begin(intent: followUpPill == nil ? .hold : .agentFollowUp)
    RealtimeHubController.shared.prefetchVoiceContextSnapshotIfNeeded()
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
      hubActive: RealtimeHubController.shared.isActive,
      micPermissionGranted: refreshedMicPermission())
    let preOverlayImage = ScreenCaptureManager.captureScreenImage()
    updateBarState()

    captureContextAndStartAudio(preOverlayImage: preOverlayImage)
    log("PushToTalkManager: started listening (mode=\(mode))")
  }

  private func enterLockedListening() {
    if isBlockedByUsageLimit() { return }
    RealtimeHubController.shared.prefetchVoiceContextSnapshotIfNeeded()
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
    if ShortcutSettings.shared.pttMuteSystemAudio {
      SystemAudioMuteController.shared.muteForListening()
    }
    if let turnID = currentVoiceTurnID,
      voiceTurnCoordinator.activeTurnID == turnID
    {
      voiceTurnCoordinator.send(.lock(turnID: turnID))
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
      hubActive: RealtimeHubController.shared.isActive,
      micPermissionGranted: refreshedMicPermission())

    // If we were already listening from the first tap, keep going.
    // Otherwise start fresh.
    if transcriptionService == nil {
      if activeTracer == nil { startActiveTracer() }
      transcriptSegments = []
      seenFinalSegmentIDs.removeAll()
      lastInterimText = ""
      currentContextSnapshot = nil
      let preOverlayImage = ScreenCaptureManager.captureScreenImage()
      captureContextAndStartAudio(preOverlayImage: preOverlayImage)
    }

    updateBarState()
    log("PushToTalkManager: entered locked listening mode (mode=\(mode))")
  }

  private func enterPendingLockDecision() {
    guard phase == .recording else { return }
    guard let turnID = currentVoiceTurnID else { return }
    voiceTurnCoordinator.send(.openLockWindow(turnID: turnID))
    stopMicCapture()
    updateBarState()
  }

  private func stopListening() {
    if let turnID = currentVoiceTurnID,
      voiceTurnCoordinator.activeTurnID == turnID
    {
      voiceTurnCoordinator.send(.cancel(turnID: turnID, reason: .cancelled))
      return
    }
    performTerminalCleanup()
  }

  private func performTerminalCleanup(discardBufferedAudio: Bool = false) {
    // Always restore audio on teardown (cancel, error, cleanup) so we never leave it muted.
    SystemAudioMuteController.shared.restore()
    contextCaptureTask?.cancel()
    contextCaptureTask = nil
    micCaptureStartInFlight = false
    if followUpPill != nil {
      followUpPill = nil
      AgentPillsManager.shared.recordingPillID = nil
    }
    stopAudioTranscription(discardBufferedAudio: discardBufferedAudio)
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
  }

  /// Drain every previous-owner voice authority before the defaults/auth owner
  /// mutation becomes visible. Logical termination enters through the reducer;
  /// the remaining calls close idle/warm physical resources that have no active
  /// turn and therefore cannot be represented by a reducer effect.
  func quiesceForEffectiveOwnerTransition(
    previousOwnerID: String?,
    cleanupCapability: RuntimeOwnerTransitionCleanupCapability
  ) async {
    guard RuntimeOwnerIdentity.authorizesTransitionCleanup(
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

  // MARK: - Agent voice follow-up

  /// Begin a voice follow-up to a specific agent pill (the pill's mic button). Reuses
  /// the realtime omni STT capture; the transcript routes to the agent's session via
  /// AgentPillsManager.continueAgent (not the floating bar / hub model).
  func startPillFollowUp(for pill: AgentPill) {
    guard isIdle else {
      log("PushToTalkManager: follow-up ignored — PTT busy (phase=\(String(describing: phase)))")
      AgentPillsManager.shared.recordingPillID = nil
      return
    }
    log("PushToTalkManager: voice follow-up START for agent \(pill.title)")
    followUpPill = pill
    startListening()
  }

  /// End the in-progress voice follow-up (second mic tap) and send it to the agent.
  func endPillFollowUp() {
    guard followUpPill != nil, !isIdle else { return }
    log("PushToTalkManager: voice follow-up END — finalizing")
    finalize()
  }

  /// Cancel an in-progress voice follow-up for a pill that was dismissed.
  func cancelPillFollowUp(for pillID: UUID) {
    guard followUpPill?.id == pillID else { return }
    log("PushToTalkManager: voice follow-up CANCEL for dismissed agent")
    stopListening()
  }

  // MARK: - Automation (headless PTT for the desktop bridge)

  /// Begin a push-to-talk capture exactly as the shortcut key-down does
  /// (`handleShortcutDown` → `startListening`), so the automation bridge can drive
  /// MIC-01 without synthetic key events. `startListening()`'s own guard makes this a
  /// no-op when PTT is busy; the returned state lets the caller confirm. Pairs with
  /// `endPushToTalkForAutomation()`.
  @discardableResult
  func beginPushToTalkForAutomation() -> [String: String] {
    if barState == nil {
      let state = FloatingControlBarState()
      automationBarState = state
      barState = state
      configureVoiceTurnCoordinator(barState: state)
    }
    automationCaptureBypass = true
    startListening()
    let isRecording = voiceTurnCoordinator.activeTurn?.phase.isRecording == true
    if !isRecording { automationCaptureBypass = false }
    return ["state": VoiceTurnCoordinator.phaseLabel(phase ?? .idle), "listening": isRecording ? "true" : "false"]
  }

  /// Release an in-progress push-to-talk capture the same way a long-hold key-up does
  /// (`handleShortcutUp` .listening branch → `finalize`), producing the final
  /// transcript. Releasing with no captured audio exercises the empty-batch path,
  /// which must end the turn with a hint rather than hang. No-op unless a capture is
  /// active.
  @discardableResult
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
  nonisolated private static let minTurnAudioSeconds: Double = 0.35
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

  private func finalize() {
    guard phase?.isRecording == true else { return }
    guard let turnID = currentVoiceTurnID else { return }
    voiceTurnCoordinator.send(.finalize(turnID: turnID))
  }

  private func continueFinalization() {
    guard let turnID = currentVoiceTurnID,
      voiceTurnCoordinator.activeTurnID == turnID,
      voiceTurnCoordinator.activeTurn?.phase == .finalizing
    else { return }
    lastOptionUpTime = 0
    // Dictation is over — restore any audio we muted so the track resumes immediately.
    SystemAudioMuteController.shared.restore()
    finalizedMode = currentPTTMode()

    // The reducer emitted stopCapture before entering this effect continuation.
    activeTracer?.end("audio_capture")
    activeTracer?.end("ptt_recording")

    if isWaitingForHub {
      voiceTurnCoordinator.send(.responseWaitingChanged(turnID: turnID, active: true))
      updateBarState()
      log("PushToTalkManager: finalizing while realtime hub warms — holding buffered audio")
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
        let attemptRecovery = silentMicRecoveryPolicy.recordDiscardedTurn(totalSec: totalSec, peak: peak)
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
          recoveryAction: attemptRecovery ? "capture_rebuild" : "none",
          recoveryResult: attemptRecovery ? "attempted" : "not_attempted")
        log(
          "PushToTalkManager: discarding hub turn — audio \(String(format: "%.2f", totalSec))s "
            + "peak=\(peak)/32767 rms=\(rms) device=[\(dev)] "
            + "(peak≈0 ⇒ dead mic; high peak ⇒ classifier misfire; low ⇒ quiet/far mic) — not committing"
        )
        if attemptRecovery {
          requestCoreAudioCaptureRecovery(reason: "repeated dead-mic PTT turns", restartPTT: false, batchMode: false)
        }
        _ = RealtimeHubController.shared.cancelTurn(turnID: turnID)
        AnalyticsManager.shared.floatingBarPTTEnded(
          mode: finalizedMode, hadTranscript: false, transcriptLength: 0)
        // Too short to have captured anything (fast tap / capture not ready) — hint
        // the user to hold longer instead of clearing silently. A longer hub turn
        // that simply had no speech keeps the quiet reset.
        if totalSec < Self.minTurnAudioSeconds {
          finishTooShortPTTTurnWithHint(reason: "hub, \(String(format: "%.2f", totalSec))s")
        } else {
          voiceTurnCoordinator.send(.finish(turnID: turnID, reason: .silentRejected))
        }
        return
      }
      // Real speech — commit. The hub speaks the reply and dispatches tools
      // itself; no transcript/router/LLM hop here.
      let commitResult = RealtimeHubController.shared.commitTurn()
      if commitResult == .rejectedNoSession {
        log("PushToTalkManager: realtime hub rejected commit — falling back to buffered transcription")
        batchAudioLock.lock()
        batchAudioBuffer = turnAudio
        batchAudioLock.unlock()
        voiceTurnCoordinator.send(.selectRoute(turnID: turnID, route: .deepgramBatch))
        transcribeBufferedWarmWaitAudio()
        return
      }
      silentMicRecoveryPolicy.recordSuccessfulTurn()
      DesktopDiagnosticsManager.shared.recordPTTCommitted(mode: finalizedMode, hubActive: true)
      AnalyticsManager.shared.floatingBarPTTEnded(
        mode: finalizedMode, hadTranscript: true, transcriptLength: 0)
      log(
        "PushToTalkManager: hub turn "
          + "\(commitResult == .accepted ? "committed" : "deferred until its realtime session is ready")")
      return
    }

    // Silence gate — an accidental tap (or a hold with nothing said) records
    // near-silence. Drop the turn here instead of letting STT hallucinate a
    // phrase from it. Applies to the omni and batch paths, which retain the
    // raw turn audio; live-Deepgram streams without buffering and already
    // returns empty on silence.
    let isBatch = ShortcutSettings.shared.pttTranscriptionMode == .batch
    if isOmniSTT || isBatch {
      batchAudioLock.lock()
      let turnAudio = batchAudioBuffer
      batchAudioLock.unlock()
      let (totalSec, voicedSec) = Self.voicedAudioSeconds(pcm16k: turnAudio)
      if totalSec < Self.minTurnAudioSeconds || voicedSec < Self.minVoicedSeconds {
        let (peak, rms) = Self.audioEnergy(pcm16k: turnAudio)
        // A dead mic (peak≈0 for a real hold) leaves omni/batch users stuck on
        // repeated silent turns with no recovery. Mirror the hub path: rebuild the
        // CoreAudio capture after consecutive dead-mic turns.
        let attemptRecovery = silentMicRecoveryPolicy.recordDiscardedTurn(totalSec: totalSec, peak: peak)
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
          recoveryAction: attemptRecovery ? "capture_rebuild" : "none",
          recoveryResult: attemptRecovery ? "attempted" : "not_attempted")
        log(
          "PushToTalkManager: discarding silent turn (audio \(String(format: "%.2f", totalSec))s, voiced \(String(format: "%.2f", voicedSec))s) — not transcribing"
        )
        AnalyticsManager.shared.floatingBarPTTEnded(
          mode: finalizedMode, hadTranscript: false, transcriptLength: 0)
        if attemptRecovery {
          requestCoreAudioCaptureRecovery(reason: "repeated dead-mic PTT turns", restartPTT: false, batchMode: isBatch)
        }
        // A too-short turn means the release beat capture (or the user tapped
        // instead of holding). Give visible feedback instead of a silent clear;
        // longer holds that were merely quiet keep the quiet reset.
        if totalSec < Self.minTurnAudioSeconds {
          finishTooShortPTTTurnWithHint(reason: "\(isOmniSTT ? "omni" : "batch"), \(String(format: "%.2f", totalSec))s")
        } else {
          stopListening()
        }
        return
      }
    }

    // Past the silence gate — a real turn will be transcribed and answered. Show
    // the "thinking" indicator through the transcription/first-token gap; it hands
    // off to the conversation surface (or voice glow) the moment output arrives.
    silentMicRecoveryPolicy.recordSuccessfulTurn()
    voiceTurnCoordinator.send(.transcriptionStarted(turnID: turnID))

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
      voiceTurnCoordinator.send(
        .transcriptionFinalizationStarted(turnID: turnID, mode: .omni))
      return
    }

    let isBatchMode = ShortcutSettings.shared.pttTranscriptionMode == .batch

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
        finishTooShortPTTTurnWithHint(reason: "batch, empty buffer")
        return
      }

      voiceTurnCoordinator.send(.transcriptChanged(turnID: turnID, text: "Transcribing…"))

      Task {
        do {
          await self.contextCaptureTask?.value
          guard self.voiceTurnCoordinator.activeTurnID == turnID else { return }
          let language = AssistantSettings.shared.effectiveTranscriptionLanguage
          let audioSeconds = Double(audioData.count) / (16000.0 * 2.0)
          log("PushToTalkManager: batch audio \(audioData.count) bytes (\(String(format: "%.1f", audioSeconds))s), pttLanguage=\(language), selectedLanguage=\(AssistantSettings.shared.transcriptionLanguage), autoDetect=\(AssistantSettings.shared.transcriptionAutoDetect)")

          self.activeTracer?.begin("batch_transcribe", metadata: ["method": "TranscriptionService.batchTranscribe"])
          var batchResult = try await TranscriptionService.batchTranscribe(
            audioData: audioData,
            language: language,
            contextKeywords: self.currentContextSnapshot?.keywords ?? []
          )
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
          self.voiceTurnCoordinator.send(
            .transcriptionFailed(turnID: turnID, message: error.localizedDescription))
          return
        }
        self.sendTranscript(turnID: turnID)
      }
    } else {
      // Live mode: flush remaining audio and wait for final transcript from Deepgram
      transcriptionService?.finishStream()
      log("PushToTalkManager: finalizing (live) — mic stopped, waiting for final transcript")
      voiceTurnCoordinator.send(
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
    voiceTurnCoordinator.send(.finish(turnID: turnID, reason: .tooShort))
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
    var justHitCap = false
    if batchAudioBuffer.count < Self.maxBatchAudioBytes {
      batchAudioBuffer.append(audioData)
      if batchAudioBuffer.count >= Self.maxBatchAudioBytes && !batchAudioOverflowSignaled {
        batchAudioOverflowSignaled = true
        justHitCap = true
      }
    }
    batchAudioLock.unlock()
    if justHitCap { showBatchAudioOverflowWarning(turn: turn) }
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
        self.voiceTurnCoordinator.send(
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
      voiceTurnCoordinator.send(.transcriptionFinalizationCompleted(turnID: turnID))
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
    if !query.isEmpty {
      query = PTTTranscriptContextualCorrector.correct(query, keywords: contextKeywords)
    }
    let hasQuery = !query.isEmpty
    let wasFollowUp = isCurrentSessionFollowUp

    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: finalizedMode,
      hadTranscript: hasQuery,
      transcriptLength: query.count
    )
    if hasQuery {
      DesktopDiagnosticsManager.shared.recordPTTCommitted(mode: finalizedMode, hubActive: false)
    }

    isCurrentSessionFollowUp = false

    transcriptSegments = []
    seenFinalSegmentIDs.removeAll()
    lastInterimText = ""
    currentContextSnapshot = nil

    guard hasQuery else {
      log("PushToTalkManager: no transcript to send")
      voiceTurnCoordinator.send(.finish(turnID: turnID, reason: .silentRejected))
      return
    }

    voiceTurnCoordinator.send(.transcriptionFinal(turnID: turnID, text: query))

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
    // Voice follow-up to an agent pill: route the transcript into THAT agent's session
    // (RealtimeHub pipeline) instead of the floating bar.
    if let pill = followUpPill {
      followUpPill = nil
      AgentPillsManager.shared.recordingPillID = nil
      activeTracer = nil
      let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
      if q.isEmpty {
        log("PushToTalkManager: voice follow-up empty — not sending")
      } else {
        guard voiceTurnCoordinator.requireCurrentOwner(for: turnID) != nil else { return }
        log("PushToTalkManager: routing voice follow-up → agent (\(q.count) chars)")
        let completionToken = currentVoiceTurnID.flatMap {
          voiceTurnCoordinator.nonHubCompletionToken(for: $0)
        }
        AgentPillsManager.shared.continueAgent(from: pill, text: q) { outcome in
          guard let completionToken else { return }
          VoiceTurnCoordinator.shared.completeNonHubProvider(
            completionToken,
            outcome: outcome)
        }
        if completionToken == nil, let turnID = currentVoiceTurnID {
          log("PushToTalkManager: agent follow-up missing provider completion identity")
          voiceTurnCoordinator.send(.finish(turnID: turnID, reason: .providerFailed))
        }
      }
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
        self.voiceTurnCoordinator.send(
          .contextResolved(turnID: turnID, outcome: .captured(version)))
        self.activeTracer?.end("context_ocr")
      }
    }
  }

  private func startAudioTranscription() {
    if automationCaptureBypass, let turnID = currentVoiceTurnID {
      micCaptureGeneration &+= 1
      voiceTurnCoordinator.send(
        .captureStarted(turnID: turnID, captureID: VoiceCaptureID(micCaptureGeneration)))
      return
    }
    // Always re-check permission (it can be granted at any time via System Settings)
    hasMicPermission = AudioCaptureService.checkPermission()

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
          self.voiceTurnCoordinator.send(
            .finish(turnID: permissionTurnID, reason: .permissionDenied))
        }
      }
      return
    }

    // Realtime-as-hub (Phase 1): when enabled + BYOK-keyed, the realtime model
    // drives this turn end-to-end (in-session STT + reasoning + tool-choice routing
    // + spoken reply). Stream mic PCM to the hub and skip both the omni/Deepgram
    // STT path AND the transcript→router→ChatProvider hop. The Haiku classify()
    // router is bypassed — routing is the model's tool choice.
    // Voice follow-up to an agent: always use the omni STT (we need a transcript to
    // route to the agent), never the hub model — the hub would answer it itself.
    if followUpPill != nil {
      if let turnID = currentVoiceTurnID {
        voiceTurnCoordinator.send(.selectRoute(turnID: turnID, route: .agentFollowUp))
      }
      _ = startOmniTranscription()
      return
    }

    if RealtimeHubController.shared.isActive {
      if let turnID = currentVoiceTurnID {
        voiceTurnCoordinator.send(.selectRoute(turnID: turnID, route: .hub(sessionID: nil)))
      }
      startRealtimeHubCapture(bufferWhileWarming: false)
      return
    }

    startRealtimeHubWarmWait()
    return
  }

  private func startRealtimeHubCapture(bufferWhileWarming: Bool) {
    if !bufferWhileWarming {
      batchAudioLock.lock(); batchAudioBuffer = Data(); batchAudioLock.unlock()
    }
    RealtimeHubController.shared.beginTurn(turnID: currentVoiceTurnID)
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
    log("PushToTalkManager: realtime hub active — model is the voice hub")
  }

  private func startRealtimeHubWarmWait() {
    batchAudioLock.lock(); batchAudioBuffer = Data(); batchAudioLock.unlock()
    if let turnID = currentVoiceTurnID {
      voiceTurnCoordinator.send(.selectRoute(turnID: turnID, route: .hubWarmWait))
    }
    RealtimeHubController.shared.ensureWarm()
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
    if ready {
      startRealtimeHubCapture(bufferWhileWarming: true)
      if phase == .finalizing {
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
      DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
        source: "buffered_hub",
        mode: finalizedMode,
        audioSeconds: totalSec,
        voicedSeconds: nil,
        peak: peak,
        rms: rms,
        deviceDescription: dev,
        micPermissionGranted: hasMicPermission,
        hubActive: true)
      log(
        "PushToTalkManager: discarding buffered hub turn — audio \(String(format: "%.2f", totalSec))s "
          + "peak=\(peak)/32767 rms=\(rms) device=[\(dev)] — not committing")
      if let turnID = currentVoiceTurnID {
        _ = RealtimeHubController.shared.cancelTurn(turnID: turnID)
      }
      AnalyticsManager.shared.floatingBarPTTEnded(
        mode: finalizedMode, hadTranscript: false, transcriptLength: 0)
      if let turnID = currentVoiceTurnID {
        voiceTurnCoordinator.send(
          .finish(
            turnID: turnID,
            reason: totalSec < Self.minTurnAudioSeconds ? .tooShort : .silentRejected))
      }
      return
    }
    let commitResult = RealtimeHubController.shared.commitTurn()
    if commitResult == .rejectedNoSession {
      log("PushToTalkManager: buffered hub commit rejected — falling back to buffered transcription")
      batchAudioLock.lock()
      batchAudioBuffer = turnAudio
      batchAudioLock.unlock()
      transcribeBufferedWarmWaitAudio()
      return
    }
    DesktopDiagnosticsManager.shared.recordPTTCommitted(mode: finalizedMode, hubActive: true)
    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: finalizedMode, hadTranscript: true, transcriptLength: 0)
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
      DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
        source: "warm_wait_fallback",
        mode: finalizedMode,
        audioSeconds: totalSec,
        voicedSeconds: voicedSec,
        peak: peak,
        rms: rms,
        deviceDescription: audioCaptureService?.currentDeviceDescription,
        micPermissionGranted: hasMicPermission,
        hubActive: false)
      log(
        "PushToTalkManager: discarding warm-wait fallback turn (audio \(String(format: "%.2f", totalSec))s, voiced \(String(format: "%.2f", voicedSec))s)")
      AnalyticsManager.shared.floatingBarPTTEnded(
        mode: finalizedMode, hadTranscript: false, transcriptLength: 0)
      if let turnID = currentVoiceTurnID {
        voiceTurnCoordinator.send(
          .finish(
            turnID: turnID,
            reason: totalSec < Self.minTurnAudioSeconds ? .tooShort : .silentRejected))
      }
      return
    }
    guard let turnID = currentVoiceTurnID else { return }
    voiceTurnCoordinator.send(.selectRoute(turnID: turnID, route: .deepgramBatch))
    voiceTurnCoordinator.send(.transcriptionStarted(turnID: turnID))
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
        if let transcript = batchResult.transcript, !transcript.isEmpty {
          self.transcriptSegments = [transcript]
        }
      } catch {
        logError("PushToTalkManager: warm-wait fallback transcription failed", error: error)
        self.voiceTurnCoordinator.send(
          .transcriptionFailed(turnID: turnID, message: error.localizedDescription))
        return
      }
      self.sendTranscript(turnID: turnID)
    }
  }

  private func startMicCapture(
    batchMode: Bool = false,
    overrideDeviceID: AudioDeviceID? = nil,
    diagnosticRecoveryAction: String? = nil
  ) {
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
    let capture = overrideDeviceID.map(AudioCaptureService.init(overrideDeviceID:)) ?? AudioCaptureService()
    audioCaptureService = capture

    // Silent-mic watchdog: Bluetooth inputs can return zeros during A2DP/HFP conflicts,
    // and stale CoreAudio routes can do the same even when the selected device is built-in.
    capture.resetSilentMicWatchdog()
    capture.detectSilentMicOnAnyTransport = true
    capture.onSilentMicDetected = { [weak self] detection in
      Task { @MainActor in
        guard let self, self.micCaptureGeneration == generation,
          self.voiceTurnCoordinator.activeTurnID == turnID
        else { return }
        self.handleSilentMicDetection(detection, batchMode: batchMode)
      }
    }

    Task { @MainActor [weak self] in
      guard let self else { return }
      do {
        try await capture.startCapture(
          onAudioChunk: { [weak self] audioData in
            Task { @MainActor [weak self] in
              guard let self else { return }
              guard self.micCaptureGeneration == generation,
                self.voiceTurnCoordinator.activeTurnID == turnID,
                self.shouldKeepMicCaptureAlive
              else { return }
              if self.isHubMode {
                // Lifecycle admission and provider commit are serialized on the
                // main actor. A chunk queued behind finalization observes the
                // closed capture token and cannot leak into the next turn.
                RealtimeHubController.shared.feedAudio(audioData, turnID: turnID)
                self.appendBatchAudioBounded(audioData, turn: generation)
                return
              }
              if self.isOmniSTT {
                if let svc = self.realtimeOmniService {
                  svc.sendAudio(self.resampleForOmni(audioData))
                } else {
                  self.omniPreconnectBuffer.append(audioData)
                }
                self.appendBatchAudioBounded(audioData, turn: generation)
              } else if batchMode {
                self.appendBatchAudioBounded(audioData, turn: generation)
              } else {
                self.transcriptionService?.sendAudio(audioData)
              }
            }
          },
          onAudioLevel: { [weak self] level in
            guard let self, self.micCaptureGeneration == generation,
              self.voiceTurnCoordinator.activeTurnID == turnID,
              self.shouldKeepMicCaptureAlive
            else { return }
            // Feed the floating-bar mic waveform (VoiceWaveformBars). Throttled to ~5 Hz
            // inside the monitor; used only for visualization.
            AudioLevelMonitor.shared.updateMicrophoneLevel(level)
          }
        )
        let isCurrentGeneration = self.micCaptureGeneration == generation
        guard isCurrentGeneration, self.shouldKeepMicCaptureAlive else {
          capture.stopCapture()
          if self.audioCaptureService === capture {
            self.audioCaptureService = nil
          }
          if isCurrentGeneration {
            self.micCaptureStartInFlight = false
          }
          if let diagnosticRecoveryAction {
            DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged(
              recoveryAction: diagnosticRecoveryAction,
              recoveryResult: "ignored_turn_ended")
          }
          log("PushToTalkManager: mic capture start completed after turn ended — stopped")
          return
        }
        self.micCaptureStartInFlight = false
        self.voiceTurnCoordinator.send(
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
        if let diagnosticRecoveryAction {
          DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged(
            recoveryAction: diagnosticRecoveryAction,
            recoveryResult: "failed")
        }
        logError("PushToTalkManager: mic capture failed", error: error)
        self.voiceTurnCoordinator.send(
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
       builtInID != detection.deviceID {
      log("PushToTalkManager: silent-mic fallback — switching to built-in mic (deviceID=\(builtInID))")
      silentMicRecoveryPolicy.recordCaptureRebuild()
      stopMicCapture()
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

  private func requestCoreAudioCaptureRecovery(reason: String, restartPTT: Bool, batchMode: Bool) {
    log("PushToTalkManager: requesting CoreAudio capture rebuild — \(reason)")
    silentMicRecoveryPolicy.recordCaptureRebuild()
    stopMicCapture()
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

  private func preferredPTTInputOverrideDeviceID() -> AudioDeviceID? {
    if AudioCaptureService.isDefaultOutputBluetooth(),
      let builtIn = AudioCaptureService.findBuiltInMicDeviceID()
    {
      return builtIn
    }
    return nil
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
  private func stopMicCapture(captureID expectedCaptureID: VoiceCaptureID? = nil) -> Bool {
    if let expectedCaptureID,
      expectedCaptureID != VoiceCaptureID(micCaptureGeneration)
    {
      log("PushToTalkManager: ignored stale stopCapture id=\(expectedCaptureID)")
      return false
    }
    micCaptureGeneration &+= 1
    micCaptureStartInFlight = false
    audioCaptureService?.stopCapture()
    audioCaptureService = nil
    return true
  }

  private func stopAudioTranscription(discardBufferedAudio: Bool = false) {
    stopMicCapture()
    transcriptionService?.stop(discardBufferedAudio: discardBufferedAudio)
    transcriptionService = nil
    realtimeOmniService?.stop()
    realtimeOmniService = nil
    omniDelegateProxy = nil
    omniPreconnectBuffer.removeAll()
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
    voiceTurnCoordinator.send(
      .transcriptionProviderStartedScoped(turnID: startingTurnID, identity: identity))
    guard voiceTurnCoordinator.activeTurn?.transcriptionEffectIdentity == identity else {
      return false
    }
    let delegateProxy = VoiceTurnOmniDelegateProxy(owner: self, identity: identity)
    omniDelegateProxy = delegateProxy
    let provider = RealtimeOmniSettings.shared.effectiveProvider
    if let turnID = currentVoiceTurnID,
      voiceTurnCoordinator.activeTurn?.route != .agentFollowUp
    {
      voiceTurnCoordinator.send(.selectRoute(turnID: turnID, route: .omniSTT))
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
      batchAudioLock.lock(); batchAudioBuffer = Data(); batchAudioLock.unlock()
      startMicCapture()  // capture immediately; chunks buffer until the relay connects
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
        self.voiceTurnCoordinator.send(
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
      voiceTurnCoordinator.send(.transcriptChanged(turnID: turnID, text: lastInterimText))
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
      voiceTurnCoordinator.send(.transcriptionFinalizationCompleted(turnID: turnID))
    }
    guard !audio.isEmpty else {
      sendTranscript(turnID: turnID)
      return
    }
    voiceTurnCoordinator.send(.transcriptChanged(turnID: turnID, text: "Transcribing…"))
    voiceTurnCoordinator.send(.selectRoute(turnID: turnID, route: .deepgramBatch))
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
        self.voiceTurnCoordinator.send(
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
    voiceTurnCoordinator.send(
      .transcriptionCompletionClaimedScoped(turnID: turnID, identity: identity))
    return voiceTurnCoordinator.activeTurn?.transcriptionEffectIdentity == identity
      && voiceTurnCoordinator.activeTurn?.transcriptionCompletionClaimed == true
  }
}
