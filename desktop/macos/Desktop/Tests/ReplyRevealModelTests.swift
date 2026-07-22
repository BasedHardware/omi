import XCTest

@testable import Omi_Computer

@MainActor
final class ReplyRevealModelTests: XCTestCase {
  func testRevealsWholeWordsAndCompletes() {
    let model = ReplyRevealModel()
    let full = "alpha beta gamma delta epsilon"
    var shown = ""
    for i in 0..<500 {
      shown = model.revealed(at: Date(timeIntervalSinceReferenceDate: Double(i) * 0.05), full: full)
      guard !shown.isEmpty, shown != full else { continue }
      // The tail must always land on a word boundary — never a half-typed word.
      let nextChar = full[full.index(full.startIndex, offsetBy: shown.count)]
      XCTAssertEqual(nextChar, " ", "reveal stopped mid-word: '\(shown)'")
    }
    XCTAssertEqual(shown, full, "the reveal must catch up to the full reply")
  }

  func testRestartsWhenTextShrinks() {
    let model = ReplyRevealModel()
    // Reveal a long buffer partway, then hand it a shorter buffer (new turn).
    for i in 0..<10 {
      _ = model.revealed(at: Date(timeIntervalSinceReferenceDate: Double(i) * 0.05), full: "one two three four")
    }
    let shown = model.revealed(at: Date(timeIntervalSinceReferenceDate: 1), full: "hi")
    XCTAssertEqual(shown, "")
  }
}
