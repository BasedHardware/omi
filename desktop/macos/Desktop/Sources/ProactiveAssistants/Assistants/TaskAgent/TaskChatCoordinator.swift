import Combine
import OmiSupport
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

  private static let legacyUnreadTaskIdsKey = "taskChat.unreadTaskIds"

  @Published var streamingTaskIds: Set<String> = []
  @Published var unreadTaskIds: Set<String> = [] {
    didSet {
      guard !suppressUnreadPersistence, let ownerID = activeOwnerID else { return }
      UserDefaults.standard.set(
        Array(unreadTaskIds),
        forKey: Self.unreadTaskIdsKey(ownerID: ownerID)
      )
    }
  }
  @Published var streamingStatuses: [String: String] = [:]
  @Published var activeTaskState: TaskChatState?

  private var workstreamStates: [String: TaskChatState] = [:]
  private var taskToWorkstream: [String: String] = [:]
  private var taskIdsByWorkstream: [String: Set<String>] = [:]
  private var detailByWorkstream: [String: OmiAPI.WorkstreamDetailProjection] = [:]
  private var runtimeStatusCancellable: AnyCancellable?
  private var ownerChangeCancellable: AnyCancellable?
  private var lastRuntimeStatusByWorkstream: [String: AgentRunProjectionStatus] = [:]
  private var rehydratedWorkstreamIds: Set<String> = []
  private var ownerGeneration: UInt64 = 0
  private var activeOwnerID: String?
  private var suppressUnreadPersistence = false
  private var isResettingOwnerProjection = false

  private let chatProvider: ChatProvider
  private let workstreamAPI: any TaskWorkstreamAPI
  private let persistWorkstreamLink: @MainActor (String, String, String, LocalMutationAuthorization) async -> Void
  private let ownerIDProvider: @MainActor () -> String?

  init(
    chatProvider: ChatProvider,
    workstreamAPI: any TaskWorkstreamAPI = LiveTaskWorkstreamAPI(),
    ownerIDProvider: @escaping @MainActor () -> String? = {
      RuntimeOwnerIdentity.currentOwnerId()
    },
    persistWorkstreamLink:
      @escaping @MainActor (
        String, String, String, LocalMutationAuthorization
      ) async -> Void = { taskId, workstreamId, _, authorization in
        try? await ActionItemStorage.shared.updateActionItemFields(
          backendId: taskId,
          workstreamId: workstreamId,
          authorization: authorization
        )
      }
  ) {
    self.chatProvider = chatProvider
    self.workstreamAPI = workstreamAPI
    self.ownerIDProvider = ownerIDProvider
    self.persistWorkstreamLink = persistWorkstreamLink
    activeOwnerID = Self.normalizedOwnerID(ownerIDProvider())
    UserDefaults.standard.removeObject(forKey: Self.legacyUnreadTaskIdsKey)
    if let ownerID = activeOwnerID,
      let saved = UserDefaults.standard.array(
        forKey: Self.unreadTaskIdsKey(ownerID: ownerID)
      ) as? [String]
    {
      unreadTaskIds = Set(saved)
    }
    runtimeStatusCancellable = AgentRuntimeStatusStore.shared.$projectionsBySurface
      .receive(on: DispatchQueue.main)
      .sink { [weak self] projections in
        self?.applyRuntimeProjections(projections)
      }
    ownerChangeCancellable = NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)
      .sink { [weak self] _ in
        MainActor.assumeIsolated {
          self?.resetOwnerProjection()
        }
      }
  }

  // MARK: - Public identity/actions

  struct OwnerProjectionSnapshot: Equatable {
    let stateCount: Int
    let taskMappingCount: Int
    let workstreamMappingCount: Int
    let detailCount: Int
    let runtimeStatusCount: Int
    let messageCount: Int
  }

  var ownerProjectionSnapshot: OwnerProjectionSnapshot {
    OwnerProjectionSnapshot(
      stateCount: workstreamStates.count,
      taskMappingCount: taskToWorkstream.count,
      workstreamMappingCount: taskIdsByWorkstream.count,
      detailCount: detailByWorkstream.count,
      runtimeStatusCount: lastRuntimeStatusByWorkstream.count,
      messageCount: workstreamStates.values.reduce(0) { $0 + $1.messages.count }
    )
  }

  /// Synchronous owner teardown delivered while the exclusive effective-owner
  /// transition is still held. Suspended work keeps the previous generation,
  /// so it cannot repopulate any task, status, transcript, or detail map.
  func resetOwnerProjection() {
    guard !isResettingOwnerProjection else { return }
    isResettingOwnerProjection = true
    defer { isResettingOwnerProjection = false }
    ownerGeneration &+= 1
    activeOwnerID = nil
    for state in workstreamStates.values { state.invalidateOwnerState() }
    workstreamStates.removeAll()
    taskToWorkstream.removeAll()
    taskIdsByWorkstream.removeAll()
    detailByWorkstream.removeAll()
    lastRuntimeStatusByWorkstream.removeAll()
    rehydratedWorkstreamIds.removeAll()
    AgentRuntimeStatusStore.shared.reset()
    activeTaskId = nil
    activeWorkstreamId = nil
    activeThreadProjection = nil
    activeTaskState = nil
    isPanelOpen = false
    isOpening = false
    errorMessage = nil
    pendingInputText = ""
    streamingTaskIds.removeAll()
    streamingStatuses.removeAll()
    suppressUnreadPersistence = true
    unreadTaskIds.removeAll()
    suppressUnreadPersistence = false
  }

  private func captureOwnerLease() -> TaskChatOwnerLease? {
    guard let ownerID = Self.normalizedOwnerID(ownerIDProvider()) else {
      if activeOwnerID != nil { resetOwnerProjection() }
      return nil
    }
    if let activeOwnerID, activeOwnerID != ownerID {
      resetOwnerProjection()
    }
    if activeOwnerID == nil {
      activeOwnerID = ownerID
      suppressUnreadPersistence = true
      unreadTaskIds = Set(
        UserDefaults.standard.array(forKey: Self.unreadTaskIdsKey(ownerID: ownerID))
          as? [String] ?? []
      )
      suppressUnreadPersistence = false
    }
    guard
      let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
        expectedOwnerID: ownerID
      )
    else { return nil }
    return TaskChatOwnerLease(
      authorizationSnapshot: authorizationSnapshot,
      generation: ownerGeneration
    )
  }

  private func isCurrent(_ lease: TaskChatOwnerLease) -> Bool {
    activeOwnerID == lease.ownerID
      && ownerGeneration == lease.generation
      && RuntimeOwnerIdentity.isAuthorizationCurrent(lease.authorizationSnapshot)
  }

  private static func normalizedOwnerID(_ ownerID: String?) -> String? {
    guard let ownerID else { return nil }
    let normalized = ownerID.trimmingCharacters(in: .whitespacesAndNewlines)
    return normalized.isEmpty ? nil : normalized
  }

  private static func unreadTaskIdsKey(ownerID: String) -> String {
    "\(legacyUnreadTaskIdsKey).owner.\(ownerID)"
  }

  /// Explicit user action behind “Work on this with Omi”. An unlinked task is
  /// allowed to create its durable workstream only through this method.
  func openChat(for task: TaskActionItem) async {
    guard let lease = captureOwnerLease() else { return }
    await openThread(for: task, createIfNeeded: true, lease: lease)
  }

  /// Opens an existing linked thread without creating product state.
  @discardableResult
  func openExistingThread(for task: TaskActionItem) async -> Bool {
    guard let lease = captureOwnerLease() else { return false }
    guard let expectedWorkstreamId = task.workstreamId ?? taskToWorkstream[task.id] else { return false }
    await openThread(for: task, createIfNeeded: false, lease: lease)
    return isCurrent(lease)
      && activeTaskId == task.id && activeWorkstreamId == expectedWorkstreamId
  }

  /// Resume an existing thread from dashboard/goal projections without
  /// manufacturing a second workstream or relying on a locally cached task.
  @discardableResult
  func openExistingThread(workstreamID: String, preferredTaskID: String? = nil) async -> Bool {
    guard let lease = captureOwnerLease() else { return false }
    do {
      let task = try await existingThreadTask(
        workstreamID: workstreamID,
        preferredTaskID: preferredTaskID,
        lease: lease
      )
      guard isCurrent(lease) else { return false }
      await openThread(for: task, createIfNeeded: false, lease: lease)
      return isCurrent(lease)
        && activeTaskId == task.id && activeWorkstreamId == workstreamID
    } catch {
      if isCurrent(lease) {
        errorMessage = error.localizedDescription
        logError("TaskChatCoordinator: Failed to resume projected thread \(workstreamID)", error: error)
      }
      return false
    }
  }

  func existingThreadTask(workstreamID: String, preferredTaskID: String? = nil) async throws -> TaskActionItem {
    guard let lease = captureOwnerLease() else { throw LocalMutationAuthorizationError.revoked }
    return try await existingThreadTask(
      workstreamID: workstreamID,
      preferredTaskID: preferredTaskID,
      lease: lease
    )
  }

  private func existingThreadTask(
    workstreamID: String,
    preferredTaskID: String?,
    lease: TaskChatOwnerLease
  ) async throws -> TaskActionItem {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    let detail = try await workstreamAPI.detail(
      workstreamId: workstreamID,
      authorizationSnapshot: lease.authorizationSnapshot
    )
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    let wireTask: OmiAPI.ActionItemResponse
    if let preferredTaskID {
      guard let preferred = detail.tasks.first(where: { $0.id == preferredTaskID }) else {
        throw TaskThreadError.requestedTaskUnavailable
      }
      wireTask = preferred
    } else {
      guard let first = detail.tasks.first else { throw TaskThreadError.threadHasNoTasks }
      wireTask = first
    }
    return try JSONDecoder().decode(
      TaskActionItem.self,
      from: JSONEncoder().encode(wireTask)
    )
  }

  func switchToTask(_ task: TaskActionItem) async {
    guard let lease = captureOwnerLease() else { return }
    guard task.id != activeTaskId else { return }
    await openThread(for: task, createIfNeeded: false, lease: lease)
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
    guard let lease = captureOwnerLease() else { throw LocalMutationAuthorizationError.revoked }
    let control = try await workstreamAPI.workflowControl(
      authorizationSnapshot: lease.authorizationSnapshot
    )
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    guard let generation = control.accountGeneration else {
      throw TaskThreadError.unresolvedWorkflowControl
    }
    let receipt = try await workstreamAPI.resolveGoalIntent(
      goalId: goalId,
      title: title,
      objective: objective,
      anchorTaskDescription: anchorTaskDescription,
      idempotencyKey: TaskWorkIntentIdentity.goal(goalId: goalId, occurrenceId: occurrenceId),
      accountGeneration: generation,
      authorizationSnapshot: lease.authorizationSnapshot
    )
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    return receipt
  }

  func refreshActiveThread() async {
    guard let lease = captureOwnerLease() else { return }
    guard let workstreamId = activeWorkstreamId, let taskId = activeTaskId else { return }
    do {
      let detail = try await workstreamAPI.detail(
        workstreamId: workstreamId,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      guard isCurrent(lease) else { return }
      register(detail: detail)
      activeThreadProjection = TaskThreadProjection(detail: detail, activeTaskID: taskId)
    } catch {
      if isCurrent(lease) {
        errorMessage = error.localizedDescription
        logError("TaskChatCoordinator: Failed to refresh thread \(workstreamId)", error: error)
      }
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
    guard let lease = captureOwnerLease() else { return }
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
        guard let self, self.isCurrent(lease) else { return }
        do {
          let prepareReceipt = try await TaskWorkstreamContinuity.prepare(
            workstreamId: workstreamId,
            taskIds: taskIds,
            checkpoints: [],
            authorizationSnapshot: lease.authorizationSnapshot
          )
          guard self.isCurrent(lease) else { return }
          if !prepareReceipt.deliveries.isEmpty {
            let detail = try await self.workstreamAPI.detail(
              workstreamId: workstreamId,
              authorizationSnapshot: lease.authorizationSnapshot
            )
            guard self.isCurrent(lease) else { return }
            await self.deliverContinuity(
              prepareReceipt.deliveries,
              detail: detail,
              lease: lease
            )
          }
        } catch {
          if self.isCurrent(lease) {
            self.rehydratedWorkstreamIds.remove(workstreamId)
            logError("TaskChatCoordinator: Failed to rehydrate workstream status \(workstreamId)", error: error)
          }
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
    guard let lease = captureOwnerLease() else { return }
    await openThread(for: task, createIfNeeded: true, revealPanel: false, lease: lease)
    guard isCurrent(lease) else { return }
    // openThread can early-exit (isOpening) or fail without resetting state when
    // revealPanel is false — activeTaskState may still belong to a previous task.
    // Never send this task's prompt into another task's thread.
    guard activeTaskId == task.id, let state = activeTaskState, !state.isSending else { return }
    // Stamp before sending: RecurringTaskScheduler gates re-investigation on this.
    try? await ActionItemStorage.shared.updateAgentStartedAt(
      taskId: task.id,
      startedAt: Date(),
      authorization: LocalMutationAuthorization {
        RuntimeOwnerIdentity.isAuthorizationCurrent(lease.authorizationSnapshot)
      }
    )
    await state.sendMessage(
      TaskAgentSettings.shared.buildCanonicalTaskPrompt(for: task),
      taskContext: activeContextPacket
    )
    guard isCurrent(lease) else { return }
    await refreshActiveThread()
  }

  // MARK: - Resolution

  private func openThread(
    for task: TaskActionItem,
    createIfNeeded: Bool,
    revealPanel: Bool = true,
    lease: TaskChatOwnerLease
  ) async {
    guard isCurrent(lease) else { return }
    guard !isOpening else { return }
    isOpening = true
    errorMessage = nil
    defer { isOpening = false }

    do {
      let workstreamId = try await resolveWorkstreamId(
        for: task,
        createIfNeeded: createIfNeeded,
        lease: lease
      )
      guard isCurrent(lease) else { return }
      let detail = try await workstreamAPI.detail(
        workstreamId: workstreamId,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      guard isCurrent(lease) else { return }
      let projection = TaskThreadProjection(detail: detail, activeTaskID: task.id)
      let prepareReceipt = try await TaskWorkstreamContinuity.prepare(
        workstreamId: workstreamId,
        taskIds: detail.tasks.map(\.id) + [task.id],
        checkpoints: detail.checkpoints,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      guard isCurrent(lease) else { return }

      activeTaskId = task.id
      activeWorkstreamId = workstreamId
      activeThreadProjection = projection
      markAsRead(task.id)
      register(detail: detail)
      await deliverContinuity(prepareReceipt.deliveries, detail: detail, lease: lease)
      guard isCurrent(lease) else { return }
      taskToWorkstream[task.id] = workstreamId
      taskIdsByWorkstream[workstreamId, default: []].insert(task.id)

      let state: TaskChatState
      if let existing = workstreamStates[workstreamId] {
        existing.selectTask(task.id)
        state = existing
      } else {
        let configuredPath = TaskAgentSettings.shared.workingDirectory
        let workspace =
          configuredPath.isEmpty
          ? FileManager.default.homeDirectoryForCurrentUser.path
          : configuredPath

        let legacyImportCheckpoint =
          "kernelJournal.legacyTaskImport.v1|\(lease.ownerID)|\(workstreamId)"
        if !UserDefaults.standard.bool(forKey: legacyImportCheckpoint) {
          var cursor: TaskChatLegacyMessageCursor?
          while true {
            guard isCurrent(lease) else { return }
            let page = try await TaskChatMessageStorage.shared.legacyMessagePage(
              fromTaskIds: detail.tasks.map(\.id) + [task.id],
              workstreamId: workstreamId,
              after: cursor
            )
            guard isCurrent(lease) else { return }
            try await TaskChatRuntime.importLegacyMessages(
              workstreamId: workstreamId,
              ownerID: lease.ownerID,
              authorizationSnapshot: lease.authorizationSnapshot,
              messages: page.rows.map { $0.toChatMessage() }
            )
            guard isCurrent(lease) else { return }
            guard page.rows.count == TaskChatLegacyCompatibilityMetadata.pageSize,
              let nextCursor = page.nextCursor
            else { break }
            cursor = nextCursor
          }
          UserDefaults.standard.set(true, forKey: legacyImportCheckpoint)
        }
        let created = TaskChatState(
          taskId: task.id,
          workstreamId: workstreamId,
          workspacePath: workspace,
          authorizationSnapshot: lease.authorizationSnapshot,
          ownerIDProvider: ownerIDProvider
        )
        created.onQueryCompleted = { [weak self] result, chatMessageId in
          guard let self, self.isCurrent(lease) else { return }
          await self.consumeCompletedQuery(
            result,
            workstreamId: workstreamId,
            chatMessageId: chatMessageId,
            lease: lease
          )
        }
        await created.loadPersistedMessages()
        guard isCurrent(lease) else {
          created.invalidateOwnerState()
          return
        }
        workstreamStates[workstreamId] = created
        state = created
      }

      activeTaskState = state
      pendingInputText = ""
      if revealPanel { isPanelOpen = true }
    } catch {
      if isCurrent(lease) {
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
  }

  func resolveWorkstreamId(
    for task: TaskActionItem,
    createIfNeeded: Bool
  ) async throws -> String {
    guard let lease = captureOwnerLease() else { throw LocalMutationAuthorizationError.revoked }
    return try await resolveWorkstreamId(
      for: task,
      createIfNeeded: createIfNeeded,
      lease: lease
    )
  }

  private func resolveWorkstreamId(
    for task: TaskActionItem,
    createIfNeeded: Bool,
    lease: TaskChatOwnerLease
  ) async throws -> String {
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    if let linked = task.workstreamId ?? taskToWorkstream[task.id] {
      return linked
    }
    guard createIfNeeded else { throw TaskThreadError.taskIsUnlinked }

    let control = try await workstreamAPI.workflowControl(
      authorizationSnapshot: lease.authorizationSnapshot
    )
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
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
      accountGeneration: generation,
      authorizationSnapshot: lease.authorizationSnapshot
    )
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    let authorization = LocalMutationAuthorization {
      RuntimeOwnerIdentity.isAuthorizationCurrent(lease.authorizationSnapshot)
    }
    await persistWorkstreamLink(
      task.id,
      receipt.workstreamId,
      lease.ownerID,
      authorization
    )
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }
    taskToWorkstream[task.id] = receipt.workstreamId
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
      guard let lease = captureOwnerLease() else { return }
      let workstreamId = detail.workstream.workstreamId
      guard detail.tasks.contains(where: { $0.id == activeTaskID }) else { return }
      register(detail: detail)
      activeTaskId = activeTaskID
      activeWorkstreamId = workstreamId
      activeThreadProjection = TaskThreadProjection(detail: detail, activeTaskID: activeTaskID)
      let state =
        workstreamStates[workstreamId]
        ?? TaskChatState(
          taskId: activeTaskID,
          workstreamId: workstreamId,
          workspacePath: FileManager.default.homeDirectoryForCurrentUser.path,
          authorizationSnapshot: lease.authorizationSnapshot,
          ownerIDProvider: ownerIDProvider
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
        guard let lease = self.captureOwnerLease() else {
          return ["error": "task thread owner unavailable"]
        }
        let activeTaskID =
          params["task"] == "second"
          ? TaskThreadScenario13Fixture.secondTaskID
          : TaskThreadScenario13Fixture.firstTaskID
        do {
          let runtime = try await self.buildScenario13RuntimeProjection(
            resumeOnly: params["resume"] == "true",
            authorizationSnapshot: lease.authorizationSnapshot
          )
          guard self.isCurrent(lease) else {
            return ["error": "task thread owner changed"]
          }
          self.loadScenario13Fixture(activeTaskID: activeTaskID, detail: runtime.detail)
          TaskThreadScenario13HarnessWindow.show(coordinator: self)
          let projection = self.activeThreadProjection
          return [
            "workstream_id": projection?.workstreamID ?? "",
            "active_task_id": projection?.activeTaskID ?? "",
            "kernel_surface": "workstream",
            "artifact_versions": projection?.artifactVersions.map { "v\($0.version)" }.joined(separator: ",") ?? "",
            "cited_v2": projection?.artifactVersions.first(where: { $0.version == 2 })?.evidenceRefs?.isEmpty == false
              ? "true" : "false",
            "external_send_decision": runtime.externalSendDecision,
            "runtime_bridge": "live_app_kernel",
            "kernel_session_id": runtime.kernelSessionID,
          ]
        } catch {
          return ["error": String(describing: error)]
        }
      }
    }

    private func buildScenario13RuntimeProjection(
      resumeOnly: Bool,
      authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    ) async throws -> (
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
          authorizationSnapshot: authorizationSnapshot,
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
          authorizationSnapshot: authorizationSnapshot,
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
          authorizationSnapshot: authorizationSnapshot,
          control: control
        )
        let v2 = try await TaskWorkstreamContinuity.persist(
          workstream: projection,
          queryResult: scenario13QueryResult(version: 2),
          chatMessageId: "scenario-13-chat-v2",
          authorizationSnapshot: authorizationSnapshot,
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
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
        throw LocalMutationAuthorizationError.revoked
      }
      let policyRaw = try await control(
        "evaluate_desktop_tool_policy",
        [
          "requestedBundles": ["external.write_send"],
          "selectedBundles": ["external.write_send"],
          "externalSend": true,
          "operation": "send_email",
          "resourceRef": "workstream:\(TaskThreadScenario13Fixture.workstreamID)",
        ])
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
        throw LocalMutationAuthorizationError.revoked
      }
      struct PolicyResponse: Decodable {
        struct Policy: Decodable { let decision: String }
        let ok: Bool
        let policy: Policy
      }
      let policy = try JSONDecoder().decode(PolicyResponse.self, from: Data(policyRaw.utf8))
      guard policy.ok else { throw TaskWorkstreamContinuityError.invalidRuntimeResponse }
      let kernelProjection = try await TaskWorkstreamContinuity.project(
        workstreamId: TaskThreadScenario13Fixture.workstreamID,
        authorizationSnapshot: authorizationSnapshot,
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
    chatMessageId: String,
    lease: TaskChatOwnerLease
  ) async {
    guard isCurrent(lease) else { return }
    guard let detail = detailByWorkstream[workstreamId] else { return }
    let selectedTaskId =
      activeWorkstreamId == workstreamId
      ? activeTaskId ?? detail.tasks.first?.id ?? ""
      : detail.tasks.first?.id ?? ""
    let projection = TaskThreadProjection(detail: detail, activeTaskID: selectedTaskId)
    do {
      let receipt = try await TaskWorkstreamContinuity.persist(
        workstream: projection,
        queryResult: result,
        chatMessageId: chatMessageId,
        authorizationSnapshot: lease.authorizationSnapshot
      )
      guard isCurrent(lease) else { return }
      await deliverContinuity(receipt.deliveries, detail: detail, lease: lease)
      guard isCurrent(lease) else { return }
      await refreshActiveThread()
    } catch {
      if isCurrent(lease) {
        errorMessage = "Reply complete, but thread continuity could not be saved. \(error.localizedDescription)"
        logError("TaskChatCoordinator: Failed to persist workstream continuity", error: error)
      }
    }
  }

  private func deliverContinuity(
    _ deliveries: [TaskKernelDelivery],
    detail: OmiAPI.WorkstreamDetailProjection,
    lease: TaskChatOwnerLease
  ) async {
    guard isCurrent(lease) else { return }
    guard !deliveries.isEmpty else { return }
    let workstreamId = detail.workstream.workstreamId
    let generation: Int
    do {
      let control = try await workstreamAPI.workflowControl(
        authorizationSnapshot: lease.authorizationSnapshot
      )
      guard isCurrent(lease) else { return }
      guard let resolved = control.accountGeneration else {
        throw TaskThreadError.unresolvedWorkflowControl
      }
      generation = resolved
    } catch {
      guard isCurrent(lease) else { return }
      for delivery in deliveries {
        try? await TaskWorkstreamContinuity.resolveDelivery(
          id: delivery.deliveryId,
          delivered: false,
          error: error,
          authorizationSnapshot: lease.authorizationSnapshot
        )
      }
      logError("TaskChatCoordinator: Failed to resolve continuity delivery generation", error: error)
      return
    }

    var backendHeads = Dictionary(
      lastWriteWins: TaskThreadProjection(
        detail: detail,
        activeTaskID: detail.tasks.first?.id ?? ""
      ).artifactHeads.map { ($0.logicalKey, $0) }
    )
    var knownArtifacts = detail.artifacts
    let evidenceEventIds = detail.recentEvents
      .filter { $0.sensitivity == .normal && !($0.evidenceRefs ?? []).isEmpty }
      .map(\.eventId)

    for delivery in deliveries {
      guard isCurrent(lease) else { return }
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
              ],
              authorizationSnapshot: lease.authorizationSnapshot
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
            accountGeneration: generation,
            authorizationSnapshot: lease.authorizationSnapshot
          )
          guard isCurrent(lease) else { return }
          backendHeads[logicalKey] = created
          knownArtifacts.append(created)
          try await TaskWorkstreamContinuity.resolveDelivery(
            id: delivery.deliveryId,
            delivered: true,
            receipt: ["artifact_id": created.artifactId, "version": created.version],
            authorizationSnapshot: lease.authorizationSnapshot
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
            accountGeneration: generation,
            authorizationSnapshot: lease.authorizationSnapshot
          )
          guard isCurrent(lease) else { return }
          try await TaskWorkstreamContinuity.resolveDelivery(
            id: delivery.deliveryId,
            delivered: true,
            receipt: ["checkpoint_id": saved.checkpointId],
            authorizationSnapshot: lease.authorizationSnapshot
          )
        default:
          throw TaskWorkstreamContinuityError.invalidRuntimeResponse
        }
      } catch {
        guard isCurrent(lease) else { return }
        try? await TaskWorkstreamContinuity.resolveDelivery(
          id: delivery.deliveryId,
          delivered: false,
          error: error,
          authorizationSnapshot: lease.authorizationSnapshot
        )
        logError("TaskChatCoordinator: Continuity delivery \(delivery.deliveryId) remains queued", error: error)
      }
    }
  }

  // MARK: - Runtime projection

  private func applyRuntimeProjections(_ projections: [String: AgentRunProjection]) {
    guard !isResettingOwnerProjection, captureOwnerLease() != nil else { return }
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
  case requestedTaskUnavailable
  case threadHasNoTasks

  var errorDescription: String? {
    switch self {
    case .taskIsUnlinked:
      "Choose Work on this with Omi to start ongoing work for this task."
    case .unresolvedWorkflowControl:
      "Omi could not safely resolve task continuity yet. Try again."
    case .requestedTaskUnavailable:
      "The requested task is no longer part of this thread."
    case .threadHasNoTasks:
      "This thread has no task to open."
    }
  }
}
