import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class OmiMarkdownLineSpacingTests: XCTestCase {
  func testChatLineSpacingIsFivePointsAtTheDefaultBody() {
    XCTAssertEqual(OmiMarkdownContent.chatLineSpacing(fontSize: 14), 5)
    XCTAssertEqual(OmiMarkdownContent.chatLineSpacing(fontSize: 28), 10)
  }

  func testHardBrokenChatLinesIncludeTheExtraLeading() {
    let single = measureHeight("Hello")
    let stacked = measureHeight("Hello\nWorld")
    let extra = stacked - (2 * single)
    XCTAssertEqual(
      extra,
      OmiMarkdownContent.chatLineSpacing(fontSize: 14),
      accuracy: 1.5,
      "adjacent chat lines must sit 5 pt apart at the default body, not flush")
  }

  func testWrappedChatLinesAreTallerThanASingleLineByAtLeastTheExtraLeading() {
    let long =
      "This completed answer wraps several times so the extra leading between chat lines is visible."
    let wrapped = measureHeight(long, width: 220)
    let single = measureHeight("Hello", width: 220)
    XCTAssertGreaterThan(
      wrapped,
      single + OmiMarkdownContent.chatLineSpacing(fontSize: 14),
      "wrapped chat prose must include the extra 5 pt of leading")
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
