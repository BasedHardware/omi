import AVFoundation
import Cocoa
import Combine
import CoreAudio

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
  /// When set, the next finalized PTT turn is a voice follow-up to this agent pill:
  /// it uses the realtime omni STT and routes the transcript into the pill's agent
  /// session (RealtimeHub pipeline), NOT the floating bar or the hub model.
  private var followUpPill: AgentPill?
  // Cached local cue for the instant PTT-up ack (preloaded so play() never hits disk).
  private lazy var ackSound: NSSound? = {
    let s = NSSound(named: "Pop")
    s?.volume = 0.35
    return s
  }()
  // Mic chunks captured before the relay finishes connecting (raw 16k PCM),
  // flushed once the service exists so the user's first words aren't clipped.
  private var omniPreconnectBuffer: [Data] = []
  // True once the omni model returned any transcript this turn — gates the
  // Deepgram fallback so a benign trailing socket error doesn't trigger it.
  private var omniReceivedTranscript = false
  private var omniTurnSent = false  // dedup: send/fallback the omni turn at most once
  private var audioCaptureService: AudioCaptureService?
  private var transcriptSegments: [String] = []
  private var lastInterimText: String = ""
  private var finalizeWorkItem: DispatchWorkItem?
  private var hasMicPermission: Bool = false
  private var isCurrentSessionFollowUp = false
  private var currentContextSnapshot: PTTContextSnapshot?
  private var contextCaptureTask: Task<Void, Never>?

  // Batch mode: accumulate raw audio for post-recording transcription
  private var batchAudioBuffer = Data()
  private let batchAudioLock = NSLock()

  // Live mode: timeout for waiting on final transcript after CloseStream
  private var liveFinalizationTimeout: DispatchWorkItem?

  private init() {}

  // MARK: - Setup / Teardown

  func setup(barState: FloatingControlBarState) {
    self.barState = barState
    hasMicPermission = AudioCaptureService.checkPermission()
    installEventMonitors()
    // Realtime hub: wire it to the bar and warm the WS if it's enabled + BYOK-keyed,
    // so the persistent socket is ready before the first PTT (and stays warm after).
    RealtimeHubController.shared.setup(barState: barState)
    RealtimeHubController.shared.ensureWarm()
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

  private func startListening() {
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
    if ShortcutSettings.shared.pttMuteSystemAudio {
      SystemAudioMuteController.shared.muteForListening()
    }
    state = .listening
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

    let isFollowUp = isCurrentSessionFollowUp
    AnalyticsManager.shared.floatingBarPTTStarted(mode: isFollowUp ? "follow_up_hold" : "hold")
    let preOverlayImage = ScreenCaptureManager.captureScreenImage()
    updateBarState()

    captureContextAndStartAudio(preOverlayImage: preOverlayImage)
    log("PushToTalkManager: started listening (hold mode, followUp=\(isFollowUp))")
  }

  private func enterLockedListening() {
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

    let isFollowUp = isCurrentSessionFollowUp
    AnalyticsManager.shared.floatingBarPTTStarted(mode: isFollowUp ? "follow_up_locked" : "locked")

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
    log("PushToTalkManager: entered locked listening mode (followUp=\(isFollowUp))")
  }

  private func enterPendingLockDecision() {
    guard state == .listening else { return }

    state = .pendingLockDecision
    audioCaptureService?.stopCapture()
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
    if isHubMode {
      isHubMode = false
      RealtimeHubController.shared.cancelTurn()
    }
    if followUpPill != nil {
      followUpPill = nil
      AgentPillsManager.shared.recordingPillID = nil
    }
    stopAudioTranscription()
    state = .idle
    transcriptSegments = []
    lastInterimText = ""
    currentContextSnapshot = nil
    batchAudioLock.lock()
    batchAudioBuffer = Data()
    batchAudioLock.unlock()
    isCurrentSessionFollowUp = false
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

  private var finalizedMode: String = "hold"

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
  private static let minTurnAudioSeconds: Double = 0.35
  private static let minVoicedSeconds: Double = 0.2
  /// RMS threshold (int16 samples) above which a 20ms frame counts as voiced.
  /// ~-41 dBFS: comfortably above quiet-room mic noise, far below soft speech.
  private static let voicedRMSThreshold: Double = 300
  // Hub silence gate is gentler than the omni gate: the realtime model tolerates a
  // little noise, and a too-strict gate that drops real speech ("not even listening")
  // is far worse than occasionally letting a marginal turn through. Lower RMS so a
  // quieter / further mic still registers, and require only a sliver of voice.
  private static let hubVoicedRMSThreshold: Double = 170
  private static let hubMinTurnAudioSeconds: Double = 0.2
  private static let hubMinVoicedSeconds: Double = 0.08

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
    // Energy gate FIRST: clear/audible speech (the common case) must always pass. The Silero
    // classifier was intermittently misclassifying real speech as "no speech" and discarding
    // whole turns — RMS energy is reliable for audible speech, so accept it outright.
    let (total, voiced) = voicedAudioSeconds(pcm16k: data, rmsThreshold: hubVoicedRMSThreshold)
    if total >= hubMinTurnAudioSeconds && voiced >= hubMinVoicedSeconds { return true }
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
    finalizedMode = state == .lockedListening ? "locked" : "hold"
    state = .finalizing
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil

    // Stop mic immediately — no more audio capture
    audioCaptureService?.stopCapture()
    activeTracer?.end("audio_capture")
    activeTracer?.end("ptt_recording")

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
        log(
          "PushToTalkManager: discarding hub turn — audio \(String(format: "%.2f", totalSec))s "
            + "peak=\(peak)/32767 rms=\(rms) device=[\(dev)] "
            + "(peak≈0 ⇒ dead mic; high peak ⇒ classifier misfire; low ⇒ quiet/far mic) — not committing"
        )
        RealtimeHubController.shared.cancelTurn()
        AnalyticsManager.shared.floatingBarPTTEnded(
          mode: finalizedMode, hadTranscript: false, transcriptLength: 0)
        updateBarState()  // clears the listening UI (no "…")
        return
      }
      // Real speech — instant local ack + commit. The hub speaks the reply and
      // dispatches tools itself; no transcript/router/LLM hop here.
      if ShortcutSettings.shared.pttSoundsEnabled { ackSound?.play() }
      RealtimeHubController.shared.commitTurn()
      // Collapse the bar on release — the hub speaks its reply as audio (no inline
      // status UI), the same as the legacy voice path.
      updateBarState()
      AnalyticsManager.shared.floatingBarPTTEnded(
        mode: finalizedMode, hadTranscript: true, transcriptLength: 0)
      log("PushToTalkManager: hub turn committed (instant ack)")
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
        log(
          "PushToTalkManager: discarding silent turn (audio \(String(format: "%.2f", totalSec))s, voiced \(String(format: "%.2f", voicedSec))s) — not transcribing"
        )
        AnalyticsManager.shared.floatingBarPTTEnded(
          mode: finalizedMode, hadTranscript: false, transcriptLength: 0)
        stopListening()
        return
      }
    }

    // Play end-of-PTT sound
    if ShortcutSettings.shared.pttSoundsEnabled {
      let sound = NSSound(named: "Bottle")
      sound?.volume = 0.3
      sound?.play()
    }

    // Realtime omni: commit the turn and wait for the final transcript.
    if isOmniSTT {
      // QueryTracer: the omni provider's post-commit finalization (VAD close +
      // final STT inference + round-trip) — closed at the top of sendTranscript().
      activeTracer?.begin(
        "omni_transcribe", metadata: ["provider": RealtimeOmniSettings.shared.effectiveProvider.displayName])
      realtimeOmniService?.commitInputTurn()
      log("PushToTalkManager: finalizing (omni STT) — waiting for final transcript")
      let timeout = DispatchWorkItem { [weak self] in
        Task { @MainActor in
          guard let self, self.state == .finalizing else { return }
          log("PushToTalkManager: omni finalization timeout — sending transcript")
          self.sendTranscript()
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
        log("PushToTalkManager: batch mode — no audio recorded")
        sendTranscript()
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
      isHubMode = true
      // Retain the turn's raw audio so finalize() can silence-gate it.
      batchAudioLock.lock(); batchAudioBuffer = Data(); batchAudioLock.unlock()
      RealtimeHubController.shared.beginTurn()
      // Bluetooth output: opening a BT mic forces the device into 16 kHz HFP mode,
      // which drops the OUTPUT rate too and chops the spoken reply (the A2DP↔HFP
      // flap). So when output is Bluetooth, capture from the built-in mic instead —
      // the BT device stays in A2DP and the reply plays full-quality. Trade-off: it
      // then listens via the Mac mic, so the user must speak toward the laptop
      // (talking into far AirPods won't register). The gentle hub silence gate
      // (170 RMS) lets the built-in mic register far better than the old 300-RMS one.
      if AudioCaptureService.isDefaultOutputBluetooth(),
        let builtIn = AudioCaptureService.findBuiltInMicDeviceID()
      {
        log("PushToTalkManager: hub on Bluetooth output — capturing from built-in mic to keep A2DP")
        startMicCapture(overrideDeviceID: builtIn)
      } else {
        startMicCapture()
      }
      log("PushToTalkManager: realtime hub active — model is the voice hub")
      return
    }

    // The floating bar's STT is the realtime omni model (replaces Deepgram):
    // one omni model transcribes; reasoning/tools/TTS are untouched (the final
    // transcript still goes to ChatProvider via sendTranscript()/sendQuery()).
    // Falls back to legacy Deepgram STT only if no provider key is available.
    if startOmniTranscription() { return }

    let isBatchMode = ShortcutSettings.shared.pttTranscriptionMode == .batch

    if isBatchMode {
      // Batch mode: just capture audio into buffer, no streaming connection
      batchAudioLock.lock()
      batchAudioBuffer = Data()
      batchAudioLock.unlock()
      startMicCapture(batchMode: true)
      log("PushToTalkManager: started audio capture (batch mode)")
    } else {
      // Live mode: start mic capture and stream to Deepgram
      startMicCapture()

      do {
        let language = AssistantSettings.shared.effectiveTranscriptionLanguage
        let service = try TranscriptionService(
          language: language,
          channels: 1,
          contextKeywords: currentContextSnapshot?.keywords ?? []
        )
        transcriptionService = service

        service.start(
          onSegments: { [weak self] segments in
            Task { @MainActor in
              self?.handleTranscriptSegments(segments)
            }
          },
          onEvent: { _ in },  // PTT doesn't use events
          onError: { [weak self] error in
            Task { @MainActor in
              logError("PushToTalkManager: transcription error", error: error)
              self?.stopListening()
            }
          },
          onConnected: {
            Task { @MainActor in
              log("PushToTalkManager: backend connected")
            }
          }
        )
      } catch {
        logError("PushToTalkManager: failed to create TranscriptionService", error: error)
        stopListening()
      }
    }
  }

  private func startMicCapture(batchMode: Bool = false, overrideDeviceID: AudioDeviceID? = nil) {
    if audioCaptureService == nil {
      if let override = overrideDeviceID {
        audioCaptureService = AudioCaptureService(overrideDeviceID: override)
      } else {
        audioCaptureService = AudioCaptureService()
      }
    }
    guard let capture = audioCaptureService else { return }

    // Silent-mic watchdog: Bluetooth input often returns zero samples while another app
    // holds A2DP output. Fall back to the built-in mic so PTT still captures the user.
    capture.onSilentMicDetected = { [weak self] in
      Task { @MainActor in
        self?.handleSilentMicFallback(batchMode: batchMode)
      }
    }

    Task { @MainActor [weak self] in
      guard let self else { return }
      do {
        try await capture.startCapture(
          onAudioChunk: { [weak self] audioData in
            guard let self else { return }
            if self.isHubMode {
              // Realtime hub owns this turn — stream mic PCM straight to it, and
              // retain it so finalize() can silence-gate the turn.
              RealtimeHubController.shared.feedAudio(audioData)
              self.batchAudioLock.lock()
              self.batchAudioBuffer.append(audioData)
              self.batchAudioLock.unlock()
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
              self.batchAudioLock.lock()
              self.batchAudioBuffer.append(audioData)
              self.batchAudioLock.unlock()
            } else if batchMode {
              // Batch mode: accumulate audio in buffer
              self.batchAudioLock.lock()
              self.batchAudioBuffer.append(audioData)
              self.batchAudioLock.unlock()
            } else {
              // Live mode: stream to Deepgram
              self.transcriptionService?.sendAudio(audioData)
            }
          },
          onAudioLevel: { _ in }
        )
        log("PushToTalkManager: mic capture started (batch=\(batchMode))")
      } catch {
        logError("PushToTalkManager: mic capture failed", error: error)
        self.stopListening()
      }
    }
  }

  /// Swap the current capture for one pinned to the built-in mic when the silent-mic
  /// watchdog detects a dead Bluetooth input (A2DP profile conflict).
  @MainActor
  private func handleSilentMicFallback(batchMode: Bool) {
    guard state == .listening || state == .lockedListening || state == .pendingLockDecision else {
      return
    }
    guard let builtInID = AudioCaptureService.findBuiltInMicDeviceID() else {
      log("PushToTalkManager: silent-mic detected but no built-in mic to fall back to")
      return
    }
    log("PushToTalkManager: silent-mic fallback — switching to built-in mic (deviceID=\(builtInID))")
    audioCaptureService?.stopCapture()
    audioCaptureService = nil
    startMicCapture(batchMode: batchMode, overrideDeviceID: builtInID)
  }

  private func stopAudioTranscription() {
    audioCaptureService?.stopCapture()
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
    let isShowingVoiceUI = (state == .listening || state == .lockedListening)
    barState.isVoiceListening = isShowingVoiceUI
    barState.isVoiceLocked = (state == .lockedListening)
    barState.isVoiceFollowUp = isCurrentSessionFollowUp && isShowingVoiceUI
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
    } else if !barState.isVoiceListening && wasListening {
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
  fileprivate func startOmniTranscription() -> Bool {
    let provider = RealtimeOmniSettings.shared.effectiveProvider
    isOmniSTT = true
    omniReceivedTranscript = false
    omniTurnSent = false
    omniPreconnectBuffer.removeAll()
    // Keep a copy of the whole turn so we can fall back to Deepgram if the relay
    // is unreachable (e.g. backend not yet on prod) — PTT must never break.
    batchAudioLock.lock(); batchAudioBuffer = Data(); batchAudioLock.unlock()
    startMicCapture()  // capture immediately; chunks buffer until the relay connects
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
    // If the omni model already gave us a transcript this turn, the error is a
    // benign teardown — ignore it. Otherwise the relay is unreachable (e.g. the
    // backend isn't on prod yet): fall back to Deepgram so PTT never breaks.
    guard !omniReceivedTranscript,
          state == .listening || state == .lockedListening
            || state == .pendingLockDecision || state == .finalizing
    else { return }
    fallBackToDeepgram()
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
