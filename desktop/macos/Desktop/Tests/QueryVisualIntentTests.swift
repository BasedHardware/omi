import XCTest

@testable import Omi_Computer

/// Tests for `QueryVisualIntent.wantsScreenshot` — the heuristic that
/// decides whether to capture the screen for a given query.
///
/// Conservative: ambiguous queries return `true` so the screen is
/// captured. The cost of a wasted 100-300ms capture is much less than
/// the cost of missing a screenshot the user expected.
final class QueryVisualIntentTests: XCTestCase {

    // MARK: - Track 2 benchmark prompts

    /// The judge's listed examples. "What do you see?" needs the screen;
    /// the others don't.
    func testJudgeExamplePrompts() {
        XCTAssertTrue(
            QueryVisualIntent.wantsScreenshot("What do you see?"),
            "'What do you see?' obviously needs the screen"
        )
        XCTAssertFalse(
            QueryVisualIntent.wantsScreenshot("Hi, how are you?"),
            "Greeting — no screen needed"
        )
        XCTAssertTrue(
            QueryVisualIntent.wantsScreenshot("What should I do today?"),
            "'What should I do today?' may need screen context (calendar, "
            + "tasks widget) — capture"
        )
        XCTAssertFalse(
            QueryVisualIntent.wantsScreenshot("What did I just discuss?"),
            "Personal recall — no screen needed"
        )
    }

    // MARK: - Top-20 popular queries (most don't need a screen)

    func testPopularQueriesDoNotNeedScreen() {
        let noScreen = [
            "remind me to call mom tomorrow",
            "what's the weather",
            "translate 'good morning' to Spanish",
            "what's 15% of 240",
            "what did I say about pricing last week",
            "explain quantum entanglement like I'm 10",
            "tell me a joke",
            "play some focus music",
            "what time is it in Tokyo",
        ]
        for q in noScreen {
            XCTAssertFalse(
                QueryVisualIntent.wantsScreenshot(q),
                "Expected no screen for: \(q)"
            )
        }
    }

    func testVisualQueriesDoNeedScreen() {
        let yesScreen = [
            "what's on my screen",
            "what does this say",
            "can you see my screen",
            "summarize the article on this page",
            "open Linear and create a new issue",
            "click the submit button",
            "what's in this folder",
            "highlight the error",
            "what color is the header",
        ]
        for q in yesScreen {
            XCTAssertTrue(
                QueryVisualIntent.wantsScreenshot(q),
                "Expected screen capture for: \(q)"
            )
        }
    }

    // MARK: - Deictic references

    /// "This", "that", "these" — common in screen-grounded queries
    /// when paired with a question/imperative verb.
    func testDeicticReferences() {
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("explain this"))
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("what is that"))
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("summarize these"))
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("fix this"))
    }

    /// Time references using "this" / "that" should NOT trigger a
    /// screen capture — the user is talking about time, not the screen.
    /// Code review on PR #7889 caught this false positive.
    func testTimeDeicticsDoNotCapture() {
        XCTAssertFalse(QueryVisualIntent.wantsScreenshot("this morning"))
        XCTAssertFalse(QueryVisualIntent.wantsScreenshot("that afternoon"))
        XCTAssertFalse(QueryVisualIntent.wantsScreenshot("this evening"))
        XCTAssertFalse(QueryVisualIntent.wantsScreenshot("yesterday"))
        XCTAssertFalse(QueryVisualIntent.wantsScreenshot("next week"))
    }

    /// "Translate this" / "spell this" / "read this sentence" are
    /// talking about text, not the screen. "read this" is in the
    /// noun-signal list for screen-content queries, but bare "translate
    /// this" without "screen" / "page" / "document" should not capture.
    /// The deictic patterns require a question or specific verb, so
    /// "translate this" does not match.
    func testTextDeicticsDoNotCapture() {
        XCTAssertFalse(QueryVisualIntent.wantsScreenshot("translate this for me"))
        XCTAssertFalse(QueryVisualIntent.wantsScreenshot("spell this word"))
        XCTAssertFalse(QueryVisualIntent.wantsScreenshot("define this term"))
    }

    // MARK: - Screen nouns

    func testScreenNouns() {
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("what's on the screen"))
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("open a new tab"))
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("show me the document"))
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("read the error message"))
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("zoom in on the chart"))
    }

    // MARK: - Edge cases

    func testEmptyQueryDoesNotCapture() {
        // Defensive: empty query shouldn't capture. The fast-path in
        // QueryRouter also handles this (returns .chat(.fastPath)), but
        // belt-and-suspenders.
        XCTAssertFalse(QueryVisualIntent.wantsScreenshot(""))
        XCTAssertFalse(QueryVisualIntent.wantsScreenshot("   "))
    }

    func testCasingDoesNotAffectDetection() {
        XCTAssertEqual(
            QueryVisualIntent.wantsScreenshot("WHAT'S ON MY SCREEN"),
            QueryVisualIntent.wantsScreenshot("what's on my screen")
        )
    }

    func testSubstringMatchAnywhere() {
        // Visual signals can appear anywhere in the query, not just the
        // start. "Look at" appears mid-phrase; the detector should
        // match it. (We don't test "translate this" here anymore —
        // that case is in `testTextDeicticsDoNotCapture` and verifies
        // the refined deictic check correctly does NOT match.)
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("I want to see the settings"))
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("can you look at this window"))
    }

    // MARK: - Conservative: ambiguous → capture

    /// If the detector is unsure, it returns `true` (capture). Better
    /// to over-capture than to miss a screenshot the user expected.
    func testAmbiguousQueriesCapture() {
        let ambiguous = [
            "what is this", "show me", "look at this",
        ]
        for q in ambiguous {
            XCTAssertTrue(
                QueryVisualIntent.wantsScreenshot(q),
                "Ambiguous query should capture (conservative): \(q)"
            )
        }
    }

    /// "Help" alone is too ambiguous — the user might want general
    /// assistance, not screen context. Don't waste a screenshot on it.
    func testBareHelpDoesNotCapture() {
        XCTAssertFalse(QueryVisualIntent.wantsScreenshot("help"))
        XCTAssertFalse(QueryVisualIntent.wantsScreenshot("help me"))
    }
}
