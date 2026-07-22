import XCTest

@testable import Omi_Computer

final class HomeStageHistoryAutoOpenPolicyTests: XCTestCase {
  func testExplicitAutomationHubCloseSurvivesLateMessageCountChange() {
    var policy = HomeStageHistoryAutoOpenPolicy()

    XCTAssertFalse(
      policy.shouldAutoOpen(isLegacy: false, mode: .chat, hasMessages: true),
      "A message arriving while chat is already open must leave the one-shot auto-open pending")

    policy.suppressAutoOpenForExplicitHubClose()

    XCTAssertFalse(
      policy.shouldAutoOpen(isLegacy: false, mode: .hub, hasMessages: true),
      "A late message-count change must not undo an explicit automation hub close")
  }

  func testInitialHistoryStillAutoOpensChatOnce() {
    var policy = HomeStageHistoryAutoOpenPolicy()

    XCTAssertTrue(policy.shouldAutoOpen(isLegacy: false, mode: .hub, hasMessages: true))
    XCTAssertFalse(policy.shouldAutoOpen(isLegacy: false, mode: .hub, hasMessages: true))
  }
}
