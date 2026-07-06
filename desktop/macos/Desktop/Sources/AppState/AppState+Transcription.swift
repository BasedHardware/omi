import AVFoundation
import Combine
import SwiftUI
import UserNotifications

@MainActor
extension AppState {
  func toggleTranscription() {
    if isTranscribing {
      stopTranscription()
    } else {
      startTranscription()
    }
  }

  /// Start real-time transcription
  /// - Parameter source: Audio source to use (defaults to current audioSource setting)
  func startTranscription(source: AudioSource? = nil) {
    guard !isTranscribing else { return }
    if !sttFallbackInProgress {
      sttCloudFallbackTried = false
      forceLocalSTTForSession = false
    }

    // Paywall hard-stop: every code path that enables the mic + WS streaming
    // funnels through here, including auto-restart from sleep and toggle
    // shortcuts. Refuse to start and surface the upgrade popup.
    if blockIfPaywalled() { return }

    // Use provided source or fall back to current setting
    let effectiveSource = source ?? audioSource
    var recordingConversationSource = currentConversationSource

    // For BLE device, check if device is connected
    if effectiveSource == .bleDevice {
      guard DeviceProvider.shared.isConnected else {
        showAlert(title: "Device Not Connected", message: "Please connect a wearable device first.")
        return
      }
    } else {
      // For microphone, check permission
      guard AudioCaptureService.checkPermission() else {
        requestMicrophonePermission()
        return
      }
    }

    do {
      // Get effective language from settings (handles auto-detect vs single language)
      let effectiveLanguage = AssistantSettings.shared.effectiveTranscriptionLanguage
      log(
        "Transcription: Using language=\(effectiveLanguage) (autoDetect=\(AssistantSettings.shared.transcriptionAutoDetect), selected=\(AssistantSettings.shared.transcriptionLanguage))"
      )

      // Desktop transcribes on-device with Parakeet by default on Apple Silicon — no Deepgram.
      // Intel Macs (no Neural Engine) fall back to the cloud path. Force cloud for debugging with
      // OMI_FORCE_CLOUD_STT=1 or `defaults write <bundle> forceCloudSTT -bool true`.
      let forceCloudSTT = !forceLocalSTTForSession  // reverse fallback overrides toward on-device
        && (ProcessInfo.processInfo.environment["OMI_FORCE_CLOUD_STT"] == "1"
          || UserDefaults.standard.bool(forKey: "forceCloudSTT")
          || forceCloudSTTForSession)  // set after an on-device Parakeet model-load failure
      useLocalSTT = effectiveSource != .bleDevice && !forceCloudSTT && Self.isAppleSilicon
      let clientConversationId = UUID().uuidString.lowercased()

      if useLocalSTT {
        log("Transcription: ON-DEVICE Parakeet mode (OMI_LOCAL_STT) — no cloud STT")
        // Segments are delivered on the main actor by the service, so no Task hop here.
        let onLocalSegments: LocalTranscriptionService.SegmentsHandler = { [weak self] segments in
          self?.handleBackendSegments(segments)
        }
        // If the on-device model can't load, fall back to cloud STT instead of recording
        // into a void (the failure is otherwise silent — a blank transcript).
        let onModelLoadFailed: @MainActor () -> Void = { [weak self] in
          self?.handleLocalSTTModelLoadFailure()
        }
        // Mic = the user; system audio = another speaker. Transcribed separately for diarization.
        let mic = LocalTranscriptionService(language: effectiveLanguage, isUser: true)
        mic.start(onSegments: onLocalSegments, onModelLoadFailed: onModelLoadFailed)
        localMicService = mic
        let system = LocalTranscriptionService(language: effectiveLanguage, isUser: false)
        system.start(onSegments: onLocalSegments, onModelLoadFailed: onModelLoadFailed)
        localSystemService = system
      } else {
        // Always streaming via Python backend /v4/listen
        transcriptionService = try TranscriptionService(
          language: effectiveLanguage,
          clientConversationId: clientConversationId
        )
      }

      // Set conversation source based on audio source
      if effectiveSource == .bleDevice, let device = DeviceProvider.shared.connectedDevice {
        currentConversationSource = ConversationSource.from(deviceType: device.type)
        recordingInputDeviceName = device.displayName
      } else {
        currentConversationSource = .desktop
        recordingInputDeviceName = AudioCaptureService.getCurrentMicrophoneName()
      }
      recordingConversationSource = currentConversationSource

      // Initialize audio services based on source
      if effectiveSource == .microphone {
        // Initialize audio capture service
        audioCaptureService = AudioCaptureService()

        // Initialize audio mixer for combining mic and system audio
        audioMixer = AudioMixer()

        // VAD gate not used for Python backend streaming (backend handles its own VAD)
        vadGateService = nil

        // Initialize system audio capture if supported (macOS 14.4+) and not in "Never" mode.
        // The actual start/stop is driven by reconcileCapture() based on the user's System Audio
        // mode (Always / Only during meetings / Never) and meeting state. `.never` is also forced
        // by the hidden `disableSystemAudioCapture` debug flag — see effectiveSystemAudioMode.
        // Toggle the debug flag with: defaults write <bundle> disableSystemAudioCapture -bool true
        let systemAudioMode = effectiveSystemAudioMode
        if systemAudioMode == .never {
          log("Transcription: System audio capture mode = never — not initializing")
        } else if #available(macOS 14.4, *) {
          systemAudioCaptureService = SystemAudioCaptureService()
          log(
            "Transcription: System audio capture initialized (mode=\(systemAudioMode.rawValue), macOS 14.4+)"
          )
        } else {
          log("Transcription: System audio capture not available (requires macOS 14.4+)")
        }
      }
      // For BLE device, BleAudioService will be used in startAudioCapture

      // Streaming mode: start transcription service first, then audio on connect.
      // Local (Parakeet) mode has no WebSocket — start capture immediately instead.
      if useLocalSTT {
        Task { [weak self] in
          await self?.startAudioCapture(source: effectiveSource)
        }
      } else {
      transcriptionService?.start(
        onSegments: { [weak self] segments in
          Task { @MainActor in
            self?.handleBackendSegments(segments)
          }
        },
        onEvent: { [weak self] event in
          Task { @MainActor in
            self?.handleListenEvent(event)
          }
        },
        onError: { [weak self] error in
          Task { @MainActor in
            logError("Transcription error", error: error)
            AnalyticsManager.shared.recordingError(
              error: error.localizedDescription,
              reason: "cloud_stt_error",
              source: self?.currentConversationSource.rawValue,
              stage: "streaming"
            )
            // Cloud WS gave up (reconnects exhausted) → try to keep recording on-device
            // instead of dropping it. Falls through to stopTranscription if not possible.
            self?.handleCloudSTTReconnectFailure()
          }
        },
        onConnected: { [weak self] in
          Task { @MainActor in
            log("Transcription: Connected to Python backend")
            // Start audio capture once connected
            await self?.startAudioCapture(source: effectiveSource)
          }
        },
        onDisconnected: {
          log("Transcription: Disconnected from Python backend")
        }
      )
      }

      isTranscribing = true
      recordingGeneration &+= 1
      AssistantSettings.shared.transcriptionEnabled = true
      audioSource = effectiveSource
      currentTranscript = ""
      speakerSegments = []
      totalSegmentCount = 0
      totalWordCount = 0
      liveSpeakerPersonMap = [:]
      LiveTranscriptMonitor.shared.clear()
      recordingStartTime = Date()
      currentBackendConversationId = nil
      pendingBackendConversationId = nil
      ignoredRotatedBackendConversationIds = []
      AudioLevelMonitor.shared.reset()
      RecordingTimer.shared.start()

      log(
        "Transcription: Using source: \(effectiveSource.rawValue), device: \(recordingInputDeviceName ?? "Unknown")"
      )

      // Create crash-safe DB session for persistence
      Task {
        do {
          let sessionId = try await TranscriptionStorage.shared.startSession(
            source: currentConversationSource.rawValue,
            language: effectiveLanguage,
            timezone: TimeZone.current.identifier,
            inputDeviceName: recordingInputDeviceName,
            clientConversationId: useLocalSTT ? nil : clientConversationId,
            finalizationStrategy: useLocalSTT ? .localSegments : .cloudReconcile
          )
          await MainActor.run {
            self.currentSessionId = sessionId
            // Start live notes session
            LiveNotesMonitor.shared.startSession(sessionId: sessionId)
          }
          if let backendId = await MainActor.run(body: { () -> String? in
            let candidate = self.pendingBackendConversationId ?? self.currentBackendConversationId
            guard let candidate else { return nil }
            return DesktopConversationMatchPolicy.shouldBindConversationSession(
              incomingBackendId: candidate,
              activeBackendId: self.currentBackendConversationId,
              ignoredRotatedBackendIds: self.ignoredRotatedBackendConversationIds
            ) ? candidate : nil
          }) {
            try await TranscriptionStorage.shared.bindBackendConversation(id: sessionId, backendId: backendId)
            await MainActor.run {
              self.currentBackendConversationId = backendId
              self.pendingBackendConversationId = nil
              self.ignoredRotatedBackendConversationIds = []
            }
          }
          log("Transcription: Created DB session \(sessionId)")
        } catch {
          logError("Transcription: Failed to create DB session", error: error)
          // Non-fatal - continue recording even if DB fails
        }
      }

      // Start 4-hour max recording timer
      maxRecordingTimer = Timer.scheduledTimer(
        withTimeInterval: maxRecordingDuration, repeats: false
      ) { [weak self] _ in
        Task { @MainActor in
          guard let self = self, self.isTranscribing else { return }
          log("Transcription: 4-hour limit reached - restarting session")
          let sessionId = self.currentSessionId
          let wasLocalSTT = self.useLocalSTT
          let mic = self.localMicService
          let sys = self.localSystemService
          if wasLocalSTT {
            self.localMicService = nil
            self.localSystemService = nil
          }
          // Stop, durably queue finalization, and restart.
          self.stopAudioCapture()
          if wasLocalSTT {
            await mic?.finish()
            await sys?.finish()
          }
          if let sessionId {
            try? await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .maxDurationRotation)
          }
          self.clearTranscriptionState(
            finalizationReason: .maxDurationRotation,
            runFinalizer: false,
            allowCloudForceProcess: false,
            finishSession: false
          )
          if let sessionId {
            Task {
              await ConversationFinalizationService.shared.finalizeSession(
                id: sessionId,
                reason: .maxDurationRotation,
                allowCloudForceProcess: false
              )
            }
          }
          self.startTranscription()
        }
      }

