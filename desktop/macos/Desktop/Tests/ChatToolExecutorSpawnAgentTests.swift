import XCTest

@testable import Omi_Computer

final class ChatToolExecutorSpawnAgentTests: XCTestCase {
  private var ownerFixture: RuntimeOwnerAuthorityTestFixture!

  override func setUp() async throws {
    ownerFixture = RuntimeOwnerAuthorityTestFixture()
    await ownerFixture.establish(authOwnerID: "spawn-test-owner")
  }

  override func tearDown() async throws {
    await ownerFixture.restore()
    ownerFixture = nil
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
    // omi-test-quality: source-inspection -- static contract: provider setup must stay on the native installer path and never regain an agent-pill spawn path.
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  func testChatSpawnAgentRequiresObjectiveBeforeSpawning() async {
    let before = AgentPillsManager.shared.pills.count
    let toolCall = ToolCall(
      name: "spawn_agent",
      arguments: ["title": "Agent"],
      thoughtSignature: nil)

    let result = await ChatToolExecutor.execute(
      toolCall,
      originatingChatMode: .act,
      expectedOwnerID: "spawn-test-owner")

    XCTAssertEqual(result, "Error: Missing objective. Pass a clear, self-contained task objective.")
    XCTAssertEqual(AgentPillsManager.shared.pills.count, before)
  }

  func testDirectPermissionToolsRemainCanonicalPhysicalExecutors() {
    XCTAssertEqual(
      GeneratedToolExecutors.chatDispatch(for: "check_permission_status"),
      .checkPermissionStatus)
    XCTAssertEqual(
      GeneratedToolExecutors.chatDispatch(for: "request_permission"),
      .requestPermission)
  }

  func testSpawnAgentHasNoDormantSwiftExecutionPath() {
    XCTAssertNil(GeneratedToolExecutors.resolve("spawn_agent"))
    XCTAssertEqual(GeneratedToolExecutors.chatDispatch(for: "spawn_agent"), .unhandled)
  }

  func testSpawnAgentResponseReportsTheCurrentPillStatus() {
    let pill = AgentPill(query: "Review the launch status", model: "test")

    for status in [AgentPill.Status.queued, .starting, .running, .done, .stopped] {
      pill.status = status
      XCTAssertTrue(ChatToolExecutor.spawnAgentResponse(for: pill).contains("status: \(status.machineLabel)"))
    }

    pill.status = .failed("Provider exited")
    XCTAssertTrue(ChatToolExecutor.spawnAgentResponse(for: pill).contains("FAILED to start: Provider exited"))
  }
}
