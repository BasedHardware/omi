import XCTest

@testable import Omi_Computer

/// Locks in the contract for the extended `ToolCallStatus` enum and the
/// `isInFlight` computed property that downstream guards rely on.
final class ToolCallStatusTests: XCTestCase {

  // MARK: - isInFlight contract

  func testIsInFlightTrueForRunningSlowStalled() {
    XCTAssertTrue(ToolCallStatus.running.isInFlight)
    XCTAssertTrue(ToolCallStatus.slow.isInFlight)
    XCTAssertTrue(ToolCallStatus.stalled.isInFlight)
  }

  func testIsInFlightFalseForCompletedFailed() {
    XCTAssertFalse(ToolCallStatus.completed.isInFlight)
    XCTAssertFalse(ToolCallStatus.failed.isInFlight)
  }

  /// Adding a new enum case without updating this expectation should
  /// force a conscious decision about whether that state is in-flight.
  func testIsInFlightCoversEveryCase() {
    XCTAssertEqual(ToolCallStatus.allCases.count, 5)
    XCTAssertEqual(
      ToolCallStatus.allCases.filter(\.isInFlight),
      [.running, .slow, .stalled]
    )
  }

  // MARK: - Stall tracking-id derivation

  /// The `StallDetector` registration site and the `applyStallTransitions`
  /// match site MUST derive a tool's tracking key the same way, or stall
  /// transitions for `toolUseId`-less tools are silently dropped. Both go
  /// through `ChatProvider.stallTrackingId`; this locks its contract.
  func testStallTrackingIdUsesToolUseIdWhenPresent() {
    XCTAssertEqual(
      ChatProvider.stallTrackingId(toolUseId: "abc123", name: "execute_sql"),
      "abc123"
    )
  }

  func testStallTrackingIdFallsBackToNameWhenToolUseIdMissing() {
    XCTAssertEqual(
      ChatProvider.stallTrackingId(toolUseId: nil, name: "execute_sql"),
      "untracked-execute_sql"
    )
  }
}
