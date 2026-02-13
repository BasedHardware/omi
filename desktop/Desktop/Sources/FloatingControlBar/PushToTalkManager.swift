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

    updateBarState()

    // Capture screenshot in background — do NOT block the main thread
    Task.detached { [weak self] in
      let url = ScreenCaptureManager.captureScreen()
      await MainActor.run {
        self?.capturedScreenshotURL = url
        log("PushToTalkManager: screenshot captured: \(url?.lastPathComponent ?? "nil")")
      }
    }

    startAudioTranscription()
    log("PushToTalkManager: started listening (hold mode)")
  }

  private func enterLockedListening() {
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil
    state = .lockedListening

    // If we were already listening from the first tap, keep going.
    // Otherwise start fresh.
    if transcriptionService == nil {
      transcriptSegments = []
      lastInterimText = ""

      Task.detached { [weak self] in
        let url = ScreenCaptureManager.captureScreen()
        await MainActor.run {
          self?.capturedScreenshotURL = url
        }
      }

      startAudioTranscription()
    }

    updateBarState()
    log("PushToTalkManager: entered locked listening mode")
  }

  private func stopListening() {
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil
    stopAudioTranscription()
    state = .idle
    capturedScreenshotURL = nil
    transcriptSegments = []
    lastInterimText = ""
    updateBarState()
  }

  private func finalize() {
    guard state == .listening || state == .lockedListening else { return }

    state = .finalizing
    finalizeWorkItem?.cancel()
    finalizeWorkItem = nil
    updateBarState()

    log("PushToTalkManager: finalizing — waiting for last segments")

    // Wait 500ms for DeepGram to flush final segments, then send
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
      Task { @MainActor in
        self?.sendTranscript()
      }
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

    // Reset state
    state = .idle
    transcriptSegments = []
    lastInterimText = ""
    capturedScreenshotURL = nil
    updateBarState()

    guard !query.isEmpty else {
      log("PushToTalkManager: no transcript to send")
      return
    }

    log("PushToTalkManager: sending query (\(query.count) chars): \(query)")
    FloatingControlBarManager.shared.openAIInputWithQuery(query, screenshot: screenshot)
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

    // Start mic capture immediately (before DeepGram connects) so audio is ready
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
        onConnected: { [weak self] in
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

  private func startMicCapture() {
    if audioCaptureService == nil {
      audioCaptureService = AudioCaptureService()
    }
    guard let capture = audioCaptureService else { return }

    do {
      try capture.startCapture(
        onAudioChunk: { [weak self] audioData in
          self?.transcriptionService?.sendAudio(audioData)
        },
        onAudioLevel: { _ in }
      )
      log("PushToTalkManager: mic capture started")
    } catch {
      logError("PushToTalkManager: mic capture failed", error: error)
      stopListening()
    }
  }

  private func stopAudioTranscription() {
    audioCaptureService?.stopCapture()
    transcriptionService?.stop()
    transcriptionService = nil
  }

  private func handleTranscript(_ segment: TranscriptionService.TranscriptSegment) {
    guard state == .listening || state == .lockedListening else { return }

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
  }

  // MARK: - Bar State Sync

  private func updateBarState() {
    guard let barState = barState else { return }
    let wasListening = barState.isVoiceListening
    barState.isVoiceListening =
      (state == .listening || state == .lockedListening || state == .finalizing)
    barState.isVoiceLocked = (state == .lockedListening)
    if state == .idle {
      barState.voiceTranscript = ""
    }

    // Resize the floating bar window for PTT state changes
    if barState.isVoiceListening && !wasListening {
      FloatingControlBarManager.shared.resizeForPTT(expanded: true)
    } else if !barState.isVoiceListening && wasListening {
      FloatingControlBarManager.shared.resizeForPTT(expanded: false)
    }
  }
}
