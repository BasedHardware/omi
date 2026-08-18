import Foundation

/// Admission for transcript-driven director evaluations: a *user* utterance
/// that cleared a minimum length, separated from any earlier speech evaluation
/// by a cooldown, while the assistant is not mid-turn. Pure so the decide loop
/// is unit-testable without the coordinator or the engine.
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
  }

  static func decides(
    flagEnabled: Bool,
    conversationActive: Bool,
    latestUserSlice: TranscriptSpeechSlice?,
    lastEvaluationAt: Date?,
    now: Date,
    minimumUserWordCount: Int = minimumUserWordCount,
    cooldownSeconds: TimeInterval = evaluationCooldownSeconds
  ) -> Outcome {
    guard flagEnabled else { return .skip(.flagDisabled) }
    guard !conversationActive else { return .skip(.conversationActive) }
    guard let latestUserSlice, latestUserSlice.isUser else { return .skip(.noUserSpeech) }
    let wordCount = latestUserSlice.text.split(whereSeparator: { $0.isWhitespace }).count
    guard wordCount >= minimumUserWordCount else { return .skip(.utteranceTooShort) }
    if let lastEvaluationAt {
      guard now.timeIntervalSince(lastEvaluationAt) >= cooldownSeconds else {
        return .skip(.coolingDown)
      }
    }
    return .evaluate
  }
}
