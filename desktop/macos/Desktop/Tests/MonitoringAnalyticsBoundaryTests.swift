import XCTest

@testable import Omi_Computer

/// Drives the real `AnalyticsManager` monitoring methods through the scoped
/// capture seam, mirroring `IntegrationNudgeAnalyticsBoundaryTests`: asserting
/// on the payload builders alone would not catch an emitter that forgets to
/// route through the allow-list filter, or that is wired to the wrong builder.
@MainActor
final class MonitoringAnalyticsBoundaryTests: XCTestCase {
  private let capturedBox = Box<[(String, [String: Any])]>([])

  private func startCapturing() {
    let box = capturedBox
    box.value = []
    AnalyticsManager.shared.setMonitoringTelemetryCaptureForTests { event, properties in
      box.value.append((event, properties))
    }
    addTeardownBlock {
      await MainActor.run {
        AnalyticsManager.shared.setMonitoringTelemetryCaptureForTests(nil)
      }
    }
  }

  func testStartedEmitsSessionID() {
    startCapturing()

    AnalyticsManager.shared.monitoringStarted(sessionID: "session-a")

    let event = capturedBox.value.first
    XCTAssertEqual(event?.0, MonitoringTelemetry.startedEventName)
    XCTAssertEqual(event?.1["session_id"] as? String, "session-a")
  }

  func testStoppedEmitsDurationFields() {
    startCapturing()

    let summary = MonitoringSummary(
      sessionID: "session-b",
      durationSeconds: 125.4,
      pausedSeconds: 5.2,
      activeSeconds: 120.2,
      stopReason: .signOut,
      durationSource: .wallClock
    )
    AnalyticsManager.shared.monitoringStopped(summary: summary)

    let event = capturedBox.value.first
    XCTAssertEqual(event?.0, MonitoringTelemetry.stoppedEventName)
    XCTAssertEqual(event?.1["session_id"] as? String, "session-b")
    XCTAssertEqual(event?.1["duration_seconds"] as? Int, 125)
    XCTAssertEqual(event?.1["paused_seconds"] as? Int, 5)
    XCTAssertEqual(event?.1["active_seconds"] as? Int, 120)
    XCTAssertEqual(event?.1["stop_reason"] as? String, "sign_out")
    XCTAssertEqual(event?.1["duration_source"] as? String, "wall_clock")
  }

  func testRecoveredEmitsRecoveredAfterSeconds() {
    startCapturing()

    let outcome = MonitoringSessionRecovery.Outcome(
      sessionID: "session-c",
      durationSeconds: 90,
      activeSeconds: 90,
      pausedSeconds: 0,
      stopReason: .sessionLost,
      durationSource: .recoveredHeartbeat,
      recoveredAfterSeconds: 45
    )
    AnalyticsManager.shared.monitoringSessionRecovered(outcome)

    let event = capturedBox.value.first
    XCTAssertEqual(event?.0, MonitoringTelemetry.stoppedEventName)
    XCTAssertEqual(event?.1["stop_reason"] as? String, "session_lost")
    XCTAssertEqual(event?.1["duration_source"] as? String, "recovered_heartbeat")
    XCTAssertEqual(event?.1["recovered_after_seconds"] as? Int, 45)
  }

  /// Nothing an emitter passes may escape the allow-list, whatever a future
  /// caller adds to a payload builder.
  func testEveryEmittedKeyIsOnTheAllowList() {
    startCapturing()

    AnalyticsManager.shared.monitoringStarted(sessionID: "session-d")
    AnalyticsManager.shared.monitoringStopped(
      summary: MonitoringSummary(
        sessionID: "session-d", durationSeconds: 60, pausedSeconds: 0,
        activeSeconds: 60, stopReason: .userToggle, durationSource: .wallClock))
    AnalyticsManager.shared.monitoringSessionRecovered(
      MonitoringSessionRecovery.Outcome(
        sessionID: "session-d", durationSeconds: 60, activeSeconds: 60,
        pausedSeconds: 0, stopReason: .sessionLost, durationSource: .recoveredHeartbeat,
        recoveredAfterSeconds: 30))

    XCTAssertEqual(capturedBox.value.count, 3)
    for event in capturedBox.value {
      for key in event.1.keys {
        XCTAssertTrue(
          MonitoringTelemetry.allowedKeys.contains(key),
          "'\(key)' escaped the allow-list in \(event.0)"
        )
      }
    }
  }

  final class Box<T>: @unchecked Sendable {
    var value: T
    init(_ value: T) { self.value = value }
  }
}
