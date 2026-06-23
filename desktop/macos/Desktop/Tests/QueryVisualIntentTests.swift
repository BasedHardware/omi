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

    /// "This", "that", "these" — common in screen-grounded queries.
    func testDeicticReferences() {
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("explain this"))
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("what is that"))
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("summarize these"))
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("translate this for me"))
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
        // start. "Translate this" has "this" mid-phrase; the detector
        // should still match.
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("can you translate this for me"))
        XCTAssertTrue(QueryVisualIntent.wantsScreenshot("I want to see the settings"))
    }

    // MARK: - Conservative: ambiguous → capture

    /// If the detector is unsure, it returns `true` (capture). Better
    /// to over-capture than to miss a screenshot the user expected.
    func testAmbiguousQueriesCapture() {
        let ambiguous = [
            "help", "what is this", "show me", "look at this",
        ]
        for q in ambiguous {
            XCTAssertTrue(
                QueryVisualIntent.wantsScreenshot(q),
                "Ambiguous query should capture (conservative): \(q)"
            )
        }
    }
}
