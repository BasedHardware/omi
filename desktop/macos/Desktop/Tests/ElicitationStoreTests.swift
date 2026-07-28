import XCTest

@testable import Omi_Computer

@MainActor
final class ElicitationStoreTests: XCTestCase {
  private func payload(
    dispatchID: String = "disp-1",
    ownerID: String = "owner-1",
    mode: String = "permission",
    allowsFreeText: Bool = false,
    options: [[String: Any]] = [
      ["optionId": "once", "label": "Allow once", "effect": "allow_once"],
      ["optionId": "always", "label": "Allow always", "effect": "allow_always"],
      ["optionId": "no", "label": "Deny", "effect": "reject_once"],
    ]
  ) -> [String: Any] {
    [
      "type": "elicitation_pending",
      "dispatchId": dispatchID,
      "ownerId": ownerID,
      "sessionId": "sess-1",
      "runId": "run-1",
      "mode": mode,
      "adapterId": "hermes",
      "title": "Hermes needs permission",
      "prompt": "Run a command",
      "subject": "rm -rf build/",
      "context": "/Users/dev/omi",
      "options": options,
      "allowsFreeText": allowsFreeText,
      "createdAtMs": 1_700_000_000_000,
    ]
  }

  private func makeStore() -> (ElicitationStore, () -> [(PendingElicitation, ElicitationAnswer)]) {
    var submitted: [(PendingElicitation, ElicitationAnswer)] = []
    let store = ElicitationStore { elicitation, answer in
      submitted.append((elicitation, answer))
    }
    return (store, { submitted })
  }

  func testDecodesEverythingTheCardRenders() throws {
    let elicitation = try XCTUnwrap(PendingElicitation(payload: payload()))

    XCTAssertEqual(elicitation.id, "disp-1")
    XCTAssertEqual(elicitation.mode, .permission)
    XCTAssertEqual(elicitation.prompt, "Run a command")
    XCTAssertEqual(elicitation.subject, "rm -rf build/")
    XCTAssertEqual(elicitation.context, "/Users/dev/omi")
    XCTAssertEqual(elicitation.options.map(\.id), ["once", "always", "no"])
    XCTAssertEqual(elicitation.options.map(\.label), ["Allow once", "Allow always", "Deny"])
  }

  func testPermissionRefusesFreeTextEvenWhenThePayloadClaimsOtherwise() throws {
    // The ACP response shape carries only an optionId, so a payload asserting
    // otherwise must not open a text field that produces an invalid answer.
    let elicitation = try XCTUnwrap(
      PendingElicitation(payload: payload(mode: "permission", allowsFreeText: true)))

    XCTAssertFalse(elicitation.allowsFreeText)
  }

  func testQuestionKeepsFreeTextWhenOffered() throws {
    let elicitation = try XCTUnwrap(
      PendingElicitation(payload: payload(mode: "question", allowsFreeText: true)))

    XCTAssertTrue(elicitation.allowsFreeText)
  }

  func testRejectsAPayloadMissingWhatTheCardNeeds() {
    for missing in ["dispatchId", "ownerId", "sessionId", "mode", "title", "prompt"] {
      var broken = payload()
      broken.removeValue(forKey: missing)
      XCTAssertNil(PendingElicitation(payload: broken), "expected nil without \(missing)")
    }
    var badMode = payload()
    badMode["mode"] = "something_else"
    XCTAssertNil(PendingElicitation(payload: badMode))
  }

  func testOptionEffectsDriveTheirPresentation() throws {
    let elicitation = try XCTUnwrap(PendingElicitation(payload: payload()))

    XCTAssertTrue(elicitation.options[1].isPermanent)
    XCTAssertFalse(elicitation.options[0].isPermanent)
    XCTAssertTrue(elicitation.options[2].isRejection)
    XCTAssertFalse(elicitation.options[0].isRejection)
  }

  func testPresentsTheOldestQuestionFirst() throws {
    let (store, _) = makeStore()
    let first = try XCTUnwrap(PendingElicitation(payload: payload(dispatchID: "a")))
    let second = try XCTUnwrap(PendingElicitation(payload: payload(dispatchID: "b")))

    store.enqueue(first)
    store.enqueue(second)

    XCTAssertEqual(store.focused?.id, "a")
    XCTAssertEqual(store.waitingCount, 2)

    store.stage(.option("once"), for: first)
    store.submitFocused()
    XCTAssertEqual(store.focused?.id, "b")
    XCTAssertEqual(store.waitingCount, 1)
  }

  func testARedeliveredQuestionDoesNotEnqueueTwice() throws {
    let (store, _) = makeStore()
    let elicitation = try XCTUnwrap(PendingElicitation(payload: payload()))

    store.enqueue(elicitation)
    store.enqueue(elicitation)

    XCTAssertEqual(store.waitingCount, 1)
  }

  func testAnsweringSubmitsExactlyOnce() throws {
    let (store, submitted) = makeStore()
    let elicitation = try XCTUnwrap(PendingElicitation(payload: payload()))
    store.enqueue(elicitation)

    store.answer(elicitation, with: .option("no"))
    store.answer(elicitation, with: .option("once"))

    XCTAssertEqual(submitted().count, 1)
    XCTAssertEqual(submitted().first?.1, .option("no"))
  }

