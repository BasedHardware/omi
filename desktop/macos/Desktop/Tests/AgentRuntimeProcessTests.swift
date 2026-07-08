import XCTest

@testable import Omi_Computer

final class AgentRuntimeProcessTests: XCTestCase {
  // MARK: - CHAT-02 agent stall hook

  func testSuspendStreamNoOpsWithoutRunningProcess() async {
    // External contract: the debug suspend never reports success without a real
    // suspend — it returns an error (prod-gated in the test host, or no running
    // process on a dev bundle), never suspended:true, and never SIGSTOPs a bogus pid.
    let result = await AgentRuntimeProcess.shared.debugSuspendStream(durationMs: 190_000)
    XCTAssertNotEqual(result["suspended"], "true")
    XCTAssertNotNil(result["error"])
  }

  func testResumeStreamNoOpsWithoutProcess() async {
    let result = await AgentRuntimeProcess.shared.debugResumeStream()
    XCTAssertNotEqual(result["resumed"], "true")
    XCTAssertNotNil(result["error"])
  }

  func testAgentStallHookIsNonProdGatedAndSafe() throws {
    let processSource = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift"),
      encoding: .utf8)
    // Production gate, live-process guard, real signals, bounded window, and a
    // generation-guarded auto-resume so a forgotten resume can't wedge the agent.
    for needle in [
      "func debugSuspendStream(durationMs: Int)",
      "guard AppBuild.isNonProduction else",
      "process.isRunning, process.processIdentifier > 0",
      "kill(pid, SIGSTOP)",
      "kill(pid, SIGCONT)",
      "min(durationMs, 300_000)",
      "generation == debugSuspendGeneration",
    ] {
      XCTAssertTrue(processSource.contains(needle), "AgentRuntimeProcess missing stall-hook invariant: \(needle)")
    }

