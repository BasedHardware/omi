import Foundation

/// Why a user gave an answer a thumbs-down.
///
/// The raw values match the backend `FeedbackReason` enum and the five reasons
/// the mobile client has always sent, so desktop and mobile feedback land in
/// the same buckets in the daily report. Adding a case here without adding it
/// to `backend/models/feedback.py` will be rejected by the API as invalid.
enum ChatFeedbackReason: String, CaseIterable, Identifiable, Sendable {
  case incorrectOrHallucination = "incorrect_or_hallucination"
  case notHelpfulOrIrrelevant = "not_helpful_or_irrelevant"
  case didntFollowInstructions = "didnt_follow_instructions"
  case tooVerbose = "too_verbose"
  case other = "other"

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
    }
  }
}