  func testTheKernelRetiringAQuestionRemovesItsCard() throws {
    let (store, submitted) = makeStore()
    let elicitation = try XCTUnwrap(PendingElicitation(payload: payload()))
    store.enqueue(elicitation)

    store.remove(id: elicitation.id)

    XCTAssertNil(store.focused)
    // Retirement is not an answer: nothing is sent back on the user's behalf.
    XCTAssertTrue(submitted().isEmpty)
  }

  func testRetiringAnUnknownQuestionIsHarmless() throws {
    let (store, _) = makeStore()
    let elicitation = try XCTUnwrap(PendingElicitation(payload: payload()))
    store.enqueue(elicitation)

    store.remove(id: "never-existed")

    XCTAssertEqual(store.waitingCount, 1)
  }

  func testSignOutDropsOnlyThatOwnersQuestions() throws {
    let (store, _) = makeStore()
    let mine = try XCTUnwrap(PendingElicitation(payload: payload(dispatchID: "a", ownerID: "owner-1")))
    let theirs = try XCTUnwrap(PendingElicitation(payload: payload(dispatchID: "b", ownerID: "owner-2")))
    store.enqueue(mine)
    store.enqueue(theirs)

    store.clear(ownerID: "owner-1")

    XCTAssertEqual(store.queue.map(\.id), ["b"])
  }
}

@MainActor
final class ElicitationQueueNavigationTests: XCTestCase {
  private func pending(_ id: String) -> PendingElicitation {
    PendingElicitation(payload: [
      "dispatchId": id, "ownerId": "o1", "sessionId": "s1", "mode": "question",
      "title": "Omi is asking", "prompt": "Q \(id)",
      "options": [["optionId": "yes", "label": "Yes", "effect": "choice"]],
      "allowsFreeText": true,
    ])!
  }

  private func makeStore() -> (ElicitationStore, () -> [(PendingElicitation, ElicitationAnswer)]) {
    var sent: [(PendingElicitation, ElicitationAnswer)] = []
    return (ElicitationStore { sent.append(($0, $1)) }, { sent })
  }

  func testChoosingAnOptionSendsNothingUntilSend() {
    let (store, sent) = makeStore()
    let one = pending("a")
    store.enqueue(one)

    store.stage(.option("yes"), for: one)
    XCTAssertTrue(sent().isEmpty, "choosing must not send")
    XCTAssertEqual(store.waitingCount, 1, "the card stays until sent")

    store.submitFocused()
    XCTAssertEqual(sent().count, 1)
    XCTAssertEqual(store.waitingCount, 0)
  }

  func testSendDoesNothingWithoutAChoice() {
    let (store, sent) = makeStore()
    store.enqueue(pending("a"))

    store.submitFocused()

    XCTAssertTrue(sent().isEmpty)
    XCTAssertEqual(store.waitingCount, 1)
  }

  func testTheUserCanMoveBetweenQuestionsInAnyOrder() {
    let (store, _) = makeStore()
    let a = pending("a")
    let c = pending("c")
    store.enqueue(a)
    store.enqueue(pending("b"))
    store.enqueue(c)

    XCTAssertEqual(store.focused?.id, "a")
    store.focus(c)
    XCTAssertEqual(store.focused?.id, "c")
    XCTAssertEqual(store.focusedIndex, 2)

    store.focusNext()
    XCTAssertEqual(store.focused?.id, "a", "stepping past the end wraps")
    store.focusPrevious()
    XCTAssertEqual(store.focused?.id, "c")
  }

  func testChoicesSurviveMovingBetweenQuestions() {
    let (store, sent) = makeStore()
    let a = pending("a")
    let b = pending("b")
    store.enqueue(a)
    store.enqueue(b)

    store.stage(.option("yes"), for: a)
    store.focus(b)
    store.stage(.text("later"), for: b)
    store.focus(a)

    XCTAssertEqual(store.staged[a.id], .option("yes"), "returning shows the earlier choice")
    XCTAssertEqual(store.staged[b.id], .text("later"))

    store.submitFocused()
    XCTAssertEqual(sent().count, 1)
    XCTAssertEqual(sent().first?.1, .option("yes"))
    XCTAssertEqual(store.staged[b.id], .text("later"), "sending one keeps the other's choice")
  }

  func testAnsweringMovesFocusToWhatTookItsPlace() {
    let (store, _) = makeStore()
    let a = pending("a")
    store.enqueue(a)
    store.enqueue(pending("b"))

    store.stage(.option("yes"), for: a)
    store.submitFocused()

    XCTAssertEqual(store.focused?.id, "b")
  }

  func testRetiringTheFocusedQuestionDropsItsStagedChoice() {
    let (store, _) = makeStore()
    let a = pending("a")
    store.enqueue(a)
    store.stage(.option("yes"), for: a)

    store.remove(id: "a")

    XCTAssertNil(store.staged["a"])
    XCTAssertNil(store.focused)
  }

  func testFocusingAQuestionThatIsNotQueuedIsIgnored() {
    let (store, _) = makeStore()
    let a = pending("a")
    store.enqueue(a)

    store.focus(pending("ghost"))

    XCTAssertEqual(store.focused?.id, "a")
  }
}
