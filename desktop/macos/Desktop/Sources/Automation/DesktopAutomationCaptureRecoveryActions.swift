import Foundation
import OmiSupport

extension DesktopAutomationActionRegistry {
  func registerCaptureRecoveryActions() {
    register(
      name: "capture_source_recovery_snapshot", effects: [],
      summary: "Read current capture-source liveness and microphone recovery state without recording content"
    ) { _ in
      guard let state = AppState.current else { return ["error": "app state unavailable"] }
      return state.captureSourceRecoverySnapshot()
    }

    register(
      name: "inject_silent_microphone_trip",
      effects: [.localState, .localArtifact, .networkOrModel, .remoteWrite],
      summary: "Inject one watchdog event into a real active microphone session on a synthetic local profile",
      category: "debug", surfaces: ["audio"],
      sideEffects: ["may rebuild microphone capture or finalize the synthetic recording"],
      examples: ["./scripts/omi-ctl action inject_silent_microphone_trip"]
    ) { _ in
      guard AppBuild.isNonProduction, DesktopLocalProfile.isEnabled else {
        return ["error": "requires a non-production local harness profile"]
      }
      guard let state = AppState.current, state.isLiveCapturing,
        state.audioSource == .microphone, let microphone = state.audioCaptureService,
        microphone.capturing, !state.captureGateInFlight
      else { return ["error": "requires an active, settled microphone capture"] }
      let session = state.currentSessionId
      let generation = state.recordingGeneration
      let tap = state.systemAudioCaptureService as AnyObject?
      let mixer = state.audioMixer
      // The driver is real. Only its watchdog observation is injected; no fake
      // liveness, authorization, STT, or session authority is installed.
      await state.handleSharedCaptureSilentMicDetection(
        detection: AudioCaptureService.SilentMicDetection(
          deviceID: microphone.activeDeviceID, deviceDescription: "injected watchdog event",
          consecutiveSilentWindows: 2, isBluetoothTransport: false,
          framesReceived: 32000, peak: 0, secondsToFirstFrame: nil))
      var result = state.captureSourceRecoverySnapshot()
      result["same_session"] = "\(state.currentSessionId == session && state.recordingGeneration == generation)"
      result["same_system_tap"] = "\((state.systemAudioCaptureService as AnyObject?) === tap)"
      result["same_mixer"] = "\(state.audioMixer === mixer)"
      return result
    }
  }
}

@MainActor
extension AppState {
  func captureSourceRecoverySnapshot() -> [String: String] {
    [
      "is_transcribing": "\(isTranscribing)",
      "is_live_capturing": "\(isLiveCapturing)",
      "microphone_capturing": "\(audioCaptureService?.capturing == true)",
      "microphone_signal_missing": "\(isMicrophoneSignalMissing)",
      "system_audio_live": "\(isSystemAudioCaptureLive)",
      "recovery_attempts": "\(silentMicRecoveryAttempts)",
      "capture_gate_in_flight": "\(captureGateInFlight)",
      "has_transcription_error": "\(transcriptionServiceError != nil)",
      "listening_tooltip": ShellStatusTooltip.audio(
        state: CaptureListeningLogic.listeningStatus(appState: self), mode: "current mode",
        hasMicrophonePermission: hasMicrophonePermission,
        microphoneSignalMissing: transcriptionServiceError == nil && isMicrophoneSignalMissing,
        systemAudioContinues: isSystemAudioCaptureLive),
    ]
  }
}
