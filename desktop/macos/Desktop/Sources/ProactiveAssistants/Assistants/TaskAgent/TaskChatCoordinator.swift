import Combine
import SwiftUI

/// Projects a selected task into its durable workstream conversation. The task
/// remains UI scope; kernel session, messages, artifacts, and runtime state are
/// keyed by workstream identity.
@MainActor
final class TaskChatCoordinator: ObservableObject {
  @Published var activeTaskId: String?
  @Published private(set) var activeWorkstreamId: String?
  @Published private(set) var activeThreadProjection: TaskThreadProjection?
  @Published var isPanelOpen = false
  @Published var isOpening = false
  @Published var errorMessage: String?
  @Published var pendingInputText = ""
  @Published var workspacePath: String = TaskAgentSettings.shared.workingDirectory

  private static let unreadTaskIdsKey = "taskChat.unreadTaskIds"

  @Published var streamingTaskIds: Set<String> = []
  @Published var unreadTaskIds: Set<String> = [] {
    didSet { UserDefaults.standard.set(Array(unreadTaskIds), forKey: Self.unreadTaskIdsKey) }
  }
  @Published var streamingStatuses: [String: String] = [:]
  @Published var activeTaskState: TaskChatState?

  private var workstreamStates: [String: TaskChatState] = [:]
  private var taskToWorkstream: [String: String] = [:]
  private var taskIdsByWorkstream: [String: Set<String>] = [:]
  private var detailByWorkstream: [String: OmiAPI.WorkstreamDetailProjection] = [:]
  private var runtimeStatusCancellable: AnyCancellable?
  private var lastRuntimeStatusByWorkstream: [String: AgentRunProjectionStatus] = [:]
  private var rehydratedWorkstreamIds: Set<String> = []

  private let chatProvider: ChatProvider
  private let workstreamAPI: any TaskWorkstreamAPI
  private let persistWorkstreamLink: @MainActor (String, String) async -> Void

  init(
    chatProvider: ChatProvider,
    workstreamAPI: any TaskWorkstreamAPI = LiveTaskWorkstreamAPI(),
    persistWorkstreamLink: @escaping @MainActor (String, String) async -> Void = { taskId, workstreamId in
      try? await ActionItemStorage.shared.updateActionItemFields(
        backendId: taskId,
        workstreamId: workstreamId
      )
    }
  ) {
    self.chatProvider = chatProvider
    self.workstreamAPI = workstreamAPI
    self.persistWorkstreamLink = persistWorkstreamLink
    if let saved = UserDefaults.standard.array(forKey: Self.unreadTaskIdsKey) as? [String] {
      unreadTaskIds = Set(saved)
    }
    runtimeStatusCancellable = AgentRuntimeStatusStore.shared.$projectionsBySurface
      .receive(on: DispatchQueue.main)
      .sink { [weak self] projections in
        self?.applyRuntimeProjections(projections)
      }
  }

  // MARK: - Public identity/actions

  /// Explicit user action behind “Work on this with Omi”. An unlinked task is
  /// allowed to create its durable workstream only through this method.
  func openChat(for task: TaskActionItem) async {
    await openThread(for: task, createIfNeeded: true)
  }

  /// Opens an existing linked thread without creating product state.
  @discardableResult
  func openExistingThread(for task: TaskActionItem) async -> Bool {
    guard let expectedWorkstreamId = task.workstreamId ?? taskToWorkstream[task.id] else { return false }
    await openThread(for: task, createIfNeeded: false)
    return activeTaskId == task.id && activeWorkstreamId == expectedWorkstreamId
  }

  func switchToTask(_ task: TaskActionItem) async {
    guard task.id != activeTaskId else { return }
    await openThread(for: task, createIfNeeded: false)
  }

