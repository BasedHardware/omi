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

/// Push-to-talk manager for voice input via the Option (⌥) key.
///
/// State machine:
///   idle → [Option down] → listening → [Option up] → finalizing → sends query → idle
///   idle → [Quick tap] → pendingLockDecision → [tap again within 400ms] → lockedListening
///   pendingLockDecision → [timeout] → finalizing → sends query → idle
@MainActor
class PushToTalkManager: ObservableObject {
  static let shared = PushToTalkManager()

  // MARK: - State

  enum PTTState {
    case idle
    case listening
    case pendingLockDecision
    case lockedListening
    case finalizing
  }

  @Published private(set) var state: PTTState = .idle

  // MARK: - Private Properties

  private var globalMonitor: Any?
  private var localMonitor: Any?
  private var barState: FloatingControlBarState?

  // Double-tap detection
  private var lastOptionDownTime: TimeInterval = 0
  private var lastOptionUpTime: TimeInterval = 0
  private let doubleTapThreshold: TimeInterval = 0.4
  private let tapToLockMaxHoldDuration: TimeInterval = 0.22

  // Transcription
  private var transcriptionService: TranscriptionService?
  // Realtime omni STT (replaces Deepgram). Connects through the omi backend relay.
  private var realtimeOmniService: RealtimeOmniService?
  private var isOmniSTT = false
  // Realtime-as-hub (Phase 1): when active, the realtime model is THE hub — it does
  // in-session STT + reasoning + routing (tool choice) + speaks the reply. Mic PCM is
  // streamed to RealtimeHubController; there is no transcript→router→ChatProvider hop.
  private var isHubMode = false
  private var isWaitingForHub = false
  private var hubWaitTask: Task<Void, Never>?
  /// When set, the next finalized PTT turn is a voice follow-up to this agent pill:
  /// it uses the realtime omni STT and routes the transcript into the pill's agent
  /// session (RealtimeHub pipeline), NOT the floating bar or the hub model.
  private var followUpPill: AgentPill?
  // Mic chunks captured before the relay finishes connecting (raw 16k PCM),
  // flushed once the service exists so the user's first words aren't clipped.
  private var omniPreconnectBuffer: [Data] = []
  // True once the omni model returned any transcript this turn — gates the
  // Deepgram fallback so a benign trailing socket error doesn't trigger it.
  private var omniReceivedTranscript = false
  private var omniTurnSent = false  // dedup: send/fallback the omni turn at most once
  private var audioCaptureService: AudioCaptureService?
  private var micCaptureStartInFlight = false
  private var silentMicRecoveryPolicy = PTTSilentMicRecoveryPolicy()
  private var micCaptureGeneration: UInt64 = 0
  private var transcriptSegments: [String] = []
  private var lastInterimText: String = ""
  private var finalizeWorkItem: DispatchWorkItem?
  /// Monotonic tag for the transient too-short "hold longer" hint, so an older
  /// hint's 2s reset timer can't clear a newer hint from a rapid follow-up tap.
  private var pttHintGeneration = 0
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

  // Live mode: timeout for waiting on final transcript after CloseStream
  private var liveFinalizationTimeout: DispatchWorkItem?
  private static let hubWarmGraceSeconds: TimeInterval = 1.0

  private init() {}

  // MARK: - Setup / Teardown

  func setup(barState: FloatingControlBarState) {
    self.barState = barState
    hasMicPermission = AudioCaptureService.checkPermission()
    installEventMonitors()
    // Realtime hub: wire it to the bar and warm the WS if it's enabled + BYOK-keyed,
    // so the persistent socket is ready before the first PTT (and stays warm after).
    RealtimeHubController.shared.setup(barState: barState)
    // Hermetic local harness has no Firebase SDK and no live realtime providers.
    if !DesktopLocalProfile.isEnabled {
      RealtimeHubController.shared.ensureWarm()
    }
    log("PushToTalkManager: setup complete, micPermission=\(hasMicPermission)")
  }

  func cleanup() {
    stopListening()
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

    switch state {
    case .idle:
      // Check for double-tap: if last Option-up was recent, enter locked mode
      if ShortcutSettings.shared.doubleTapForLock && (now - lastOptionUpTime) < doubleTapThreshold {
        lastOptionUpTime = 0
        enterLockedListening()
      } else {
        lastOptionDownTime = now
        startListening()
      }

    case .listening:
      // Already listening (hold mode), ignore repeated flagsChanged
      break

    case .pendingLockDecision:
      stopListening()
      enterLockedListening()

    case .lockedListening:
      // Tap while locked → finalize
      finalize()

    case .finalizing:
      break
    }
  }