    let bridgeSource = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("Sources/DesktopAutomationBridge.swift"),
      encoding: .utf8)
    for needle in ["name: \"suspend_agent_stream\"", "name: \"resume_agent_stream\""] {
      XCTAssertTrue(bridgeSource.contains(needle), "bridge missing action: \(needle)")
    }
    // Both actions must be behind the non-prod guard.
    let suspendIdx = bridgeSource.range(of: "name: \"suspend_agent_stream\"")!.lowerBound
    let afterSuspend = String(bridgeSource[suspendIdx...].prefix(600))
    XCTAssertTrue(afterSuspend.contains("AppBuild.isNonProduction"),
      "suspend_agent_stream must be gated to non-production bundles")
  }

  func testV2ResultParsingPreservesCanonicalAndAdapterIds() {
    let line = """
      {"type":"result","protocolVersion":2,"requestId":"req-1","clientId":"client-1","sessionId":"omi-1","runId":"run-1","attemptId":"attempt-1","adapterSessionId":"acp-1","terminalStatus":"succeeded","text":"done","costUsd":1.25,"inputTokens":3,"outputTokens":4,"cacheReadTokens":5,"cacheWriteTokens":6}
      """

    let message = AgentRuntimeProcess.RuntimeMessage.parse(line)

    XCTAssertEqual(message?.kind, .result)
    XCTAssertEqual(message?.requestId, "req-1")
    XCTAssertEqual(message?.clientId, "client-1")
    XCTAssertEqual(message?.requestKey, AgentRuntimeProcess.RuntimeMessage.RequestKey(clientId: "client-1", requestId: "req-1"))
    XCTAssertEqual(message?.payload["sessionId"] as? String, "omi-1")
    XCTAssertEqual(message?.payload["adapterSessionId"] as? String, "acp-1")
    XCTAssertEqual(message?.payload["terminalStatus"] as? String, "succeeded")
  }

  func testCancelAckRoutesByRequestId() {
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"cancel_ack","protocolVersion":2,"requestId":"cancel-me","clientId":"client-1","accepted":true,"dispatchAttempted":true,"adapterAcknowledged":false}"#
    )

    XCTAssertEqual(message?.kind, .cancelAck)
    XCTAssertEqual(message?.requestKey, AgentRuntimeProcess.RuntimeMessage.RequestKey(clientId: "client-1", requestId: "cancel-me"))
    XCTAssertEqual(message?.payload["accepted"] as? Bool, true)
    XCTAssertEqual(message?.payload["adapterAcknowledged"] as? Bool, false)
  }

  func testInitMessageCarriesAdvertisedAgentControlTools() {
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"init","sessionId":"","agentControlTools":["list_agent_sessions","spawn_background_agent"]}"#
    )

    XCTAssertEqual(message?.kind, .initMessage)
    XCTAssertEqual(message?.payload["agentControlTools"] as? [String], ["list_agent_sessions", "spawn_background_agent"])
  }

  func testControlToolResultRoutesByRequestId() {
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"control_tool_result","protocolVersion":2,"requestId":"control-1","clientId":"client-1","name":"inspect_agent_artifacts","result":"{\"ok\":true,\"artifacts\":[]}"}"#
    )

    XCTAssertEqual(message?.kind, .controlToolResult)
    XCTAssertEqual(message?.requestKey, AgentRuntimeProcess.RuntimeMessage.RequestKey(clientId: "client-1", requestId: "control-1"))
    XCTAssertEqual(message?.payload["name"] as? String, "inspect_agent_artifacts")
    XCTAssertEqual(message?.payload["result"] as? String, #"{"ok":true,"artifacts":[]}"#)
  }

  func testV2MessagesWithoutClientIdDoNotHaveRequestKey() {
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"result","protocolVersion":2,"requestId":"req-1","sessionId":"omi-1","runId":"run-1","attemptId":"attempt-1","terminalStatus":"succeeded","text":"done"}"#
    )

    XCTAssertEqual(message?.kind, .result)
    XCTAssertNil(message?.requestKey)
  }

  func testHarnessModeMapsNamedAdapters() {
    XCTAssertEqual(AgentRuntimeProcess.adapterId(forHarnessMode: "piMono"), "pi-mono")
    XCTAssertEqual(AgentRuntimeProcess.adapterId(forHarnessMode: "pi-mono"), "pi-mono")
    XCTAssertEqual(AgentRuntimeProcess.adapterId(forHarnessMode: "hermes"), "hermes")
    XCTAssertEqual(AgentRuntimeProcess.adapterId(forHarnessMode: "openclaw"), "openclaw")
    XCTAssertEqual(AgentRuntimeProcess.adapterId(forHarnessMode: "openClaw"), "openclaw")
    XCTAssertNil(AgentRuntimeProcess.adapterId(forHarnessMode: "unknown"))
  }

  func testPiMonoAliasUsesCanonicalAdapterForAuthGuards() throws {
    let processSourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let processSource = try String(contentsOf: processSourceURL, encoding: .utf8)

    XCTAssertTrue(processSource.contains("let preferredAdapterId = AgentRuntimeRouting.adapterId(for: preferredHarness)"))
    XCTAssertTrue(processSource.contains("preferredAdapterId == .piMono"))
    XCTAssertFalse(processSource.contains(#"preferredHarnessMode == "piMono""#))

    let bridgeSourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentBridge.swift")
    let bridgeSource = try String(contentsOf: bridgeSourceURL, encoding: .utf8)

    XCTAssertTrue(bridgeSource.contains("AgentRuntimeProcess.adapterId(forHarnessMode: harnessMode) == AgentAdapterId.piMono.rawValue"))
    XCTAssertTrue(bridgeSource.contains("if isPiMonoHarness, tokenRefreshTask == nil"))
    XCTAssertTrue(bridgeSource.contains("guard isPiMonoHarness else { return false }"))
    XCTAssertFalse(bridgeSource.contains(#"harnessMode == "piMono""#))
  }

  func testPiMonoInvalidTokenRetriesAfterForcedAuthRefresh() throws {
    let bridgeSourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentBridge.swift")
    let bridgeSource = try String(contentsOf: bridgeSourceURL, encoding: .utf8)

    XCTAssertTrue(bridgeSource.contains("error.isSessionAuthenticationFailure"))
    XCTAssertTrue(bridgeSource.contains("!bridgeOutputTracker.hasOutput"))
    XCTAssertTrue(bridgeSource.contains("private final class BridgeOutputTracker: @unchecked Sendable"))
    XCTAssertTrue(bridgeSource.contains("refreshing token and retrying once"))
    // The refresh must convert real auth failures to authMissing so ChatProvider
    // routes to the sign-in recovery CTA, while propagating CancellationError so a
    // cancelled request is not misrouted to auth recovery.
    XCTAssertTrue(bridgeSource.contains("catch is CancellationError"))
    XCTAssertTrue(bridgeSource.contains("throw CancellationError()"))
    XCTAssertTrue(bridgeSource.contains("catch {"))
    XCTAssertTrue(bridgeSource.contains("throw BridgeError.authMissing"))
    XCTAssertFalse(bridgeSource.contains("guard try await refreshAuthToken()"))
    XCTAssertFalse(bridgeSource.contains("(try? await refreshAuthToken()) == true"))
    XCTAssertTrue(bridgeSource.contains("let retryRequestId = UUID().uuidString"))
  }

  func testNamedBundleStateDirectoriesAreIsolated() {
    let home = URL(fileURLWithPath: "/tmp/test-home")

    let firstState = AgentRuntimeProcess.defaultStateDirectory(
      bundleIdentifier: "com.omi.omi-ticket-five-a",
      homeDirectory: home
    )
    let secondState = AgentRuntimeProcess.defaultStateDirectory(
      bundleIdentifier: "com.omi.omi-ticket-five-b",
      homeDirectory: home
    )
    let firstArtifacts = AgentRuntimeProcess.defaultArtifactsDirectory(
      bundleIdentifier: "com.omi.omi-ticket-five-a",
      homeDirectory: home
    )
    let secondArtifacts = AgentRuntimeProcess.defaultArtifactsDirectory(
      bundleIdentifier: "com.omi.omi-ticket-five-b",
      homeDirectory: home
    )

    XCTAssertNotEqual(firstState, secondState)
    XCTAssertNotEqual(firstArtifacts, secondArtifacts)
    XCTAssertTrue(firstState.hasSuffix("AgentRuntime/com.omi.omi-ticket-five-a"))
    XCTAssertTrue(secondState.hasSuffix("AgentRuntime/com.omi.omi-ticket-five-b"))
    XCTAssertTrue(firstArtifacts.hasSuffix("Artifacts/com.omi.omi-ticket-five-a"))
    XCTAssertTrue(secondArtifacts.hasSuffix("Artifacts/com.omi.omi-ticket-five-b"))
  }

  func testCompatibilitySessionIdPrefersAdapterSession() {
    let withAdapter = AgentBridge.QueryResult(
      text: "done",
      costUsd: 0,
      omiSessionId: "omi-session",
      runId: "run",
      attemptId: "attempt",
      adapterSessionId: "adapter-session",
      terminalStatus: "succeeded",
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0
    )
    let withoutAdapter = AgentBridge.QueryResult(
      text: "done",
      costUsd: 0,
      omiSessionId: "omi-session",
      runId: "run",
      attemptId: "attempt",
      adapterSessionId: nil,
      terminalStatus: "succeeded",
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0
    )

    XCTAssertEqual(withAdapter.adapterSessionId, "adapter-session")
    XCTAssertEqual(withoutAdapter.omiSessionId, "omi-session")
    XCTAssertNil(withoutAdapter.adapterSessionId)
  }

  func testSharedRuntimeDoesNotTrackCurrentHarnessMode() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertFalse(source.contains("currentHarnessMode"))
    XCTAssertFalse(source.contains("harness changed"))
    XCTAssertFalse(source.contains(#""adapterId": harnessMode == "piMono" ? "pi-mono" : "acp""#))
  }

  func testLocalAdapterDiscoveryRunsForSharedRuntimeStartup() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("applyLocalAgentEnvironment(to: &env)"))
    XCTAssertFalse(source.contains("applyLocalAgentEnvironment(to: &env, adapterId: preferredAdapterId)"))
    XCTAssertFalse(source.contains("guard adapterId == .hermes || adapterId == .openclaw else"))
    XCTAssertTrue(source.contains(#"env["HOME"] = home"#))
    XCTAssertTrue(source.contains(#"env["HERMES_HOME"] = "\(home)/.hermes""#))
    XCTAssertTrue(source.contains(#""\(home)/.hermes/hermes-agent/venv/bin""#))
    XCTAssertTrue(source.contains("existingPath.split(separator: \":\").map(String.init) + trustedPathDirs"))
    XCTAssertTrue(source.contains("+ adapterPathDirs"))
    XCTAssertFalse(source.contains("adapterPathPrefixDirs + existingPath.split"))
    XCTAssertTrue(source.contains(#"env["PATH"] = pathElements.joined(separator: ":")"#))
    XCTAssertTrue(source.contains(#"env["OMI_OPENCLAW_ADAPTER_COMMAND"]"#))
    XCTAssertTrue(source.contains(#"env["OMI_HERMES_ADAPTER_COMMAND"]"#))
  }

  @MainActor
  func testUsableByokEnvironmentSuppressesAllKeysWhenOneProviderIsKnownBad() {
    let savedKeys = Dictionary(
      uniqueKeysWithValues: BYOKProvider.allCases.map { provider in
        (provider, UserDefaults.standard.string(forKey: provider.storageKey))
      })
    defer {
      for provider in BYOKProvider.allCases {
        if let saved = savedKeys[provider] ?? nil {
          UserDefaults.standard.set(saved, forKey: provider.storageKey)
        } else {
          UserDefaults.standard.removeObject(forKey: provider.storageKey)
        }
      }
      CredentialHealthManager.shared.reset()
    }

    for provider in BYOKProvider.allCases {
      UserDefaults.standard.set("sk-agent-\(provider.rawValue)", forKey: provider.storageKey)
    }
    let openAIKey = APIKeyService.byokKey(.openai)!
    CredentialHealthManager.shared.recordProviderFailure(
      .providerAuthFailed(provider: .openai, mode: .byok),
      provider: .openai,
      authMode: .byok,
      fingerprint: APIKeyService.byokFingerprint(openAIKey),
      context: "test")

    let result = AgentRuntimeProcess.usableBYOKEnvironment()

    XCTAssertTrue(result.values.isEmpty)
    XCTAssertEqual(result.suppressedProviders, [.openai])
  }

  @MainActor
  func testUsableByokEnvironmentIncludesAllKeysWhenAllProvidersAreUsable() {
    let savedKeys = Dictionary(
      uniqueKeysWithValues: BYOKProvider.allCases.map { provider in
        (provider, UserDefaults.standard.string(forKey: provider.storageKey))
      })
    defer {
      for provider in BYOKProvider.allCases {
        if let saved = savedKeys[provider] ?? nil {
          UserDefaults.standard.set(saved, forKey: provider.storageKey)
        } else {
          UserDefaults.standard.removeObject(forKey: provider.storageKey)
        }
      }
      CredentialHealthManager.shared.reset()
    }

    for provider in BYOKProvider.allCases {
      UserDefaults.standard.set("sk-agent-\(provider.rawValue)", forKey: provider.storageKey)
    }

    let result = AgentRuntimeProcess.usableBYOKEnvironment()

    XCTAssertEqual(result.values[AgentRuntimeProcess.byokEnvironmentKey(for: .openai)], "sk-agent-openai")
    XCTAssertEqual(result.values[AgentRuntimeProcess.byokEnvironmentKey(for: .anthropic)], "sk-agent-anthropic")
    XCTAssertEqual(result.values[AgentRuntimeProcess.byokEnvironmentKey(for: .gemini)], "sk-agent-gemini")
    XCTAssertEqual(result.values[AgentRuntimeProcess.byokEnvironmentKey(for: .deepgram)], "sk-agent-deepgram")
    XCTAssertTrue(result.suppressedProviders.isEmpty)
  }

  func testRemoveInheritedByokEnvironmentScrubsPrefixCaseInsensitively() {
    var env = [
      "OMI_BYOK_OPENAI": "stale-openai",
      "omi_byok_experimental": "stale-experimental",
      "OmI_bYoK_LEGACY": "stale-legacy",
      "OMI_AUTH_TOKEN": "token",
      "PATH": "/usr/bin",
    ]

    AgentRuntimeProcess.removeInheritedBYOKEnvironment(from: &env)

    XCTAssertNil(env["OMI_BYOK_OPENAI"])
    XCTAssertNil(env["omi_byok_experimental"])
    XCTAssertNil(env["OmI_bYoK_LEGACY"])
    XCTAssertEqual(env["OMI_AUTH_TOKEN"], "token")
    XCTAssertEqual(env["PATH"], "/usr/bin")
  }

  func testPiMonoStartupRefreshesAuthTokenAndFiltersByokEnvironment() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("Self.removeInheritedBYOKEnvironment(from: &env)"))
    XCTAssertTrue(source.contains("let byok = await Self.usableBYOKEnvironment()"))
    XCTAssertTrue(source.contains("let forceRefreshToken = preferredAdapterId == .piMono && !DesktopLocalProfile.isEnabled"))
    XCTAssertTrue(source.contains("getIdToken(forceRefresh: forceRefreshToken)"))
    XCTAssertFalse(source.contains("log(\"AgentRuntimeProcess: pi-mono BYOK active, forwarding \\(BYOKProvider.allCases.count) user keys\")"))
    XCTAssertTrue(source.contains("forwarding \\(byok.values.count) usable user keys"))
  }

  func testOpenClawAdapterCommandUsesSiblingNodeWhenAvailable() throws {
    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("openclaw-command-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tempDir) }

    let nodePath = tempDir.appendingPathComponent("node").path
    let openClawPath = tempDir.appendingPathComponent("openclaw").path
    FileManager.default.createFile(atPath: nodePath, contents: Data("#!/bin/sh\n".utf8))
    FileManager.default.createFile(atPath: openClawPath, contents: Data("#!/usr/bin/env node\n".utf8))
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: nodePath)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: openClawPath)

    let command = AgentRuntimeProcess.openClawAdapterCommand(openClawPath: openClawPath)

    XCTAssertEqual(command, "'\(nodePath)' '\(openClawPath)' acp")
  }

  func testOpenClawAdapterCommandFallsBackToLauncherWithoutSiblingNode() throws {
    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("openclaw-command-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tempDir) }

    let openClawPath = tempDir.appendingPathComponent("openclaw").path
    FileManager.default.createFile(atPath: openClawPath, contents: Data("#!/usr/bin/env node\n".utf8))
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: openClawPath)

    let command = AgentRuntimeProcess.openClawAdapterCommand(openClawPath: openClawPath)

    XCTAssertEqual(command, "'\(openClawPath)' acp")
  }

  func testStdoutReaderIsEventDrivenInsteadOfDetachedAvailableDataLoop() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("handle.readabilityHandler = { [weak self] handle in"))
    // The implementation now uses a generation-guarded signature; match the current
    // function name without coupling the test to the exact parameter list.
    XCTAssertTrue(source.contains("func processStdoutData("))
    XCTAssertFalse(source.contains("Task.detached { [weak self] in"))
    XCTAssertFalse(source.contains("while !Task.isCancelled"))
  }

  func testFailedRuntimeStartCleansUpLatchedRunningState() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("cleanupFailedStart(process: proc, error: error)"))
    XCTAssertTrue(source.contains("isRunning = false"))
    XCTAssertTrue(source.contains("receivedInit = false"))
    XCTAssertTrue(source.contains("resumeInitContinuations(throwing: BridgeError.stopped)"))
  }

  func testSharedRestartIsBlockedWhileRequestsAreActive() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("guard activeRequests.isEmpty, activeControlRequests.isEmpty else"))
    XCTAssertTrue(source.contains("isRestarting = true"))
    XCTAssertTrue(source.contains("guard !isRestarting else"))
    XCTAssertTrue(source.contains("BridgeError.restarting"))
    XCTAssertTrue(source.contains("BridgeError.requestAlreadyActive"))
  }

  func testClientRegistrationWaitsForInitWhenProcessIsAlreadyRunning() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("if isRunning {\n      try await waitForInit(timeout: 30.0)\n      return\n    }"))
    XCTAssertTrue(source.contains("try await waitForInit(timeout: 30.0)"))
    XCTAssertTrue(source.contains("case .initMessage:"))
    XCTAssertTrue(source.contains("resolveInitContinuations()"))
  }

  func testAppSurfacesUseDirectControlToolOnly() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertFalse(source.contains("func requestScopedControlTool("))
    XCTAssertFalse(source.contains(#""type": "control_tool""#))
    XCTAssertTrue(source.contains("func directControlTool("))
    XCTAssertTrue(source.contains("activeControlRequests[requestKey]"))
    XCTAssertTrue(source.contains("completeControlRequest(message)"))
    XCTAssertTrue(source.contains("if !sent, let request = activeControlRequests.removeValue(forKey: requestKey)"))
    XCTAssertTrue(source.contains("failure.map(BridgeError.agentRuntimeFailure) ?? BridgeError.agentError(raw)"))
    XCTAssertTrue(source.contains(#"["failed", "timed_out", "orphaned"].contains(terminalStatus)"#))
  }

  func testDirectControlToolRequestsUseDedicatedSignedInOwnerEnvelope() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("func directControlTool("))
    XCTAssertTrue(source.contains("Agent control requires a signed-in owner"))
    XCTAssertTrue(source.contains("advertisedAgentControlTools.contains(name)"))
    XCTAssertTrue(source.contains("Agent runtime does not advertise direct control tool"))
    XCTAssertTrue(source.contains(#""type": "direct_control_tool""#))
    XCTAssertTrue(source.contains(#""ownerId": ownerId"#))
  }

  func testToolResultsEchoRequestScope() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("completeToolCall("))
    XCTAssertTrue(source.contains("requestId: request.requestId"))
    XCTAssertTrue(source.contains("clientId: request.clientId"))
    XCTAssertTrue(source.contains(#"if let requestId { payload["requestId"] = requestId }"#))
    XCTAssertTrue(source.contains(#"if let clientId { payload["clientId"] = clientId }"#))
  }

  func testStartupTimeoutResumesInitContinuations() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("resumeInitContinuations(throwing: BridgeError.timeout)"))
    XCTAssertFalse(source.contains("withThrowingTaskGroup(of: Void.self)"))
  }

  func testOutOfMemoryDiagnosticRequiresConfirmedRuntimeSignature() {
    XCTAssertTrue(
      AgentRuntimeProcess.isConfirmedOutOfMemoryDiagnostic(
        "FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory"
      )
    )
    XCTAssertTrue(
      AgentRuntimeProcess.isConfirmedOutOfMemoryDiagnostic(
        "FatalProcessOutOfMemory: Zone Allocation failed"
      )
    )
    XCTAssertTrue(
      AgentRuntimeProcess.isConfirmedOutOfMemoryDiagnostic(
        "Failed to reserve virtual memory for CodeRange"
      )
    )

    XCTAssertFalse(
      AgentRuntimeProcess.isConfirmedOutOfMemoryDiagnostic(
        "Provider returned: the requested model is out of memory for this prompt"
      )
    )
    XCTAssertFalse(
      AgentRuntimeProcess.isConfirmedOutOfMemoryDiagnostic(
        "The browser extension reported out of memory while reading a page"
      )
    )
  }

  func testRuntimeDoesNotTreatGenericAbortSignalsAsOutOfMemory() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("let likelyOOM = lastExitWasOOM || oomDiagnosticLatch.isConfirmed(generation: processGeneration)"))
    XCTAssertFalse(source.contains("exitCode == 134"))
    XCTAssertFalse(source.contains("exitCode == 133"))
  }

  func testStderrOutOfMemoryLatchIsSynchronousAndGenerationScoped() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("oomDiagnosticLatch.markIfConfirmed(text, generation: expectedGeneration)"))
    XCTAssertTrue(source.contains("private final class AgentRuntimeOOMDiagnosticLatch: @unchecked Sendable"))
    XCTAssertTrue(source.contains("guard self.generation == generation else { return }"))
    XCTAssertFalse(source.contains("Task { await self?.markOOM"))
  }

  func testIntentionalStopInvalidatesOldProcessGenerationBeforeTerminating() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("""
  private func stopProcess(resumeRequestsWith error: BridgeError) async {
    let proc = process
    processGeneration &+= 1
    lastExitWasOOM = false
    oomDiagnosticLatch.reset(generation: processGeneration)
"""))
  }
}
