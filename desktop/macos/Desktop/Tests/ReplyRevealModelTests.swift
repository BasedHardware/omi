import XCTest

@testable import Omi_Computer

@MainActor
final class ReplyRevealModelTests: XCTestCase {
  func testSnapsToFullWhenNotStreaming() {
    let model = ReplyRevealModel()
    let shown = model.revealed(
      at: Date(timeIntervalSinceReferenceDate: 0), full: "hello world", streaming: false)
    XCTAssertEqual(shown, "hello world")
  }

  func testStreamingRevealsWholeWordsAndCompletes() {
    let model = ReplyRevealModel()
    let full = "alpha beta gamma delta epsilon"
    var shown = ""
    for i in 0..<500 {
      shown = model.revealed(
        at: Date(timeIntervalSinceReferenceDate: Double(i) * 0.05), full: full, streaming: true)
      guard !shown.isEmpty, shown != full else { continue }
      // The tail must always land on a word boundary — never a half-typed word.
      let nextChar = full[full.index(full.startIndex, offsetBy: shown.count)]
      XCTAssertEqual(nextChar, " ", "reveal stopped mid-word: '\(shown)'")
    }
    XCTAssertEqual(shown, full, "the reveal must catch up to the full reply")
  }

  func testRestartsWhenTextShrinks() {
    let model = ReplyRevealModel()
    _ = model.revealed(at: Date(timeIntervalSinceReferenceDate: 0), full: "one two three", streaming: false)
    // A shorter buffer = a new turn; reveal restarts from empty.
    let shown = model.revealed(
      at: Date(timeIntervalSinceReferenceDate: 0.02), full: "hi", streaming: true)
    XCTAssertEqual(shown, "")
  }
}
