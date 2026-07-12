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
      ("execute_sql", ["query": "UPDATE action_items SET completed = 1 WHERE id = 42"], "desktop.context.local_write")
    ] {
      let decision = ChatToolExecutor.localPolicyDecision(toolName: toolName, arguments: arguments)
      guard case .deny(let message) = decision else {
        return XCTFail("\(toolName) should still require approval")
      }
      XCTAssertTrue(message.hasPrefix("POLICY_DENIED:"), "\(toolName) returned: \(message)")
      XCTAssertTrue(message.contains("\"capability\":\"\(capability)\""), "\(toolName) returned: \(message)")
    }
  }

  @MainActor
  func testPermissionRequestNeedsCurrentTurnAuthorizationOutsideOnboarding() async {
    let savedOnboardingAppState = ChatToolExecutor.onboardingAppState
    defer { ChatToolExecutor.onboardingAppState = savedOnboardingAppState }
    ChatToolExecutor.onboardingAppState = AppState()
    let result = await ChatToolExecutor.execute(
      ToolCall(name: "request_permission", arguments: ["type": "screen_recording"], thoughtSignature: nil),
      isOnboardingSurface: false)

    XCTAssertTrue(result.hasPrefix("POLICY_DENIED:"), "request_permission returned: \(result)")
    XCTAssertTrue(result.contains("\"code\":\"explicit_user_permission_required\""), "request_permission returned: \(result)")
    XCTAssertTrue(result.contains("\"capability\":\"desktop.permissions.request\""), "request_permission returned: \(result)")
  }

  // MARK: - Chat screenshot sharing (regression: chat screen vision was hard-denied
  // with no approval path from 2026-06-29 until the Screen Sharing in Chat setting)

  private let screenshotKey = DefaultsKey.chatScreenshotSharingEnabled.rawValue

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: screenshotKey)
    super.tearDown()
  }

  func testScreenshotToolsAllowedByDefault() {
    UserDefaults.standard.removeObject(forKey: screenshotKey)
    for toolName in ["capture_screen", "get_screenshot"] {
      XCTAssertEqual(
        ChatToolExecutor.localPolicyDecision(toolName: toolName, arguments: [:]), .allow,
        "\(toolName) must be allowed when the setting is unset (default on)")
    }
  }

  func testScreenshotToolsAllowedWhenSettingEnabled() {
    UserDefaults.standard.set(true, forKey: screenshotKey)
    XCTAssertEqual(
      ChatToolExecutor.localPolicyDecision(toolName: "capture_screen", arguments: [:]), .allow)
  }

  func testScreenshotToolsDeniedWhenSettingDisabled() {
    UserDefaults.standard.set(false, forKey: screenshotKey)
    for toolName in ["capture_screen", "get_screenshot"] {
      guard
        case .deny(let message) = ChatToolExecutor.localPolicyDecision(
          toolName: toolName, arguments: [:])
      else {
        return XCTFail("\(toolName) should be denied when Screen Sharing in Chat is off")
      }
      XCTAssertTrue(message.hasPrefix("POLICY_DENIED:"), "\(toolName) returned: \(message)")
      XCTAssertTrue(
        message.contains("\"capability\":\"desktop.context.screenshot_image\""),
        "\(toolName) returned: \(message)")
      XCTAssertTrue(
        message.contains("Screen Sharing in Chat"),
        "deny message should point the user at the setting; returned: \(message)")
    }
  }
}
