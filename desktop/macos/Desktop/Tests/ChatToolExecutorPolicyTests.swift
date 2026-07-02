import XCTest

@testable import Omi_Computer

final class ChatToolExecutorPolicyTests: XCTestCase {
  func testTaskMutationPolicyDeniesAgentTaskChangesByDefault() {
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

      guard case .deny(let message) = decision else {
        return XCTFail("\(toolName) should require approval")
      }
      XCTAssertTrue(message.hasPrefix("POLICY_DENIED:"), "\(toolName) returned: \(message)")
      XCTAssertTrue(message.contains("\"capability\":\"desktop.tasks.readwrite\""), "\(toolName) returned: \(message)")
      XCTAssertTrue(message.contains("Task changes from an agent require explicit approval"), "\(toolName) returned: \(message)")
      XCTAssertFalse(message.contains("backend-task-123"), "\(toolName) leaked raw task id")
      XCTAssertFalse(message.contains("Change a task"), "\(toolName) leaked raw task description")
    }
  }

  @MainActor
  func testTaskDeleteAndCompleteExecuteFailClosedBeforeMutation() async {
    for toolName in ["complete_task", "delete_task"] {
      let result = await ChatToolExecutor.execute(
        ToolCall(
          name: toolName,
          arguments: ["task_id": "backend-task-123"],
          thoughtSignature: nil))

      XCTAssertTrue(result.hasPrefix("POLICY_DENIED:"), "\(toolName) returned: \(result)")
      XCTAssertTrue(result.contains("\"capability\":\"desktop.tasks.readwrite\""), "\(toolName) returned: \(result)")
      XCTAssertFalse(result.contains("task not found"), "\(toolName) should not reach task storage")
      XCTAssertFalse(result.contains("backend-task-123"), "\(toolName) leaked raw task id")
    }
  }

  @MainActor
  func testBackendTaskCreateAndUpdateFailClosedBeforeNetwork() async {
    let calls = [
      ToolCall(
        name: "create_action_item",
        arguments: ["description": "Create this task"],
        thoughtSignature: nil),
      ToolCall(
        name: "update_action_item",
        arguments: ["action_item_id": "backend-task-123", "completed": true],
        thoughtSignature: nil),
    ]

    for call in calls {
      let result = await ChatToolExecutor.execute(call)
      XCTAssertTrue(result.hasPrefix("POLICY_DENIED:"), "\(call.name) returned: \(result)")
      XCTAssertTrue(result.contains("\"capability\":\"desktop.tasks.readwrite\""), "\(call.name) returned: \(result)")
      XCTAssertFalse(result.contains("description is required"), "\(call.name) should not reach backend validation")
      XCTAssertFalse(result.contains("action_item_id is required"), "\(call.name) should not reach backend validation")
      XCTAssertFalse(result.contains("backend-task-123"), "\(call.name) leaked raw task id")
      XCTAssertFalse(result.contains("Create this task"), "\(call.name) leaked raw task description")
    }
  }
}
