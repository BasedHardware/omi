import XCTest

@testable import Omi_Computer

@MainActor
final class AgentRuntimeStatusStoreTests: XCTestCase {
  override func setUp() {
    super.setUp()
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
    XCTAssertEqual(store.knownSessionId(for: surface), "ses-1")
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
    XCTAssertEqual(store.knownSessionId(for: reopened), "ses-main")
  }
}
