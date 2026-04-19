import XCTest

@testable import Omi_Computer

@MainActor
final class CaptureScreenToolTests: XCTestCase {

  // MARK: - Tool dispatch

  /// Verify "capture_screen" is handled by ChatToolExecutor and does NOT fall
  /// through to "Unknown tool: capture_screen".
  func testCaptureScreenToolIsHandled() async {
    let toolCall = ToolCall(name: "capture_screen", arguments: [:], thoughtSignature: nil)
    let result = await ChatToolExecutor.execute(toolCall)

    // Must be handled — never "Unknown tool"
    XCTAssertFalse(
      result.hasPrefix("Unknown tool"),
      "capture_screen should be dispatched, got: \(result)")
  }

  /// Verify the result is either a file path (permission granted) or a
  /// descriptive permission error (permission denied).
  func testCaptureScreenReturnsPathOrPermissionError() async {
    let toolCall = ToolCall(name: "capture_screen", arguments: [:], thoughtSignature: nil)
    let result = await ChatToolExecutor.execute(toolCall)

    if result.hasPrefix("Error:") {
      // Permission denied path — the error message should guide the user
      XCTAssertTrue(
        result.contains("Screen recording permission") || result.contains("Failed to capture"),
        "Expected helpful capture error, got: \(result)")
    } else {
      // Permission granted path — result should be a valid file path
      XCTAssertTrue(
        result.hasPrefix("/"),
        "Expected file path starting with /, got: \(result)")
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
