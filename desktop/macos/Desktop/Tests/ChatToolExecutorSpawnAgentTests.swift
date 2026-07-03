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

  func testChatSpawnAgentRejectsVagueBriefsBeforeSpawning() async {
    let before = AgentPillsManager.shared.pills.count
    let toolCall = ToolCall(
      name: "spawn_agent",
      arguments: ["brief": "Perform a new search for the user.", "title": "New Search"],
      thoughtSignature: nil)

    let result = await ChatToolExecutor.execute(
      toolCall,
      originatingChatMode: .act,
      originatingClientScope: nil)

    XCTAssertTrue(result.contains("Missing self-contained brief"))
    XCTAssertEqual(AgentPillsManager.shared.pills.count, before)
  }

  func testChatSpawnAgentRoutesThroughDelegationExecutor() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent("Providers/ChatToolExecutor.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("AgentDelegationExecutor.shared.spawnResolvedDelegation"))
    XCTAssertFalse(source.contains("AgentPillsManager.shared.spawnFromUserQuery("))
  }
}
