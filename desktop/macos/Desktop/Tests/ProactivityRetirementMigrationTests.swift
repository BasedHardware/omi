import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class ProactivityRetirementMigrationTests: XCTestCase {
  func testUpgradeDetachesBindingsAndPreservesCanonicalAndUserRows() throws {
    let queue = try DatabaseQueue()
    let suite = "retirement-migration-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    try queue.write { db in
      try db.execute(sql: "CREATE TABLE screenshots (id INTEGER PRIMARY KEY)")
    }
    var migrator = DatabaseMigrator()
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: "fixture")
    JITTriggerMirrorSchema.registerMigration(on: &migrator)
    try migrator.migrate(queue)
    let kept = ["proactive_extractions", "focus_sessions", "memories", "live_notes", "goals"]
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets (id, subjectKind, subjectID, createdAt, updatedAt)
          VALUES ('bucket-1', 'task', 'task-1', '2026-10-01', '2026-10-02');
          INSERT INTO subject_bindings
            (referenceHash, bucketID, subjectKind, subjectID, confidence, source, occurrenceCount, createdAt, updatedAt)
          VALUES ('reference', 'bucket-1', 'task', 'task-1', 0.9, 'fixture', 3, '2026-10-01', '2026-10-02')
          """)
      try db.execute(
        sql: """
          INSERT INTO jit_knowledge_ledger_mirror_members
            (ownerID, memoryID, itemRevision, status, sourceState, canonicalMemoryID, contentPurged)
          VALUES ('fixture', 'memory-1', 7, 'active', 'ledger', 'memory-1', 0);
          INSERT INTO jit_knowledge_ledger_mirror_aliases
            (ownerID, aliasMemoryID, canonicalMemoryID, sourceMemoryID, reason)
          VALUES ('fixture', 'alias-1', 'memory-1', 'memory-1', 'fixture')
          """)
      for table in kept {
        try db.execute(sql: "CREATE TABLE \(table) (id TEXT PRIMARY KEY); INSERT INTO \(table) VALUES ('sentinel')")
      }
    }
    ProactivityRetirementMigration.registerMigration(on: &migrator)
    try migrator.migrate(queue)
    try migrator.migrate(queue)
    try queue.read { db in
      for table in ProactivityRetirementMigration.retiredTables {
        XCTAssertFalse(try db.tableExists(table), table)
      }
      for table in kept {
        XCTAssertEqual(try String.fetchOne(db, sql: "SELECT id FROM \(table)"), "sentinel")
      }
      for table in [
        "jit_knowledge_ledger_mirror_receipts", "jit_knowledge_ledger_mirror_members",
        "jit_knowledge_ledger_mirror_aliases",
      ] {
        XCTAssertTrue(try db.tableExists(table), table)
      }
      XCTAssertEqual(
        try Int.fetchOne(
          db, sql: "SELECT itemRevision FROM jit_knowledge_ledger_mirror_members WHERE memoryID = 'memory-1'"), 7)
      XCTAssertEqual(
        try String.fetchOne(
          db, sql: "SELECT canonicalMemoryID FROM jit_knowledge_ledger_mirror_aliases WHERE aliasMemoryID = 'alias-1'"),
        "memory-1")
      let binding = try XCTUnwrap(Row.fetchOne(db, sql: "SELECT * FROM subject_bindings"))
      XCTAssertEqual(binding["subjectID"] as String, "task-1")
      XCTAssertEqual(binding["occurrenceCount"] as Int, 3)
      XCTAssertEqual(binding["confidence"] as Double, 0.9)
      XCTAssertNil(binding["bucketID"] as String?)
      XCTAssertTrue(try Row.fetchAll(db, sql: "PRAGMA foreign_key_list(subject_bindings)").isEmpty)
      XCTAssertTrue(try Row.fetchAll(db, sql: "PRAGMA foreign_key_check").isEmpty)
    }
  }

  func testFreshDatabaseWithoutRetiredTablesIsSafe() throws {
    let queue = try DatabaseQueue()
    var migrator = DatabaseMigrator()
    ProactivityRetirementMigration.registerMigration(on: &migrator)
    try migrator.migrate(queue)
    try migrator.migrate(queue)
  }
}
