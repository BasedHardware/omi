import AppKit
import XCTest

@testable import Omi_Computer

@MainActor
final class ComposeProposalCoordinatorTests: ComposeProposalTestCase {
  // MARK: - Coordinator

  func testMailHandoffReportsHandedOffNotSent() async {
    let surface = FakeComposeSurface()
    surface.immediateEvent = .shared
    let coordinator = makeCoordinator(surface, sleep: neverElapses)

    let outcome = await coordinator.propose(emailProposal(), context: context())

    XCTAssertEqual(outcome, .handedOff)
    XCTAssertEqual(surface.presented, [emailProposal()])
  }

  func testReportArrivingWhileWaitingIsTheOutcome() async {
    let surface = FakeComposeSurface()
    // The report lands after the call is already waiting on the window.
    let coordinator = makeCoordinator(surface, sleep: { _ in await surface.report(.cancelled) })

    let outcome = await coordinator.propose(messageProposal(), context: context())

    XCTAssertEqual(outcome, .cancelled)
  }

  func testOneDraftPerRequestEvenAfterMailTookTheFirst() async {
    // Mail frees its window at once, so the per-request limit is what stops a
    // looping model from stacking compose windows.
    let surface = FakeComposeSurface()
    surface.immediateEvent = .shared
    let coordinator = makeCoordinator(surface, sleep: neverElapses)

    let first = await coordinator.propose(emailProposal(), context: context())
    let second = await coordinator.propose(emailProposal(["alex@example.com"]), context: context())
    let nextRequest = await coordinator.propose(emailProposal(body: "Updated deck."), context: context(run: "run-2"))

    XCTAssertEqual(first, .handedOff)
    XCTAssertEqual(second, .limitReached)
    XCTAssertEqual(nextRequest, .handedOff)
    XCTAssertEqual(surface.presented.count, 2)
  }

  func testOneEmailAndOneMessagePerRequest() async {
    // "Email Sam the deck and text him it's on the way" is one request.
    let surface = FakeComposeSurface()
    surface.immediateEvent = .shared
    let coordinator = makeCoordinator(surface, sleep: neverElapses)

    let email = await coordinator.propose(emailProposal(), context: context())
    let message = await coordinator.propose(messageProposal(), context: context())
    let secondMessage = await coordinator.propose(messageProposal(body: "Also bring the charger"), context: context())

    XCTAssertEqual([email, message, secondMessage], [.handedOff, .handedOff, .limitReached])
  }

  func testAtMostThreeDraftsAMinute() async {
    let surface = FakeComposeSurface()
    surface.immediateEvent = .shared
    var clock = Date(timeIntervalSince1970: 1_000)
    let coordinator = makeCoordinator(surface, sleep: neverElapses, now: { clock })

    var outcomes: [ComposeProposalOutcome] = []
    for run in 1...4 {
      outcomes.append(
        await coordinator.propose(emailProposal(body: "Draft \(run)"), context: context(run: "run-\(run)")))
    }
    clock = clock.addingTimeInterval(61)
    let afterAMinute = await coordinator.propose(emailProposal(body: "Draft 5"), context: context(run: "run-5"))

    XCTAssertEqual(outcomes, [.handedOff, .handedOff, .handedOff, .limitReached])
    XCTAssertEqual(afterAMinute, .handedOff)
  }

  func testWithoutARunOnlyOneDraftAMinute() async {
    let surface = FakeComposeSurface()
    surface.immediateEvent = .shared
    var clock = Date(timeIntervalSince1970: 1_000)
    let coordinator = makeCoordinator(surface, sleep: neverElapses, now: { clock })

    let first = await coordinator.propose(emailProposal(body: "A"), context: context(run: nil))
    let second = await coordinator.propose(emailProposal(body: "B"), context: context(run: nil))
    clock = clock.addingTimeInterval(61)
    let later = await coordinator.propose(emailProposal(body: "C"), context: context(run: nil))

    XCTAssertEqual([first, second, later], [.handedOff, .limitReached, .handedOff])
  }

