import XCTest

@testable import Omi_Computer

final class LocalAgentProviderRoutingTests: XCTestCase {
  func testClassifyTaskDetectsCoding() {
    XCTAssertEqual(
      LocalAgentProviderRouting.classifyTask("debug this python script"),
      .coding
    )
  }

  func testClassifyTaskDetectsAutomation() {
    XCTAssertEqual(
      LocalAgentProviderRouting.classifyTask("automate sending this email"),
      .automation
    )
  }

  func testPreferredProvidersMatchSharedRouterPriors() {
    XCTAssertEqual(
      LocalAgentProviderRouting.preferredProviders(for: .coding),
      AgentProviderRouter.prior(for: .coding))
    XCTAssertEqual(
      LocalAgentProviderRouting.preferredProviders(for: .automation),
      AgentProviderRouter.prior(for: .computerUse))
    XCTAssertEqual(
      LocalAgentProviderRouting.preferredProviders(for: .general),
      AgentProviderRouter.prior(for: .general))
  }

  func testModelBriefMentioningHermesDoesNotCountAsExplicitUserRequest() {
    let env = ["OMI_CODEX_ADAPTER_COMMAND": "/tmp/codex"]
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "Use Hermes to refactor the auth module",
      requestedProvider: .hermes,
      userRequestText: nil,
      title: nil,
      environment: env,
      fileManager: FileManager(),
      homeDirectory: "/tmp/omi-routing-test"
    )

