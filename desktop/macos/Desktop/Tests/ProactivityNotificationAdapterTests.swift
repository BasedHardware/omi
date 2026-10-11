import XCTest

@testable import Omi_Computer

@MainActor
final class ProactivityNotificationAdapterTests: XCTestCase {
  private func item(
    kind: String = "action_item", targetID: String = "task-1",
    dismissed: Bool = false, acted: Bool = false
  ) -> OmiAPI.ProactivityFeedItem {
    OmiAPI.ProactivityFeedItem(
      acted: acted, body: "A synthetic follow-up", createdAt: "2026-10-03T12:00:00Z",
      dismissed: dismissed, feedback: "", id: "feed-1", producer: "future_registered_producer",
      target: .init(id: targetID, kind: kind), title: "Follow up")
  }

  func testKnownTargetsAcceptFutureProducerWithoutGuessingFromCopy() {
    XCTAssertEqual(ProactivityNotificationAdapter.target(for: item()), .actionItem("task-1"))
    XCTAssertEqual(
      ProactivityNotificationAdapter.target(for: item(kind: "conversation", targetID: "conversation-1")),
      .conversation("conversation-1"))
  }

  func testTerminalItemsAndUnknownOrEmptyTargetsCannotPresent() {
    XCTAssertNil(ProactivityNotificationAdapter.target(for: item(dismissed: true)))
    XCTAssertNil(ProactivityNotificationAdapter.target(for: item(acted: true)))
    XCTAssertNil(ProactivityNotificationAdapter.target(for: item(kind: "future_target")))
    XCTAssertNil(ProactivityNotificationAdapter.target(for: item(targetID: "  ")))
  }

  func testForeignAuthorizationCannotReportPresentation() throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    authority.endTransition(ownerID: "synthetic-owner")
    let snapshot = try XCTUnwrap(authority.capture(ownerID: "synthetic-owner", expectedOwnerID: nil))
    var presentations = 0
    ProactivityNotificationAdapter.present(item(), authorizationSnapshot: snapshot, hasBeenPresented: { _ in false }) {
      _, _ in
      presentations += 1
    }
    XCTAssertEqual(presentations, 0)
  }

  func testStableIdentitySeparatesOwnersAndOutcomes() {
    let shown = ProactivityNotificationAdapter.identity(ownerID: "a", itemID: "item", event: "shown")
    XCTAssertEqual(shown, ProactivityNotificationAdapter.identity(ownerID: "a", itemID: "item", event: "shown"))
    XCTAssertNotEqual(shown, ProactivityNotificationAdapter.identity(ownerID: "b", itemID: "item", event: "shown"))
    XCTAssertNotEqual(shown, ProactivityNotificationAdapter.identity(ownerID: "a", itemID: "item", event: "opened"))
  }

  func testFeedCardsHaveTheirOwnIdentityAndDoNotDuplicateTheChatJournal() {
    XCTAssertEqual(ProactiveNotificationKind.from(assistantId: "proactivity_v2"), .proactivityV2)
    XCTAssertFalse(ProactiveNotificationKind.proactivityV2.isJournaled)
  }
}
