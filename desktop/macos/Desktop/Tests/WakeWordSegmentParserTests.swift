import XCTest

@testable import Omi_Computer

final class WakeWordSegmentParserTests: XCTestCase {
  func testExtractsCommandAfterWakeWord() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(
        after: "Omi, let's order Maya some food", wakePhrase: "Omi"),
      "let's order Maya some food")
  }

  func testAcceptsCaseAndPunctuationVariants() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "omi, let's order pizza", wakePhrase: "Omi"),
      "let's order pizza")
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "Omi let's order pizza", wakePhrase: "omi"),
      "let's order pizza")
  }

  func testBareWakeWordReturnsNil() {
    XCTAssertNil(WakeWordSegmentParser.command(after: "Omi", wakePhrase: "Omi"))
    XCTAssertNil(WakeWordSegmentParser.command(after: "Omi.", wakePhrase: "Omi"))
  }

  func testIgnoresSegmentsWithoutWakeWord() {
    XCTAssertNil(WakeWordSegmentParser.command(after: "We should order pizza", wakePhrase: "Omi"))
    XCTAssertNil(WakeWordSegmentParser.command(after: "Omiway to the store", wakePhrase: "Omi"))
  }

  func testAcceptsGreetingVariant() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "Hey Omi, order pizza", wakePhrase: "Omi"),
      "order pizza")
  }

  func testAcceptsConfiguredGreetingPhrase() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "Hey Omi order pizza", wakePhrase: "hey omi"),
      "order pizza")
  }

  func testEmptyPhraseReturnsNil() {
    XCTAssertNil(WakeWordSegmentParser.command(after: "Omi order pizza", wakePhrase: "  "))
  }

  /// Regression: a live mic session transcribed "Omi, how are you?" as
  /// "Oh me, how are you?" (Parakeet, conf=0.92) and the wake word silently
  /// never fired. STT spells the phrase by sound, so homophones must match.
  func testAcceptsSpeechToTextHomophones() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "Oh me, how are you?", wakePhrase: "Omi"),
      "how are you?")
    for rendering in ["Omni", "Ohmi", "Oh mi", "Omee", "O me"] {
      XCTAssertEqual(
        WakeWordSegmentParser.command(after: "\(rendering), order pizza", wakePhrase: "Omi"),
        "order pizza",
        "expected \(rendering) to be treated as the wake word")
    }
  }

  func testAcceptsGreetingBeforeHomophone() {
    XCTAssertEqual(
      WakeWordSegmentParser.command(after: "Hey oh me, order pizza", wakePhrase: "Omi"),
      "order pizza")
  }

  /// The wider match must not swallow ordinary speech: a homophone still needs a
  /// word boundary and a real command behind it.
  func testHomophoneWithoutBoundaryOrCommandIsIgnored() {
    XCTAssertNil(WakeWordSegmentParser.command(after: "Omnibus schedule changed", wakePhrase: "Omi"))
    XCTAssertNil(WakeWordSegmentParser.command(after: "Oh me", wakePhrase: "Omi"))
  }
}
