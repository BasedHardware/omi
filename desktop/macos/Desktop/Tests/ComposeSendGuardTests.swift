import XCTest

@testable import Omi_Computer

/// The person says "Send" after a draft and the model reaches for send_message.
/// The draft is already waiting in Messages, so Omi must not send its own copy.
@MainActor
final class ComposeSendGuardTests: ComposeProposalTestCase {
  private var clock = Date(timeIntervalSince1970: 1_000)

  private func coordinatorWithDraft(
    _ proposal: ComposeProposal? = nil,
    owner: String = "owner-1",
    event: ComposeSurfaceEvent = .shared
  ) async -> ComposeProposalCoordinator {
    let surface = FakeComposeSurface()
    surface.immediateEvent = event
    let coordinator = makeCoordinator(surface, sleep: neverElapses, now: { [unowned self] in self.clock })
    _ = await coordinator.propose(proposal ?? messageProposal(), context: context(owner: owner))
    return coordinator
  }

  private func blocked(_ to: String, owner: String = "owner-1", _ coordinator: ComposeProposalCoordinator) -> Bool {
    ChatToolExecutor.sendBlockedByWaitingDraft(to: to, ownerID: owner, coordinator: coordinator) != nil
  }

  func testSendAfterAHandedOffDraftIsRefusedAndSendsNothing() async throws {
    let coordinator = await coordinatorWithDraft()

    // Reaches the guard before Messages could ever be contacted.
    let result = await ChatToolExecutor.executeSendMessage(
      ["to": "555-010-0100", "text": "On my way"], ownerID: "owner-1", composeCoordinator: coordinator)

    let payload = try decode(result)
    XCTAssertEqual(payload["reason"] as? String, "draft_in_messages")
    XCTAssertEqual(payload["status"] as? String, "not_sent")
    XCTAssertEqual(payload["sent_by_omi"] as? Bool, false)
    XCTAssertTrue((payload["error"] as? String)?.contains("press Send in Messages") == true)
  }

  func testAnyTextToTheSameRecipientIsRefused() async {
    let coordinator = await coordinatorWithDraft()

    XCTAssertTrue(blocked("+1 (555) 010-0100", coordinator), "same person, other spelling")
    XCTAssertTrue(blocked("15550100100", coordinator))
  }

  func testAfterTenMinutesTheNormalPathApplies() async {
    let coordinator = await coordinatorWithDraft()

    clock = clock.addingTimeInterval(599)
    XCTAssertTrue(blocked("+15550100100", coordinator))
    clock = clock.addingTimeInterval(2)
    XCTAssertFalse(blocked("+15550100100", coordinator))
  }

  func testADifferentRecipientOrOwnerTakesTheNormalPath() async {
    let coordinator = await coordinatorWithDraft()

    XCTAssertFalse(blocked("+15550100199", coordinator))
    XCTAssertFalse(blocked("+15550100100", owner: "owner-2", coordinator))
  }

  func testAnEmailDraftOrACancelledDraftDoesNotBlockASend() async {
    let email = ComposeProposal(channel: .email, recipients: ["sam@example.com"], subject: nil, body: "Hi")
    let emailCoordinator = await coordinatorWithDraft(email)
    XCTAssertFalse(blocked("sam@example.com", emailCoordinator), "only a draft waiting in Messages")

    let cancelled = await coordinatorWithDraft(event: .cancelled)
    XCTAssertFalse(blocked("+15550100100", cancelled))
  }

  func testEveryRecipientOfAGroupDraftIsCovered() async {
    let group = ComposeProposal(
      channel: .message, recipients: ["+15550100100", "maya@example.com"], subject: nil, body: "Dinner?")
    let coordinator = await coordinatorWithDraft(group)

    XCTAssertTrue(blocked("Maya@Example.com", coordinator))
  }
}
