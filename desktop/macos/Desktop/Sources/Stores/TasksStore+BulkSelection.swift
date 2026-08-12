import Foundation

@MainActor
extension TasksStore {
  struct BulkDeleteOperations {
    var loadLocalTasks: (() async throws -> [TaskActionItem])?
    var deleteLocalTaskIDs:
      ((_ ids: [String], _ authorization: RuntimeOwnerAuthorizationSnapshot) async throws -> Void)?
    var deleteRemoteTaskIDs:
      (
        (
          _ ids: [String], _ ownerID: String,
          _ authorization: RuntimeOwnerAuthorizationSnapshot
        ) async throws -> Void
      )?

    init(
      loadLocalTasks: (() async throws -> [TaskActionItem])? = nil,
      deleteLocalTaskIDs: (
        (_ ids: [String], _ authorization: RuntimeOwnerAuthorizationSnapshot) async throws -> Void
      )? = nil,
      deleteRemoteTaskIDs: (
        (
          _ ids: [String], _ ownerID: String,
          _ authorization: RuntimeOwnerAuthorizationSnapshot
        ) async throws -> Void
      )? = nil
    ) {
      self.loadLocalTasks = loadLocalTasks
      self.deleteLocalTaskIDs = deleteLocalTaskIDs
      self.deleteRemoteTaskIDs = deleteRemoteTaskIDs
    }
  }

  private enum LocalBulkDeleteCommitResult {
    case committed
    case failed
    case ownerChanged
  }

  /// Fetches the complete account-wide task identity census without expanding
  /// the rendered list. The IDs-only endpoint is intentionally unpaginated and
  /// cheap; locally created rows are unioned in so offline work is selectable
  /// before it receives a backend ID.
  func selectionSnapshotIDs(
    completed: Bool,
    expectedOwnerID: String? = nil,
    operations: OwnerBoundOperations = OwnerBoundOperations()
  ) async throws -> [String] {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else {
      throw LocalMutationAuthorizationError.revoked
    }

    let remoteIDs: [String]
    if let fetchSelectionTaskIds = operations.fetchSelectionTaskIds {
      remoteIDs = try await fetchSelectionTaskIds(completed, lease.ownerID)
    } else {
      remoteIDs = try await APIClient.shared.getActionItemIds(
        completed: completed,
        expectedOwnerId: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
    }
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }

    let localTasks = try await ActionItemStorage.shared.getAllLocalActionItems()
    guard isCurrent(lease) else { throw LocalMutationAuthorizationError.revoked }

    var seen = Set<String>()
    let localOnlyIDs =
      localTasks
      .filter { $0.completed == completed }
      .map(\.id)
      .filter { ActionItemTaskIdentity(surfacedId: $0).isLocalOnly }
    return (remoteIDs + localOnlyIDs).filter {
      !$0.isEmpty && seen.insert($0).inserted
    }
  }

