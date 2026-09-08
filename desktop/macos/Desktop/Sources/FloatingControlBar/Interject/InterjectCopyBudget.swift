import Foundation

/// Per-decision-type visible-copy limits. The 120/600 director clamp remains
/// the hard safety ceiling; these only tighten when Interject is on.
enum InterjectCopyBudget {
  struct Limits: Equatable, Sendable {
    let titleLimit: Int
    let messageLimit: Int
  }

  static let safetyTitleLimit = 120
  static let safetyMessageLimit = 600

  static func limits(for decision: String) -> Limits {
    switch decision {
    case "task_candidate":
      return Limits(titleLimit: 80, messageLimit: 280)
    case "resurface":
      return Limits(titleLimit: 60, messageLimit: 160)
    case "insight":
      return Limits(titleLimit: 70, messageLimit: 200)
    case "suggest":
      return Limits(titleLimit: 70, messageLimit: 220)
    default:
      return Limits(titleLimit: safetyTitleLimit, messageLimit: safetyMessageLimit)
    }
  }

  static func clampedTitleLimit(_ proposed: Int) -> Int {
    min(max(proposed, 1), safetyTitleLimit)
  }

  static func clampedMessageLimit(_ proposed: Int) -> Int {
    min(max(proposed, 1), safetyMessageLimit)
  }

  /// Appended to the director stable prompt only when Interject is on, so the
  /// flag-off prefix stays byte-identical to today.
  static let directorPromptSection = """
    Copy length, by decision type — terse, but readable. Plain language. Jargon \
    only when the topic itself uses it.
    - task_candidate: title ≤ 80 characters, message ≤ 280. Name the commitment \
    and who owes it.
    - resurface: title ≤ 60 characters, message ≤ 160. One-line reminder of the \
    open task and why it is timely.
    - insight: title ≤ 70 characters, message ≤ 200. One-line teaser; the card \
    expands on hover if more is needed.
    - suggest: title ≤ 70 characters, message ≤ 220. One concrete next step.
    Never pad. Never spend the budget on a category label.
    """
}
