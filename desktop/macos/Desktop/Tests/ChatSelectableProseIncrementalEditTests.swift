import AppKit
import XCTest

@testable import Omi_Computer

/// The AppKit prose view's two per-flush contracts: an update edits the text
/// storage from the first character that differs (in characters *or*
/// attributes), and the height it reports from its own layout is the height
/// the throwaway measurement would have produced.
@MainActor
final class ChatSelectableProseIncrementalEditTests: XCTestCase {

  private func prose(_ markdown: String) throws -> NSAttributedString {
    try XCTUnwrap(
      ChatSelectableProse.attributedString(markdown: markdown, style: .assistant, fontSize: 14, fontScale: 1))
  }

  // MARK: - Incremental edits

  func testAppendingWordsEditsOnlyTheTail() throws {
    let old = try prose("The transcript keeps every row")
    let new = try prose("The transcript keeps every row eagerly mounted so the")
    let storage = NSTextStorage(attributedString: old)

    XCTAssertEqual(
      ChatSelectableProseText.commonAttributedPrefixLength(old, new), old.length,
      "an append shares the whole old string as its prefix")
    ChatSelectableProseText.apply(new, to: storage)
    XCTAssertTrue(storage.isEqual(to: new), "the storage must end up exactly equal to the new prose")
  }

  func testAClosingEmphasisReStylesTheWordsThatArrivedEarlier() throws {
    let old = try prose("Keep **every row")
    let new = try prose("Keep **every row** mounted")
    let storage = NSTextStorage(attributedString: old)

    let prefix = ChatSelectableProseText.commonAttributedPrefixLength(old, new)
    // `**every row` was literal text; once the run closes those words turn
    // bold, so the prefix ends where the styling diverges — before them.
    XCTAssertLessThan(prefix, old.length)
    XCTAssertEqual(String(old.string.prefix(prefix)), "Keep ")
    ChatSelectableProseText.apply(new, to: storage)
    XCTAssertTrue(storage.isEqual(to: new))
  }

  func testAnIdenticalUpdateDoesNotTouchTheStorage() throws {
    let text = try prose("Nothing changed here.")
    let storage = NSTextStorage(attributedString: text)
    let edits = EditCount()
    let observer = NotificationCenter.default.addObserver(
      forName: NSTextStorage.didProcessEditingNotification, object: storage, queue: nil
    ) { _ in edits.increment() }
    defer { NotificationCenter.default.removeObserver(observer) }

    ChatSelectableProseText.apply(text, to: storage)
    XCTAssertEqual(edits.value, 0)
  }

  func testAnEditNeverSplitsAComposedCharacter() throws {
    // "e" + combining acute vs. a precomposed "é": the character prefix lands
    // inside the sequence; the edit must back up to its start.
    let old = NSAttributedString(string: "caf" + "e\u{0301}" + " au lait")
    let new = NSAttributedString(string: "caf" + "e\u{0301}\u{0308}" + " au lait")
    let prefix = ChatSelectableProseText.commonAttributedPrefixLength(old, new)
    XCTAssertEqual(prefix, 3, "the edit starts at the composed sequence, not inside it")
    let storage = NSTextStorage(attributedString: old)
    ChatSelectableProseText.apply(new, to: storage)
    // Characters only: an attribute-less storage has its font fixed on edit,
    // which is TextKit's business, not this edit's.
    XCTAssertEqual(storage.string, new.string)
  }

  // MARK: - Live height

  func testTheLiveLayoutReportsTheSameHeightAsAThrowawayMeasurement() throws {
    let markdown = (0..<12).map {
      "Line \($0) of prose that is long enough to wrap at a narrow column, with **bold** and `code`."
    }
    .joined(separator: "\n")
    let attributed = try prose(markdown)
    let textView = ChatProseTextView(usingTextLayoutManager: false)
    textView.textContainerInset = .zero
    textView.textContainer?.lineFragmentPadding = 0
    textView.textContainer?.widthTracksTextView = true
    textView.isVerticallyResizable = false
    textView.isHorizontallyResizable = false
    textView.textStorage?.setAttributedString(attributed)

    for width in [320.0, 480.0, 640.0] as [CGFloat] {
      textView.frame = NSRect(x: 0, y: 0, width: width, height: 10)
      let throwaway = ChatSelectableProseText.height(of: attributed, fittingWidth: width)
      let live = ChatSelectableProseText.liveHeight(of: textView, showing: attributed, fittingWidth: width)
      XCTAssertEqual(live, throwaway, "at width \(width) the live layout must agree with the throwaway measure")
    }
  }

  func testTheLiveLayoutDeclinesAWidthItIsNotAt() throws {
    let attributed = try prose("Short.")
    let textView = ChatProseTextView(usingTextLayoutManager: false)
    textView.textContainer?.widthTracksTextView = true
    textView.textStorage?.setAttributedString(attributed)
    textView.frame = NSRect(x: 0, y: 0, width: 300, height: 10)

    XCTAssertNil(
      ChatSelectableProseText.liveHeight(of: textView, showing: attributed, fittingWidth: 200),
      "a proposal at another width must fall back to the throwaway measure, never resize the live container")
    XCTAssertNil(
      ChatSelectableProseText.liveHeight(of: textView, showing: try prose("Other."), fittingWidth: 300),
      "a view showing different text cannot answer for this one")
  }

  // MARK: - Preprocessing without regular expressions

  func testHeaderAndBulletPreprocessingMatchesTheRegularExpressionForm() {
    let cases = [
      "# Title", "###### Deep", "####### Seven hashes", "##No space", "## ", "##\t\tTabbed heading",
      "* item", "  * nested item", "\t* tabbed item", "*not a bullet", "**bold** text", " * spaced",
      "plain line", "", "#", "# a * b", "  ",
    ]
    for line in cases {
      XCTAssertEqual(
        OmiMarkdownContent.preprocessText(line), Self.regexPreprocess(line),
        "preprocessing must match the original regular-expression rules for \(line.debugDescription)")
    }
    let joined = cases.joined(separator: "\n")
    XCTAssertEqual(OmiMarkdownContent.preprocessText(joined), Self.regexPreprocess(joined))
  }

  private final class EditCount: @unchecked Sendable {
    private let lock = NSLock()
    private var count = 0
    var value: Int {
      lock.lock()
      defer { lock.unlock() }
      return count
    }
    func increment() {
      lock.lock()
      count += 1
      lock.unlock()
    }
  }

  /// The rules as they were written before, kept here as the oracle.
  private static func regexPreprocess(_ text: String) -> String {
    text.components(separatedBy: "\n").map { line in
      var processed = line
      if let match = processed.range(of: #"^#{1,6}\s+"#, options: .regularExpression) {
        let headerText = String(processed[match.upperBound...])
        processed = "**\(headerText)**"
      }
      processed = processed.replacingOccurrences(
        of: #"^(\s*)\* "#, with: "$1• ", options: .regularExpression)
      return processed
    }.joined(separator: "\n")
  }
}