  private func handleShortcutUp() {
    let now = ProcessInfo.processInfo.systemUptime

    switch state {
    case .listening:
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

    case .lockedListening:
      // In locked mode, Option-up is ignored (we finalize on next Option-down)
      break

    case .idle, .finalizing:
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
    guard state == .idle || state == .pendingLockDecision else {
      log("PushToTalkManager: startListening ignored — state=\(state)")
      return
    }
    if isBlockedByUsageLimit() { return }
    RealtimeHubController.shared.prefetchVoiceSeedContextIfNeeded()
    // Reset the overflow flag under the buffer lock so it's atomic w.r.t. the
    // audio thread's appendBatchAudioBounded (fresh turn → allow the warning again).
    batchAudioLock.lock()
    batchAudioOverflowSignaled = false
    batchAudioLock.unlock()
    barState?.pttHintText = ""  // clear any lingering too-short/too-long hint from a prior tap
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
    if ShortcutSettings.shared.pttMuteSystemAudio {
      SystemAudioMuteController.shared.muteForListening()
    }
    state = .listening
    barState?.isThinking = false
    startActiveTracer()
    isCurrentSessionFollowUp = barState?.showingAIResponse == true
    transcriptSegments = []
    lastInterimText = ""
    currentContextSnapshot = nil
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil

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
    RealtimeHubController.shared.prefetchVoiceSeedContextIfNeeded()
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
    if ShortcutSettings.shared.pttMuteSystemAudio {
      SystemAudioMuteController.shared.muteForListening()
    }
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil
    state = .lockedListening
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
      lastInterimText = ""
      currentContextSnapshot = nil
      let preOverlayImage = ScreenCaptureManager.captureScreenImage()
      captureContextAndStartAudio(preOverlayImage: preOverlayImage)
    }

    updateBarState()
    log("PushToTalkManager: entered locked listening mode (mode=\(mode))")
  }

  private func enterPendingLockDecision() {
    guard state == .listening else { return }

    state = .pendingLockDecision
    stopMicCapture()
    updateBarState()

    let workItem = DispatchWorkItem { [weak self] in
      Task { @MainActor in
        guard let self, self.state == .pendingLockDecision else { return }
        self.finalize()
      }
    }
    finalizeWorkItem = workItem
    DispatchQueue.main.asyncAfter(deadline: .now() + doubleTapThreshold, execute: workItem)
  }

  private func stopListening() {
    // Always restore audio on teardown (cancel, error, cleanup) so we never leave it muted.
    SystemAudioMuteController.shared.restore()
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil
    liveFinalizationTimeout?.cancel()
    liveFinalizationTimeout = nil
    contextCaptureTask?.cancel()
    contextCaptureTask = nil
    hubWaitTask?.cancel()
    hubWaitTask = nil
    isWaitingForHub = false
    micCaptureStartInFlight = false
    if isHubMode {
      isHubMode = false
      RealtimeHubController.shared.cancelTurn()
    }
    if followUpPill != nil {
      followUpPill = nil
      AgentPillsManager.shared.recordingPillID = nil
    }
    stopAudioTranscription(parkWarm: false)
    state = .idle
    barState?.isThinking = false
    transcriptSegments = []
    lastInterimText = ""
    currentContextSnapshot = nil
    batchAudioLock.lock()
    batchAudioBuffer = Data()
    batchAudioLock.unlock()
    isCurrentSessionFollowUp = false
    barState?.pttHintText = ""
    // Abandoned session (cancel / silent turn) — drop its tracer unsent so it
    // doesn't leak into the next PTT turn. No trace is written for these.
    activeTracer = nil
    updateBarState()
  }

  /// Cancel PTT without sending — used when conversation is closed mid-PTT.
  func cancelListening() {
    guard state != .idle else { return }
    log("PushToTalkManager: cancelling listening")
    stopListening()
  }

  // MARK: - Agent voice follow-up

  /// Begin a voice follow-up to a specific agent pill (the pill's mic button). Reuses
  /// the realtime omni STT capture; the transcript routes to the agent's session via
  /// AgentPillsManager.continueAgent (not the floating bar / hub model).
  func startPillFollowUp(for pill: AgentPill) {
    guard state == .idle else {
      log("PushToTalkManager: follow-up ignored — PTT busy (state=\(state))")
      AgentPillsManager.shared.recordingPillID = nil
      return
    }
    log("PushToTalkManager: voice follow-up START for agent \(pill.title)")
    followUpPill = pill
    startListening()
  }

  /// End the in-progress voice follow-up (second mic tap) and send it to the agent.
  func endPillFollowUp() {
    guard followUpPill != nil, state != .idle else { return }
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
    startListening()
    return ["state": "\(state)", "listening": state == .listening ? "true" : "false"]
  }

  /// Release an in-progress push-to-talk capture the same way a long-hold key-up does
  /// (`handleShortcutUp` .listening branch → `finalize`), producing the final
  /// transcript. Releasing with no captured audio exercises the empty-batch path,
  /// which must end the turn with a hint rather than hang. No-op unless a capture is
  /// active.
  @discardableResult
  func endPushToTalkForAutomation() -> [String: String] {
    let wasActive = state == .listening || state == .lockedListening
    if wasActive { finalize() }
    return ["state": "\(state)", "finalized": wasActive ? "true" : "false"]
  }

  private var finalizedMode: String = "hold"

  private func currentPTTMode() -> String {
    let baseMode = state == .lockedListening ? "locked" : "hold"
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
    if total >= hubMinTurnAudioSeconds && speechLike >= hubMinSpeechLikeSeconds { return true }
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
    // ~96ms contiguous speech, or ~192ms total. Each Silero frame is 512 samples = 32ms.
    return maxRun >= 3 || speechFrames >= 6
  }

