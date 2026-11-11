import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

/// The floating bar's real queue and presentation latch, driven with real authorization changes.
@MainActor
final class HandsFreeRequestScopeTests: XCTestCase {
  private let authority = RuntimeOwnerAuthorityTestFixture()

  override func tearDown() async throws {
    await authority.restore()
  }

  private func request(as owner: String = "scope-account-a") async throws -> HandsFreeRequest {
    await authority.establish(authOwnerID: owner)
    return HandsFreeRequest(origin: try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot()))
  }

  // MARK: Queued dispatch

  func testAQueuedCommandFromAnotherAccountNeverDispatches() async throws {
    var slot = RequestBoundSlot<String>()
    slot.put("order food", request: try await request())

    await authority.establish(authOwnerID: "scope-account-b")

    XCTAssertNil(slot.take(), "B signed in before the queue drained")
    XCTAssertNil(slot.take(), "and the stale command is gone, not retried")
  }

  func testSigningOutAndBackInAsTheSameAccountInvalidatesTheOldRequest() async throws {
    let original = try await request()
    var slot = RequestBoundSlot<String>()
    slot.put("order food", request: original)

    await authority.establish(authOwnerID: nil)
    await authority.establish(authOwnerID: "scope-account-a")

    XCTAssertFalse(original.isCurrent)
    XCTAssertNil(slot.take())
  }

  func testTheSameAccountDispatchesExactlyOnce() async throws {
    let request = try await request()
    var slot = RequestBoundSlot<String>()
    slot.put("order food", request: request)

    let first = slot.take()
    XCTAssertEqual(first?.payload, "order food")
    XCTAssertEqual(first?.request, request)
    XCTAssertNil(slot.take())
  }

  func testATypedQueryIsNeverBlockedByAccountChecks() async throws {
    var slot = RequestBoundSlot<String>()
    slot.put("typed question", request: nil)
    await authority.establish(authOwnerID: "scope-account-b")
    XCTAssertEqual(slot.take()?.payload, "typed question")
  }

  func testATriggerWhoseAccountChangedBeforeTheTaskRunsIsNotCurrent() async throws {
    let request = try await request()
    XCTAssertTrue(request.isCurrent)
    await authority.establish(authOwnerID: "scope-account-b")
    XCTAssertFalse(request.isCurrent, "the guard each send hop uses rejects it")
  }

  // MARK: Presentation latch

  func testARejectedHandsFreeRequestDoesNotHideTheNextTypedAnswer() {
    var latch = QuietSurfaceLatch()
    let handsFree = UUID()
    latch.arm(handsFree)

    latch.release(handsFree)  // origin revoked: the request is rejected before presenting

    XCTAssertTrue(latch.presentsSurface(for: nil), "the next typed question stays visible")
  }

  func testAnOldRequestCannotClearANewerRequestsArm() {
    var latch = QuietSurfaceLatch()
    let old = UUID()
    let newer = UUID()
    latch.arm(old)
    latch.arm(newer)

    latch.release(old)

    XCTAssertTrue(latch.presentsSurface(for: old))
    XCTAssertFalse(latch.presentsSurface(for: newer), "the newer hands-free answer stays quiet")
  }

  func testATypedQuestionDuringAHandsFreeRequestStaysVisibleAndLeavesItsArm() {
    var latch = QuietSurfaceLatch()
    let handsFree = UUID()
    latch.arm(handsFree)

    XCTAssertTrue(latch.presentsSurface(for: nil))
    XCTAssertFalse(latch.presentsSurface(for: handsFree))
    XCTAssertTrue(latch.presentsSurface(for: handsFree), "an arm quiets exactly one presentation")
  }

  // MARK: Realtime send completion

  func testAStaleRealtimeSendCompletionNeverTouchesAReplacementTurn() {
    let ours = VoiceTurnID()
    let replacement = VoiceTurnID()

    XCTAssertEqual(WakeWordSendOutcome(originCurrent: true, activeTurnID: ours, turnID: ours), .commit)
    XCTAssertEqual(WakeWordSendOutcome(originCurrent: false, activeTurnID: ours, turnID: ours), .cancelOwnTurn)
    XCTAssertEqual(
      WakeWordSendOutcome(originCurrent: true, activeTurnID: replacement, turnID: ours), .leaveReplacement)
    XCTAssertEqual(
      WakeWordSendOutcome(originCurrent: false, activeTurnID: replacement, turnID: ours), .leaveReplacement,
      "even after an account switch, a stale completion never cancels the replacement")
    XCTAssertEqual(WakeWordSendOutcome(originCurrent: true, activeTurnID: nil, turnID: ours), .leaveReplacement)
  }
}
