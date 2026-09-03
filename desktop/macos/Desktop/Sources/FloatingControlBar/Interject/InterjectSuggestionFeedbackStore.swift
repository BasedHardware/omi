import Foundation

enum InterjectFeedbackVerb: String, Codable, CaseIterable, Sendable {
  case useful
  case falsePositive = "false_positive"
  case snooze
  case disable
  case missed
  case correction
  case riff

  /// Decision 24 teach-rate verbs plus correction. `riff` is ordinary
  /// continuation — parse it so the token can be stripped, do not tally it.
  var recordsAsTeachSignal: Bool { self != .riff }
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

/// The only write entry point other surfaces may call. Voice, typed follow-up,
/// and JIT verdict buttons all go through here; analytics is a side effect of
/// this write, not a second tally.
enum InterjectSuggestionFeedbackMutation {
  static func record(
    evaluationID: UUID,
    suggestionID: UUID,
    verb: InterjectFeedbackVerb,
    recordedAt: Date = Date(),
    store: InterjectSuggestionFeedbackStore = .shared,
    emitAnalytics: Bool = true
  ) async {
    guard verb.recordsAsTeachSignal else { return }
    let identity = SuggestionAssistantTelemetry.NotificationIdentity(
      evaluationID: evaluationID, suggestionID: suggestionID)
    if emitAnalytics {
      await MainActor.run {
        AnalyticsManager.shared.suggestionFeedbackRecorded(
          verb: verb.rawValue, suggestionIdentity: identity)
      }
    }
    await store.record(
      InterjectFeedbackRecord(
        evaluationID: evaluationID,
        suggestionID: suggestionID,
        verb: verb,
        recordedAt: recordedAt
      )
    )
  }

  /// Journaled proactive-card thumbs-down. Analytics is a side effect of this
  /// write, not a second tally. Identity prefers the stored notification pair
  /// and falls back to the continuity UUID.
  static func recordFromChatRating(
    continuityKey: String?,
    reason: String?,
    store: InterjectSuggestionFeedbackStore = .shared
  ) async {
    guard let continuityKey else { return }
    let verb = ChatRatingReason(rawValue: reason ?? "")?.interjectVerb() ?? .falsePositive
    let resolved = await MainActor.run {
      FloatingControlBarManager.shared.feedbackIdentity(
        forContinuityKey: continuityKey)
    }
    let identity =
      resolved
      ?? ChatContinuityInvariants.notificationID(fromContinuityKey: continuityKey).map {
        SuggestionAssistantTelemetry.NotificationIdentity(evaluationID: $0, suggestionID: $0)
      }
    guard let identity else { return }
    await record(
      evaluationID: identity.evaluationID,
      suggestionID: identity.suggestionID,
      verb: verb,
      store: store
    )
    await MainActor.run {
      SuggestionTaskNudgeEngagement.record(fromContinuityKey: continuityKey)
    }
  }
}
