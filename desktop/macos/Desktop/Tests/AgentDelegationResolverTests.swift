import XCTest

@testable import Omi_Computer

final class AgentDelegationResolverTests: XCTestCase {
  func testBriefValidatorRejectsVagueDelegationBriefs() {
    XCTAssertFalse(DelegationBriefValidator.isStructurallyAcceptable(
      brief: "Perform a new search for the user.",
      rawIntent: "another search"))
    XCTAssertFalse(DelegationBriefValidator.isStructurallyAcceptable(
      brief: "another search",
      rawIntent: "another search"))
    XCTAssertFalse(DelegationBriefValidator.isStructurallyAcceptable(
      brief: "do that",
      rawIntent: "do that"))
  }

  func testBriefValidatorAcceptsSelfContainedDelegationBrief() {
    XCTAssertTrue(DelegationBriefValidator.isStructurallyAcceptable(
      brief: "Using OpenClaw, search for current AI trends on X and summarize the newest notable findings.",
      rawIntent: "do another search"))
    XCTAssertTrue(DelegationBriefValidator.isStructurallyAcceptable(
      brief: "Search local database",
      rawIntent: nil))
  }

  func testResolverPromptRequiresSelfContainedChildBriefsAndStructuredAgentContext() throws {
    let source = try sourceFile("FloatingControlBar/AgentDelegationResolver.swift")

    XCTAssertTrue(source.contains("Child-agent briefs must be self-contained"))
    XCTAssertTrue(source.contains("If context is insufficient to reconstruct a concrete task, return clarify."))
    XCTAssertTrue(source.contains("\"action\":\"chat\"|\"clarify\"|\"spawn\""))
    XCTAssertTrue(source.contains("Current and recent background agents:"))
  }

  func testDelegationExecutorIsOnlyProductionSpawnBoundaryForTopLevelSurfaces() throws {
    let realtime = try sourceFile("FloatingControlBar/RealtimeHubController.swift")
    let floating = try sourceFile("FloatingControlBar/FloatingControlBarWindow.swift")
    let executor = try sourceFile("FloatingControlBar/AgentDelegationExecutor.swift")

    XCTAssertFalse(realtime.contains("AgentPillsManager.shared.spawnFromUserQuery("))
    XCTAssertFalse(floating.contains("AgentPillsManager.shared.spawnFromUserQuery("))
    XCTAssertTrue(realtime.contains("AgentDelegationResolver.shared.resolve"))
    XCTAssertTrue(floating.contains("AgentDelegationResolver.shared.resolve"))
    XCTAssertTrue(realtime.contains("AgentDelegationExecutor.shared.spawnResolvedDelegation"))
    XCTAssertTrue(floating.contains("AgentDelegationExecutor.shared.spawnResolvedDelegation"))
    XCTAssertTrue(executor.contains("AgentPillsManager.shared.spawnFromUserQuery("))
  }

  func testTopLevelDelegationSurfacesPassStructuredAgentSnapshotsToResolver() throws {
    let realtime = try sourceFile("FloatingControlBar/RealtimeHubController.swift")
    let floating = try sourceFile("FloatingControlBar/FloatingControlBarWindow.swift")

    XCTAssertTrue(realtime.contains("agentStatusSummary: AgentPillsManager.shared.snapshotJSON(limit: 8)"))
    XCTAssertTrue(floating.contains("agentStatusSummary: AgentPillsManager.shared.snapshotJSON(limit: 8)"))
    XCTAssertFalse(realtime.contains("agentStatusSummary: AgentPillsManager.shared.statusSummary()"))
    XCTAssertFalse(floating.contains("agentStatusSummary: AgentPillsManager.shared.statusSummary()"))
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
