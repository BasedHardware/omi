import XCTest

@testable import Omi_Computer

/// Visual-input heuristics only. Semantic intent routing is kernel-owned.
final class FloatingBarHeuristicsTests: XCTestCase {
  // MARK: - queryNeedsScreenshot (#2: only capture when screen-related)

  func testScreenshotCapturedForVisualQueries() {
    let visual = [
      "What's on my screen right now?",
      "Read this and summarize it",
      "What does this error mean?",
      "Look at my screen and tell me what to click",
      "What is this?",
    ]
    for q in visual {
      XCTAssertTrue(
        FloatingControlBarManager.queryNeedsScreenshot(q),
        "Expected screenshot for visual query: \"\(q)\"")
    }
  }

  func testScreenshotSkippedForNonVisualQueries() {
    let nonVisual = [
      "What's up?",
      "What's my goal for today?",
      "What's the capital of France?",
      "Give me three productivity tips",
      "What did I work on this morning?",
    ]
    for q in nonVisual {
      XCTAssertFalse(
        FloatingControlBarManager.queryNeedsScreenshot(q),
        "Expected NO screenshot for non-visual query: \"\(q)\"")
    }
  }
}
