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
}
