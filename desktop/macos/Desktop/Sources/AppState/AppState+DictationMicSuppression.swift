import Foundation

extension AppState {
  /// The session's dictation-app microphone monitor, created on the first mic capture start and
  /// stopped with the meeting detector on teardown. Idempotent across the silent-mic rebuilds
  /// that recreate `AudioCaptureService`: every capture in the session shares one gate.
  @discardableResult
  func ensureDictationMicSuppressionMonitor() -> DictationMicSuppressionMonitor {
    if let monitor = dictationMicSuppressionMonitor { return monitor }
    let monitor = DictationMicSuppressionMonitor(
      isEnabled: { ShortcutSettings.shared.ambientIgnoresDictationApps },
      onWindowClosed: { window in
        AnalyticsManager.shared.ambientDictationMicSuppressed(
          dictationApp: window.bundleID, durationSeconds: window.duration)
      })
    dictationMicSuppressionMonitor = monitor
    monitor.start()
    return monitor
  }

  func stopDictationMicSuppressionMonitor() {
    dictationMicSuppressionMonitor?.stop()
    dictationMicSuppressionMonitor = nil
  }
}

extension AnalyticsManager {
  /// One completed window in which ambient capture muted its microphone contribution because a
  /// dictation app held the mic. `dictationApp` is a bundle ID — a bounded dimension, never text.
  func ambientDictationMicSuppressed(dictationApp: String, durationSeconds: TimeInterval) {
    PostHogManager.shared.track(
      "Desktop Ambient Dictation Mic Suppressed",
      properties: [
        "platform": "macos",
        "dictation_app": dictationApp,
        "duration_s": (durationSeconds * 10).rounded() / 10,
      ])
  }
}
