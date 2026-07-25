import XCTest

@testable import Omi_Computer

/// Deterministic policy test for the stale deferred Home ask-field focus fix
/// (home-stage S6 regression). Exercises the real production policy directly —
/// no run loop, no sleeps.
final class HomeAskFocusPolicyTests: XCTestCase {
  func testFreshTokenMatchesCurrentGeneration() {
    let policy = HomeAskFocusPolicy()
    let token = policy.currentToken()
    XCTAssertTrue(policy.isCurrent(token))
    XCTAssertEqual(token.generation, 0)
  }

  func testInvalidateStalesEveryPriorToken() {
    let policy = HomeAskFocusPolicy()
    let token = policy.currentToken()

    policy.invalidate()

    XCTAssertFalse(
      policy.isCurrent(token),
      "A token captured before an invalidate must no longer be current")
  }

  func testTokenCapturedAfterInvalidateIsCurrent() {
    let policy = HomeAskFocusPolicy()
    let stale = policy.currentToken()
    policy.invalidate()
    let fresh = policy.currentToken()

    XCTAssertFalse(policy.isCurrent(stale))
    XCTAssertTrue(policy.isCurrent(fresh))
  }

  func testGenerationIsStrictlyMonotonic() {
    let policy = HomeAskFocusPolicy()
    let first = policy.currentToken()

    XCTAssertEqual(policy.invalidate(), 1)
    XCTAssertEqual(policy.invalidate(), 2)
    XCTAssertEqual(policy.invalidate(), 3)

    XCTAssertFalse(policy.isCurrent(first))
    XCTAssertTrue(policy.isCurrent(policy.currentToken()))
    XCTAssertEqual(policy.generation, 3)
  }

  /// The exact regression: `openHomeChat` schedules a deferred focus, then a
  /// connect / collapse / close lands before the yielded focus resumes. The
  /// deferred focus must be dropped, not applied (applying it would set the ask
  /// field focused while not in chat, and the focus observer would reopen chat).
  func testStaleDeferredFocusIsDroppedAfterCollapseOrClose() {
    let policy = HomeAskFocusPolicy()

    // openHomeChat(focusInput: true) captures the generation it scheduled against.
    let scheduledToken = policy.currentToken()

    // Before the yielded focus resumes, the user collapses (Esc / click-outside
    // / connect ×) or the automation bridge closes — every one of these
    // invalidates outstanding deferred focus.
    policy.invalidate()

    // The deferred focus resumes and re-checks its generation: stale → skip.
    XCTAssertFalse(
      policy.isCurrent(scheduledToken),
      "A deferred focus scheduled before a collapse/connect/close must be dropped")
  }

  /// An unrelated later open must still be able to focus: invalidation only
  /// kills the superseded generation, not subsequent ones.
  func testSubsequentOpenCanStillFocusAfterAnInvalidate() {
    let policy = HomeAskFocusPolicy()
    _ = policy.currentToken()
    policy.invalidate()

    let reopenedToken = policy.currentToken()
    XCTAssertTrue(policy.isCurrent(reopenedToken))
  }
}
