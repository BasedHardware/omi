import Foundation

enum InterjectFeedbackVerb: String, Codable, CaseIterable, Sendable {
  case useful
  case falsePositive = "false_positive"
  case snooze
  case disable
  case missed
  case correction
  case riff
}

/// One canonical suggestion-feedback row. Identity is the existing
/// `evaluation_id` / `suggestion_id` pair — other surfaces read this, they
/// never keep a parallel tally (FC-split-mutation-authority).
struct InterjectFeedbackRecord: Codable, Equatable, Sendable {
  let evaluationID: UUID
  let suggestionID: UUID
  let verb: InterjectFeedbackVerb
  let recordedAt: Date
}

/// Single mutation owner for suggestion feedback. Last write wins per identity.
actor InterjectSuggestionFeedbackStore {
  static let shared = InterjectSuggestionFeedbackStore()

  private var records: [String: InterjectFeedbackRecord] = [:]

  static func identityKey(evaluationID: UUID, suggestionID: UUID) -> String {
    "\(evaluationID.uuidString)|\(suggestionID.uuidString)"
  }

  func record(_ record: InterjectFeedbackRecord) {
    let key = Self.identityKey(
      evaluationID: record.evaluationID, suggestionID: record.suggestionID)
    records[key] = record
  }

  func current(evaluationID: UUID, suggestionID: UUID) -> InterjectFeedbackRecord? {
    records[Self.identityKey(evaluationID: evaluationID, suggestionID: suggestionID)]
  }

  func removeAllForTests() {
    records.removeAll()
  }
}

/// The only write entry point other surfaces may call. Voice routing and any
/// later mouse fallback both go through here.
enum InterjectSuggestionFeedbackMutation {
  static func record(
    evaluationID: UUID,
    suggestionID: UUID,
    verb: InterjectFeedbackVerb,
    recordedAt: Date = Date(),
    store: InterjectSuggestionFeedbackStore = .shared
  ) async {
    await store.record(
      InterjectFeedbackRecord(
        evaluationID: evaluationID,
        suggestionID: suggestionID,
        verb: verb,
        recordedAt: recordedAt
      )
    )
  }
}
