import Foundation
import ImageIO

/// Closed, privacy-safe funnel telemetry for live suggestions.
///
/// These payload builders intentionally accept no prompt, suggestion, memory,
/// screenshot, app/window, title, or error values. The only correlators are
/// per-evaluation opaque UUIDs; all remaining dimensions are finite buckets or
/// counts bounded by the production grounding limits.
enum SuggestionAssistantTelemetry {
  static let settingChangedEventName = "Suggestion Assistant Setting Changed"
  static let gateOutcomeEventName = "Suggestion Assistant Gate Outcome"
  static let evaluationStartedEventName = "Suggestion Assistant Evaluation Started"
  static let evaluationCompletedEventName = "Suggestion Assistant Evaluation Completed"
  static let evaluationFailedEventName = "Suggestion Assistant Evaluation Failed"
  static let deliveryOutcomeEventName = "Suggestion Assistant Delivery Outcome"

  enum Setting: String, CaseIterable, Sendable {
    case enabled
  }

  enum GateOutcome: String, CaseIterable, Sendable {
    case eligible
    case disabled
    case excludedApp = "excluded_app"
    case dwell
    case cooldown
    case dailyBudget = "daily_budget"
    case noGrounding = "no_grounding"

    init(_ decision: SuggestionGateDecision) {
      switch decision {
      case .evaluate: self = .eligible
      case .skippedDisabled: self = .disabled
      case .skippedExcludedApp: self = .excludedApp
      case .skippedDwell: self = .dwell
      case .skippedCooldown: self = .cooldown
      case .skippedDailyBudget: self = .dailyBudget
      case .skippedNoGrounding: self = .noGrounding
      }
    }
  }

  enum Model: String, CaseIterable, Sendable {
    case gemini25FlashLite = "gemini_2_5_flash_lite"
    case gemini25Flash = "gemini_2_5_flash"
    case other

    init(configuredModel: String) {
      switch configuredModel {
      case "gemini-2.5-flash-lite": self = .gemini25FlashLite
      case "gemini-2.5-flash": self = .gemini25Flash
      default: self = .other
      }
    }
  }

  enum ImageWidthBucket: String, CaseIterable, Sendable {
    case undecodable
    case upTo768 = "0_768"
    case from769To1280 = "769_1280"
    case over1280 = "1281_plus"
  }

  enum ImageBytesBucket: String, CaseIterable, Sendable {
    case upTo256KB = "0_256kb"
    case from257KBTo1MB = "257kb_1mb"
    case from1MBTo4MB = "1mb_4mb"
    case over4MB = "4mb_plus"
  }

  enum LatencyBucket: String, CaseIterable, Sendable {
    case upTo1Second = "0_1s"
    case from1To3Seconds = "1_3s"
    case from3To10Seconds = "3_10s"
    case from10To30Seconds = "10_30s"
    case from30To120Seconds = "30_120s"
    case over120Seconds = "120s_plus"
  }

  /// Closed failure class for `Suggestion Assistant Evaluation Failed`.
  /// Raw error strings, URLs, and user content are never accepted.
  enum EvaluationFailureReason: String, CaseIterable, Sendable {
    case network
    case httpStatus4xx = "http_status_4xx"
    case httpStatus5xx = "http_status_5xx"
    case rateLimited = "rate_limited"
    case decodeFailed = "decode_failed"
    case timeout
    case cancelled
    case other

    init(_ error: Error) {
      self = Self.classify(error)
    }

    private static func classify(_ error: Error) -> EvaluationFailureReason {
      if error is CancellationError { return .cancelled }
      if error is DecodingError { return .decodeFailed }
      if let urlError = error as? URLError {
        switch urlError.code {
        case .timedOut: return .timeout
        case .cancelled: return .cancelled
        default: return .network
        }
      }
      if let geminiError = error as? GeminiClient.GeminiClientError {
        switch geminiError {
        case .networkError(let underlying):
          return classify(underlying)
        case .invalidResponse:
          return .decodeFailed
        case .apiError(let message, _):
          return classifyAPIMessage(message)
        case .missingAPIKey:
          return .other
        }
      }
      let nsError = error as NSError
      if nsError.domain == NSURLErrorDomain {
        switch nsError.code {
        case NSURLErrorTimedOut: return .timeout
        case NSURLErrorCancelled: return .cancelled
        default: return .network
        }
      }
      let typeName = String(describing: type(of: error))
      if typeName.contains("SuggestionEvaluationError") { return .decodeFailed }
      return .other
    }

