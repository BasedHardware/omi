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
            "spawn a subagent to look at my memories",
            "start a background agent to review my notes",
            // long, no explicit signal — word-count gate should still keep the router
            "tell me a fun fact about cats and dogs and birds and fish and lizards please",
        ]
        for q in keep {
            XCTAssertFalse(
                FloatingControlBarManager.routerCanSkipToChat(q),
                "Expected to KEEP the router for task-like query: \"\(q)\"")
        }
    }

    func testExplicitFloatingAgentRequestsAreDetected() {
        let spawnRequests: [(String, String)] = [
            ("spawn a subagent to look at my memories", "look at my memories"),
            ("start a background agent to review my notes", "review my notes"),
            ("launch an agent to research this", "research this"),
            ("make a floating agent for this task", "this task"),
            ("have an agent make a simple snake facts html page", "make a simple snake facts html page"),
        ]
        for (q, task) in spawnRequests {
            XCTAssertTrue(
                AgentPillsManager.explicitlyRequestsFloatingAgent(q),
                "Expected explicit floating-agent request: \"\(q)\"")
            XCTAssertEqual(
                AgentPillsManager.floatingAgentHandoff(for: q)?.agentTask,
                task,
                "Expected child agent task to exclude the parent control command: \"\(q)\"")
        }

        let normalFollowUps = [
            "how did it go?",
            "ask this agent what it found",
            "what do you know about my memories?",
            "can you explain that result?",
        ]
        for q in normalFollowUps {
            XCTAssertFalse(
                AgentPillsManager.explicitlyRequestsFloatingAgent(q),
                "Expected normal follow-up, not floating-agent control command: \"\(q)\"")
        }
    }

    // MARK: - scoped negation guard (Cubic P1)

    func testNegationGuardDoesNotSuppressLegitimateSpawnRequests() {
        // These contain "no"/"not"/"without"/"don't" for unrelated reasons but are
        // legitimate spawn requests — must NOT be suppressed by the negation guard.
        let legitimateSpawns = [
            "spawn an agent to run without errors",
            "start a background agent that never logs secrets",
            "launch a subagent to fix the not-found bug",
            "create a pill to clean up notes with no duplicates",
            "run an agent to remove items that are not pinned",
            // Action verb after negation but NOT followed by an agent noun
            "don't make me laugh, spawn an agent",
            "not sure how to start a background agent",
            "never mind, launch an agent anyway",
        ]
        for q in legitimateSpawns {
            XCTAssertTrue(
                AgentPillsManager.explicitlyRequestsFloatingAgent(q),
                "Expected floating-agent request, but negation guard wrongly suppressed: \"\(q)\"")
        }
    }

    func testNegationGuardSuppressesExplicitOptOuts() {
        // These are explicit opt-outs that should answer inline, not spawn a pill.
        let optOuts = [
            "don't spawn an agent",
            "do not create a pill",
            "no agent, just answer here",
            "not an agent, just tell me",
            "without spawning a subagent",
            "without a pill",
            "don't run any agents",
            // Gerund-based opt-outs
            "not spawning an agent",
            "never creating pills",
            "without creating any agents",
        ]
        for q in optOuts {
            XCTAssertFalse(
                AgentPillsManager.explicitlyRequestsFloatingAgent(q),
                "Expected inline answer, but negation guard did NOT suppress explicit opt-out: \"\(q)\"")
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
