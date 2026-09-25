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
      captureAttempt?.noteErrorTerminal()
      stopTranscription(finalizationReason: .silentMicExhausted)
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
}
