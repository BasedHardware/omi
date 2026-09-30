import Foundation
@preconcurrency import GRDB

extension MemoryStorage {
  /// Siri reads raw cache flags. The display projection omits deletion,
  /// lock provenance, and canonical ledger lifecycle details.
  func getSiriMemoryRecords(backendIds: [String]) async throws -> [MemoryRecord] {
    let wanted = Array(Set(backendIds.filter { !$0.isEmpty }))
    guard !wanted.isEmpty else { return [] }
    let db = try await ensureInitialized()
    var found: [MemoryRecord] = []
    for start in stride(from: 0, to: wanted.count, by: 200) {
      let chunk = Array(wanted[start..<min(start + 200, wanted.count)])
      let rows = try await db.read { database in
        try MemoryRecord.filter(chunk.contains(Column("backendId"))).fetchAll(database)
      }
      found.append(contentsOf: rows)
    }
    return found
  }

  func getSiriMemoryCandidates() async throws -> [MemoryRecord] {
    let db = try await ensureInitialized()
    return try await db.read { database in
      try MemoryRecord
        .filter(Column("backendId") != nil)
        .filter(Column("backendSynced") == true)
        .order(Column("createdAt").desc)
        .fetchAll(database)
    }
  }
}
