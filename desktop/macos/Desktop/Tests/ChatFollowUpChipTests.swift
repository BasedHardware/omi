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
}
