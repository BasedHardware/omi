import XCTest

@testable import Omi_Computer

@MainActor
final class CaptureScreenToolTests: XCTestCase {

  // MARK: - Tool dispatch

  /// Verify "capture_screen" is handled by ChatToolExecutor and does NOT fall
  /// through to "Unknown tool: capture_screen".
  func testCaptureScreenToolIsDeniedByDefaultPolicy() async {
    let toolCall = ToolCall(name: "capture_screen", arguments: [:], thoughtSignature: nil)
    let result = await ChatToolExecutor.execute(toolCall)

    XCTAssertFalse(
      result.hasPrefix("Unknown tool"),
      "capture_screen should be dispatched, got: \(result)")
    XCTAssertTrue(result.hasPrefix("POLICY_DENIED:"), "capture_screen should fail closed, got: \(result)")
    XCTAssertTrue(result.contains("\"capability\":\"desktop.context.screenshot_image\""))
    XCTAssertTrue(result.contains("Screenshot image access requires explicit approval"))
  }

  func testScreenshotImagePolicyDeniesLocalImageBytesByDefault() {
    for toolName in ["capture_screen", "get_screenshot"] {
      let decision = ChatToolExecutor.localPolicyDecision(
        toolName: toolName,
        arguments: ["screenshot_id": "123"])

      guard case .deny(let message) = decision else {
        return XCTFail("\(toolName) should require approval")
      }
      XCTAssertTrue(message.hasPrefix("POLICY_DENIED:"))
      XCTAssertTrue(message.contains("\"capability\":\"desktop.context.screenshot_image\""))
      XCTAssertTrue(message.contains("Screenshot image access requires explicit approval"))
      XCTAssertFalse(message.contains("123"))
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
