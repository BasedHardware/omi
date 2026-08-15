@preconcurrency import GRDB

extension ActionItemStorage {
  /// Hard-delete a complete selected task scope in one SQLite transaction.
  /// Select All can legitimately contain thousands of off-page IDs; opening a
  /// separate write transaction for every row makes the UI look frozen and can
  /// expose a partially deleted cache to refresh observers.
  func deleteActionItemsByBackendIds(
    _ backendIds: [String],
    authorization: LocalMutationAuthorization
  ) async throws {
    try authorization.require()
    guard !backendIds.isEmpty else { return }
    let db = try await ensureInitialized()

    try await authorization.withCommitLease {
      try await db.write { database in
        try authorization.require()
        for surfacedID in backendIds {
          if let record = try Self.fetchRecord(database, surfacedId: surfacedID) {
            try record.delete(database)
          }
        }
        try authorization.require()
      }
    }

    HomeKnowledgeCountInvalidation.post(
      logMessage: "ActionItemStorage: Hard-deleted \(backendIds.count) selected action items")
  }
}
