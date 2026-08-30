import Foundation

/// Reading-time display duration for a proactive card.
///
/// Flag-off callers must use ``legacyTimeout`` so the 6s path stays literal.
enum InterjectDisplayDuration {
  static let legacyTimeout: TimeInterval = 6
  static let secondsPerWord: TimeInterval = 0.250
  static let minimumTimeout: TimeInterval = 4
  static let maximumTimeout: TimeInterval = 14

  /// Per-decision-type bases. `task_candidate` needs longer than a resurface
  /// because the commitment is the point of the interruption.
  static func baseTimeout(for kind: ProactiveNotificationKind) -> TimeInterval {
    switch kind {
    case .task:
      return 6
    case .resurface:
      return 4
    case .insight, .suggestion:
      return 5
    case .general, .memory, .goal, .meetingNotes, .integration:
      return 5
    }
  }

  static func wordCount(in text: String) -> Int {
    text.split { $0.isWhitespace || $0.isNewline }.count
  }

  /// `base + 250ms/word`, clamped to 4…14s.
  static func timeout(
    title: String,
    message: String,
    kind: ProactiveNotificationKind
  ) -> TimeInterval {
    let words = wordCount(in: title) + wordCount(in: message)
    let raw = baseTimeout(for: kind) + (TimeInterval(words) * secondsPerWord)
    return min(maximumTimeout, max(minimumTimeout, raw))
  }

  /// Flag-off path is exactly 6 seconds, ignoring copy and category.
  static func timeout(
    title: String,
    message: String,
    kind: ProactiveNotificationKind,
    enabled: Bool
  ) -> TimeInterval {
    enabled ? timeout(title: title, message: message, kind: kind) : legacyTimeout
  }
}
