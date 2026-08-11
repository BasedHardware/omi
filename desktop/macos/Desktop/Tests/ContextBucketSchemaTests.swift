import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class ContextBucketSchemaTests: XCTestCase {
  private struct LegacyBinding: Codable {
    let referenceHash: String
    let subjectKind: String
    let subjectID: String
    let workstreamID: String?
    let updatedAt: Date
  }

  func testMigrationCreatesTablesAndMovesLegacyBindings() throws {
    let suiteName = "ContextBucketSchemaTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let ownerID = "owner-1"
    let updatedAt = Date(timeIntervalSince1970: 1_725_000_000)
    defaults.set(
      try JSONEncoder().encode([
        LegacyBinding(
          referenceHash: "sha256:reference",
          subjectKind: "task",
          subjectID: "task-7",
          workstreamID: "workstream-2",
          updatedAt: updatedAt)
      ]),
      forKey: ContextBucketSchema.legacyDefaultsKey(ownerID: ownerID))

    let queue = try DatabaseQueue()
    try createBaseScreenshotsTable(in: queue)
    var migrator = DatabaseMigrator()
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: ownerID)
    try migrator.migrate(queue)
    try ContextBucketSchema.removeMigratedLegacyDefaults(
      afterMigrating: queue,
      defaults: defaults,
      ownerID: ownerID)

    let tables = try queue.read { db in
      Set(try String.fetchAll(db, sql: "SELECT name FROM sqlite_master WHERE type = 'table'"))
    }
    XCTAssertTrue(ContextBucketSchema.tableNames.isSubset(of: tables))
    let row = try queue.read { db in
      try Row.fetchOne(
        db, sql: "SELECT * FROM subject_bindings WHERE referenceHash = ?", arguments: ["sha256:reference"])
    }
    XCTAssertEqual(row?["subjectID"], "task-7")
    XCTAssertEqual(row?["workstreamID"], "workstream-2")
    XCTAssertNil(defaults.data(forKey: ContextBucketSchema.legacyDefaultsKey(ownerID: ownerID)))
  }

  func testDeliveryTTLDeletesOnlyExpiredRows() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    try queue.write { db in
      for (id, expiry) in [("expired", now.addingTimeInterval(-1)), ("live", now.addingTimeInterval(60))] {
        try db.execute(
          sql: """
            INSERT INTO proactive_deliveries
              (id, decisionType, lifecycleState, provenanceJson, attemptedAt, expiresAt, createdAt)
            VALUES (?, 'silence', 'attempted', '{}', ?, ?, ?)
            """,
          arguments: [id, now, expiry, now])
      }
      XCTAssertEqual(try ContextBucketSchema.deleteExpiredDeliveries(in: db, now: now), 1)
    }
    let remaining = try queue.read { db in
      try String.fetchAll(db, sql: "SELECT id FROM proactive_deliveries ORDER BY id")
    }
    XCTAssertEqual(remaining, ["live"])
  }

  func testContextTablesAreExcludedFromAgentSync() {
    XCTAssertTrue(ContextBucketSchema.tableNames.isDisjoint(with: AgentSyncService.syncedTableNames))
  }

  func testOneBucketPerDurableSubjectWhenWorkstreamIsNil() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, workstreamID, createdAt, updatedAt)
          VALUES ('first', 'task', 'task-7', NULL, ?, ?)
          """,
        arguments: [now, now])
      XCTAssertThrowsError(
        try db.execute(
          sql: """
            INSERT INTO context_buckets
              (id, subjectKind, subjectID, workstreamID, createdAt, updatedAt)
            VALUES ('duplicate', 'task', 'task-7', NULL, ?, ?)
            """,
          arguments: [now, now]))
    }
  }

  private func migratedQueue() throws -> DatabaseQueue {
    let queue = try DatabaseQueue()
    try createBaseScreenshotsTable(in: queue)
    var migrator = DatabaseMigrator()
    let defaults = try XCTUnwrap(UserDefaults(suiteName: "ContextBucketSchemaTests.empty.\(UUID().uuidString)"))
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: "owner")
    try migrator.migrate(queue)
    return queue
  }

  private func createBaseScreenshotsTable(in queue: DatabaseQueue) throws {
    try queue.write { db in
      try db.create(table: "screenshots") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("timestamp", .datetime).notNull()
        table.column("appName", .text).notNull()
      }
    }
  }
}
