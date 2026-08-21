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
        secondsSinceAnchor: 12, firedRefreshesThisContext: 0, keyboardIdleSeconds: 6))
  }

  func testComposingPauseDoesNotFireMidBurst() {
    // Live regression: recipient → subject → body pauses run 1–3s. A refresh
    // fired inside the burst evaluates a half-typed question and burns the
    // repeat-cooldown slot, so the finished question's answer lands minutes
    // late instead of seconds.
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 20, firedRefreshesThisContext: 0, keyboardIdleSeconds: 3))
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 60, firedRefreshesThisContext: 3, keyboardIdleSeconds: 4.5))
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

  func testSecondRefreshGetsOneTypingGraceWindow() {
    // The burst that armed refresh #1 still counts for refresh #2 (a zero-fact
    // extraction loses the question otherwise)...
    XCTAssertTrue(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 40, firedRefreshesThisContext: 1, keyboardIdleSeconds: 55))
    // ...but not beyond the grace window, and never for refresh #3+.
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 40, firedRefreshesThisContext: 1, keyboardIdleSeconds: 90))
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: 40, firedRefreshesThisContext: 2, keyboardIdleSeconds: 55))
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

  func testRetryAnchorReArmsShortlyWithoutDoubleFire() {
    let now = Date()
    let anchor = ContextDwellRefreshPolicy.retryAnchor(now: now)
    let age = now.timeIntervalSince(anchor)
    // A failed refresh retries in ~10s (cooldown minus the backdate)...
    XCTAssertEqual(
      age, ContextDwellRefreshPolicy.repeatRefreshCooldownSeconds - 10, accuracy: 0.001)
    // ...which is NOT immediately eligible again, so the tick loop cannot
    // double-fire in the same breath.
    XCTAssertFalse(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: age, firedRefreshesThisContext: 1, keyboardIdleSeconds: 5))
    XCTAssertTrue(
      ContextDwellRefreshPolicy.shouldRefresh(
        secondsSinceAnchor: age + 11, firedRefreshesThisContext: 1, keyboardIdleSeconds: 5))
  }
}
