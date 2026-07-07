import XCTest

@testable import Omi_Computer

final class AgentRuntimeProcessTests: XCTestCase {
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
    XCTAssertTrue(bridgeSource.contains("guard isPiMonoHarness else { return }"))
    XCTAssertFalse(bridgeSource.contains(#"harnessMode == "piMono""#))
  }

  func testNamedBundleStateDirectoriesAreIsolated() {
    let home = URL(fileURLWithPath: "/tmp/test-home")

    let first = AgentRuntimeProcess.defaultStateDirectory(
      bundleIdentifier: "com.omi.omi-ticket-five-a",
      homeDirectory: home
    )
    let second = AgentRuntimeProcess.defaultStateDirectory(
      bundleIdentifier: "com.omi.omi-ticket-five-b",
      homeDirectory: home
    )

    XCTAssertNotEqual(first, second)
    XCTAssertTrue(first.hasSuffix("AgentRuntime/com.omi.omi-ticket-five-a"))
    XCTAssertTrue(second.hasSuffix("AgentRuntime/com.omi.omi-ticket-five-b"))
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

    XCTAssertEqual(withAdapter.sessionId, "adapter-session")
    XCTAssertEqual(withoutAdapter.sessionId, "omi-session")
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
    // Discovery shares its search dirs with the detector and also scans the live PATH.
    XCTAssertTrue(source.contains("LocalAgentProviderDetector.adapterActivationSearchDirectories(homeDirectory: home)"))
    XCTAssertTrue(source.contains("existingPath.split(separator: \":\").map(String.init)"))
    XCTAssertTrue(source.contains("for path in pathDirs + sharedSearchDirs"))
    XCTAssertTrue(source.contains(#"env["PATH"] = pathElements.joined(separator: ":")"#))
    XCTAssertTrue(source.contains(#"env["OMI_OPENCLAW_ADAPTER_COMMAND"]"#))
    XCTAssertTrue(source.contains(#"env["OMI_HERMES_ADAPTER_COMMAND"]"#))
    XCTAssertTrue(source.contains(#"env["OMI_CODEX_ADAPTER_COMMAND"]"#))
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
