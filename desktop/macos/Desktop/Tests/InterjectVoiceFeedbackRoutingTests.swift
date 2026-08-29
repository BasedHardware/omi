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
}
