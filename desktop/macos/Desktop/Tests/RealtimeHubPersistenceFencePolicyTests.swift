import XCTest

@testable import Omi_Computer

/// Regression coverage for the persistence-fence retry busy-loop.
///
/// `refreshVoiceContextAfterPersistenceFence` used to `continue` on every failed
/// `refreshVoiceContextSnapshot()`. When the owner signed out or the session was
/// invalidated mid-turn, the kernel snapshot could never resolve (the agent
/// bridge refuses to start without a current authorization) and the failure
/// returned instantly, so the loop spun agent-bridge startup at full speed —
/// ~56k "sign in to use AI chat" failures per minute in one observed session,
/// bloating the log to gigabytes. The loop now consults
/// `RealtimeHubLifecyclePolicy.canRetryPersistenceFence`, which only permits a
/// retry while the fence still owns its original authenticated scope.
final class RealtimeHubPersistenceFencePolicyTests: XCTestCase {
  private let ownerA = RealtimeHubOwnerScope.authenticated("uid-A")
  private let ownerB = RealtimeHubOwnerScope.authenticated("uid-B")

  func testRetriesWhileOwnerUnchangedAndAuthenticated() {
    XCTAssertTrue(
      RealtimeHubLifecyclePolicy.canRetryPersistenceFence(
        taskCancelled: false, fenceOwnerScope: ownerA, currentOwnerScope: ownerA))
  }

  func testStopsWhenTaskCancelled() {
    XCTAssertFalse(
      RealtimeHubLifecyclePolicy.canRetryPersistenceFence(
        taskCancelled: true, fenceOwnerScope: ownerA, currentOwnerScope: ownerA))
  }

  func testStopsWhenOwnerSignsOutMidFence() {
    // The exact busy-loop trigger: fence started authenticated, owner is now signedOut.
    XCTAssertFalse(
      RealtimeHubLifecyclePolicy.canRetryPersistenceFence(
        taskCancelled: false, fenceOwnerScope: ownerA, currentOwnerScope: .signedOut))
  }

  func testStopsWhenOwnerSwaps() {
    XCTAssertFalse(
      RealtimeHubLifecyclePolicy.canRetryPersistenceFence(
        taskCancelled: false, fenceOwnerScope: ownerA, currentOwnerScope: ownerB))
  }

  func testNeverRetriesWhileSignedOut() {
    // Even if the scope "matches", a signed-out bridge can never start, so never spin.
    XCTAssertFalse(
      RealtimeHubLifecyclePolicy.canRetryPersistenceFence(
        taskCancelled: false, fenceOwnerScope: .signedOut, currentOwnerScope: .signedOut))
  }
}
