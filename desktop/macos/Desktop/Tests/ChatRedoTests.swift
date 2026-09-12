import XCTest

@testable import Omi_Computer

/// Redo under an answer re-asks that answer's own question. Two decisions carry
/// it, and both are values so they can be driven without mounting a transcript:
/// which question a row re-asks (`ChatRedoTarget`), and what the resulting send
/// is allowed to do (`QueryShellSendLedger.planRedo`).
final class ChatRedoTests: XCTestCase {

  private func msg(_ id: String, _ text: String, _ sender: ChatSender) -> ChatMessage {
    ChatMessage(id: id, text: text, sender: sender)
  }

  private func proactiveNotification(_ id: String, _ text: String) -> ChatMessage {
    ChatMessage(
      id: id,
      clientTurnId: ChatContinuityInvariants.proactiveNotificationContinuityKey(
        id: UUID(), kind: .insight),
      text: text, sender: .ai)
  }

  // MARK: - Which question a row re-asks

  func testRedoAsksTheQuestionDirectlyAboveTheAnswer() {
    let messages = [
      msg("u1", "what changed today?", .user),
      msg("a1", "three things changed", .ai),
    ]
    XCTAssertEqual(
      ChatRedoTarget.question(forMessageID: "a1", in: messages), "what changed today?")
  }

  /// The reader scrolled back and redid an OLDER answer: it must re-ask that
  /// answer's question, never the most recent one.
  func testRedoOfAnOlderAnswerAsksThatAnswersOwnQuestion() {
    let messages = [
      msg("u1", "first question", .user),
      msg("a1", "first answer", .ai),
      msg("u2", "second question", .user),
      msg("a2", "second answer", .ai),
    ]
    XCTAssertEqual(ChatRedoTarget.question(forMessageID: "a1", in: messages), "first question")
    XCTAssertEqual(ChatRedoTarget.question(forMessageID: "a2", in: messages), "second question")
  }

  /// An answer preceded by another assistant row (a tool trace, a proactive
  /// note) still walks up to the question rather than stopping at the row above.
  func testRedoWalksPastInterveningAssistantRows() {
    let messages = [
      msg("u1", "why is the build red?", .user),
      msg("a1", "checking", .ai),
      msg("a2", "the release compile fails", .ai),
    ]
    XCTAssertEqual(
      ChatRedoTarget.question(forMessageID: "a2", in: messages), "why is the build red?")
  }

  func testUserTurnHasNothingToRedo() {
    let messages = [msg("u1", "what changed today?", .user), msg("a1", "answer", .ai)]
    XCTAssertNil(ChatRedoTarget.question(forMessageID: "u1", in: messages))
  }

  /// An assistant row with no question above it — a proactive notification, or
  /// a transcript whose question scrolled out of history — offers no Redo at
  /// all rather than a control that re-asks nothing.
  func testAnswerWithNoQuestionAboveItOffersNoRedo() {
    let messages = [msg("a1", "you have a meeting in five minutes", .ai)]
    XCTAssertNil(ChatRedoTarget.question(forMessageID: "a1", in: messages))
    XCTAssertNil(ChatRedoTarget.question(forMessageID: "missing", in: messages))
  }

  func testWhitespaceOnlyQuestionIsNotRedoable() {
    let messages = [msg("u1", "   \n ", .user), msg("a1", "answer", .ai)]
    XCTAssertNil(ChatRedoTarget.question(forMessageID: "a1", in: messages))
  }

  /// A proactive notification is unprompted even when a user turn precedes it:
  /// it gets no question, so no Redo, while the ordinary answer below it keeps
  /// the question it really came from.
  func testProactiveNotificationUnderAUserTurnGetsNoRedo() {
    let messages = [
      msg("u1", "what changed today?", .user),
      proactiveNotification("n1", "you have a meeting in five minutes"),
      msg("a1", "three things changed", .ai),
    ]
    XCTAssertNil(ChatRedoTarget.question(forMessageID: "n1", in: messages))
    XCTAssertNil(ChatRedoTarget.questionsByAnswerID(in: messages)["n1"])
    XCTAssertEqual(ChatRedoTarget.questionsByAnswerID(in: messages)["a1"], "what changed today?")
  }

