import XCTest

@testable import Omi_Computer

final class InterjectVoiceFeedbackRoutingTests: XCTestCase {
  func testParseStripsTheTokenAndKeepsTheSpokenAcknowledgment() {
    let parsed = InterjectVoiceFeedbackRouting.parse(
      """
      [[interject:correction]]
      Got it — Thursday. I'd had it as Wednesday; fixed.
      """
    )
    XCTAssertEqual(parsed.verb, .correction)
    XCTAssertEqual(parsed.spoken, "Got it — Thursday. I'd had it as Wednesday; fixed.")
  }

  func testParseRecognizesEveryFeedbackVerb() {
    for verb in InterjectFeedbackVerb.allCases {
      let parsed = InterjectVoiceFeedbackRouting.parse("[[interject:\(verb.rawValue)]] ok")
      XCTAssertEqual(parsed.verb, verb, verb.rawValue)
      XCTAssertEqual(parsed.spoken, "ok")
    }
  }

  func testMissingTokenLeavesTheReplyUntouched() {
    let parsed = InterjectVoiceFeedbackRouting.parse("Just a riff with no marker")
    XCTAssertNil(parsed.verb)
    XCTAssertEqual(parsed.spoken, "Just a riff with no marker")
  }

  func testDisplayTextStripsACompleteLeadingToken() {
    XCTAssertEqual(
      InterjectVoiceFeedbackRouting.displayText(
        from: "[[interject:correction]]\nGot it — Thursday."),
      "Got it — Thursday."
    )
    XCTAssertEqual(
      InterjectVoiceFeedbackRouting.displayText(from: "[[interject:not_a_verb]] still hidden"),
      "still hidden",
      "an unknown verb is still machine noise, never rendered"
    )
  }

  func testDisplayTextHidesATokenStillStreamingIn() {
    XCTAssertEqual(InterjectVoiceFeedbackRouting.displayText(from: "[[interject:corr"), "")
    XCTAssertEqual(InterjectVoiceFeedbackRouting.displayText(from: "[[inter"), "")
    XCTAssertEqual(InterjectVoiceFeedbackRouting.displayText(from: "[[i"), "")
  }

  func testDisplayTextDoesNotBlankAMarkdownLinkMidStream() {
    // A stream that has only emitted `[` or `[[` is ordinary copy far more
    // often than a token opener; blanking it flickers real assistant text.
    for partial in ["[", "[[", "[C", "[Click here](https://omi.me)"] {
      XCTAssertEqual(
        InterjectVoiceFeedbackRouting.displayText(from: partial), partial,
        "a Markdown link must survive every streaming prefix")
    }
  }

  func testDisplayTextLeavesOrdinaryRepliesUntouched() {
    XCTAssertEqual(InterjectVoiceFeedbackRouting.displayText(from: "Just a reply"), "Just a reply")
    XCTAssertEqual(
      InterjectVoiceFeedbackRouting.displayText(from: "See [[interject:useful]] mid-text"),
      "See [[interject:useful]] mid-text",
      "only a leading token is a directive"
    )
    XCTAssertEqual(InterjectVoiceFeedbackRouting.displayText(from: ""), "")
  }

  func testSpokenTextHelperMatchesParse() {
    XCTAssertEqual(
      InterjectVoiceFeedbackRouting.spokenText(from: "[[interject:useful]] Thanks — I'll keep that."),
      "Thanks — I'll keep that."
    )
  }

  func testClassificationInstructionDoesNotListSpeakableOutputTokens() {
    let instruction = InterjectVoiceFeedbackRouting.classificationInstruction
    let trusted = InterjectVoiceFeedbackRouting.trustedTurnInstruction
    for text in [instruction, trusted] {
      XCTAssertFalse(
        text.contains("[[interject:"),
        "hub inject must not teach a speakable classification token")
      XCTAssertFalse(
        text.lowercased().contains("interject riff"),
        "hub inject must not name the spoken classification phrase")
      XCTAssertFalse(
        text.contains("Put exactly one token on its own first line"),
        "hub inject must not ask for a first-line speech token")
      for verb in InterjectFeedbackVerb.allCases {
        XCTAssertFalse(
          text.contains("[[interject:\(verb.rawValue)]]"),
          "verb \(verb.rawValue) must not appear as a speakable output token")
      }
    }
    XCTAssertTrue(instruction.contains("record_interject_feedback"))
    XCTAssertTrue(trusted.contains(instruction))
  }

  func testHubDidEmitTextSpeaksSpokenTextOnlyWhenNativeAudioMissing() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent(
        "Sources/FloatingControlBar/RealtimeHubController+SessionDelegate.swift")
    // omi-test-quality: source-inspection -- static contract: native PCM is never sanitized by spokenText; speakOneShot of spokenText(from: assistantText) may run only behind if !audioReceivedThisTurn
    let source = try String(contentsOf: sourceURL, encoding: .utf8)
    XCTAssertTrue(source.contains("spokenText(from: assistantText)"))
    XCTAssertTrue(source.contains("if !audioReceivedThisTurn, !reply.isEmpty,"))
    XCTAssertTrue(source.contains("speakOneShot(reply, lease: lease)"))

    let fnRange = try XCTUnwrap(source.range(of: "func hubDidEmitText("))
    let afterFn = source[fnRange.lowerBound...]
    let searchStart = afterFn.index(after: fnRange.lowerBound)
    let nextFn = afterFn.range(of: "\n  func ", range: searchStart..<afterFn.endIndex)
    let body = String(afterFn[..<(nextFn?.lowerBound ?? afterFn.endIndex)])
    XCTAssertEqual(
      body.components(separatedBy: "speakOneShot(reply, lease: lease)").count - 1, 1)
    let speakIndex = try XCTUnwrap(body.range(of: "speakOneShot(reply, lease: lease)"))
    let guardIndex = try XCTUnwrap(body.range(of: "if !audioReceivedThisTurn, !reply.isEmpty,"))
    XCTAssertLessThan(guardIndex.lowerBound, speakIndex.lowerBound)
  }
}
