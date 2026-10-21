import Foundation
@preconcurrency import GRDB

extension MemoryStorage {
  /// Cache a Siri-confirmed write only while its original account still owns
  /// the local database. General API refreshes keep using the unscoped overload.
  @discardableResult
  func syncServerMemory(
    _ memory: ServerMemory,
    authorization: LocalMutationAuthorization,
    beforeLocalWrite: @Sendable () async -> Void = {},
    onIndexChange: @escaping @Sendable ([String]) -> Void = SiriIndexHooks.memoriesChanged
  ) async throws -> Int64 {
    try authorization.require()
    let db = try await ensureInitialized()
    await beforeLocalWrite()
    try authorization.require()
    let result = try await authorization.withCommitLeaseSuppressingSupersededResult {
      let (skipped, adopted, inserted, index, changed, id) = try await db.write { database in
        try authorization.require()
        let (skipped, adopted, inserted, index, changed) =
          try Self.reconcileServerMemories([memory], in: database)
        guard
          let id = try MemoryRecord
            .filter(Column("backendId") == memory.id)
            .fetchOne(database)?.id
        else { throw MemoryStorageError.syncFailed("Synced memory was not found") }
        try authorization.require()
        return (skipped, adopted, inserted, index, changed, id)
      }
      try authorization.require()
      if inserted > 0 { HomeKnowledgeCountInvalidation.post() }
      LocalEmbeddingIndexer.scheduleMemoryIndex(items: index)
      onIndexChange(changed)
      return (skipped, adopted, id)
    }
    if result.0 > 0 || result.1 > 0 {
      log("MemoryStorage: Siri memory cache skipped \(result.0) newer local, adopted \(result.1) orphan")
    }
    return result.2
  }
}
