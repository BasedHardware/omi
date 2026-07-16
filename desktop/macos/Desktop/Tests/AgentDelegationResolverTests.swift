import XCTest

@testable import Omi_Computer

final class AgentDelegationBoundaryTests: XCTestCase {
  func testBriefValidatorRejectsVagueDelegationBriefs() {
    XCTAssertFalse(
      DelegationBriefValidator.isStructurallyAcceptable(
        brief: "Perform a new search for the user.",
        rawIntent: "another search"))
    XCTAssertFalse(
      DelegationBriefValidator.isStructurallyAcceptable(
        brief: "another search",
        rawIntent: "another search"))
    XCTAssertFalse(
      DelegationBriefValidator.isStructurallyAcceptable(
        brief: "do that",
        rawIntent: "do that"))
  }

  func testBriefValidatorAcceptsSelfContainedDelegationBrief() {
    XCTAssertTrue(
      DelegationBriefValidator.isStructurallyAcceptable(
        brief: "Using OpenClaw, search for current AI trends on X and summarize the newest notable findings.",
        rawIntent: "do another search"))
    XCTAssertTrue(
      DelegationBriefValidator.isStructurallyAcceptable(
        brief: "Search local database",
        rawIntent: nil))
  }

  func testKernelControlPlaneIsOnlyProductionSpawnBoundaryForTopLevelSurfaces() throws {
    // omi-test-quality: source-inspection -- static contract: no Swift semantic router or pre-loop spawn boundary may return
    let realtime = try RealtimeHubControllerSourceTestSupport.moduleSource(testFilePath: #filePath)
    let floating = try sourceFile("FloatingControlBar/FloatingControlBarWindow.swift")
    let pills = try sourceFile("FloatingControlBar/AgentPill.swift")
    let executor = try sourceFile("FloatingControlBar/AgentDelegationExecutor.swift")
    let coordinator = try sourceFile("Chat/DesktopCoordinatorService.swift")

    XCTAssertFalse(realtime.contains("AgentPillsManager.shared.spawnFromUserQuery("))
    XCTAssertFalse(floating.contains("AgentPillsManager.shared.spawnFromUserQuery("))
    XCTAssertFalse(realtime.contains("AgentDelegationResolver"))
    XCTAssertFalse(floating.contains("AgentDelegationResolver"))
    XCTAssertFalse(pills.contains("static func classify("))
    XCTAssertFalse(realtime.contains("AgentDelegationExecutor.shared.spawnResolvedDelegation"))
    XCTAssertTrue(realtime.contains("invokeExternallyAuthorizedTool("))
    XCTAssertTrue(floating.contains("AgentDelegationExecutor.shared.spawnResolvedDelegation"))
    XCTAssertFalse(executor.contains("AgentPillsManager.shared.spawnFromUserQuery("))
    XCTAssertTrue(executor.contains("AgentPillsManager.shared.spawn("))
    XCTAssertTrue(pills.contains("DesktopCoordinatorService.shared.spawnAgent("))
    XCTAssertTrue(coordinator.contains(#"static let spawnAgent = "spawn_agent""#))
  }

  func testLegacySemanticRouterSourcesAreDeleted() throws {
    let sourcesRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar")

    XCTAssertFalse(
      FileManager.default.fileExists(
        atPath: sourcesRoot.appendingPathComponent("AgentDelegationResolver.swift").path))
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
