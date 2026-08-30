import XCTest

@testable import Omi_Computer

/// What the front window contributes to a spoken lookup.
///
/// Accessibility and a screenshot cover for each other: AX is exact where an app
/// publishes it and absent where it does not, and the picture has no such gap. These
/// pin the part that turns a UI tree into something a model can read.
final class ScreenGlanceTests: XCTestCase {
  /// A tree repeats itself — a button's title is its parent's description, and rows
  /// arrive twice through AXChildren and AXVisibleChildren. The budget has to go on
  /// distinct content.
  func testRepeatedStringsCollapseToOne() {
    XCTAssertEqual(
      ScreenGlance.render(["Submit", "Submit", "submit", "Deadline"]),
      "Submit\nDeadline")
  }

  func testEmptyAndSingleCharacterNoiseIsDropped() {
    XCTAssertEqual(ScreenGlance.render(["", "  ", "x", "•", "Overview"]), "Overview")
  }

  /// Newlines would fake structure the tree does not have, so a multi-line value
  /// becomes one line.
  func testAValueSpanningLinesBecomesOneLine() {
    XCTAssertEqual(ScreenGlance.render(["Build next\ngeneration agents"]), "Build next generation agents")
  }

  /// One AXValue can hold a whole document. Past the per-line cap it is a dump, not a
  /// label, and it must not eat the whole budget.
  func testASingleHugeValueIsClipped() {
    let rendered = ScreenGlance.render([String(repeating: "a", count: 5_000)])
    XCTAssertEqual(rendered.count, ScreenGlance.maxLineLength + 1, "clipped plus the ellipsis")
    XCTAssertTrue(rendered.hasSuffix("…"))
  }

  /// The whole block is bounded too: a long page must not crowd out the sweep results
  /// the same prompt carries.
  func testTheBlockStopsAtItsBudget() {
    let many = (0..<5_000).map { "line number \($0) of this very long window" }
    XCTAssertLessThanOrEqual(ScreenGlance.render(many).count, ScreenGlance.maxTextLength)
  }

  func testOrderIsPreservedSoTheHeadingComesFirst() {
    XCTAssertEqual(
      ScreenGlance.render(["All Things Agentic Hackathon", "Deadline", "Aug 31, 2026"]),
      "All Things Agentic Hackathon\nDeadline\nAug 31, 2026")
  }

  // MARK: - The prompt block

  private func glance(text: String, image: Data?) -> ScreenGlance.Glance {
    ScreenGlance.Glance(
      appName: "Brave Browser", windowTitle: "All Things Agentic Hackathon",
      pageURL: "https://allthingsagentichackathon.devpost.com", text: text, image: image)
  }

  func testNothingOnScreenContributesNothing() {
    XCTAssertTrue(ScreenGlance.promptSection(nil).isEmpty)
  }

  /// The app, window and page name what "this" refers to even when the tree is dark.
  func testAWindowWithNoAccessibilityTextStillNamesItself() {
    let section = ScreenGlance.promptSection(glance(text: "", image: Data([0xFF])))
    XCTAssertTrue(section.contains("Brave Browser"))
    XCTAssertTrue(section.contains("All Things Agentic Hackathon"))
    XCTAssertTrue(section.contains("devpost.com"))
    XCTAssertTrue(section.contains("picture of this window is attached"))
    XCTAssertFalse(section.contains("Text read from the window"))
  }

  /// Without Screen Recording permission there is no picture, and the block must not
  /// claim one — the model would answer from an image it never received.
  func testNoImageIsNeverAnnouncedAsAttached() {
    let section = ScreenGlance.promptSection(glance(text: "Deadline", image: nil))
    XCTAssertFalse(section.contains("attached"))
    XCTAssertTrue(section.contains("Text read from the window:"))
    XCTAssertTrue(section.contains("Deadline"))
  }

  /// A dark tree and no capture permission still leaves the window's own name, which is
  /// often enough to tell the model what "this" is.
  func testAGlanceWithNeitherTextNorPictureIsStillWorthItsTitle() {
    XCTAssertTrue(glance(text: "", image: nil).isEmpty)
    XCTAssertTrue(ScreenGlance.promptSection(glance(text: "", image: nil)).contains("Window:"))
  }
}