  func deleteMultipleTasks(
    ids: [String],
    expectedOwnerID: String? = nil,
    operations: BulkDeleteOperations = BulkDeleteOperations()
  ) async -> BulkDeleteOutcome {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else {
      return .ownerChanged
    }
    guard !ids.isEmpty else { return .deletedEverywhere }

    // Collect every locally known relevance score before the atomic delete;
    // off-page selections are not necessarily present in the rendered arrays.
    let allTasks: [TaskActionItem]
    if let loadLocalTasks = operations.loadLocalTasks {
      allTasks = (try? await loadLocalTasks()) ?? (incompleteTasks + completedTasks)
    } else {
      allTasks =
        (try? await ActionItemStorage.shared.getAllLocalActionItems())
        ?? (incompleteTasks + completedTasks)
    }
    guard isCurrent(lease) else { return .ownerChanged }

    // The backend is authoritative and validates the entire chunk for locked
    // tasks before deleting anything. Ask it first so a 402/network failure
    // cannot empty the local cache and make the same tasks reappear on refresh.
    let remoteIDs = ids.filter { !ActionItemTaskIdentity(surfacedId: $0).isLocalOnly }
    if !remoteIDs.isEmpty {
      do {
        if let deleteRemoteTaskIDs = operations.deleteRemoteTaskIDs {
          try await deleteRemoteTaskIDs(remoteIDs, lease.ownerID, lease.authorizationSnapshot)
        } else {
          try await APIClient.shared.batchDeleteActionItems(
            ids: remoteIDs,
            expectedOwnerId: lease.ownerID,
            authorizationSnapshot: lease.authorizationSnapshot
          )
        }
      } catch let partialFailure as APIClient.BatchDeletePartialFailure {
        guard isCurrent(lease) else { return .ownerChanged }
        let confirmedIDs = Set(partialFailure.confirmedIDs)
        if !confirmedIDs.isEmpty {
          let confirmedInOrder = ids.filter { confirmedIDs.contains($0) }
          switch await commitLocalBulkDelete(
            ids: confirmedInOrder,
            allTasks: allTasks,
            lease: lease,
            operations: operations
          ) {
          case .committed:
            break
          case .failed:
            return .localFailure(remoteDeletedIDs: confirmedIDs)
          case .ownerChanged:
            return .ownerChanged
          }
        }
        self.error = partialFailure.underlying.localizedDescription
        logError(
          "TasksStore: Bulk delete partially completed on backend (\(partialFailure.confirmedIDs.count) confirmed, "
            + "\(partialFailure.pendingIDs.count) pending)",
          error: partialFailure.underlying
        )
        return .remoteFailure(confirmedIDs: confirmedIDs)
      } catch {
        guard isCurrent(lease) else { return .ownerChanged }
        self.error = error.localizedDescription
        logError("TasksStore: Failed to delete selected tasks on backend; local rows preserved", error: error)
        return .remoteFailure(confirmedIDs: [])
      }
    }

    switch await commitLocalBulkDelete(
      ids: ids,
      allTasks: allTasks,
      lease: lease,
      operations: operations
    ) {
    case .committed:
      return .deletedEverywhere
    case .failed:
      return .localFailure(remoteDeletedIDs: Set(remoteIDs))
    case .ownerChanged:
      return .ownerChanged
    }
  }

  private func commitLocalBulkDelete(
    ids: [String],
    allTasks: [TaskActionItem],
    lease: OwnerOperationLease,
    operations: BulkDeleteOperations
  ) async -> LocalBulkDeleteCommitResult {
    let selectedIDs = Set(ids)
    let tasksByID = Dictionary(lastWriteWins: allTasks.map { ($0.id, $0) })
    let scores = ids.compactMap { tasksByID[$0]?.relevanceScore }
    let removesEveryLocalTask = allTasks.allSatisfy { selectedIDs.contains($0.id) }

    do {
      if let deleteLocalTaskIDs = operations.deleteLocalTaskIDs {
        try await deleteLocalTaskIDs(ids, lease.authorizationSnapshot)
      } else {
        try await ActionItemStorage.shared.deleteActionItemsByBackendIds(
          ids,
          authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
        )
      }
    } catch {
      guard isCurrent(lease) else { return .ownerChanged }
      self.error = error.localizedDescription
      logError("TasksStore: Failed to delete selected tasks locally", error: error)
      return .failed
    }
    guard isCurrent(lease) else { return .ownerChanged }
    incompleteTasks.removeAll { selectedIDs.contains($0.id) }
    completedTasks.removeAll { selectedIDs.contains($0.id) }

    // Compact relevance scores highest-first so shifts do not affect each other.
    if !removesEveryLocalTask {
      for score in scores.sorted(by: >) {
        try? await ActionItemStorage.shared.compactScoresAfterRemoval(
          removedScore: score,
          authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
        )
        guard isCurrent(lease) else { return .ownerChanged }
      }
    }
    if !removesEveryLocalTask, !scores.isEmpty {
      Task { @MainActor [weak self] in
        await self?.syncScoresToBackend(lease: lease)
      }
    }
    return .committed
  }
}
