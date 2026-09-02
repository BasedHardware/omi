import Foundation

/// Desktop thumbs-down reason codes. Enum column only — no free text.
enum ChatRatingReason: String, CaseIterable, Sendable {
  case notAboutMe = "not_about_me"
  case alreadyDone = "already_done"
  case wrongFacts = "wrong_facts"
  case badTiming = "bad_timing"
  case notUseful = "not_useful"

  var chipLabel: String {
    switch self {
    case .notAboutMe: return "Not about me"
    case .alreadyDone: return "Already done"
    case .wrongFacts: return "Wrong facts"
    case .badTiming: return "Bad timing"
    case .notUseful: return "Not useful"
    }
  }

  /// Five surface-appropriate chips. Notification rows use the taxonomy that
  /// classified 45 of 80 thumbs-downs; chat/voice rows lead with honesty/value.
  static func chips(isProactiveNotification: Bool) -> [ChatRatingReason] {
    if isProactiveNotification {
      return [.notAboutMe, .alreadyDone, .wrongFacts, .badTiming, .notUseful]
    }
    return [.wrongFacts, .alreadyDone, .notUseful, .badTiming, .notAboutMe]
  }

  func interjectVerb() -> InterjectFeedbackVerb {
    switch self {
    case .notAboutMe, .notUseful, .alreadyDone: return .falsePositive
    case .badTiming: return .snooze
    case .wrongFacts: return .correction
    }
  }
}
