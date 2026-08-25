import Foundation

extension TasksStore {
  /// Hydrates a canonical task through the owner-fenced store before a card or detail page mutates it.
  func resolveCanonicalTask(
    id: String,
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async -> TaskActionItem? {
    let normalizedID = id.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalizedID.isEmpty,
      let lease = captureOwnerLease(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return nil }

    if let existing = tasks.first(where: { $0.id == normalizedID && !$0.isRetired }) {
      return existing
    }
    do {
      let localTask: TaskActionItem?
      if let loadTaskDetail = operations.loadTaskDetail {
        localTask = try await loadTaskDetail(normalizedID, lease.ownerID)
      } else {
        localTask = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: normalizedID)
      }
      guard isCurrent(lease) else { return nil }
      if let localTask, localTask.id == normalizedID, !localTask.isRetired {
        publishHydratedCanonicalTask(localTask)
        return localTask
      }

      let remoteTask: TaskActionItem?
      if let fetchTaskDetail = operations.fetchTaskDetail {
        remoteTask = try await fetchTaskDetail(normalizedID, lease.ownerID)
      } else {
        remoteTask = try await APIClient.shared.getActionItem(
          id: normalizedID,
          expectedOwnerId: lease.ownerID,
          authorizationSnapshot: lease.authorizationSnapshot
        )
      }
      guard isCurrent(lease), let remoteTask, remoteTask.id == normalizedID, !remoteTask.isRetired
      else { return nil }
      try await syncPage([remoteTask], lease: lease, operations: operations)
      guard isCurrent(lease),
        let hydratedTask = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: normalizedID),
        !hydratedTask.isRetired
      else { return nil }
      publishHydratedCanonicalTask(hydratedTask)
      await refreshDashboard(lease: lease, operations: operations)
      guard isCurrent(lease) else { return nil }
      return hydratedTask
    } catch {
      guard isCurrent(lease) else { return nil }
      self.error = "This task is no longer available."
      logError("TasksStore: Failed to hydrate canonical task", error: error)
      return nil
    }
  }

  private func publishHydratedCanonicalTask(_ task: TaskActionItem) {
    incompleteTasks.removeAll { $0.id == task.id }
    completedTasks.removeAll { $0.id == task.id }
    deletedTasks.removeAll { $0.id == task.id }
    if task.isRetired {
      deletedTasks.insert(task, at: 0)
    } else if task.completed {
      completedTasks.insert(task, at: 0)
    } else {
      incompleteTasks.insert(task, at: 0)
    }
  }
}
