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

  func workflowControl(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.TaskWorkflowControl {
    OmiAPI.TaskWorkflowControl(accountGeneration: generation, workflowMode: .read)
  }

  func resolveTaskIntent(
    taskId: String,
    title: String?,
    objective: String?,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
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
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
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

  func detail(
    workstreamId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkstreamDetailProjection {
    scenario13Detail()
  }
}

private actor SuspendedTaskWorkstreamAPI: TaskWorkstreamAPI {
  private var detailStarted = false
  private var detailReleased = false

  func waitUntilDetailStarted() async {
    while !detailStarted { await Task.yield() }
  }

  func releaseDetail() {
    detailReleased = true
  }

  func workflowControl(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.TaskWorkflowControl {
    OmiAPI.TaskWorkflowControl(accountGeneration: 9, workflowMode: .read)
  }

  func resolveTaskIntent(
    taskId: String,
    title: String?,
    objective: String?,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkIntentReceipt {
    OmiAPI.WorkIntentReceipt(
      createdAt: "2026-07-09T10:00:00Z",
      goalId: nil,
      newlyCreated: false,
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
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkIntentReceipt {
    OmiAPI.WorkIntentReceipt(
      createdAt: "2026-07-09T10:00:00Z",
      goalId: goalId,
      newlyCreated: false,
      receiptId: "receipt-goal",
      taskId: "goal-anchor-task",
      workstreamId: TaskThreadScenario13Fixture.workstreamID
    )
  }

  func detail(
    workstreamId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkstreamDetailProjection {
    detailStarted = true
    while !detailReleased { await Task.yield() }
    return scenario13Detail()
  }
}

private actor SuspendedTaskIntentAPI: TaskWorkstreamAPI {
  private var intentStarted = false
  private var intentReleased = false
  private(set) var remoteMutationCount = 0

  func waitUntilIntentStarted() async {
    while !intentStarted { await Task.yield() }
  }

  func releaseIntent() { intentReleased = true }

  func workflowControl(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.TaskWorkflowControl {
    OmiAPI.TaskWorkflowControl(accountGeneration: 9, workflowMode: .read)
  }

  func resolveTaskIntent(
    taskId: String,
    title: String?,
    objective: String?,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkIntentReceipt {
    intentStarted = true
    while !intentReleased { await Task.yield() }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw LocalMutationAuthorizationError.revoked
    }
    remoteMutationCount += 1
    return OmiAPI.WorkIntentReceipt(
      createdAt: "2026-07-09T10:00:00Z",
      goalId: nil,
      newlyCreated: true,
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
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkIntentReceipt {
    throw TaskThreadError.unresolvedWorkflowControl
  }

  func detail(
    workstreamId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkstreamDetailProjection {
    scenario13Detail()
  }
}

private actor SuspendedTaskJournalPage {
  private var started = false
  private var released = false

  func fetch(_ page: AgentRuntimeProcess.JournalOperationResult) async
    -> AgentRuntimeProcess.JournalOperationResult
  {
    started = true
    while !released { await Task.yield() }
    return page
  }

  func waitUntilStarted() async {
    while !started { await Task.yield() }
  }

  func release() {
    released = true
  }
}

private actor SuspendedTaskLinkCommit {
  private var started = false
  private var released = false

  func pause() async {
    started = true
    while !released { await Task.yield() }
  }

  func waitUntilStarted() async {
    while !started { await Task.yield() }
  }

  func release() {
    released = true
  }
}

@MainActor
private final class TaskChatOwnerBox {
  var value: String?

  init(_ value: String?) {
    self.value = value
  }
}

@MainActor
final class TaskThreadProjectionTests: XCTestCase {
  private var previousOwnerID: String?

  override func setUp() async throws {
    try await super.setUp()
    previousOwnerID = RuntimeOwnerIdentity.currentOwnerId()
    await transitionOwner(to: "owner-a")
  }

  override func tearDown() async throws {
    await transitionOwner(to: previousOwnerID)
    try await super.tearDown()
  }

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
      persistWorkstreamLink: { _, _, _, _ in }
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
      persistWorkstreamLink: { taskId, workstreamId, ownerID, _ in
        XCTAssertFalse(ownerID.isEmpty)
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

  func testSuspendedWorkstreamLinkCommitCannotCrossOwnerTransition() async {
    let gate = SuspendedTaskLinkCommit()
    var committedLinks: [(String, String)] = []
    let coordinator = TaskChatCoordinator(
      chatProvider: ChatProvider(),
      workstreamAPI: FakeTaskWorkstreamAPI(),
      persistWorkstreamLink: { taskID, workstreamID, ownerID, authorization in
        XCTAssertEqual(ownerID, "owner-a")
        await gate.pause()
        guard (try? authorization.require()) != nil else { return }
        committedLinks.append((taskID, workstreamID))
      }
    )
    let task = TaskActionItem(
      id: "owner-a-link",
      description: "Do not persist across owners",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 0)
    )

    let resolve = Task { @MainActor in
      try? await coordinator.resolveWorkstreamId(for: task, createIfNeeded: true)
    }
    await gate.waitUntilStarted()
    await transitionOwner(to: "owner-b")
    await gate.release()
    let resolved = await resolve.value

    XCTAssertNil(resolved)
    XCTAssertTrue(committedLinks.isEmpty)
    XCTAssertEqual(coordinator.ownerProjectionSnapshot.taskMappingCount, 0)
  }

  func testSuspendedOwnerATaskIntentCannotMutateRemoteStateUnderOwnerB() async {
    let api = SuspendedTaskIntentAPI()
    var persistedLinks = 0
    let coordinator = TaskChatCoordinator(
      chatProvider: ChatProvider(),
      workstreamAPI: api,
      persistWorkstreamLink: { _, _, _, _ in persistedLinks += 1 }
    )
    let task = TaskActionItem(
      id: "owner-a-remote-intent",
      description: "Never create this under owner B",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 0)
    )

    let resolve = Task { @MainActor in
      try? await coordinator.resolveWorkstreamId(for: task, createIfNeeded: true)
    }
    await api.waitUntilIntentStarted()
    await transitionOwner(to: "owner-b")
    await api.releaseIntent()
    let result = await resolve.value
    let mutations = await api.remoteMutationCount

    XCTAssertNil(result)
    XCTAssertEqual(mutations, 0)
    XCTAssertEqual(persistedLinks, 0)
    XCTAssertEqual(coordinator.ownerProjectionSnapshot.taskMappingCount, 0)
  }

  func testGoalOriginUsesAnchorIntentAndStableIdentity() async throws {
    let api = FakeTaskWorkstreamAPI()
    let coordinator = TaskChatCoordinator(
      chatProvider: ChatProvider(),
      workstreamAPI: api,
      persistWorkstreamLink: { _, _, _, _ in }
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
      persistWorkstreamLink: { _, _, _, _ in }
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
      persistWorkstreamLink: { _, _, _, _ in }
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

  func testTaskRuntimeKeepsBridgePreferenceSeparateFromAskActRunMode() throws {
    let routing = try TaskChatRuntime.queryRouting(
      bridgePreference: "hermes",
      runMode: "ask",
      workspacePath: "/tmp/task-runtime"
    )

    XCTAssertEqual(routing.adapterId, AgentRuntimeProcess.adapterId(forHarnessMode: "hermes"))
    XCTAssertNil(routing.modelProfile)
    XCTAssertEqual(routing.workingDirectory, "/tmp/task-runtime")
    XCTAssertEqual(routing.runMode, "ask")
  }

  func testTaskChatAtomicAdmissionRejectsBothVisibleRowsTogether() async {
    let owner = TaskChatOwnerBox("owner-a")
    var capturedWrites: [KernelJournalTurnWrite] = []
    let state = TaskChatState(
      taskId: "task-atomic",
      workstreamId: "workstream-atomic-\(UUID().uuidString)",
      workspacePath: "/tmp",
      ownerIDProvider: { owner.value },
      recordJournalExchangeOperation: { _, requestedOwner, authorizationSnapshot, writes in
        XCTAssertEqual(requestedOwner, "owner-a")
        XCTAssertTrue(RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot))
        capturedWrites = writes
        throw BridgeError.agentError("second exchange turn identity collision")
      }
    )

    await state.sendMessage("Keep both halves atomic")

    XCTAssertEqual(capturedWrites.map(\.role), ["user", "assistant"])
    XCTAssertEqual(capturedWrites.map(\.status), [.completed, .streaming])
    XCTAssertEqual(capturedWrites.last?.content, "")
    XCTAssertTrue(state.messages.isEmpty)
    XCTAssertFalse(state.isSending)
    XCTAssertEqual(state.errorMessage, "Could not save this message. Try again.")
  }

  func testSuspendedOwnerAJournalPageCannotPublishAfterInvalidation() async throws {
    let owner = TaskChatOwnerBox("owner-a")
    let gate = SuspendedTaskJournalPage()
    let surface = AgentSurfaceReference.workstream(workstreamId: "workstream-owner-bound")
    let ownerATurn = try XCTUnwrap(KernelJournalTurn(
      dictionary: [
        "conversationId": "conversation-owner-a",
        "turnId": "owner-a-private-turn",
        "turnSeq": 1,
        "conversationGeneration": 1,
        "generationBaseTurnSeq": 0,
        "producerId": "producer-owner-a",
        "payloadHash": "sha256:owner-a",
        "role": "user",
        "surfaceKind": surface.surfaceKind,
        "externalRefKind": surface.externalRefKind,
        "externalRefId": surface.externalRefId,
        "content": "Owner A private task chat",
        "origin": "workstream",
        "status": "completed",
        "contentBlocks": [],
        "resources": [],
        "metadataJson": "{}",
        "createdAtMs": 1,
        "updatedAtMs": 1,
      ]
    ))
    let page = AgentRuntimeProcess.JournalOperationResult(
      operation: "list",
      conversationId: "conversation-owner-a",
      turn: nil,
      turns: [ownerATurn],
      clearedCount: 0,
      highWaterTurnSeq: 1,
      conversationGeneration: 1,
      generationBaseTurnSeq: 0
    )
    let state = TaskChatState(
      taskId: "task-owner-a",
      workstreamId: surface.externalRefId,
      workspacePath: "/tmp",
      ownerIDProvider: { owner.value },
      attachJournalEventsOperation: { _, _, _ in UUID() },
      listJournalTurnsOperation: { _, requestedOwner, _, _, _ in
        XCTAssertEqual(requestedOwner, "owner-a")
        return await gate.fetch(page)
      }
    )

    let load = Task { @MainActor in await state.loadPersistedMessages() }
    await gate.waitUntilStarted()
    owner.value = "owner-b"
    state.invalidateOwnerState()
    await gate.release()
    await load.value

    XCTAssertTrue(state.ownerProjectionIsEmpty)
    XCTAssertTrue(state.messages.isEmpty)
  }

  func testOwnerNotificationPurgesAndFencesSuspendedCoordinatorProjection() async {
    let owner = TaskChatOwnerBox("owner-a")
    let api = SuspendedTaskWorkstreamAPI()
    let coordinator = TaskChatCoordinator(
      chatProvider: ChatProvider(),
      workstreamAPI: api,
      ownerIDProvider: { owner.value },
      persistWorkstreamLink: { _, _, _, _ in }
    )
    coordinator.loadScenario13Fixture(
      activeTaskID: TaskThreadScenario13Fixture.firstTaskID,
      detail: scenario13Detail()
    )
    coordinator.activeTaskState?.messages = [
      ChatMessage(text: "Owner A private task chat", sender: .user)
    ]
    coordinator.streamingTaskIds = [TaskThreadScenario13Fixture.firstTaskID]
    coordinator.streamingStatuses[TaskThreadScenario13Fixture.firstTaskID] = "Working..."
    XCTAssertGreaterThan(coordinator.ownerProjectionSnapshot.stateCount, 0)
    XCTAssertGreaterThan(coordinator.ownerProjectionSnapshot.messageCount, 0)

    let suspendedOpen = Task { @MainActor in
      await coordinator.openExistingThread(
        workstreamID: TaskThreadScenario13Fixture.workstreamID,
        preferredTaskID: TaskThreadScenario13Fixture.secondTaskID
      )
    }
    await api.waitUntilDetailStarted()

    owner.value = "owner-b"
    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)

    XCTAssertEqual(
      coordinator.ownerProjectionSnapshot,
      .init(
        stateCount: 0,
        taskMappingCount: 0,
        workstreamMappingCount: 0,
        detailCount: 0,
        runtimeStatusCount: 0,
        messageCount: 0
      )
    )
    XCTAssertNil(coordinator.activeTaskState)
    XCTAssertNil(coordinator.activeThreadProjection)
    XCTAssertTrue(coordinator.streamingTaskIds.isEmpty)
    XCTAssertTrue(coordinator.streamingStatuses.isEmpty)

    await api.releaseDetail()
    let opened = await suspendedOpen.value
    XCTAssertFalse(opened)
    XCTAssertEqual(coordinator.ownerProjectionSnapshot.stateCount, 0)
    XCTAssertNil(coordinator.activeTaskId)
    XCTAssertNil(coordinator.activeWorkstreamId)
  }

  private func transitionOwner(to ownerID: String?) async {
    _ = await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      plannedNextOwner: { _, _ in ownerID },
      quiesceVoice: { _, _ in },
      retargetLocalStorage: { _, _ in },
      ownerDidChange: {
        await MainActor.run {
          NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
        }
      }
    ) { defaults in
      defaults.removeObject(forKey: .automationOwnerOverride)
      if let ownerID {
        defaults.set(ownerID, forKey: .authUserId)
      } else {
        defaults.removeObject(forKey: .authUserId)
      }
    }
  }
}
