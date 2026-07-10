import XCTest

@testable import Omi_Computer

private func scenario13Detail() -> OmiAPI.WorkstreamDetailProjection {
  let evidence = OmiAPI.EvidenceRef(
    deviceId: nil,
    excerptHash: nil,
    id: "conversation-friday",
    kind: .conversation,
    scope: .canonical,
    version: "conversation.v1"
  )
  let v1 = OmiAPI.ArtifactDescriptor(
    artifactId: "artifact-email-v1",
    contentHash: "sha256:scenario13-email-v1",
    createdAt: "2026-07-09T11:00:00Z",
    evidenceEventIds: [],
    evidenceRefs: [evidence],
    kind: "email_draft",
    logicalKey: "launch-email",
    sourceRunId: nil,
    status: .superseded,
    supersedesArtifactId: nil,
    uri: "file:///tmp/omi-scenario-13-email-v1.md",
    version: 1,
    workstreamId: TaskThreadScenario13Fixture.workstreamID
  )
  let v2 = OmiAPI.ArtifactDescriptor(
    artifactId: "artifact-email-v2",
    contentHash: "sha256:scenario13-email-v2",
    createdAt: "2026-07-09T12:00:00Z",
    evidenceEventIds: ["event-friday"],
    evidenceRefs: [evidence],
    kind: "email_draft",
    logicalKey: "launch-email",
    sourceRunId: nil,
    status: .awaiting_review,
    supersedesArtifactId: v1.artifactId,
    uri: "file:///tmp/omi-scenario-13-email-v2.md",
    version: 2,
    workstreamId: TaskThreadScenario13Fixture.workstreamID
  )
  return TaskThreadScenario13Fixture.detail(artifacts: [v1, v2])
}

private actor FakeTaskWorkstreamAPI: TaskWorkstreamAPI {
  private(set) var taskIntentCalls: [(String, String, Int)] = []
  private(set) var taskIntentBodies: [(String?, String?)] = []
  private(set) var goalIntentCalls: [(String, String, Int)] = []
  var generation: Int? = 9

  func workflowControl() async throws -> OmiAPI.TaskWorkflowControl {
    OmiAPI.TaskWorkflowControl(accountGeneration: generation, workflowMode: .read)
  }

  func resolveTaskIntent(
    taskId: String,
    title: String?,
    objective: String?,
    idempotencyKey: String,
    accountGeneration: Int
  ) async throws -> OmiAPI.WorkIntentReceipt {
    taskIntentCalls.append((taskId, idempotencyKey, accountGeneration))
    taskIntentBodies.append((title, objective))
    return OmiAPI.WorkIntentReceipt(
      createdAt: "2026-07-09T10:00:00Z",
      goalId: nil,
      newlyCreated: taskIntentCalls.count == 1,
      receiptId: "receipt-task",
      taskId: taskId,
      workstreamId: TaskThreadScenario13Fixture.workstreamID
    )
  }

  func resolveGoalIntent(
    goalId: String,
    title: String,
    objective: String,
    anchorTaskDescription: String,
    idempotencyKey: String,
    accountGeneration: Int
  ) async throws -> OmiAPI.WorkIntentReceipt {
    goalIntentCalls.append((goalId, idempotencyKey, accountGeneration))
    return OmiAPI.WorkIntentReceipt(
      createdAt: "2026-07-09T10:00:00Z",
      goalId: goalId,
      newlyCreated: true,
      receiptId: "receipt-goal",
      taskId: "goal-anchor-task",
      workstreamId: TaskThreadScenario13Fixture.workstreamID
    )
  }

  func detail(workstreamId: String) async throws -> OmiAPI.WorkstreamDetailProjection {
    scenario13Detail()
  }
}

@MainActor
final class TaskThreadProjectionTests: XCTestCase {
  func testTwoTaskScopesKeepOneWorkstreamAndArtifactIdentity() {
    let detail = scenario13Detail()
    let first = TaskThreadProjection(detail: detail, activeTaskID: TaskThreadScenario13Fixture.firstTaskID)
    let second = first.selecting(taskID: TaskThreadScenario13Fixture.secondTaskID)

    XCTAssertEqual(first.workstreamID, second.workstreamID)
    XCTAssertNotEqual(first.activeTaskID, second.activeTaskID)
    XCTAssertEqual(first.artifactVersions.map(\.artifactId), second.artifactVersions.map(\.artifactId))
    XCTAssertEqual(first.artifactVersions.map(\.version), [2, 1])
    XCTAssertEqual(first.artifactHeads.map(\.version), [2])
    XCTAssertEqual(first.artifactVersions.first?.evidenceRefs?.first?.id, "conversation-friday")
  }

  func testContextPacketIsBoundedMinimizedAndSelectsCurrentTask() throws {
    let projection = TaskThreadProjection(
      detail: scenario13Detail(),
      activeTaskID: TaskThreadScenario13Fixture.secondTaskID
    )
    let encoded = try XCTUnwrap(TaskThreadContextPacket.encode(projection))
    let data = try XCTUnwrap(encoded.data(using: .utf8))
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let currentTask = try XCTUnwrap(json["current_task"] as? [String: Any])

    XCTAssertEqual(json["schema_version"] as? Int, 1)
    XCTAssertEqual(currentTask["id"] as? String, TaskThreadScenario13Fixture.secondTaskID)
    XCTAssertEqual((json["artifact_heads"] as? [[String: Any]])?.count, 1)
    XCTAssertNil(json["transcript"])
    XCTAssertNil(json["messages"])
    XCTAssertNil(json["run_status"])
    XCTAssertFalse(encoded.contains("Agent output so far"))
    XCTAssertFalse(encoded.contains("Confidential acquisition detail"))
    XCTAssertTrue(encoded.contains("Sensitive update omitted"))
  }

