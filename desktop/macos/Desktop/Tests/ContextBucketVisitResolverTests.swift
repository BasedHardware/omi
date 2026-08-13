import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class ContextBucketVisitResolverTests: XCTestCase {
  func testExplicitRebindAttachesCurrentSubjectBucketNotStalePointer() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    let referenceHash = "sha256:window"
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, workstreamID, createdAt, updatedAt)
          VALUES
            ('bucket-a', 'task', 'task-a', NULL, ?, ?),
            ('bucket-b', 'task', 'task-b', NULL, ?, ?)
          """,
        arguments: [now, now, now, now])
      try db.execute(
        sql: """
          INSERT INTO subject_bindings
            (referenceHash, bucketID, subjectKind, subjectID, confidence, source,
             occurrenceCount, createdAt, updatedAt)
          VALUES (?, 'bucket-a', 'task', 'task-b', 1.0, 'explicit_open', 2, ?, ?)
          """,
        arguments: [referenceHash, now, now])

      let resolved = try ContextBucketVisitResolver.resolveBucketID(
        in: db,
        referenceHash: referenceHash,
        normalizedTitle: "Shared window",
        startedAt: now)
      XCTAssertEqual(resolved, "bucket-b")
      XCTAssertEqual(
        try String.fetchOne(
          db, sql: "SELECT bucketID FROM subject_bindings WHERE referenceHash = ?",
          arguments: [referenceHash]),
        "bucket-b")
    }
  }

  func testActiveVisitKeepsOriginalBucketAfterSubjectRebind() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, workstreamID, createdAt, updatedAt)
          VALUES
            ('bucket-original', 'context', 'subject-a', NULL, ?, ?),
            ('bucket-new', 'task', 'task-b', NULL, ?, ?)
          """,
        arguments: [now, now, now, now])
      try db.execute(
        sql: """
          INSERT INTO context_visits
            (contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
          VALUES (7, 11, 'bucket-original', 'Browser', 'Window', 'browser::window',
                  'sha256:window', ?, 'active', ?, ?)
          """,
        arguments: [now, now, now])
      let visitID = db.lastInsertedRowID

      // A later explicit rebind changes the subject binding, not the durable
      // bucket identity captured by this already-active visit.
      try db.execute(
        sql: """
          INSERT INTO subject_bindings
            (referenceHash, bucketID, subjectKind, subjectID, confidence, source,
             occurrenceCount, createdAt, updatedAt)
          VALUES ('sha256:window', 'bucket-new', 'task', 'task-b', 1.0,
                  'explicit_open', 1, ?, ?)
          """,
        arguments: [now, now])

      XCTAssertEqual(
        try ContextBucketVisitResolver.persistedBucketID(
          in: db,
          visitID: visitID,
          contextGeneration: 7,
          poolEpoch: 11),
        "bucket-original")
      XCTAssertNil(
        try ContextBucketVisitResolver.persistedBucketID(
          in: db,
          visitID: visitID,
          contextGeneration: 8,
          poolEpoch: 11))
    }
  }

  private func migratedQueue() throws -> DatabaseQueue {
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.create(table: "screenshots") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("timestamp", .datetime).notNull()
        table.column("appName", .text).notNull()
      }
    }
    var migrator = DatabaseMigrator()
    let defaults = try XCTUnwrap(
      UserDefaults(suiteName: "ContextBucketVisitResolverTests.\(UUID().uuidString)"))
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: "owner")
    try migrator.migrate(queue)
    return queue
  }
}
