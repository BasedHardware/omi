import XCTest

@testable import Omi_Computer

/// After a draft is handed off, "send it" must not stack a second copy.
@MainActor
final class ComposeDuplicateDraftTests: ComposeProposalTestCase {
  func testTheSameDraftIsNotHandedOffAgainForTwoMinutes() async {
    // The person says "send it" after a draft; the model must not stack a copy.
    let surface = FakeComposeSurface()
    surface.immediateEvent = .shared
    var clock = Date(timeIntervalSince1970: 1_000)
    let coordinator = makeCoordinator(surface, sleep: neverElapses, now: { clock })

    let first = await coordinator.propose(messageProposal(), context: context(run: "run-1"))
    clock = clock.addingTimeInterval(30)
    let again = await coordinator.propose(messageProposal(body: "  On my way \n"), context: context(run: "run-2"))
    let edited = await coordinator.propose(messageProposal(body: "On my way, 5 min"), context: context(run: "run-3"))
    clock = clock.addingTimeInterval(91)
    let later = await coordinator.propose(messageProposal(), context: context(run: "run-4"))

    XCTAssertEqual([first, again, edited, later], [.handedOff, .duplicateDraft, .handedOff, .handedOff])
    XCTAssertEqual(surface.presented.count, 3)
  }

  func testTheSameDraftMatchesRecipientsInAnyOrderAndSpelling() {
    let one = ComposeProposal(
      channel: .message, recipients: ["+1 (555) 010-0100", "Maya@Example.com"], subject: nil, body: "Hi")
    let two = ComposeProposal(
      channel: .message, recipients: ["maya@example.com", "+15550100100"], subject: nil, body: "Hi")
    let email = ComposeProposal(channel: .email, recipients: one.recipients, subject: nil, body: "Hi")

    XCTAssertEqual(ComposeProposalCoordinator.draftDigest(one), ComposeProposalCoordinator.draftDigest(two))
    XCTAssertNotEqual(ComposeProposalCoordinator.draftDigest(one), ComposeProposalCoordinator.draftDigest(email))
  }

  func testACancelledDraftCanBeAskedForAgain() async {
    let surface = FakeComposeSurface()
    surface.immediateEvent = .cancelled
    let coordinator = makeCoordinator(surface, sleep: neverElapses)

    let first = await coordinator.propose(messageProposal(), context: context(run: "run-1"))
    surface.immediateEvent = .shared
    let again = await coordinator.propose(messageProposal(), context: context(run: "run-2"))

    XCTAssertEqual([first, again], [.cancelled, .handedOff])
  }

  func testADifferentOwnerIsNotADuplicate() async {
    let surface = FakeComposeSurface()
    surface.immediateEvent = .shared
    let coordinator = makeCoordinator(surface, sleep: neverElapses)

    _ = await coordinator.propose(messageProposal(), context: context(run: "run-1", owner: "owner-1"))
    let other = await coordinator.propose(messageProposal(), context: context(run: "run-2", owner: "owner-2"))

    XCTAssertEqual(other, .handedOff)
  }
}
