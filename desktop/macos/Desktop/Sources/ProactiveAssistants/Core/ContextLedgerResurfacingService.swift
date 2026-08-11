import Foundation
@preconcurrency import GRDB

/// Flag-on replacement for the independent resurfacing notifier. Resurfacing
/// consumes the shared ledger and never creates a second delivery authority.
actor ContextLedgerResurfacingService {
  static let shared = ContextLedgerResurfacingService()
  private(set) var lastResolvedProvenanceRef: String?

  func observe(_ event: TaskLocalContextEvent, now: Date = Date()) async {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return }
    lastResolvedProvenanceRef = try? await pool.read { db in
      try String.fetchOne(
        db,
        sql: """
            SELECT d.id
            FROM subject_bindings b
            JOIN proactive_deliveries d ON d.bucketID = b.bucketID
            WHERE b.referenceHash = ? AND d.lifecycleState = 'delivered' AND d.expiresAt > ?
            ORDER BY d.deliveredAt DESC LIMIT 1
          """,
        arguments: [event.referenceHash, now])
    }
  }
}
