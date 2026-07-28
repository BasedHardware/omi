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

  func testAnAnswerCanCarryChosenOptionsAndTheUsersOwnWords() throws {
    let elicitation = try XCTUnwrap(PendingElicitation(payload: payload(mode: "question")))
    let wire = try XCTUnwrap(
      ElicitationWire.resolvePayload(
        dispatchID: elicitation.id,
        ownerID: elicitation.ownerID,
        currentOwnerID: elicitation.ownerID,
        answer: .answer(optionIDs: ["once", "no"], text: "and this")))

    // A pick-many question is legitimately answered "these two, plus this", so
    // neither part silently discards the other.
    XCTAssertEqual(wire["optionIds"] as? [String], ["once", "no"])
    XCTAssertEqual(wire["text"] as? String, "and this")
  }

  func testAnEmptyAnswerCarriesNeitherKey() throws {
    let elicitation = try XCTUnwrap(PendingElicitation(payload: payload(mode: "question")))
    let wire = try XCTUnwrap(
      ElicitationWire.resolvePayload(
        dispatchID: elicitation.id,
        ownerID: elicitation.ownerID,
        currentOwnerID: elicitation.ownerID,
        answer: .answer(optionIDs: [], text: nil)))

    XCTAssertNil(wire["optionIds"])
    XCTAssertNil(wire["text"])
    XCTAssertTrue(ElicitationAnswer.answer(optionIDs: [], text: "").isEmpty)
    XCTAssertFalse(ElicitationAnswer.answer(optionIDs: [], text: "x").isEmpty)
  }

  func testAWaitingQuestionArmsADeadlineThatInteractionPushesBack() throws {
    let (store, _) = makeStore()
    let elicitation = try XCTUnwrap(PendingElicitation(payload: payload(mode: "question")))
    XCTAssertNil(store.deadline, "nothing is waiting, so nothing is counting down")

    store.enqueue(elicitation)
    let armed = try XCTUnwrap(store.deadline)
    XCTAssertEqual(
      armed.timeIntervalSinceNow, ElicitationStore.idleTimeout, accuracy: 2,
      "a question arriving starts the budget")

    // The budget is idle-based, not total: working on the answer buys it back.
    store.stage(.options(["once"]), for: elicitation)
    let afterChoosing = try XCTUnwrap(store.deadline)
    XCTAssertGreaterThanOrEqual(afterChoosing, armed)
  }

  func testTheClockStopsWhenNothingIsWaiting() throws {
    let (store, _) = makeStore()
    let elicitation = try XCTUnwrap(PendingElicitation(payload: payload(mode: "question")))
    store.enqueue(elicitation)
    XCTAssertNotNil(store.deadline)

    // Answering the last question retires the card, so a countdown pointing at
    // nothing must not keep running.
    store.answer(elicitation, with: .options(["once"]))
    XCTAssertNil(store.deadline)
    XCTAssertNil(store.secondsRemaining)
  }

  func testExpirySendsWhatWasAnsweredAndCancelsTheRest() throws {
    let (store, submitted) = makeStore()
    let first = try XCTUnwrap(PendingElicitation(payload: payload(dispatchID: "a", mode: "question")))
    let second = try XCTUnwrap(PendingElicitation(payload: payload(dispatchID: "b", mode: "question")))
    store.enqueue(first)
    store.enqueue(second)
    store.stage(.options(["once"]), for: first)

    // Expiry is the same act as Send: the work the user did give is delivered
    // rather than thrown away with the questions they never reached.
    store.submitAll()

    XCTAssertEqual(submitted().map(\.0.id), ["a", "b"])
    XCTAssertEqual(submitted().map(\.1), [.options(["once"]), .cancel])
    XCTAssertTrue(store.queue.isEmpty)
    XCTAssertNil(store.deadline)
  }

  func testAPermissionIsNeverMultiSelectHoweverThePayloadArrives() throws {
    // An ACP response names exactly one option, so a pick-many control there
    // would build an answer the protocol cannot send.
    var claimsMultiple = payload(mode: "permission")
    claimsMultiple["allowsMultiple"] = true
    XCTAssertFalse(try XCTUnwrap(PendingElicitation(payload: claimsMultiple)).allowsMultiple)
  }

  func testMultiSelectNeedsOptionsToPickFrom() throws {
    var noOptions = payload(mode: "question", options: [])
    noOptions["allowsMultiple"] = true
    // Pick-many with nothing to pick is just a free-text question.
    XCTAssertFalse(try XCTUnwrap(PendingElicitation(payload: noOptions)).allowsMultiple)

    var withOptions = payload(mode: "question")
    withOptions["allowsMultiple"] = true
    XCTAssertTrue(try XCTUnwrap(PendingElicitation(payload: withOptions)).allowsMultiple)
  }

  func testAnswerCarriesEveryChosenOptionToTheKernel() throws {
    let elicitation = try XCTUnwrap(PendingElicitation(payload: payload(mode: "question")))
    let wire = try XCTUnwrap(
      ElicitationWire.resolvePayload(
        dispatchID: elicitation.id,
        ownerID: elicitation.ownerID,
        currentOwnerID: elicitation.ownerID,
        answer: .options(["once", "no"])))

    XCTAssertEqual(wire["decision"] as? String, "answer")
    XCTAssertEqual(wire["optionIds"] as? [String], ["once", "no"])
  }

  func testCarriesTheAgentsRecommendationWithoutActingOnIt() throws {
    var body = payload()
    body["recommendedDefault"] = "once"
    let elicitation = try XCTUnwrap(PendingElicitation(payload: body))

    XCTAssertEqual(elicitation.recommendedDefault, "once")

    // The recommendation is advisory. Nothing is staged, so nothing can be sent
    // without the user choosing it: a default that answers itself is not consent.
    let (store, submitted) = makeStore()
    store.enqueue(elicitation)
    store.submitFocused()
    XCTAssertTrue(submitted().isEmpty)
    XCTAssertNil(store.stagedForFocused)
  }

  func testIgnoresARecommendationThatNamesNoOfferedOption() throws {
    var unknown = payload()
    unknown["recommendedDefault"] = "not-an-offered-option"
    XCTAssertNil(try XCTUnwrap(PendingElicitation(payload: unknown)).recommendedDefault)

    // Absent is the common case and must not resolve to an arbitrary option.
    XCTAssertNil(try XCTUnwrap(PendingElicitation(payload: payload())).recommendedDefault)
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

    store.stage(.options(["once"]), for: first)
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

    store.answer(elicitation, with: .options(["no"]))
    store.answer(elicitation, with: .options(["once"]))

    XCTAssertEqual(submitted().count, 1)
    XCTAssertEqual(submitted().first?.1, .options(["no"]))
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
  private func pending(_ id: String) throws -> PendingElicitation {
    try XCTUnwrap(
      PendingElicitation(payload: [
        "dispatchId": id, "ownerId": "o1", "sessionId": "s1", "mode": "question",
        "title": "Omi is asking", "prompt": "Q \(id)",
        "options": [["optionId": "yes", "label": "Yes", "effect": "choice"]],
        "allowsFreeText": true,
      ]))
  }

  private func makeStore() -> (ElicitationStore, () -> [(PendingElicitation, ElicitationAnswer)]) {
    var sent: [(PendingElicitation, ElicitationAnswer)] = []
    return (ElicitationStore { sent.append(($0, $1)) }, { sent })
  }

  func testChoosingAnOptionSendsNothingUntilSend() throws {
    let (store, sent) = makeStore()
    let one = try pending("a")
    store.enqueue(one)

    store.stage(.options(["yes"]), for: one)
    XCTAssertTrue(sent().isEmpty, "choosing must not send")
    XCTAssertEqual(store.waitingCount, 1, "the card stays until sent")

    store.submitFocused()
    XCTAssertEqual(sent().count, 1)
    XCTAssertEqual(store.waitingCount, 0)
  }

  func testSendDoesNothingWithoutAChoice() throws {
    let (store, sent) = makeStore()
    store.enqueue(try pending("a"))

    store.submitFocused()

    XCTAssertTrue(sent().isEmpty)
    XCTAssertEqual(store.waitingCount, 1)
  }

  func testTheUserCanMoveBetweenQuestionsInAnyOrder() throws {
    let (store, _) = makeStore()
    let a = try pending("a")
    let c = try pending("c")
    store.enqueue(a)
    store.enqueue(try pending("b"))
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

  func testChoicesSurviveMovingBetweenQuestions() throws {
    let (store, sent) = makeStore()
    let a = try pending("a")
    let b = try pending("b")
    store.enqueue(a)
    store.enqueue(b)

    store.stage(.options(["yes"]), for: a)
    store.focus(b)
    store.stage(.text("later"), for: b)
    store.focus(a)

    XCTAssertEqual(store.staged[a.id], .options(["yes"]), "returning shows the earlier choice")
    XCTAssertEqual(store.staged[b.id], .text("later"))

    store.submitFocused()
    XCTAssertEqual(sent().count, 1)
    XCTAssertEqual(sent().first?.1, .options(["yes"]))
    XCTAssertEqual(store.staged[b.id], .text("later"), "sending one keeps the other's choice")
  }

  func testAnsweringMovesFocusToWhatTookItsPlace() throws {
    let (store, _) = makeStore()
    let a = try pending("a")
    store.enqueue(a)
    store.enqueue(try pending("b"))

    store.stage(.options(["yes"]), for: a)
    store.submitFocused()

    XCTAssertEqual(store.focused?.id, "b")
  }

  func testRetiringTheFocusedQuestionDropsItsStagedChoice() throws {
    let (store, _) = makeStore()
    let a = try pending("a")
    store.enqueue(a)
    store.stage(.options(["yes"]), for: a)

    store.remove(id: "a")

    XCTAssertNil(store.staged["a"])
    XCTAssertNil(store.focused)
  }

  func testFocusingAQuestionThatIsNotQueuedIsIgnored() throws {
    let (store, _) = makeStore()
    let a = try pending("a")
    store.enqueue(a)

    store.focus(try pending("ghost"))

    XCTAssertEqual(store.focused?.id, "a")
  }
}

@MainActor
final class ElicitationBatchTests: XCTestCase {
  private func pending(_ id: String) throws -> PendingElicitation {
    try XCTUnwrap(
      PendingElicitation(payload: [
        "dispatchId": id, "ownerId": "o1", "sessionId": "s1", "mode": "question",
        "title": "Omi is asking", "prompt": "Q \(id)",
        "options": [["optionId": "yes", "label": "Yes", "effect": "choice"]],
        "allowsFreeText": true,
      ]))
  }

  private func makeStore() -> (ElicitationStore, () -> [(PendingElicitation, ElicitationAnswer)]) {
    var sent: [(PendingElicitation, ElicitationAnswer)] = []
    return (ElicitationStore { sent.append(($0, $1)) }, { sent })
  }

  func testSendingTheBatchDeliversEveryChoiceAtOnce() throws {
    let (store, sent) = makeStore()
    let a = try pending("a")
    let b = try pending("b")
    store.enqueue(a)
    store.enqueue(b)
    store.stage(.options(["yes"]), for: a)
    store.stage(.text("later"), for: b)

    store.submitAll()

    XCTAssertEqual(sent().count, 2)
    XCTAssertEqual(sent().first(where: { $0.0.id == "a" })?.1, .options(["yes"]))
    XCTAssertEqual(sent().first(where: { $0.0.id == "b" })?.1, .text("later"))
    XCTAssertEqual(store.waitingCount, 0)
  }

  func testAQuestionPassedOverIsCancelledRatherThanLeftPending() throws {
    // A question nobody answers would block its agent forever.
    let (store, sent) = makeStore()
    let a = try pending("a")
    store.enqueue(a)
    store.enqueue(try pending("b"))
    store.stage(.options(["yes"]), for: a)

    store.submitAll()

    XCTAssertEqual(sent().first(where: { $0.0.id == "b" })?.1, .cancel)
    XCTAssertEqual(store.waitingCount, 0, "the batch drains completely")
  }

  func testSendingWithNothingChosenCancelsTheWholeBatch() throws {
    let (store, sent) = makeStore()
    store.enqueue(try pending("a"))
    store.enqueue(try pending("b"))

    store.submitAll()

    XCTAssertEqual(sent().count, 2)
    XCTAssertTrue(sent().allSatisfy { $0.1 == .cancel })
  }
}
