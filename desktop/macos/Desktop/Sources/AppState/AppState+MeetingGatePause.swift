import Foundation

extension AppState {
  /// Pause both capture paths without ending the session, for the window in which the meeting gate
  /// has not answered yet. Mirrors the pause branches `reconcileCapture` uses once it does answer;
  /// this is the same stop, taken earlier, when the honest answer is "not in a call as far as we
  /// know".
  /// Apply `MeetingGateReadinessPolicy` and pause when it says the gate cannot yet justify capture.
  @MainActor
  func pauseCaptureIfMeetingGateUnknown(
    mode: AssistantSettings.AudioRecordingMode, meetingStateReady: Bool
  ) {
    guard
      MeetingGateReadinessPolicy.shouldPauseCapture(
        mode: mode, meetingStateReady: meetingStateReady)
    else { return }
    pauseCaptureWhileMeetingGateUnknown()
  }

  @MainActor
  func pauseCaptureWhileMeetingGateUnknown() {
    if let mic = audioCaptureService, mic.capturing {
      mic.stopCapture()
      AudioLevelMonitor.shared.updateMicrophoneLevel(0)
      log("Transcription: Microphone capture paused (meeting state not yet known)")
    }
    if #available(macOS 14.4, *) {
      if let systemService = systemAudioCaptureService as? SystemAudioCaptureService,
        systemService.capturing
      {
        systemService.stopCapture()
        AudioLevelMonitor.shared.updateSystemLevel(0)
        log("Transcription: System audio capture paused (meeting state not yet known)")
      }
    }
  }
}
