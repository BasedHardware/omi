import XCTest

@testable import Omi_Computer

final class AgentSelectorTests: XCTestCase {
  func testClassifyCategories() {
    XCTAssertEqual(AgentSelector.classify("refactor the auth function and fix the bug"), .codebaseEdit)
    XCTAssertEqual(AgentSelector.classify("run npm install and build the project"), .shellOps)
    XCTAssertEqual(AgentSelector.classify("reply to the whatsapp from mom"), .messaging)
    XCTAssertEqual(AgentSelector.classify("keep monitoring the feed overnight"), .longAutonomous)
    XCTAssertEqual(AgentSelector.classify("research the best vector databases"), .research)
    XCTAssertEqual(AgentSelector.classify("what's the weather"), .general)
  }

  func testBestPicksCodeAgentForCoding() {
    // acp and codex both score 3 for codebaseEdit; default priority puts Claude Code first.
    let best = AgentSelector.best(brief: "implement a retry wrapper in the repo", available: [.piMono, .acp, .codex])
    XCTAssertEqual(best, .acp)
  }

  func testCodexLeadsShellOps() {
    XCTAssertEqual(AgentSelector.best(brief: "run the migration in the terminal", available: [.acp, .codex]), .codex)
  }

  func testMultiChannelAgentLeadsMessaging() {
    XCTAssertEqual(AgentSelector.best(brief: "reply to the telegram from sam", available: [.acp, .hermes]), .hermes)
  }

  func testLongRunningAgentLeadsOvernight() {
    XCTAssertEqual(AgentSelector.best(brief: "keep monitoring overnight", available: [.acp, .openclaw]), .openclaw)
  }

  func testUserDefaultBreaksTies() {
    let best = AgentSelector.best(
      brief: "add a unit test to the repo", available: [.acp, .codex], userDefault: .codex)
    XCTAssertEqual(best, .codex)  // tie at 3 -> user default wins
  }

  func testRankReturnsOrderedFallbackChain() {
    let chain = AgentSelector.rank(
      brief: "implement a feature in the repo", available: [.piMono, .hermes, .codex, .acp])
    XCTAssertEqual(chain.first, .acp)  // best fit
    XCTAssertEqual(chain.last, .piMono)  // Omi AI is the general default, last for coding
    XCTAssertEqual(Set(chain), Set<AgentHarnessMode>([.piMono, .hermes, .codex, .acp]))
  }

  func testEmptyAvailableHasNoBest() {
    XCTAssertNil(AgentSelector.best(brief: "fix the bug", available: []))
  }
}
