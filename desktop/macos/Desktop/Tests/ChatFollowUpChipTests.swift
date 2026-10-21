import AppKit
import XCTest

@testable import Omi_Computer

/// The grounded closing question on the typed lanes.
///
/// The realtime voice lane ends about two thirds of its answers with a question
/// and runs about four turns; the chat window and the floating bar end with one
/// 4-9% of the time, and recall answers never do. These assert the three things
/// that have to hold for the chip to be worth anything: the tail leaves the
/// visible text exactly once, only a real question survives to become a chip,
/// and a question the chip produced is attributable as such.
@MainActor
final class ChatFollowUpChipTests: XCTestCase {

  override func setUp() async throws {
    QuestionOriginContext.resetForTests()
  }

  override func tearDown() async throws {
    QuestionOriginContext.resetForTests()
    AnalyticsManager.shared.questionTelemetryCaptureForTests = nil
  }

  // MARK: - Tail parsing

  func testTailIsLiftedOffTheVisibleAnswer() {
    let (visible, question) = ChatFollowUpTail.split(
      "You and Priya settled on shipping Thursday.\n\(ChatFollowUpTail.delimiter) Who else was in that call?"
    )
    XCTAssertEqual(visible, "You and Priya settled on shipping Thursday.")
    XCTAssertEqual(question, "Who else was in that call?")
    XCTAssertFalse(visible.contains(ChatFollowUpTail.delimiter))
  }

  func testAnswerWithoutATailIsUntouched() {
    let (visible, question) = ChatFollowUpTail.split("Nothing came up for that.")
    XCTAssertEqual(visible, "Nothing came up for that.")
    XCTAssertNil(question)
  }

  func testGenericAndMalformedTailsAreDroppedButStillStripped() {
    for tail in [
      "Anything else?", "Want more detail?", "Does that help?", "Let me know if you want more.",
      "I will check that next.", String(repeating: "word ", count: 30) + "?",
    ] {
      let (visible, question) = ChatFollowUpTail.split("Here it is.\n\(ChatFollowUpTail.delimiter) \(tail)")
      XCTAssertEqual(visible, "Here it is.", "tail: \(tail)")
      XCTAssertNil(question, "generic or malformed tail became a chip: \(tail)")
    }
  }

  /// The client's generic filter is the backend's `_GENERIC_PATTERNS`. Prefix
  /// matching dropped chips the server had already built and sent — anything
  /// merely *starting* with a generic phrase, however specific the rest.
  func testTheGenericFilterMatchesTheBackendRuleRatherThanAPrefix() {
    for generic in [
      "Anything else?", "Want more details?", "Do you want more information?",
      "Does that make sense?", "Any other questions?", "Shall I go on?",
      "Would you like to know more?", "What else?",
      // The prefix list matched "does that answer" and nothing else; the
      // backend's `(does|did) that (help|make sense|answer)` matches both.
      "Did that answer your question?",
    ] {
      XCTAssertTrue(ChatFollowUpTail.isGeneric(generic), "should be generic: \(generic)")
    }

    for specific in [
      "What else did Priya flag in that review?",
      "What else was decided in that standup?",
      "Want me to pull the Thursday thread?",
      "Does that Thursday date still hold?",
    ] {
      XCTAssertFalse(
        ChatFollowUpTail.isGeneric(specific),
        "a specific chip the backend accepts was dropped by the client: \(specific)")
    }
  }

  // MARK: - Streaming projection

  func testStreamingHidesACompletedTailAndAnUnambiguousPartialOne() {
    XCTAssertEqual(
      ChatFollowUpTail.strippingPendingTail("Shipped Thursday.\n\(ChatFollowUpTail.delimiter) Who else?"),
      "Shipped Thursday.\n")
    XCTAssertEqual(ChatFollowUpTail.strippingPendingTail("Shipped Thursday.\n<<<FOLL"), "Shipped Thursday.\n")
  }

  func testStreamingNeverEatsOrdinaryTextThatOnlyLooksLikeTheMarker() {
    XCTAssertEqual(ChatFollowUpTail.strippingPendingTail("a < b"), "a < b")
    XCTAssertEqual(ChatFollowUpTail.strippingPendingTail("compare a << b"), "compare a << b")
  }

