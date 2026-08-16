import XCTest

@testable import Omi_Computer

@MainActor
final class CaptureScreenToolTests: XCTestCase {

  private let screenshotKey = DefaultsKey.chatScreenshotSharingEnabled.rawValue
  private var ownerFixture: RuntimeOwnerAuthorityTestFixture!

  override func setUp() async throws {
    ownerFixture = RuntimeOwnerAuthorityTestFixture()
    await ownerFixture.establish(authOwnerID: "capture-screen-test-owner")
  }

  override func tearDown() async throws {
    UserDefaults.standard.removeObject(forKey: screenshotKey)
    await ownerFixture.restore()
    ownerFixture = nil
  }

  // MARK: - Tool dispatch

  /// Verify "capture_screen" is handled by ChatToolExecutor and does NOT fall
  /// through to "Unknown tool: capture_screen". With Screen Sharing in Chat off,
  /// it must fail its physical execution precondition.
  func testCaptureScreenToolIsDeniedWhenSharingDisabled() async {
    UserDefaults.standard.set(false, forKey: screenshotKey)
    let toolCall = ToolCall(name: "capture_screen", arguments: [:], thoughtSignature: nil)
    let result = await ChatToolExecutor.execute(toolCall)

    XCTAssertFalse(
      result.hasPrefix("Unknown tool"),
      "capture_screen should be dispatched, got: \(result)")
    XCTAssertTrue(
      result.hasPrefix("EXECUTION_PRECONDITION_FAILED:"),
      "capture_screen should fail closed, got: \(result)")
    XCTAssertTrue(result.contains("\"code\":\"execution_precondition_failed\""))
    XCTAssertTrue(result.contains("\"reason\":\"screenshot_sharing_disabled\""))
    XCTAssertFalse(result.contains("capability"))
    XCTAssertTrue(result.contains("Screen Sharing in Chat"))
  }

  func testScreenshotImagePreconditionDoesNotLeakArgumentsWhenSharingDisabled() {
    UserDefaults.standard.set(false, forKey: screenshotKey)
    for toolName in ["capture_screen", "get_screenshot"] {
      let decision = ChatToolExecutor.physicalExecutionPrecondition(toolName: toolName)

      guard case .failed(let message) = decision else {
        return XCTFail("\(toolName) should fail its physical precondition")
      }
      XCTAssertTrue(message.hasPrefix("EXECUTION_PRECONDITION_FAILED:"))
      XCTAssertTrue(message.contains("\"reason\":\"screenshot_sharing_disabled\""))
      XCTAssertFalse(message.contains("123"))
    }
  }

  /// Regression: chat screen vision was hard-denied with no approval path from
  /// 2026-06-29 (a4160e40cf) until the Screen Sharing in Chat setting. Default
  /// (setting unset) must allow the tools to dispatch.
  func testScreenshotImagePreconditionAllowsByDefault() {
    UserDefaults.standard.removeObject(forKey: screenshotKey)
    for toolName in ["capture_screen", "get_screenshot"] {
      XCTAssertEqual(
        ChatToolExecutor.physicalExecutionPrecondition(toolName: toolName), .satisfied,
        "\(toolName) must dispatch when Screen Sharing in Chat is on (default)")
    }
  }

  // MARK: - Source-level invariant

  /// Guard: the switch in execute() must contain a "capture_screen" case.
  /// Prevents accidental removal during refactoring.
  func testCaptureScreenCaseExistsInSource() throws {
    let sourcesDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests/
      .deletingLastPathComponent()  // Desktop/
      .appendingPathComponent("Sources")
      .appendingPathComponent("Providers")
      .appendingPathComponent("ChatToolExecutor.swift")

    let content = try String(contentsOf: sourcesDir, encoding: .utf8)
    XCTAssertTrue(
      content.contains("case \"capture_screen\""),
      "ChatToolExecutor.swift must contain case \"capture_screen\"")
  }
}
