import XCTest

@testable import Omi_Computer

final class PiMonoWiringTests: XCTestCase {

  // MARK: - TaskChatState mode-mapping logic
  // Mirrors the shared mapping used by ChatProvider and TaskChatState.

  func testTaskChatModeMappingDefaultNil() {
    // When chatBridgeMode is not set, defaults to "piMono"
    let mode: String? = nil
    let resolved = ChatProvider.BridgeMode(rawValue: mode ?? "piMono") ?? .piMono
    let harness = ChatProvider.harnessMode(for: resolved)

    XCTAssertEqual(harness, "piMono")
  }

  func testTaskChatModeMappingPiMono() {
    XCTAssertEqual(ChatProvider.harnessMode(for: .piMono), "piMono")
  }

  func testTaskChatModeMappingClaudeCode() {
    XCTAssertEqual(ChatProvider.harnessMode(for: .userClaude), "acp")
  }

  func testTaskChatModeMappingHermes() {
    XCTAssertEqual(ChatProvider.harnessMode(for: .hermes), "hermes")
  }

  func testTaskChatModeMappingOpenClaw() {
    XCTAssertEqual(ChatProvider.harnessMode(for: .openClaw), "openclaw")
  }

  func testTaskChatModeMappingAgentSDK() {
    XCTAssertEqual(ChatProvider.harnessMode(for: .omiAI), "piMono")
  }

  func testHarnessToAdapterMappingFailsClosed() {
    XCTAssertEqual(AgentRuntimeRouting.adapterId(for: .piMono).rawValue, "pi-mono")
    XCTAssertEqual(AgentRuntimeRouting.adapterId(for: .acp).rawValue, "acp")
    XCTAssertEqual(AgentRuntimeRouting.adapterId(for: .hermes).rawValue, "hermes")
    XCTAssertEqual(AgentRuntimeRouting.adapterId(for: .openclaw).rawValue, "openclaw")
    XCTAssertNil(AgentRuntimeRouting.harnessMode(from: "unknown"))
  }

  func testLocalAgentProviderDetectorUsesExplicitCommand() {
    let availability = LocalAgentProviderDetector.availability(
      for: .hermes,
      environment: ["OMI_HERMES_ADAPTER_COMMAND": " /usr/local/bin/hermes acp "],
      homeDirectory: "/tmp/missing-home")

    XCTAssertTrue(availability.isAvailable)
    XCTAssertEqual(availability.status, .available(command: "/usr/local/bin/hermes acp"))
  }

