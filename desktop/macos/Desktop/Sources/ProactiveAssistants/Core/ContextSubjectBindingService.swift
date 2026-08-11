import Foundation
@preconcurrency import GRDB

/// Database-backed replacement for the legacy UserDefaults matcher. Both the
/// flag-on engine and the flag-off rollback path read the migrated binding row,
/// so removing the old defaults key does not change today's behavior.
actor ContextSubjectBindingService {
  static let shared = ContextSubjectBindingService()
  private struct Recent {
    let referenceHash: String
    let occurredAt: Date
  }
  private var recent: Recent?

  func resolve(_ event: TaskLocalContextEvent, now: Date = Date()) async -> TaskLocalContextEvent {
    if [.person, .appWindow, .document].contains(event.kind) {
      recent = Recent(referenceHash: event.referenceHash, occurredAt: event.occurredAt)
    }
    if let subject = event.subject {
      try? await upsert(referenceHash: event.referenceHash, subject: subject, now: now)
      return event
    }
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool,
      let row = try? await pool.read({ db in
        try Row.fetchOne(
          db,
          sql: """
            SELECT subjectKind, subjectID, workstreamID FROM subject_bindings
            WHERE referenceHash = ? AND updatedAt > ?
            """,
          arguments: [event.referenceHash, now.addingTimeInterval(-30 * 24 * 60 * 60)])
      }),
      let kind = OmiAPI.RecommendationSubjectKind(rawValue: row["subjectKind"] as String),
      kind != ._unknown
    else { return event }
    return event.attaching(
      subject: TaskContextSubject(
        kind: kind, id: row["subjectID"], workstreamID: row["workstreamID"]))
  }

  func bindRecentContext(to subject: TaskContextSubject, now: Date = Date()) async {
    guard let recent, now.timeIntervalSince(recent.occurredAt) <= 90 else {
      self.recent = nil
      return
    }
    self.recent = nil
    try? await upsert(referenceHash: recent.referenceHash, subject: subject, now: now)
  }

  func resolveAndObserve(_ event: TaskLocalContextEvent) async {
    let matched = await resolve(event)
    await TaskContextualResurfacingService.shared.observe(matched)
  }

  private func upsert(referenceHash: String, subject: TaskContextSubject, now: Date) async throws {
    guard referenceHash.hasPrefix("sha256:") else { return }
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw ContextBucketStoreError.databaseUnavailable }
    try await pool.write { db in
      try db.execute(
        sql: """
          INSERT INTO subject_bindings
            (referenceHash, subjectKind, subjectID, workstreamID, confidence, source,
             occurrenceCount, createdAt, updatedAt)
          VALUES (?, ?, ?, ?, 1.0, 'explicit_open', 1, ?, ?)
          ON CONFLICT(referenceHash) DO UPDATE SET
            subjectKind = excluded.subjectKind,
            subjectID = excluded.subjectID,
            workstreamID = excluded.workstreamID,
            confidence = 1.0,
            source = 'explicit_open',
            occurrenceCount = subject_bindings.occurrenceCount + 1,
            updatedAt = excluded.updatedAt
          """,
        arguments: [referenceHash, subject.kind.rawValue, subject.id, subject.workstreamID, now, now])
      try db.execute(
        sql: "DELETE FROM subject_bindings WHERE updatedAt <= ?",
        arguments: [now.addingTimeInterval(-30 * 24 * 60 * 60)])
      let overflow = try String.fetchAll(
        db,
        sql: "SELECT referenceHash FROM subject_bindings ORDER BY updatedAt DESC LIMIT -1 OFFSET 256")
      for staleReference in overflow {
        try db.execute(
          sql: "DELETE FROM subject_bindings WHERE referenceHash = ?",
          arguments: [staleReference])
      }
    }
  }
}
