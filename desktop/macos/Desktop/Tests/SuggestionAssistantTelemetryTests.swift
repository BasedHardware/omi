import Foundation
import XCTest

@testable import Omi_Computer

/// Contract tests for the live-suggestion funnel. The builders accept only
/// opaque IDs plus bounded buckets/counts, so raw suggestion/context/model
/// material cannot become a PostHog property by construction.
final class SuggestionAssistantTelemetryTests: XCTestCase {
  private func shape() -> SuggestionAssistantTelemetry.EvaluationShape {
    SuggestionAssistantTelemetry.EvaluationShape(
      model: .gemini25FlashLite,
      previewData: Data([0x00, 0x01, 0x02]),
      grounding: SuggestionGrounding(
        memories: ["memory content must never leave the device"],
        commitmentRecords: [SuggestionCommitment(id: "c1", text: "private commitment")],
        relatedScreens: ["screen text"]
      )
    )
  }

  func testSettingAndGateSchemasAreClosed() {
    XCTAssertEqual(Set(SuggestionAssistantTelemetry.Setting.allCases.map(\.rawValue)), Set(["enabled"]))
    XCTAssertEqual(
      Set(SuggestionAssistantTelemetry.GateOutcome.allCases.map(\.rawValue)),
      Set([
        "eligible", "disabled", "excluded_app", "dwell",
        "cooldown", "daily_budget", "no_grounding",
      ])
    )
    XCTAssertEqual(
      Set(SuggestionAssistantTelemetry.settingChangedPayload(setting: .enabled, value: true).keys),
      Set(["setting", "value"])
    )
    XCTAssertEqual(
      SuggestionAssistantTelemetry.settingChangedPayload(setting: .enabled, value: true)["value"] as? Bool,
      true
    )
    XCTAssertEqual(
      SuggestionAssistantTelemetry.settingChangedPayload(setting: .enabled, value: true)["setting"] as? String,
      "enabled"
    )
    XCTAssertEqual(
      SuggestionAssistantTelemetry.gateOutcomePayload(.excludedApp) as? [String: String],
      ["outcome": "excluded_app"]
    )
  }

  func testEvaluationPayloadUsesOnlyClosedCostAndGroundingShape() throws {
    let identity = SuggestionAssistantTelemetry.Identity(
      evaluationID: try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000001"))
    )
    let payload = SuggestionAssistantTelemetry.evaluationStartedPayload(identity: identity, shape: shape())

    XCTAssertEqual(
      Set(payload.keys),
      Set([
        "evaluation_id", "model", "image_width_bucket", "image_bytes_bucket", "grounding_source_count",
        "memory_count", "has_memories", "commitment_count", "has_commitments", "related_screen_count",
        "has_related_screens", "goal_count", "has_goals",
      ])
    )
    XCTAssertEqual(payload["evaluation_id"] as? String, "00000000-0000-0000-0000-000000000001")
    XCTAssertEqual(payload["model"] as? String, "gemini_2_5_flash_lite")
    XCTAssertEqual(payload["image_width_bucket"] as? String, "undecodable")
    XCTAssertEqual(payload["image_bytes_bucket"] as? String, "0_256kb")
    XCTAssertEqual(payload["grounding_source_count"] as? Int, 3)
    XCTAssertEqual(payload["memory_count"] as? Int, 1)
    XCTAssertEqual(payload["commitment_count"] as? Int, 1)
    XCTAssertEqual(payload["related_screen_count"] as? Int, 1)
    XCTAssertEqual(payload["goal_count"] as? Int, 0)
    XCTAssertEqual(payload["has_goals"] as? Bool, false)

    let serialized = try XCTUnwrap(
      String(
        data: try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
        encoding: .utf8
      )
    )
    XCTAssertFalse(serialized.contains("memory content"))
    XCTAssertFalse(serialized.contains("private commitment"))
    XCTAssertFalse(serialized.contains("screen text"))
    XCTAssertFalse(serialized.contains("0x00"))
  }

