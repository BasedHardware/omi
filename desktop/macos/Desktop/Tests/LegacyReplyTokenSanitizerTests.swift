import XCTest

@testable import Omi_Computer

final class LegacyReplyTokenSanitizerTests: XCTestCase {
  func testSavedMachineTokenNeverRendersOrSpeaks() {
    let saved = "[[interject:useful]] Here is the answer."
    XCTAssertEqual(LegacyReplyTokenSanitizer.displayText(from: saved), "Here is the answer.")
    XCTAssertEqual(LegacyReplyTokenSanitizer.spokenText(from: saved), "Here is the answer.")
  }

  func testPartialLegacyTokenDoesNotFlashDuringHistoryStreaming() {
    for text in ["[[i", "[[interject:", "[[interject:useful"] {
      XCTAssertEqual(LegacyReplyTokenSanitizer.displayText(from: text), "")
    }
  }

  func testOrdinaryMarkdownAndTextRemainUnchanged() {
    for text in ["[", "[[", "[a link](https://example.test)", "An ordinary answer"] {
      XCTAssertEqual(LegacyReplyTokenSanitizer.displayText(from: text), text)
      XCTAssertEqual(LegacyReplyTokenSanitizer.spokenText(from: text), text)
    }
  }
}