  /// The transcript body resolves every row at once rather than walking the
  /// history per row (a streamed token re-evaluates that body). The batch has
  /// to answer exactly what the per-row walk answers, including the rows that
  /// have no question above them.
  func testBatchQuestionLookupMatchesThePerRowWalk() {
    let messages = [
      msg("a0", "you have a meeting in five minutes", .ai),
      msg("u1", "first question", .user),
      proactiveNotification("n1", "your focus block ends soon"),
      msg("a1", "first answer", .ai),
      msg("a1b", "still the first question's answer", .ai),
      msg("u2", "   \n ", .user),
      msg("a2", "answer to a blank question", .ai),
      msg("u3", "third question", .user),
      msg("a3", "third answer", .ai),
    ]
    let batch = ChatRedoTarget.questionsByAnswerID(in: messages)
    for message in messages {
      XCTAssertEqual(
        batch[message.id],
        ChatRedoTarget.question(forMessageID: message.id, in: messages),
        "row \(message.id)")
    }
    XCTAssertEqual(batch["a3"], "third question")
    XCTAssertNil(batch["a0"])
    XCTAssertNil(batch["n1"])
    XCTAssertNil(batch["a2"])
  }

  // MARK: - Where the redone answer is drawn

  /// The transcript is `Q, A`; redoing `A` appends `Q(redo), A2`. What the
  /// reader must see is `Q, A2` — the new answer in the old one's place, their
  /// question asked once.
  private func redoTurn(_ nonce: String, replacing answerID: String, question: String, answer: String)
    -> [ChatMessage]
  {
    let key = "redo:\(nonce):\(answerID)"
    return [
      ChatMessage(id: key, clientTurnId: key, text: question, sender: .user),
      ChatMessage(id: "\(key)-assistant", clientTurnId: key, text: answer, sender: .ai),
    ]
  }

  func testRedoneAnswerReplacesTheOldOneInPlace() {
    let base = [msg("u1", "what changed today?", .user), msg("a1", "first answer", .ai)]
    let projected = ChatRedoDisplayProjection.project(
      base + redoTurn("n1", replacing: "a1", question: "what changed today?", answer: "second answer"))

    XCTAssertEqual(projected.map(\.id), ["u1", "redo:n1:a1-assistant"])
    XCTAssertEqual(projected.map(\.text), ["what changed today?", "second answer"])
  }

  /// Redoing an OLDER answer replaces that answer where it sits; every later
  /// exchange keeps its own place below it.
  func testRedoOfAnOlderAnswerKeepsTheRestOfTheThreadInPlace() {
    let base = [
      msg("u1", "first question", .user),
      msg("a1", "first answer", .ai),
      msg("u2", "second question", .user),
      msg("a2", "second answer", .ai),
    ]
    let projected = ChatRedoDisplayProjection.project(
      base + redoTurn("n1", replacing: "a1", question: "first question", answer: "better first answer"))

    XCTAssertEqual(
      projected.map(\.text),
      [
        "first question", "better first answer", "second question", "second answer",
      ])
  }

  /// Redoing a redo replaces the same original slot, not the row below it.
  func testRedoOfARedoStillOccupiesTheOriginalSlot() {
    let base = [msg("u1", "q", .user), msg("a1", "first", .ai)]
    let once = base + redoTurn("n1", replacing: "a1", question: "q", answer: "second")
    let twice = once + redoTurn("n2", replacing: "redo:n1:a1-assistant", question: "q", answer: "third")

    XCTAssertEqual(ChatRedoDisplayProjection.project(twice).map(\.text), ["q", "third"])
  }

  /// A redo whose answer never arrived (the turn failed, so the journal
  /// projection dropped its empty assistant row) must leave the original answer
  /// standing rather than blanking the slot.
  func testFailedRedoLeavesTheOriginalAnswerVisible() {
    let base = [msg("u1", "q", .user), msg("a1", "first answer", .ai)]
    let userRowOnly = Array(redoTurn("n1", replacing: "a1", question: "q", answer: "unused").prefix(1))

    XCTAssertEqual(
      ChatRedoDisplayProjection.project(base + userRowOnly).map(\.text),
      [
        "q", "first answer",
      ])
  }

  /// The same failure with the notice persisted ON the assistant row
  /// (`applyTurnFailureMarker`): the error text is not an answer, so it must
  /// not take the replaced answer's slot — the original answer stays standing.
  func testFailedRedoWithErrorNoticeLeavesTheOriginalAnswerStanding() {
    let base = [msg("u1", "q", .user), msg("a1", "first answer", .ai)]
    var turn = redoTurn("n1", replacing: "a1", question: "q", answer: "unused")
    turn[1].text = "The answer didn't come back. Try again."
    turn[1].journalStatus = .failed

    XCTAssertEqual(
      ChatRedoDisplayProjection.project(base + turn).map(\.text),
      ["q", "first answer"])
  }

  /// The answer being replaced can be older than the mounted window. Hiding the
  /// redo rows then would draw nothing at all, so they render where they are.
  func testRedoRendersInPlaceWhenTheReplacedAnswerIsNotLoaded() {
    let projected = ChatRedoDisplayProjection.project(
      redoTurn("n1", replacing: "a-not-loaded", question: "q", answer: "answer"))

    XCTAssertEqual(projected.map(\.text), ["q", "answer"])
  }

