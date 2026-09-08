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

  // MARK: - What the redo send may do

  /// A redo is the same logical question asked again: it keeps its analytics
  /// event but must never advance the one-time rating-prompt trigger.
  func testRedoNeverRecountsTheQuestion() {
    let ledger = QueryShellSendLedger()
    guard let plan = ledger.planRedo("what changed today?") else {
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
    XCTAssertEqual(ledger.planRedo("redone question")?.returnsToComposerIfRefused, false)
  }

  func testEmptyQuestionPlansNoRedo() {
    let ledger = QueryShellSendLedger()
    XCTAssertNil(ledger.planRedo(""))
    XCTAssertNil(ledger.planRedo("   \n"))
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

    guard let redo = ledger.planRedo("first question") else {
      return XCTFail("a non-empty question must produce a redo plan")
    }
    ledger.recordAccepted(redo)
    XCTAssertEqual(ledger.planRetry()?.question, "first question")
    XCTAssertEqual(ledger.planRetry()?.countsAsQuestion, false)
  }
}
