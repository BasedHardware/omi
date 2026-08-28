@preconcurrency import AVFoundation
import Combine
import SwiftUI
@preconcurrency import UserNotifications

@MainActor
extension AppState {
  func toggleTranscription() {
    if isTranscribing {
      AssistantSettings.shared.audioRecordingMode = .off
    } else {
      let selected = AssistantSettings.shared.audioRecordingMode
      AssistantSettings.shared.audioRecordingMode = selected == .off ? .onlyMeetings : selected
    }
  }

  /// Start real-time transcription
  /// - Parameter source: Audio source to use (defaults to current audioSource setting)
  func startTranscription(
    source: AudioSource? = nil,
    conversationRole: MeetingConversationBoundaryPolicy.Role = .ambient
  ) {
    guard !isTranscribing else { return }
    guard AssistantSettings.shared.audioRecordingMode != .off else {
      log("Transcription: start ignored because Audio Recording is Off")
      return
    }
    sttSession.prepareForStart()
    silentMicRecoveryAttempts = 0
    currentConversationRole = conversationRole
    meetingBoundaryInProgress = false
    pendingMeetingState = nil
    // A new session re-evaluates the route from scratch: the user may have unplugged the
    // dead device, and pinning last session's heal would ignore a working default.
    silentMicHealedDeviceID = nil
    meetingEndFinalizationInProgress = false

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
      let debugForceCloud = STTSessionState.debugForceCloudSTT(
        environmentForceCloud: ProcessInfo.processInfo.environment["OMI_FORCE_CLOUD_STT"] == "1",
        userDefaultsForceCloud: UserDefaults.standard.bool(forKey: "forceCloudSTT")
      )
      sttSession.beginRecording(
        audioSource: effectiveSource,
        isAppleSilicon: Self.isAppleSilicon,
        debugForceCloud: debugForceCloud
      )
      let clientConversationId = UUID().uuidString.lowercased()
      currentClientConversationId = sttSession.useLocalSTT ? nil : clientConversationId

      if sttSession.useLocalSTT {
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
          clientConversationId: clientConversationId,
          conversationRole: currentConversationRole
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
        // Initialize audio capture service. The user's persisted microphone
        // choice is resolved and applied in startMicCaptureIfNeeded(), off the
        // main actor, right before the device actually opens.
        audioCaptureService = AudioCaptureService()

        // Initialize audio mixer for combining mic and system audio
        audioMixer = AudioMixer()

        // VAD gate not used for Python backend streaming (backend handles its own VAD)
        vadGateService = nil

        // Initialize system audio capture if supported (macOS 14.4+). The user's one Audio
        // Recording mode controls intent + meeting gating; a hidden developer override may suppress
        // only the system tap without creating another user-facing policy.
        // Toggle the debug flag with: defaults write <bundle> disableSystemAudioCapture -bool true
        let recordingMode = audioRecordingMode
        if !shouldCaptureSystemAudio {
          log("Transcription: System audio capture disabled by developer override")
        } else if #available(macOS 14.4, *) {
          systemAudioCaptureService = SystemAudioCaptureService()
          log(
            "Transcription: System audio capture initialized (mode=\(recordingMode.rawValue), macOS 14.4+)"
          )
        } else {
          log("Transcription: System audio capture not available (requires macOS 14.4+)")
        }
      }
      // For BLE device, BleAudioService will be used in startAudioCapture