    private static func classifyAPIMessage(_ message: String) -> EvaluationFailureReason {
      if let status = httpStatus(from: message) {
        if status == 429 { return .rateLimited }
        if (400..<500).contains(status) { return .httpStatus4xx }
        if (500..<600).contains(status) { return .httpStatus5xx }
      }
      let lower = message.lowercased()
      if lower.contains("rate limit") || lower.contains("resource exhausted") || lower.contains("quota") {
        return .rateLimited
      }
      if lower.contains("timeout") || lower.contains("timed out") { return .timeout }
      return .other
    }

    private static func httpStatus(from message: String) -> Int? {
      let prefix = "HTTP "
      guard message.hasPrefix(prefix) else { return nil }
      let digits = message.dropFirst(prefix.count).prefix(while: \.isNumber)
      return Int(digits)
    }
  }

  /// Terminal state after a decoded model yield asks to interrupt the user.
  /// `delivered` is emitted only after the floating bar presents the card;
  /// the existing `Notification Sent` event shares the same presentation point.
  enum DeliveryOutcome: String, CaseIterable, Sendable {
    case delivered
    case filteredLowConfidence = "filtered_low_confidence"
    case filteredDuplicate = "filtered_duplicate"
    /// A commitment nudge that named work absent from the grounding it was given.
    case filteredUngroundedCommitment = "filtered_ungrounded_commitment"
    case rejectedOwner = "rejected_owner"
    /// Withheld because the user is presenting. Distinct from the `filtered_*` outcomes:
    /// those retire a suggestion on its merits, this one defers an otherwise-deliverable
    /// suggestion on audience, and deliberately leaves it eligible to deliver later.
    case suppressedPresenting = "suppressed_presenting"
    /// Withheld because the user silenced notifications for a period. Like
    /// `suppressed_presenting` this defers rather than retires: the suggestion is not
    /// written to the dedup window, so it can still be delivered once the snooze lapses.
    case suppressedSnoozed = "suppressed_snoozed"
  }

  /// One evaluation produces at most one suggestion. Separate UUIDs preserve
  /// a future one-to-many evolution without tying either identifier to content.
  struct Identity: Equatable, Sendable {
    let evaluationID: UUID
    let suggestionID: UUID?

    init(evaluationID: UUID = UUID(), suggestionID: UUID? = nil) {
      self.evaluationID = evaluationID
      self.suggestionID = suggestionID
    }

    func withSuggestion() -> Identity {
      Identity(evaluationID: evaluationID, suggestionID: UUID())
    }
  }

  /// The only metadata a suggestion is allowed to add to existing notification
  /// events. It deliberately cannot hold a title/message/context string.
  struct NotificationIdentity: Equatable, Sendable {
    let evaluationID: UUID
    let suggestionID: UUID

    init(evaluationID: UUID, suggestionID: UUID) {
      self.evaluationID = evaluationID
      self.suggestionID = suggestionID
    }

    init?(_ identity: Identity?) {
      guard let identity, let suggestionID = identity.suggestionID else { return nil }
      self.init(evaluationID: identity.evaluationID, suggestionID: suggestionID)
    }
  }

  struct EvaluationShape: Equatable, Sendable {
    let model: Model
    let imageWidthBucket: ImageWidthBucket
    let imageBytesBucket: ImageBytesBucket
    let memoryCount: Int
    let commitmentCount: Int
    let relatedScreenCount: Int
    let goalCount: Int

    init(model: Model, previewData: Data, grounding: SuggestionGrounding) {
      self.model = model
      imageWidthBucket = Self.imageWidthBucket(for: previewData)
      imageBytesBucket = Self.imageBytesBucket(for: previewData)
      // The source queries cap these at 15 memories, 25 commitments, 12 screens,
      // and 4 active goals. Keep an explicit ceiling here as defense-in-depth if a
      // source changes before the telemetry contract does.
      memoryCount = min(max(grounding.memories.count, 0), 15)
      commitmentCount = min(max(grounding.openCommitments.count, 0), 25)
      relatedScreenCount = min(max(grounding.relatedScreens.count, 0), 12)
      // Goals count toward `SuggestionGrounding.isEmpty`, so a goal-only grounding can be
      // the sole reason an evaluation is paid for. Leaving it out of the shape would report
      // grounding_source_count=0 for a spend that did happen.
      goalCount = min(max(grounding.goals.count, 0), 8)
    }

