import AVFoundation
import Cocoa
import Combine

/// Push-to-talk manager for voice input via the Option (⌥) key.
///
/// State machine:
///   idle → [Option down] → listening → [Option up] → finalizing → sends query → idle
///   idle → [Option tap+tap within 400ms] → lockedListening → [Option tap] → finalizing → idle
@MainActor
class PushToTalkManager: ObservableObject {
  static let shared = PushToTalkManager()

  // MARK: - State

  enum PTTState {
    case idle
    case listening
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

  // Transcription
  private var transcriptionService: TranscriptionService?
  private var audioCaptureService: AudioCaptureService?
  private var transcriptSegments: [String] = []
  private var lastInterimText: String = ""
  private var finalizeWorkItem: DispatchWorkItem?
  private var hasMicPermission: Bool = false

  // Batch mode: accumulate raw audio for post-recording transcription
  private var batchAudioBuffer = Data()
  private let batchAudioLock = NSLock()

  // Live mode: timeout for waiting on final transcript after CloseStream
  private var liveFinalizationTimeout: DispatchWorkItem?

  // Screenshot
  private var capturedScreenshotURL: URL?

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
    // Global monitor — fires when OTHER apps are focused
    globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .flagsChanged) {
      [weak self] event in
      Task { @MainActor in
        self?.handleFlagsChanged(event)
      }
    }