      // Track transcription started
      AnalyticsManager.shared.transcriptionStarted()

      log("Transcription: Starting...")

    } catch {
      AnalyticsManager.shared.recordingError(
        error: error.localizedDescription,
        reason: "start_transcription_failed",
        source: recordingConversationSource.rawValue,
        stage: "startup"
      )
      showAlert(title: "Transcription Error", message: error.localizedDescription)
    }
  }

  /// Start audio capture and pipe to transcription service
  /// - Parameter source: Audio source to capture from
  func startAudioCapture(source: AudioSource = .microphone) async {
    if source == .bleDevice {
      // Use BLE device audio
      await startBleAudioCapture()
    } else {
      // Use microphone (+ optional system audio)
      await startMicrophoneAudioCapture()
    }
  }

  /// Arm microphone + system audio capture for the session. Actual capture is managed by
  /// `reconcileCapture()` according to the System Audio mode + meeting state:
  ///  - Always / Never: the microphone runs for the whole session (system audio per mode).
  ///  - Only during meetings: nothing is captured until a call is detected, then mic + system
  ///    start, and both pause when the call ends — so the mic (and its indicator) stays off
  ///    outside meetings.
  /// Captured audio is mixed into one mono stream (cloud) or fed to separate Parakeet instances
  /// (local) so calls/videos/music end up in the transcript alongside the user's voice.
  func startMicrophoneAudioCapture() async {
    guard let audioCaptureService = audioCaptureService else { return }

    // Silent-mic watchdog: on A2DP profile conflict the Bluetooth input device returns zero
    // samples even though CoreAudio reports healthy capture. Fall back to built-in mic for
    // Bluetooth, and rebuild the full CoreAudio capture stack for stale-route wedges.
    audioCaptureService.onSilentMicDetected = { [weak self] detection in
      Task { @MainActor in
        switch detection.suggestedAction {
        case .fallbackToBuiltIn:
          self?.handleSilentMicFallback()
        case .rebuildCoreAudioStack:
          await self?.rebuildCoreAudioCaptureStack(reason: detection.reason)
        }
      }
    }

    // Cloud mode: the mixer sums mic + system into one mono stream for the WebSocket.
    // Local mode: bypass the mixer — mic and system are transcribed by SEPARATE Parakeet
    // instances so transcripts are diarized by source (mic = you, system = another speaker).
    if !useLocalSTT {
      audioMixer?.start { [weak self] monoMixed in
        self?.transcriptionService?.sendAudio(monoMixed)
      }
    }

    // Start (or gate) microphone + system capture according to the System Audio mode + meeting state.
    await reconcileCapture()

    log("Transcription: Audio capture armed (mic + system managed by meeting gate)")
  }

  /// Start microphone capture and wire its chunks/level to the active sink (the mixer in cloud mode,
  /// the mic Parakeet instance in local mode).
  /// - Returns: true if the mic is capturing after the call (already capturing or started OK);
  ///   false on a hard start failure (or if the session was torn down during the async start).
  @discardableResult
  func startMicCaptureIfNeeded() async -> Bool {
    guard let mic = audioCaptureService else { return false }
    guard !mic.capturing else { return true }
    do {
      try await mic.startCapture(
        onAudioChunk: { [weak self] audioData in
          guard let self else { return }
          if self.useLocalSTT {
            self.localMicService?.appendAudio(audioData)
          } else {
            self.audioMixer?.setMicAudio(audioData)
          }
        },
        onAudioLevel: { level in
          // Use dedicated monitor to avoid triggering AppState re-renders
          AudioLevelMonitor.shared.updateMicrophoneLevel(level)
        }
      )
      // The HAL setup above is async and can be slow. If recording stopped — or the service was
      // swapped (silent-mic fallback) — while we were awaiting it, undo the just-started capture.
      guard isTranscribing, audioCaptureService === mic else {
        mic.stopCapture()
        return false
      }
      log("Transcription: Microphone capture started")
      return true
    } catch {
      logError("Transcription: Failed to start microphone capture", error: error)
      return false
    }
  }

  // MARK: - Capture Gating (meeting-aware)

  /// Start the system-audio tap and wire its chunks/levels to the active sink (the mixer in cloud
  /// mode, the system Parakeet instance in local mode). No-op if already capturing. System audio is
  /// optional — a failure is logged and mic-only capture continues.
  @available(macOS 14.4, *)
  func startSystemAudioCaptureIfNeeded() async {
    guard let systemService = systemAudioCaptureService as? SystemAudioCaptureService else { return }
    guard !systemService.capturing else { return }
    do {
      try await systemService.startCapture(
        onAudioChunk: { [weak self] audioData in
          guard let self else { return }
          if self.useLocalSTT {
            self.localSystemService?.appendAudio(audioData)
          } else {
            self.audioMixer?.setSystemAudio(audioData)
          }
        },
        onAudioLevel: { level in
          AudioLevelMonitor.shared.updateSystemLevel(level)
        }
      )
      // The HAL setup above is async and can be slow. If recording stopped — or the service was
      // torn down / recreated — while we were awaiting it, immediately stop the just-started tap
      // so we don't leave an orphaned capture running.
      guard isTranscribing,
        (systemAudioCaptureService as? SystemAudioCaptureService) === systemService
      else {
        systemService.stopCapture()
        log("Transcription: System audio capture aborted (recording stopped during start)")
        return
      }
      log("Transcription: System audio capture started (mode=\(effectiveSystemAudioMode.rawValue))")
    } catch {
      logError(
        "Transcription: System audio capture failed (continuing with mic only)", error: error)
    }
  }

  /// Bring microphone + system-audio capture into line with the current System Audio mode and
  /// meeting state. Idempotent and safe to call repeatedly — invoked on capture start, when the
  /// System Audio mode setting changes, and when the meeting detector flips.
  ///
  /// In "Only during meetings" mode the *entire* recording is gated: with no active call neither the
  /// microphone nor system audio is captured (the mic indicator stays dark). When a call is
  /// detected, both start; when it ends, both pause. In Always/Never the microphone runs for the
  /// whole session and system audio follows the mode. Overlapping async start/stop is serialized
  /// via `captureGateInFlight` / `captureReconcilePending`.
  func reconcileCapture() async {
    guard isTranscribing else {
      meetingDetector?.stop()
      meetingDetector = nil
      isAwaitingMeeting = false
      return
    }

    // Coalesce: if an async start/stop is in flight, request another pass when it finishes.
    if captureGateInFlight {
      captureReconcilePending = true
      return
    }

    let mode = effectiveSystemAudioMode

    // The meeting detector runs only in "Only during meetings" mode.
    if mode == .onlyDuringMeetings {
      if meetingDetector == nil {
        let detector = MeetingDetector(onChange: { [weak self] _ in
          Task { @MainActor in await self?.reconcileCapture() }
        })
        meetingDetector = detector
        detector.start()
      }
    } else {
      meetingDetector?.stop()
      meetingDetector = nil
    }

    let meetingActive = meetingDetector?.isMeetingActive ?? false
    // Only during meetings → capture (mic + system) only while in a call. Always/Never → the mic
    // runs continuously (system audio still respects the mode below).
    let shouldCapture = mode != .onlyDuringMeetings || meetingActive
    isAwaitingMeeting = mode == .onlyDuringMeetings && !meetingActive

    captureGateInFlight = true

    // Microphone
    if let mic = audioCaptureService {
      if shouldCapture, !mic.capturing {
        let started = await startMicCaptureIfNeeded()
        if !started, isTranscribing {
          // Hard mic failure on a required start — stop the session rather than leave it silently
          // "recording" with no audio (the silent-mic watchdog handles zero-sample mics separately).
          log("Transcription: stopping — microphone could not start")
          captureGateInFlight = false
          stopTranscription()
          return
        }
      } else if !shouldCapture, mic.capturing {
        mic.stopCapture()
        AudioLevelMonitor.shared.updateMicrophoneLevel(0)
        log("Transcription: Microphone capture paused (no active call)")
      }
    }

    // System audio (macOS 14.4+). Captured when we should capture AND the mode isn't "never".
    if #available(macOS 14.4, *) {
      let systemShouldCapture = shouldCapture && mode != .never
      if systemShouldCapture, systemAudioCaptureService == nil {
        systemAudioCaptureService = SystemAudioCaptureService()
        log("Transcription: System audio capture service created on demand (mode=\(mode.rawValue))")
      }
      if let systemService = systemAudioCaptureService as? SystemAudioCaptureService {
        if systemShouldCapture, !systemService.capturing {
          await startSystemAudioCaptureIfNeeded()
        } else if !systemShouldCapture, systemService.capturing {
          systemService.stopCapture()
          AudioLevelMonitor.shared.updateSystemLevel(0)
          log("Transcription: System audio capture paused")
        }
      }
    }

    captureGateInFlight = false
    if let recoveryReason = pendingCoreAudioCaptureRecoveryReason {
      pendingCoreAudioCaptureRecoveryReason = nil
      await rebuildCoreAudioCaptureStack(reason: recoveryReason)
      return
    }
    if captureReconcilePending {
      captureReconcilePending = false
      await reconcileCapture()
    }
  }

  /// Fall back from a silent Bluetooth mic to the built-in microphone.
  /// Triggered by `AudioCaptureService.onSilentMicDetected`.
  @MainActor
  func handleSilentMicFallback() {
    guard isTranscribing, !silentMicFallbackInProgress else { return }
    silentMicFallbackInProgress = true

    guard let builtInID = AudioCaptureService.findBuiltInMicDeviceID() else {
      log("Transcription: silent-mic detected but no built-in microphone available — leaving capture as-is")
      silentMicFallbackInProgress = false
      return
    }

    log("Transcription: silent-mic fallback — switching to built-in mic (deviceID=\(builtInID))")

    // Tear down the dead Bluetooth capture and spin a new one pinned to the built-in mic.
    // Silent healing — no user-facing UI, the recording just keeps working.
    audioCaptureService?.stopCapture()
    audioCaptureService = AudioCaptureService(overrideDeviceID: builtInID)
    recordingInputDeviceName =
      AudioCaptureService.getCurrentMicrophoneName() ?? "Built-in Microphone"

    Task { @MainActor in
      await self.startMicrophoneAudioCapture()
      self.silentMicFallbackInProgress = false
    }
  }

  @MainActor
  func rebuildCoreAudioCaptureStack(reason: String) async {
    guard isTranscribing, audioCaptureService != nil else { return }

    if captureGateInFlight {
      pendingCoreAudioCaptureRecoveryReason = reason
      return
    }

    log("Transcription: rebuilding CoreAudio capture stack — \(reason)")
    captureReconcilePending = false
    silentMicFallbackInProgress = false

    if #available(macOS 14.4, *) {
      if let systemService = systemAudioCaptureService as? SystemAudioCaptureService {
        systemService.stopCapture()
      }
      systemAudioCaptureService = nil
      AudioLevelMonitor.shared.updateSystemLevel(0)
    }

    audioCaptureService?.stopCapture()
    audioCaptureService = AudioCaptureService()
    AudioLevelMonitor.shared.updateMicrophoneLevel(0)

    if !useLocalSTT {
      audioMixer?.stop()
      audioMixer = AudioMixer()
    }

    recordingInputDeviceName = AudioCaptureService.getCurrentMicrophoneName() ?? recordingInputDeviceName
    await startMicrophoneAudioCapture()
  }

  /// Start BLE device audio capture
  func startBleAudioCapture() async {
    guard let connection = DeviceProvider.shared.activeConnection,
      let transcriptionService = transcriptionService
    else {
      logError("Transcription: No device connection or transcription service", error: nil)
      stopTranscription()
      return
    }

    // Start BLE audio processing and pipe directly to transcription
    await BleAudioService.shared.startProcessing(
      from: connection,
      transcriptionService: transcriptionService,
      audioDataHandler: { _ in
        // Audio level is updated by BleAudioService
        Task { @MainActor in
          AudioLevelMonitor.shared.updateMicrophoneLevel(BleAudioService.shared.audioLevel)
        }
      }
    )

    // Start listening for button events
    startButtonEventListener()

    log("Transcription: BLE audio capture started (device: \(connection.device.displayName))")
  }

  /// Start listening for button events from BLE device
  func startButtonEventListener() {
    guard let buttonStream = DeviceProvider.shared.getButtonStream() else {
      log("Transcription: Device does not support button events")
      return
    }

    buttonStreamTask?.cancel()
    buttonStreamTask = Task { [weak self] in
      do {
        for try await buttonState in buttonStream {
          self?.handleButtonEvent(buttonState)
        }
      } catch {
        log("Transcription: Button stream ended: \(error.localizedDescription)")
      }
    }
  }

  /// Handle button events from BLE device
  func handleButtonEvent(_ buttonState: [UInt8]) {
    guard !buttonState.isEmpty else { return }

    let state = buttonState[0]
    log("Transcription: Device button event: \(state)")

    switch state {
    case 1:
      // Single tap - could be used for voice command mode (future feature)
      log("Transcription: Single tap - no action configured")

    case 2:
      // Double tap - finish conversation and continue recording
      log("Transcription: Double tap - finishing conversation")
      Task {
        _ = await finishConversation()
      }

    case 3:
      // Long press - stop transcription completely
      log("Transcription: Long press - stopping transcription")
      stopTranscription()

    default:
      log("Transcription: Unknown button state: \(state)")
    }
  }

  /// Stop button event listener
  func stopButtonEventListener() {
    buttonStreamTask?.cancel()
    buttonStreamTask = nil
  }

  /// Stop real-time transcription.
  /// The Python backend handles conversation lifecycle automatically when the WebSocket closes.
  /// When `/v4/listen` has announced the backend conversation id, finalize that exact conversation
  /// instead of relying on the user's current in-progress pointer.
  func stopTranscription() {
    // On-device path: there is no backend WebSocket/conversation, so skip the cloud
    // force-process/reconciliation entirely. Stop capture, then AWAIT both Parakeet instances'
    // final tail flushes (delivered to the still-current session) BEFORE clearing state, so the
    // last words persist to the right conversation instead of racing the async drain.
    if useLocalSTT {
      let mic = localMicService
      let sys = localSystemService
      localMicService = nil
      localSystemService = nil
      Task { @MainActor in
        self.stopAudioCapture()
        await mic?.finish()
        await sys?.finish()
        self.clearTranscriptionState(finalizationReason: .userStop, allowCloudForceProcess: false)
        self.silentMicFallbackInProgress = false
      }
      return
    }

    // Capture session metadata BEFORE clearing state (clearTranscriptionState sets sessionId to nil).
    let capturedSessionId = currentSessionId
    let capturedBackendId = currentBackendConversationId ?? pendingBackendConversationId

    stopAudioCapture()
    clearTranscriptionState(
      finalizationReason: .userStop,
      runFinalizer: false,
      allowCloudForceProcess: false,
      finishSession: false
    )
    silentMicFallbackInProgress = false

    Task {
      if let sessionId = capturedSessionId {
        var persistedBackendId: String?
        if let backendId = capturedBackendId, !backendId.isEmpty {
          do {
            try await TranscriptionStorage.shared.bindBackendConversation(id: sessionId, backendId: backendId)
            persistedBackendId = try await TranscriptionStorage.shared.getSession(id: sessionId)?.backendId
          } catch {
            logError(
              "Transcription: Failed to persist backend conversation \(backendId) for stopped session \(sessionId)",
              error: error
            )
          }
        }
        do {
          try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .userStop)
        } catch {
          logError("Transcription: Failed to finish DB session \(sessionId)", error: error)
          return
        }

        await ConversationFinalizationService.shared.finalizeSession(
          id: sessionId,
          reason: .userStop,
          allowCloudForceProcess: DesktopConversationMatchPolicy.canForceProcessBoundCloudSession(
            capturedBackendId: capturedBackendId,
            persistedBackendId: persistedBackendId
          )
        )
      }

      await loadConversations()
    }
  }

  /// On-device Parakeet failed to load — fall back to cloud STT instead of silently recording a
  /// blank transcript. Cleanly stops the dead on-device session and restarts the SAME recording in
  /// cloud mode (no fragile mid-stream audio rerouting). Sticky for the app run so we don't retry a
  /// broken model on every recording.
  @MainActor
  func handleLocalSTTModelLoadFailure() {
    guard isTranscribing, useLocalSTT, !sttFallbackInProgress else { return }
    sttFallbackInProgress = true
    forceCloudSTTForSession = true
    log("Transcription: Parakeet model load failed — falling back to cloud STT")
    AnalyticsManager.shared.recordingError(
      error: "parakeet_model_load_failed_fallback_cloud",
      reason: "local_stt_model_load_failed",
      source: currentConversationSource.rawValue,
      stage: "fallback"
    )
    let source = audioSource
    stopTranscription()
    // Restart in cloud mode once stop has settled (isTranscribing flips false inside the stop's
    // async teardown). Bounded wait avoids racing the `!isTranscribing` guard in startTranscription.
    Task { @MainActor [weak self] in
      guard let self else { return }
      for _ in 0..<20 {
        if !self.isTranscribing { break }
        try? await Task.sleep(nanoseconds: 100_000_000)
      }
      self.startTranscription(source: source)
      self.sttFallbackInProgress = false
    }
  }

  /// Cloud STT websocket gave up (reconnects exhausted). On Apple Silicon, keep the recording
  /// alive by switching to on-device Parakeet (which works offline) instead of stopping. Skipped
  /// — and falls back to a normal stop — if we're only on cloud because Parakeet already failed,
  /// or we've already tried this once this session.
  @MainActor
  func handleCloudSTTReconnectFailure() {
    guard isTranscribing, audioSource != .bleDevice, !useLocalSTT, Self.isAppleSilicon,
      !forceCloudSTTForSession, !sttCloudFallbackTried, !sttFallbackInProgress
    else {
      stopTranscription()
      return
    }
    sttCloudFallbackTried = true
    sttFallbackInProgress = true
    forceLocalSTTForSession = true
    log("Transcription: cloud STT unreachable (reconnects exhausted) — falling back to on-device Parakeet")
    AnalyticsManager.shared.recordingError(
      error: "cloud_stt_reconnect_failed_fallback_local",
      reason: "cloud_stt_reconnect_failed",
      source: currentConversationSource.rawValue,
      stage: "fallback"
    )
    let source = audioSource
    stopTranscription()
    Task { @MainActor [weak self] in
      guard let self else { return }
      for _ in 0..<20 {
        if !self.isTranscribing { break }
        try? await Task.sleep(nanoseconds: 100_000_000)
      }
      self.startTranscription(source: source)
      self.sttFallbackInProgress = false
    }
  }

  /// Finish the current conversation and keep recording for a new one.
  /// Disconnects the WebSocket (triggers backend conversation processing) then reconnects.
  func finishConversation() async -> FinishConversationResult {
    guard totalSegmentCount > 0 || !speakerSegments.isEmpty else {
      log("Transcription: No segments to finish")
      return .discarded
    }

    log("Transcription: Finishing conversation — disconnecting WebSocket to trigger backend processing")

    // Capture state before rotation — memory_created event for this conversation
    // may arrive on the new WebSocket after currentSessionId and recordingStartTime have changed.
    finishedSessionId = currentSessionId
    finishedRecordingStartTime = recordingStartTime
    let finishedUsesLocalSTT = useLocalSTT
    let sessionToFinalize = currentSessionId

    // Local mode: flush both Parakeet instances' final tails to the CURRENT session BEFORE we
    // rotate currentSessionId, so the last sub-window words attach to THIS conversation rather
    // than racing into the next one. `finish()` delivers its segments on the main actor and
    // returns only once they're persisted. Fresh instances are armed in the reconnect block below.
    if useLocalSTT {
      await localMicService?.finish()
      await localSystemService?.finish()
    } else {
      // Close the cloud stream before marking the old local session finished, so no late
      // WebSocket segments can be persisted after the finalization snapshot starts.
      transcriptionService?.stop()
      transcriptionService = nil
    }

    // Mark current DB session as finished before stopping
    // (backend will process it; memory_created event may arrive on the new session's WebSocket)
    if let sessionId = sessionToFinalize {
      do {
        try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .finishAndContinue)
        log("Transcription: Finished DB session \(sessionId) before reconnect")
      } catch {
        logError("Transcription: Failed to finish DB session \(sessionId)", error: error)
      }
    }

    // Clear currentSessionId BEFORE reconnecting — any segments arriving on the new WebSocket
    // must not be persisted against the finished session. They'll be buffered in memory until
    // the new session ID is set in the Task below.
    currentSessionId = nil

    // Clear segments for the next conversation but keep recording active
    speakerSegments = []
    totalSegmentCount = 0
    totalWordCount = 0
    liveSpeakerPersonMap = [:]
    LiveTranscriptMonitor.shared.clear()
    LiveNotesMonitor.shared.endSession()
    LiveNotesMonitor.shared.clear()

    // Reset the recording start time and backend binding for the next conversation.
    // If the new WebSocket fast-reconnects before the backend finalizes the prior
    // conversation, it can briefly re-emit the old conversation id; do not bind the
    // fresh local SQLite session to that rotated id.
    recordingStartTime = Date()
    if let currentBackendConversationId {
      ignoredRotatedBackendConversationIds.insert(currentBackendConversationId)
    }
    currentBackendConversationId = nil
    pendingBackendConversationId = nil
    RecordingTimer.shared.restart()

    if let sessionId = sessionToFinalize {
      Task {
        await ConversationFinalizationService.shared.finalizeSession(
          id: sessionId,
          reason: .finishAndContinue,
          allowCloudForceProcess: !finishedUsesLocalSTT
        )
      }
    }

    // Restart the 4-hour max recording timer
    maxRecordingTimer?.invalidate()
    maxRecordingTimer = Timer.scheduledTimer(withTimeInterval: maxRecordingDuration, repeats: false)
    { [weak self] _ in
      Task { @MainActor in
        guard let self = self, self.isTranscribing else { return }
        log("Transcription: 4-hour limit reached — stopping and restarting")
        let sessionId = self.currentSessionId
        let wasLocalSTT = self.useLocalSTT
        let mic = self.localMicService
        let sys = self.localSystemService
        if wasLocalSTT {
          self.localMicService = nil
          self.localSystemService = nil
        }
        self.stopAudioCapture()
        if wasLocalSTT {
          await mic?.finish()
          await sys?.finish()
        }
        if let sessionId {
          try? await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .maxDurationRotation)
        }
        self.clearTranscriptionState(
          finalizationReason: .maxDurationRotation,
          runFinalizer: false,
          allowCloudForceProcess: false,
          finishSession: false
        )
        if let sessionId {
          Task {
            await ConversationFinalizationService.shared.finalizeSession(
              id: sessionId,
              reason: .maxDurationRotation,
              allowCloudForceProcess: false
            )
          }
        }
        self.startTranscription()
      }
    }

    // Reconnect transcription service for the next conversation
    let nextClientConversationId = useLocalSTT ? nil : UUID().uuidString.lowercased()
    do {
      let effectiveLanguage = AssistantSettings.shared.effectiveTranscriptionLanguage
      if useLocalSTT {
        // On-device mode: re-arm fresh local Parakeet instances (mic + system) for the next
        // conversation — do NOT reconnect the cloud WebSocket. Stopping the old ones flushes
        // their final tails; the source-routed capture callbacks feed the new instances.
        let onLocalSegments: LocalTranscriptionService.SegmentsHandler = { [weak self] segments in
          self?.handleBackendSegments(segments)
        }
        let mic = LocalTranscriptionService(language: effectiveLanguage, isUser: true)
        mic.start(onSegments: onLocalSegments)
        localMicService = mic
        let system = LocalTranscriptionService(language: effectiveLanguage, isUser: false)
        system.start(onSegments: onLocalSegments)
        localSystemService = system
        log("Transcription: Re-armed on-device Parakeet (mic + system) for next conversation")
      } else {
        transcriptionService = try TranscriptionService(
          language: effectiveLanguage,
          clientConversationId: nextClientConversationId
        )
        transcriptionService?.start(
          onSegments: { [weak self] segments in
            Task { @MainActor in
              self?.handleBackendSegments(segments)
            }
          },
          onEvent: { [weak self] event in
            Task { @MainActor in
              self?.handleListenEvent(event)
            }
          },
          onError: { [weak self] error in
            Task { @MainActor in
              logError("Transcription error (reconnect)", error: error)
              self?.stopTranscription()
            }
          },
          onConnected: {
            log("Transcription: Reconnected to Python backend for next conversation")
          },
          onDisconnected: {
            log("Transcription: Disconnected from Python backend")
          }
        )
      }
    } catch {
      logError("Transcription: Failed to reconnect for next conversation", error: error)
      return .error(error.localizedDescription)
    }

    // Start a new DB session for the next conversation
    let lang = AssistantSettings.shared.effectiveTranscriptionLanguage
    Task {
      do {
        let sessionId = try await TranscriptionStorage.shared.startSession(
          source: currentConversationSource.rawValue,
          language: lang,
          timezone: TimeZone.current.identifier,
          inputDeviceName: recordingInputDeviceName,
          clientConversationId: nextClientConversationId,
          finalizationStrategy: useLocalSTT ? .localSegments : .cloudReconcile
        )
        await MainActor.run {
          self.currentSessionId = sessionId
          LiveNotesMonitor.shared.startSession(sessionId: sessionId)
        }
        if let backendId = await MainActor.run(body: { () -> String? in
          let candidate = self.pendingBackendConversationId ?? self.currentBackendConversationId
          guard let candidate else { return nil }
          return DesktopConversationMatchPolicy.shouldBindConversationSession(
            incomingBackendId: candidate,
            activeBackendId: self.currentBackendConversationId,
            ignoredRotatedBackendIds: self.ignoredRotatedBackendConversationIds
          ) ? candidate : nil
        }) {
          try await TranscriptionStorage.shared.bindBackendConversation(id: sessionId, backendId: backendId)
          await MainActor.run {
            self.currentBackendConversationId = backendId
            self.pendingBackendConversationId = nil
            self.ignoredRotatedBackendConversationIds = []
          }
        }
        log("Transcription: Created new DB session \(sessionId) for next conversation")
      } catch {
        logError("Transcription: Failed to create DB session for next conversation", error: error)
      }
    }

    // Refresh the conversations list to show the new conversation
    await loadConversations()

    log("Transcription: Ready for next conversation")
    return .saved
  }

  /// Stop audio capture services (but keep transcript data for saving)
  func stopAudioCapture() {
    // Cancel timers
    maxRecordingTimer?.invalidate()
    maxRecordingTimer = nil
    RecordingTimer.shared.stop()

    // Reset audio levels
    AudioLevelMonitor.shared.reset()

    // Stop BLE audio if active
    if audioSource == .bleDevice {
      BleAudioService.shared.stopProcessing()
      stopButtonEventListener()
    }

    // Stop the meeting detector (only active in "Only during meetings" mode)
    meetingDetector?.stop()
    meetingDetector = nil
    captureGateInFlight = false
    captureReconcilePending = false
    pendingCoreAudioCaptureRecoveryReason = nil
    isAwaitingMeeting = false

    // Stop system audio capture first (if available)
    if #available(macOS 14.4, *) {
      if let systemService = systemAudioCaptureService as? SystemAudioCaptureService {
        systemService.stopCapture()
      }
    }
    systemAudioCaptureService = nil

    // Stop microphone capture
    audioCaptureService?.stopCapture()
    audioCaptureService = nil

    // Stop audio mixer
    audioMixer?.stop()
    audioMixer = nil

    // Clear VAD gate
    vadGateService = nil

    // Stop transcription service
    transcriptionService?.stop()
    transcriptionService = nil

    // Stop on-device Parakeet services (if active) — both flush their final tails.
    localMicService?.stop()
    localMicService = nil
    localSystemService?.stop()
    localSystemService = nil
    useLocalSTT = false

    isTranscribing = false
  }

  /// Clear transcription state after saving
  func clearTranscriptionState(
    finalizationReason: TranscriptionFinalizationReason = .userStop,
    runFinalizer: Bool = true,
    allowCloudForceProcess: Bool = false,
    finishSession: Bool = true
  ) {
    log(
      "Transcription: Final segments count: \(totalSegmentCount) (in-memory: \(speakerSegments.count)), words: \(totalWordCount)"
    )

    // End live notes session
    LiveNotesMonitor.shared.endSession()

    // Mark DB session as finished (pending upload / crash recovery)
    if finishSession, let sessionId = currentSessionId {
      Task {
        do {
          try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: finalizationReason)
          log("Transcription: Finished DB session \(sessionId)")
          if runFinalizer {
            await ConversationFinalizationService.shared.finalizeSession(
              id: sessionId,
              reason: finalizationReason,
              allowCloudForceProcess: allowCloudForceProcess
            )
          }
        } catch {
          logError("Transcription: Failed to finish DB session \(sessionId)", error: error)
        }
      }
    }

    // Clear segments after finalization
    speakerSegments = []
    liveSpeakerPersonMap = [:]
    LiveTranscriptMonitor.shared.clear()
    LiveNotesMonitor.shared.clear()
    recordingStartTime = nil
    currentSessionId = nil

    // Track transcription stopped
    AnalyticsManager.shared.transcriptionStopped(wordCount: totalWordCount)
    totalSegmentCount = 0
    totalWordCount = 0
    currentTranscript = ""

    log("Transcription: Stopped")
  }

  /// Aggressively trim transcript state to free memory (called by ResourceMonitor during critical memory pressure).
  /// Segments are already persisted in SQLite, so trimming in-memory state is safe.
  func trimTranscriptStateForMemoryPressure() {
    let beforeCount = speakerSegments.count
    if speakerSegments.count > 50 {
      speakerSegments = Array(speakerSegments.suffix(50))
    }
    currentTranscript = ""
    LiveTranscriptMonitor.shared.updateSegments(speakerSegments)
    log(
      "ResourceMonitor: Trimmed transcript state \(beforeCount) -> \(speakerSegments.count) segments"
    )
  }

  // MARK: - Automation capture test seam (non-prod hermetic E2E)

  /// Start a headless capture session without mic/audio — T2 hermetic only.
  func automationStartCaptureTestSession() -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "capture test session disabled on production bundles"]
    }
    guard !isTranscribing else {
      return [
        "already_recording": "true",
        "session_id": currentSessionId ?? "",
        "segment_count": "\(totalSegmentCount)",
      ]
    }
    let sessionId = UUID().uuidString.lowercased()
    currentSessionId = sessionId
    recordingStartTime = Date()
    isTranscribing = true
    useLocalSTT = false
    speakerSegments = []
    totalSegmentCount = 0
    totalWordCount = 0
    currentTranscript = ""
    return [
      "started": "true",
      "session_id": sessionId,
      "is_transcribing": "true",
    ]
  }

  func automationInjectCaptureTestTranscript(text: String) -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "capture test transcript disabled on production bundles"]
    }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return ["error": "missing transcript text"] }
    guard isTranscribing else { return ["error": "no active capture session"] }
    let start = recordingStartTime.map { Date().timeIntervalSince($0) } ?? 0
    let segment = TranscriptionService.BackendSegment(
      id: UUID().uuidString.lowercased(),
      text: trimmed,
      speaker: "SPEAKER_00",
      speaker_id: 0,
      is_user: true,
      person_id: nil,
      start: max(0, start),
      end: max(0.1, start + 0.5),
      translations: nil
    )
    handleBackendSegments([segment])
    return [
      "injected": trimmed,
      "session_id": currentSessionId ?? "",
      "segment_count": "\(totalSegmentCount)",
      "conversation_count": "\(totalConversationsCount ?? conversations.count)",
    ]
  }

  func automationStopCaptureTestSession() async -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "capture test session disabled on production bundles"]
    }
    guard isTranscribing else {
      return [
        "already_stopped": "true",
        "conversation_count": "\(totalConversationsCount ?? conversations.count)",
      ]
    }
    let beforeCount = totalConversationsCount ?? conversations.count
    stopTranscription()
    for _ in 0..<40 {
      if !isTranscribing { break }
      try? await Task.sleep(nanoseconds: 100_000_000)
    }
    await loadConversations()
    let afterCount = totalConversationsCount ?? conversations.count
    return [
      "stopped": "true",
      "conversation_count_before": "\(beforeCount)",
      "conversation_count_after": "\(afterCount)",
      "segment_count": "\(totalSegmentCount)",
    ]
  }

  // MARK: - Conversations
}