    private static func imageWidthBucket(for data: Data) -> ImageWidthBucket {
      guard let source = CGImageSourceCreateWithData(data as CFData, nil),
        let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
        let width = properties[kCGImagePropertyPixelWidth] as? Int
      else { return .undecodable }

      switch width {
      case ...768: return .upTo768
      case ...1280: return .from769To1280
      default: return .over1280
      }
    }

    private static func imageBytesBucket(for data: Data) -> ImageBytesBucket {
      switch data.count {
      case ...(256 * 1024): return .upTo256KB
      case ...(1024 * 1024): return .from257KBTo1MB
      case ...(4 * 1024 * 1024): return .from1MBTo4MB
      default: return .over4MB
      }
    }
  }

  static func settingChangeIsPersistedChange(oldValue: Bool, newValue: Bool) -> Bool {
    oldValue != newValue
  }

  static func settingChangedPayload(setting: Setting, value: Bool) -> [String: Any] {
    ["setting": setting.rawValue, "value": value]
  }

  static func gateOutcomePayload(_ outcome: GateOutcome) -> [String: Any] {
    ["outcome": outcome.rawValue]
  }

  static func evaluationStartedPayload(identity: Identity, shape: EvaluationShape) -> [String: Any] {
    evaluationPayload(identity: identity, shape: shape)
  }

  static func evaluationCompletedPayload(
    identity: Identity,
    shape: EvaluationShape,
    latency: TimeInterval,
    producedSuggestion: Bool
  ) -> [String: Any] {
    var payload = evaluationPayload(identity: identity, shape: shape)
    payload["latency_bucket"] = latencyBucket(latency).rawValue
    payload["produced_suggestion"] = producedSuggestion
    if let suggestionID = identity.suggestionID {
      payload["suggestion_id"] = suggestionID.uuidString
    }
    return payload
  }

  static func evaluationFailedPayload(
    identity: Identity,
    shape: EvaluationShape,
    latency: TimeInterval,
    reason: EvaluationFailureReason
  ) -> [String: Any] {
    var payload = evaluationPayload(identity: identity, shape: shape)
    payload["latency_bucket"] = latencyBucket(latency).rawValue
    payload["reason"] = reason.rawValue
    return payload
  }

  static func notificationPayload(_ identity: NotificationIdentity) -> [String: Any] {
    [
      "evaluation_id": identity.evaluationID.uuidString,
      "suggestion_id": identity.suggestionID.uuidString,
    ]
  }

  static func deliveryOutcomePayload(
    _ outcome: DeliveryOutcome,
    identity: NotificationIdentity
  ) -> [String: Any] {
    var payload = notificationPayload(identity)
    payload["outcome"] = outcome.rawValue
    return payload
  }

  static func latencyBucket(_ latency: TimeInterval) -> LatencyBucket {
    switch max(latency, 0) {
    case ..<1: return .upTo1Second
    case ..<3: return .from1To3Seconds
    case ..<10: return .from3To10Seconds
    case ..<30: return .from10To30Seconds
    case ..<120: return .from30To120Seconds
    default: return .over120Seconds
    }
  }

  private static func evaluationPayload(identity: Identity, shape: EvaluationShape) -> [String: Any] {
    let sourceCount = [
      shape.memoryCount, shape.commitmentCount, shape.relatedScreenCount, shape.goalCount,
    ]
    .filter { $0 > 0 }
    .count
    return [
      "evaluation_id": identity.evaluationID.uuidString,
      "model": shape.model.rawValue,
      "image_width_bucket": shape.imageWidthBucket.rawValue,
      "image_bytes_bucket": shape.imageBytesBucket.rawValue,
      "grounding_source_count": sourceCount,
      "memory_count": shape.memoryCount,
      "has_memories": shape.memoryCount > 0,
      "commitment_count": shape.commitmentCount,
      "has_commitments": shape.commitmentCount > 0,
      "related_screen_count": shape.relatedScreenCount,
      "has_related_screens": shape.relatedScreenCount > 0,
      "goal_count": shape.goalCount,
      "has_goals": shape.goalCount > 0,
    ]
  }
}