  private func finalize() {
    guard state == .listening || state == .lockedListening || state == .pendingLockDecision else { return }

    lastOptionUpTime = 0
    // Dictation is over — restore any audio we muted so the track resumes immediately.
    SystemAudioMuteController.shared.restore()
    finalizedMode = currentPTTMode()
    state = .finalizing
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil

    // Stop mic immediately — no more audio capture
    stopMicCapture()
    activeTracer?.end("audio_capture")
    activeTracer?.end("ptt_recording")

    if isWaitingForHub {
      barState?.beginVoiceResponseWaiting()
      updateBarState()
      log("PushToTalkManager: finalizing while realtime hub warms — holding buffered audio")
      return
    }

    // Realtime hub: silence-gate the turn first. An accidental ⌥ tap (or a hold
    // with nothing said) records near-silence — committing it makes the model
    // answer anyway (often a generic "looking at your screen"). Drop those before
    // committing, exactly like the omni/batch paths.
    if isHubMode {
      isHubMode = false
      activeTracer = nil
      state = .idle
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
        RealtimeHubController.shared.cancelTurn()
        AnalyticsManager.shared.floatingBarPTTEnded(
          mode: finalizedMode, hadTranscript: false, transcriptLength: 0)
        // Too short to have captured anything (fast tap / capture not ready) — hint
        // the user to hold longer instead of clearing silently. A longer hub turn
        // that simply had no speech keeps the quiet reset.
        if totalSec < Self.minTurnAudioSeconds {
          finishTooShortPTTTurnWithHint(reason: "hub, \(String(format: "%.2f", totalSec))s")
        } else {
          updateBarState()  // clears the listening UI (no "…")
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
        transcribeBufferedWarmWaitAudio()
        return
      }
      silentMicRecoveryPolicy.recordSuccessfulTurn()
      DesktopDiagnosticsManager.shared.recordPTTCommitted(mode: finalizedMode, hubActive: true)
      barState?.beginVoiceResponseWaiting()
      // Show the "thinking" indicator in the notch during the release→first-audio
      // gap. It clears when the hub's spoken reply starts (isVoiceResponseActive),
      // so the glow takes over.
      barState?.isThinking = true
      updateBarState()
      AnalyticsManager.shared.floatingBarPTTEnded(
        mode: finalizedMode, hadTranscript: true, transcriptLength: 0)
      log("PushToTalkManager: hub turn \(commitResult == .deferredForReplacement ? "deferred for replacement session" : "committed")")
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
    barState?.isThinking = true
    updateBarState()

    // Realtime omni: commit the turn and wait for the final transcript.
    if isOmniSTT {
      // The relay already died this turn (omniDidError nilled it) — don't wait on a dead
      // socket; transcribe the buffered turn audio via Deepgram now so PTT still answers.
      if realtimeOmniService == nil {
        log("PushToTalkManager: omni relay unavailable — transcribing turn via Deepgram")
        fallBackToDeepgram()
        return
      }
      // QueryTracer: the omni provider's post-commit finalization (VAD close +
      // final STT inference + round-trip) — closed at the top of sendTranscript().
      activeTracer?.begin(
        "omni_transcribe", metadata: ["provider": RealtimeOmniSettings.shared.effectiveProvider.displayName])
      realtimeOmniService?.commitInputTurn()
      log("PushToTalkManager: finalizing (omni STT) — waiting for final transcript")
      let timeout = DispatchWorkItem { [weak self] in
        Task { @MainActor in
          guard let self, self.state == .finalizing else { return }
          // No clean final transcript from the relay in time — don't ship the garbage
          // interim it may have left behind; fall back to Deepgram on the full buffered
          // turn audio. fallBackToDeepgram() no-ops if the turn was already sent.
          log("PushToTalkManager: omni finalization timeout — falling back to Deepgram")
          self.fallBackToDeepgram()
        }
      }
      liveFinalizationTimeout = timeout
      // Safety net only — the real send happens the instant the omni model
      // returns its final transcript (omniDidReceiveInputTranscript isFinal /
      // omniDidFinishTurn). Generous so the relay round-trip can complete.
      DispatchQueue.main.asyncAfter(deadline: .now() + 8.0, execute: timeout)
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

      barState?.voiceTranscript = "Transcribing..."

      Task {
        do {
          await self.contextCaptureTask?.value
          let language = AssistantSettings.shared.effectiveTranscriptionLanguage
          let audioSeconds = Double(audioData.count) / (16000.0 * 2.0)
          log("PushToTalkManager: batch audio \(audioData.count) bytes (\(String(format: "%.1f", audioSeconds))s), pttLanguage=\(language), selectedLanguage=\(AssistantSettings.shared.transcriptionLanguage), autoDetect=\(AssistantSettings.shared.transcriptionAutoDetect)")

          self.activeTracer?.begin("batch_transcribe", metadata: ["method": "TranscriptionService.batchTranscribe"])
          var transcript = try await TranscriptionService.batchTranscribe(
            audioData: audioData,
            language: language,
            contextKeywords: self.currentContextSnapshot?.keywords ?? []
          )

          if (transcript == nil || transcript?.isEmpty == true) && language != "en" && language != "multi" && audioSeconds < 5.0 {
            log("PushToTalkManager: selected language returned empty on short audio, retrying with 'en'")
            transcript = try await TranscriptionService.batchTranscribe(
              audioData: audioData,
              language: "en",
              contextKeywords: self.currentContextSnapshot?.keywords ?? []
            )
          }
          self.activeTracer?.end("batch_transcribe")

          if let transcript, !transcript.isEmpty {
            self.transcriptSegments = [transcript]
          } else {
            log("PushToTalkManager: transcription returned empty after retry")
          }
        } catch {
          logError("PushToTalkManager: batch transcription failed", error: error)
          let message = (error as? TranscriptionService.TranscriptionError)?.errorDescription ?? "Transcription failed"
          barState?.voiceTranscript = "⚠️ \(message)"
          try? await Task.sleep(nanoseconds: 3_000_000_000)
          barState?.voiceTranscript = ""
        }
        self.sendTranscript()
      }
    } else {
      // Live mode: flush remaining audio and wait for final transcript from Deepgram
      transcriptionService?.finishStream()
      log("PushToTalkManager: finalizing (live) — mic stopped, waiting for final transcript")

      // Safety timeout: if Deepgram doesn't send a final segment within 3s, send what we have
      let timeout = DispatchWorkItem { [weak self] in
        Task { @MainActor in
          guard let self, self.state == .finalizing else { return }
          log("PushToTalkManager: live finalization timeout — sending transcript")
          self.sendTranscript()
        }
      }
      liveFinalizationTimeout = timeout
      DispatchQueue.main.asyncAfter(deadline: .now() + 3.0, execute: timeout)
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
    // Return to idle immediately. The hub path already reset state, but the
    // omni/batch discard path leaves it in `.finalizing`; without this a new PTT
    // press within the 2s hint window is dropped (handleShortcutDown ignores
    // `.finalizing`). The bar stays voice-sized via pttHintText, not `state`.
    state = .idle
    barState?.pttHintText = "Hold longer to record"
    updateBarState()  // keeps/expands the bar to its voice size so the hint shows

    // Tag this hint so a newer too-short tap's hint isn't cleared early by this
    // timer (rapid taps would otherwise share the identical hint string).
    pttHintGeneration &+= 1
    let generation = pttHintGeneration
    Task { @MainActor [weak self] in
      try? await Task.sleep(nanoseconds: 2_000_000_000)
      guard let self, self.pttHintGeneration == generation else { return }
      // Only reset if the hint is still on screen — a newer turn may have replaced it.
      if self.barState?.pttHintText == "Hold longer to record" {
        self.barState?.pttHintText = ""
        self.stopListening()  // collapses the bar (pttHintText now empty)
      }
    }
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
      self.barState?.pttHintText = "Recording too long — keep it under 5 min"
      self.updateBarState()
      self.pttHintGeneration &+= 1
      let generation = self.pttHintGeneration
      Task { @MainActor [weak self] in
        try? await Task.sleep(nanoseconds: 4_000_000_000)
        guard let self, self.pttHintGeneration == generation else { return }
        if self.barState?.pttHintText == "Recording too long — keep it under 5 min" {
          self.barState?.pttHintText = ""
          self.updateBarState()
        }
      }
    }
  }

  private func sendTranscript() {
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

    // Reset state — skip PTT collapse resize when we have a query,
    // because openAIInputWithQuery will resize to the correct size.
    // Also skip resize when in follow-up mode (panel is already at response size).
    state = .idle
    transcriptSegments = []
    lastInterimText = ""
    currentContextSnapshot = nil
    updateBarState(skipResize: hasQuery || wasFollowUp)

    guard hasQuery else {
      log("PushToTalkManager: no transcript to send")
      return
    }

    // Dropped the Gemini ASR-cleanup round-trip (~0.5s on the critical path): the
    // transcript is already locally corrected against screen-OCR keywords above
    // (PTTTranscriptContextualCorrector), and Claude tolerates minor ASR typos.
    // Send straight through (sendTranscript already runs on the main actor).
    activeTracer?.mark("transcript_cleanup")
    sendQuery(query, wasFollowUp: wasFollowUp)
  }

  private func sendQuery(_ query: String, wasFollowUp: Bool) {
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
        log("PushToTalkManager: routing voice follow-up → agent \(pill.title): \"\(q.prefix(60))\"")
        AgentPillsManager.shared.continueAgent(from: pill, text: q)
      }
      return
    }
    // QueryTracer: hand the PTT tracer to the floating-bar query via TaskLocal so
    // routing, the LLM call, and TTS all record into this same trace. Ownership
    // moves out of activeTracer here; the unstructured Task spawned inside
    // openAIInputWithQuery / sendFollowUpQuery inherits the bound value.
    let tracer = activeTracer
    activeTracer = nil
    barState?.beginVoiceResponseWaiting()
    let dispatch = {
      if wasFollowUp {
        log("PushToTalkManager: sending follow-up query (\(query.count) chars): \(query)")
        FloatingControlBarManager.shared.sendFollowUpQuery(query, fromVoice: true)
      } else {
        log("PushToTalkManager: sending query (\(query.count) chars): \(query)")
        FloatingControlBarManager.shared.openAIInputWithQuery(query, fromVoice: true)
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
        guard self.state == .listening || self.state == .lockedListening || self.state == .finalizing else { return }
        self.currentContextSnapshot = snapshot
        self.activeTracer?.end("context_ocr")
      }
    }
  }

  private func startAudioTranscription() {
    // Always re-check permission (it can be granted at any time via System Settings)
    hasMicPermission = AudioCaptureService.checkPermission()

    guard hasMicPermission else {
      log("PushToTalkManager: no microphone permission, requesting")
      Task {
        let granted = await AudioCaptureService.requestPermission()
        self.hasMicPermission = granted
        if granted {
          log("PushToTalkManager: microphone permission granted")
        } else {
          log("PushToTalkManager: microphone permission denied")
          self.stopListening()
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
      _ = startOmniTranscription()
      return
    }

    if RealtimeHubController.shared.isActive {
      startRealtimeHubCapture(bufferWhileWarming: false)
      return
    }

    startRealtimeHubWarmWait()
    return
  }

  private func startRealtimeHubCapture(bufferWhileWarming: Bool) {
    isHubMode = true
    isWaitingForHub = false
    if !bufferWhileWarming {
      batchAudioLock.lock(); batchAudioBuffer = Data(); batchAudioLock.unlock()
    }
    RealtimeHubController.shared.beginTurn()
    if bufferWhileWarming {
      batchAudioLock.lock()
      let bufferedAudio = batchAudioBuffer
      batchAudioLock.unlock()
      if !bufferedAudio.isEmpty {
        RealtimeHubController.shared.feedAudio(bufferedAudio)
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
    isWaitingForHub = true
    isHubMode = false
    batchAudioLock.lock(); batchAudioBuffer = Data(); batchAudioLock.unlock()
    RealtimeHubController.shared.ensureWarm()
    if let builtIn = preferredPTTInputOverrideDeviceID() {
      log("PushToTalkManager: waiting for realtime hub — buffering built-in mic audio")
      startMicCapture(batchMode: true, overrideDeviceID: builtIn)
    } else {
      log("PushToTalkManager: waiting for realtime hub — buffering mic audio")
      startMicCapture(batchMode: true)
    }
    hubWaitTask?.cancel()
    hubWaitTask = Task { @MainActor [weak self] in
      let ready = await RealtimeHubController.shared.waitUntilActive(timeout: Self.hubWarmGraceSeconds)
      self?.resolveRealtimeHubWarmWait(ready: ready)
    }
  }

  private func resolveRealtimeHubWarmWait(ready: Bool) {
    guard isWaitingForHub else { return }
    hubWaitTask = nil
    guard state == .listening || state == .lockedListening || state == .pendingLockDecision || state == .finalizing else {
      isWaitingForHub = false
      return
    }
    if ready {
      isWaitingForHub = false
      startRealtimeHubCapture(bufferWhileWarming: true)
      if state == .finalizing {
        commitBufferedRealtimeHubTurn()
      }
      return
    }

    isWaitingForHub = false
    if state == .finalizing {
      log("PushToTalkManager: realtime hub warm wait timed out after release — transcribing buffered audio")
      transcribeBufferedWarmWaitAudio()
    } else {
      log("PushToTalkManager: realtime hub warm wait timed out — using omni STT")
      _ = startOmniTranscription(captureAlreadyRunning: true)
    }
  }

  private func commitBufferedRealtimeHubTurn() {
    guard isHubMode else { return }
    isHubMode = false
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
      RealtimeHubController.shared.cancelTurn()
      AnalyticsManager.shared.floatingBarPTTEnded(
        mode: finalizedMode, hadTranscript: false, transcriptLength: 0)
      state = .idle
      updateBarState()
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
    barState?.beginVoiceResponseWaiting()
    state = .idle
    updateBarState()
    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: finalizedMode, hadTranscript: true, transcriptLength: 0)
    log("PushToTalkManager: buffered hub turn \(commitResult == .deferredForReplacement ? "deferred for replacement session" : "committed") after warm wait")
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
      stopListening()
      return
    }
    Task { @MainActor [weak self] in
      guard let self else { return }
      do {
        let language = AssistantSettings.shared.effectiveTranscriptionLanguage
        self.activeTracer?.begin("batch_transcribe", metadata: ["reason": "hub_warm_timeout"])
        let transcript = try await TranscriptionService.batchTranscribe(
          audioData: audio,
          language: language,
          contextKeywords: self.currentContextSnapshot?.keywords ?? []
        )
        self.activeTracer?.end("batch_transcribe")
        if let transcript, !transcript.isEmpty {
          self.transcriptSegments = [transcript]
        }
      } catch {
        logError("PushToTalkManager: warm-wait fallback transcription failed", error: error)
      }
      self.sendTranscript()
    }
  }

  /// Routing state the mic-frame closures consult per chunk. Lock-guarded so a
  /// parked (warm) capture can be re-leased to a new turn without reinstalling
  /// closures on a running capture (the IOProc thread reads them).
  private final class MicCaptureLease {
    private let lock = NSLock()
    private var _generation: UInt64
    private var _batchMode: Bool
    init(generation: UInt64, batchMode: Bool) {
      _generation = generation
      _batchMode = batchMode
    }
    func snapshot() -> (generation: UInt64, batchMode: Bool) {
      lock.lock()
      defer { lock.unlock() }
      return (_generation, _batchMode)
    }
    func renew(generation: UInt64, batchMode: Bool) {
      lock.lock()
      _generation = generation
      _batchMode = batchMode
      lock.unlock()
    }
  }

  /// Warm mic keep-alive: opening a CoreAudio input can take seconds under
  /// load (observed ~5s with capture pipelines spinning up), which makes a
  /// PTT turn hear nothing. Instead of destroying the capture at turn end,
  /// park it running-but-dropped and re-lease it on the next press.
  private var parkedMicCapture:
    (service: AudioCaptureService, lease: MicCaptureLease, overrideID: AudioDeviceID?)?
  private var parkedMicExpiryTask: Task<Void, Never>?
  private var activeMicLease: MicCaptureLease?
  private var activeMicOverrideID: AudioDeviceID?
  private static let parkedMicKeepAliveSeconds: UInt64 = 120

  private func parkMicCapture(_ service: AudioCaptureService, lease: MicCaptureLease, overrideID: AudioDeviceID?) {
    parkedMicExpiryTask?.cancel()
    if let old = parkedMicCapture, old.service !== service {
      old.service.stopCapture()
    }
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
    parkedMicExpiryTask?.cancel()
    parkedMicExpiryTask = nil
    parkedMicCapture?.service.stopCapture()
    parkedMicCapture = nil
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

    // Warm reuse: a parked capture on the same device skips the multi-second
    // CoreAudio device open entirely — the turn hears audio immediately.
    if let parked = parkedMicCapture, parked.overrideID == overrideDeviceID, parked.service.capturing {
      parkedMicExpiryTask?.cancel()
      parkedMicExpiryTask = nil
      parkedMicCapture = nil
      parked.lease.renew(generation: generation, batchMode: batchMode)
      parked.service.resetSilentMicWatchdog()
      audioCaptureService = parked.service
      activeMicLease = parked.lease
      activeMicOverrideID = overrideDeviceID
      micCaptureStartInFlight = false
      if let diagnosticRecoveryAction {
        DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged(
          recoveryAction: diagnosticRecoveryAction,
          recoveryResult: "succeeded_warm_reuse")
      }
      log("PushToTalkManager: mic capture adopted from warm keep-alive (batch=\(batchMode))")
      return
    }
    discardParkedMicCapture()

    let capture = overrideDeviceID.map(AudioCaptureService.init(overrideDeviceID:)) ?? AudioCaptureService()
    let lease = MicCaptureLease(generation: generation, batchMode: batchMode)
    activeMicLease = lease
    activeMicOverrideID = overrideDeviceID
    audioCaptureService = capture

    // Silent-mic watchdog: Bluetooth inputs can return zeros during A2DP/HFP conflicts,
    // and stale CoreAudio routes can do the same even when the selected device is built-in.
    capture.resetSilentMicWatchdog()
    capture.detectSilentMicOnAnyTransport = true
    capture.onSilentMicDetected = { [weak self] detection in
      Task { @MainActor in
        guard let self else { return }
        let leased = lease.snapshot()
        guard self.micCaptureGeneration == leased.generation else { return }
        self.handleSilentMicDetection(detection, batchMode: leased.batchMode)
      }
    }

    Task { @MainActor [weak self] in
      guard let self else { return }
      do {
        try await capture.startCapture(
          onAudioChunk: { [weak self] audioData in
            guard let self else { return }
            let leased = lease.snapshot()
            guard self.micCaptureGeneration == leased.generation, self.shouldKeepMicCaptureAlive else { return }
            let batchMode = leased.batchMode
            let generation = leased.generation
            if self.isHubMode {
              // Realtime hub owns this turn — stream mic PCM straight to it, and
              // retain it so finalize() can silence-gate the turn.
              RealtimeHubController.shared.feedAudio(audioData)
              self.appendBatchAudioBounded(audioData, turn: generation)
              return
            }
            if self.isOmniSTT {
              // Realtime omni: stream mic PCM (resampled to the provider's rate),
              // or buffer raw until the relay finishes connecting.
              if let svc = self.realtimeOmniService {
                svc.sendAudio(self.resampleForOmni(audioData))
              } else {
                self.omniPreconnectBuffer.append(audioData)
              }
              // Also retain the raw turn for a Deepgram fallback if omni fails.
              self.appendBatchAudioBounded(audioData, turn: generation)
            } else if batchMode {
              // Batch mode: accumulate audio in buffer
              self.appendBatchAudioBounded(audioData, turn: generation)
            } else {
              // Live mode: stream to Deepgram
              self.transcriptionService?.sendAudio(audioData)
            }
          },
          onAudioLevel: { [weak self] level in
            guard let self, self.micCaptureGeneration == lease.snapshot().generation,
              self.shouldKeepMicCaptureAlive
            else { return }
            // Feed the floating-bar mic waveform (VoiceWaveformBars). Throttled to ~5 Hz
            // inside the monitor; used only for visualization.
            AudioLevelMonitor.shared.updateMicrophoneLevel(level)
          }
        )
        let isCurrentGeneration = self.micCaptureGeneration == generation
        guard isCurrentGeneration, self.shouldKeepMicCaptureAlive else {
          // The device is finally open — keep it warm for the next press
          // instead of paying the multi-second open again.
          if self.audioCaptureService === capture {
            self.audioCaptureService = nil
          }
          if isCurrentGeneration {
            self.micCaptureStartInFlight = false
          }
          self.parkMicCapture(capture, lease: lease, overrideID: overrideDeviceID)
          if let diagnosticRecoveryAction {
            DesktopDiagnosticsManager.shared.recordPTTDeviceRouteChanged(
              recoveryAction: diagnosticRecoveryAction,
              recoveryResult: "ignored_turn_ended_parked_warm")
          }
          log("PushToTalkManager: mic capture start completed after turn ended — parked warm")
          return
        }
        self.micCaptureStartInFlight = false
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
        self.stopListening()
      }
    }
  }

  /// Recover when the silent-mic watchdog detects a capture that is running but
  /// returning zeros. Bluetooth profile conflicts can usually be fixed by pinning
  /// to the built-in mic. Non-Bluetooth silence points to a stale CoreAudio route,
  /// so rebuild the whole capture stack instead.
  @MainActor
  private func handleSilentMicDetection(_ detection: AudioCaptureService.SilentMicDetection, batchMode: Bool) {
    guard state == .listening || state == .lockedListening || state == .pendingLockDecision else {
      return
    }
    if detection.suggestedAction == .fallbackToBuiltIn,
       let builtInID = AudioCaptureService.findBuiltInMicDeviceID(),
       builtInID != detection.deviceID {
      log("PushToTalkManager: silent-mic fallback — switching to built-in mic (deviceID=\(builtInID))")
      silentMicRecoveryPolicy.recordCaptureRebuild()
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

  private func requestCoreAudioCaptureRecovery(reason: String, restartPTT: Bool, batchMode: Bool) {
    log("PushToTalkManager: requesting CoreAudio capture rebuild — \(reason)")
    silentMicRecoveryPolicy.recordCaptureRebuild()
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

  private func preferredPTTInputOverrideDeviceID() -> AudioDeviceID? {
    guard let builtIn = AudioCaptureService.findBuiltInMicDeviceID() else { return nil }
    let parkedCapture = parkedMicCapture?.service
    if AudioCaptureService.isDefaultOutputBluetooth() {
      return builtIn
    }
    // The transcription capture may be pinned to a specific mic (e.g. Ray-Ban
    // Meta glasses chosen in Settings → Transcription). Opening a second
    // IOProc on a device another capture already holds — or opening any
    // Bluetooth input while another capture runs and can flap the A2DP↔HFP
    // profile — races both instances' stream-format reconfiguration. PTT
    // yields and captures from the built-in mic instead.
    if let defaultInput = AudioCaptureService.currentDefaultInputDeviceID(),
      defaultInput != builtIn
    {
      if AudioCaptureService.isDeviceActivelyCaptured(defaultInput, excluding: parkedCapture) {
        log("PushToTalkManager: default input is held by another capture — using built-in mic")
        return builtIn
      }
      if AudioCaptureService.hasActiveCapture(excluding: parkedCapture),
        AudioCaptureService.isBluetoothTransport(deviceID: defaultInput)
      {
        log("PushToTalkManager: Bluetooth input while another capture is live — using built-in mic")
        return builtIn
      }
    }
    return nil
  }

  private func clearBufferedTurnAudio() {
    batchAudioLock.lock()
    batchAudioBuffer = Data()
    batchAudioLock.unlock()
  }

  private var shouldKeepMicCaptureAlive: Bool {
    state == .listening || state == .lockedListening
  }

  private func stopMicCapture(parkWarm: Bool = true) {
    micCaptureGeneration &+= 1
    micCaptureStartInFlight = false
    if parkWarm, let service = audioCaptureService, service.capturing, let lease = activeMicLease {
      // Turn ended: keep the open device warm so the next press hears
      // audio immediately (frames are dropped via the generation guard).
      parkMicCapture(service, lease: lease, overrideID: activeMicOverrideID)
    } else {
      audioCaptureService?.stopCapture()
      if !parkWarm {
        discardParkedMicCapture()
      }
    }
    audioCaptureService = nil
    activeMicLease = nil
    activeMicOverrideID = nil
  }

  private func stopAudioTranscription(parkWarm: Bool = true) {
    hubWaitTask?.cancel()
    hubWaitTask = nil
    isWaitingForHub = false
    stopMicCapture(parkWarm: parkWarm)
    transcriptionService?.stop()
    transcriptionService = nil
    realtimeOmniService?.stop()
    realtimeOmniService = nil
    isOmniSTT = false
    omniPreconnectBuffer.removeAll()
  }

  private func handleTranscriptSegments(_ segments: [TranscriptionService.BackendSegment]) {
    guard
      state == .listening || state == .lockedListening || state == .pendingLockDecision
        || state == .finalizing
    else { return }

    for segment in segments {
      transcriptSegments.append(segment.text)
    }
    lastInterimText = ""

    // In finalizing state, segments mean backend is done — send immediately
    if state == .finalizing {
      log("PushToTalkManager: received transcript during finalization — sending now")
      liveFinalizationTimeout?.cancel()
      liveFinalizationTimeout = nil
      sendTranscript()
    }
  }

  // MARK: - Bar State Sync

  private func updateBarState(skipResize: Bool = false) {
    guard let barState = barState else { return }
    let wasListening = barState.isVoiceListening
    // A pending too-short hint keeps the bar in its voice-UI size/position so the
    // inline "hold longer" text is visible (and correctly sized) for its brief window.
    let isShowingVoiceUI =
      (state == .listening || state == .lockedListening) || !barState.pttHintText.isEmpty
    barState.isVoiceListening = isShowingVoiceUI
    barState.isVoiceLocked = (state == .lockedListening)
    barState.isVoiceFollowUp = isCurrentSessionFollowUp && isShowingVoiceUI
    if isShowingVoiceUI {
      barState.clearVoiceResponseState()
    }
    if !isShowingVoiceUI {
      barState.voiceTranscript = ""
      barState.voiceFollowUpTranscript = ""
    }

    // Skip resize when in follow-up mode, expanded AI conversation, or during onboarding
    // (during onboarding the floating bar shouldn't appear as a separate window)
    let isOnboarding = !UserDefaults.standard.bool(forKey: "hasCompletedOnboarding")
    guard !skipResize && !barState.isVoiceFollowUp && !barState.showingAIConversation && !isOnboarding else { return }
    if barState.isVoiceListening && !wasListening {
      FloatingControlBarManager.shared.resizeForPTT(expanded: true)
    } else if !barState.isVoiceListening && wasListening && !(barState.isThinking && barState.usesNotchIsland) {
      // Keep the notch expanded while "thinking" so the indicator has room; the
      // view's isThinking observer collapses it when the response arrives. The
      // pill (non-notch) display has no thinking indicator, so it collapses now.
      FloatingControlBarManager.shared.resizeForPTT(expanded: false)
    }
  }
}

// MARK: - Realtime Omni STT integration
//
// When "Realtime Voice" is enabled, one omni model (Gemini 3.1 Flash Live or
// GPT Realtime 2) transcribes the PTT turn instead of Deepgram. The final
// transcript flows through the unchanged sendTranscript() → ChatProvider path,
// so agents, tools, memory, vision, and the text input all keep working.
extension PushToTalkManager: RealtimeOmniServiceDelegate {

  /// Starts realtime omni STT via the omi backend relay. Always returns true
  /// (omni is the floating bar's STT); on auth failure it stops the turn.
  @discardableResult
  fileprivate func startOmniTranscription(captureAlreadyRunning: Bool = false) -> Bool {
    let provider = RealtimeOmniSettings.shared.effectiveProvider
    isOmniSTT = true
    omniReceivedTranscript = false
    omniTurnSent = false
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
      guard let self, self.isOmniSTT else { return }
      do {
        let authHeader = try await AuthService.shared.getAuthHeader()
        let base = DesktopBackendEnvironment.pythonBaseURL()
        let service = RealtimeOmniService(
          provider: provider, relayBaseURL: base, authHeader: authHeader, sttOnly: true, delegate: self)
        self.realtimeOmniService = service
        // Flush anything captured while we were fetching auth.
        for raw in self.omniPreconnectBuffer { service.sendAudio(self.resampleForOmni(raw)) }
        self.omniPreconnectBuffer.removeAll()
        service.start()
        log("PushToTalkManager: started omni STT (\(provider.displayName)) via backend relay")
      } catch {
        logError("PushToTalkManager: omni auth failed", error: error)
        self.stopListening()
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

  func omniDidConnect() {
    log("PushToTalkManager: omni STT connected")
  }

  func omniDidReceiveInputTranscript(_ text: String, isFinal: Bool) {
    guard state == .listening || state == .lockedListening
            || state == .pendingLockDecision || state == .finalizing else { return }
    if !text.isEmpty { omniReceivedTranscript = true }
    if isFinal {
      let finalText = text.isEmpty ? lastInterimText : text
      let trimmed = finalText.trimmingCharacters(in: .whitespacesAndNewlines)
      if !trimmed.isEmpty && !transcriptSegments.contains(trimmed) {
        transcriptSegments.append(trimmed)
      }
      lastInterimText = ""
      if state == .finalizing {
        liveFinalizationTimeout?.cancel()
        liveFinalizationTimeout = nil
        guard !omniTurnSent else { return }
        omniTurnSent = true
        sendTranscript()
      }
    } else {
      lastInterimText += text
      barState?.voiceTranscript = lastInterimText
    }
  }

  func omniDidReceiveAudio(_ pcm24k: Data) {
    // STT-only: the omni model's own voice is unused; Claude's reply is spoken
    // by the existing FloatingBarVoicePlaybackService.
  }

  func omniDidFinishTurn() {
    if state == .finalizing {
      liveFinalizationTimeout?.cancel()
      liveFinalizationTimeout = nil
      guard !omniTurnSent else { return }
      omniTurnSent = true
      sendTranscript()
    }
  }

  func omniDidError(_ message: String) {
    logError("PushToTalkManager: omni STT error: \(message)")
    // Benign ONLY if the turn already completed (final transcript sent). A mid-turn relay
    // death — even after a spurious interim like "Olha olha" that set omniReceivedTranscript
    // — must NOT be ignored, or the turn is lost (garbage/no reply). The full turn audio is
    // always buffered in batchAudioBuffer, so we re-transcribe it via Deepgram.
    guard !omniTurnSent,
          state == .listening || state == .lockedListening
            || state == .pendingLockDecision || state == .finalizing
    else { return }
    // Kill the dead relay so finalize() doesn't wait on it; the mic keeps buffering.
    realtimeOmniService?.stop()
    realtimeOmniService = nil
    // If the user already released, transcribe the buffered turn now. If they're still
    // holding, keep capturing — finalize()'s dead-relay branch falls back to Deepgram with
    // the full turn audio (avoids cutting them off mid-sentence).
    if state == .finalizing {
      fallBackToDeepgram()
    }
  }

  /// Transcribe the buffered turn audio via Deepgram when omni is unavailable.
  fileprivate func fallBackToDeepgram() {
    guard !omniTurnSent else { return }
    omniTurnSent = true
    log("PushToTalkManager: omni unavailable — falling back to Deepgram for this turn")
    isOmniSTT = false
    realtimeOmniService?.stop()
    realtimeOmniService = nil
    batchAudioLock.lock()
    let audio = batchAudioBuffer
    batchAudioLock.unlock()
    guard !audio.isEmpty else { sendTranscript(); return }
    barState?.voiceTranscript = "Transcribing…"
    Task { @MainActor [weak self] in
      guard let self else { return }
      do {
        let language = AssistantSettings.shared.effectiveTranscriptionLanguage
        let transcript = try await TranscriptionService.batchTranscribe(
          audioData: audio, language: language,
          contextKeywords: self.currentContextSnapshot?.keywords ?? [])
        if let transcript, !transcript.isEmpty { self.transcriptSegments = [transcript] }
      } catch {
        logError("PushToTalkManager: Deepgram fallback failed", error: error)
      }
      self.liveFinalizationTimeout?.cancel()
      self.liveFinalizationTimeout = nil
      self.sendTranscript()
    }
  }
}
