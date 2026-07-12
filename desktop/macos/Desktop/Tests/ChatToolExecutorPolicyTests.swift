import XCTest

@testable import Omi_Computer

final class ChatToolExecutorPolicyTests: XCTestCase {
  private var previousAuthOwner: Any?
  private var previousAutomationOwner: Any?

  override func setUp() {
    super.setUp()
    previousAuthOwner = UserDefaults.standard.object(forKey: .authUserId)
    previousAutomationOwner = UserDefaults.standard.object(forKey: .automationOwnerOverride)
    UserDefaults.standard.set("chat-tool-policy-owner", forKey: .authUserId)
    UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
  }

  @MainActor
  func testTaskDeleteAndCompleteReachTaskStorage() async {
    for toolName in ["complete_task", "delete_task"] {
      let result = await ChatToolExecutor.execute(
        ToolCall(
          name: toolName,
          arguments: ["task_id": "backend-task-123"],
          thoughtSignature: nil))

      XCTAssertFalse(
        result.hasPrefix("EXECUTION_PRECONDITION_FAILED:"),
        "\(toolName) returned: \(result)")
      XCTAssertTrue(result.contains("task not found") || result.hasPrefix("Error:"), "\(toolName) returned: \(result)")
    }
  }

  func testSQLAuthorizationIsNotOwnedBySwiftPhysicalPreconditions() {
    XCTAssertEqual(
      ChatToolExecutor.physicalExecutionPrecondition(toolName: "execute_sql"),
      .satisfied)
  }

  // MARK: - Chat screenshot sharing (regression: chat screen vision was hard-denied
  // with no approval path from 2026-06-29 until the Screen Sharing in Chat setting)

  private let screenshotKey = DefaultsKey.chatScreenshotSharingEnabled.rawValue

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: screenshotKey)
    if let previousAuthOwner {
      UserDefaults.standard.set(previousAuthOwner, forKey: .authUserId)
    } else {
      UserDefaults.standard.removeObject(forKey: .authUserId)
    }
    if let previousAutomationOwner {
      UserDefaults.standard.set(previousAutomationOwner, forKey: .automationOwnerOverride)
    } else {
      UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
    }
    super.tearDown()
  }

  func testScreenshotToolsAllowedByDefault() {
    UserDefaults.standard.removeObject(forKey: screenshotKey)
    for toolName in ["capture_screen", "get_screenshot"] {
      XCTAssertEqual(
        ChatToolExecutor.physicalExecutionPrecondition(toolName: toolName), .satisfied,
        "\(toolName) must be allowed when the setting is unset (default on)")
    }
  }

  func testScreenshotToolsAllowedWhenSettingEnabled() {
    UserDefaults.standard.set(true, forKey: screenshotKey)
    XCTAssertEqual(
      ChatToolExecutor.physicalExecutionPrecondition(toolName: "capture_screen"),
      .satisfied)
  }

  func testScreenshotToolsDeniedWhenSettingDisabled() {
    UserDefaults.standard.set(false, forKey: screenshotKey)
    for toolName in ["capture_screen", "get_screenshot"] {
      guard
        case .failed(let message) = ChatToolExecutor.physicalExecutionPrecondition(
          toolName: toolName)
      else {
        return XCTFail("\(toolName) should be denied when Screen Sharing in Chat is off")
      }
      XCTAssertTrue(
        message.hasPrefix("EXECUTION_PRECONDITION_FAILED:"),
        "\(toolName) returned: \(message)")
      XCTAssertTrue(
        message.contains("\"code\":\"execution_precondition_failed\""),
        "\(toolName) returned: \(message)")
      XCTAssertTrue(
        message.contains("\"reason\":\"screenshot_sharing_disabled\""),
        "\(toolName) returned: \(message)")
      XCTAssertFalse(message.contains("capability"), "\(toolName) returned: \(message)")
      XCTAssertTrue(
        message.contains("Screen Sharing in Chat"),
        "deny message should point the user at the setting; returned: \(message)")
    }
  }
}