  func testTerminalPayloadsJoinOnOpaqueIDsAndUseLatencyBuckets() throws {
    let evaluationID = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000002"))
    let identity = SuggestionAssistantTelemetry.Identity(evaluationID: evaluationID).withSuggestion()
    let completed = SuggestionAssistantTelemetry.evaluationCompletedPayload(
      identity: identity,
      shape: shape(),
      latency: 3.2,
      producedSuggestion: true
    )
    let failed = SuggestionAssistantTelemetry.evaluationFailedPayload(
      identity: identity,
      shape: shape(),
      latency: 125,
      reason: .timeout
    )

    XCTAssertEqual(completed["evaluation_id"] as? String, evaluationID.uuidString)
    XCTAssertEqual(completed["suggestion_id"] as? String, identity.suggestionID?.uuidString)
    XCTAssertEqual(completed["latency_bucket"] as? String, "3_10s")
    XCTAssertEqual(completed["produced_suggestion"] as? Bool, true)
    XCTAssertEqual(failed["evaluation_id"] as? String, evaluationID.uuidString)
    XCTAssertEqual(failed["latency_bucket"] as? String, "120s_plus")
    XCTAssertEqual(failed["reason"] as? String, "timeout")
    XCTAssertNil(failed["suggestion_id"])
    XCTAssertNil(failed["produced_suggestion"])
  }

  func testEvaluationFailureReasonsAreClosedAndNeverCarryRawErrorMaterial() {
    XCTAssertEqual(
      Set(SuggestionAssistantTelemetry.EvaluationFailureReason.allCases.map(\.rawValue)),
      Set([
        "network", "http_status_4xx", "http_status_5xx", "rate_limited",
        "decode_failed", "timeout", "cancelled", "other",
      ])
    )

    let classified: [(Error, SuggestionAssistantTelemetry.EvaluationFailureReason)] = [
      (CancellationError(), .cancelled),
      (URLError(.timedOut), .timeout),
      (URLError(.notConnectedToInternet), .network),
      (URLError(.cancelled), .cancelled),
      (DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "secret payload")), .decodeFailed),
      (GeminiClient.GeminiClientError.invalidResponse, .decodeFailed),
      (GeminiClient.GeminiClientError.apiError("HTTP 429: quota-key-xyz", retryable: true), .rateLimited),
      (GeminiClient.GeminiClientError.apiError("HTTP 503: upstream body", retryable: true), .httpStatus5xx),
      (GeminiClient.GeminiClientError.apiError("HTTP 400: prompt leaked", retryable: false), .httpStatus4xx),
      (GeminiClient.GeminiClientError.missingAPIKey, .other),
    ]
    for (error, expected) in classified {
      XCTAssertEqual(SuggestionAssistantTelemetry.EvaluationFailureReason(error), expected, String(describing: error))
    }

    let payload = SuggestionAssistantTelemetry.evaluationFailedPayload(
      identity: SuggestionAssistantTelemetry.Identity(),
      shape: shape(),
      latency: 1,
      reason: SuggestionAssistantTelemetry.EvaluationFailureReason(
        GeminiClient.GeminiClientError.apiError("HTTP 429: user@example.com leaked", retryable: true)
      )
    )
    let serialized = String(describing: payload)
    XCTAssertEqual(payload["reason"] as? String, "rate_limited")
    XCTAssertFalse(serialized.contains("user@example.com"))
    XCTAssertFalse(serialized.contains("leaked"))
    XCTAssertFalse(serialized.contains("HTTP 429"))
  }

  func testNotificationDismissalKindIsClosed() {
    XCTAssertEqual(
      Set(NotificationDismissalKind.allCases.map(\.rawValue)),
      Set(["user", "timeout", "replaced"])
    )
  }

  func testNotificationIdentityCarriesOnlyEvaluationAndSuggestionJoinKeys() throws {
    let identity = SuggestionAssistantTelemetry.Identity(
      evaluationID: try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000003"))
    ).withSuggestion()
    let notificationIdentity = try XCTUnwrap(SuggestionAssistantTelemetry.NotificationIdentity(identity))
    let payload = SuggestionAssistantTelemetry.notificationPayload(notificationIdentity)

    XCTAssertEqual(Set(payload.keys), Set(["evaluation_id", "suggestion_id"]))
    XCTAssertEqual(payload["evaluation_id"] as? String, identity.evaluationID.uuidString)
    XCTAssertEqual(payload["suggestion_id"] as? String, identity.suggestionID?.uuidString)
  }

  func testDeliveryOutcomesAreClosedAndJoinWithoutCardContent() throws {
    let identity = SuggestionAssistantTelemetry.Identity().withSuggestion()
    let notificationIdentity = try XCTUnwrap(SuggestionAssistantTelemetry.NotificationIdentity(identity))
    XCTAssertEqual(
      Set(SuggestionAssistantTelemetry.DeliveryOutcome.allCases.map(\.rawValue)),
      Set([
        "delivered", "filtered_low_confidence", "filtered_duplicate",
        "filtered_ungrounded_commitment", "rejected_owner",
        // Deferrals, not filters: the suggestion was deliverable and was withheld on
        // audience or on the user's explicit silence, and is left eligible afterwards.
        // Extending the closed set here is the review this guard exists to force — a
        // sixth outcome added without touching this line still fails.
        "suppressed_presenting", "suppressed_snoozed",
      ])
    )

    let payload = SuggestionAssistantTelemetry.deliveryOutcomePayload(
      .filteredLowConfidence,
      identity: notificationIdentity
    )
    XCTAssertEqual(Set(payload.keys), Set(["evaluation_id", "suggestion_id", "outcome"]))
    XCTAssertEqual(payload["outcome"] as? String, "filtered_low_confidence")
    XCTAssertFalse(String(describing: payload).contains("private commitment"))
  }

  func testLatencyBucketsAreFiniteAtBoundaries() {
    XCTAssertEqual(SuggestionAssistantTelemetry.latencyBucket(-1), .upTo1Second)
    XCTAssertEqual(SuggestionAssistantTelemetry.latencyBucket(0.999), .upTo1Second)
    XCTAssertEqual(SuggestionAssistantTelemetry.latencyBucket(1), .from1To3Seconds)
    XCTAssertEqual(SuggestionAssistantTelemetry.latencyBucket(3), .from3To10Seconds)
    XCTAssertEqual(SuggestionAssistantTelemetry.latencyBucket(10), .from10To30Seconds)
    XCTAssertEqual(SuggestionAssistantTelemetry.latencyBucket(30), .from30To120Seconds)
    XCTAssertEqual(SuggestionAssistantTelemetry.latencyBucket(120), .over120Seconds)
  }
}

