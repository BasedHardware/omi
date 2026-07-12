import XCTest

@testable import Omi_Computer

@MainActor
final class ChatToolExecutorSpawnAgentTests: XCTestCase {
  func testDirectPermissionToolsRemainCanonicalPhysicalExecutors() {
    XCTAssertEqual(
      GeneratedToolExecutors.chatDispatch(for: "check_permission_status"),
      .checkPermissionStatus)
    XCTAssertEqual(
      GeneratedToolExecutors.chatDispatch(for: "request_permission"),
      .requestPermission)
  }

  func testSpawnAgentHasNoDormantSwiftExecutionPath() async {
    let previousOwner = UserDefaults.standard.object(forKey: DefaultsKey.authUserId.rawValue)
    defer {
      if let previousOwner {
        UserDefaults.standard.set(previousOwner, forKey: DefaultsKey.authUserId.rawValue)
      } else {
        UserDefaults.standard.removeObject(forKey: DefaultsKey.authUserId.rawValue)
      }
    }
    UserDefaults.standard.set("spawn-test-owner", forKey: DefaultsKey.authUserId.rawValue)
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
