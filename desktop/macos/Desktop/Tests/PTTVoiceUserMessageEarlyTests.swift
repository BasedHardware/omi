import XCTest

@testable import Omi_Computer

/// Voice/PTT questions must appear in chat the instant they're transcribed — via
/// `beginVoiceUserMessage` — and the completed turn must reconcile against THAT turn's
/// bubble (by explicit id, never a shared global) so an out-of-order async completion
/// can't rewrite a different turn's bubble. These exercise the synchronous message-array
/// mutations of the real `ChatProvider`; the backend save fired by `recordCompletedTurn`
/// is a fire-and-forget Task that runs after the assertions and is irrelevant here.
@MainActor
final class PTTVoiceUserMessageEarlyTests: XCTestCase {

  private func userTexts(_ p: ChatProvider) -> [String] {
    p.messages.filter { $0.sender == .user }.map(\.text)
  }
  private func aiTexts(_ p: ChatProvider) -> [String] {
    p.messages.filter { $0.sender == .ai }.map(\.text)
  }

  /// The question bubble shows immediately, before any reply exists.
  func testBeginShowsUserQuestionImmediately() {
    let p = ChatProvider()
    p.beginVoiceUserMessage(userText: "what is the capital of France")
    XCTAssertEqual(userTexts(p), ["what is the capital of France"])
    XCTAssertTrue(aiTexts(p).isEmpty, "reply must not exist yet")
  }

  /// Completing the turn appends the reply and reuses the early bubble (matched by id) —
  /// exactly one user message, not two.
  func testCompletionReusesEarlyBubbleNoDuplicate() {
    let p = ChatProvider()
    let early = p.beginVoiceUserMessage(userText: "hi there")
    let (user, ai) = p.recordCompletedTurn(
      userText: "hi there", assistantText: "hello!", earlyUserMessageId: early?.id)
    XCTAssertEqual(userTexts(p), ["hi there"], "must not duplicate the user bubble")
    XCTAssertEqual(aiTexts(p), ["hello!"])
    XCTAssertEqual(p.messages.count, 2)
    XCTAssertEqual(user?.id, early?.id, "reused the same bubble")
    XCTAssertNotNil(ai)
  }

  /// If the final transcript was language-corrected after the early show, the existing
  /// bubble's text is updated in place — still a single user message.
  func testCompletionReconcilesCorrectedText() {
    let p = ChatProvider()
    let early = p.beginVoiceUserMessage(userText: "provider misdetect")  // early, uncorrected
    p.recordCompletedTurn(
      userText: "corrected question", assistantText: "reply", earlyUserMessageId: early?.id)
    XCTAssertEqual(userTexts(p), ["corrected question"])
    XCTAssertEqual(p.messages.filter { $0.sender == .user }.count, 1)
  }

  /// Without an early show (e.g. a provider that never fires the trigger), the
  /// completed turn still appends both messages — unchanged legacy behavior.
  func testCompletionWithoutEarlyShowAppendsBoth() {
    let p = ChatProvider()
    let (user, ai) = p.recordCompletedTurn(userText: "typed-like", assistantText: "answer")
    XCTAssertEqual(userTexts(p), ["typed-like"])
    XCTAssertEqual(aiTexts(p), ["answer"])
    XCTAssertNotNil(user)
    XCTAssertNotNil(ai)
  }

  /// An empty/whitespace transcript shows nothing (no blank bubble).
  func testEmptyTranscriptShowsNothing() {
    let p = ChatProvider()
    XCTAssertNil(p.beginVoiceUserMessage(userText: "   "))
    XCTAssertTrue(p.messages.isEmpty)
  }

  /// Two voice turns in a row each produce exactly one user bubble.
  func testConsecutiveTurnsEachGetOwnBubble() {
    let p = ChatProvider()
    let e1 = p.beginVoiceUserMessage(userText: "first question")
    p.recordCompletedTurn(
      userText: "first question", assistantText: "first reply", earlyUserMessageId: e1?.id)
    let e2 = p.beginVoiceUserMessage(userText: "second question")
    p.recordCompletedTurn(
      userText: "second question", assistantText: "second reply", earlyUserMessageId: e2?.id)
    XCTAssertEqual(userTexts(p), ["first question", "second question"])
    XCTAssertEqual(aiTexts(p), ["first reply", "second reply"])
  }

  /// Race guard: turn 2 begins before turn 1's (async) completion runs. Each completion
  /// must reconcile ITS OWN bubble by id — a shared global id would let turn 1's late
  /// completion overwrite turn 2's bubble and corrupt history.
  func testInterleavedTurnsDoNotCorruptEachOther() {
    let p = ChatProvider()
    let e1 = p.beginVoiceUserMessage(userText: "Q1")   // turn 1 shows
    let e2 = p.beginVoiceUserMessage(userText: "Q2")   // turn 2 shows before turn 1 completes
    XCTAssertNotEqual(e1?.id, e2?.id)
    // completions arrive (turn 1 then turn 2), each carrying its own captured id
    p.recordCompletedTurn(userText: "Q1", assistantText: "R1", earlyUserMessageId: e1?.id)
    p.recordCompletedTurn(userText: "Q2", assistantText: "R2", earlyUserMessageId: e2?.id)
    XCTAssertEqual(userTexts(p), ["Q1", "Q2"], "each bubble kept its own text")
    XCTAssertEqual(aiTexts(p), ["R1", "R2"])
    XCTAssertEqual(p.messages.filter { $0.sender == .user }.count, 2, "no duplicate/lost bubble")
  }

  /// Same race but completions arrive OUT OF ORDER (turn 2 completes first). Still no
  /// cross-turn corruption — the id, not arrival order, decides which bubble is reused.
  func testOutOfOrderCompletionsReconcileCorrectBubble() {
    let p = ChatProvider()
    let e1 = p.beginVoiceUserMessage(userText: "Q1")
    let e2 = p.beginVoiceUserMessage(userText: "Q2")
    p.recordCompletedTurn(userText: "Q2", assistantText: "R2", earlyUserMessageId: e2?.id)
    p.recordCompletedTurn(userText: "Q1", assistantText: "R1", earlyUserMessageId: e1?.id)
    // Q1 and Q2 bubbles both retain their original text (neither overwrote the other).
    let users = p.messages.filter { $0.sender == .user }
    XCTAssertEqual(users.count, 2)
    XCTAssertEqual(users.first(where: { $0.id == e1?.id })?.text, "Q1")
    XCTAssertEqual(users.first(where: { $0.id == e2?.id })?.text, "Q2")
  }
}
