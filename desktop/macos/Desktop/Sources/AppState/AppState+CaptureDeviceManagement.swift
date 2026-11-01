@preconcurrency import AVFoundation
import Foundation

/// Capture-device management for a live transcription session: silent-mic
/// healing, CoreAudio stack rebuilds, and preferred-microphone re-pinning.
/// These paths all mutate `audioCaptureService` in place so the session,
/// conversation, and capture-attempt identity survive (SCA-526).
@MainActor
extension AppState {
  /// Fall back from a silent Bluetooth mic to the built-in microphone.
  /// Triggered by `AudioCaptureService.onSilentMicDetected`.
  func handleSilentMicFallback(detection: AudioCaptureService.SilentMicDetection) async {
    guard isTranscribing, !silentMicFallbackInProgress else { return }
    recordSilentMicDiagnostic(detection: detection, phase: "initial", result: "watchdog_trip")
    silentMicFallbackInProgress = true
    defer { silentMicFallbackInProgress = false }

    guard let builtInID = AudioCaptureService.findBuiltInMicDeviceID() else {
      log("Transcription: silent-mic detected but no built-in microphone available — leaving capture as-is")
      silentMicFallbackInProgress = false
      await handleSharedCaptureSilentMicDetection(detection: detection, recordTrip: false)
      return
    }

    log("Transcription: silent-mic fallback — switching to built-in mic (deviceID=\(builtInID))")
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "silent_mic",
      from: "bluetooth",
      to: "built_in",
      reason: "local_heal",
      outcome: .degraded,
      extra: ["user_visible": false])

