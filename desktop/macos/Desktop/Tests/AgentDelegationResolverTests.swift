import XCTest

@testable import Omi_Computer

final class AgentDelegationBoundaryTests: XCTestCase {
  func testKernelControlPlaneIsOnlyProductionProviderSpawnBoundary() throws {
    // omi-test-quality: source-inspection -- static contract: no Swift semantic router may interpret user wording into a provider spawn.
    let realtime = try RealtimeHubControllerSourceTestSupport.moduleSource(testFilePath: #filePath)
    let floating = try sourceFile("FloatingControlBar/FloatingControlBarWindow.swift")
    let pills = try sourceFile("FloatingControlBar/AgentPill.swift")
    let coordinator = try sourceFile("Chat/DesktopCoordinatorService.swift")

    XCTAssertFalse(realtime.contains("AgentPillsManager.shared.spawnFromUserQuery("))
    XCTAssertFalse(floating.contains("AgentPillsManager.shared.spawnFromUserQuery("))
    XCTAssertFalse(realtime.contains("AgentDelegationResolver"))
    XCTAssertFalse(floating.contains("AgentDelegationResolver"))
    XCTAssertFalse(pills.contains("static func classify("))
    XCTAssertFalse(realtime.contains("AgentDelegationExecutor.shared.spawnResolvedDelegation"))
    XCTAssertTrue(realtime.contains("invokeExternallyAuthorizedTool("))
    XCTAssertFalse(floating.contains("providerDirective"))
    XCTAssertFalse(floating.contains("resolveDelegationAndDispatch"))
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
    XCTAssertFalse(
      FileManager.default.fileExists(
        atPath: sourcesRoot.appendingPathComponent("AgentDelegationExecutor.swift").path))
    XCTAssertFalse(
      FileManager.default.fileExists(
        atPath: sourcesRoot.appendingPathComponent("DelegationBriefValidator.swift").path))
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
