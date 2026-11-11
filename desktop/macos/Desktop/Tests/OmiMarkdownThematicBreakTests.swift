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

  // MARK: - Tildes

  /// **The reported answer, verbatim.**
  ///
  /// A list of ticket prices came back with everything between the first two prices struck through
  /// and the tildes themselves missing. `(~$190)` and `(~$230)` are each flanked by punctuation on
  /// both sides, so under Foundation's parser each tilde can both open and close a run: they paired
  /// with each other rather than marking their own prices as approximate.
  ///
  /// GFM strikethrough is `~~`. A single `~` is a character.
  @MainActor
  func testApproximatePricesAreTextRatherThanStrikethroughDelimiters() throws {
    let rendered = try XCTUnwrap(
      OmiMarkdownContent.inlineAttributedString(
        from: "**Jonas Brothers** (~$190), **Zedd** (~$230), **Masego** (~$360)",
        style: .assistant,
        fontSize: 14,
        fontScale: 1
      ))

    XCTAssertEqual(
      String(rendered.characters),
      "Jonas Brothers (~$190), Zedd (~$230), Masego (~$360)",
      "Every price keeps the tilde that made it approximate.")
    XCTAssertTrue(
      Self.struckText(in: rendered).isEmpty,
      "Nothing in a list of prices is struck through.")
  }

  @MainActor
  func testDoubleTildeIsStillStrikethrough() throws {
    let rendered = try XCTUnwrap(
      OmiMarkdownContent.inlineAttributedString(
        from: "a ~~struck~~ b", style: .assistant, fontSize: 14, fontScale: 1))

    XCTAssertEqual(String(rendered.characters), "a struck b")
    XCTAssertEqual(
      Self.struckText(in: rendered), ["struck"],
      "The GFM delimiter still means what GFM says it means.")
  }

  /// Other lone tildes that reach this renderer from ordinary assistant prose.
  @MainActor
  func testLoneTildesSurviveInProse() throws {
    for source in ["approx ~5 minutes", "cd ~/Documents and ~/Desktop", "a ~~~three~~~ b"] {
      let rendered = try XCTUnwrap(
        OmiMarkdownContent.inlineAttributedString(
          from: source, style: .assistant, fontSize: 14, fontScale: 1))
      XCTAssertEqual(String(rendered.characters), source, "\(source) is ordinary text")
      XCTAssertTrue(Self.struckText(in: rendered).isEmpty)
    }
  }

  /// A backslash is literal inside a code span, so escaping there would print `\~` at the user. The
  /// escape has to step over code spans — where tildes are already inert — rather than through them.
  @MainActor
  func testCodeSpansDoNotPickUpEscapeCharacters() throws {
    let rendered = try XCTUnwrap(
      OmiMarkdownContent.inlineAttributedString(
        from: "`rm ~/a ~/b` and (~$5)", style: .assistant, fontSize: 14, fontScale: 1))

    XCTAssertEqual(String(rendered.characters), "rm ~/a ~/b and (~$5)")
    XCTAssertFalse(String(rendered.characters).contains("\\"))
  }

  /// The escaper itself, at the delimiter level it operates on.
  func testOnlyRunsOfExactlyTwoSurviveAsDelimiters() {
    XCTAssertEqual(OmiMarkdownTilde.escapingNonPairDelimiters("(~$190)"), "(\\~$190)")
    XCTAssertEqual(OmiMarkdownTilde.escapingNonPairDelimiters("~~struck~~"), "~~struck~~")
    XCTAssertEqual(OmiMarkdownTilde.escapingNonPairDelimiters("~~~three~~~"), "\\~\\~\\~three\\~\\~\\~")
    XCTAssertEqual(
      OmiMarkdownTilde.escapingNonPairDelimiters("no tildes"), "no tildes",
      "Text without a tilde is returned untouched.")
  }

  private static func struckText(in attributed: AttributedString) -> [String] {
    attributed.runs.compactMap { run in
      guard run.inlinePresentationIntent?.contains(.strikethrough) == true else { return nil }
      return String(attributed[run.range].characters)
    }
  }
}
