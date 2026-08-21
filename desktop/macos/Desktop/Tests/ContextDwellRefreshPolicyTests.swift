import XCTest

@testable import Omi_Computer

final class ContextDwellRefreshPolicyTests: XCTestCase {
  func testNoRefreshBeforeInitialDwell() {
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 11, firedRefreshesThisContext: 0, keyboardIdleSeconds: 5))
  }

  func testFirstRefreshAfterTypingSettles() {
    XCTAssertTrue(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 12, firedRefreshesThisContext: 0, keyboardIdleSeconds: 3))
  }

  func testNoRefreshWithoutTypingSinceAnchor() {
    // Reading or watching: the last key-down predates the anchor entirely.
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 30, firedRefreshesThisContext: 0, keyboardIdleSeconds: 300))
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 30, firedRefreshesThisContext: 0, keyboardIdleSeconds: 30))
  }

  func testNoRefreshWhileStillTyping() {
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 25, firedRefreshesThisContext: 0, keyboardIdleSeconds: 0.5),
      "mid-word capture wastes the evaluation on a half-typed thought")
  }

  func testRepeatRefreshRequiresCooldownSincePreviousRefresh() {
    // A single-page app never switches context, so repeats must stay possible —
    // but only after the refresh-to-refresh cooldown, not the initial dwell.
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 30, firedRefreshesThisContext: 1, keyboardIdleSeconds: 5))
    XCTAssertTrue(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 40, firedRefreshesThisContext: 1, keyboardIdleSeconds: 5))
    XCTAssertTrue(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 45, firedRefreshesThisContext: 40, keyboardIdleSeconds: 5),
      "repeats never exhaust while the user keeps typing")
  }
}
