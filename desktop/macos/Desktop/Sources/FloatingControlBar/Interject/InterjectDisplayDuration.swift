import Foundation

/// Reading-time display duration for a proactive card.
///
/// Flag-off callers use ``flagOffTimeout``: the floating bar's informational-card time
/// (`FloatingBarNoticePolicy`), paused while hovered like the Interject path.
enum InterjectDisplayDuration {
  static let flagOffTimeout: TimeInterval = OmiFeedbackTiming.informational
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
    case .general, .functional, .trial, .onboarding, .dailyRecap, .memory, .goal, .meetingNotes,
      .integration:
      return 5
    }
  }

  static func wordCount(in text: String) -> Int {
    text.split { $0.isWhitespace || $0.isNewline }.count
  }

  /// Insight cards render one line until hover. Duration follows that teaser
  /// so a long body the user has not expanded cannot pin the card at 14s.
  static let insightTeaserWordCap = 12

  /// First line, capped to the notch teaser width.
  static func teaserText(of message: String) -> String {
    let firstLine =
      message.split(separator: "\n", maxSplits: 1, omittingEmptySubsequences: false)
      .first.map(String.init) ?? message
    let words = firstLine.split { $0.isWhitespace }
    if words.count <= insightTeaserWordCap { return firstLine }
    return words.prefix(insightTeaserWordCap).joined(separator: " ")
  }

  /// `base + 250ms/word`, clamped to 4…14s. Insights count the teaser, not
  /// the unexpanded body.
  static func timeout(
    title: String,
    message: String,
    kind: ProactiveNotificationKind
  ) -> TimeInterval {
    let countedMessage = kind == .insight ? teaserText(of: message) : message
    let words = wordCount(in: title) + wordCount(in: countedMessage)
    let raw = baseTimeout(for: kind) + (TimeInterval(words) * secondsPerWord)
    return min(maximumTimeout, max(minimumTimeout, raw))
  }

  /// Flag-off path is the informational-card time, ignoring copy and category.
  static func timeout(
    title: String,
    message: String,
    kind: ProactiveNotificationKind,
    enabled: Bool
  ) -> TimeInterval {
    enabled ? timeout(title: title, message: message, kind: kind) : flagOffTimeout
  }
}
