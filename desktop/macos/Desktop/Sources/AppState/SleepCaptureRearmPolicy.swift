import Foundation

/// DarkWake posts `willSleep` and keeps the process scheduled, but does not post
/// `didWake` until a later FullWake. Always-on capture has to restart from that
/// still-scheduled probe. A real wake still owns every mode except off.
enum SleepCaptureRearmSignal: Equatable {
  case didWake
  case stillScheduled
}

enum SleepCaptureRearmAction: Equatable {
  case leaveStopped
  case restart
}

enum SleepCaptureRearmPolicy {
  /// Long enough that a suspended Mac has not resumed. If this elapses while
  /// the process is still scheduled, the sleep was DarkWake.
  static let stillScheduledDelay: Duration = .seconds(2)

  /// Same settle `didWake` already waits before touching the microphone.
  static let audioSettleDelay: Duration = .seconds(2)

  static func action(
    wasTranscribingBeforeSleep: Bool,
    recordingMode: AssistantSettings.AudioRecordingMode,
    isTranscribing: Bool,
    signal: SleepCaptureRearmSignal
  ) -> SleepCaptureRearmAction {
    guard wasTranscribingBeforeSleep, !isTranscribing else { return .leaveStopped }
    switch signal {
    case .didWake:
      return recordingMode == .off ? .leaveStopped : .restart
    case .stillScheduled:
      return recordingMode == .always ? .restart : .leaveStopped
    }
  }
}

@MainActor
extension AppState {
  func armDarkWakeCaptureRearm() {
    cancelDarkWakeCaptureRearm()
    guard
      SleepCaptureRearmPolicy.action(
        wasTranscribingBeforeSleep: wasTranscribingBeforeSleep,
        recordingMode: AssistantSettings.shared.audioRecordingMode,
        isTranscribing: isTranscribing,
        signal: .stillScheduled
      ) == .restart
    else { return }
    darkWakeRearmTask = Task { @MainActor [weak self] in
      do {
        try await Task.sleep(for: SleepCaptureRearmPolicy.stillScheduledDelay)
        try await Task.sleep(for: SleepCaptureRearmPolicy.audioSettleDelay)
      } catch {
        return
      }
      guard let self, !Task.isCancelled else { return }
      guard self.claimSleepRestart(signal: .stillScheduled) else { return }
      log("DarkWake: restarting always-on transcription")
      self.startTranscription(
        conversationRole: self.conversationRoleBeforeSleep,
        userInitiated: false,
        launchContext: .wake
      )
    }
  }

  func cancelDarkWakeCaptureRearm() {
    darkWakeRearmTask?.cancel()
    darkWakeRearmTask = nil
  }

  /// Consumes the sleep handoff. A real wake always consumes it. The DarkWake
  /// probe consumes it only when it is the path that restarts always-on capture,
  /// so a later FullWake does not start a second session.
  @discardableResult
  func claimSleepRestart(signal: SleepCaptureRearmSignal) -> Bool {
    let action = SleepCaptureRearmPolicy.action(
      wasTranscribingBeforeSleep: wasTranscribingBeforeSleep,
      recordingMode: AssistantSettings.shared.audioRecordingMode,
      isTranscribing: isTranscribing,
      signal: signal
    )
    if signal == .didWake || action == .restart {
      wasTranscribingBeforeSleep = false
    }
    return action == .restart
  }
}
