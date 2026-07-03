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

    // Shared wording with spawn_agent (DirectedProvider.unsupportedProviderMessage).
    XCTAssertTrue(result.contains("Unsupported agent provider 'skynet'"))
    XCTAssertEqual(AgentPillsManager.shared.pills.count, before)
  }

  func testSetupAgentProviderNeverSpawnsAnAgentPill() throws {
    // The typed-chat executor delegates to the deterministic
    // LocalAgentProviderInstaller (native confirm dialog + Process); it must
    // never route the install through an agent pill again.
    let source = try chatToolExecutorSource()

    XCTAssertTrue(source.contains("LocalAgentProviderInstaller.shared.beginInstall(for: provider)"))
    XCTAssertFalse(source.contains("spawnInstallAssistPill"))
  }

  private func chatToolExecutorSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Providers/ChatToolExecutor.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
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