  func testLightweightOpenDoesNotCreateDurableWorkstream() async {
    let api = FakeTaskWorkstreamAPI()
    let coordinator = TaskChatCoordinator(
      chatProvider: ChatProvider(),
      workstreamAPI: api,
      persistWorkstreamLink: { _, _ in }
    )
    let task = TaskActionItem(
      id: "lightweight-task",
      description: "What is the status?",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 0)
    )

    do {
      _ = try await coordinator.resolveWorkstreamId(for: task, createIfNeeded: false)
      XCTFail("A lightweight open must not create durable product state")
    } catch TaskThreadError.taskIsUnlinked {
      // Expected.
    } catch {
      XCTFail("Unexpected error: \(error)")
    }
    let calls = await api.taskIntentCalls
    XCTAssertEqual(calls.count, 0)
  }

  func testExplicitTaskIntentIsStableAndIdempotent() async throws {
    let api = FakeTaskWorkstreamAPI()
    var persistedLinks: [(String, String)] = []
    let coordinator = TaskChatCoordinator(
      chatProvider: ChatProvider(),
      workstreamAPI: api,
      persistWorkstreamLink: { taskId, workstreamId in
        persistedLinks.append((taskId, workstreamId))
      }
    )
    let task = TaskActionItem(
      id: "unlinked-task",
      description: "Draft launch email",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 0)
    )

    let first = try await coordinator.resolveWorkstreamId(for: task, createIfNeeded: true)
    let second = try await coordinator.resolveWorkstreamId(for: task, createIfNeeded: true)
    let calls = await api.taskIntentCalls
    let bodies = await api.taskIntentBodies

    XCTAssertEqual(first, second)
    XCTAssertEqual(calls.count, 1)
    XCTAssertEqual(calls.first?.1, "work-intent:task:unlinked-task")
    XCTAssertEqual(calls.first?.2, 9)
    XCTAssertNil(bodies.first?.0)
    XCTAssertNil(bodies.first?.1)
    XCTAssertEqual(persistedLinks.first?.0, "unlinked-task")
    XCTAssertEqual(persistedLinks.first?.1, first)
  }

  func testGoalOriginUsesAnchorIntentAndStableIdentity() async throws {
    let api = FakeTaskWorkstreamAPI()
    let coordinator = TaskChatCoordinator(
      chatProvider: ChatProvider(),
      workstreamAPI: api,
      persistWorkstreamLink: { _, _ in }
    )

    let receipt = try await coordinator.resolveGoalOrigin(
      goalId: "goal-launch",
      occurrenceId: "occurrence-1",
      title: "Launch",
      objective: "Ship the launch",
      anchorTaskDescription: "Draft launch email"
    )
    let calls = await api.goalIntentCalls

    XCTAssertEqual(receipt.taskId, "goal-anchor-task")
    XCTAssertEqual(calls.count, 1)
    XCTAssertEqual(calls.first?.1, "work-intent:goal:goal-launch:occurrence-1")
    XCTAssertEqual(calls.first?.2, 9)
  }

  func testDashboardResumeSelectsTheExactPreferredTask() async throws {
    let coordinator = TaskChatCoordinator(
      chatProvider: ChatProvider(),
      workstreamAPI: FakeTaskWorkstreamAPI(),
      persistWorkstreamLink: { _, _ in }
    )

    let selected = try await coordinator.existingThreadTask(
      workstreamID: TaskThreadScenario13Fixture.workstreamID,
      preferredTaskID: TaskThreadScenario13Fixture.secondTaskID
    )

    XCTAssertEqual(selected.id, TaskThreadScenario13Fixture.secondTaskID)
    XCTAssertEqual(selected.workstreamId, TaskThreadScenario13Fixture.workstreamID)
  }

  func testDashboardResumeFailsWhenPreferredTaskIsMissing() async {
    let coordinator = TaskChatCoordinator(
      chatProvider: ChatProvider(),
      workstreamAPI: FakeTaskWorkstreamAPI(),
      persistWorkstreamLink: { _, _ in }
    )

    let opened = await coordinator.openExistingThread(
      workstreamID: TaskThreadScenario13Fixture.workstreamID,
      preferredTaskID: "missing-task"
    )

    XCTAssertFalse(opened)
    XCTAssertNil(coordinator.activeTaskId)
    XCTAssertEqual(coordinator.errorMessage, "The requested task is no longer part of this thread.")
  }

  func testRuntimeSurfaceUsesWorkstreamAuthority() {
    let surface = AgentSurfaceReference.workstream(workstreamId: "ws-1")
    XCTAssertEqual(surface.surfaceKind, "workstream")
    XCTAssertEqual(surface.externalRefKind, "workstream")
    XCTAssertEqual(surface.externalRefId, "ws-1")
  }

  func testScenarioFixtureProjectsRestartStableIdentityAndCitedV2() {
    let firstLaunch = scenario13Detail()
    let restartedLaunch = scenario13Detail()
    XCTAssertEqual(firstLaunch.workstream.workstreamId, restartedLaunch.workstream.workstreamId)
    XCTAssertEqual(firstLaunch.artifacts.count, 2)
    XCTAssertFalse(restartedLaunch.artifacts.first(where: { $0.version == 2 })?.evidenceRefs?.isEmpty ?? true)
  }

  func testCanonicalPromptDoesNotReadLegacyTmuxOutput() {
    let task = TaskActionItem(
      id: "task-1",
      description: "Draft launch email",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 0)
    )
    let prompt = TaskAgentSettings.shared.buildCanonicalTaskPrompt(for: task)
    XCTAssertFalse(prompt.contains("Agent output so far"))
  }
}
