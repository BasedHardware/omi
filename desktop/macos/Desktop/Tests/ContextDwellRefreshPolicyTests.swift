import XCTest

@testable import Omi_Computer

final class ContextDwellRefreshPolicyTests: XCTestCase {
  private let changedHash: UInt64 = 0xFFFF_FFFF_0000_0000
  private let anchorHash: UInt64 = 0x0000_0000_0000_0000

  func testNoRefreshBeforeFirstMilestone() {
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        dwellSeconds: 19, completedRefreshes: 0,
        lastEvaluatedHash: anchorHash, currentHash: changedHash))
  }

  func testRefreshAtFirstMilestoneWhenContentChanged() {
    XCTAssertTrue(
      ContextDwellRefreshPolicy.shouldRefresh(
        dwellSeconds: 20, completedRefreshes: 0,
        lastEvaluatedHash: anchorHash, currentHash: changedHash))
  }

  func testStaticScreenNeverRefreshes() {
    // Identical hash and a 1-bit flicker both stay under the change bar.
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        dwellSeconds: 120, completedRefreshes: 0,
        lastEvaluatedHash: anchorHash, currentHash: anchorHash))
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        dwellSeconds: 120, completedRefreshes: 0,
        lastEvaluatedHash: anchorHash, currentHash: 0x1))
  }

  func testSecondMilestoneRequiresLongerDwell() {
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        dwellSeconds: 30, completedRefreshes: 1,
        lastEvaluatedHash: anchorHash, currentHash: changedHash))
    XCTAssertTrue(
      ContextDwellRefreshPolicy.shouldRefresh(
        dwellSeconds: 45, completedRefreshes: 1,
        lastEvaluatedHash: anchorHash, currentHash: changedHash))
  }

  func testRefreshBudgetIsExhaustible() {
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        dwellSeconds: 3600, completedRefreshes: 2,
        lastEvaluatedHash: anchorHash, currentHash: changedHash),
      "a dwell never buys more than the milestone count of refreshes")
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        dwellSeconds: 3600, completedRefreshes: -1,
        lastEvaluatedHash: anchorHash, currentHash: changedHash))
  }

  func testMissingAnchorHashAllowsRefresh() {
    XCTAssertTrue(
      ContextDwellRefreshPolicy.shouldRefresh(
        dwellSeconds: 20, completedRefreshes: 0,
        lastEvaluatedHash: nil, currentHash: changedHash))
  }
}