  /// Ticket 11 consumes this hook; goals create an anchor task and thread through
  /// the same idempotent backend intent, never through a separate thread creator.
  func resolveGoalOrigin(
    goalId: String,
    occurrenceId: String,
    title: String,
    objective: String,
    anchorTaskDescription: String
  ) async throws -> OmiAPI.WorkIntentReceipt {
    let control = try await workstreamAPI.workflowControl()
    guard let generation = control.accountGeneration else {
      throw TaskThreadError.unresolvedWorkflowControl
    }
    return try await workstreamAPI.resolveGoalIntent(
      goalId: goalId,
      title: title,
      objective: objective,
      anchorTaskDescription: anchorTaskDescription,
      idempotencyKey: TaskWorkIntentIdentity.goal(goalId: goalId, occurrenceId: occurrenceId),
      accountGeneration: generation
    )
  }

  func refreshActiveThread() async {
    guard let workstreamId = activeWorkstreamId, let taskId = activeTaskId else { return }
    do {
      let detail = try await workstreamAPI.detail(workstreamId: workstreamId)
      register(detail: detail)
      activeThreadProjection = TaskThreadProjection(detail: detail, activeTaskID: taskId)
    } catch {
      errorMessage = error.localizedDescription
      logError("TaskChatCoordinator: Failed to refresh thread \(workstreamId)", error: error)
    }
  }

  var activeContextPacket: String? {
    activeThreadProjection.flatMap(TaskThreadContextPacket.encode)
  }

  func closeChat() {
    isPanelOpen = false
    activeTaskId = nil
    activeWorkstreamId = nil
    activeTaskState = nil
    activeThreadProjection = nil
    pendingInputText = ""
    errorMessage = nil
  }

  func markAsRead(_ taskId: String) {
    unreadTaskIds.remove(taskId)
  }

  /// Feeds canonical task/workstream links from the list projection into the
  /// coordinator before any thread is opened, then restores kernel run status.
  func ingestTaskMappings(_ tasks: [TaskActionItem]) {
    var newlyLinked: [String: [String]] = [:]
    for task in tasks {
      guard let workstreamId = task.workstreamId, !workstreamId.isEmpty else { continue }
      taskToWorkstream[task.id] = workstreamId
      taskIdsByWorkstream[workstreamId, default: []].insert(task.id)
      if !rehydratedWorkstreamIds.contains(workstreamId) {
        newlyLinked[workstreamId, default: []].append(task.id)
      }
    }
    applyRuntimeProjections(AgentRuntimeStatusStore.shared.projectionsBySurface)
    for (workstreamId, taskIds) in newlyLinked {
      rehydratedWorkstreamIds.insert(workstreamId)
      Task { @MainActor [weak self] in
        do {
          let prepareReceipt = try await TaskWorkstreamContinuity.prepare(
            workstreamId: workstreamId,
            taskIds: taskIds,
            checkpoints: []
          )
          if !prepareReceipt.deliveries.isEmpty {
            let detail = try await self?.workstreamAPI.detail(workstreamId: workstreamId)
            if let self, let detail {
              await self.deliverContinuity(prepareReceipt.deliveries, detail: detail)
            }
          }
        } catch {
          self?.rehydratedWorkstreamIds.remove(workstreamId)
          logError("TaskChatCoordinator: Failed to rehydrate workstream status \(workstreamId)", error: error)
        }
      }
    }
  }

  func purgeState(for taskId: String) {
    guard let workstreamId = taskToWorkstream.removeValue(forKey: taskId) else {
      unreadTaskIds.remove(taskId)
      return
    }
    taskIdsByWorkstream[workstreamId]?.remove(taskId)
    streamingTaskIds.remove(taskId)
    streamingStatuses.removeValue(forKey: taskId)
    unreadTaskIds.remove(taskId)
    if taskIdsByWorkstream[workstreamId]?.isEmpty != false {
      workstreamStates.removeValue(forKey: workstreamId)
      taskIdsByWorkstream.removeValue(forKey: workstreamId)
      detailByWorkstream.removeValue(forKey: workstreamId)
      lastRuntimeStatusByWorkstream.removeValue(forKey: workstreamId)
      rehydratedWorkstreamIds.remove(workstreamId)
    }
    if activeTaskId == taskId { closeChat() }
  }

  // MARK: - Background work

  func investigateInBackground(for task: TaskActionItem) async {
    await openThread(for: task, createIfNeeded: true, revealPanel: false)
    guard let state = activeTaskState, !state.isSending else { return }
    await state.sendMessage(
      TaskAgentSettings.shared.buildCanonicalTaskPrompt(for: task),
      taskContext: activeContextPacket
    )
    await refreshActiveThread()
  }