  /// The projection is one-way, so it has to be fed the raw accumulated answer
  /// on every flush — never its own previous output plus the next delta. Under
  /// that contract no flush boundary can put a character of the tail on screen:
  /// whatever is shown is the visible answer, at most followed by a still
  /// ambiguous head of the delimiter (`<` or `<<`, which are left alone so real
  /// prose is never eaten).
  func testNoRawFlushBoundaryEverShowsAPieceOfTheTail() {
    let visible = "Shipped Thursday.\n"
    let answer = visible + ChatFollowUpTail.delimiter + " Who else was in that call?"
    for boundary in 1...answer.count {
      let shown = ChatFollowUpTail.strippingPendingTail(String(answer.prefix(boundary)))
      guard shown.hasPrefix(visible) || visible.hasPrefix(shown) else {
        return XCTFail("flush boundary \(boundary) showed non-answer text: \(shown)")
      }
      let extra = shown.hasPrefix(visible) ? String(shown.dropFirst(visible.count)) : ""
      XCTAssertTrue(
        ChatFollowUpTail.delimiter.hasPrefix(extra),
        "flush boundary \(boundary) leaked \(extra) into the visible answer")
    }
  }

  func testStreamingProjectionRunsOnTheAssistantTextPath() {
    XCTAssertEqual(
      ChatProvider.normalizeStreamingAssistantText(
        "Shipped Thursday.\n\(ChatFollowUpTail.delimiter) Who else was there?"),
      "Shipped Thursday.\n")
  }

  // MARK: - Attachment policy

  func testAFailedOrEmptyOrClarifyingTurnCarriesNoChip() {
    XCTAssertFalse(
      ChatFollowUpTail.shouldAttach(question: "Who else?", visibleText: "Something broke.", failed: true))
    XCTAssertFalse(ChatFollowUpTail.shouldAttach(question: "Who else?", visibleText: "   ", failed: false))
    XCTAssertFalse(
      ChatFollowUpTail.shouldAttach(
        question: "Who else?", visibleText: "Which standup — Monday or Thursday?", failed: false))
    XCTAssertFalse(ChatFollowUpTail.shouldAttach(question: nil, visibleText: "An answer.", failed: false))
  }

  func testAGroundedTurnCarriesTheChip() {
    XCTAssertTrue(
      ChatFollowUpTail.shouldAttach(
        question: "Who else was in that call?",
        visibleText: "You and Priya settled on shipping Thursday.",
        failed: false))
  }

  // MARK: - Codec

  func testFollowUpBlockRoundTripsThroughTheCodec() {
    let block = ChatContentBlock.followUp(id: "m1:followup", text: "Who else was in that call?")
    let encoded = ChatContentBlockCodec.encodeArray([block])
    XCTAssertEqual(
      encoded.first as? [String: String],
      ["type": "followUp", "id": "m1:followup", "text": "Who else was in that call?"])

    let decoded = ChatContentBlockCodec.decode(encoded)
    XCTAssertEqual(decoded.count, 1)
    guard case .followUp(let id, let text) = decoded[0] else {
      return XCTFail("followUp did not survive the round trip: \(decoded)")
    }
    XCTAssertEqual(id, "m1:followup")
    XCTAssertEqual(text, "Who else was in that call?")
  }

  func testCodecAcceptsTheBackendSnakeCaseTypeAndRejectsAnUnusableQuestion() {
    let accepted = ChatContentBlockCodec.decode([
      ["type": "follow_up", "id": "m1:followup", "text": "When is that review due?"]
    ])
    XCTAssertEqual(accepted.count, 1, "the backend's wire type must decode on the client")

    // A block that survived a bad generation must not become a chip that reads
    // as filler or as a statement.
    for text in ["", "Anything else?", "I will look into that next."] {
      XCTAssertTrue(
        ChatContentBlockCodec.decode([["type": "followUp", "id": "m1:followup", "text": text]]).isEmpty,
        "decoded an unusable follow-up: \(text)")
    }
  }

