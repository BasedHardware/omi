import XCTest

@testable import Omi_Computer

/// Regression coverage for `ChatProvider.normalizeAssistantSentenceSpacing`.
/// The normalizer inserts a space after sentence punctuation followed by an
/// uppercase letter. Previously it ran over the whole message with no code
/// awareness, so identifiers like `pd.DataFrame` or `System.IO` inside code were
/// rewritten to `pd. DataFrame` / `System. IO` and — because the streamed text
/// becomes the durable transcript — that corruption was persisted. The normalizer
/// now preserves fenced blocks and inline backtick spans verbatim.
@MainActor
final class ChatSentenceSpacingTests: XCTestCase {

    // MARK: - Prose (behavior preserved)

    func testInsertsSpaceAfterSentencePunctuationInProse() {
        XCTAssertEqual(ChatProvider.normalizeAssistantSentenceSpacing("Hello.World"), "Hello. World")
        XCTAssertEqual(ChatProvider.normalizeAssistantSentenceSpacing("Great!Lets go"), "Great! Lets go")
        XCTAssertEqual(ChatProvider.normalizeAssistantSentenceSpacing("Done?Then stop"), "Done? Then stop")
    }

    func testInsertsSpaceBeforeQuotedUppercase() {
        XCTAssertEqual(
            ChatProvider.normalizeAssistantSentenceSpacing("He said.\"Yes\""),
            "He said. \"Yes\""
        )
    }

    func testLeavesProperlySpacedProseUnchanged() {
        let text = "This is fine. And so is this."
        XCTAssertEqual(ChatProvider.normalizeAssistantSentenceSpacing(text), text)
    }

    // MARK: - Inline code (must not be mangled)

    func testDoesNotMangleInlineCodeIdentifiers() {
        XCTAssertEqual(
            ChatProvider.normalizeAssistantSentenceSpacing("Use `pd.DataFrame` to load it"),
            "Use `pd.DataFrame` to load it"
        )
        XCTAssertEqual(
            ChatProvider.normalizeAssistantSentenceSpacing("Import `System.IO` first"),
            "Import `System.IO` first"
        )
    }

    func testNormalizesProseButPreservesInlineCodeOnSameLine() {
        XCTAssertEqual(
            ChatProvider.normalizeAssistantSentenceSpacing("Done.Call `a.Bar()` here.Next"),
            "Done. Call `a.Bar()` here. Next"
        )
    }

    func testUnterminatedInlineBacktickTreatsRemainderAsCode() {
        // A backtick still open mid-stream: everything after it stays verbatim.
        XCTAssertEqual(
            ChatProvider.normalizeAssistantSentenceSpacing("See `x.Y"),
            "See `x.Y"
        )
    }

    // MARK: - Fenced code blocks (must not be mangled)

    func testDoesNotMangleFencedCodeBlock() {
        let input = """
        Here is code.Read it:
        ```python
        df = pd.DataFrame()
        obj.Method()
        ```
        Runs fine.Enjoy
        """
        let expected = """
        Here is code. Read it:
        ```python
        df = pd.DataFrame()
        obj.Method()
        ```
        Runs fine. Enjoy
        """
        XCTAssertEqual(ChatProvider.normalizeAssistantSentenceSpacing(input), expected)
    }

    func testUnterminatedFenceTreatsRemainderAsCode() {
        let input = """
        Intro.Text
        ```swift
        let x = Foo.Bar()
        y.Baz()
        """
        let expected = """
        Intro. Text
        ```swift
        let x = Foo.Bar()
        y.Baz()
        """
        XCTAssertEqual(ChatProvider.normalizeAssistantSentenceSpacing(input), expected)
    }
}