    // Hold the healed route for the rest of the session so the next rebuild does not
    // re-resolve back to the silent default and undo this.
    silentMicHealedDeviceID = builtInID
    recordingInputDeviceName =
      AudioCaptureService.deviceName(for: builtInID) ?? "Built-in Microphone"
    // Use the same serialized, physical-teardown boundary as other microphone
    // recovery. A queued Bluetooth callback must not swap services under a gate
    // that is already recovering or rotating the recording.
    await rebuildCoreAudioCaptureStack(reason: detection.reason, scope: .microphone)
  }

  /// Re-pin live mic capture onto a reappeared preferred device **without** ending the
  /// session. The monitor's former full `stopTranscription`+`startTranscription` restart
  /// emitted a Stopped/Started pair and split the conversation on every qualifying
  /// device-list event — a flapping Bluetooth headset became a visible capture loop
  /// (SCA-526). An in-place swap costs a brief capture gap and keeps the session,
  /// conversation, and attempt identity intact.
  func reapplyPreferredMicrophone(deviceID: AudioDeviceID, deviceName: String?) async {
    if captureGateInFlight {
      pendingPreferredMicReapplyDeviceID = deviceID
      pendingPreferredMicReapplyDeviceName = deviceName
      return
    }
    guard swapCaptureServiceToPreferredMicrophone(deviceID: deviceID, deviceName: deviceName)
    else { return }
    // Same entry point the silent-mic fallback uses: arms the watchdog, keeps the
    // mixer/local-STT sink wiring, and honors the meeting gate via reconcileCapture.
    await startMicrophoneAudioCapture()
  }

  /// Synchronous swap portion of `reapplyPreferredMicrophone` — stops the old
  /// capture service and installs a replacement bound to `deviceID`. The
  /// session, conversation, and attempt identity are untouched; the caller
  /// re-arms capture through `startMicrophoneAudioCapture`. Split out so the
  /// identity-preserving contract is testable without opening the HAL.
  @discardableResult
  func swapCaptureServiceToPreferredMicrophone(
    deviceID: AudioDeviceID, deviceName: String?
  ) -> Bool {
    guard isTranscribing, let current = audioCaptureService, current.capturing else {
      return false
    }
    guard current.activeDeviceID != deviceID else { return false }
    // A silent-mic heal stays pinned for the session — swapping back onto the device
    // that just went silent would undo the recovery (and the watchdog would fire again).
    guard silentMicHealedDeviceID == nil else { return false }
    pendingPreferredMicReapplyDeviceID = nil
    pendingPreferredMicReapplyDeviceName = nil
    lastPreferredMicSwapAt = Date()

    log(
      "Transcription: preferred microphone reconnected — swapping capture in place (deviceID=\(deviceID))"
    )
    // Provider/device switch with successful recovery — shared fallback surface (AGENTS.md).
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "transcription_input",
      from: "system_default_input",
      to: "preferred_microphone",
      reason: "device_reconnected",
      outcome: .recovered)

    current.stopCapture()
    audioCaptureService = AudioCaptureService(overrideDeviceID: deviceID)
    if let deviceName {
      recordingInputDeviceName = deviceName
    }
    return true
  }

  @discardableResult
  func rebuildCoreAudioCaptureStack(
    reason: String, scope: CoreAudioCaptureRecoveryRequest.Scope = .allSources,
    effects: CoreAudioCaptureRecoveryEffects = .live
  ) async -> Bool {
    guard isTranscribing, let previous = audioCaptureService else { return false }

    if captureGateInFlight {
      // Rotation / actual stack failure needs both sources re-bound. A later
      // microphone trip cannot downgrade that already-owed reconciliation.
      if pendingCoreAudioCaptureRecovery?.scope != .allSources {
        pendingCoreAudioCaptureRecovery = CoreAudioCaptureRecoveryRequest(reason: reason, scope: scope)
      }
      return false
    }

    log("Transcription: rebuilding CoreAudio capture scope=\(scope) — \(reason)")
    captureReconcilePending = false
    captureGateInFlight = true

    previous.stopCapture()
    // Releasing an IOProc is asynchronous. Never open the replacement before
    // its predecessor has physically released the device. Stop/owner changes
    // while waiting revoke this recovery; they must not resurrect capture.
    await previous.waitForPhysicalStop()
    guard isTranscribing, audioCaptureService === previous else { return false }
    if scope == .allSources {
      if #available(macOS 14.4, *) {
        (systemAudioCaptureService as? SystemAudioCaptureService)?.stopCapture()
        systemAudioCaptureService = nil
        AudioLevelMonitor.shared.updateSystemLevel(0)
      }
      if !sttSession.useLocalSTT {
        audioMixer?.stop()
        audioMixer = AudioMixer()
      }
    }
    // Rebuilding must not silently move the user back onto a route already proven dead.
    // The choice is `SilentMicRoutePolicy`'s so the contract has one tested home; a nil
    // result means "follow the system default", which is what the plain initialiser does.
    audioCaptureService = effects.makeMicrophone(
      SilentMicRoutePolicy.captureDeviceID(healed: silentMicHealedDeviceID, systemDefault: nil))
    AudioLevelMonitor.shared.updateMicrophoneLevel(0)

    // The tap, mixer clock/buffers, STT and conversation are independent owners.
    // Replacing them for a microphone-only failure drops valid system audio.

    let routeName =
      silentMicHealedDeviceID.flatMap { AudioCaptureService.deviceName(for: $0) }
      ?? AudioCaptureService.getCurrentMicrophoneName()
    recordingInputDeviceName = routeName ?? recordingInputDeviceName
    captureGateInFlight = false
    await effects.armCapture(self)
    return isTranscribing
  }

  /// A fresh `AudioCaptureService` resets its own watchdog cap. Keep the terminal policy at
  /// the session owner so an unrecoverable USB/built-in route cannot loop forever while the
  /// UI continues to claim it is recording.
  func handleSharedCaptureSilentMicDetection(
    detection: AudioCaptureService.SilentMicDetection, recordTrip: Bool = true
  ) async {
    guard isTranscribing else { return }
    silentMicRecoveryAttempts += 1
    if recordTrip {
      recordSilentMicDiagnostic(
        detection: detection,
        phase: armedMicrophoneRecovery.isProbing
          ? "armed_retry" : silentMicRecoveryAttempts == 1 ? "initial" : "rebuild",
        result: "watchdog_trip")
    }

    switch SharedCaptureSilentMicRecoveryPolicy.action(
      for: silentMicRecoveryAttempts,
      systemAudioLive: !armedMicrophoneRecovery.isProbing && isSystemAudioCaptureLive)
    {
    case .rebuild:
      log("Transcription: silent microphone detected — rebuilding microphone capture only")
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "silent_mic",
        from: "stalled_route",
        to: "rebuilt_microphone",
        reason: "local_heal",
        outcome: .degraded,
        extra: ["recovery_attempts": silentMicRecoveryAttempts, "user_visible": false])
      let restarted = await rebuildCoreAudioCaptureStack(reason: detection.reason, scope: .microphone)
      if restarted {
        recordSilentMicDiagnostic(detection: nil, phase: "rebuild", result: "capture_restarted")
      }
    case .continueSystemAudio:
      isMicrophoneSignalMissing = true
      // Do not finalize, re-arm, release STT, or close the tap. The current mic
      // remains open and its live-signal callback can clear this warning.
      log("Transcription: microphone recovery exhausted — continuing live system audio")
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "silent_mic", from: "stalled_route", to: "system_audio_only",
        reason: "policy", outcome: .degraded,
        extra: ["recovery_attempts": silentMicRecoveryAttempts, "user_visible": true])
      recordSilentMicDiagnostic(detection: detection, phase: "rebuild", result: "system_audio_continues")
    case .stopAndSurfaceError:
      log("Transcription: stopping after repeated silent microphone recovery failures")
      let shouldArm =
        captureAttempt?.intent == .auto
        && audioSource == .microphone
        && AudioCaptureService.authorizationStatus() == .authorized
        && AssistantSettings.shared.audioRecordingMode != .off
      if !shouldArm {
        DesktopDiagnosticsManager.shared.recordTranscriptionSilentCaptureExhausted(
          recoveryAttempts: silentMicRecoveryAttempts)
      }
      if shouldArm {
        recordSilentMicDiagnostic(detection: detection, phase: "armed_retry", result: "armed_waiting")
      }
      let exhaustedLaunchContext = captureAttempt?.launchContext
      let exhaustedUpdateAttemptID = captureAttempt?.updateAttemptID
      let exhaustedInputIsBuiltIn = (audioCaptureService?.activeDeviceID).flatMap {
        CaptureInputPresence.builtIn(deviceID: $0)
      }
      captureAttempt?.noteErrorTerminal()
      if shouldArm { armedMicrophoneTransitionInFlight = true }
      let teardown = stopTranscription(finalizationReason: .silentMicExhausted)
      if shouldArm {
        await teardown?.value
        armedMicrophoneTransitionInFlight = false
        guard !isTranscribing, AssistantSettings.shared.audioRecordingMode != .off else { return }
        armedMicrophoneRecovery.enter(
          appState: self, launchContext: exhaustedLaunchContext,
          updateAttemptID: exhaustedUpdateAttemptID, inputIsBuiltIn: exhaustedInputIsBuiltIn)
        log("Transcription: automatic capture waiting for a live microphone")
        return
      }
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

  var isSystemAudioCaptureLive: Bool {
    if #available(macOS 14.4, *),
      let systemService = systemAudioCaptureService as? SystemAudioCaptureService
    {
      return systemService.hasRecentAudioFrames
    }
    return false
  }

  func handleSharedMicrophoneSignalRecovered(from service: AudioCaptureService) {
    guard isTranscribing, audioCaptureService === service, service.capturing, isMicrophoneSignalMissing else { return }
    isMicrophoneSignalMissing = false
    recordSilentMicDiagnostic(detection: nil, phase: "rebuild", result: "live_signal")
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "silent_mic", from: "system_audio_only", to: "microphone_and_system",
      reason: "local_heal", outcome: .recovered)
  }
}
