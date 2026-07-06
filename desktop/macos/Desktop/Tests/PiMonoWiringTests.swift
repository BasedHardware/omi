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

  func testTaskChatModeMappingCodex() {
    XCTAssertEqual(ChatProvider.harnessMode(for: .codex), "codex")
  }

  func testTaskChatModeMappingAgentSDK() {
    XCTAssertEqual(ChatProvider.harnessMode(for: .omiAI), "piMono")
  }

  func testHarnessToAdapterMappingFailsClosed() {
    XCTAssertEqual(AgentRuntimeRouting.adapterId(for: .piMono).rawValue, "pi-mono")
    XCTAssertEqual(AgentRuntimeRouting.adapterId(for: .acp).rawValue, "acp")
    XCTAssertEqual(AgentRuntimeRouting.adapterId(for: .hermes).rawValue, "hermes")
    XCTAssertEqual(AgentRuntimeRouting.adapterId(for: .openclaw).rawValue, "openclaw")
    XCTAssertEqual(AgentRuntimeRouting.adapterId(for: .codex).rawValue, "codex")
    XCTAssertEqual(AgentRuntimeRouting.harnessMode(from: "codex"), .codex)
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

  func testLocalAgentProviderDetectorIgnoresArbitraryPathEntries() throws {
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

    XCTAssertFalse(availability.isAvailable)
  }

  // MARK: - Best-agent selection + startup-failure fallback

  func testStartupClassFailuresAreRetryableOnAnotherAgent() {
    // Real strings produced by the pre-flight / activation / auth paths —
    // all occur BEFORE the agent does any work, so auto-fallback is safe.
    let startupFailures = [
      "Codex is not available. Make sure Codex is installed first, then try again.",
      "I don't see Hermes installed. Make sure Hermes is installed first, then try again.",
      "Codex is installed but not signed in. Run `codex login` in Terminal, or add an OpenAI API key in Omi Settings, then try again.",
      "Codex isn't signed in. Run `codex login` in Terminal, or add an OpenAI API key in Omi Settings, then try again.",
      "Not authenticated. Run `codex login` or set OPENAI_API_KEY.",
      "codex adapter requires OMI_CODEX_ADAPTER_COMMAND",
      "OpenClaw needs setup",
      // Found live in dogfooding: openclaw binary present but gateway daemon
      // not running — subprocess dies before any work happens.
      "OpenClaw failed: ACP bridge failed: connect ECONNREFUSED 127.0.0.1:18789",
    ]
    for message in startupFailures {
      XCTAssertTrue(AgentPillsManager.isStartupClassFailure(message), "should be startup-class: \(message)")
    }
  }

  func testMidTaskFailuresNeverAutoFallback() {
    // Mid-task/side-effect-capable failures must NOT be re-run on another
    // agent — the task may already be partially executed.
    let midTaskFailures = [
      "Something went wrong. Please try again.",
      "AI took too long to respond. Try again.",
      "AI stopped unexpectedly. Try sending your message again.",
      "Agent ended before reporting a final result",
      "AI service is busy. Please try again in a moment.",
      "tool execution failed: browser tab crashed",
    ]
    for message in midTaskFailures {
      XCTAssertFalse(AgentPillsManager.isStartupClassFailure(message), "must not be startup-class: \(message)")
    }
  }

  func testRouterDecisionDefaultsToNoExternalProviders() {
    let decision = AgentPillsManager.RouterDecision(route: .agent, title: "T", ack: "A")
    XCTAssertTrue(decision.rankedProviders.isEmpty)
  }

  // MARK: - Codex auth pre-flight

  func testCodexInstalledWithoutAnyCredentialNeedsAuth() throws {
    let home = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-codex-noauth-\(UUID().uuidString)", isDirectory: true)
    let bin = home.appendingPathComponent(".local/bin", isDirectory: true)
    try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: home) }

    let executable = bin.appendingPathComponent("codex-acp")
    try "#!/bin/sh\nexit 0\n".write(to: executable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable.path)

    let availability = LocalAgentProviderDetector.availability(
      for: .codex,
      environment: [:],
      homeDirectory: home.path,
      byokOpenAIKeyPresent: false)

    XCTAssertFalse(availability.isAvailable)
    XCTAssertEqual(availability.status, .needsAuth(command: executable.path))
    XCTAssertTrue(availability.setupPrompt.contains("codex login"))
    XCTAssertTrue(availability.setupPrompt.contains("OpenAI API key"))
  }

  func testCodexCredentialSourcesUnlockAvailability() throws {
    let home = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-codex-auth-\(UUID().uuidString)", isDirectory: true)
    let bin = home.appendingPathComponent(".local/bin", isDirectory: true)
    try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: home) }

    let executable = bin.appendingPathComponent("codex-acp")
    try "#!/bin/sh\nexit 0\n".write(to: executable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable.path)

    // 1. API key in environment
    XCTAssertTrue(
      LocalAgentProviderDetector.availability(
        for: .codex, environment: ["OPENAI_API_KEY": "sk-test"],
        homeDirectory: home.path, byokOpenAIKeyPresent: false
      ).isAvailable)

    // 2. codex login session (~/.codex/auth.json)
    let codexDir = home.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: codexDir, withIntermediateDirectories: true)
    try "{}".write(to: codexDir.appendingPathComponent("auth.json"), atomically: true, encoding: .utf8)
    XCTAssertTrue(
      LocalAgentProviderDetector.availability(
        for: .codex, environment: [:],
        homeDirectory: home.path, byokOpenAIKeyPresent: false
      ).isAvailable)
    try FileManager.default.removeItem(at: codexDir)

    // 3. in-app BYOK OpenAI key
    XCTAssertTrue(
      LocalAgentProviderDetector.availability(
        for: .codex, environment: [:],
        homeDirectory: home.path, byokOpenAIKeyPresent: true
      ).isAvailable)
  }

  func testCodexMissingBinaryIsMissingNotNeedsAuth() throws {
    for dir in ["/opt/homebrew/bin", "/usr/local/bin"] {
      try XCTSkipIf(
        FileManager.default.isExecutableFile(atPath: "\(dir)/codex-acp"),
        "codex-acp is actually installed in \(dir); missing-state is unobservable here")
    }
    let availability = LocalAgentProviderDetector.availability(
      for: .codex,
      environment: ["PATH": "/tmp/definitely-missing-\(UUID().uuidString)"],
      homeDirectory: "/tmp/missing-home",
      byokOpenAIKeyPresent: true)

    XCTAssertEqual(availability.status, .missing)
    XCTAssertTrue(availability.setupPrompt.contains("npm i -g"))
  }

  func testLocalAgentProviderDetectorMissingPromptIsUserFacing() throws {
    // The detector unconditionally searches /opt/homebrew/bin and
    // /usr/local/bin; on machines with a real openclaw install this test
    // cannot observe the "missing" state.
    for dir in ["/opt/homebrew/bin", "/usr/local/bin"] {
      try XCTSkipIf(
        FileManager.default.isExecutableFile(atPath: "\(dir)/openclaw"),
        "openclaw is actually installed in \(dir); missing-state is unobservable here")
    }
    let availability = LocalAgentProviderDetector.availability(
      for: .openclaw,
      environment: ["PATH": "/tmp/definitely-missing-\(UUID().uuidString)"],
      homeDirectory: "/tmp/missing-home")

    XCTAssertFalse(availability.isAvailable)
    XCTAssertEqual(
      availability.setupPrompt,
      "I don't see OpenClaw installed. Install it with `npm i -g openclaw`, start it with `openclaw gateway`, then try again.")
    XCTAssertEqual(
      availability.toolError,
      "Error: I don't see OpenClaw installed. Install it with `npm i -g openclaw`, start it with `openclaw gateway`, then try again.")
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

  func testAIProviderAllContainsSupportedProviders() {
    XCTAssertEqual(AIProvider.all.map(\.id), ["piMono", "claude", "hermes", "openclaw", "codex"])
  }

  func testAIProviderFromBridgeModeReturnsCorrectProvider() {
    XCTAssertEqual(AIProvider.from(bridgeMode: "piMono")?.id, "piMono")
    XCTAssertEqual(AIProvider.from(bridgeMode: "claudeCode")?.id, "claude")
    XCTAssertEqual(AIProvider.from(bridgeMode: "hermes")?.id, "hermes")
    XCTAssertEqual(AIProvider.from(bridgeMode: "openclaw")?.id, "openclaw")
    XCTAssertEqual(AIProvider.from(bridgeMode: "codex")?.id, "codex")
    XCTAssertNil(AIProvider.from(bridgeMode: "unknown"))
    XCTAssertNil(AIProvider.from(bridgeMode: "agentSDK"))
  }

  func testProviderDirectiveRoutesAskOpenClawToOpenClawHarness() {
    let directive = AgentPillsManager.providerDirective(from: "Please ask openclaw how it's going")

    XCTAssertEqual(directive?.provider, .openclaw)
    XCTAssertEqual(directive?.provider.harnessMode, .openclaw)
    XCTAssertEqual(directive?.rewrittenQuery, "how it's going")
    XCTAssertEqual(directive?.title, "OpenClaw")
  }

  func testProviderDirectiveRoutesHermesToHermesHarness() {
    let directive = AgentPillsManager.providerDirective(from: "Hermes: summarize your current status")

    XCTAssertEqual(directive?.provider, .hermes)
    XCTAssertEqual(directive?.provider.harnessMode, .hermes)
    XCTAssertEqual(directive?.rewrittenQuery, "summarize your current status")
    XCTAssertEqual(directive?.title, "Hermes")
  }

  func testProviderDirectiveRoutesCodexToCodexHarness() {
    let directive = AgentPillsManager.providerDirective(from: "use codex to refactor the parser")

    XCTAssertEqual(directive?.provider, .codex)
    XCTAssertEqual(directive?.provider.harnessMode, .codex)
    XCTAssertEqual(directive?.rewrittenQuery, "to refactor the parser")
    XCTAssertEqual(directive?.title, "Codex")
  }

  func testProviderDirectiveIgnoresNonProviderQuestions() {
    XCTAssertNil(AgentPillsManager.providerDirective(from: "what is openclaw?"))
    XCTAssertNil(AgentPillsManager.providerDirective(from: "openclaw architecture"))
    XCTAssertNil(AgentPillsManager.providerDirective(from: "hermes scarf"))
    XCTAssertNil(AgentPillsManager.providerDirective(from: "compare hermes and openclaw"))
    XCTAssertNil(AgentPillsManager.providerDirective(from: "how is it going?"))
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
