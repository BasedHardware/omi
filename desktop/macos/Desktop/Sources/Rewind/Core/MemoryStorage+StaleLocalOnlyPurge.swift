import Foundation
@preconcurrency import GRDB

// MARK: - Stale Local-Only Purge

extension MemoryStorage {
  /// Soft-delete local-only rows stranded by a failed backend create.
  ///
  /// The extraction durability pipeline inserts locally first; when the remote
  /// create fails (for example an expired auth refresh), the row stays
  /// `backendId NULL, backendSynced false` forever because nothing retries
  /// `getUnsyncedMemories()`. Such rows keep counting in cache-first surfaces
  /// — home knowledge count, local search, Spotlight candidates — while the
  /// Memories page renders the authoritative server page, so the user has no
  /// delete affordance for them. Rows younger than `days` are kept so a stuck
  /// extraction has a window to be retried; rows with a backendId are never
  /// touched (those are the reconcile's to prune).
  @discardableResult
  func purgeStaleLocalOnlyMemories(olderThan days: Int = 30, now: Date = Date()) async throws -> Int {
    let db = try await ensureInitialized()
    let cutoff = now.addingTimeInterval(-TimeInterval(days) * 86_400)
    let purged = try await db.write { database -> Int in
      let stale =
        try MemoryRecord
        .filter(Column("backendId") == nil)
        .filter(Column("backendSynced") == false)
        .filter(Column("deleted") == false)
        .filter(Column("createdAt") < cutoff)
        .fetchAll(database)
      for var record in stale {
        record.deleted = true
        record.updatedAt = now
        try record.update(database)
      }
      return stale.count
    }
    if purged > 0 {
      log("MemoryStorage: Purged \(purged) stale local-only memories older than \(days) days")
      HomeKnowledgeCountInvalidation.post()
    }
    return purged
  }
}
