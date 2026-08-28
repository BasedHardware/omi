import XCTest

@testable import Omi_Computer

/// Controller-level behavior of the presence-gated warm deferral: passive
/// lifecycle callers of `ensureWarm()` (mint completions, owner-change
/// recovery, barge-in cleanup) must NOT clear an away deferral — background
/// churn would silently defeat the quota gate — while user-intent paths
/// (PTT, launch, the presence poll's input-return) always clear it.
@MainActor
final class RealtimeHubPresenceGateTests: XCTestCase {
  private func deferredController(idleSeconds: TimeInterval) -> RealtimeHubController {
    let controller = RealtimeHubController()
    controller.warmDeferredForUserAway = true
    controller.presenceIdleProvider = { idleSeconds }
    return controller
  }

  func testPassiveWarmRequestPreservesAwayDeferral() {
    let controller = deferredController(idleSeconds: RealtimeHubWarmPresencePolicy.idleThreshold * 2)
    controller.ensureWarm()
    XCTAssertTrue(controller.warmDeferredForUserAway)
    XCTAssertNil(controller.session)
  }

  func testUserInitiatedWarmClearsAwayDeferral() {
    let controller = deferredController(idleSeconds: RealtimeHubWarmPresencePolicy.idleThreshold * 2)
    controller.ensureWarm(userInitiated: true)
    XCTAssertFalse(controller.warmDeferredForUserAway)
  }

  /// A passive request while the HID sample shows fresh input = the user is
  /// actually back — resume warming rather than waiting for the poll tick.
  func testPassiveWarmRequestResumesWhenInputIsFresh() {
    let controller = deferredController(idleSeconds: 0)
    controller.ensureWarm()
    XCTAssertFalse(controller.warmDeferredForUserAway)
  }
}

/// The return detector must not lose a brief return between delayed polls:
/// the freshness window is the measured inter-sample gap plus slack, never a
/// fixed sub-gap constant.
@MainActor
final class RealtimeHubPresencePollTimingTests: XCTestCase {
  private func deferredController(idleSeconds: TimeInterval) -> RealtimeHubController {
    let controller = RealtimeHubController()
    controller.warmDeferredForUserAway = true
    controller.presenceIdleProvider = { idleSeconds }
    return controller
  }

  /// Input 15s ago, poll delayed to a 20s gap: a fixed 10s window would miss
  /// this return forever; the elapsed-aware window resumes warming.
  func testInputBetweenDelayedPollsResumesWarming() {
    let controller = deferredController(idleSeconds: 15)
    XCTAssertTrue(controller.presencePollTick(elapsedSincePreviousSample: 20))
    XCTAssertFalse(controller.warmDeferredForUserAway)
  }

  /// Input from before the previous sample (older than the whole gap) is not
  /// a return — the deferral holds.
  func testStaleInputAcrossDelayedPollsStaysDeferred() {
    let controller = deferredController(idleSeconds: 40)
    XCTAssertFalse(controller.presencePollTick(elapsedSincePreviousSample: 20))
    XCTAssertTrue(controller.warmDeferredForUserAway)
  }

  /// An on-time poll keeps the one-interval window (plus slack).
  func testOnTimePollAcceptsInputInsideTheInterval() {
    let controller = deferredController(idleSeconds: 5)
    XCTAssertTrue(
      controller.presencePollTick(
        elapsedSincePreviousSample: RealtimeHubWarmPresencePolicy.presencePollInterval))
    XCTAssertFalse(controller.warmDeferredForUserAway)
  }

  /// A cleared deferral stops the poll loop without touching warm state.
  func testTickStopsWhenDeferralAlreadyCleared() {
    let controller = RealtimeHubController()
    controller.warmDeferredForUserAway = false
    XCTAssertTrue(controller.presencePollTick(elapsedSincePreviousSample: 10))
  }
}