  func testAnOpenMessagesSheetBlocksADraftFromTheNextRequest() async {
    let surface = FakeComposeSurface()
    let coordinator = makeCoordinator(surface, sleep: elapsesAtOnce)

    let first = await coordinator.propose(messageProposal(), context: context())
    let second = await coordinator.propose(emailProposal(), context: context(run: "run-2"))

    XCTAssertEqual(first, .open)
    XCTAssertEqual(second, .alreadyOpen)
    XCTAssertEqual(surface.presented.count, 1, "a second window must not open over the first")
  }

  func testLateReportFreesTheSlotForTheNextRequest() async {
    let surface = FakeComposeSurface()
    let coordinator = makeCoordinator(surface, sleep: elapsesAtOnce)

    let first = await coordinator.propose(messageProposal(), context: context())
    // The person cancels after the tool already answered `open`.
    surface.report(.cancelled)
    let second = await coordinator.propose(messageProposal(), context: context(run: "run-2"))

    XCTAssertEqual(first, .open, "a late report cannot rewrite an answer already given")
    XCTAssertEqual(second, .open)
    XCTAssertEqual(surface.presented.count, 2)
  }

  func testASheetThatNeverReportsStopsBlockingAfterTheStaleBound() async {
    let surface = FakeComposeSurface()
    var clock = Date(timeIntervalSince1970: 1_000)
    let coordinator = makeCoordinator(surface, sleep: elapsesAtOnce, staleAfter: 300, now: { clock })

    _ = await coordinator.propose(messageProposal(), context: context(run: "run-1"))
    clock = clock.addingTimeInterval(299)
    let blocked = await coordinator.propose(messageProposal(), context: context(run: "run-2"))
    clock = clock.addingTimeInterval(2)
    let replaced = await coordinator.propose(messageProposal(), context: context(run: "run-3"))

    XCTAssertEqual(blocked, .alreadyOpen)
    XCTAssertEqual(replaced, .open)
    XCTAssertEqual(surface.presented.count, 2)
  }

  func testANewOwnerDoesNotInheritTheSlotOrTheLimits() async {
    let surface = FakeComposeSurface()
    let coordinator = makeCoordinator(surface, sleep: elapsesAtOnce)

    _ = await coordinator.propose(messageProposal(), context: context(run: "run-1", owner: "owner-1"))
    let otherOwner = await coordinator.propose(messageProposal(), context: context(run: "run-1", owner: "owner-2"))

    XCTAssertEqual(otherOwner, .open)
    XCTAssertEqual(surface.presented.count, 2)
  }

  func testSignOutReleasesTheSlot() async {
    let surface = FakeComposeSurface()
    let coordinator = makeCoordinator(surface, sleep: elapsesAtOnce)

    _ = await coordinator.propose(messageProposal(), context: context(run: "run-1"))
    coordinator.releaseForOwnerChange()
    let afterSignOut = await coordinator.propose(messageProposal(), context: context(run: "run-2"))

    XCTAssertEqual(afterSignOut, .open)
  }

  func testUnavailableServiceOpensNothing() async {
    let surface = FakeComposeSurface()
    surface.available = false
    let coordinator = makeCoordinator(surface, sleep: neverElapses)

    let outcome = await coordinator.propose(emailProposal(), context: context())

    XCTAssertEqual(outcome, .unavailable)
    XCTAssertTrue(surface.presented.isEmpty)
  }

  func testRefusedPresentationDoesNotHoldTheSlotOrCountAgainstTheRequest() async {
    let surface = FakeComposeSurface()
    surface.startSucceeds = false
    let coordinator = makeCoordinator(surface, sleep: elapsesAtOnce)

    let refused = await coordinator.propose(messageProposal(), context: context())
    surface.startSucceeds = true
    let next = await coordinator.propose(messageProposal(), context: context())

    XCTAssertEqual(refused, .unavailable)
    XCTAssertEqual(next, .open)
  }

  func testNotConfiguredAndFailureReportsMapThrough() async {
    let surface = FakeComposeSurface()
    let coordinator = makeCoordinator(surface, sleep: neverElapses)

    surface.immediateEvent = .notConfigured
    let notConfigured = await coordinator.propose(emailProposal(), context: context(run: "run-1"))
    surface.immediateEvent = .failed(code: 42)
    let failed = await coordinator.propose(emailProposal(), context: context(run: "run-2"))

    XCTAssertEqual(notConfigured, .unavailable)
    XCTAssertEqual(failed, .failed(code: 42))
  }

