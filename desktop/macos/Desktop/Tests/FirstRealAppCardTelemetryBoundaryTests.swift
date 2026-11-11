import XCTest

@testable import Omi_Computer

/// `AnalyticsManager.firstRealAppCard` is the only place this event is
/// constructed. The card's copy names the frontmost application, so the risk
/// here is not a wrong number — it is an app name reaching PostHog. This drives
/// the real emitter through its scoped capture seam and asserts the payload is
/// nothing but a bounded phase, mirroring `NotificationDeliveryTelemetryBoundaryTests`.
@MainActor
final class FirstRealAppCardTelemetryBoundaryTests: XCTestCase {
  private var captured: [(String, [String: Any])] = []

  private func startCapturing() {
    captured = []
    FirstRealAppCardTelemetry.captureForTests = { [weak self] event, properties in
      self?.captured.append((event, properties))
    }
    addTeardownBlock {
      await MainActor.run { FirstRealAppCardTelemetry.captureForTests = nil }
    }
  }

  func testEachPhaseEmitsTheOneEventNameAndItsPhase() throws {
    startCapturing()

    for phase in FirstRealAppCardTelemetry.Phase.allCases {
      AnalyticsManager.shared.firstRealAppCard(phase: phase)
    }

    XCTAssertEqual(captured.count, FirstRealAppCardTelemetry.Phase.allCases.count)
    XCTAssertEqual(Set(captured.map(\.0)), ["first_real_app_card"])
    XCTAssertEqual(
      captured.compactMap { $0.1["phase"] as? String },
      ["shown", "tapped", "ptt_after_card", "dismissed", "timed_out"]
    )
  }

  /// Nothing an emitter passes may escape the allow-list — never an app name,
  /// a card title, a bundle identifier, or a window title.
  func testEveryEmittedKeyIsOnTheAllowList() throws {
    startCapturing()

    for phase in FirstRealAppCardTelemetry.Phase.allCases {
      AnalyticsManager.shared.firstRealAppCard(phase: phase)
    }

    XCTAssertFalse(captured.isEmpty)
    for event in captured {
      for key in event.1.keys {
        XCTAssertTrue(
          FirstRealAppCardTelemetry.allowedKeys.contains(key),
          "\(key) is not an allowed dimension of \(FirstRealAppCardTelemetry.eventName)")
      }
    }
  }
}
