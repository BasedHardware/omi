import XCTest

@testable import Omi_Computer

@MainActor
final class ChatToolExecutorSpawnAgentTests: XCTestCase {
  func testFloatingPillCannotSpawnNestedFloatingPill() async {
    let before = AgentPillsManager.shared.pills.count
    let toolCall = ToolCall(
      name: "spawn_agent",
      arguments: ["brief": "Sleep for 10 seconds", "title": "Sleep Agent"],
      thoughtSignature: nil)

    let result = await ChatToolExecutor.execute(
      toolCall,
      originatingClientScope: "floating-pill")

    XCTAssertTrue(result.contains("unavailable from an existing floating background agent"))
    XCTAssertEqual(AgentPillsManager.shared.pills.count, before)
  }

  func testChatSpawnAgentRejectsEmptyObjectiveBeforeSpawning() async {
    let before = AgentPillsManager.shared.pills.count
    let toolCall = ToolCall(
      name: "spawn_agent",
      arguments: ["title": "New Search"],
      thoughtSignature: nil)

    let result = await ChatToolExecutor.execute(
      toolCall,
      originatingChatMode: .act,
      originatingClientScope: nil)

    XCTAssertTrue(result.contains("Missing objective"))
    XCTAssertEqual(AgentPillsManager.shared.pills.count, before)
  }

  func testChatSpawnAgentRoutesThroughCoordinatorSpawn() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent("Providers/ChatToolExecutor.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("DesktopCoordinatorService.shared.spawnAgent("))
    XCTAssertTrue(source.contains("refreshProjectedPillsFromKernel"))
    XCTAssertFalse(source.contains("AgentPillsManager.shared.spawnFromUserQuery("))
  }
}