  // MARK: - Resolution

  private func openThread(
    for task: TaskActionItem,
    createIfNeeded: Bool,
    revealPanel: Bool = true
  ) async {
    guard !isOpening else { return }
    isOpening = true
    errorMessage = nil
    defer { isOpening = false }

    do {
      let workstreamId = try await resolveWorkstreamId(for: task, createIfNeeded: createIfNeeded)
      let detail = try await workstreamAPI.detail(workstreamId: workstreamId)
      let projection = TaskThreadProjection(detail: detail, activeTaskID: task.id)
      let prepareReceipt = try await TaskWorkstreamContinuity.prepare(
        workstreamId: workstreamId,
        taskIds: detail.tasks.map(\.id) + [task.id],
        checkpoints: detail.checkpoints
      )

      activeTaskId = task.id
      activeWorkstreamId = workstreamId
      activeThreadProjection = projection
      markAsRead(task.id)
      register(detail: detail)
      await deliverContinuity(prepareReceipt.deliveries, detail: detail)
      taskToWorkstream[task.id] = workstreamId
      taskIdsByWorkstream[workstreamId, default: []].insert(task.id)

      let state: TaskChatState
      if let existing = workstreamStates[workstreamId] {
        existing.selectTask(task.id)
        state = existing
      } else {
        let configuredPath = TaskAgentSettings.shared.workingDirectory
        let workspace = configuredPath.isEmpty
          ? FileManager.default.homeDirectoryForCurrentUser.path
          : configuredPath

        _ = try await TaskChatMessageStorage.shared.migrateLegacyMessages(
          fromTaskIds: detail.tasks.map(\.id) + [task.id],
          toWorkstreamId: workstreamId
        )
        let created = TaskChatState(
          taskId: task.id,
          workstreamId: workstreamId,
          workspacePath: workspace
        )
        created.systemPromptBuilder = { [weak self] in
          self?.chatProvider.buildTaskChatSystemPrompt() ?? ""
        }
        created.onQueryCompleted = { [weak self] result, chatMessageId in
          await self?.consumeCompletedQuery(
            result,
            workstreamId: workstreamId,
            chatMessageId: chatMessageId
          )
        }
        await created.loadPersistedMessages()
        try await TaskChatRuntime.importLegacyHistory(
          workstreamId: workstreamId,
          messages: created.messages
        )
        workstreamStates[workstreamId] = created
        state = created
      }

      activeTaskState = state
      pendingInputText = ""
      if revealPanel { isPanelOpen = true }
    } catch {
      errorMessage = error.localizedDescription
      if revealPanel {
        activeTaskId = nil
        activeWorkstreamId = nil
        activeThreadProjection = nil
        activeTaskState = nil
        isPanelOpen = true
      }
      logError("TaskChatCoordinator: Failed to open task-backed thread", error: error)
    }
  }

  func resolveWorkstreamId(
    for task: TaskActionItem,
    createIfNeeded: Bool
  ) async throws -> String {
    if let linked = task.workstreamId ?? taskToWorkstream[task.id] {
      return linked
    }
    guard createIfNeeded else { throw TaskThreadError.taskIsUnlinked }

    let control = try await workstreamAPI.workflowControl()
    guard let generation = control.accountGeneration else {
      throw TaskThreadError.unresolvedWorkflowControl
    }
    let receipt = try await workstreamAPI.resolveTaskIntent(
      taskId: task.id,
      // Task identity is the complete stable request. The backend derives the
      // current title/objective from the canonical task inside its transaction,
      // so an edit cannot poison an ambiguous-success retry.
      title: nil,
      objective: nil,
      idempotencyKey: TaskWorkIntentIdentity.task(taskId: task.id),
      accountGeneration: generation
    )
    taskToWorkstream[task.id] = receipt.workstreamId
    await persistWorkstreamLink(task.id, receipt.workstreamId)
    return receipt.workstreamId
  }

