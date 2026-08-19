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

  func testMigrationAddsWorkstreamTagColumnToBucketFacts() throws {
    let suiteName = "ContextBucketSchemaTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let queue = try DatabaseQueue()
    try createBaseScreenshotsTable(in: queue)
    var migrator = DatabaseMigrator()
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: "owner-1")
    try migrator.migrate(queue)
    let columns = try queue.read { db in
      try db.columns(in: "bucket_facts").map(\.name)
    }
    XCTAssertTrue(columns.contains("workstreamTag"))
    let indexes = try queue.read { db in
      try String.fetchAll(
        db, sql: "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'bucket_facts'")
    }
    XCTAssertTrue(indexes.contains("idx_bucket_facts_workstream"))
  }

  func testMigrationCreatesWorkstreamAssignmentsAndCandidateTables() throws {
    let queue = try migratedQueue()
    let tables = try queue.read { db in
      Set(try String.fetchAll(db, sql: "SELECT name FROM sqlite_master WHERE type = 'table'"))
    }
    XCTAssertTrue(tables.contains("bucket_workstreams"))
    XCTAssertTrue(tables.contains("proactive_candidates"))
    let workstreamColumns = try queue.read { db in
      try db.columns(in: "bucket_workstreams").map(\.name)
    }
    XCTAssertEqual(
      Set(workstreamColumns),
      ["id", "bucketID", "tag", "source", "assignedAt"])
    let candidateColumns = try queue.read { db in
      try db.columns(in: "proactive_candidates").map(\.name)
    }
    XCTAssertEqual(
      Set(candidateColumns),
      [
        "id", "bucketID", "workstreamTag", "message", "groundingFactIDsJson", "triggerNote",
        "state", "createdAt", "expiresAt", "consumedAt",
      ])
    let indexes = try queue.read { db in
      Set(
        try String.fetchAll(
          db, sql: "SELECT name FROM sqlite_master WHERE type = 'index'"))
    }
    XCTAssertTrue(indexes.contains("idx_bucket_workstreams_tag"))
    XCTAssertTrue(indexes.contains("idx_proactive_candidates_lookup"))
    XCTAssertTrue(indexes.contains("idx_proactive_candidates_workstream"))
    let factColumns = try queue.read { db in
      try db.columns(in: "bucket_facts").map(\.name)
    }
    XCTAssertTrue(
      factColumns.contains("workstreamTag"),
      "the dormant fact-level column must survive this migration")
  }

  func testAnonymousDatabaseUsesSignedOutLegacyOwnerNamespace() throws {
    let suiteName = "ContextBucketSchemaTests.anonymous.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let updatedAt = Date(timeIntervalSince1970: 1_725_000_000)
    defaults.set(
      try JSONEncoder().encode([
        LegacyBinding(
          referenceHash: "sha256:signed-out",
          subjectKind: "task",
          subjectID: "task-anonymous",
          workstreamID: nil,
          updatedAt: updatedAt)
      ]),
      forKey: ContextBucketSchema.legacyDefaultsKey(ownerID: "signed-out"))

    let queue = try DatabaseQueue()
    try createBaseScreenshotsTable(in: queue)
    var migrator = DatabaseMigrator()
    // The database was initialized under anonymous, then retargeted to the
    // real owner. The physical move supplies signed-out as the fallback source.
    ContextBucketSchema.registerMigration(
      on: &migrator,
      defaults: defaults,
      ownerID: "real-owner",
      fallbackOwnerID: "signed-out")
    try migrator.migrate(queue)
    let subjectID = try queue.read { db in
      try String.fetchOne(db, sql: "SELECT subjectID FROM subject_bindings")
    }
    XCTAssertEqual(subjectID, "task-anonymous")
    try ContextBucketSchema.removeMigratedLegacyDefaults(
      afterMigrating: queue, defaults: defaults, ownerID: "real-owner")
    XCTAssertNil(defaults.data(forKey: ContextBucketSchema.legacyDefaultsKey(ownerID: "signed-out")))
  }

  func testPrimaryOwnerSourceWinsOverSignedOutFallback() throws {
    let suiteName = "ContextBucketSchemaTests.primary-fallback.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let updatedAt = Date(timeIntervalSince1970: 1_725_000_000)
    let makeBinding: (String, String) throws -> Data = { referenceHash, subjectID in
      try JSONEncoder().encode([
        LegacyBinding(
          referenceHash: referenceHash,
          subjectKind: "task",
          subjectID: subjectID,
          workstreamID: nil,
          updatedAt: updatedAt)
      ])
    }
    defaults.set(
      try makeBinding("sha256:real", "task-real"),
      forKey: ContextBucketSchema.legacyDefaultsKey(ownerID: "real-owner"))
    defaults.set(
      try makeBinding("sha256:signed-out", "task-signed-out"),
      forKey: ContextBucketSchema.legacyDefaultsKey(ownerID: "signed-out"))

    let queue = try DatabaseQueue()
    try createBaseScreenshotsTable(in: queue)
    var migrator = DatabaseMigrator()
    ContextBucketSchema.registerMigration(
      on: &migrator,
      defaults: defaults,
      ownerID: "real-owner",
      fallbackOwnerID: "signed-out")
    try migrator.migrate(queue)

    let subjectID = try queue.read { db in
      try String.fetchOne(db, sql: "SELECT subjectID FROM subject_bindings")
    }
    XCTAssertEqual(subjectID, "task-real")
    try ContextBucketSchema.removeMigratedLegacyDefaults(
      afterMigrating: queue, defaults: defaults, ownerID: "real-owner")
    XCTAssertNil(defaults.data(forKey: ContextBucketSchema.legacyDefaultsKey(ownerID: "real-owner")))
    XCTAssertNotNil(defaults.data(forKey: ContextBucketSchema.legacyDefaultsKey(ownerID: "signed-out")))
  }

  func testLateLegacyWritesRemainWhenMigrationConsumedNoSource() throws {
    let suiteName = "ContextBucketSchemaTests.late-write.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let queue = try DatabaseQueue()
    try createBaseScreenshotsTable(in: queue)
    var migrator = DatabaseMigrator()
    let ownerID = "owner-late"
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: ownerID)
    try migrator.migrate(queue)
    let updatedAt = Date(timeIntervalSince1970: 1_725_000_000)
    defaults.set(
      try JSONEncoder().encode([
        LegacyBinding(
          referenceHash: "sha256:late",
          subjectKind: "task",
          subjectID: "task-late",
          workstreamID: nil,
          updatedAt: updatedAt)
      ]),
      forKey: ContextBucketSchema.legacyDefaultsKey(ownerID: ownerID))
    try ContextBucketSchema.removeMigratedLegacyDefaults(
      afterMigrating: queue, defaults: defaults, ownerID: ownerID)
    XCTAssertNotNil(defaults.data(forKey: ContextBucketSchema.legacyDefaultsKey(ownerID: ownerID)))
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

  func testExpiredAndTerminalCandidatesAreDeletedByRetentionSweep() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets (id, subjectKind, subjectID, createdAt, updatedAt)
          VALUES ('bucket', 'task', 'task-1', ?, ?)
          """,
        arguments: [now, now])
      for (id, state, expiry) in [
        ("armed-live", "armed", now.addingTimeInterval(60)),
        ("armed-expired", "armed", now.addingTimeInterval(-1)),
        ("consumed", "consumed", now.addingTimeInterval(60)),
      ] {
        try db.execute(
          sql: """
            INSERT INTO proactive_candidates
              (id, bucketID, message, groundingFactIDsJson, triggerNote, state,
               createdAt, expiresAt)
            VALUES (?, 'bucket', 'message', '[]', 'when relevant', ?, ?, ?)
            """,
          arguments: [id, state, now, expiry])
      }
      XCTAssertEqual(try ContextBucketSchema.deleteExpiredProactiveCandidates(in: db, now: now), 2)
    }
    let remaining = try queue.read { db in
      try String.fetchAll(db, sql: "SELECT id FROM proactive_candidates ORDER BY id")
    }
    XCTAssertEqual(remaining, ["armed-live"])
  }

  func testDerivedDataEgressIsDefaultDenyAndContextTablesStayOutOfAgentSync() throws {
    XCTAssertTrue(ContextBucketSchema.tableNames.isDisjoint(with: AgentSyncService.syncedTableNames))

    XCTAssertEqual(DerivedDataEgressPolicy.declarations.count, DerivedDataClass.allCases.count)
    XCTAssertEqual(
      DerivedDataClass.allCases.filter {
        if case .allow = DerivedDataEgressPolicy.decision(for: $0) { return true }
        return false
      },
      [.meetingIdentity])
    XCTAssertTrue(
      DerivedDataEgressPolicy.declaredRoutes.allSatisfy {
        if case .allow = DerivedDataEgressPolicy.decision(for: $0.dataClass) { return true }
        return false
      })
    XCTAssertEqual(
      Set(DerivedDataEgressPolicy.declaredRoutes.map(\.route)),
      Set(DerivedDataEgressRoute.allCases),
      "A new derived-data route must be declared in the policy before it can pass CI")

    let denied = DerivedDataEgressRequest(
      dataClass: .contextBucketFacts,
      route: .calendarMeetings,
      purpose: DerivedDataEgressPolicy.meetingIdentityPurpose)
    XCTAssertThrowsError(try DerivedDataEgressPolicy.authorize(denied)) { error in
      XCTAssertEqual(error as? DerivedDataEgressPolicyError, .denied(.contextBucketFacts))
    }
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