@MainActor
final class SuggestionAssistantTelemetryBoundaryTests: XCTestCase {
  private var savedEnabled = false
  private var captured: [(name: String, properties: [String: Any])] = []

  override func setUp() async throws {
    savedEnabled = SuggestionAssistantSettings.shared.isEnabled
    SuggestionAssistantSettings.shared.isEnabled = false
    captured = []
    AnalyticsManager.shared.setSuggestionAssistantTelemetryCaptureForTests { [weak self] name, properties in
      self?.captured.append((name, properties))
    }
  }

  override func tearDown() async throws {
    SuggestionAssistantSettings.shared.isEnabled = savedEnabled
    AnalyticsManager.shared.setSuggestionAssistantTelemetryCaptureForTests(nil)
    captured = []
  }

  func testUserSettingChangeEmitsOnceAndNoOpIsSilent() {
    XCTAssertFalse(SuggestionAssistantSettings.shared.applyUserEnabledChange(false))
    XCTAssertTrue(SuggestionAssistantSettings.shared.applyUserEnabledChange(true))
    XCTAssertFalse(SuggestionAssistantSettings.shared.applyUserEnabledChange(true))

    XCTAssertEqual(captured.count, 1)
    XCTAssertEqual(captured[0].name, SuggestionAssistantTelemetry.settingChangedEventName)
    XCTAssertEqual(captured[0].properties["setting"] as? String, "enabled")
    XCTAssertEqual(captured[0].properties["value"] as? Bool, true)
    XCTAssertEqual(Set(captured[0].properties.keys), Set(["setting", "value"]))
  }