  /// Deterministic non-production projection used by the named scenario-13
  /// harness. It enters through the same coordinator/view state as live data;
  /// only the network fetch is replaced by the frozen fixture.
#if DEBUG
  func loadScenario13Fixture(
    activeTaskID: String,
    detail: OmiAPI.WorkstreamDetailProjection
  ) {
    let workstreamId = detail.workstream.workstreamId
    guard detail.tasks.contains(where: { $0.id == activeTaskID }) else { return }
    register(detail: detail)
    activeTaskId = activeTaskID
    activeWorkstreamId = workstreamId
    activeThreadProjection = TaskThreadProjection(detail: detail, activeTaskID: activeTaskID)
    let state = workstreamStates[workstreamId] ?? TaskChatState(
      taskId: activeTaskID,
      workstreamId: workstreamId,
      workspacePath: FileManager.default.homeDirectoryForCurrentUser.path
    )
    state.selectTask(activeTaskID)
    workstreamStates[workstreamId] = state
    activeTaskState = state
    errorMessage = nil
    isPanelOpen = true
  }

  func registerAutomationActions() {
    DesktopAutomationActionRegistry.shared.register(
      name: "task_thread_scenario_13",
      summary: "Exercise live task-backed thread continuity through the app kernel",
      params: ["task", "resume"]
    ) { [weak self] params in
      guard let self else { return ["error": "task thread coordinator unavailable"] }
      let activeTaskID = params["task"] == "second"
        ? TaskThreadScenario13Fixture.secondTaskID
        : TaskThreadScenario13Fixture.firstTaskID
      do {
        let runtime = try await self.buildScenario13RuntimeProjection(
          resumeOnly: params["resume"] == "true"
        )
        self.loadScenario13Fixture(activeTaskID: activeTaskID, detail: runtime.detail)
        TaskThreadScenario13HarnessWindow.show(coordinator: self)
        let projection = self.activeThreadProjection
        return [
          "workstream_id": projection?.workstreamID ?? "",
          "active_task_id": projection?.activeTaskID ?? "",
          "kernel_surface": "workstream",
          "artifact_versions": projection?.artifactVersions.map { "v\($0.version)" }.joined(separator: ",") ?? "",
          "cited_v2": projection?.artifactVersions.first(where: { $0.version == 2 })?.evidenceRefs?.isEmpty == false ? "true" : "false",
          "external_send_decision": runtime.externalSendDecision,
          "runtime_bridge": "live_app_kernel",
          "kernel_session_id": runtime.kernelSessionID,
        ]
      } catch {
        return ["error": String(describing: error)]
      }
    }
  }

