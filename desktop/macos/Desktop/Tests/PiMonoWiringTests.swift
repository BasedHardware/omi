import XCTest

@testable import Omi_Computer

final class PiMonoWiringTests: XCTestCase {

  // MARK: - TaskChatState mode-mapping logic
  // Mirrors the branching in TaskChatState.ensureBridge():
  //   let mode = UserDefaults.standard.string(forKey: "chatBridgeMode") ?? "piMono"
  //   let harness = mode == "piMono" ? "piMono" : "acp"

  func testTaskChatModeMappingDefaultNil() {
    // When chatBridgeMode is not set, defaults to "piMono"
    let mode: String? = nil
    let resolved = mode ?? "piMono"
    let harness = resolved == "piMono" ? "piMono" : "acp"

    XCTAssertEqual(harness, "piMono")
  }

  func testTaskChatModeMappingPiMono() {
    let mode = "piMono"
    let harness = mode == "piMono" ? "piMono" : "acp"

    XCTAssertEqual(harness, "piMono")
  }

  func testTaskChatModeMappingClaudeCode() {
    let mode = "claudeCode"
    let harness = mode == "piMono" ? "piMono" : "acp"

    XCTAssertEqual(harness, "acp")
  }

  func testTaskChatModeMappingAgentSDK() {
    // Legacy "agentSDK" mode should fall through to acp harness
    let mode = "agentSDK"
    let harness = mode == "piMono" ? "piMono" : "acp"

    XCTAssertEqual(harness, "acp")
  }

  // MARK: - ApiKeysResponse shape assertion
  // After #6594, the response must NOT contain anthropic_api_key.

  func testApiKeysResponseDecodesWithoutAnthropicKey() throws {
    let json = """
    {
      "firebase_api_key": "AIza-test",
      "google_calendar_api_key": "cal-key"
    }
    """.data(using: .utf8)!
    let response = try JSONDecoder().decode(APIClient.ApiKeysResponse.self, from: json)
    XCTAssertEqual(response.firebaseApiKey, "AIza-test")
    XCTAssertEqual(response.googleCalendarApiKey, "cal-key")
  }

  func testApiKeysResponseIgnoresUnknownAnthropicField() throws {
    // If the backend ever sends anthropic_api_key, the client must ignore it
    let json = """
    {
      "firebase_api_key": "AIza-test",
      "anthropic_api_key": "sk-ant-LEAKED",
      "google_calendar_api_key": "cal-key"
    }
    """.data(using: .utf8)!
    let response = try JSONDecoder().decode(APIClient.ApiKeysResponse.self, from: json)
    XCTAssertEqual(response.firebaseApiKey, "AIza-test")
    // Verify no property named anthropicApiKey exists on the response
    let mirror = Mirror(reflecting: response)
    let propertyNames = mirror.children.map { $0.label ?? "" }
    XCTAssertFalse(propertyNames.contains("anthropicApiKey"),
      "ApiKeysResponse must not have anthropicApiKey property (removed in #6594)")
  }

  // MARK: - Source-level wiring assertions
  // Ensures no AgentBridge(passApiKey:) exists in production code (parameter removed in #6594).

  func testNoAgentBridgePassApiKeyInSources() throws {
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
    while let url = enumerator.nextObject() as? URL {
      guard url.pathExtension == "swift" else { continue }
      let content = try String(contentsOf: url, encoding: .utf8)
      for (i, line) in content.components(separatedBy: .newlines).enumerated() {
        if line.contains("AgentBridge(passApiKey:") {
          let relativePath = url.lastPathComponent
          violations.append("\(relativePath):\(i + 1): \(line.trimmingCharacters(in: .whitespaces))")
        }
      }
    }

    XCTAssertEqual(
      violations, [],
      "Found AgentBridge(passApiKey:) — passApiKey parameter was removed in #6594. Use AgentBridge(harnessMode:) instead:\n"
        + violations.joined(separator: "\n"))
  }

  func testNoAnthropicApiKeyInClientCode() throws {
    let sourcesDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests/
      .deletingLastPathComponent()  // Desktop/
      .appendingPathComponent("Sources")

    guard FileManager.default.fileExists(atPath: sourcesDir.path) else {
      throw XCTSkip("Sources directory not found at \(sourcesDir.path)")
    }

    let targetFiles = ["APIClient.swift", "APIKeyService.swift"]
    let pattern = "anthropicApiKey"

    var violations: [String] = []
    for fileName in targetFiles {
      let enumerator = FileManager.default.enumerator(
        at: sourcesDir,
        includingPropertiesForKeys: nil,
        options: [.skipsHiddenFiles]
      )!
      while let url = enumerator.nextObject() as? URL {
        guard url.lastPathComponent == fileName else { continue }
        let content = try String(contentsOf: url, encoding: .utf8)
        for (i, line) in content.components(separatedBy: .newlines).enumerated() {
          if line.contains(pattern) {
            violations.append("\(fileName):\(i + 1): \(line.trimmingCharacters(in: .whitespaces))")
          }
        }
      }
    }

    XCTAssertEqual(
      violations, [],
      "Found anthropicApiKey in client code — removed in #6594:\n"
        + violations.joined(separator: "\n"))
  }

