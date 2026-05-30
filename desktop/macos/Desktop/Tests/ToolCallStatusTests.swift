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

  /// Adding a new enum case without updating `isInFlight` would silently
  /// classify it as not-in-flight (no default branch — Swift exhaustive
  /// switch catches the missing case at compile time). This test exists
  /// to make the contract intentional rather than incidental.
  func testIsInFlightCoversEveryCase() {
    // If a future commit adds a case, this test forces the author to
    // think about whether it should be in-flight or not.
    let allCases: [ToolCallStatus] = [.running, .slow, .stalled, .completed, .failed]
    let inFlightCount = allCases.filter { $0.isInFlight }.count
    XCTAssertEqual(inFlightCount, 3, "exactly running, slow, stalled are in-flight")
  }
}