  private func buildScenario13RuntimeProjection(resumeOnly: Bool) async throws -> (
    detail: OmiAPI.WorkstreamDetailProjection,
    externalSendDecision: String,
    kernelSessionID: String
  ) {
    let control: TaskWorkstreamContinuity.Control = { name, input in
      try await TaskChatRuntime.debugAutomationControlTool(name: name, input: input)
    }
    let versions: [TaskKernelArtifactVersion]
    if resumeOnly {
      let resumed = try await TaskWorkstreamContinuity.project(
        workstreamId: TaskThreadScenario13Fixture.workstreamID,
        control: control
      )
      guard resumed.agentSessionId != nil, resumed.artifactVersions.count >= 2 else {
        throw TaskWorkstreamContinuityError.missingRestartProjection
      }
      versions = resumed.artifactVersions
    } else {
      let base = TaskThreadScenario13Fixture.baseDetail
      _ = try await TaskWorkstreamContinuity.prepare(
        workstreamId: TaskThreadScenario13Fixture.workstreamID,
        taskIds: [TaskThreadScenario13Fixture.firstTaskID, TaskThreadScenario13Fixture.secondTaskID],
        checkpoints: [],
        control: control
      )
      let projection = TaskThreadProjection(
        detail: base,
        activeTaskID: TaskThreadScenario13Fixture.secondTaskID
      )
      let v1 = try await TaskWorkstreamContinuity.persist(
        workstream: projection,
        queryResult: scenario13QueryResult(version: 1),
        chatMessageId: "scenario-13-chat-v1",
        control: control
      )
      let v2 = try await TaskWorkstreamContinuity.persist(
        workstream: projection,
        queryResult: scenario13QueryResult(version: 2),
        chatMessageId: "scenario-13-chat-v2",
        control: control
      )
      versions = [v1.artifactVersions.first, v2.artifactVersions.first].compactMap { $0 }
    }
    let descriptors = versions.map { version in
      OmiAPI.ArtifactDescriptor(
        artifactId: version.artifact.artifactId,
        contentHash: version.artifact.contentHash ?? "sha256:scenario13-email-v\(version.version)",
        createdAt: version.version == 1 ? "2026-07-09T11:00:00Z" : "2026-07-09T12:00:00Z",
        evidenceEventIds: version.version == 1 ? [] : ["event-friday"],
        evidenceRefs: version.evidenceRefs,
        kind: version.artifact.kind,
        logicalKey: version.logicalKey,
        sourceRunId: nil,
        status: version.version == 1 ? .superseded : .awaiting_review,
        supersedesArtifactId: version.supersedesArtifactId,
        uri: version.artifact.uri,
        version: version.version,
        workstreamId: TaskThreadScenario13Fixture.workstreamID
      )
    }
    let policyRaw = try await control("evaluate_desktop_tool_policy", [
      "requestedBundles": ["external.write_send"],
      "selectedBundles": ["external.write_send"],
      "externalSend": true,
      "operation": "send_email",
      "resourceRef": "workstream:\(TaskThreadScenario13Fixture.workstreamID)",
    ])
    struct PolicyResponse: Decodable {
      struct Policy: Decodable { let decision: String }
      let ok: Bool
      let policy: Policy
    }
    let policy = try JSONDecoder().decode(PolicyResponse.self, from: Data(policyRaw.utf8))
    guard policy.ok else { throw TaskWorkstreamContinuityError.invalidRuntimeResponse }
    let kernelProjection = try await TaskWorkstreamContinuity.project(
      workstreamId: TaskThreadScenario13Fixture.workstreamID,
      control: control
    )
    guard let kernelSessionID = kernelProjection.agentSessionId else {
      throw TaskWorkstreamContinuityError.missingRestartProjection
    }
    return (
      TaskThreadScenario13Fixture.detail(artifacts: descriptors),
      policy.policy.decision,
      kernelSessionID
    )
  }

  private func scenario13QueryResult(version: Int) -> AgentBridge.QueryResult {
    let artifact = AgentArtifactProjection(
      artifactId: "scenario-13-source-v\(version)",
      sessionId: "scenario-13-source-session",
      runId: nil,
      attemptId: nil,
      kind: "email_draft",
      role: "result",
      uri: "file:///tmp/omi-scenario-13-email-v\(version).md",
      displayName: "launch-email",
      mimeType: "text/markdown",
      contentHash: "sha256:scenario13-email-v\(version)",
      sizeBytes: nil,
      lifecycleState: "retained",
      lifecycleUpdatedAtMs: nil,
      metadataRows: ["logicalKey: launch-email"],
      createdAtMs: nil
    )
    return AgentBridge.QueryResult.debugFixture(
      text: "Scenario artifact v\(version)",
      runId: "scenario-13-run-v\(version)",
      attemptId: "scenario-13-attempt-v\(version)",
      artifacts: [artifact]
    )
  }
#endif

  private func register(detail: OmiAPI.WorkstreamDetailProjection) {
    let workstreamId = detail.workstream.workstreamId
    detailByWorkstream[workstreamId] = detail
    let ids = Set(detail.tasks.map(\.id))
    taskIdsByWorkstream[workstreamId, default: []].formUnion(ids)
    for taskId in ids { taskToWorkstream[taskId] = workstreamId }
    applyRuntimeProjections(AgentRuntimeStatusStore.shared.projectionsBySurface)
  }