    // Local monitor — fires when THIS app is focused
    localMonitor = NSEvent.addLocalMonitorForEvents(matching: .flagsChanged) { [weak self] event in
      Task { @MainActor in
        self?.handleFlagsChanged(event)
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

  // MARK: - Option Key Handling

  private func handleFlagsChanged(_ event: NSEvent) {
    // Don't process PTT when the floating bar is hidden
    guard FloatingControlBarManager.shared.isVisible else { return }

    let settings = ShortcutSettings.shared

    let pttActive: Bool
    switch settings.pttKey {
    case .option:
      // Ignore if other modifiers are held (Cmd, Ctrl, Shift)
      let otherModifiers: NSEvent.ModifierFlags = [.command, .control, .shift]
      guard event.modifierFlags.intersection(otherModifiers) == [] else { return }
      pttActive = event.modifierFlags.contains(.option)
    case .rightCommand:
      // Right Cmd: keyCode 54. flagsChanged fires for both left/right Cmd.
      // Only trigger on right Cmd (keyCode 54), not left (55).
      guard event.keyCode == 54 || event.keyCode == 55 else { return }
      pttActive = event.modifierFlags.contains(.command) && event.keyCode == 54
    case .fn:
      pttActive = event.modifierFlags.contains(.function)
    }

    if pttActive {
      handleOptionDown()
    } else {
      handleOptionUp()
    }
  }

  private func handleOptionDown() {
    let now = ProcessInfo.processInfo.systemUptime

    switch state {
    case .idle:
      // Check for double-tap: if last Option-up was recent, enter locked mode
      if ShortcutSettings.shared.doubleTapForLock && (now - lastOptionUpTime) < doubleTapThreshold {
        enterLockedListening()
      } else {
        lastOptionDownTime = now
        startListening()
      }

    case .listening:
      // Already listening (hold mode), ignore repeated flagsChanged
      break

    case .lockedListening:
      // Tap while locked → finalize
      finalize()

    case .finalizing:
      break
    }
  }

  private func handleOptionUp() {
    let now = ProcessInfo.processInfo.systemUptime

    switch state {
    case .listening:
      let holdDuration = now - lastOptionDownTime
      lastOptionUpTime = now

      if ShortcutSettings.shared.doubleTapForLock && holdDuration < doubleTapThreshold {
        // Short tap — delay briefly to allow double-tap detection
        let workItem = DispatchWorkItem { [weak self] in
          Task { @MainActor in
            guard let self = self, self.state == .listening else { return }
            self.finalize()
          }
        }
        finalizeWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + doubleTapThreshold, execute: workItem)
      } else {
        // Long hold released — finalize immediately
        finalize()
      }

    case .lockedListening:
      // In locked mode, Option-up is ignored (we finalize on next Option-down)
      lastOptionUpTime = now

    case .idle, .finalizing:
      lastOptionUpTime = now
    }
  }

  // MARK: - Listening Lifecycle

  private func startListening() {
    state = .listening
    transcriptSegments = []
    lastInterimText = ""
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil

    // Play start-of-PTT sound
    if ShortcutSettings.shared.pttSoundsEnabled {
      let sound = NSSound(named: "Funk")
      sound?.volume = 0.3
      sound?.play()
    }

    // Check if an AI conversation is already active — enter follow-up mode
    let isFollowUp = barState?.showingAIResponse == true
    if isFollowUp {
      barState?.isVoiceFollowUp = true
      barState?.voiceFollowUpTranscript = ""
    }

    AnalyticsManager.shared.floatingBarPTTStarted(mode: isFollowUp ? "follow_up_hold" : "hold")
    updateBarState()

    // Only capture screenshot if not in follow-up mode (conversation already has context)
    if !isFollowUp {
      Task.detached { [weak self] in
        let url = ScreenCaptureManager.captureScreen()
        guard let self else { return }
        await MainActor.run {
          self.capturedScreenshotURL = url
          log("PushToTalkManager: screenshot captured: \(url?.lastPathComponent ?? "nil")")
        }
      }
    }

    startAudioTranscription()
    log("PushToTalkManager: started listening (hold mode, followUp=\(isFollowUp))")
  }

  private func enterLockedListening() {
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil
    state = .lockedListening

    // Play start-of-PTT sound for locked mode
    if ShortcutSettings.shared.pttSoundsEnabled {
      let sound = NSSound(named: "Funk")
      sound?.volume = 0.3
      sound?.play()
    }

    // Check if an AI conversation is already active — enter follow-up mode
    let isFollowUp = barState?.showingAIResponse == true
    if isFollowUp {
      barState?.isVoiceFollowUp = true
      barState?.voiceFollowUpTranscript = ""
    }

    AnalyticsManager.shared.floatingBarPTTStarted(mode: isFollowUp ? "follow_up_locked" : "locked")

    // If we were already listening from the first tap, keep going.
    // Otherwise start fresh.
    if transcriptionService == nil {
      transcriptSegments = []
      lastInterimText = ""

      // Only capture screenshot if not in follow-up mode
      if !isFollowUp {
        Task.detached { [weak self] in
          let url = ScreenCaptureManager.captureScreen()
          guard let self else { return }
          await MainActor.run {
            self.capturedScreenshotURL = url
          }
        }
      }

      startAudioTranscription()
    }

    updateBarState()
    log("PushToTalkManager: entered locked listening mode (followUp=\(isFollowUp))")
  }

  private func stopListening() {
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil
    liveFinalizationTimeout?.cancel()
    liveFinalizationTimeout = nil
    stopAudioTranscription()
    state = .idle
    capturedScreenshotURL = nil
    transcriptSegments = []
    lastInterimText = ""
    batchAudioLock.lock()
    batchAudioBuffer = Data()
    batchAudioLock.unlock()
    updateBarState()
  }

  /// Cancel PTT without sending — used when conversation is closed mid-PTT.
  func cancelListening() {
    guard state != .idle else { return }
    log("PushToTalkManager: cancelling listening")
    barState?.isVoiceFollowUp = false
    barState?.voiceFollowUpTranscript = ""
    stopListening()
  }

  private var finalizedMode: String = "hold"

  private func finalize() {
    guard state == .listening || state == .lockedListening else { return }

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
          let language = AssistantSettings.shared.effectiveTranscriptionLanguage
          let transcript = try await TranscriptionService.batchTranscribe(
            audioData: audioData,
            language: language
          )
          if let transcript, !transcript.isEmpty {
            self.transcriptSegments = [transcript]
          }
        } catch {
          logError("PushToTalkManager: batch transcription failed", error: error)
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
    let screenshot = capturedScreenshotURL
    let hasQuery = !query.isEmpty
    let wasFollowUp = barState?.isVoiceFollowUp == true

    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: finalizedMode,
      hadTranscript: hasQuery,
      transcriptLength: query.count
    )

    // Clear follow-up state
    barState?.isVoiceFollowUp = false
    barState?.voiceFollowUpTranscript = ""

    // Reset state — skip PTT collapse resize when we have a query,
    // because openAIInputWithQuery will resize to the correct size.
    // Also skip resize when in follow-up mode (panel is already at response size).
    state = .idle
    transcriptSegments = []
    lastInterimText = ""
    capturedScreenshotURL = nil
    updateBarState(skipResize: hasQuery || wasFollowUp)

    guard hasQuery else {
      log("PushToTalkManager: no transcript to send")
      return
    }

    if wasFollowUp {
      log("PushToTalkManager: sending follow-up query (\(query.count) chars): \(query)")
      FloatingControlBarManager.shared.sendFollowUpQuery(query)
    } else {
      log("PushToTalkManager: sending query (\(query.count) chars): \(query)")
      FloatingControlBarManager.shared.openAIInputWithQuery(query, screenshot: screenshot)
    }
  }

