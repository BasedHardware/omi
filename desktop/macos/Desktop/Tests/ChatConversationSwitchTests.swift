import XCTest

@testable import Omi_Computer

/// Regression coverage for `ChatConversationSwitch.transition`.
///
/// The conversation-switch reset in `ChatMessagesView` used to gate on the
/// `onChange` `oldValue` (`oldId != nil`). Switching between two conversations
/// through a transient empty timeline (A -> nil -> B) made `oldId` nil at the
/// moment B arrived, so the reset was skipped and conversation B inherited A's
/// stale `scrollMode` / `initialRestoreHandled` — opening at the wrong scroll
/// position. The pure transition below must still reset for B.
final class ChatConversationSwitchTests: XCTestCase {
  func testInitialPopulationTracksWithoutReset() {
    let t = ChatConversationSwitch.transition(current: nil, incoming: "A1")
    XCTAssertEqual(t.newTracked, "A1")
    XCTAssertFalse(t.shouldReset, "Initial population must not reset (onAppear handles it)")
  }

  func testDirectSwitchResets() {
    let t = ChatConversationSwitch.transition(current: "A1", incoming: "B1")
    XCTAssertEqual(t.newTracked, "B1")
    XCTAssertTrue(t.shouldReset)
  }

  func testTransientEmptyKeepsTrackingPreviousConversation() {
    // A -> nil: the empty/loading state must not clear tracking, otherwise
    // the subsequent real conversation looks like an initial population.
    let t = ChatConversationSwitch.transition(current: "A1", incoming: nil)
    XCTAssertEqual(t.newTracked, "A1", "nil incoming must keep the previous tracked id")
    XCTAssertFalse(t.shouldReset)
  }

  func testSwitchThroughEmptyStillResetsForNewConversation() {
    // Full A -> nil -> B sequence: the reset must fire when B arrives.
    let afterEmpty = ChatConversationSwitch.transition(current: "A1", incoming: nil)
    let afterB = ChatConversationSwitch.transition(current: afterEmpty.newTracked, incoming: "B1")
    XCTAssertEqual(afterB.newTracked, "B1")
    XCTAssertTrue(afterB.shouldReset, "Switching A -> nil -> B must reset scroll state for B")
  }

  func testNoChangeIsANoOp() {
    let t = ChatConversationSwitch.transition(current: "A1", incoming: "A1")
    XCTAssertEqual(t.newTracked, "A1")
    XCTAssertFalse(t.shouldReset)
  }
}