  func testTranscriptWithoutRedoIsUnchanged() {
    let base = [msg("u1", "q", .user), msg("a1", "a", .ai)]
    XCTAssertEqual(ChatRedoDisplayProjection.project(base).map(\.id), ["u1", "a1"])
  }

  // MARK: - The key that carries the replacement

  func testRedoContinuityKeyNamesTheAnswerItReplaces() {
    let key = ChatContinuityInvariants.redoContinuityKey(supersedingMessageID: "turn_abc-assistant")
    XCTAssertTrue(key.hasPrefix("redo:"))
    XCTAssertEqual(
      ChatContinuityInvariants.supersededMessageID(fromContinuityKey: key), "turn_abc-assistant")
  }

  /// The id being replaced may itself contain colons — a proactive
  /// notification's turn, or a previous redo — so only the nonce separator ends.
  func testRedoKeyRoundTripsAnIDContainingColons() {
    let key = ChatContinuityInvariants.redoContinuityKey(
      supersedingMessageID: "notification:general:ABC-assistant")
    XCTAssertEqual(
      ChatContinuityInvariants.supersededMessageID(fromContinuityKey: key),
      "notification:general:ABC-assistant")
  }

  func testOrdinaryContinuityKeysSupersedeNothing() {
    XCTAssertNil(ChatContinuityInvariants.supersededMessageID(fromContinuityKey: nil))
    XCTAssertNil(ChatContinuityInvariants.supersededMessageID(fromContinuityKey: UUID().uuidString))
    XCTAssertNil(
      ChatContinuityInvariants.supersededMessageID(fromContinuityKey: "notification:ABC"))
    XCTAssertNil(ChatContinuityInvariants.supersededMessageID(fromContinuityKey: "redo:nonce:"))
  }

  // MARK: - What the redo send may do

  /// A redo is the same logical question asked again: it keeps its analytics
  /// event but must never advance the one-time rating-prompt trigger.
  func testRedoNeverRecountsTheQuestion() {
    let ledger = QueryShellSendLedger()
    guard let plan = ledger.planRedo("what changed today?", replacingAnswerID: "a1") else {
      return XCTFail("a non-empty question must produce a redo plan")
    }
    XCTAssertEqual(plan.question, "what changed today?")
    XCTAssertFalse(plan.countsAsQuestion)
  }

  /// A submit empties the composer, so a refusal has to hand the question back.
  /// A redo never took the composer's contents, so a refused redo must leave
  /// whatever the reader is typing exactly where it is.
  func testRefusedRedoDoesNotWriteIntoTheComposer() {
    let ledger = QueryShellSendLedger()
    XCTAssertEqual(ledger.planSubmit("typed question")?.returnsToComposerIfRefused, true)
    XCTAssertEqual(
      ledger.planRedo("redone question", replacingAnswerID: "a1")?.returnsToComposerIfRefused,
      false)
  }

  /// The plan carries the key that names the replaced answer; a submit carries
  /// none, so an ordinary question replaces nothing.
  func testOnlyARedoPlanCarriesAReplacementKey() {
    let ledger = QueryShellSendLedger()
    XCTAssertNil(ledger.planSubmit("typed question")?.continuityKey)
    XCTAssertEqual(
      ChatContinuityInvariants.supersededMessageID(
        fromContinuityKey: ledger.planRedo("q", replacingAnswerID: "a1")?.continuityKey),
      "a1")
  }

  func testEmptyQuestionOrAnswerPlansNoRedo() {
    let ledger = QueryShellSendLedger()
    XCTAssertNil(ledger.planRedo("", replacingAnswerID: "a1"))
    XCTAssertNil(ledger.planRedo("   \n", replacingAnswerID: "a1"))
    XCTAssertNil(ledger.planRedo("q", replacingAnswerID: " "))
  }

  /// After an accepted redo, the question in flight is the redone one — so if
  /// THAT turn fails, `Try again` must re-send it and not the newer question
  /// the reader had asked before scrolling back.
  func testTryAgainAfterARedoResendsTheRedoneQuestion() {
    var ledger = QueryShellSendLedger()
    guard let submit = ledger.planSubmit("second question") else {
      return XCTFail("a resolved submit must produce a send plan")
    }
    ledger.recordAccepted(submit)
    XCTAssertEqual(ledger.planRetry()?.question, "second question")

    guard let redo = ledger.planRedo("first question", replacingAnswerID: "a1") else {
      return XCTFail("a non-empty question must produce a redo plan")
    }
    ledger.recordAccepted(redo)
    XCTAssertEqual(ledger.planRetry()?.question, "first question")
    XCTAssertEqual(ledger.planRetry()?.countsAsQuestion, false)
  }
}
