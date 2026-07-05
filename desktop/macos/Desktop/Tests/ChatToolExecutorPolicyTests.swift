import XCTest

@testable import Omi_Computer

final class ChatToolExecutorPolicyTests: XCTestCase {
  func testStructuredTaskMutationToolsReachTheirExecutors() {
    let taskMutationTools = [
      "complete_task",
      "delete_task",
      "create_action_item",
      "update_action_item",
    ]

    for toolName in taskMutationTools {
      let decision = ChatToolExecutor.localPolicyDecision(
        toolName: toolName,
        arguments: [
          "task_id": "backend-task-123",
          "action_item_id": "backend-task-123",
          "description": "Change a task",
        ])

      XCTAssertEqual(decision, .allow, "\(toolName) should not be blocked before its structured executor runs")
    }
  }

  @MainActor
  func testTaskDeleteAndCompleteReachTaskStorage() async {
    for toolName in ["complete_task", "delete_task"] {
      let result = await ChatToolExecutor.execute(
        ToolCall(
          name: toolName,
          arguments: ["task_id": "backend-task-123"],
          thoughtSignature: nil))

      XCTAssertFalse(result.hasPrefix("POLICY_DENIED:"), "\(toolName) returned: \(result)")
      XCTAssertTrue(result.contains("task not found") || result.hasPrefix("Error:"), "\(toolName) returned: \(result)")
    }
  }

  func testRawSensitiveSurfacesStillRequireApproval() {
    for (toolName, arguments, capability) in [
      ("execute_sql", ["query": "UPDATE action_items SET completed = 1 WHERE id = 42"], "desktop.context.local_write"),
      ("capture_screen", [:], "desktop.context.screenshot_image"),
    ] {
      let decision = ChatToolExecutor.localPolicyDecision(toolName: toolName, arguments: arguments)
      guard case .deny(let message) = decision else {
        return XCTFail("\(toolName) should still require approval")
      }
      XCTAssertTrue(message.hasPrefix("POLICY_DENIED:"), "\(toolName) returned: \(message)")
      XCTAssertTrue(message.contains("\"capability\":\"\(capability)\""), "\(toolName) returned: \(message)")
    }
  }
}
