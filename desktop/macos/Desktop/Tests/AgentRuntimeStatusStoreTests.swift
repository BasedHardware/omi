import XCTest

@testable import Omi_Computer

@MainActor
final class AgentRuntimeStatusStoreTests: XCTestCase {
  override func setUp() async throws {
    try await super.setUp()
    AgentRuntimeStatusStore.shared.reset()
    TaskAgentStatusRegistry.shared.reset()
  }

  func testResultProjectionIndexesCanonicalSurfaceSessionAndRun() {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.taskChat(taskId: "task-1")
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"result","protocolVersion":2,"requestId":"req","sessionId":"ses-1","runId":"run-1","attemptId":"attempt-1","adapterSessionId":"native-1","terminalStatus":"succeeded","text":"done","costUsd":0.25,"inputTokens":10,"outputTokens":5}"#
    )!

    store.ingest(message: message, surface: surface)

    let projection = store.projection(for: surface)
    XCTAssertEqual(projection?.sessionId, "ses-1")
    XCTAssertEqual(projection?.runId, "run-1")
    XCTAssertEqual(projection?.attemptId, "attempt-1")
    XCTAssertEqual(projection?.adapterSessionId, "native-1")
    XCTAssertEqual(projection?.status, .succeeded)
    XCTAssertEqual(store.projection(for: surface)?.sessionId, "ses-1")
  }

  func testUnknownResultTerminalStatusFailsClosed() {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.workstream(workstreamId: "workstream-unknown")
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"result","protocolVersion":2,"requestId":"req","sessionId":"ses-1","runId":"run-1","attemptId":"attempt-1","terminalStatus":"future_terminal","text":"done"}"#
    )!

    store.ingest(message: message, surface: surface)

    XCTAssertEqual(store.projection(for: surface)?.status, .failed)
    XCTAssertEqual(
      store.projection(for: surface)?.errorMessage,
      "Agent returned an invalid terminal status")
  }

  func testCancelledResultNeverProjectsSuccess() {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.workstream(workstreamId: "workstream-cancelled")
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"result","protocolVersion":2,"requestId":"req","sessionId":"ses-1","runId":"run-1","attemptId":"attempt-1","terminalStatus":"cancelled","text":"stopped"}"#
    )!

    store.ingest(message: message, surface: surface)

    XCTAssertEqual(store.projection(for: surface)?.status, .cancelled)
    XCTAssertNotEqual(store.projection(for: surface)?.status, .succeeded)
  }

  func testPresentationStartDoesNotFabricateTerminalSuccess() {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.floatingPill(pillId: UUID())

    store.beginRequest(surface: surface)
    store.updateActivity(surface: surface, statusText: "Searching")

    let projection = store.projection(for: surface)
    XCTAssertEqual(projection?.status, .running)
    XCTAssertFalse(projection?.status.isTerminal ?? true)
    XCTAssertNil(projection?.completedAt)
  }

  func testRestoresActiveWorkstreamRunFromKernelSnapshot() {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.workstream(workstreamId: "workstream-1")
    let updatedAt = Date(timeIntervalSince1970: 1_700_000_000)

    store.restoreKernelProjection(
      surface: surface,
      sessionId: "sess-workstream",
      runId: "run-workstream",
      status: .running,
      statusText: "Revising draft",
      errorMessage: nil,
      updatedAt: updatedAt,
      completedAt: nil
    )

    let projection = store.projection(for: surface)
    XCTAssertEqual(projection?.sessionId, "sess-workstream")
    XCTAssertEqual(projection?.runId, "run-workstream")
    XCTAssertEqual(projection?.status, .running)
    XCTAssertEqual(projection?.statusText, "Revising draft")
    XCTAssertEqual(projection?.updatedAt, updatedAt)
    XCTAssertNil(projection?.completedAt)
  }

  func testErrorProjectionUsesStructuredFailure() {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.floatingPill(pillId: UUID())
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"error","protocolVersion":2,"requestId":"req","sessionId":"ses-failed","runId":"run-failed","attemptId":"attempt-failed","message":"legacy text","failure":{"code":"adapter_process_exited","source":"adapter_process","adapterId":"openclaw","provider":"openai","retryable":true,"userMessage":"OpenClaw failed: OpenAI API error: upstream unavailable","technicalMessage":"OpenAI API error: upstream unavailable"}}"#
    )!

    store.ingest(message: message, surface: surface)

    let projection = store.projection(for: surface)
    XCTAssertEqual(projection?.status, .failed)
    XCTAssertEqual(projection?.errorMessage, "OpenClaw failed: OpenAI API error: upstream unavailable")
    XCTAssertEqual(projection?.failure?.code, "adapter_process_exited")
    XCTAssertEqual(projection?.failure?.adapterId, "openclaw")
    XCTAssertEqual(projection?.failure?.provider, "openai")
    XCTAssertEqual(projection?.failure?.retryable, true)
  }

  func testUpdateActivityDoesNotReviveTerminalProjection() {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.taskChat(taskId: "task-terminal")
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"result","protocolVersion":2,"requestId":"req","sessionId":"ses-terminal","runId":"run-terminal","attemptId":"attempt-terminal","terminalStatus":"succeeded","text":"done"}"#
    )!
    store.ingest(message: message, surface: surface)

    store.updateActivity(surface: surface, statusText: "Responding...")

    let projection = store.projection(for: surface)
    XCTAssertEqual(projection?.status, .succeeded)
    // Terminal result text "done" is preserved; the late updateActivity is
    // correctly ignored because the projection is already terminal.
    XCTAssertEqual(projection?.statusText, "done")
    XCTAssertNotNil(projection?.completedAt)
  }

  func testLateRuntimeDeltaDoesNotReviveTerminalProjection() {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.floatingPill(pillId: UUID())
    let result = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"result","protocolVersion":2,"requestId":"req","sessionId":"ses-terminal","runId":"run-terminal","attemptId":"attempt-terminal","terminalStatus":"succeeded","text":"done"}"#
    )!
    let lateDelta = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"text_delta","protocolVersion":2,"requestId":"req","sessionId":"ses-terminal","runId":"run-terminal","attemptId":"attempt-terminal","delta":"late"}"#
    )!

    store.ingest(message: result, surface: surface)
    store.ingest(message: lateDelta, surface: surface)

    let projection = store.projection(for: surface)
    XCTAssertEqual(projection?.status, .succeeded)
    // Terminal result text "done" is preserved; the late text_delta is
    // correctly ignored because the projection is already terminal.
    XCTAssertEqual(projection?.statusText, "done")
    XCTAssertNotNil(projection?.completedAt)
  }

  func testBeginRequestStartsNewLifecycleAfterTerminalProjection() {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.floatingPill(pillId: UUID())
    let result = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"result","protocolVersion":2,"requestId":"req","sessionId":"ses-terminal","runId":"run-terminal","attemptId":"attempt-terminal","terminalStatus":"succeeded","text":"done"}"#
    )!

    store.ingest(message: result, surface: surface)
    store.beginRequest(surface: surface, statusText: "Working on follow-up...")

    let projection = store.projection(for: surface)
    XCTAssertEqual(projection?.status, .starting)
    XCTAssertEqual(projection?.statusText, "Working on follow-up...")
    XCTAssertNil(projection?.completedAt)
    XCTAssertNil(projection?.runId)
    XCTAssertEqual(projection?.sessionId, "ses-terminal")
  }

  func testTerminalResultPreservesResultStatusText() {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.floatingPill(pillId: UUID())
    store.beginRequest(surface: surface)
    store.updateActivity(surface: surface, statusText: "Working...")

    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"result","protocolVersion":2,"requestId":"req","sessionId":"ses-terminal","runId":"run-terminal","attemptId":"attempt-terminal","terminalStatus":"succeeded","text":"done"}"#
    )!
    store.ingest(message: message, surface: surface)

    let projection = store.projection(for: surface)
    XCTAssertEqual(projection?.status, .succeeded)
    // Terminal result text "done" replaces the stale running text "Working...".
    XCTAssertEqual(projection?.statusText, "done")
    XCTAssertNotNil(projection?.completedAt)
  }

  func testToolResultDisplayDoesNotSurfaceRawOutput() {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.floatingPill(pillId: UUID())
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"tool_result_display","protocolVersion":2,"requestId":"req","name":"Bash","output":"TOKEN=secret-value\n/private/tmp/user-file"}"#
    )!

    store.ingest(message: message, surface: surface)

    let projection = store.projection(for: surface)
    XCTAssertEqual(projection?.status, .running)
    XCTAssertEqual(projection?.statusText, "Running command")
    XCTAssertFalse(projection?.statusText?.contains("secret-value") ?? true)
  }

  func testToolResultDisplayDoesNotOverwriteCancellation() {
    let store = AgentRuntimeStatusStore()
    let surface = AgentSurfaceReference.floatingPill(pillId: UUID())
    let cancel = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"cancel_ack","protocolVersion":2,"requestId":"req","accepted":true}"#
    )!
    let resultDisplay = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"tool_result_display","protocolVersion":2,"requestId":"req","name":"Bash","output":"done"}"#
    )!

    store.ingest(message: cancel, surface: surface)
    store.ingest(message: resultDisplay, surface: surface)

    XCTAssertEqual(store.projection(for: surface)?.status, .cancelling)
  }

  func testTaskRegistryMarkCompletedDoesNotCreateSuccessWithoutRuntimeResult() throws {
    TaskAgentStatusRegistry.shared.registerTask(taskId: "task-no-result", title: "No Result")
    TaskAgentStatusRegistry.shared.markRunning(taskId: "task-no-result")
    TaskAgentStatusRegistry.shared.markCompleted(taskId: "task-no-result")

    let json = TaskAgentStatusRegistry.shared.snapshotJSON()
    let data = try XCTUnwrap(json.data(using: .utf8))
    let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(payload["task_agents"] as? [[String: Any]])
    let snapshot = try XCTUnwrap(snapshots.first)

    XCTAssertEqual(snapshot["taskId"] as? String, "task-no-result")
    XCTAssertEqual(snapshot["status"] as? String, "running")
  }

  func testTaskRegistryReportsCompletedOnlyFromRuntimeResult() throws {
    let surface = AgentSurfaceReference.taskChat(taskId: "task-result")
    TaskAgentStatusRegistry.shared.registerTask(taskId: "task-result", title: "Runtime Result")
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"result","protocolVersion":2,"requestId":"req","sessionId":"ses-2","runId":"run-2","attemptId":"attempt-2","terminalStatus":"succeeded","text":"done"}"#
    )!
    AgentRuntimeStatusStore.shared.ingest(message: message, surface: surface)

    let json = TaskAgentStatusRegistry.shared.snapshotJSON()
    let data = try XCTUnwrap(json.data(using: .utf8))
    let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(payload["task_agents"] as? [[String: Any]])
    let snapshot = try XCTUnwrap(snapshots.first)

    XCTAssertEqual(snapshot["taskId"] as? String, "task-result")
    XCTAssertEqual(snapshot["status"] as? String, "completed")
  }

  func testStableSurfaceReferenceReusesKnownOmiSessionId() {
    let store = AgentRuntimeStatusStore()
    let firstOpen = AgentSurfaceReference.mainChat(chatId: "backend-chat-1")
    let reopened = AgentSurfaceReference.mainChat(chatId: "backend-chat-1")
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"result","protocolVersion":2,"requestId":"req","sessionId":"ses-main","runId":"run-main","attemptId":"attempt-main","terminalStatus":"succeeded","text":"done"}"#
    )!

    store.ingest(message: message, surface: firstOpen)

    XCTAssertEqual(firstOpen, reopened)
    XCTAssertEqual(store.projection(for: reopened)?.sessionId, "ses-main")
  }
}
