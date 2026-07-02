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

  func testFloatingPillCannotStartProviderInstall() async {
    let before = AgentPillsManager.shared.pills.count
    let toolCall = ToolCall(
      name: "setup_agent_provider",
      arguments: ["provider": "codex"],
      thoughtSignature: nil)

    let result = await ChatToolExecutor.execute(
      toolCall,
      originatingClientScope: "floating-pill")

    XCTAssertTrue(result.contains("unavailable from an existing floating background agent"))
    XCTAssertEqual(AgentPillsManager.shared.pills.count, before)
  }

  func testAskModeCannotStartProviderInstall() async {
    let before = AgentPillsManager.shared.pills.count
    let toolCall = ToolCall(
      name: "setup_agent_provider",
      arguments: ["provider": "codex"],
      thoughtSignature: nil)

    let result = await ChatToolExecutor.execute(
      toolCall,
      originatingChatMode: .ask)

    XCTAssertTrue(result.contains("unavailable in Ask mode"))
    XCTAssertEqual(AgentPillsManager.shared.pills.count, before)
  }

  func testSetupAgentProviderRejectsUnsupportedProvider() async {
    let before = AgentPillsManager.shared.pills.count
    let toolCall = ToolCall(
      name: "setup_agent_provider",
      arguments: ["provider": "skynet"],
      thoughtSignature: nil)

    let result = await ChatToolExecutor.execute(toolCall, originatingChatMode: .act)

    XCTAssertTrue(result.contains("Unsupported provider 'skynet'"))
    XCTAssertEqual(AgentPillsManager.shared.pills.count, before)
  }
}
