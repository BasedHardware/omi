import XCTest

@testable import Omi_Computer

final class AgentProviderRouterTests: XCTestCase {

  private func allAvailable(_ provider: AgentPillsManager.DirectedProvider) -> Bool { true }
  private func noneAvailable(_ provider: AgentPillsManager.DirectedProvider) -> Bool { false }

  // MARK: - Classification

  func testClassifiesCodingTasks() {
    XCTAssertEqual(AgentProviderRouter.classify("write a hello world script"), .coding)
    XCTAssertEqual(AgentProviderRouter.classify("Fix the bug in the login function"), .coding)
    XCTAssertEqual(AgentProviderRouter.classify("refactor the API endpoint and add a unit test"), .coding)
  }

  func testClassifiesComputerUseTasks() {
    XCTAssertEqual(AgentProviderRouter.classify("open the browser and fill the signup form"), .computerUse)
    XCTAssertEqual(AgentProviderRouter.classify("search the web for flight prices and book the cheapest"), .computerUse)
  }

  func testClassifiesGeneralTasks() {
    XCTAssertEqual(AgentProviderRouter.classify("summarize my meetings from this week"), .general)
    XCTAssertEqual(AgentProviderRouter.classify("plan a birthday dinner"), .general)
  }

  // MARK: - Routing

  func testCodingTaskPrefersCodexWhenEverythingInstalled() {
    let decision = AgentProviderRouter.route(task: "write a python script", availability: allAvailable)
    XCTAssertEqual(decision.primary, .codex)
    XCTAssertEqual(decision.fallbacks, [.hermes, .openclaw, nil])
  }

  func testComputerUseTaskPrefersOpenClawWhenEverythingInstalled() {
    let decision = AgentProviderRouter.route(
      task: "open the browser and click the first result", availability: allAvailable)
    XCTAssertEqual(decision.primary, .openclaw)
    XCTAssertEqual(decision.fallbacks, [.hermes, .codex, nil])
  }

  func testSkipsUninstalledProviders() {
    let decision = AgentProviderRouter.route(task: "write a python script") { $0 == .hermes }
    XCTAssertEqual(decision.primary, .hermes)
    XCTAssertEqual(decision.fallbacks, [nil])
  }

  func testFallsBackToDefaultOrchestratorWhenNothingInstalled() {
    let decision = AgentProviderRouter.route(task: "write a python script", availability: noneAvailable(_:))
    XCTAssertNil(decision.primary)
    XCTAssertTrue(decision.fallbacks.isEmpty)
  }

  func testChainAlwaysTerminatesWithDefaultOrchestrator() {
    let decision = AgentProviderRouter.route(task: "anything at all", availability: allAvailable)
    XCTAssertEqual(decision.fallbacks.last ?? .codex, nil)
  }

  func testReasonMentionsTaskKindAndChain() {
    let decision = AgentProviderRouter.route(task: "fix the bug", availability: allAvailable)
    XCTAssertTrue(decision.reason.contains("task=coding"))
    XCTAssertTrue(decision.reason.contains("codex"))
    XCTAssertTrue(decision.reason.contains("default"))
  }

  // MARK: - Shared dispatch decision (all spawn surfaces)

  func testDispatchExplicitNameIsDirect() {
    let d = AgentProviderRouter.dispatchDecision(providerName: "codex", brief: "anything", availability: allAvailable)
    XCTAssertEqual(d?.primary, .codex)
    XCTAssertEqual(d?.fallbacks.isEmpty, true)
    XCTAssertEqual(d?.reason, "explicit")
  }

  func testDispatchUnknownNameIsNil() {
    XCTAssertNil(AgentProviderRouter.dispatchDecision(providerName: "gemini", brief: "x", availability: allAvailable))
  }

  func testDispatchAutoRoutes() {
    let d = AgentProviderRouter.dispatchDecision(
      providerName: "auto", brief: "write a python script", availability: allAvailable)
    XCTAssertEqual(d?.primary, .codex)
  }

  func testDispatchUnnamedCodingTaskRoutesToBestReadyProvider() {
    let d = AgentProviderRouter.dispatchDecision(
      providerName: "", brief: "write a python script", availability: allAvailable)
    XCTAssertEqual(d?.primary, .codex)
    XCTAssertEqual(d?.fallbacks, [.hermes, .openclaw, nil])
  }

  func testDispatchUnnamedGeneralTaskStaysOnDefaultOrchestrator() {
    let d = AgentProviderRouter.dispatchDecision(
      providerName: "", brief: "plan a birthday dinner", availability: allAvailable)
    XCTAssertNotNil(d)
    XCTAssertNil(d?.primary)
    XCTAssertEqual(d?.fallbacks.isEmpty, true)
  }

  func testDispatchUnnamedCodingTaskWithNoReadyProvidersStaysDefault() {
    let d = AgentProviderRouter.dispatchDecision(
      providerName: "", brief: "write a python script", availability: noneAvailable(_:))
    XCTAssertNotNil(d)
    XCTAssertNil(d?.primary)
  }
}
