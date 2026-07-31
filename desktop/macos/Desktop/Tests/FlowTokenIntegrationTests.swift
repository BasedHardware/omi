import AppKit
import FlowToken
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor final class FlowTokenIntegrationTests: XCTestCase {
  func testPlainTextGateKeepsStructuredMarkdownOnOmiRenderer() {
    XCTAssertTrue(OmiMarkdown.isPlainText("A streamed answer with a second sentence."))
    XCTAssertTrue(OmiMarkdown.isPlainText("First paragraph.\n\nSecond paragraph."))
    XCTAssertFalse(OmiMarkdown.isPlainText("# Heading"))
    XCTAssertFalse(OmiMarkdown.isPlainText("- List item"))
    XCTAssertFalse(OmiMarkdown.isPlainText("Intro\n- List item"))
    XCTAssertFalse(OmiMarkdown.isPlainText("Use **bold** text."))
    XCTAssertFalse(OmiMarkdown.isPlainText("Run `swift test`."))
    XCTAssertFalse(OmiMarkdown.isPlainText("[Open Omi](https://omi.me)"))
    XCTAssertFalse(OmiMarkdown.isPlainText("| Name | Value |\n| --- | --- |\n| Omi | 1 |"))
  }

  func testFlowTokenFadeInRendersPlainStreamingTextWithFiniteLayout() {
    let host = NSHostingView(
      rootView: TokenizedText(
        "A streamed answer.", separator: .diff, animation: .fadeIn, animationDuration: 0.18)
    )
    host.frame = NSRect(x: 0, y: 0, width: 480, height: 120)
    host.layoutSubtreeIfNeeded()

    let size = host.fittingSize
    XCTAssertTrue(size.width.isFinite)
    XCTAssertTrue(size.height.isFinite)
    XCTAssertGreaterThan(size.height, 0)
  }

}