  // MARK: - AIProvider struct tests

  func testAIProviderPiMonoHasCorrectValues() {
    let p = AIProvider.piMono
    XCTAssertEqual(p.id, "piMono")
    XCTAssertEqual(p.displayName, "Omi AI")
    XCTAssertEqual(p.bridgeModeRawValue, "piMono")
    XCTAssertNil(p.attributionURL)
    XCTAssertEqual(p.sfSymbol, "")
    XCTAssertFalse(p.tagline.isEmpty)
  }

  func testAIProviderClaudeHasCorrectValues() {
    let p = AIProvider.claude
    XCTAssertEqual(p.id, "claude")
    XCTAssertEqual(p.displayName, "Claude")
    XCTAssertEqual(p.bridgeModeRawValue, "claudeCode")
    XCTAssertEqual(p.attributionURL?.host, "claude.ai")
    XCTAssertEqual(p.sfSymbol, "")
    XCTAssertFalse(p.tagline.isEmpty)
  }

  func testAIProviderAllContainsBothProviders() {
    XCTAssertEqual(AIProvider.all.count, 2)
    XCTAssertEqual(AIProvider.all.map(\.id), ["piMono", "claude"])
  }

  func testAIProviderFromBridgeModeReturnsCorrectProvider() {
    XCTAssertEqual(AIProvider.from(bridgeMode: "piMono")?.id, "piMono")
    XCTAssertEqual(AIProvider.from(bridgeMode: "claudeCode")?.id, "claude")
    XCTAssertNil(AIProvider.from(bridgeMode: "unknown"))
    XCTAssertNil(AIProvider.from(bridgeMode: "agentSDK"))
  }

  // MARK: - Rename completeness: no ACPBridge / acp-bridge in Swift sources

  func testNoACPBridgeReferencesInSources() throws {
    let sourcesDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests/
      .deletingLastPathComponent()  // Desktop/
      .appendingPathComponent("Sources")

    guard FileManager.default.fileExists(atPath: sourcesDir.path) else {
      throw XCTSkip("Sources directory not found at \(sourcesDir.path)")
    }

    let patterns = ["ACPBridge", "acp-bridge", "acpBridge"]
    var violations: [String] = []

    let enumerator = FileManager.default.enumerator(
      at: sourcesDir,
      includingPropertiesForKeys: nil,
      options: [.skipsHiddenFiles]
    )!
    while let url = enumerator.nextObject() as? URL {
      guard url.pathExtension == "swift" else { continue }
      let content = try String(contentsOf: url, encoding: .utf8)
      for (i, line) in content.components(separatedBy: .newlines).enumerated() {
        for pattern in patterns {
          if line.contains(pattern) {
            violations.append("\(url.lastPathComponent):\(i + 1): \(line.trimmingCharacters(in: .whitespaces))")
          }
        }
      }
    }

    XCTAssertEqual(
      violations, [],
      "Found stale ACPBridge/acp-bridge references — renamed to AgentBridge/agent in #6594:\n"
        + violations.joined(separator: "\n"))
  }

  // MARK: - Legacy key backend wiring (source-level)

  func testRustConfigServesLegacyAnthropicKey() throws {
    let configRoutesPath = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests/
      .deletingLastPathComponent()  // Desktop/
      .deletingLastPathComponent()  // desktop/
      .appendingPathComponent("Backend-Rust/src/routes/config.rs")

    guard FileManager.default.fileExists(atPath: configRoutesPath.path) else {
      throw XCTSkip("config.rs not found at \(configRoutesPath.path)")
    }

    let src = try String(contentsOf: configRoutesPath, encoding: .utf8)

    // The response struct must have anthropic_api_key field
    XCTAssert(src.contains("anthropic_api_key: Option<String>"),
      "ApiKeysResponse must contain anthropic_api_key for old client compat")

    // It must be sourced from desktop_legacy_anthropic_key, NOT anthropic_api_key
    XCTAssert(src.contains("desktop_legacy_anthropic_key.clone()"),
      "anthropic_api_key must be sourced from desktop_legacy_anthropic_key, not anthropic_api_key")
  }
}
