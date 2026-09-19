import XCTest

// Local source-inspection tripwire for FC-selection-overlay-layout-loop on the
// live transcript, which the shared boundary checker
// (`.github/scripts/check_chat_selection_boundary.py`) does not yet list. When
// the checker expansion lands, `LiveTranscriptView.swift` belongs in its
// protected set and this suite can migrate there.
final class LiveTranscriptSelectionBoundaryTests: XCTestCase {
  private func source(_ relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    guard FileManager.default.fileExists(atPath: url.path) else {
      XCTFail(
        "\(relativePath) no longer exists; update or delete LiveTranscriptSelectionBoundaryTests with it.")
      throw CocoaError(.fileNoSuchFile)
    }
    // omi-test-quality: source-inspection -- static contract: SwiftUI installs SelectionOverlay per Text modifier at build time; no runtime observation short of a window server can see it, so "no per-bubble overlay in the live transcript" is a property of the source text.
    return try String(contentsOf: url, encoding: .utf8)
  }

  /// The live-capture transcript must not mount SwiftUI selection: each
  /// segment bubble would wrap its `Text` in an NSTextView-backed layout
  /// engine, and a long capture relays every one of them on each live update —
  /// the same failure class the saved transcript hit in `SpeakerBubbleView`.
  func testLiveTranscriptBubblesDoNotInstallSwiftUISelection() throws {
    let source = try source("MainWindow/Components/LiveTranscriptView.swift")

    XCTAssertFalse(
      source.contains(".textSelection(.enabled)"),
      "live transcript bubbles must not install SwiftUI SelectionOverlay; copy is served by the saved transcript's Copy control"
    )
  }

  /// The long-nested-markdown hosts this fixed (expanded agent cards and the
  /// discovery card's nested `ScrollView`) must keep prose on the
  /// `ChatSelectableProse` path so parent rebuilds cannot relay a tall
  /// SwiftUI `Text` inside a nested scroller.
  func testLongNestedMarkdownHostsUseAppKitProseSelection() throws {
    let chatBubbleSource = try source("MainWindow/Components/ChatBubble.swift")

    XCTAssertTrue(
      chatBubbleSource.contains(
        "OmiMarkdown(text: summary.output, sender: .ai, appKitProseSelection: true)"),
      "expanded background-agent summary output must draw prose through ChatSelectableProse"
    )
    XCTAssertTrue(
      chatBubbleSource.contains(
        "OmiMarkdown(text: output, sender: .ai, appKitProseSelection: true)"),
      "expanded agent completion output must draw prose through ChatSelectableProse"
    )
    XCTAssertTrue(
      chatBubbleSource.contains(
        "OmiMarkdown(text: fullText, sender: .ai, appKitProseSelection: true)"),
      "discovery card full text must draw prose through ChatSelectableProse"
    )
  }
}
