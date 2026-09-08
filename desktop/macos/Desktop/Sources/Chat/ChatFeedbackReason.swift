import Foundation

/// Why a user gave a thumbs-down.
///
/// The raw values match the backend `FeedbackReason` enum. The first five are
/// the reasons the mobile client has always sent, so desktop and mobile chat
/// feedback land in the same buckets in the daily report. The remaining five
/// are desktop-only, for proactive-notification cards (focus/insight/task/
/// memory) — a distinct taxonomy from a chat answer's, kept separate rather
/// than folded into the mobile five so neither set is diluted by the other's.
/// Adding a case here without adding it to `backend/models/feedback.py` will
/// be rejected by the API as invalid.
enum ChatFeedbackReason: String, CaseIterable, Identifiable, Sendable {
  case incorrectOrHallucination = "incorrect_or_hallucination"
  case notHelpfulOrIrrelevant = "not_helpful_or_irrelevant"
  case didntFollowInstructions = "didnt_follow_instructions"
  case tooVerbose = "too_verbose"
  case other = "other"

  case notAboutMe = "not_about_me"
  case alreadyDone = "already_done"
  case wrongFacts = "wrong_facts"
  case badTiming = "bad_timing"
  case notUseful = "not_useful"

  var id: String { rawValue }

  /// Short label for the inline picker. Kept to two or three words so the
  /// whole picker fits under a chat bubble without wrapping.
  var label: String {
    switch self {
    case .incorrectOrHallucination: return "Incorrect"
    case .notHelpfulOrIrrelevant: return "Not helpful"
    case .didntFollowInstructions: return "Ignored instructions"
    case .tooVerbose: return "Too long"
    case .other: return "Other"
    case .notAboutMe: return "Not about me"
    case .alreadyDone: return "Already done"
    case .wrongFacts: return "Wrong facts"
    case .badTiming: return "Bad timing"
    case .notUseful: return "Not useful"
    }
  }

  /// Hover help, spelling out the distinction the short label compresses.
  var help: String {
    switch self {
    case .incorrectOrHallucination: return "The answer contained wrong or invented information"
    case .notHelpfulOrIrrelevant: return "The answer didn't address what I asked"
    case .didntFollowInstructions: return "The answer ignored instructions I gave"
    case .tooVerbose: return "The answer was longer or wordier than it needed to be"
    case .other: return "Something else"
    case .notAboutMe: return "This notification wasn't relevant to me"
    case .alreadyDone: return "I already took care of this"
    case .wrongFacts: return "This notification got the facts wrong"
    case .badTiming: return "This showed up at the wrong moment"
    case .notUseful: return "This didn't help me"
    }
  }

  /// Five surface-appropriate chips. Notification rows use the taxonomy that
  /// classified 45 of 80 thumbs-downs; chat/voice rows use the mobile five so
  /// the daily report keeps comparing the same buckets across platforms.
  static func chips(isProactiveNotification: Bool) -> [ChatFeedbackReason] {
    if isProactiveNotification {
      return [.notAboutMe, .alreadyDone, .wrongFacts, .badTiming, .notUseful]
    }
    return [.incorrectOrHallucination, .notHelpfulOrIrrelevant, .didntFollowInstructions, .tooVerbose, .other]
  }

  /// Only ever consulted for a proactive-notification rating (guarded by the
  /// caller), so the mobile-answer cases below are never actually reached —
  /// still handled explicitly so the switch stays exhaustive.
  func interjectVerb() -> InterjectFeedbackVerb {
    switch self {
    case .notAboutMe, .notUseful, .alreadyDone: return .falsePositive
    case .badTiming: return .snooze
    case .wrongFacts: return .correction
    case .incorrectOrHallucination: return .correction
    case .notHelpfulOrIrrelevant, .didntFollowInstructions, .tooVerbose, .other: return .falsePositive
    }
  }
}