  private func consumeCompletedQuery(
    _ result: AgentBridge.QueryResult,
    workstreamId: String,
    chatMessageId: String
  ) async {
    guard let detail = detailByWorkstream[workstreamId] else { return }
    let selectedTaskId = activeWorkstreamId == workstreamId
      ? activeTaskId ?? detail.tasks.first?.id ?? ""
      : detail.tasks.first?.id ?? ""
    let projection = TaskThreadProjection(detail: detail, activeTaskID: selectedTaskId)
    do {
      let receipt = try await TaskWorkstreamContinuity.persist(
        workstream: projection,
        queryResult: result,
        chatMessageId: chatMessageId
      )
      await deliverContinuity(receipt.deliveries, detail: detail)
      await refreshActiveThread()
    } catch {
      errorMessage = "Reply complete, but thread continuity could not be saved. \(error.localizedDescription)"
      logError("TaskChatCoordinator: Failed to persist workstream continuity", error: error)
    }
  }

  private func deliverContinuity(
    _ deliveries: [TaskKernelDelivery],
    detail: OmiAPI.WorkstreamDetailProjection
  ) async {
    guard !deliveries.isEmpty else { return }
    let workstreamId = detail.workstream.workstreamId
    let generation: Int
    do {
      let control = try await workstreamAPI.workflowControl()
      guard let resolved = control.accountGeneration else {
        throw TaskThreadError.unresolvedWorkflowControl
      }
      generation = resolved
    } catch {
      for delivery in deliveries {
        try? await TaskWorkstreamContinuity.resolveDelivery(
          id: delivery.deliveryId,
          delivered: false,
          error: error
        )
      }
      logError("TaskChatCoordinator: Failed to resolve continuity delivery generation", error: error)
      return
    }

    var backendHeads = Dictionary(
      uniqueKeysWithValues: TaskThreadProjection(
        detail: detail,
        activeTaskID: detail.tasks.first?.id ?? ""
      ).artifactHeads.map { ($0.logicalKey, $0) }
    )
    var knownArtifacts = detail.artifacts
    let evidenceEventIds = detail.recentEvents
      .filter { $0.sensitivity == .normal && !($0.evidenceRefs ?? []).isEmpty }
      .map(\.eventId)

    for delivery in deliveries {
      do {
        switch delivery.payload.kind {
        case "artifact_descriptor":
          guard let logicalKey = delivery.payload.logicalKey,
            let artifactKind = delivery.payload.artifactKind,
            let uri = delivery.payload.uri,
            let contentHash = delivery.payload.contentHash,
            contentHash.count >= 16
          else {
            throw TaskWorkstreamContinuityError.invalidRuntimeResponse
          }
          if let existing = knownArtifacts.first(where: {
            $0.logicalKey == logicalKey && $0.contentHash == contentHash
          }) {
            if existing.version >= (backendHeads[logicalKey]?.version ?? 0) {
              backendHeads[logicalKey] = existing
            }
            try await TaskWorkstreamContinuity.resolveDelivery(
              id: delivery.deliveryId,
              delivered: true,
              receipt: [
                "artifact_id": existing.artifactId,
                "version": existing.version,
                "reconciled_after_ambiguous_success": true,
              ]
            )
            continue
          }
          let head = backendHeads[logicalKey]
          if head != nil, evidenceEventIds.isEmpty {
            throw TaskWorkstreamContinuityError.missingRevisionEvidence
          }
          let created = try await workstreamAPI.createArtifact(
            workstreamId: workstreamId,
            artifact: OmiAPI.ArtifactDescriptorCreate(
              contentHash: contentHash,
              evidenceEventIds: head == nil ? [] : evidenceEventIds,
              evidenceRefs: delivery.payload.evidenceRefs,
              kind: artifactKind,
              logicalKey: logicalKey,
              sourceRunId: delivery.payload.sourceRunId,
              supersedesArtifactId: head?.artifactId,
              uri: uri,
              version: (head?.version ?? 0) + 1
            ),
            idempotencyKey: delivery.deliveryId,
            accountGeneration: generation
          )
          backendHeads[logicalKey] = created
          knownArtifacts.append(created)
          try await TaskWorkstreamContinuity.resolveDelivery(
            id: delivery.deliveryId,
            delivered: true,
            receipt: ["artifact_id": created.artifactId, "version": created.version]
          )
        case "continuation_checkpoint":
          guard let checkpoint = delivery.payload.checkpoint else {
            throw TaskWorkstreamContinuityError.invalidRuntimeResponse
          }
          let saved = try await workstreamAPI.upsertCheckpoint(
            workstreamId: workstreamId,
            runtimeId: checkpoint.sourceRuntimeId,
            checkpoint: OmiAPI.ContinuationCheckpointUpsert(
              contextSummary: checkpoint.canonicalSummary,
              evidenceRefs: checkpoint.evidenceRefs,
              lastEventSequence: checkpoint.lastEventSequence,
              runtimeId: checkpoint.sourceRuntimeId
            ),
            idempotencyKey: delivery.deliveryId,
            accountGeneration: generation
          )
          try await TaskWorkstreamContinuity.resolveDelivery(
            id: delivery.deliveryId,
            delivered: true,
            receipt: ["checkpoint_id": saved.checkpointId]
          )
        default:
          throw TaskWorkstreamContinuityError.invalidRuntimeResponse
        }
      } catch {
        try? await TaskWorkstreamContinuity.resolveDelivery(
          id: delivery.deliveryId,
          delivered: false,
          error: error
        )
        logError("TaskChatCoordinator: Continuity delivery \(delivery.deliveryId) remains queued", error: error)
      }
    }
  }

