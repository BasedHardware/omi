import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class OmiMarkdownLineSpacingTests: XCTestCase {
  func testChatLineSpacingIsHalfTheBodySize() {
    XCTAssertEqual(OmiMarkdownContent.chatLineSpacing(fontSize: 14), 7)
    XCTAssertEqual(OmiMarkdownContent.chatLineSpacing(fontSize: 16), 8)
  }

  func testHardBrokenChatLinesIncludeHalfLineLeading() {
    let single = measureHeight("Hello")
    let stacked = measureHeight("Hello\nWorld")
    let extra = stacked - (2 * single)
    XCTAssertEqual(
      extra,
      OmiMarkdownContent.chatLineSpacing(fontSize: 14),
      accuracy: 1.5,
      "adjacent chat lines must sit a half-line apart, not flush")
  }

  func testWrappedChatLinesAreTallerThanASingleLineByAtLeastHalfALine() {
    let long =
      "This completed answer wraps several times so the extra leading between chat lines is visible."
    let wrapped = measureHeight(long, width: 220)
    let single = measureHeight("Hello", width: 220)
    XCTAssertGreaterThan(
      wrapped,
      single + OmiMarkdownContent.chatLineSpacing(fontSize: 14),
      "wrapped chat prose must include the extra half-line of leading")
  }

  private func measureHeight(_ text: String, width: CGFloat = 400) -> CGFloat {
    let host = NSHostingView(
      rootView: OmiMarkdown(text: text, style: .assistant)
        .frame(width: width, alignment: .leading)
    )
    host.frame = NSRect(x: 0, y: 0, width: width, height: 800)
    host.layoutSubtreeIfNeeded()
    return host.fittingSize.height
  }
}
