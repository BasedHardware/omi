import Foundation

/// Admission for transcript-driven director evaluations: a *user* utterance
/// that cleared a minimum length, separated from any earlier speech evaluation
/// by a cooldown, while the assistant is not mid-turn. Pure so the decide loop
/// is unit-testable without the coordinator or the engine.
///
/// The decision is made about the slice that just *arrived*, never about
/// whichever user slice happens to still be in the window. Judging the window
/// let another person speaking after the cooldown re-trigger an evaluation
/// grounded on a user utterance from up to the retention window ago — the
/// speaker had said nothing, and the answer would have been to a stale
/// question.
enum SpeechProactivityAdmission {
  static let minimumUserWordCount = 4
  static let evaluationCooldownSeconds: TimeInterval = 90

  enum Outcome: Equatable {
    case evaluate
    case skip(Reason)
  }

  enum Reason: Equatable {
    case flagDisabled
    case conversationActive
    case noUserSpeech
    case utteranceTooShort
    case coolingDown
    /// The same backend segment already triggered an evaluation. Transcripts
    /// are re-delivered as a segment grows, so without this the same utterance
    /// evaluates again every time the cooldown lapses.
    case alreadyEvaluated
  }

  static func decides(
    flagEnabled: Bool,
    conversationActive: Bool,
    arrivingSlice: TranscriptSpeechSlice?,
    lastEvaluationAt: Date?,
    lastEvaluatedSegmentID: String? = nil,
    now: Date,
    minimumUserWordCount: Int = minimumUserWordCount,
    cooldownSeconds: TimeInterval = evaluationCooldownSeconds
  ) -> Outcome {
    guard flagEnabled else { return .skip(.flagDisabled) }
    guard !conversationActive else { return .skip(.conversationActive) }
    guard let arrivingSlice, arrivingSlice.isUser else { return .skip(.noUserSpeech) }
    let wordCount = arrivingSlice.text.split(whereSeparator: { $0.isWhitespace }).count
    guard wordCount >= minimumUserWordCount else { return .skip(.utteranceTooShort) }
    if let lastEvaluatedSegmentID, let segmentID = arrivingSlice.segmentID, segmentID == lastEvaluatedSegmentID {
      return .skip(.alreadyEvaluated)
    }
    if let lastEvaluationAt {
      guard now.timeIntervalSince(lastEvaluationAt) >= cooldownSeconds else {
        return .skip(.coolingDown)
      }
    }
    return .evaluate
  }
}
