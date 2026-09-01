import Foundation

/// Pause/resume remaining-time tracker for a presented card.
///
/// Hover and PTT pause; releasing them resumes from the leftover duration.
/// The manager sleeps ``remaining(at:)`` and dismisses only when this reports
/// expiry while unpaused.
struct InterjectDisplayTimer: Equatable, Sendable {
  var duration: TimeInterval
  private var remainingWhenPaused: TimeInterval
  private var runningSince: Date?

  var isPaused: Bool { runningSince == nil }

  static func start(duration: TimeInterval, now: Date) -> InterjectDisplayTimer {
    InterjectDisplayTimer(
      duration: duration,
      remainingWhenPaused: duration,
      runningSince: now
    )
  }

  func remaining(at now: Date) -> TimeInterval {
    if let runningSince {
      return max(0, remainingWhenPaused - now.timeIntervalSince(runningSince))
    }
    return max(0, remainingWhenPaused)
  }

  func isExpired(at now: Date) -> Bool {
    !isPaused && remaining(at: now) <= 0
  }

  mutating func pause(now: Date) {
    guard runningSince != nil else { return }
    remainingWhenPaused = remaining(at: now)
    runningSince = nil
  }

  mutating func resume(now: Date) {
    guard isPaused else { return }
    runningSince = now
  }
}