    guard case .spawn(let plan) = resolution else {
      return XCTFail("Expected spawn fallback to Codex, got \(resolution)")
    }
    XCTAssertEqual(plan.selectedProvider, .codex)
    XCTAssertTrue(plan.usedFallback)
  }

  func testExplicitHermesInUserTextStillRequiresSetupWhenMissing() {
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "fix the bug",
      requestedProvider: .hermes,
      userRequestText: "use hermes to fix the bug",
      title: nil,
      environment: [:],
      fileManager: FileManager(),
      homeDirectory: "/tmp/omi-routing-test"
    )

    guard case .setupRequired(let provider, let prompt, _) = resolution else {
      return XCTFail("Expected setupRequired, got \(resolution)")
    }
    XCTAssertEqual(provider, .hermes)
    XCTAssertTrue(prompt.contains("Hermes"))
  }

  func testSmartRoutingFallsBackWhenRequestedProviderMissing() {
    let env = ["OMI_CODEX_ADAPTER_COMMAND": "/tmp/codex"]
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "write a script to parse logs",
      requestedProvider: .hermes,
      userRequestText: "write a script to parse logs",
      title: "Log parser",
      environment: env,
      fileManager: FileManager(),
      homeDirectory: "/tmp/omi-routing-test"
    )

    guard case .spawn(let plan) = resolution else {
      return XCTFail("Expected spawn, got \(resolution)")
    }
    XCTAssertEqual(plan.selectedProvider, .codex)
    XCTAssertTrue(plan.usedFallback)
    XCTAssertNotNil(plan.fallbackNote)
    XCTAssertEqual(plan.harnessOverride, .codex)
  }

  func testSmartRoutingPicksCodexForCodingWhenAvailable() {
    let env = [
      "OMI_CODEX_ADAPTER_COMMAND": "/tmp/codex",
      "OMI_OPENCLAW_ADAPTER_COMMAND": "/tmp/openclaw",
    ]
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "review this swift api change",
      requestedProvider: nil,
      userRequestText: "review this swift api change",
      title: nil,
      environment: env,
      fileManager: FileManager(),
      homeDirectory: "/tmp/omi-routing-test"
    )

    guard case .spawn(let plan) = resolution else {
      return XCTFail("Expected spawn, got \(resolution)")
    }
    XCTAssertEqual(plan.selectedProvider, .codex)
    XCTAssertFalse(plan.usedFallback)
  }

  func testUnnamedGeneralTaskStaysOnDefaultOrchestrator() {
    let env = [
      "OMI_CODEX_ADAPTER_COMMAND": "/tmp/codex",
      "OMI_OPENCLAW_ADAPTER_COMMAND": "/tmp/openclaw",
      "OMI_HERMES_ADAPTER_COMMAND": "/tmp/hermes",
    ]
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "summarize my meetings from this week",
      requestedProvider: nil,
      userRequestText: nil,
      title: nil,
      environment: env,
      fileManager: FileManager(),
      homeDirectory: "/tmp/omi-routing-test"
    )

    guard case .spawn(let plan) = resolution else {
      return XCTFail("Expected spawn, got \(resolution)")
    }
    XCTAssertNil(plan.selectedProvider)
    XCTAssertNil(plan.harnessOverride)
    XCTAssertFalse(plan.usedFallback)
  }

  func testSpawnContextAdvancesFallbackChain() {
    var context = AgentSpawnContext(
      taskKind: .coding,
      explicitProvider: nil,
      fallbackChain: [.codex, .openclaw, nil],
      attemptedHarnesses: [.codex]
    )
    XCTAssertEqual(context.nextFallback(after: .codex), .some(.openclaw))
    context.recordAttempt(.openclaw)
    XCTAssertEqual(context.nextFallback(after: .openclaw), .some(nil))
  }

  func testRemainingProvidersDropsAttemptedHarnesses() {
    let context = AgentSpawnContext(
      taskKind: .coding,
      explicitProvider: nil,
      fallbackChain: [.codex, .hermes, .openclaw, nil],
      attemptedHarnesses: [.codex]
    )
    XCTAssertEqual(
      AgentSpawnFallbackPolicy.remainingProviders(from: context),
      [.hermes, .openclaw, nil])
  }

  func testTakeNextFallbackConsumesRetriableChain() {
    var remaining: [AgentPillsManager.DirectedProvider?] = [.hermes, nil]
    XCTAssertEqual(
      AgentSpawnFallbackPolicy.takeNextFallback(
        remaining: &remaining,
        error: NSError(
          domain: "test", code: 1,
          userInfo: [NSLocalizedDescriptionKey: "Failed to start child process"])),
      .some(.hermes))
    XCTAssertEqual(remaining, [nil])
    XCTAssertEqual(
      AgentSpawnFallbackPolicy.takeNextFallback(
        remaining: &remaining,
        error: NSError(
          domain: "test", code: 1,
          userInfo: [NSLocalizedDescriptionKey: "ENOENT: no such file or directory"])),
      .some(nil))
    XCTAssertTrue(remaining.isEmpty)
    XCTAssertNil(
      AgentSpawnFallbackPolicy.takeNextFallback(
        remaining: &remaining,
        error: NSError(
          domain: "test", code: 1,
          userInfo: [NSLocalizedDescriptionKey: "Failed to start child process"])) as Any?)
  }

  func testTakeNextFallbackIgnoresNonRetriableErrors() {
    var remaining: [AgentPillsManager.DirectedProvider?] = [.openclaw, nil]
    XCTAssertNil(
      AgentSpawnFallbackPolicy.takeNextFallback(
        remaining: &remaining,
        error: NSError(
          domain: "test", code: 1,
          userInfo: [NSLocalizedDescriptionKey: "Could not find the email thread"])) as Any?)
    XCTAssertEqual(remaining, [.openclaw, nil])
  }

  func testTakeNextFallbackRequiresStartupPhaseForStructuredFailures() {
    var remaining: [AgentPillsManager.DirectedProvider?] = [.hermes, nil]
    let executionFailure = BridgeError.agentRuntimeFailure(
      AgentRuntimeFailure(
        code: "adapter_spawn_failed",
        failureCode: .bridgeStartFailed,
        userMessage: "Failed to spawn adapter process",
        phase: nil
      ))
    XCTAssertNil(
      AgentSpawnFallbackPolicy.takeNextFallback(remaining: &remaining, error: executionFailure) as Any?)
    XCTAssertEqual(remaining, [.hermes, nil])

    let startupFailure = BridgeError.agentRuntimeFailure(
      AgentRuntimeFailure(
        code: "adapter_unavailable",
        failureCode: .adapterUnavailable,
        userMessage: "Adapter not ready",
        phase: "startup"
      ))
    XCTAssertEqual(
      AgentSpawnFallbackPolicy.takeNextFallback(remaining: &remaining, error: startupFailure),
      .some(.hermes))
    XCTAssertEqual(remaining, [nil])
  }

  func testIsRetriableSpawnFailureMatchesInfrastructureErrors() {
    XCTAssertTrue(LocalAgentProviderRouting.isRetriableSpawnFailure("AI not available: adapter failed"))
    XCTAssertTrue(LocalAgentProviderRouting.isRetriableSpawnFailure("ENOENT: no such file or directory"))
    XCTAssertTrue(LocalAgentProviderRouting.isRetriableSpawnFailure("Failed to start child process"))
    XCTAssertFalse(LocalAgentProviderRouting.isRetriableSpawnFailure("Could not find the email thread"))
    XCTAssertFalse(LocalAgentProviderRouting.isRetriableSpawnFailure("Could not parse adapter response: invalid JSON"))
  }

  func testExplicitProviderSpawnHasEmptyFallbackChain() {
    let env = [
      "OMI_CODEX_ADAPTER_COMMAND": "/tmp/codex",
      "OMI_HERMES_ADAPTER_COMMAND": "/tmp/hermes",
      "OMI_OPENCLAW_ADAPTER_COMMAND": "/tmp/openclaw",
    ]
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "refactor the auth module",
      requestedProvider: .codex,
      userRequestText: "use codex to refactor the auth module",
      title: nil,
      environment: env,
      fileManager: FileManager(),
      homeDirectory: "/tmp/omi-routing-test"
    )

    guard case .spawn(let plan) = resolution else {
      return XCTFail("Expected spawn, got \(resolution)")
    }
    XCTAssertEqual(plan.selectedProvider, .codex)
    XCTAssertEqual(plan.context.explicitProvider, .codex)
    XCTAssertEqual(plan.context.fallbackChain, [])
    XCTAssertEqual(AgentSpawnFallbackPolicy.remainingProviders(from: plan.context), [])
  }

  func testChatToolExplicitProviderAlsoHasEmptyFallbackChain() {
    let env = [
      "OMI_CODEX_ADAPTER_COMMAND": "/tmp/codex",
      "OMI_HERMES_ADAPTER_COMMAND": "/tmp/hermes",
    ]
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "write a script",
      requestedProvider: .hermes,
      userRequestText: nil,
      title: nil,
      treatRequestedAsExplicit: true,
      environment: env,
      fileManager: FileManager(),
      homeDirectory: "/tmp/omi-routing-test"
    )

    guard case .spawn(let plan) = resolution else {
      return XCTFail("Expected spawn, got \(resolution)")
    }
    XCTAssertEqual(plan.selectedProvider, .hermes)
    XCTAssertEqual(plan.context.fallbackChain, [])
    XCTAssertEqual(AgentSpawnFallbackPolicy.remainingProviders(from: plan.context), [])
  }

  func testNegatedProviderMentionDoesNotRouteToThatProvider() {
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "write a script",
      requestedProvider: nil,
      userRequestText: "don't use hermes, use codex",
      title: nil,
      environment: [:],
      fileManager: FileManager(),
      homeDirectory: "/tmp/omi-routing-test"
    )

    guard case .setupRequired(let provider, _, _) = resolution else {
      return XCTFail("Expected setupRequired for codex (not installed), got \(resolution)")
    }
    XCTAssertEqual(provider, .codex, "should route to the positively-requested provider, not the negated one")
  }

  func testChatToolProviderArgTreatedAsExplicit() {
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "write a script",
      requestedProvider: .hermes,
      userRequestText: nil,
      title: nil,
      treatRequestedAsExplicit: true,
      environment: [:],
      fileManager: FileManager(),
      homeDirectory: "/tmp/omi-routing-test"
    )

    guard case .setupRequired(let provider, _, _) = resolution else {
      return XCTFail("Expected setupRequired for hermes (not installed), got \(resolution)")
    }
    XCTAssertEqual(provider, .hermes, "chat tool's provider arg should be treated as explicit")
  }

  func testChatToolProviderArgIgnoredWhenNotExplicit() {
    let env = ["OMI_CODEX_ADAPTER_COMMAND": "/tmp/codex"]
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "write a python script",
      requestedProvider: .openclaw,
      userRequestText: nil,
      title: nil,
      treatRequestedAsExplicit: false,
      environment: env,
      fileManager: FileManager(),
      homeDirectory: "/tmp/omi-routing-test"
    )

    guard case .spawn(let plan) = resolution else {
      return XCTFail("Expected spawn via task-based ranking, got \(resolution)")
    }
    XCTAssertEqual(
      plan.selectedProvider, .codex,
      "without explicit intent, task-based ranking should pick codex for coding, not the model's openclaw")
  }

  // MARK: - Health-ready routing

  /// A Codex binary on disk must NOT route to spawn until it is wired and
  /// authed. `AgentProviderHealth` is the authority: binary + codex-acp
  /// bridge + credentials, not just "the executable exists".
  func testCodexBinaryWithoutBridgeOrAuthIsSetupRequired() throws {
    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("codex-no-bridge-\(UUID().uuidString)", isDirectory: true)
    let bin = tempDir.appendingPathComponent("bin", isDirectory: true)
    try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tempDir) }

    let codexPath = bin.appendingPathComponent("codex")
    FileManager.default.createFile(atPath: codexPath.path, contents: Data("#!/bin/sh\n".utf8))
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: codexPath.path)

    let env = ["PATH": bin.path, "HOME": tempDir.path]
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "write a script",
      requestedProvider: .codex,
      userRequestText: "use codex to write a script",
      title: nil,
      environment: env,
      fileManager: FileManager(),
      homeDirectory: tempDir.path
    )

    guard case .setupRequired(let provider, let prompt, _) = resolution else {
      return XCTFail("Expected setupRequired for codex with a bare binary, got \(resolution)")
    }
    XCTAssertEqual(provider, .codex)
    XCTAssertTrue(
      prompt.contains("codex-acp") || prompt.contains("Codex"),
      "setup prompt should point at what's missing, got: \(prompt)")
  }

  /// A wired-and-authed Codex routes to spawn.
  func testCodexWiredAndAuthedRoutesToSpawn() throws {
    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("codex-ready-\(UUID().uuidString)", isDirectory: true)
    let bin = tempDir.appendingPathComponent("bin", isDirectory: true)
    let home = tempDir.appendingPathComponent("home", isDirectory: true)
    let codexDotDir = home.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: codexDotDir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tempDir) }

    for name in ["codex", "codex-acp"] {
      let path = bin.appendingPathComponent(name)
      FileManager.default.createFile(atPath: path.path, contents: Data("#!/bin/sh\n".utf8))
      try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: path.path)
    }
    FileManager.default.createFile(
      atPath: codexDotDir.appendingPathComponent("auth.json").path,
      contents: Data("{}".utf8))

    let env = ["PATH": bin.path, "HOME": home.path]
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "write a script",
      requestedProvider: .codex,
      userRequestText: "use codex to write a script",
      title: nil,
      environment: env,
      fileManager: FileManager(),
      homeDirectory: home.path
    )

    guard case .spawn(let plan) = resolution else {
      return XCTFail("Expected spawn for wired+authed codex, got \(resolution)")
    }
    XCTAssertEqual(plan.selectedProvider, .codex)
  }

  /// Auto-routing (no explicit provider) must exclude a bare Codex binary from
  /// the fallback chain the same way it is excluded from spawn selection.
  func testAutoRoutingExcludesBareCodexBinaryFromFallbackChain() throws {
    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("codex-auto-\(UUID().uuidString)", isDirectory: true)
    let bin = tempDir.appendingPathComponent("bin", isDirectory: true)
    let home = tempDir.appendingPathComponent("home", isDirectory: true)
    let hermesDotDir = home.appendingPathComponent(".hermes", isDirectory: true)
    try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: hermesDotDir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tempDir) }

    // Hermes is fully ready (binary only — no auth gate).
    let hermesPath = bin.appendingPathComponent("hermes")
    FileManager.default.createFile(atPath: hermesPath.path, contents: Data("#!/bin/sh\n".utf8))
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: hermesPath.path)

    // Codex is a bare binary: present but not wired/authed.
    let codexPath = bin.appendingPathComponent("codex")
    FileManager.default.createFile(atPath: codexPath.path, contents: Data("#!/bin/sh\n".utf8))
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: codexPath.path)

    let env = ["PATH": bin.path, "HOME": home.path]
    let resolution = LocalAgentProviderRouting.resolveSpawn(
      brief: "write a script",
      requestedProvider: nil,
      userRequestText: "write a script",
      title: nil,
      environment: env,
      fileManager: FileManager(),
      homeDirectory: home.path
    )

    guard case .spawn(let plan) = resolution else {
      return XCTFail("Expected spawn via ready hermes, got \(resolution)")
    }
    XCTAssertEqual(plan.selectedProvider, .hermes)
    XCTAssertFalse(
      plan.context.fallbackChain.contains(.codex),
      "bare codex binary must not appear in the fallback chain")
  }
}
