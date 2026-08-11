import Foundation

@MainActor
extension TasksStore {
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
    expectedOwnerID: String? = nil
  ) async -> BulkDeleteOutcome {
    guard let lease = captureOwnerLease(expectedOwnerID: expectedOwnerID) else {
      return .localFailure
    }
    guard !ids.isEmpty else { return .deletedEverywhere }

    // Collect every locally known relevance score before the atomic delete;
    // off-page selections are not necessarily present in the rendered arrays.
    let allTasks =
      (try? await ActionItemStorage.shared.getAllLocalActionItems())
      ?? (incompleteTasks + completedTasks)
    guard isCurrent(lease) else { return .ownerChanged }
    let tasksByID = Dictionary(lastWriteWins: allTasks.map { ($0.id, $0) })
    let scores = ids.compactMap { tasksByID[$0]?.relevanceScore }
    let selectedIDs = Set(ids)
    let removesEveryLocalTask = allTasks.allSatisfy { selectedIDs.contains($0.id) }

    // Local-first: commit the complete selection atomically so refresh
    // observers cannot see a half-deleted cache.
    do {
      try await ActionItemStorage.shared.deleteActionItemsByBackendIds(
        ids,
        authorization: Self.localMutationAuthorization(snapshot: lease.authorizationSnapshot)
      )
    } catch {
      guard isCurrent(lease) else { return .ownerChanged }
      self.error = error.localizedDescription
      logError("TasksStore: Failed to delete selected tasks locally", error: error)
      return .localFailure
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

    // Hard-delete authoritative IDs through the existing bulk endpoint.
    let remoteIDs = ids.filter { !ActionItemTaskIdentity(surfacedId: $0).isLocalOnly }
    guard !remoteIDs.isEmpty else {
      return isCurrent(lease) ? .deletedEverywhere : .ownerChanged
    }
    do {
      try await APIClient.shared.batchDeleteActionItems(
        ids: remoteIDs,
        expectedOwnerId: lease.ownerID,
        authorizationSnapshot: lease.authorizationSnapshot
      )
    } catch let partialFailure as APIClient.BatchDeletePartialFailure {
      guard isCurrent(lease) else { return .ownerChanged }
      self.error = partialFailure.underlying.localizedDescription
      logError(
        "TasksStore: Bulk delete partially completed on backend (\(partialFailure.confirmedIDs.count) confirmed, "
          + "\(partialFailure.pendingIDs.count) pending)",
        error: partialFailure.underlying
      )
      return .remoteFailure(confirmedIDs: Set(partialFailure.confirmedIDs))
    } catch {
      guard isCurrent(lease) else { return .ownerChanged }
      self.error = error.localizedDescription
      logError("TasksStore: Failed to delete selected tasks on backend (local delete preserved)", error: error)
      return .remoteFailure(confirmedIDs: [])
    }
    guard isCurrent(lease) else { return .ownerChanged }
    return .deletedEverywhere
  }
}