      // Streaming mode: start transcription service first, then audio on connect.
      // Local (Parakeet) mode has no WebSocket — start capture immediately instead.
      if sttSession.useLocalSTT {
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
      let sessionGeneration = recordingGeneration
      // Snapshot provenance before any awaited microphone/device resolution;
      // a detector edge may rotate the live role while this task is suspended,
      // but it must not rewrite the identity of the session being created.
      let sessionConversationRole = currentConversationRole
      Task {
        do {
          // Persist the microphone this session will actually use: an explicit
          // selection resolves asynchronously (off-main HAL read), so wait for
          // it here rather than recording the system-default name and leaving
          // the conversation with wrong input-device provenance. Microphone
          // sessions only — a BLE session's provenance is the BLE device.
          if effectiveSource == .microphone,
            let preferredName = await AudioCaptureService.resolvePreferredMicrophone()?.name
          {
            // The recording may have stopped (or stopped and restarted) while
            // the HAL lookup was in flight — a stale task must not create a
            // session for a dead recording nor touch a newer one's state.
            guard recordingGeneration == sessionGeneration else { return }
            recordingInputDeviceName = preferredName
          }
          guard recordingGeneration == sessionGeneration else { return }
          let sessionId = try await TranscriptionStorage.shared.startSession(
            source: currentConversationSource.rawValue,
            language: effectiveLanguage,
            timezone: TimeZone.current.identifier,
            inputDeviceName: recordingInputDeviceName,
            clientConversationId: sttSession.useLocalSTT ? nil : clientConversationId,
            conversationRole: sessionConversationRole,
            finalizationStrategy: sttSession.useLocalSTT ? .localSegments : .cloudReconcile
          )
          // Stale after creation: leave the orphaned row to the crash-safe
          // reconciler rather than pointing a newer recording at it — and stop
          // the whole task so the backend binding below cannot run either.
          let sessionStillCurrent = await MainActor.run { () -> Bool in
            guard self.recordingGeneration == sessionGeneration else { return false }
            self.currentSessionId = sessionId
            // Start live notes session
            LiveNotesMonitor.shared.startSession(sessionId: sessionId)
            return true
          }
          guard sessionStillCurrent else { return }
          let pendingMeetingState = await MainActor.run { () -> Bool? in
            let pending = self.pendingMeetingState
            self.pendingMeetingState = nil
            return pending
          }
          if let pendingMeetingState {
            await self.handleMeetingObservation(active: pendingMeetingState)
            guard self.recordingGeneration == sessionGeneration else { return }
          }
          if let backendId = await MainActor.run(body: { () -> String? in
            let candidate = self.pendingBackendConversationId ?? self.currentBackendConversationId
            guard let candidate else { return nil }
            return DesktopConversationMatchPolicy.shouldBindConversationSession(
              incomingBackendId: candidate,
              expectedBackendId: self.currentClientConversationId,
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
          let conversationRole = self.currentConversationRole
          let wasLocalSTT = self.sttSession.useLocalSTT
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
            await self.flushTranscriptPersistence()
          }
          self.captureFinishedRecordingForLifecycleIfCloud(wasLocalSTT: wasLocalSTT)
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
          self.startTranscription(conversationRole: conversationRole)
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
      showAlert(
        title: "Couldn't Start Transcription",
        message: UserFacingErrorPresentation.message(for: error, while: .transcription)
      )
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
  /// Silent-mic watchdog: CoreAudio can report a healthy IOProc while a Bluetooth, USB, or
  /// built-in input returns only zeros. Listen/manual/Quick Note all flow through here, so
  /// they must opt into all-transport detection just as PTT does. Shared by the session-arm
  /// path and the preferred-microphone swap in startMicCaptureIfNeeded().
  private func configureSharedCaptureWatchdog(_ service: AudioCaptureService) {
    SharedCaptureSilentMicRecoveryPolicy.configure(service)
    service.onSilentMicDetected = { [weak self] detection in
      Task { @MainActor in
        switch detection.suggestedAction {
        case .fallbackToBuiltIn:
          self?.handleSilentMicFallback()
        case .rebuildCoreAudioStack:
          await self?.handleSharedCaptureSilentMicDetection(reason: detection.reason)
        }
      }
    }
  }

  func startMicrophoneAudioCapture() async {
    guard let audioCaptureService = audioCaptureService else { return }

    // Authorization first, capture second. CoreAudio HAL capture never triggers the
    // system microphone prompt on its own: with a notDetermined or revoked TCC entry it
    // "succeeds" and delivers zero samples forever. The silent-mic watchdog then reads
    // those zeros as a dead device and loops the user through rebuilds into a
    // "Microphone Isn't Capturing Audio" alert every ~90s — a permission problem wearing
    // a hardware costume. startTranscription() has its own guard, but resume, the meeting
    // gate, and the watchdog's own rebuild all arm capture through here without passing it.
    var gateAction = MicrophoneCaptureAuthorizationPolicy.action(
      for: AudioCaptureService.authorizationStatus())
    if gateAction == .requestPermission {
      log("Transcription: microphone permission undetermined — requesting before capture")
      gateAction = MicrophoneCaptureAuthorizationPolicy.action(
        afterRequestGranted: await AudioCaptureService.requestPermission())
    }
    guard gateAction == .proceed else {
      surfaceMicrophonePermissionAlert()
      stopTranscription()
      return
    }

    configureSharedCaptureWatchdog(audioCaptureService)

    // Cloud mode: the mixer sums mic + system into one mono stream for the WebSocket.
    // Local mode: bypass the mixer — mic and system are transcribed by SEPARATE Parakeet
    // instances so transcripts are diarized by source (mic = you, system = another speaker).
    if !sttSession.useLocalSTT {
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
    guard var mic = audioCaptureService else { return false }
    guard !mic.capturing else { return true }

    // Honor the user's persisted microphone choice (e.g. Ray-Ban Meta glasses)
    // at the moment the device opens — this also covers the meetings-only gate
    // and recovery rebuilds. Re-resolved every open because device IDs are not
    // stable across reconnects, through the shared single-flight resolver so a
    // wedged HAL strands at most one worker across all callers and retries.
    let preferredUID =
      UserDefaults.standard.string(forKey: AudioCaptureService.preferredInputUIDDefaultsKey) ?? ""
    if !preferredUID.isEmpty, !mic.hasOverrideDevice {
      let resolved = await AudioCaptureService.resolvePreferredMicrophone()
      // The session may have been torn down or the service swapped while the
      // resolution was in flight.
      guard let current = audioCaptureService, current === mic else { return false }
      if let resolved {
        let replacement = AudioCaptureService(overrideDeviceID: resolved.id)
        configureSharedCaptureWatchdog(replacement)
        audioCaptureService = replacement
        mic = replacement
        recordingInputDeviceName = resolved.name ?? recordingInputDeviceName
        log("Transcription: using preferred microphone \(recordingInputDeviceName ?? "?")")
      } else {
        // The user's explicit choice is unavailable — capture continues on the
        // system default. A silent substitution must be visible to release
        // health, so record the degradation on the shared fallback surface.
        log("Transcription: preferred microphone unavailable — using the system default input")
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "transcription_input",
          from: "preferred_microphone",
          to: "system_default_input",
          reason: "device_unavailable",
          outcome: .degraded)
      }
    }

    // A parked PTT warm capture may still hold the very device this session is
    // about to open — release it and wait for its HAL teardown so the two
    // owners' IOProcs can never overlap on one device (Bluetooth A2DP↔HFP
    // profile flap, stream-format reconfiguration races). Deliberately the
    // LAST await before the device opens: a PTT turn finishing during the
    // preferred-mic resolution above can park a fresh capture, which an
    // earlier handshake would miss.
    if let parked = PushToTalkManager.shared.releaseParkedMicCapture() {
      await parked.waitForPhysicalStop()
      guard let current = audioCaptureService, current === mic else { return false }
    }

    do {
      let useLocalSTT = sttSession.useLocalSTT
      let localService = localMicService
      let mixer = audioMixer
      try await mic.startCapture(
        onAudioChunk: { audioData in
          if useLocalSTT {
            localService?.appendAudio(audioData)
          } else {
            mixer?.setMicAudio(audioData)
          }
        },
        onAudioLevel: { level in
          // Use dedicated monitor to avoid triggering AppState re-renders
          Task { @MainActor in
            AudioLevelMonitor.shared.updateMicrophoneLevel(level)
          }
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
      let useLocalSTT = sttSession.useLocalSTT
      let localSystem = localSystemService
      let mixer = audioMixer
      try await systemService.startCapture(
        onAudioChunk: { audioData in
          if useLocalSTT {
            localSystem?.appendAudio(audioData)
          } else {
            mixer?.setSystemAudio(audioData)
          }
        },
        onAudioLevel: { level in
          Task { @MainActor in
            AudioLevelMonitor.shared.updateSystemLevel(level)
          }
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
      recordSystemAudioCaptureOutcome(.granted)
      log("Transcription: System audio capture started (mode=\(audioRecordingMode.rawValue))")
    } catch {
      // Mirror the success path's staleness guards: if recording stopped or the
      // service was replaced while startCapture was suspended, the failure says
      // nothing about permission for the CURRENT session — don't record it.
      guard isTranscribing,
        (systemAudioCaptureService as? SystemAudioCaptureService) === systemService
      else {
        log("Transcription: System audio capture failed after session ended — outcome not recorded")
        return
      }
      recordSystemAudioCaptureOutcome(SystemAudioPermissionStatus.classify(captureError: error))
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
      meetingDetectorMode = nil
      isAwaitingMeeting = false
      return
    }

    // Coalesce: if an async start/stop is in flight, request another pass when it finishes.
    if captureGateInFlight {
      captureReconcilePending = true
      return
    }

    let mode = audioRecordingMode
    guard mode != .off else {
      stopTranscription()
      return
    }

    // The detector supplies meeting boundaries in every active microphone mode. Only Meetings
    // uses the signal to gate capture; Always uses it to label/rotate conversations.
    ensureMeetingDetector(for: mode)

    let meetingStateReady = mode != .onlyMeetings || meetingDetector?.hasObservedState == true
    let meetingActive = meetingDetector?.isMeetingActive ?? false
    // Only Meetings captures mic + system only while a call is active. Always captures both
    // continuously, subject to OS capability and the hidden developer system-tap override.
    let shouldCapture = mode == .always || meetingActive
    isAwaitingMeeting = mode == .onlyMeetings && !meetingActive

    guard meetingStateReady else {
      // Fail closed while the gate has not answered — see `pauseCaptureWhileMeetingGateUnknown`.
      pauseCaptureIfMeetingGateUnknown(mode: mode, meetingStateReady: meetingStateReady)
      log("Transcription: waiting for meeting detector before changing capture state")
      return
    }

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

    // System audio (macOS 14.4+). Captured whenever the chosen policy is actively recording.
    if #available(macOS 14.4, *) {
      let systemShouldCapture = shouldCapture && shouldCaptureSystemAudio
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

    if !meetingEndFinalizationInProgress,
      MeetingConversationBoundaryPolicy.shouldFinishConversation(
        mode: mode,
        meetingStateReady: meetingStateReady,
        shouldCapture: shouldCapture,
        segmentCount: totalSegmentCount,
        hasSpeakerSegments: !speakerSegments.isEmpty
      )
    {
      meetingEndFinalizationInProgress = true
      log("Transcription: Meeting ended — finishing conversation and waiting for the next meeting")
      Task { @MainActor in
        defer { self.meetingEndFinalizationInProgress = false }
        guard
          MeetingConversationBoundaryPolicy.shouldFinishConversation(
            mode: self.audioRecordingMode,
            meetingStateReady: self.meetingDetector?.hasObservedState == true,
            shouldCapture: self.meetingDetector?.isMeetingActive == true,
            segmentCount: self.totalSegmentCount,
            hasSpeakerSegments: !self.speakerSegments.isEmpty
          )
        else {
          log("Transcription: skipped meeting-ended finalization because meeting state changed")
          return
        }
        _ = await self.finishConversation(finalizationReason: .meetingEnded)
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
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "silent_mic",
      from: "bluetooth",
      to: "built_in",
      reason: "local_heal",
      outcome: .recovered,
      extra: ["user_visible": false])

    // Tear down the dead Bluetooth capture and spin a new one pinned to the built-in mic.
    // Silent healing — no user-facing UI, the recording just keeps working.
    audioCaptureService?.stopCapture()
    audioCaptureService = AudioCaptureService(overrideDeviceID: builtInID)
    // Hold the healed route for the rest of the session so the next rebuild does not
    // re-resolve back to the silent default and undo this.
    silentMicHealedDeviceID = builtInID
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
    // Rebuilding must not silently move the user back onto a route already proven dead.
    // The choice is `SilentMicRoutePolicy`'s so the contract has one tested home; a nil
    // result means "follow the system default", which is what the plain initialiser does.
    if let deviceID = SilentMicRoutePolicy.captureDeviceID(
      healed: silentMicHealedDeviceID, systemDefault: nil)
    {
      audioCaptureService = AudioCaptureService(overrideDeviceID: deviceID)
    } else {
      audioCaptureService = AudioCaptureService()
    }
    AudioLevelMonitor.shared.updateMicrophoneLevel(0)

    if !sttSession.useLocalSTT {
      audioMixer?.stop()
      audioMixer = AudioMixer()
    }

    recordingInputDeviceName = AudioCaptureService.getCurrentMicrophoneName() ?? recordingInputDeviceName
    await startMicrophoneAudioCapture()
  }

  /// A fresh `AudioCaptureService` resets its own watchdog cap. Keep the terminal policy at
  /// the session owner so an unrecoverable USB/built-in route cannot loop forever while the
  /// UI continues to claim it is recording.
  @MainActor
  func handleSharedCaptureSilentMicDetection(reason: String) async {
    guard isTranscribing else { return }
    silentMicRecoveryAttempts += 1

    switch SharedCaptureSilentMicRecoveryPolicy.action(for: silentMicRecoveryAttempts) {
    case .rebuild:
      log("Transcription: silent microphone detected — rebuilding CoreAudio capture stack")
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "silent_mic",
        from: "stalled_route",
        to: "rebuilt_capture",
        reason: "local_heal",
        outcome: .degraded,
        extra: ["recovery_attempts": silentMicRecoveryAttempts, "user_visible": false])
      await rebuildCoreAudioCaptureStack(reason: reason)
    case .stopAndSurfaceError:
      log("Transcription: stopping after repeated silent microphone recovery failures")
      DesktopDiagnosticsManager.shared.recordTranscriptionSilentCaptureExhausted(
        recoveryAttempts: silentMicRecoveryAttempts)
      stopTranscription()
      // An unauthorized app receives exactly this symptom — endless zero samples — so
      // the policy checks permission before blaming the hardware.
      switch MicrophoneCaptureAuthorizationPolicy.terminalAlert(
        for: AudioCaptureService.authorizationStatus())
      {
      case .permission:
        surfaceMicrophonePermissionAlert()
      case .hardware:
        // Deliberately no modal. The "Microphone Isn't Capturing Audio" alert looped at
        // the user every ~90s whenever a route stayed silent and became the single most
        // hated dialog in the app (removed Aug 2026 at Nik's request). Recording already
        // stopped above — the UI state change is the signal; telemetry keeps the counter.
        log("Transcription: silent capture exhausted on an authorized mic — stopping without modal")
      }
    }
  }

  /// Tell the user the actual problem when capture is blocked by permission, and take
  /// them to the exact pane that fixes it.
  @MainActor
  func surfaceMicrophonePermissionAlert() {
    log("Transcription: microphone permission not granted — surfacing permission alert")
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "mic_permission",
      from: "capture_start",
      to: "permission_alert",
      reason: "not_authorized",
      outcome: .degraded,
      extra: ["status": String(describing: AudioCaptureService.authorizationStatus())])
    showAlert(
      title: "Omi Needs Microphone Access",
      message:
        "macOS is not letting Omi hear the microphone. Enable Omi under "
        + "System Settings → Privacy & Security → Microphone, then start recording again."
    ) {
      // Pause before the hand-off. NSWorkspace.open can return while Omi is
      // still the active app, and a queued alert must not attach a sheet that
      // System Settings then covers. didBecomeActive resumes the queue.
      self.alertPresenter.pauseQueueUntilAppActive()
      if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone") {
        NSWorkspace.shared.open(url)
      }
    }
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
  @discardableResult
  func stopTranscription() -> Task<Void, Never>? {
    preferredMicrophoneReconnectMonitor.stop()
    recordingGeneration &+= 1
    // On-device path: await both Parakeet tail flushes before clearing state so the last words persist to the current conversation.
    if sttSession.useLocalSTT {
      let mic = localMicService
      let sys = localSystemService
      localMicService = nil
      localSystemService = nil
      return Task { @MainActor in
        self.stopAudioCapture()
        await mic?.finish()
        await sys?.finish()
        await self.flushTranscriptPersistence()
        self.clearTranscriptionState(finalizationReason: .userStop, allowCloudForceProcess: false)
        self.silentMicFallbackInProgress = false
      }
    }
    // Capture session metadata BEFORE clearing state (clearTranscriptionState sets sessionId to nil).
    let capturedSessionId = currentSessionId
    let capturedBackendId = currentBackendConversationId ?? pendingBackendConversationId
    captureCurrentFinishedRecordingForLifecycle()
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
    return nil
  }

  /// On-device Parakeet failed to load — fall back to cloud STT instead of silently recording a
  /// blank transcript. Cleanly stops the dead on-device session and restarts the SAME recording in
  /// cloud mode (no fragile mid-stream audio rerouting). Sticky for the app run so we don't retry a
  /// broken model on every recording.
  @MainActor
  func handleLocalSTTModelLoadFailure() {
    guard sttSession.canBeginLocalToCloudFallback(isTranscribing: isTranscribing) else { return }
    sttSession.beginLocalToCloudFallback()
    log("Transcription: Parakeet model load failed — falling back to cloud STT")
    AnalyticsManager.shared.recordingError(
      error: "parakeet_model_load_failed_fallback_cloud",
      reason: "local_stt_model_load_failed",
      source: currentConversationSource.rawValue,
      stage: "fallback"
    )
    let source = audioSource
    let conversationRole = currentConversationRole
    stopTranscription()
    // Restart in cloud mode once stop has settled (isTranscribing flips false inside the stop's
    // async teardown). Bounded wait avoids racing the `!isTranscribing` guard in startTranscription.
    Task { @MainActor [weak self] in
      guard let self else { return }
      for _ in 0..<20 {
        if !self.isTranscribing { break }
        try? await Task.sleep(nanoseconds: 100_000_000)
      }
      self.startTranscription(source: source, conversationRole: conversationRole)
      self.sttSession.completeFallback()
    }
  }

  /// Cloud STT websocket gave up (reconnects exhausted). On Apple Silicon, keep the recording
  /// alive by switching to on-device Parakeet (which works offline) instead of stopping. Skipped
  /// — and falls back to a normal stop — if we're only on cloud because Parakeet already failed,
  /// or we've already tried this once this session.
  @MainActor
  func handleCloudSTTReconnectFailure() {
    guard
      sttSession.canBeginCloudToLocalFallback(
        isTranscribing: isTranscribing,
        audioSource: audioSource,
        isAppleSilicon: Self.isAppleSilicon
      )
    else {
      // Could not fail open (no local STT): record the exhausted cloud→stopped rotation.
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "cloud_stt",
        from: "cloud",
        to: "stopped",
        reason: "cloud_stt_reconnect_failed",
        outcome: .exhausted,
        extra: ["source": currentConversationSource.rawValue])
      stopTranscription()
      return
    }
    sttSession.beginCloudToLocalFallback()
    log("Transcription: cloud STT unreachable (reconnects exhausted) — falling back to on-device Parakeet")
    // Fail-open cloud → on-device Parakeet switch: shared fallback telemetry (AGENTS.md).
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "cloud_stt",
      from: "cloud",
      to: "local",
      reason: "cloud_stt_reconnect_failed",
      outcome: .recovered,
      extra: ["source": currentConversationSource.rawValue])
    AnalyticsManager.shared.recordingError(
      error: "cloud_stt_reconnect_failed_fallback_local",
      reason: "cloud_stt_reconnect_failed",
      source: currentConversationSource.rawValue,
      stage: "fallback"
    )
    let source = audioSource
    let conversationRole = currentConversationRole
    stopTranscription()
    Task { @MainActor [weak self] in
      guard let self else { return }
      for _ in 0..<20 {
        if !self.isTranscribing { break }
        try? await Task.sleep(nanoseconds: 100_000_000)
      }
      self.startTranscription(source: source, conversationRole: conversationRole)
      self.sttSession.completeFallback()
    }
  }

  /// Finish the current conversation and keep recording for a new one.
  /// Disconnects the WebSocket (triggers backend conversation processing) then reconnects.
  func finishConversation(
    finalizationReason: TranscriptionFinalizationReason = .finishAndContinue,
    allowEmptyRotation: Bool = false,
    nextConversationRole: MeetingConversationBoundaryPolicy.Role? = nil
  ) async -> FinishConversationResult {
    guard isTranscribing else { return .error("transcription is no longer active") }
    guard allowEmptyRotation || totalSegmentCount > 0 || !speakerSegments.isEmpty else {
      log("Transcription: No segments to finish")
      return .discarded
    }
    log("Transcription: Finishing conversation — reason=\(finalizationReason.rawValue)")
    recordingGeneration &+= 1
    let rotationGeneration = recordingGeneration

    // Capture state before rotation; memory_created may arrive on the new WebSocket.
    let finishedUsesLocalSTT = sttSession.useLocalSTT
    let sessionToFinalize = currentSessionId
    captureFinishedRecordingForLifecycleIfCloud(wasLocalSTT: finishedUsesLocalSTT)
    // Local mode: flush both Parakeet instances' final tails to the CURRENT session BEFORE we
    // rotate currentSessionId, so the last sub-window words attach to THIS conversation rather
    // than racing into the next one. `finish()` delivers its segments on the main actor and
    // returns only once they're persisted. Fresh instances are armed in the reconnect block below.
    if sttSession.useLocalSTT {
      await localMicService?.finish()
      await localSystemService?.finish()
      await flushTranscriptPersistence()
    } else {
      // Close the cloud stream before marking the old local session finished, so no late
      // WebSocket segments can be persisted after the finalization snapshot starts.
      transcriptionService?.markFinalizationReason(finalizationReason.rawValue)
      transcriptionService?.stop()
      transcriptionService = nil
    }
    guard isTranscribing, recordingGeneration == rotationGeneration else {
      return .error("transcription session changed during rotation")
    }

    // Mark current DB session as finished before stopping
    // (backend will process it; memory_created event may arrive on the new session's WebSocket)
    if let sessionId = sessionToFinalize {
      do {
        try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: finalizationReason)
        log("Transcription: Finished DB session \(sessionId) before reconnect")
      } catch {
        logError("Transcription: Failed to finish DB session \(sessionId)", error: error)
      }
    }
    guard isTranscribing, recordingGeneration == rotationGeneration else {
      return .error("transcription session changed during rotation")
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
      if ignoredRotatedBackendConversationIds.count >= Self.maxIgnoredRotatedBackendConversationIds,
        let evicted = ignoredRotatedBackendConversationIds.first
      {
        ignoredRotatedBackendConversationIds.remove(evicted)
      }
      ignoredRotatedBackendConversationIds.insert(currentBackendConversationId)
    }
    currentBackendConversationId = nil
    currentClientConversationId = nil
    pendingBackendConversationId = nil
    RecordingTimer.shared.restart()

    if let sessionId = sessionToFinalize {
      Task {
        await ConversationFinalizationService.shared.finalizeSession(
          id: sessionId,
          reason: finalizationReason,
          allowCloudForceProcess: !finishedUsesLocalSTT
        )
      }
    }

    // Restart the 4-hour max recording timer
    maxRecordingTimer?.invalidate()
    maxRecordingTimer = Timer.scheduledTimer(withTimeInterval: maxRecordingDuration, repeats: false) { [weak self] _ in
      Task { @MainActor in
        guard let self = self, self.isTranscribing else { return }
        log("Transcription: 4-hour limit reached — stopping and restarting")
        let sessionId = self.currentSessionId
        let conversationRole = self.currentConversationRole
        let wasLocalSTT = self.sttSession.useLocalSTT
        let mic = self.localMicService
        let sys = self.localSystemService
        if wasLocalSTT {
          self.localMicService = nil
          self.localSystemService = nil
        }
        self.transcriptionService?.markFinalizationReason(
          TranscriptionFinalizationReason.maxDurationRotation.rawValue)
        self.stopAudioCapture()
        if wasLocalSTT {
          await mic?.finish()
          await sys?.finish()
          await self.flushTranscriptPersistence()
        }
        self.captureFinishedRecordingForLifecycleIfCloud(wasLocalSTT: wasLocalSTT)
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
        self.startTranscription(conversationRole: conversationRole)
      }
    }

    // Reconnect transcription service for the next conversation. A stop can
    // arrive while an awaited local tail flush/rebuild is suspended; it bumps
    // recordingGeneration and tears down the capture stack. Re-check before
    // reconnecting so a stale boundary cannot resurrect a stopped session.
    guard isTranscribing, recordingGeneration == rotationGeneration else {
      return .error("transcription session changed before reconnect")
    }
    let nextClientConversationId = sttSession.useLocalSTT ? nil : UUID().uuidString.lowercased()
    currentClientConversationId = nextClientConversationId
    do {
      let effectiveLanguage = AssistantSettings.shared.effectiveTranscriptionLanguage
      if sttSession.useLocalSTT {
        // On-device mode: re-arm fresh local Parakeet instances (mic + system) for the next
        // conversation — do NOT reconnect the cloud WebSocket. Stopping the old ones flushes
        // their final tails; the source-routed capture callbacks feed the new instances.
        let onLocalSegments: LocalTranscriptionService.SegmentsHandler = { [weak self] segments in
          self?.handleBackendSegments(segments)
        }
        // Mirror startTranscription: wire onModelLoadFailed so a Parakeet model
        // load failure on the re-armed instances falls back to cloud instead of
        // recording into a void (a silent blank transcript). Without this, every
        // conversation after the first in a session loses that protection.
        let onModelLoadFailed: @MainActor () -> Void = { [weak self] in
          self?.handleLocalSTTModelLoadFailure()
        }
        let mic = LocalTranscriptionService(language: effectiveLanguage, isUser: true)
        mic.start(onSegments: onLocalSegments, onModelLoadFailed: onModelLoadFailed)
        localMicService = mic
        let system = LocalTranscriptionService(language: effectiveLanguage, isUser: false)
        system.start(onSegments: onLocalSegments, onModelLoadFailed: onModelLoadFailed)
        localSystemService = system
        // CoreAudio callbacks capture their local transcription sinks when the
        // tap starts. Rebuild them so audio reaches these fresh services rather
        // than the retired instances whose tails were just flushed.
        await rebuildCoreAudioCaptureStack(reason: "local_conversation_rotation")
        guard isTranscribing, recordingGeneration == rotationGeneration else {
          return .error("transcription session changed during reconnect")
        }
        log("Transcription: Re-armed on-device Parakeet (mic + system) for next conversation")
      } else {
        transcriptionService = try TranscriptionService(
          language: effectiveLanguage,
          clientConversationId: nextClientConversationId,
          conversationRole: nextConversationRole ?? currentConversationRole
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
              // Mirror startTranscription: on cloud reconnect exhaustion, fail
              // over to on-device Parakeet (Apple Silicon) instead of hard-
              // stopping capture mid-meeting. Plain stopTranscription() here
              // dropped the cloud->local resilience for every conversation after
              // the first.
              self?.handleCloudSTTReconnectFailure()
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
    let sessionConversationRole = nextConversationRole ?? currentConversationRole
    let sessionGeneration = recordingGeneration
    Task {
      do {
        let sessionId = try await TranscriptionStorage.shared.startSession(
          source: currentConversationSource.rawValue,
          language: lang,
          timezone: TimeZone.current.identifier,
          inputDeviceName: recordingInputDeviceName,
          clientConversationId: nextClientConversationId,
          conversationRole: sessionConversationRole,
          finalizationStrategy: sttSession.useLocalSTT ? .localSegments : .cloudReconcile
        )
        let sessionStillCurrent = await MainActor.run { () -> Bool in
          guard self.isTranscribing, self.recordingGeneration == sessionGeneration else { return false }
          self.currentSessionId = sessionId
          LiveNotesMonitor.shared.startSession(sessionId: sessionId)
          return true
        }
        guard sessionStillCurrent else { return }
        let pendingMeetingState = await MainActor.run { () -> Bool? in
          let pending = self.pendingMeetingState
          self.pendingMeetingState = nil
          return pending
        }
        if let pendingMeetingState {
          await self.handleMeetingObservation(active: pendingMeetingState)
          guard self.recordingGeneration == sessionGeneration else { return }
        }
        if let backendId = await MainActor.run(body: { () -> String? in
          guard self.isTranscribing, self.recordingGeneration == sessionGeneration else { return nil }
          let candidate = self.pendingBackendConversationId ?? self.currentBackendConversationId
          guard let candidate else { return nil }
          return DesktopConversationMatchPolicy.shouldBindConversationSession(
            incomingBackendId: candidate,
            expectedBackendId: self.currentClientConversationId,
            activeBackendId: self.currentBackendConversationId,
            ignoredRotatedBackendIds: self.ignoredRotatedBackendConversationIds
          ) ? candidate : nil
        }) {
          try await TranscriptionStorage.shared.bindBackendConversation(id: sessionId, backendId: backendId)
          await MainActor.run {
            guard self.isTranscribing, self.recordingGeneration == sessionGeneration else { return }
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
    meetingDetectorMode = nil
    captureGateInFlight = false
    captureReconcilePending = false
    pendingCoreAudioCaptureRecoveryReason = nil
    silentMicRecoveryAttempts = 0
    silentMicHealedDeviceID = nil
    isAwaitingMeeting = false
    meetingBoundaryInProgress = false
    pendingMeetingState = nil

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
    sttSession.endRecording()

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

    // A terminal STT error belongs to the session that just ended. Leaving it
    // set after an explicit stop/reset makes the idle home header look
    // permanently blocked even though no audio is being handed to STT.
    transcriptionServiceError = nil

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
    currentClientConversationId = nil
    meetingBoundaryInProgress = false
    pendingMeetingState = nil

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
  func automationStartCaptureTestSession() async -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "capture test session disabled on production bundles"]
    }
    if isTranscribing {
      if automationCaptureTestSessionActive {
        return [
          "already_recording": "true",
          "session_id": currentSessionId.map { "\($0)" } ?? "",
          "segment_count": "\(totalSegmentCount)",
        ]
      }
      return ["error": "real capture session already active"]
    }
    do {
      let sessionId = try await TranscriptionStorage.shared.startSession(
        source: currentConversationSource.rawValue,
        language: AssistantSettings.shared.effectiveTranscriptionLanguage,
        timezone: TimeZone.current.identifier,
        inputDeviceName: "harness-capture",
        clientConversationId: UUID().uuidString.lowercased(),
        finalizationStrategy: .localSegments
      )
      currentSessionId = sessionId
      recordingStartTime = Date()
      isTranscribing = true
      sttSession.activeMode = .local
      speakerSegments = []
      totalSegmentCount = 0
      totalWordCount = 0
      currentTranscript = ""
      LiveNotesMonitor.shared.startSession(sessionId: sessionId)
      automationCaptureTestSessionActive = true
      return [
        "started": "true",
        "session_id": "\(sessionId)",
        "is_transcribing": "true",
      ]
    } catch {
      return ["error": "failed to start capture session: \(error.localizedDescription)"]
    }
  }

  func automationInjectCaptureTestTranscript(text: String) async -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "capture test transcript disabled on production bundles"]
    }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return ["error": "missing transcript text"] }
    guard automationCaptureTestSessionActive else {
      if isTranscribing {
        return ["error": "cannot inject into non-automation capture session"]
      }
      return ["error": "no active capture session"]
    }
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
    await flushTranscriptPersistence()
    return [
      "injected": trimmed,
      "session_id": currentSessionId.map { "\($0)" } ?? "",
      "segment_count": "\(totalSegmentCount)",
      "conversation_count": "\(totalConversationsCount ?? conversations.count)",
    ]
  }

  /// Hermetic multi-speaker inject: accepts a JSON array of segment objects
  /// `[{"text":"...","speaker":"SPEAKER_00","speaker_id":0,"is_user":true}, ...]`.
  func automationInjectCaptureTestTranscriptMulti(segmentsJSON: String) async -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "capture test transcript disabled on production bundles"]
    }
    let trimmed = segmentsJSON.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return ["error": "missing segments JSON"] }
    guard automationCaptureTestSessionActive else {
      if isTranscribing {
        return ["error": "cannot inject into non-automation capture session"]
      }
      return ["error": "no active capture session"]
    }
    guard isTranscribing else { return ["error": "no active capture session"] }
    guard let data = trimmed.data(using: .utf8),
      let rawSegments = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]],
      !rawSegments.isEmpty
    else {
      return ["error": "segments must be a non-empty JSON array"]
    }

    let start = recordingStartTime.map { Date().timeIntervalSince($0) } ?? 0
    var backendSegments: [TranscriptionService.BackendSegment] = []
    var offset = max(0, start)
    var speakerLabels: [String] = []
    for (index, raw) in rawSegments.enumerated() {
      guard let text = raw["text"] as? String,
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      else {
        return ["error": "segment \(index) missing text"]
      }
      let speaker = (raw["speaker"] as? String) ?? "SPEAKER_00"
      var speakerId = raw["speaker_id"] as? Int ?? 0
      // Derive speaker_id from the label (e.g. SPEAKER_02 → 2) when omitted,
      // preventing silent collapse to SPEAKER_00 for multi-speaker fixtures.
      if raw["speaker_id"] == nil, let labelNum = speaker.split(separator: "_").last,
        let parsed = Int(labelNum)
      {
        speakerId = parsed
      }
      let isUser = raw["is_user"] as? Bool ?? (speakerId == 0)
      let segmentStart = raw["start"] as? Double ?? offset
      let segmentEnd = raw["end"] as? Double ?? (segmentStart + 0.5)
      backendSegments.append(
        TranscriptionService.BackendSegment(
          id: UUID().uuidString.lowercased(),
          text: text,
          speaker: speaker,
          speaker_id: speakerId,
          is_user: isUser,
          person_id: nil,
          start: segmentStart,
          end: max(segmentEnd, segmentStart + 0.1),
          translations: nil
        )
      )
      speakerLabels.append(speaker)
      offset = max(segmentEnd, segmentStart + 0.5) + 0.1
    }

    handleBackendSegments(backendSegments)
    await flushTranscriptPersistence()
    let uniqueSpeakers = Set(speakerLabels).sorted().joined(separator: ",")
    return [
      "injected_count": "\(backendSegments.count)",
      "session_id": currentSessionId.map { "\($0)" } ?? "",
      "segment_count": "\(totalSegmentCount)",
      "unique_speakers": uniqueSpeakers,
      "conversation_count": "\(totalConversationsCount ?? conversations.count)",
    ]
  }