  // MARK: - Runtime projection

  private func applyRuntimeProjections(_ projections: [String: AgentRunProjection]) {
    for (workstreamId, taskIds) in taskIdsByWorkstream {
      let surface = AgentSurfaceReference.workstream(workstreamId: workstreamId)
      guard let projection = projections[surface.key] else {
        streamingTaskIds.subtract(taskIds)
        for taskId in taskIds { streamingStatuses.removeValue(forKey: taskId) }
        continue
      }
      let previous = lastRuntimeStatusByWorkstream[workstreamId]
      lastRuntimeStatusByWorkstream[workstreamId] = projection.status
      if projection.status.isActive {
        streamingTaskIds.formUnion(taskIds)
        let status = projection.statusText ?? runtimeStatusLabel(projection.status)
        for taskId in taskIds { streamingStatuses[taskId] = status }
      } else {
        streamingTaskIds.subtract(taskIds)
        for taskId in taskIds { streamingStatuses.removeValue(forKey: taskId) }
        if previous?.isActive == true {
          if !isPanelOpen || activeWorkstreamId != workstreamId {
            unreadTaskIds.formUnion(taskIds)
          } else if let activeTaskId {
            unreadTaskIds.remove(activeTaskId)
          }
        }
      }
    }
  }

  private func runtimeStatusLabel(_ status: AgentRunProjectionStatus) -> String {
    switch status {
    case .queued, .starting: return "Starting..."
    case .waitingApproval: return "Needs approval"
    case .waitingInput: return "Needs input"
    case .cancelling: return "Stopping..."
    case .running: return "Working..."
    default: return ""
    }
  }
}

/// Non-production visual harness for scenario 13. Registration is gated by
/// DesktopAutomationLaunchOptions, so production builds have no path to show it.
#if DEBUG
@MainActor
private enum TaskThreadScenario13HarnessWindow {
  private static var window: NSWindow?

  static func show(coordinator: TaskChatCoordinator) {
    guard let taskState = coordinator.activeTaskState else { return }
    let panel = TaskChatPanel(
      taskState: taskState,
      coordinator: coordinator,
      task: nil,
      onClose: {
        coordinator.closeChat()
        window?.close()
      }
    )
    let hostingView = NSHostingView(rootView: panel)
    if let existing = window {
      existing.close()
      window = nil
    }
    let created = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 440, height: 760),
      styleMask: [.titled, .closable, .resizable, .fullSizeContentView],
      backing: .buffered,
      defer: false
    )
    created.title = "Omi — Task thread scenario"
    created.isReleasedWhenClosed = false
    created.contentView = hostingView
    created.center()
    created.makeKeyAndOrderFront(nil)
    window = created
    NSApp.activate(ignoringOtherApps: true)
  }
}
#endif

enum TaskThreadError: LocalizedError {
  case taskIsUnlinked
  case unresolvedWorkflowControl

  var errorDescription: String? {
    switch self {
    case .taskIsUnlinked:
      "Choose Work on this with Omi to start ongoing work for this task."
    case .unresolvedWorkflowControl:
      "Omi could not safely resolve task continuity yet. Try again."
    }
  }
}
