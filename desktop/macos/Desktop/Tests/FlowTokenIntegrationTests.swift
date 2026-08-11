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
    XCTAssertFalse(OmiMarkdown.isPlainText("Read <https://omi.me>"))
    XCTAssertFalse(OmiMarkdown.isPlainText("Email <mailto:user@example.com>"))
    XCTAssertFalse(OmiMarkdown.isPlainText("Email <user@example.com>"))
    XCTAssertFalse(OmiMarkdown.isPlainText("| Name | Value |\n| --- | --- |\n| Omi | 1 |"))
  }

  /// The settled document turns `---` into a divider and decodes `&amp;`, so
  /// classifying either as plain text made the bubble visibly change the
  /// instant streaming ended.
  func testPlainTextGateCatchesThematicBreaksAndCharacterReferences() {
    XCTAssertFalse(OmiMarkdown.isPlainText("Intro\n---\nOutro"))
    XCTAssertFalse(OmiMarkdown.isPlainText("---"))
    XCTAssertFalse(OmiMarkdown.isPlainText("Carrier: AT&amp;T"))
    XCTAssertFalse(OmiMarkdown.isPlainText("Fraction: &#189; done"))
    XCTAssertFalse(OmiMarkdown.isPlainText("Hex entity: &#x1F600; done"))

    // A bare ampersand or a lone dash is still ordinary prose.
    XCTAssertTrue(OmiMarkdown.isPlainText("Tom & Jerry"))
    XCTAssertTrue(OmiMarkdown.isPlainText("A dash - inside a sentence."))
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

  func testStreamingTextUsesSettledMarkdownWhitespaceRules() {
    XCTAssertEqual(StreamingAssistantText.displayedText("\n  A streamed answer.  \n"), "A streamed answer.")
  }

  func testStreamingRevealContractRequiresStrictPrefix() {
    XCTAssertTrue(
      ChatStreamingRevealContract.isStrictPrefix(
        "Paced streaming",
        expectedPrefix: "Paced",
        expectedText: "Paced streaming response"
      )
    )
    XCTAssertFalse(
      ChatStreamingRevealContract.isStrictPrefix(
        "Paced streaming response",
        expectedPrefix: "Paced",
        expectedText: "Paced streaming response"
      )
    )
    XCTAssertFalse(
      ChatStreamingRevealContract.isStrictPrefix(
        "Fast streaming",
        expectedPrefix: "Paced",
        expectedText: "Paced streaming response"
      )
    )
  }

}
