import XCTest

@testable import Omi_Computer

/// Tests for `ChatProvider.floatingBarSystemPromptPrefix` — the inline chat
/// prompt for the floating bar / PTT path.
///
/// The prompt is a **wire-format contract for speed**. It tells the model
/// when to use memory tools (slow) vs when to answer directly (fast). The
/// old prompt said "ALWAYS check memories before ANY question", which
/// forced 1-2 tool-call round trips on every greeting and general-knowledge
/// question — adding 500-2000ms to every user-perceived response.
///
/// The new prompt softens the rule: tool calls only when the question is
/// genuinely personal or context-dependent. These tests pin that behavior
/// so a future edit can't silently regress speed.
final class FloatingBarSystemPromptTests: XCTestCase {

    private let prompt = ChatProvider.floatingBarSystemPromptPrefix

    // MARK: - Tool-call behavior

    /// The old prompt's killer phrase: "ALWAYS check... before ANY question".
    /// This forced tool calls on greetings, definitions, math, etc. and
    /// added 500-2000ms to every user-perceived response. PR 3 (Track 2)
    /// removed it. This test guards the regression.
    func testPromptDoesNotForceToolCallsOnEveryQuestion() {
        XCTAssertFalse(
            prompt.lowercased().contains("before any question"),
            "Old prompt forced tool calls on every question — that was 500-2000ms of tool latency on greetings. PR 3 removed this. Adding it back is a Track 2 regression."
        )
        XCTAssertFalse(
            prompt.lowercased().contains("ALWAYS check"),
            "Prompt should not say 'ALWAYS check memories' — that's a tool-call-on-every-query rule."
        )
    }

    /// The new prompt should still let Claude call tools for genuinely
    /// personal/contextual questions. This is the only case where tool
    /// calls are appropriate from the floating bar.
    func testPromptStillAllowsToolsForPersonalQuestions() {
        XCTAssertTrue(
            prompt.lowercased().contains("get_memories")
            || prompt.lowercased().contains("search_memories"),
            "Prompt must mention the memory tools so Claude uses them for personal questions."
        )
        XCTAssertTrue(
            prompt.lowercased().contains("personal")
            || prompt.lowercased().contains("context-dependent")
            || prompt.lowercased().contains("preferences"),
            "Prompt must include a heuristic for when to use tools (personal / context-dependent)."
        )
    }

    /// The new prompt must explicitly tell Claude to answer DIRECTLY for
    /// common fast-answer categories: greetings, general knowledge,
    /// opinions, definitions, math, translations. Without this, the model
    /// defaults to a cautious "let me check your memories" stance.
    func testPromptEncouragesDirectAnswersForCommonCases() {
        let fastAnswerCategories = [
            "greetings", "general-knowledge", "opinions",
            "definitions", "explanations", "math",
            "translations", "simple lookups",
        ]
        for category in fastAnswerCategories {
            XCTAssertTrue(
                prompt.lowercased().contains(category),
                "Prompt must list '\(category)' as a category to answer directly without tool calls."
            )
        }
    }

    // MARK: - Quality rules (unchanged from old prompt)

    func testPromptKeepsNoFollowUpQuestionsRule() {
        // The quality bar stays the same: short answers, no clarification
        // questions. This is what the user pays for (judge evaluates
        // quality, not just speed).
        XCTAssertTrue(
            prompt.lowercased().contains("NEVER ask follow-up questions")
            || prompt.lowercased().contains("never ask follow-up questions")
        )
    }

    func testPromptKeepsNoListsNoHeadersRule() {
        XCTAssertTrue(
            prompt.lowercased().contains("no lists")
            || prompt.lowercased().contains("No lists")
        )
        XCTAssertTrue(
            prompt.lowercased().contains("no headers")
            || prompt.lowercased().contains("No headers")
        )
    }

    func testPromptKeepsOneToTwoSentenceRule() {
        XCTAssertTrue(
            prompt.lowercased().contains("1-2 sentences")
            || prompt.lowercased().contains("1-2 sentences")
        )
    }

    // MARK: - Screenshot rule (unchanged)

    func testPromptKeepsScreenshotDeicticRule() {
        // "What do you see?", "which one?", "what's on my screen?" all
        // depend on the screenshot being read. This rule must stay.
        XCTAssertTrue(
            prompt.lowercased().contains("screenshot")
        )
        XCTAssertTrue(
            prompt.lowercased().contains("which one")
            || prompt.lowercased().contains("which option")
            || prompt.lowercased().contains("what's on my screen")
        )
    }

    // MARK: - Web search rule (unchanged)

    func testPromptKeepsWebSearchForProperNouns() {
        XCTAssertTrue(
            prompt.lowercased().contains("search the web")
            || prompt.lowercased().contains("web search")
        )
    }
}