  func testEvaluationAndNotificationEventsPreserveTheSameOpaqueJoinKeys() throws {
    let identity = SuggestionAssistantTelemetry.Identity().withSuggestion()
    let shape = SuggestionAssistantTelemetry.EvaluationShape(
      model: .gemini25Flash,
      previewData: Data([0x00]),
      grounding: SuggestionGrounding(memories: ["never sent"])
    )
    AnalyticsManager.shared.suggestionAssistantEvaluationStarted(identity: identity, shape: shape)
    AnalyticsManager.shared.suggestionAssistantEvaluationCompleted(
      identity: identity,
      shape: shape,
      latency: 1.5,
      producedSuggestion: true
    )
    AnalyticsManager.shared.notificationSent(
      notificationId: UUID().uuidString,
      title: "Suggestion",
      assistantId: "suggestion",
      surface: "floating_bar",
      suggestionIdentity: try XCTUnwrap(SuggestionAssistantTelemetry.NotificationIdentity(identity))
    )

    XCTAssertEqual(
      captured.map(\.name),
      [
        SuggestionAssistantTelemetry.evaluationStartedEventName,
        SuggestionAssistantTelemetry.evaluationCompletedEventName,
        "Notification Sent",
      ])
    let expectedEvaluationID = identity.evaluationID.uuidString
    let expectedSuggestionID = identity.suggestionID?.uuidString
    XCTAssertEqual(captured[0].properties["evaluation_id"] as? String, expectedEvaluationID)
    XCTAssertEqual(captured[1].properties["evaluation_id"] as? String, expectedEvaluationID)
    XCTAssertEqual(captured[1].properties["suggestion_id"] as? String, expectedSuggestionID)
    XCTAssertEqual(
      captured[2].properties as? [String: String],
      [
        "evaluation_id": expectedEvaluationID,
        "suggestion_id": expectedSuggestionID ?? "",
      ])
  }

  /// Goals participate in `SuggestionGrounding.isEmpty`, so a goal-only grounding is a real
  /// reason to pay for an evaluation. If the shape ignored goals this spend would report
  /// `grounding_source_count = 0`, which is the analytics-integrity failure of describing a
  /// paid call as having had no inputs.
  func testGoalOnlyGroundingIsCountedAsASpentSource() throws {
    let goalOnly = SuggestionGrounding(
      memories: [],
      commitmentRecords: [],
      relatedScreens: [],
      goals: ["Reach 200k total users by month-end"]
    )
    XCTAssertFalse(goalOnly.isEmpty, "a goal alone must be able to justify an evaluation")

    let payload = SuggestionAssistantTelemetry.evaluationStartedPayload(
      identity: SuggestionAssistantTelemetry.Identity(),
      shape: SuggestionAssistantTelemetry.EvaluationShape(
        model: .gemini25FlashLite,
        previewData: Data([0x00, 0x01, 0x02]),
        grounding: goalOnly
      )
    )

    XCTAssertEqual(payload["grounding_source_count"] as? Int, 1)
    XCTAssertEqual(payload["goal_count"] as? Int, 1)
    XCTAssertEqual(payload["has_goals"] as? Bool, true)
    XCTAssertEqual(payload["has_commitments"] as? Bool, false)

    // The goal's text is never a property; only its bounded count.
    let serialized = try XCTUnwrap(
      String(data: try JSONSerialization.data(withJSONObject: payload), encoding: .utf8))
    XCTAssertFalse(serialized.contains("200k"))
  }

  /// Counts are bounded so an unexpectedly large source cannot become a high-cardinality
  /// property.
  func testGoalCountIsBounded() {
    let shape = SuggestionAssistantTelemetry.EvaluationShape(
      model: .gemini25FlashLite,
      previewData: Data([0x00]),
      grounding: SuggestionGrounding(goals: Array(repeating: "goal", count: 500))
    )
    XCTAssertEqual(shape.goalCount, 8)
  }
}
