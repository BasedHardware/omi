import XCTest

@testable import Omi_Computer

/// Presence-gated warming: the idle-teardown re-warm loop re-bills the full
/// session context (~18.5k tokens measured) every ~150s per running app; with
/// the user away that spend buys nothing and fleet-wide it tripped the
/// project's Gemini spend throttle. These tests pin the gate's decision table.
final class RealtimeHubWarmPresencePolicyTests: XCTestCase {
  func testActiveUserKeepsTheWarmLoop() {
    XCTAssertTrue(
      RealtimeHubWarmPresencePolicy.shouldRewarmAfterIdleTeardown(secondsSinceLastUserInput: 0))
    XCTAssertTrue(
      RealtimeHubWarmPresencePolicy.shouldRewarmAfterIdleTeardown(
        secondsSinceLastUserInput: RealtimeHubWarmPresencePolicy.idleThreshold - 1))
  }

  func testAwayUserDefersTheRewarm() {
    XCTAssertFalse(
      RealtimeHubWarmPresencePolicy.shouldRewarmAfterIdleTeardown(
        secondsSinceLastUserInput: RealtimeHubWarmPresencePolicy.idleThreshold))
    XCTAssertFalse(
      RealtimeHubWarmPresencePolicy.shouldRewarmAfterIdleTeardown(
        secondsSinceLastUserInput: 8 * 60 * 60))
  }

  /// A failed HID idle query must fail OPEN — behave exactly like today
  /// (always re-warm) rather than silently killing the warm path.
  func testUnknownIdleFailsOpenToWarming() {
    XCTAssertTrue(
      RealtimeHubWarmPresencePolicy.shouldRewarmAfterIdleTeardown(secondsSinceLastUserInput: nil))
    XCTAssertTrue(
      RealtimeHubWarmPresencePolicy.shouldResumeWarming(secondsSinceLastUserInput: nil))
  }

  /// While deferred, only input NEWER than the poll interval resumes warming —
  /// otherwise the stale pre-departure idle sample would resume immediately.
  func testResumeRequiresInputFresherThanThePollInterval() {
    XCTAssertTrue(
      RealtimeHubWarmPresencePolicy.shouldResumeWarming(secondsSinceLastUserInput: 0.5))
    XCTAssertFalse(
      RealtimeHubWarmPresencePolicy.shouldResumeWarming(
        secondsSinceLastUserInput: RealtimeHubWarmPresencePolicy.presencePollInterval))
    XCTAssertFalse(
      RealtimeHubWarmPresencePolicy.shouldResumeWarming(
        secondsSinceLastUserInput: RealtimeHubWarmPresencePolicy.idleThreshold))
  }
}