  func testLocalAgentProviderDetectorFindsExecutableInActivationPath() throws {
    let home = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-provider-detector-\(UUID().uuidString)", isDirectory: true)
    let bin = home.appendingPathComponent(".local/bin", isDirectory: true)
    try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: home) }

    let executable = bin.appendingPathComponent("openclaw")
    try "#!/bin/sh\nexit 0\n".write(to: executable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable.path)

    let availability = LocalAgentProviderDetector.availability(
      for: .openclaw,
      environment: [:],
      homeDirectory: home.path)

    XCTAssertEqual(availability.status, .available(command: executable.path))
  }

  func testLocalAgentProviderDetectorHonorsInjectedPathEntries() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-provider-path-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let executable = root.appendingPathComponent("hermes")
    try "#!/bin/sh\nexit 0\n".write(to: executable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable.path)

    let availability = LocalAgentProviderDetector.availability(
      for: .hermes,
      environment: ["PATH": root.path],
      homeDirectory: "/tmp/missing-home")

    XCTAssertEqual(availability.status, .available(command: executable.path))
  }

  func testLocalAgentProviderDetectorMissingPromptIsUserFacing() {
    let availability = LocalAgentProviderDetector.availability(
      for: .openclaw,
      environment: ["PATH": "/tmp/definitely-missing-\(UUID().uuidString)"],
      homeDirectory: "/tmp/missing-home")

    XCTAssertFalse(availability.isAvailable)
    XCTAssertEqual(
      availability.setupPrompt,
      "I don't see OpenClaw installed. Make sure OpenClaw is installed first, then try again.")
    XCTAssertEqual(
      availability.toolError,
      "Error: I don't see OpenClaw installed. Make sure OpenClaw is installed first, then try again.")
  }

  // MARK: - ChatProvider.BridgeMode → (Node harness, pi provider) mapping
  // Mirrors the real mapping used by AgentRuntimeRouting.harnessMode(for:)
  // and AIProvider.currentProviderMode, via the actual APIs (not a
  // reimplementation) so this exercises the real logic.

  func testBridgeModeLocalSharesNodeHarnessButDifferentProvider() {
    // Local must run the same Node harness as piMono (the pi-mono subprocess);
    // they differ only in which pi provider AgentRuntimeProcess configures
    // that harness with (see AIProvider.currentProviderMode). This is
    // exactly what makes a piMono <-> local no-op guard bug possible if
    // identity is derived from the Node harness string instead of the raw
    // BridgeMode. See ChatProvider.switchBridgeMode's newHarness comparison.
    XCTAssertEqual(
      ChatProvider.harnessMode(for: .local),
      ChatProvider.harnessMode(for: .piMono)
    )
    XCTAssertNotEqual(ChatProvider.BridgeMode.local.rawValue, ChatProvider.BridgeMode.piMono.rawValue)
  }

  func testCurrentProviderModeReflectsSelectedBridgeMode() {
    let key = AIProvider.selectedProviderRawValueKey
    let previous = UserDefaults.standard.string(forKey: key)
    defer {
      if let previous {
        UserDefaults.standard.set(previous, forKey: key)
      } else {
        UserDefaults.standard.removeObject(forKey: key)
      }
    }

    UserDefaults.standard.set(ChatProvider.BridgeMode.piMono.rawValue, forKey: key)
    XCTAssertEqual(AIProvider.currentProviderMode, "omi")

    UserDefaults.standard.set(ChatProvider.BridgeMode.local.rawValue, forKey: key)
    XCTAssertEqual(AIProvider.currentProviderMode, "omi-local")
  }

  func testProviderModeForBridgeModeRawValueMatchesCurrentProviderMode() {
    // `providerMode(forBridgeModeRawValue:)` is the same mapping
    // `currentProviderMode` uses, but for a caller that already has a raw
    // value in hand (e.g. one it actually applied) instead of one that wants
    // a fresh UserDefaults read. ChatProvider.activeProviderMode depends on
    // both agreeing.
    XCTAssertEqual(
      AIProvider.providerMode(forBridgeModeRawValue: ChatProvider.BridgeMode.piMono.rawValue), "omi")
    XCTAssertEqual(
      AIProvider.providerMode(forBridgeModeRawValue: ChatProvider.BridgeMode.local.rawValue), "omi-local")
  }

  /// Regression: `switchBridgeMode` must actually apply a piMono <-> local
  /// switch even when the "chatBridgeMode" UserDefaults key already reflects
  /// the destination value before the call starts — exactly what happens in
  /// production when the Settings picker's own `@AppStorage("chatBridgeMode")`
  /// binding (a separate property from `ChatProvider.bridgeMode`, sharing the
  /// same key) writes the new value synchronously, before its `.onChange`
  /// handler's Task gets around to calling `switchBridgeMode` (see
  /// SettingsContentView+FloatingBarAndChat.swift). A guard that re-reads
  /// `bridgeMode` to detect "did this actually change" always sees the new
  /// value already in place in that ordering and silently no-ops — this is
  /// exactly why `activeProviderMode` exists instead.
  @MainActor
  func testSwitchBridgeModeAppliesPiMonoLocalSwitchEvenWhenThePreferenceKeyAlreadyReflectsIt() async {
    let defaults = UserDefaults.standard
    let key = "chatBridgeMode"
    let previous = defaults.string(forKey: key)
    defer {
      if let previous {
        defaults.set(previous, forKey: key)
      } else {
        defaults.removeObject(forKey: key)
      }
    }

    defaults.set(ChatProvider.BridgeMode.piMono.rawValue, forKey: key)
    let provider = ChatProvider()
    XCTAssertEqual(provider.testingActiveBridgeState.providerMode, "omi")

    // Simulate the picker's own binding already having written the
    // destination value before switchBridgeMode is called.
    defaults.set(ChatProvider.BridgeMode.local.rawValue, forKey: key)
    await provider.switchBridgeMode(to: .local)
    XCTAssertEqual(
      provider.testingActiveBridgeState.providerMode, "omi-local",
      "switching to Local must apply even though the preference key already said 'local'")

    defaults.set(ChatProvider.BridgeMode.piMono.rawValue, forKey: key)
    await provider.switchBridgeMode(to: .piMono)
    XCTAssertEqual(
      provider.testingActiveBridgeState.providerMode, "omi",
      "switching back to Omi must apply too, not just the first flip")
  }

  // MARK: - Cloud-assisted features gate
  // Regression coverage for the unified Local-provider "Cloud-assisted
  // features" setting as it applies to connector synthesis (Apple
  // Notes/Calendar/Gmail/AI-profile): Local+Off must skip (the default),
  // Local+Cloud must send, and every other provider must send regardless of
  // the setting.

  func testConnectorSynthesisGate() {
    let bridgeModeKey = AIProvider.selectedProviderRawValueKey
    let cloudAssistModeKey = AIProvider.cloudAssistModeKey
    // AIProvider.localCloudAssistMode falls back to (and migrates from) this
    // legacy key when cloudAssistModeKey is unset, so a stale "cloud" value
    // left here by an earlier run/session would flake the "Off" assertion
    // below. Save/restore it alongside the other two keys.
    let legacyKey = AIProvider.connectorSynthesisModeKey
    let previousBridgeMode = UserDefaults.standard.string(forKey: bridgeModeKey)
    let previousCloudAssistMode = UserDefaults.standard.string(forKey: cloudAssistModeKey)
    let previousLegacyMode = UserDefaults.standard.string(forKey: legacyKey)
    defer {
      if let previousBridgeMode {
        UserDefaults.standard.set(previousBridgeMode, forKey: bridgeModeKey)
      } else {
        UserDefaults.standard.removeObject(forKey: bridgeModeKey)
      }
      if let previousCloudAssistMode {
        UserDefaults.standard.set(previousCloudAssistMode, forKey: cloudAssistModeKey)
      } else {
        UserDefaults.standard.removeObject(forKey: cloudAssistModeKey)
      }
      if let previousLegacyMode {
        UserDefaults.standard.set(previousLegacyMode, forKey: legacyKey)
      } else {
        UserDefaults.standard.removeObject(forKey: legacyKey)
      }
    }

    // Local + Off (the default, including an unset key): skip.
    UserDefaults.standard.set(ChatProvider.BridgeMode.local.rawValue, forKey: bridgeModeKey)
    UserDefaults.standard.removeObject(forKey: cloudAssistModeKey)
    UserDefaults.standard.removeObject(forKey: legacyKey)
    XCTAssertEqual(AIProvider.localCloudAssistMode, .off)
    XCTAssertTrue(AIProvider.shouldSkipConnectorSynthesis())

    UserDefaults.standard.set(AIProvider.CloudAssistMode.off.rawValue, forKey: cloudAssistModeKey)
    XCTAssertTrue(AIProvider.shouldSkipConnectorSynthesis())

    // Local + Cloud (opted in): send.
    UserDefaults.standard.set(AIProvider.CloudAssistMode.cloud.rawValue, forKey: cloudAssistModeKey)
    XCTAssertEqual(AIProvider.localCloudAssistMode, .cloud)
    XCTAssertFalse(AIProvider.shouldSkipConnectorSynthesis())

    // Omi AI (any non-local provider): always sends, regardless of the
    // cloud-assist setting: the setting is meaningless off Local.
    UserDefaults.standard.set(ChatProvider.BridgeMode.piMono.rawValue, forKey: bridgeModeKey)
    UserDefaults.standard.set(AIProvider.CloudAssistMode.off.rawValue, forKey: cloudAssistModeKey)
    XCTAssertFalse(AIProvider.shouldSkipConnectorSynthesis())
  }

  // MARK: - ApiKeysResponse shape assertion
  // After #6594, the response must NOT contain anthropic_api_key.

  func testApiKeysResponseDecodesWithoutAnthropicKey() throws {
    let json = Data(
      """
      {
        "firebase_api_key": "AIza-test",
        "google_calendar_api_key": "cal-key"
      }
      """.utf8)
    let response = try JSONDecoder().decode(APIClient.ApiKeysResponse.self, from: json)
    XCTAssertEqual(response.firebaseApiKey, "AIza-test")
    XCTAssertEqual(response.googleCalendarApiKey, "cal-key")
  }

  func testApiKeysResponseIgnoresUnknownAnthropicField() throws {
    // If the backend ever sends anthropic_api_key, the client must ignore it
    let json = Data(
      """
      {
        "firebase_api_key": "AIza-test",
        "anthropic_api_key": "sk-ant-LEAKED",
        "google_calendar_api_key": "cal-key"
      }
      """.utf8)
    let response = try JSONDecoder().decode(APIClient.ApiKeysResponse.self, from: json)
    XCTAssertEqual(response.firebaseApiKey, "AIza-test")
    // Verify no property named anthropicApiKey exists on the response
    let mirror = Mirror(reflecting: response)
    let propertyNames = mirror.children.map { $0.label ?? "" }
    XCTAssertFalse(
      propertyNames.contains("anthropicApiKey"),
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

  func testAIProviderAllContainsSupportedProviders() {
    XCTAssertEqual(AIProvider.all.map(\.id), ["piMono", "claude", "hermes", "openclaw", "local"])
  }

  func testAIProviderLocalHasCorrectValues() {
    let p = AIProvider.local
    XCTAssertEqual(p.id, "local")
    XCTAssertEqual(p.displayName, "Local")
    XCTAssertEqual(p.bridgeModeRawValue, "local")
    XCTAssertNil(p.attributionURL)
    XCTAssertFalse(p.tagline.isEmpty)
  }

  // MARK: - LocalModelsResponse decoding (GET /models)

  func testLocalModelsResponseDecodesRealLMStudioShape() throws {
    // Captured verbatim (trimmed) from a live `curl .../v1/models` against
    // an actual LM Studio server, locks in the real response shape rather
    // than a guessed one.
    let json = Data(
      """
      {
        "data": [
          {"id": "qwen2.5-7b-instruct", "object": "model", "owned_by": "organization_owner"},
          {"id": "qwen3.8-27b-optiq", "object": "model", "owned_by": "organization_owner"},
          {"id": "qwen3.8-27b-mlx@6bit", "object": "model", "owned_by": "organization_owner"}
        ],
        "object": "list"
      }
      """.utf8)
    let decoded = try JSONDecoder().decode(AIProvider.LocalModelsResponse.self, from: json)
    XCTAssertEqual(decoded.data.map(\.id), ["qwen2.5-7b-instruct", "qwen3.8-27b-optiq", "qwen3.8-27b-mlx@6bit"])
  }

  func testLocalModelsResponseDecodesEmptyList() throws {
    let json = Data("{\"data\": [], \"object\": \"list\"}".utf8)
    let decoded = try JSONDecoder().decode(AIProvider.LocalModelsResponse.self, from: json)
    XCTAssertTrue(decoded.data.isEmpty)
  }

  func testLocalModelsResponseFailsOnMissingDataKey() {
    let json = Data("{\"object\": \"list\"}".utf8)
    XCTAssertThrowsError(try JSONDecoder().decode(AIProvider.LocalModelsResponse.self, from: json))
  }

  func testAIProviderFromBridgeModeReturnsCorrectProvider() {
    XCTAssertEqual(AIProvider.from(bridgeMode: "piMono")?.id, "piMono")
    XCTAssertEqual(AIProvider.from(bridgeMode: "claudeCode")?.id, "claude")
    XCTAssertEqual(AIProvider.from(bridgeMode: "hermes")?.id, "hermes")
    XCTAssertEqual(AIProvider.from(bridgeMode: "openclaw")?.id, "openclaw")
    XCTAssertEqual(AIProvider.from(bridgeMode: "local")?.id, "local")
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

}
