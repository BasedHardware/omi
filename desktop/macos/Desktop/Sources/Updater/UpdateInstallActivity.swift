import Foundation

/// Capture activity that makes an update relaunch destructive.
///
/// A Sparkle relaunch ends the live capture session: the relaunched app recovers it as
/// `crash_recovery` and opens a new one, so one call becomes two conversations. The updater
/// reads this gate instead of a VAD probe; the VAD gate it used to read has not been
/// instantiated since 2026-04, which made every deferral check a silent no-op.
///
/// Writers are the live capture paths (main actor); the reader is the Sparkle delegate and its
/// deferred-install timer, so state is guarded by a lock rather than actor isolation.
enum UpdateInstallActivity {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var lastTranscriptAt: Date?
  private nonisolated(unsafe) static var meetingCaptureActive = false

  /// Record that live transcription produced speech.
  static func markTranscriptActivity(at date: Date = Date()) {
    lock.lock()
    lastTranscriptAt = date
    lock.unlock()
  }

  /// Record whether a meeting-role conversation is being captured right now (audio reaching STT,
  /// not an Only-Meetings session armed with the microphone paused).
  static func setMeetingCaptureActive(_ active: Bool) {
    lock.lock()
    meetingCaptureActive = active
    lock.unlock()
  }

  /// The instant that capture was last known to be active. A meeting in progress is active
  /// now, even through a quiet stretch; otherwise the last transcribed speech decides.
  static func lastActivityAt(now: Date = Date()) -> Date? {
    lock.lock()
    defer { lock.unlock() }
    return meetingCaptureActive ? now : lastTranscriptAt
  }

  /// Test seam. Not DEBUG-gated: the release compile also builds the test target.
  static func resetForTesting() {
    lock.lock()
    lastTranscriptAt = nil
    meetingCaptureActive = false
    lock.unlock()
  }
}