  // MARK: - Audio Transcription (Dedicated Session)

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
        let service = try TranscriptionService(language: language, channels: 1)
        transcriptionService = service

        service.start(
          onTranscript: { [weak self] segment in
            Task { @MainActor in
              self?.handleTranscript(segment)
            }
          },
          onError: { [weak self] error in
            Task { @MainActor in
              logError("PushToTalkManager: transcription error", error: error)
              self?.stopListening()
            }
          },
          onConnected: {
            Task { @MainActor in
              log("PushToTalkManager: DeepGram connected")
            }
          }
        )
      } catch {
        logError("PushToTalkManager: failed to create TranscriptionService", error: error)
        stopListening()
      }
    }
  }

  private func startMicCapture(batchMode: Bool = false) {
    if audioCaptureService == nil {
      audioCaptureService = AudioCaptureService()
    }
    guard let capture = audioCaptureService else { return }

    Task { @MainActor [weak self] in
      guard let self else { return }
      do {
        try await capture.startCapture(
          onAudioChunk: { [weak self] audioData in
            guard let self else { return }
            if batchMode {
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

  private func stopAudioTranscription() {
    audioCaptureService?.stopCapture()
    transcriptionService?.stop()
    transcriptionService = nil
  }

  private func handleTranscript(_ segment: TranscriptionService.TranscriptSegment) {
    guard state == .listening || state == .lockedListening || state == .finalizing else { return }

    if segment.speechFinal || segment.isFinal {
      transcriptSegments.append(segment.text)
      lastInterimText = ""
    } else {
      // Track latest interim text as fallback
      lastInterimText = segment.text
    }

    // Update live transcript in the bar
    let liveText: String
    if segment.speechFinal || segment.isFinal {
      liveText = transcriptSegments.joined(separator: " ")
    } else {
      let committed = transcriptSegments.joined(separator: " ")
      liveText = committed.isEmpty ? segment.text : committed + " " + segment.text
    }
    barState?.voiceTranscript = liveText

    // Also update follow-up transcript if in follow-up mode
    if barState?.isVoiceFollowUp == true {
      barState?.voiceFollowUpTranscript = liveText
    }

    // In finalizing state, a final segment means Deepgram is done — send immediately
    if state == .finalizing && (segment.speechFinal || segment.isFinal) {
      log("PushToTalkManager: received final transcript during finalization — sending now")
      liveFinalizationTimeout?.cancel()
      liveFinalizationTimeout = nil
      sendTranscript()
    }
  }

  // MARK: - Bar State Sync

  private func updateBarState(skipResize: Bool = false) {
    guard let barState = barState else { return }
    let wasListening = barState.isVoiceListening
    barState.isVoiceListening =
      (state == .listening || state == .lockedListening || state == .finalizing)
    barState.isVoiceLocked = (state == .lockedListening)
    if state == .idle {
      barState.voiceTranscript = ""
    }

    // Skip resize when in follow-up mode or expanded AI conversation (already at full size)
    guard !skipResize && !barState.isVoiceFollowUp && !barState.showingAIConversation else { return }
    if barState.isVoiceListening && !wasListening {
      FloatingControlBarManager.shared.resizeForPTT(expanded: true)
    } else if !barState.isVoiceListening && wasListening {
      FloatingControlBarManager.shared.resizeForPTT(expanded: false)
    }
  }
}
