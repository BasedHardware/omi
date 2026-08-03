import Foundation
import XCTest

@testable import Omi_Computer

final class OmiMarkdownThematicBreakTests: XCTestCase {
  func testThematicBreakBecomesItsOwnRenderBlock() {
    let document = OmiMarkdownDocument(
      markdown: """
        Before the break

        ---

        After the break
        """
    )

    XCTAssertEqual(document.blocks.count, 3)
    XCTAssertEqual(document.blocks[0].kind, .text("Before the break"))
    XCTAssertEqual(document.blocks[1].kind, .thematicBreak)
    XCTAssertEqual(document.blocks[2].kind, .text("After the break"))
  }

  func testCommonThematicBreakVariantsAreRecognized() {
    XCTAssertTrue(OmiMarkdownDocument.isThematicBreak("---"))
    XCTAssertTrue(OmiMarkdownDocument.isThematicBreak("* * *"))
    XCTAssertTrue(OmiMarkdownDocument.isThematicBreak("___"))
    XCTAssertFalse(OmiMarkdownDocument.isThematicBreak("--"))
    XCTAssertFalse(OmiMarkdownDocument.isThematicBreak("- - x"))
    XCTAssertFalse(OmiMarkdownDocument.isThematicBreak("a --- b"))
  }

  func testThematicBreakInsideCodeFenceStaysCode() {
    let document = OmiMarkdownDocument(
      markdown: """
        ```text
        ---
        ```
        """
    )

    XCTAssertEqual(
      document.blocks,
      [
        .init(id: 0, kind: .codeBlock(language: "text", code: "---"))
      ])
  }

  func testInlineCodeProducesCopyableCodeSegmentsOnlyWhenClosed() {
    XCTAssertEqual(
      OmiMarkdownInlineCode.segments(in: "Run `omi-ctl` now."),
      [.text("Run "), .code("omi-ctl"), .text(" now.")]
    )
    XCTAssertTrue(OmiMarkdownInlineCode.containsSpan(in: "Use `openai`"))
    XCTAssertFalse(OmiMarkdownInlineCode.containsSpan(in: "Streaming `unfinished"))
    XCTAssertEqual(
      OmiMarkdownInlineCode.segments(in: "Streaming `unfinished"),
      [.text("Streaming `unfinished")]
    )
  }

  func testInlineCodeSupportsBacktickRunsUsedInsideCodeSpans() {
    XCTAssertEqual(
      OmiMarkdownInlineCode.segments(in: "Use ``literal ` tick`` here"),
      [.text("Use "), .code("literal ` tick"), .text(" here")]
    )
  }

  func testInlineCodeMaskingPreservesSurroundingMarkdownSemantics() throws {
    let source = "**bold `omi`** and [docs `--help`](https://example.com/docs)"
    let masked = try XCTUnwrap(OmiMarkdownInlineCode.maskedMarkdown(source))
    XCTAssertEqual(masked.placeholders.map(\.code), ["omi", "--help"])
    XCTAssertFalse(masked.markdown.contains("`"))

    let attributed = try AttributedString(
      markdown: masked.markdown,
      options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
    )
    let renderedLines = OmiMarkdownInlineCode.renderSegments(
      in: attributed,
      placeholders: masked.placeholders
    )
    let rendered = renderedLines.map { line in
      line.map { segment in
        switch segment {
        case .text(let value):
          String(value.characters)
        case .code(let value):
          value
        }
      }.joined()
    }.joined(separator: "\n")

    XCTAssertEqual(rendered, "bold omi and docs --help")
    XCTAssertFalse(rendered.contains("**"))
    XCTAssertFalse(rendered.contains("[docs"))

    let boldRun = try XCTUnwrap(
      attributed.runs.first { String(attributed[$0.range].characters).contains("bold") }
    )
    if let intent = boldRun.inlinePresentationIntent {
      XCTAssertTrue(intent.contains(.stronglyEmphasized))
    } else {
      XCTFail("bold Markdown semantics were not preserved")
    }

    let linkRun = try XCTUnwrap(
      attributed.runs.first { String(attributed[$0.range].characters).contains("docs") }
    )
    XCTAssertEqual(linkRun.link?.absoluteString, "https://example.com/docs")
  }
}
