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
