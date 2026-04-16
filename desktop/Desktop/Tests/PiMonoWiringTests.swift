import XCTest

@testable import Omi_Computer

final class PiMonoWiringTests: XCTestCase {

  // MARK: - ACPBridge construction defaults

  func testACPBridgeDefaultHarnessIsAcp() async {
    let bridge = ACPBridge()
    let mode = await bridge.harnessMode
    let key = await bridge.passApiKey
    XCTAssertEqual(mode, "acp")
    XCTAssertFalse(key)
  }

  func testACPBridgePiMonoHarness() async {
    let bridge = ACPBridge(passApiKey: true, harnessMode: "piMono")
    let mode = await bridge.harnessMode
    let key = await bridge.passApiKey
    XCTAssertEqual(mode, "piMono")
    XCTAssertTrue(key)
  }

  // MARK: - TaskChatState mode-mapping logic
  // Mirrors the branching in TaskChatState.ensureBridge():
  //   let mode = UserDefaults.standard.string(forKey: "chatBridgeMode") ?? "piMono"
  //   let useOmiKey = mode != "claudeCode"
  //   let harness = mode == "piMono" ? "piMono" : "acp"

  func testTaskChatModeMappingDefaultNil() {
    // When chatBridgeMode is not set, defaults to "piMono"
    let mode: String? = nil
    let resolved = mode ?? "piMono"
    let useOmiKey = resolved != "claudeCode"
    let harness = resolved == "piMono" ? "piMono" : "acp"

    XCTAssertEqual(harness, "piMono")
    XCTAssertTrue(useOmiKey)
  }

  func testTaskChatModeMappingPiMono() {
    let mode = "piMono"
    let useOmiKey = mode != "claudeCode"
    let harness = mode == "piMono" ? "piMono" : "acp"

    XCTAssertEqual(harness, "piMono")
    XCTAssertTrue(useOmiKey)
  }

  func testTaskChatModeMappingClaudeCode() {
    let mode = "claudeCode"
    let useOmiKey = mode != "claudeCode"
    let harness = mode == "piMono" ? "piMono" : "acp"

    XCTAssertEqual(harness, "acp")
    XCTAssertFalse(useOmiKey)
  }

  func testTaskChatModeMappingAgentSDK() {
    // Legacy "agentSDK" mode should use acp harness with Omi key
    let mode = "agentSDK"
    let useOmiKey = mode != "claudeCode"
    let harness = mode == "piMono" ? "piMono" : "acp"

    XCTAssertEqual(harness, "acp")
    XCTAssertTrue(useOmiKey)
  }

  // MARK: - Source-level piMono wiring assertion
  // Ensures no ACPBridge(passApiKey: true) without harnessMode exists in production code.

  func testNoBareACPBridgePassApiKeyInSources() throws {
    let sourcesDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests/
      .deletingLastPathComponent()  // Desktop/
      .appendingPathComponent("Sources")

    guard FileManager.default.fileExists(atPath: sourcesDir.path) else {
      throw XCTSkip("Sources directory not found at \(sourcesDir.path)")
    }

    let enumerator = FileManager.default.enumerator(
      at: sourcesDir,
      includingPropertiesForKeys: nil,
      options: [.skipsHiddenFiles]
    )!

    var violations: [String] = []
    // Pattern: ACPBridge(passApiKey: that does NOT contain harnessMode on the same line
    while let url = enumerator.nextObject() as? URL {
      guard url.pathExtension == "swift" else { continue }
      let content = try String(contentsOf: url, encoding: .utf8)
      for (i, line) in content.components(separatedBy: .newlines).enumerated() {
        if line.contains("ACPBridge(passApiKey:") && !line.contains("harnessMode") {
          let relativePath = url.lastPathComponent
          violations.append("\(relativePath):\(i + 1): \(line.trimmingCharacters(in: .whitespaces))")
        }
      }
    }

    XCTAssertEqual(
      violations, [],
      "Found ACPBridge(passApiKey:) without harnessMode — all instances must specify piMono or derive from bridgeMode:\n"
        + violations.joined(separator: "\n"))
  }
}
