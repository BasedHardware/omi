import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class LocalProfileHistoryRetirementMigrationTests: XCTestCase {
  func testUpgradeDropsTheProfileHistoryAndKeepsOtherTables() throws {
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.execute(
        sql: """
          CREATE TABLE ai_user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, profileText TEXT NOT NULL,
            dataSourcesUsed INTEGER NOT NULL, backendSynced BOOLEAN NOT NULL DEFAULT 0,
            generatedAt DATETIME NOT NULL);
          CREATE INDEX idx_ai_user_profiles_generated ON ai_user_profiles(generatedAt);
          INSERT INTO ai_user_profiles (profileText, dataSourcesUsed, generatedAt)
          VALUES ('stale profile', 3, '2026-11-01');
          CREATE TABLE memories (id TEXT PRIMARY KEY);
          INSERT INTO memories VALUES ('sentinel');
          """)
    }
    var migrator = DatabaseMigrator()
    LocalProfileHistoryRetirementMigration.registerMigration(on: &migrator)
    try migrator.migrate(queue)
    try migrator.migrate(queue)

    try queue.read { db in
      XCTAssertFalse(try db.tableExists(LocalProfileHistoryRetirementMigration.retiredTable))
      XCTAssertNil(
        try String.fetchOne(
          db, sql: "SELECT name FROM sqlite_master WHERE name = 'idx_ai_user_profiles_generated'"))
      XCTAssertEqual(try String.fetchOne(db, sql: "SELECT id FROM memories"), "sentinel")
    }
  }

  func testFreshDatabaseWithoutTheTableIsSafe() throws {
    let queue = try DatabaseQueue()
    var migrator = DatabaseMigrator()
    LocalProfileHistoryRetirementMigration.registerMigration(on: &migrator)
    try migrator.migrate(queue)
    try migrator.migrate(queue)
  }
}
