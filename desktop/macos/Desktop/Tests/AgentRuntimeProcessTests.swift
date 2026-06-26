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

  func testControlToolRequestsAreRequestScopedAndOwnerGuarded() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("func requestScopedControlTool("))
    XCTAssertTrue(source.contains(#""type": "control_tool""#))
    XCTAssertTrue(source.contains("App surfaces should use directControlTool"))
    XCTAssertTrue(source.contains("activeControlRequests[requestKey]"))
    XCTAssertTrue(source.contains(#"dict["ownerId"] = ownerId"#))
    XCTAssertTrue(source.contains("completeControlRequest(message)"))
    XCTAssertTrue(source.contains("if !sent, let request = activeControlRequests.removeValue(forKey: requestKey)"))
    XCTAssertTrue(source.contains("controlRequest.continuation.resume(throwing: BridgeError.agentError(raw))"))
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

    XCTAssertTrue(source.contains("completeToolCall(callId: callId, result: result, requestId: request.requestId, clientId: request.clientId)"))
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
}
