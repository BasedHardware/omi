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
  // Mic chunks captured before the relay finishes connecting (raw 16k PCM),
  // flushed once the service exists so the user's first words aren't clipped.
  private var omniPreconnectBuffer: [Data] = []
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
    state = .listening
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
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil
    liveFinalizationTimeout?.cancel()
    liveFinalizationTimeout = nil
    contextCaptureTask?.cancel()
    contextCaptureTask = nil
    stopAudioTranscription()
    state = .idle
    transcriptSegments = []
    lastInterimText = ""
    currentContextSnapshot = nil
    batchAudioLock.lock()
    batchAudioBuffer = Data()
    batchAudioLock.unlock()
    isCurrentSessionFollowUp = false
    updateBarState()
  }

  /// Cancel PTT without sending — used when conversation is closed mid-PTT.
  func cancelListening() {
    guard state != .idle else { return }
    log("PushToTalkManager: cancelling listening")
    stopListening()
  }

  private var finalizedMode: String = "hold"

  private func finalize() {
    guard state == .listening || state == .lockedListening || state == .pendingLockDecision else { return }

    lastOptionUpTime = 0
    finalizedMode = state == .lockedListening ? "locked" : "hold"
    state = .finalizing
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil
    updateBarState()

    // Stop mic immediately — no more audio capture
    audioCaptureService?.stopCapture()

    // Play end-of-PTT sound
    if ShortcutSettings.shared.pttSoundsEnabled {
      let sound = NSSound(named: "Bottle")
      sound?.volume = 0.3
      sound?.play()
    }

    // Realtime omni: commit the turn and wait for the final transcript.
    if isOmniSTT {
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

    Task { [weak self, query, contextKeywords, wasFollowUp] in
      let cleanedQuery = await PTTTranscriptCleanupService.shared.cleanup(query, keywords: contextKeywords)
      await MainActor.run {
        self?.sendQuery(cleanedQuery, wasFollowUp: wasFollowUp)
      }
    }
  }

  private func sendQuery(_ query: String, wasFollowUp: Bool) {
    if wasFollowUp {
      log("PushToTalkManager: sending follow-up query (\(query.count) chars): \(query)")
      FloatingControlBarManager.shared.sendFollowUpQuery(query, fromVoice: true)
    } else {
      log("PushToTalkManager: sending query (\(query.count) chars): \(query)")
      FloatingControlBarManager.shared.openAIInputWithQuery(query, fromVoice: true)
    }
  }

  // MARK: - Audio Transcription (Dedicated Session)

  private func captureContextAndStartAudio(preOverlayImage: CGImage? = nil) {
    contextCaptureTask?.cancel()
    startAudioTranscription()
    let captureStartedAt = Date()
    contextCaptureTask = Task { [weak self] in
      let snapshot = await PTTContextVocabularyProvider.capture(at: captureStartedAt, preOverlayImage: preOverlayImage)
      await MainActor.run {
        guard let self, !Task.isCancelled else { return }
        guard self.state == .listening || self.state == .lockedListening || self.state == .finalizing else { return }
        self.currentContextSnapshot = snapshot
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
            if self.isOmniSTT {
              // Realtime omni: stream mic PCM (resampled to the provider's rate),
              // or buffer raw until the relay finishes connecting.
              if let svc = self.realtimeOmniService {
                svc.sendAudio(self.resampleForOmni(audioData))
              } else {
                self.omniPreconnectBuffer.append(audioData)
              }
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
    omniPreconnectBuffer.removeAll()
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
      sendTranscript()
    }
  }

  func omniDidError(_ message: String) {
    logError("PushToTalkManager: omni STT error: \(message)")
    stopListening()
  }
}