  func testBlockIDMatchesTheBackendShape() {
    XCTAssertEqual(ChatFollowUpTail.blockID(messageID: "msg-7"), "msg-7:followup")
  }

  // MARK: - The hermetic e2e contract

  /// The one stub reply that carries a tail, in the wire shape it is sent in.
  ///
  /// `chat-hermetic.yaml` S8 asserts both halves of this verbatim, and the
  /// backend pins the producer in `tests/unit/test_desktop_llm_stub.py`. This is
  /// the consumer half: if the client's rules ever stop admitting that answer,
  /// the flow starts asserting a chip that no longer appears, and it should fail
  /// here — in a second — rather than on a fifteen-minute tier-2 run.
  func testTheHermeticStubTailBecomesTheStringsTheFlowAsserts() {
    let answer = "Priya flagged the storage migration in the Tuesday review."
    let chipQuestion = "What did Priya say about the storage migration?"
    let wire = "\(answer)\n\n\(ChatFollowUpTail.delimiter) \(chipQuestion)"

    let (visible, question) = ChatFollowUpTail.split(wire)
    XCTAssertEqual(visible, answer)
    XCTAssertEqual(question, chipQuestion)
    XCTAssertFalse(
      visible.contains(chipQuestion),
      "the question must leave the prose entirely — the chip and the answer saying it twice is the defect")
    XCTAssertTrue(
      ChatFollowUpTail.shouldAttach(question: question, visibleText: visible, failed: false))
  }

  /// The field `chat-hermetic.yaml` S8 reads, and the value
  /// `tap_chat_follow_up_chip` sends. One reader, so a flow can never assert a
  /// chip the tap would then fail to find.
  func testTheAutomationSnapshotProjectsTheChipQuestionOutOfTheVisibleAnswer() {
    let provider = ChatProvider()
    let chipQuestion = "What did Priya say about the storage migration?"
    provider.messages = [
      ChatMessage(id: "user-1", text: "Recap the storage migration.", sender: .user),
      ChatMessage(
        id: "assistant-1",
        text: "Priya flagged the storage migration in the Tuesday review.",
        sender: .ai,
        contentBlocks: [
          .text(id: "assistant-1:text", text: "Priya flagged the storage migration in the Tuesday review."),
          .followUp(id: ChatFollowUpTail.blockID(messageID: "assistant-1"), text: chipQuestion),
        ]),
    ]

    XCTAssertEqual(provider.automationLastFollowUpQuestion(), chipQuestion)
    let snapshot = provider.automationMainChatSnapshot(limit: 10)
    XCTAssertEqual(snapshot["last_assistant_follow_up_question"], chipQuestion)
    XCTAssertEqual(
      snapshot["last_assistant_text"],
      "Priya flagged the storage migration in the Tuesday review.",
      "the visible answer must not carry the chip's question")
  }

  // MARK: - Attribution

  func testAChipQuestionIsAttributedToTheFollowUpOrigin() {
    var captured: [(String, [String: Any])] = []
    AnalyticsManager.shared.questionTelemetryCaptureForTests = { name, props in
      captured.append((name, props))
    }

    AnalyticsManager.shared.questionOriginating(.followUp)
    AnalyticsManager.shared.chatMessageSent(messageLength: 12, source: "follow_up_chip")

    let asked = captured.filter { $0.0 == "question_asked" }
    XCTAssertEqual(asked.count, 1)
    XCTAssertEqual(asked.first?.1["origin"] as? String, "followup")
    // Existing properties are untouched by the addition.
    XCTAssertEqual(asked.first?.1["surface"] as? String, "chat_window")
    XCTAssertEqual(asked.first?.1["source"] as? String, "follow_up_chip")
  }

  func testAnUnpromptedQuestionKeepsTheDefaultOriginAndTheArmIsOneShot() {
    var captured: [(String, [String: Any])] = []
    AnalyticsManager.shared.questionTelemetryCaptureForTests = { name, props in
      captured.append((name, props))
    }

    AnalyticsManager.shared.questionOriginating(.followUp)
    AnalyticsManager.shared.chatMessageSent(messageLength: 12, source: "follow_up_chip")
    AnalyticsManager.shared.chatMessageSent(messageLength: 4, source: "query_shell")

    let origins = captured.filter { $0.0 == "question_asked" }.map { $0.1["origin"] as? String }
    XCTAssertEqual(
      origins, ["followup", "unprompted"],
      "an armed origin must apply to exactly one question, never leak onto the next")
  }