  func testAnAlreadyStoppedCallOpensNothing() async {
    let surface = FakeComposeSurface()
    let coordinator = makeCoordinator(surface, sleep: neverElapses)

    let task = Task { await coordinator.propose(messageProposal(), context: context()) }
    task.cancel()
    let outcome = await task.value

    XCTAssertEqual(outcome, .notOpened(.stopped))
    XCTAssertTrue(surface.presented.isEmpty)
  }

  func testStoppingTheTurnAfterTheWindowOpensAnswersOpen() async {
    let surface = FakeComposeSurface()
    let coordinator = makeCoordinator(surface, sleep: neverElapses)
    let holder = TaskHolder()
    surface.onPresent = { holder.task?.cancel() }

    let task = Task { () -> String in
      let outcome = await coordinator.propose(self.messageProposal(), context: self.context())
      return "\(outcome)"
    }
    holder.task = task
    let outcome = await task.value

    XCTAssertEqual(outcome, "\(ComposeProposalOutcome.open)")
    XCTAssertEqual(surface.presented.count, 1)
  }

  // MARK: - Typing guard

  func testWaitsForTheKeyboardToGoQuietBeforeOpening() async {
    let surface = FakeComposeSurface()
    surface.immediateEvent = .shared
    let keyboard = ScriptedKeyboard([0.1, 0.5, 1.0, 5.0])
    let coordinator = makeCoordinator(surface, sleep: elapsesAtOnce, keyPress: { keyboard.secondsSinceLastKeyPress() })

    let outcome = await coordinator.propose(messageProposal(), context: context())

    XCTAssertEqual(outcome, .handedOff)
    XCTAssertEqual(keyboard.polls, 4)
    XCTAssertEqual(surface.presented.count, 1)
  }

  func testTheQuietPeriodIsThreeSeconds() async {
    // Return sends from the Messages composer, so 2.5 s of quiet is still typing.
    let surface = FakeComposeSurface()
    surface.immediateEvent = .shared
    let keyboard = ScriptedKeyboard([2.5, 2.9, 3.1])
    let coordinator = makeCoordinator(surface, sleep: elapsesAtOnce, keyPress: { keyboard.secondsSinceLastKeyPress() })

    let outcome = await coordinator.propose(messageProposal(), context: context())

    XCTAssertEqual(outcome, .handedOff)
    XCTAssertEqual(keyboard.polls, 3, "the handoff follows the last idle check with no wait in between")
  }

  func testKeepsTypingMeansNoWindowAndTheSlotIsFree() async {
    let surface = FakeComposeSurface()
    let keyboard = ScriptedKeyboard([0.1])
    let coordinator = makeCoordinator(surface, sleep: elapsesAtOnce, keyPress: { keyboard.secondsSinceLastKeyPress() })

    let outcome = await coordinator.propose(messageProposal(), context: context())

    XCTAssertEqual(outcome, .notOpened(.personTyping))
    XCTAssertTrue(surface.presented.isEmpty, "keystrokes must never land in a draft")
    XCTAssertGreaterThanOrEqual(keyboard.polls, 2)

    // Typing does not use up the request's one draft.
    let quiet = makeCoordinator(surface, sleep: elapsesAtOnce)
    let retry = await quiet.propose(messageProposal(), context: context())
    XCTAssertEqual(retry, .open)
  }

  func testSharingErrorsMapToCancelledNotConfiguredOrFailed() {
    XCTAssertEqual(
      ComposeSurfaceEvent(sharingError: NSError(domain: NSCocoaErrorDomain, code: NSUserCancelledError)),
      .cancelled)
    XCTAssertEqual(
      ComposeSurfaceEvent(
        sharingError: NSError(
          domain: NSCocoaErrorDomain, code: CocoaError.Code.sharingServiceNotConfigured.rawValue)),
      .notConfigured)
    XCTAssertEqual(
      ComposeSurfaceEvent(sharingError: NSError(domain: "OtherDomain", code: NSUserCancelledError)),
      .failed(code: NSUserCancelledError))
  }
}
