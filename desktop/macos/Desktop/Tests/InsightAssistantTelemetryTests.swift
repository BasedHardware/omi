import Foundation
import XCTest

@testable import Omi_Computer

final class InsightAssistantTelemetryTests: XCTestCase {
  func testDeliveryPayloadIsClosedAndContainsNoAdviceMaterial() throws {
    let deliveryID = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000101"))
    let identity = InsightAssistantTelemetry.DeliveryIdentity(deliveryID: deliveryID)
    let payload = InsightAssistantTelemetry.deliveryOutcomePayload(
      .delivered,
      reason: .floatingBarPresented,
      identity: identity,
      surface: .floatingBar
    )

    XCTAssertEqual(
      Set(payload.keys),
      Set(["assistant_id", "delivery_id", "outcome", "reason", "notification_surface"])
    )
    XCTAssertEqual(payload["assistant_id"] as? String, "insight")
    XCTAssertEqual(payload["delivery_id"] as? String, deliveryID.uuidString)
    XCTAssertEqual(payload["outcome"] as? String, "delivered")
    XCTAssertEqual(payload["reason"] as? String, "floating_bar_presented")
    XCTAssertFalse(String(describing: payload).contains("private advice"))

    let suppressed = InsightAssistantTelemetry.deliveryOutcomePayload(
      .suppressed,
      reason: .assistantNotificationsDisabled,
      identity: identity,
      surface: .systemNotification
    )
    XCTAssertEqual(
      Set(suppressed.keys),
      Set(["assistant_id", "delivery_id", "outcome", "reason"])
    )
    XCTAssertNil(suppressed["notification_surface"])
  }

  func testReasonsAndOutcomesAreClosed() {
    XCTAssertEqual(
      Set(InsightAssistantTelemetry.Outcome.allCases.map(\.rawValue)),
      Set(["delivered", "suppressed", "failed"])
    )
    XCTAssertTrue(InsightAssistantTelemetry.Reason.allCases.allSatisfy { !$0.rawValue.isEmpty })
    XCTAssertEqual(
      Set(InsightAssistantTelemetry.Surface.allCases.map(\.rawValue)),
      Set(["floating_bar", "system_notification"])
    )
    XCTAssertEqual(InsightAssistantTelemetry.boundedCategory("unexpected"), "other")
    XCTAssertEqual(InsightAssistantTelemetry.boundedCategory("productivity"), "productivity")
  }

  func testFloatingNotificationCarriesOpaqueDeliveryIdentityToPresentationBoundary() {
    let deliveryID = UUID()
    let notification = FloatingBarNotification(
      ownerID: "owner",
      title: "title",
      message: "message",
      assistantId: "insight",
      kind: .insight,
      insightDeliveryID: deliveryID
    )

    XCTAssertEqual(notification.insightDeliveryID, deliveryID)
  }
}

@MainActor
final class InsightAssistantTelemetryBoundaryTests: XCTestCase {
  private var captured: [(name: String, properties: [String: Any])] = []
  private var savedInsightEnabled = true
  private var savedNotificationsEnabled = true

  override func setUp() async throws {
    savedInsightEnabled = InsightAssistantSettings.shared.isEnabled
    savedNotificationsEnabled = InsightAssistantSettings.shared.notificationsEnabled
    captured = []
    AnalyticsManager.shared.setInsightAssistantTelemetryCaptureForTests { [weak self] name, properties in
      self?.captured.append((name, properties))
    }
  }

  override func tearDown() async throws {
    InsightAssistantSettings.shared.isEnabled = savedInsightEnabled
    InsightAssistantSettings.shared.notificationsEnabled = savedNotificationsEnabled
    AnalyticsManager.shared.setInsightAssistantTelemetryCaptureForTests(nil)
  }

  func testAnalysisEligibilityDoesNotDependOnNotificationDeliveryToggle() async throws {
    InsightAssistantSettings.shared.isEnabled = true
    InsightAssistantSettings.shared.notificationsEnabled = false
    let assistant = try InsightAssistant(apiKey: "test-key")
    let analysisEnabled = await assistant.isEnabled
    await assistant.stop()
    XCTAssertTrue(analysisEnabled)
  }

  func testDeliveredAndSuppressedOutcomesEmitExactlyOneTerminalEvent() throws {
    let deliveredID = UUID()
    let suppressedID = UUID()
    AnalyticsManager.shared.insightGenerated(category: "productivity", deliveryID: deliveredID)
    AnalyticsManager.shared.insightAssistantDeliveryOutcome(
      .delivered,
      reason: .floatingBarPresented,
      deliveryID: deliveredID,
      surface: .floatingBar
    )
    // A second callback for the same generated advice must be ignored.
    AnalyticsManager.shared.insightAssistantDeliveryOutcome(
      .failed,
      reason: .staleOwner,
      deliveryID: deliveredID
    )
    AnalyticsManager.shared.insightAssistantDeliveryOutcome(
      .suppressed,
      reason: .assistantNotificationsDisabled,
      deliveryID: suppressedID
    )

    XCTAssertEqual(captured.count, 3)
    XCTAssertEqual(captured[0].name, "Advice Generated")
    XCTAssertEqual(captured[0].properties["delivery_id"] as? String, deliveredID.uuidString)
    XCTAssertEqual(captured[0].properties["category"] as? String, "productivity")
    XCTAssertEqual(captured[1].name, InsightAssistantTelemetry.deliveryOutcomeEventName)
    XCTAssertEqual(captured[2].name, InsightAssistantTelemetry.deliveryOutcomeEventName)
    XCTAssertEqual(captured[1].properties["outcome"] as? String, "delivered")
    XCTAssertEqual(captured[2].properties["outcome"] as? String, "suppressed")
    XCTAssertEqual(captured[1].properties["assistant_id"] as? String, "insight")
    XCTAssertEqual(captured[2].properties["assistant_id"] as? String, "insight")
    XCTAssertEqual(captured[1].properties["notification_surface"] as? String, "floating_bar")
    XCTAssertNil(captured[2].properties["notification_surface"])
  }
}
