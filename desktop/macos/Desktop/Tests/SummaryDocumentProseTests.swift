import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class SummaryDocumentProseTests: XCTestCase {
  private func render(_ source: String) throws -> NSAttributedString {
    try XCTUnwrap(
      ChatSelectableProse.attributedString(
        markdown: source, style: .assistant, fontSize: 14, fontScale: 1, documentProse: true))
  }

  private func attributes(_ text: NSAttributedString, at needle: String) throws -> [NSAttributedString.Key: Any] {
    let range = (text.string as NSString).range(of: needle)
    XCTAssertNotEqual(range.location, NSNotFound)
    guard range.location != NSNotFound else { throw NSError(domain: "Missing test text", code: 1) }
    return text.attributes(at: range.location, effectiveRange: nil)
  }

  func testHeadingsKeepHierarchyAndParagraphsRemainSeparate() throws {
    let text = try render("# Meeting\n\n## Decisions\n\n### Detail\n\nFirst paragraph.\n\nSecond paragraph.")
    XCTAssertEqual(text.string, "Meeting\nDecisions\nDetail\nFirst paragraph.\nSecond paragraph.")
    let title = try XCTUnwrap(attributes(text, at: "Meeting")[.font] as? NSFont)
    let section = try XCTUnwrap(attributes(text, at: "Decisions")[.font] as? NSFont)
    let detail = try XCTUnwrap(attributes(text, at: "Detail")[.font] as? NSFont)
    let body = try XCTUnwrap(attributes(text, at: "First paragraph")[.font] as? NSFont)
    XCTAssertGreaterThan(title.pointSize, section.pointSize)
    XCTAssertGreaterThan(section.pointSize, detail.pointSize)
    XCTAssertGreaterThan(detail.pointSize, body.pointSize)
  }

  func testListsHaveOneMarkerPerItemAndHangingIndents() throws {
    let text = try render(
      "- First **important** item\n  continued\n  - Nested item\n- Second item\n\n3. Third\n4. Fourth")
    XCTAssertEqual(
      text.string, "•\tFirst important item continued\n•\tNested item\n•\tSecond item\n3.\tThird\n4.\tFourth")
    let outer = try XCTUnwrap(attributes(text, at: "First")[.paragraphStyle] as? NSParagraphStyle)
    let nested = try XCTUnwrap(attributes(text, at: "Nested")[.paragraphStyle] as? NSParagraphStyle)
    XCTAssertGreaterThan(outer.headIndent, outer.firstLineHeadIndent)
    XCTAssertGreaterThan(nested.headIndent, outer.headIndent)
  }

  func testListContinuationParagraphDoesNotRepeatMarker() throws {
    let text = try render("- First paragraph\n\n  Continued paragraph\n\n- Next item")
    XCTAssertEqual(text.string, "•\tFirst paragraph\nContinued paragraph\n•\tNext item")
    let continued = try XCTUnwrap(attributes(text, at: "Continued")[.paragraphStyle] as? NSParagraphStyle)
    XCTAssertEqual(continued.firstLineHeadIndent, continued.headIndent)
  }

  func testInlineFormattingAndLinksSurviveDocumentParsing() throws {
    let text = try render("Read [the source](https://example.com) and `literal_code` with **emphasis**.")
    XCTAssertEqual(text.string, "Read the source and literal_code with emphasis.")
    XCTAssertEqual(try attributes(text, at: "the source")[.link] as? URL, URL(string: "https://example.com"))
    let codeFont = try XCTUnwrap(attributes(text, at: "literal_code")[.font] as? NSFont)
    XCTAssertTrue(codeFont.isFixedPitch)
    let boldFont = try XCTUnwrap(attributes(text, at: "emphasis")[.font] as? NSFont)
    XCTAssertTrue(boldFont.fontDescriptor.symbolicTraits.contains(.bold))
  }

  func testChatAndDocumentCannotShareCachedLayout() {
    let chat = ChatProseRenderCache.Key(
      markdown: "## Heading", style: .assistant, fontSize: 14, fontScaleMilli: 1000, citationOrdinals: [])
    var document = chat
    document.documentProse = true
    XCTAssertNotEqual(chat, document)
  }

  func testActualMarkdownViewUsesSelectableDocumentProseAcrossResize() throws {
    let source =
      "## Decisions\n\n- A long decision that should wrap cleanly when the reader makes the summary window narrower.\n- Another decision."
    let host = NSHostingView(
      rootView: OmiMarkdown(text: source, style: .assistant, appKitProseSelection: true, documentProse: true))
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 550, height: 700), styleMask: .borderless, backing: .buffered, defer: false
    )
    window.contentView = host
    host.appearance = NSAppearance(named: .aqua)
    func textViews(_ view: NSView) -> [NSTextView] {
      (view as? NSTextView).map { [$0] } ?? view.subviews.flatMap(textViews)
    }
    for width in [CGFloat(550), 260, 550] {
      host.frame = NSRect(x: 0, y: 0, width: width, height: 700)
      host.layoutSubtreeIfNeeded()
      let views = textViews(host)
      let rendered = views.map(\.string).joined(separator: "\n")
      let view = try XCTUnwrap(views.first { $0.string.contains("Another decision.") })
      XCTAssertTrue(views.allSatisfy(\.isSelectable))
      XCTAssertFalse(views.contains(where: \.isEditable))
      XCTAssertEqual(rendered.components(separatedBy: "Decisions").count - 1, 1)
      XCTAssertEqual(rendered.components(separatedBy: "•").count - 1, 2)
      XCTAssertFalse(rendered.contains("##"))
      view.setSelectedRange((view.string as NSString).range(of: "Another decision."))
      XCTAssertEqual((view.string as NSString).substring(with: view.selectedRange()), "Another decision.")
      let height = ChatSelectableProseText.height(of: try render(source), fittingWidth: width)
      XCTAssertGreaterThan(height, 0)
      XCTAssertLessThan(height, 700)
    }
  }
}
