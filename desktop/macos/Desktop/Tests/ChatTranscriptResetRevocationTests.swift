import XCTest

@testable import Omi_Computer

/// Regression coverage for transcript resets that abandoned an in-flight turn.
///
/// `ChatProvider` has exactly one authority for revoking a running turn: bump
/// `sendGeneration`, revoke the turn's `ChatTurnLifecycle`, and release the
/// bridge send lock. `stopAgent` used it; the transcript resets did not. They
/// blanked `messages` and left `isSending == true`, `activeTurnOwner` set and
/// `sendGeneration` unchanged, so:
///
///  * `sendMessage` rejected every later send with "already sending" and the
///    composer stayed busy with no way back short of relaunching,
///  * `canInterruptActiveTurn` refused every owner, so Stop could not recover
///    it either, and
///  * the abandoned turn's late result still satisfied
///    `ChatQueryResultAuthority`, so it ran the visible-completion path against
///    rows that no longer existed and reported a `completed` the user never saw.
///
/// The trigger is not exotic. `.runtimeOwnerDidChange` is posted whenever the
/// effective owner moves, which includes a rejected token refresh or any API
/// 401 invalidating the session — and session validation runs on app
/// activation. This drives that exact production notification rather than a
/// test-only entry point.
@MainActor
final class ChatTranscriptResetRevocationTests: XCTestCase {
  /// The owner-change reset must leave the turn lifecycle consistent, not just
  /// the transcript empty. A cleared transcript with a latched busy flag is the
  /// stuck state this test exists to prevent.
  func testOwnerChangeResetReleasesTheInFlightTurn() {
    let provider = ChatProvider()
    provider.messages = [
      ChatMessage(id: "u1", text: "hello", sender: .user),
      ChatMessage(id: "a1", text: "hi", sender: .ai),
    ]
    provider.isSending = true

    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)

    XCTAssertTrue(
      provider.messages.isEmpty,
      "Owner change must clear the previous owner's transcript"
    )
    XCTAssertFalse(
      provider.isSending,
      "Owner change must revoke the in-flight turn, not leave the composer latched busy"
    )
    XCTAssertFalse(
      provider.isStopping,
      "A revoked turn must settle out of the stopping state, not stay mid-stop"
    )
    XCTAssertNil(
      provider.activeTurnOwner,
      "A revoked turn must release ownership so a later owner can start a turn"
    )
  }

  /// `canInterruptActiveTurn` is the gate every other surface asks before it
  /// starts or stops a turn. After a reset it must report an idle provider.
  func testRevokedTurnNoLongerBlocksOtherOwners() {
    let provider = ChatProvider()
    provider.isSending = true

    XCTAssertFalse(
      provider.canInterruptActiveTurn(owner: .floatingVoice),
      "Precondition: a turn with no recorded owner blocks other owners"
    )

    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)

    XCTAssertTrue(
      provider.canInterruptActiveTurn(owner: .floatingVoice),
      "A revoked turn must not keep refusing every other surface"
    )
  }

  /// The reset must stay a no-op for the busy flag when nothing is in flight —
  /// it must not manufacture a stop for an idle provider.
  func testOwnerChangeResetLeavesAnIdleProviderIdle() {
    let provider = ChatProvider()
    provider.messages = [ChatMessage(id: "u1", text: "hello", sender: .user)]

    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)

    XCTAssertTrue(provider.messages.isEmpty)
    XCTAssertFalse(provider.isSending)
    XCTAssertFalse(provider.isStopping)
  }
}
