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
          userInfo: [NSLocalizedDescriptionKey: "Failed to start child process"])))
  }

  func testTakeNextFallbackIgnoresNonRetriableErrors() {
    var remaining: [AgentPillsManager.DirectedProvider?] = [.openclaw, nil]
    XCTAssertNil(
      AgentSpawnFallbackPolicy.takeNextFallback(
        remaining: &remaining,
        error: NSError(
          domain: "test", code: 1,
          userInfo: [NSLocalizedDescriptionKey: "Could not find the email thread"])))
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
      AgentSpawnFallbackPolicy.takeNextFallback(remaining: &remaining, error: executionFailure))
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
}
