import Foundation
@preconcurrency import GRDB

/// Database-backed replacement for the legacy UserDefaults matcher. Both the
/// flag-on engine and the flag-off rollback path read the migrated binding row,
/// so removing the old defaults key does not change today's behavior.
/// SQL retention rules for subject bindings. Kept separate from the actor so age
/// and overflow protection remain directly testable without RewindDatabase.
enum ContextSubjectBindingRetention {
  /// Drop only unbound rows. Bindings that still point at a bucket power visit
  /// lookup and snapshots, so age/overflow must not remove them.
  static func prune(in db: Database, now: Date) throws {
    try db.execute(
      sql: "DELETE FROM subject_bindings WHERE bucketID IS NULL AND updatedAt <= ?",
      arguments: [now.addingTimeInterval(-30 * 24 * 60 * 60)])
    let overflow = try String.fetchAll(
      db,
      sql: """
        SELECT referenceHash FROM subject_bindings
        WHERE bucketID IS NULL
        ORDER BY updatedAt DESC
        LIMIT -1 OFFSET 256
        """)
    for staleReference in overflow {
      try db.execute(
        sql: "DELETE FROM subject_bindings WHERE referenceHash = ?",
        arguments: [staleReference])
    }
  }
}

actor ContextSubjectBindingService {
  static let shared = ContextSubjectBindingService()

  private struct Binding: Decodable, FetchableRecord, Sendable {
    let subjectKind: String
    let subjectID: String
    let workstreamID: String?
  }

  private struct Recent {
    let referenceHash: String
    let occurredAt: Date
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  }
  private var recent: Recent?

  func resolve(
    _ event: TaskLocalContextEvent,
    now: Date = Date(),
    authorizationSnapshot suppliedAuthorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async -> TaskLocalContextEvent {
    guard
      let authorizationSnapshot = suppliedAuthorizationSnapshot
        ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot(),
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    else {
      recent = nil
      return event
    }
    if [.person, .appWindow, .document].contains(event.kind) {
      recent = Recent(
        referenceHash: event.referenceHash,
        occurredAt: event.occurredAt,
        authorizationSnapshot: authorizationSnapshot)
    }
    if let subject = event.subject {
      try? await upsert(
        referenceHash: event.referenceHash,
        subject: subject,
        now: now,
        authorizationSnapshot: authorizationSnapshot)
      return event
    }
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool, RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      let binding = try? await pool.read({ db in
        try Binding.fetchOne(
          db,
          sql: """
            SELECT subjectKind, subjectID, workstreamID FROM subject_bindings
            WHERE referenceHash = ? AND updatedAt > ?
            """,
          arguments: [event.referenceHash, now.addingTimeInterval(-30 * 24 * 60 * 60)])
      }),
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      let kind = OmiAPI.RecommendationSubjectKind(rawValue: binding.subjectKind),
      kind != ._unknown
    else { return event }
    return event.attaching(
      subject: TaskContextSubject(
        kind: kind, id: binding.subjectID, workstreamID: binding.workstreamID))
  }

  func bindRecentContext(to subject: TaskContextSubject, now: Date = Date()) async {
    guard
      let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(),
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      let recent,
      recent.authorizationSnapshot == authorizationSnapshot,
      now.timeIntervalSince(recent.occurredAt) <= 90
    else {
      self.recent = nil
      return
    }
    self.recent = nil
    try? await upsert(
      referenceHash: recent.referenceHash,
      subject: subject,
      now: now,
      authorizationSnapshot: authorizationSnapshot)
  }

  func resolveAndObserve(_ event: TaskLocalContextEvent) async {
    guard let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return }
    let matched = await resolve(event, authorizationSnapshot: authorizationSnapshot)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    await TaskContextualResurfacingService.shared.observe(matched)
  }

  private func upsert(
    referenceHash: String,
    subject: TaskContextSubject,
    now: Date,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws {
    guard
      referenceHash.hasPrefix("sha256:"),
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    else { return }
    let (pool, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw ContextBucketStoreError.databaseUnavailable }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    let mutationAuthorization = LocalMutationAuthorization {
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    }
    try await mutationAuthorization.withCommitLease {
      let (_, currentPoolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
      guard currentPoolEpoch == poolEpoch else {
        throw ContextBucketStoreError.staleFence
      }
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
        try ContextSubjectBindingRetention.prune(in: db, now: now)
      }
    }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
  }
}