  /// Hermetic capture teardown: mirrors the session-finalization portion of
  /// `stopTranscription()` (finish session, finalize conversation, clear live
  /// transcript state, reload conversations) without stopping the audio engine
  /// or cloud STT WebSocket. Keep this in sync when `stopTranscription()` changes.
  func automationStopCaptureTestSession() async -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "capture test session disabled on production bundles"]
    }
    guard automationCaptureTestSessionActive else {
      if isTranscribing {
        return ["error": "cannot stop non-automation capture session"]
      }
      return [
        "already_stopped": "true",
        "conversation_count": "\(totalConversationsCount ?? conversations.count)",
      ]
    }
    guard isTranscribing else {
      automationCaptureTestSessionActive = false
      return [
        "already_stopped": "true",
        "conversation_count": "\(totalConversationsCount ?? conversations.count)",
      ]
    }
    let beforeCount = totalConversationsCount ?? conversations.count
    let sessionId = currentSessionId
    let segmentCount = totalSegmentCount

    isTranscribing = false
    LiveNotesMonitor.shared.endSession()

    var finalizeError: String?
    await flushTranscriptPersistence()
    if let sessionId {
      do {
        try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .userStop)
        await ConversationFinalizationService.shared.finalizeSession(
          id: sessionId,
          reason: .userStop,
          allowCloudForceProcess: false
        )
      } catch {
        finalizeError = "failed to finalize capture session: \(error.localizedDescription)"
      }
    }

    // Reset cleanup state regardless of finalize outcome so a failed finalize
    // can't leave `automationCaptureTestSessionActive` stuck true (which made a
    // retried stop silently report "already_stopped" without ever finalizing).
    speakerSegments = []
    liveSpeakerPersonMap = [:]
    LiveTranscriptMonitor.shared.clear()
    LiveNotesMonitor.shared.clear()
    recordingStartTime = nil
    currentSessionId = nil
    sttSession.endRecording()
    totalSegmentCount = 0
    totalWordCount = 0
    currentTranscript = ""
    automationCaptureTestSessionActive = false

    if let finalizeError {
      return ["error": finalizeError]
    }

    await loadConversations()
    let afterCount = totalConversationsCount ?? conversations.count
    let latestConversationId = conversations.first?.id ?? ""
    return [
      "stopped": "true",
      "conversation_count_before": "\(beforeCount)",
      "conversation_count_after": "\(afterCount)",
      "conversation_count_increased": afterCount > beforeCount ? "true" : "false",
      "segment_count": "\(segmentCount)",
      "latest_conversation_id": latestConversationId,
    ]
  }
  // MARK: - Conversations
}
