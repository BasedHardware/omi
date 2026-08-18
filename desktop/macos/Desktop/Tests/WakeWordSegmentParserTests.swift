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
}