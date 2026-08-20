import XCTest

@testable import Omi_Computer

final class ContextDwellRefreshPolicyTests: XCTestCase {
  private let changedHash: UInt64 = 0xFFFF_FFFF_0000_0000
  private let anchorHash: UInt64 = 0x0000_0000_0000_0000

  func testNoRefreshBeforeInitialDwell() {
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 19, firedRefreshesThisContext: 0,
        lastEvaluatedHash: anchorHash, currentHash: changedHash))
  }

  func testFirstRefreshAtInitialDwellWhenContentChanged() {
    XCTAssertTrue(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 20, firedRefreshesThisContext: 0,
        lastEvaluatedHash: anchorHash, currentHash: changedHash))
  }

  func testStaticScreenNeverRefreshes() {
    // Identical hash and a 1-bit flicker both stay under the change bar,
    // however long the dwell.
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 3600, firedRefreshesThisContext: 0,
        lastEvaluatedHash: anchorHash, currentHash: anchorHash))
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 3600, firedRefreshesThisContext: 5,
        lastEvaluatedHash: anchorHash, currentHash: 0x1))
  }

  func testRepeatRefreshRequiresCooldownSincePreviousRefresh() {
    // A single-page app never switches context, so repeats must stay possible —
    // but only after the refresh-to-refresh cooldown, not the initial dwell.
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 45, firedRefreshesThisContext: 1,
        lastEvaluatedHash: anchorHash, currentHash: changedHash))
    XCTAssertTrue(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 90, firedRefreshesThisContext: 1,
        lastEvaluatedHash: anchorHash, currentHash: changedHash))
    XCTAssertTrue(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 90, firedRefreshesThisContext: 40,
        lastEvaluatedHash: anchorHash, currentHash: changedHash),
      "repeats never exhaust while the screen keeps changing")
  }

  func testMissingAnchorHashAllowsRefresh() {
    XCTAssertTrue(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 20, firedRefreshesThisContext: 0,
        lastEvaluatedHash: nil, currentHash: changedHash))
  }
}
