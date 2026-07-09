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
