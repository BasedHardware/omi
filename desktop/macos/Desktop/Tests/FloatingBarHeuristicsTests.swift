import XCTest
@testable import Omi_Computer

/// Guardrails for the floating-bar latency heuristics (#2 conditional screenshot,
/// #3 router skip). These are pure functions, so we can pin their classifications
/// directly instead of relying on end-to-end traces.
final class FloatingBarHeuristicsTests: XCTestCase {

    // MARK: - routerCanSkipToChat (skip the Haiku router for obvious chit-chat)

    func testRouterSkipsObviousChat() {
        let skip = [
            "What's up?",
            "Hey, how's it going?",
            "What's the capital of France?",
            "What did I do this morning?",
            "Who won the world cup in 2018?",
            "How does a hash map work?",
        ]
        for q in skip {
            XCTAssertTrue(
                FloatingControlBarManager.routerCanSkipToChat(q),
                "Expected to skip the router for chit-chat/general: \"\(q)\"")
        }
    }

    func testRouterKeptForTaskQueries() {
        let keep = [
            "Research the best mechanical keyboards and write me a summary",
            "Go through all my emails and summarize them",
            "Draft a plan for my week",
            "Create a report of my app usage",
            "Monitor my calendar and keep track of conflicts",
            // action/browser commands — must keep the router so they can route to an agent
            "open e-mails on my browser and get me top 5",
            "Can you open my browser and reply to the latest email?",  // question-phrased command
            "send a message to my team about the launch",
            "buy the top-rated keyboard on Amazon",
            "download the report and rename it",
            // long, no explicit signal — word-count gate should still keep the router
            "tell me a fun fact about cats and dogs and birds and fish and lizards please",
        ]
        for q in keep {
            XCTAssertFalse(
                FloatingControlBarManager.routerCanSkipToChat(q),
                "Expected to KEEP the router for task-like query: \"\(q)\"")
        }
    }

    // MARK: - queryNeedsScreenshot (#2: only capture when screen-related)

    func testScreenshotCapturedForVisualQueries() {
        let visual = [
            "What's on my screen right now?",
            "Read this and summarize it",
            "What does this error mean?",
            "Look at my screen and tell me what to click",
            "What is this?",
        ]
        for q in visual {
            XCTAssertTrue(
                FloatingControlBarManager.queryNeedsScreenshot(q),
                "Expected screenshot for visual query: \"\(q)\"")
        }
    }

    func testScreenshotSkippedForNonVisualQueries() {
        let nonVisual = [
            "What's up?",
            "What's my goal for today?",
            "What's the capital of France?",
            "Give me three productivity tips",
            "What did I work on this morning?",
        ]
        for q in nonVisual {
            XCTAssertFalse(
                FloatingControlBarManager.queryNeedsScreenshot(q),
                "Expected NO screenshot for non-visual query: \"\(q)\"")
        }
    }
}
