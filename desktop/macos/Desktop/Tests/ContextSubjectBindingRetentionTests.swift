import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class ContextSubjectBindingRetentionTests: XCTestCase {
  func testPruneRetainsBucketBackedBindingsThroughAgeAndOverflow() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    let stale = now.addingTimeInterval(-31 * 24 * 60 * 60)
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, createdAt, updatedAt)
          VALUES ('live-bucket', 'task', 'task-live', ?, ?)
          """,
        arguments: [now, now])
      try db.execute(
        sql: """
          INSERT INTO subject_bindings
            (referenceHash, bucketID, subjectKind, subjectID, confidence, source,
             occurrenceCount, createdAt, updatedAt)
          VALUES
            ('sha256:bucket-backed', 'live-bucket', 'task', 'task-live', 1.0, 'explicit_open', 1, ?, ?),
            ('sha256:stale-unbound', NULL, 'task', 'task-old', 1.0, 'explicit_open', 1, ?, ?)
          """,
        arguments: [stale, stale, stale, stale])

      for index in 0..<260 {
        let stamp = now.addingTimeInterval(TimeInterval(-index))
        try db.execute(
          sql: """
            INSERT INTO subject_bindings
              (referenceHash, subjectKind, subjectID, confidence, source,
               occurrenceCount, createdAt, updatedAt)
            VALUES (?, 'task', ?, 1.0, 'explicit_open', 1, ?, ?)
            """,
          arguments: [
            String(format: "sha256:overflow-%03d", index),
            "task-\(index)",
            stamp,
            stamp,
          ])
      }

      try ContextSubjectBindingRetention.prune(in: db, now: now)

      XCTAssertEqual(
        try String.fetchOne(
          db, sql: "SELECT bucketID FROM subject_bindings WHERE referenceHash = 'sha256:bucket-backed'"),
        "live-bucket")
      XCTAssertNil(
        try Row.fetchOne(
          db, sql: "SELECT 1 FROM subject_bindings WHERE referenceHash = 'sha256:stale-unbound'"))
      let unboundCount =
        try Int.fetchOne(
          db, sql: "SELECT COUNT(*) FROM subject_bindings WHERE bucketID IS NULL") ?? -1
      XCTAssertEqual(unboundCount, 256)
      XCTAssertEqual(
        try Int.fetchOne(
          db, sql: "SELECT COUNT(*) FROM subject_bindings WHERE referenceHash = 'sha256:bucket-backed'")
          ?? 0,
        1)
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
      UserDefaults(suiteName: "ContextSubjectBindingRetentionTests.\(UUID().uuidString)"))
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: "owner")
    try migrator.migrate(queue)
    return queue
  }
}