  /// Arming happens at the tap, but the dispatch can return before anything is
  /// sent — no floating window, no provider — and then no question event ever
  /// consumes the arm. Without an explicit abort the arm survives and stamps
  /// `followup` on the next, unrelated question.
  func testAnAbortedDispatchDoesNotLeaveTheOriginArmed() {
    var captured: [(String, [String: Any])] = []
    AnalyticsManager.shared.questionTelemetryCaptureForTests = { name, props in
      captured.append((name, props))
    }

    AnalyticsManager.shared.questionOriginating(.followUp)
    AnalyticsManager.shared.questionOriginationAborted()
    AnalyticsManager.shared.chatMessageSent(messageLength: 4, source: "query_shell")

    let origins = captured.filter { $0.0 == "question_asked" }.map { $0.1["origin"] as? String }
    XCTAssertEqual(
      origins, ["unprompted"],
      "an arm whose send never happened must not label the next question")
  }

  // MARK: - Voice hint

  func testTheVoiceHintNamesTheBoundShortcutAndIsAbsentWhenPushToTalkIsOff() {
    let settings = ShortcutSettings.shared
    let wasEnabled = settings.pttEnabled
    defer { settings.pttEnabled = wasEnabled }

    settings.pttEnabled = false
    XCTAssertNil(FloatingControlBarView.followUpVoiceHint(settings: settings))

    settings.pttEnabled = true
    let hint = FloatingControlBarView.followUpVoiceHint(settings: settings)
    XCTAssertNotNil(hint)
    XCTAssertTrue(hint?.hasPrefix("or hold ") == true, "hint: \(hint ?? "nil")")
    XCTAssertTrue(hint?.hasSuffix(" to ask aloud") == true, "hint: \(hint ?? "nil")")
  }

  /// A chord binding renders as several tokens. Naming only the first told the
  /// user to hold a key that does not start voice.
  func testTheVoiceHintNamesEveryTokenOfAChordBinding() {
    let settings = ShortcutSettings.shared
    let wasEnabled = settings.pttEnabled
    let wasShortcut = settings.pttShortcut
    defer {
      settings.pttShortcut = wasShortcut
      settings.pttEnabled = wasEnabled
    }

    settings.pttEnabled = true
    settings.pttShortcut = ShortcutSettings.KeyboardShortcut(modifierOnly: [.control, .option])
    XCTAssertEqual(
      settings.pttShortcut.displayTokens, ["⌃", "⌥"], "precondition: a two-token binding")
    XCTAssertEqual(FloatingControlBarView.followUpVoiceHint(settings: settings), "or hold ⌃⌥ to ask aloud")
  }

  // MARK: - Failure copy is never spoken

  /// The empty-response notice and the voice guard that silences it went out of
  /// sync once already: the copy was rewritten and `shouldSpeak` went on
  /// matching the retired sentence, so a voice query that produced nothing had
  /// its failure notice read aloud. Both halves now come from one type; this
  /// asserts the whole playback path stays silent on every string in it.
  func testFailureCopyIsNeverReadAloud() {
    for copy in [FloatingBarAnswerFailureCopy.emptyResponse] + FloatingBarAnswerFailureCopy.retired {
      let spoken = FloatingBarVoicePlaybackService.cleanedPlaybackText(
        from: ChatMessage(text: copy, sender: .ai))
      XCTAssertFalse(
        FloatingBarVoicePlaybackService.shouldSpeak(spoken),
        "failure copy would be spoken aloud: \(copy)")
    }

    let answer = FloatingBarVoicePlaybackService.cleanedPlaybackText(
      from: ChatMessage(text: "You and Priya settled on shipping Thursday.", sender: .ai))
    XCTAssertTrue(
      FloatingBarVoicePlaybackService.shouldSpeak(answer), "a real answer must still be spoken")
  }
}
