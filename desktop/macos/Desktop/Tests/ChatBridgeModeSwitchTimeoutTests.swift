import XCTest

@testable import Omi_Computer

final class ChatBridgeModeSwitchTimeoutTests: XCTestCase {
  func testModeSwitchWaitIsBoundedAndClearsWaiters() throws {
    let source = try sourceFile("Providers/ChatProvider.swift")
    XCTAssertTrue(source.contains("modeSwitchWaitTimeoutSeconds"))
    XCTAssertTrue(source.contains("waitForModeSwitchCompletion"))
    XCTAssertTrue(source.contains("recordChatBridgeModeSwitchTimeout"))
    XCTAssertTrue(source.contains("finishModeSwitchWaiters"))
    XCTAssertTrue(source.contains("defer {"))
    // Timeout must fail soft without releasing the switcher's serialization lock.
    XCTAssertTrue(source.contains("Do NOT clear modeSwitchInProgress"))
    XCTAssertTrue(source.contains("recovery_action=fail_soft"))
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
