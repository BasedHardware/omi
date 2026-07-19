import XCTest

@testable import Omi_Computer

@MainActor
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

  func testDirectPermissionToolsRemainCanonicalPhysicalExecutors() {
    XCTAssertEqual(
      GeneratedToolExecutors.chatDispatch(for: "check_permission_status"),
      .checkPermissionStatus)
    XCTAssertEqual(
      GeneratedToolExecutors.chatDispatch(for: "request_permission"),
      .requestPermission)
  }

  func testSpawnAgentHasNoDormantSwiftExecutionPath() async {
    let before = AgentPillsManager.shared.pills.count
    let toolCall = ToolCall(
      name: "spawn_agent",
      arguments: ["objective": "Private owner A task", "title": "Agent"],
      thoughtSignature: nil)

    let result = await ChatToolExecutor.execute(
      toolCall,
      originatingChatMode: .act,
      expectedOwnerID: "spawn-test-owner")

    XCTAssertEqual(result, "Unknown tool: spawn_agent")
    XCTAssertEqual(AgentPillsManager.shared.pills.count, before)
  }
}
