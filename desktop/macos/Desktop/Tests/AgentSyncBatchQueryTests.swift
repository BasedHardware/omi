import XCTest

@testable import Omi_Computer

/// Regression test for the AgentSync mutable-table pagination skip: paging with a
/// strict `updatedAt > ?` cursor drops every row past the first batch when more
/// than `batchSize` rows share the same `updatedAt` (a bulk update touching >100
/// rows in one second), silently diverging the VM's copy. Mutable tables must page
/// on a compound `(updatedAt, id)` cursor.
final class AgentSyncBatchQueryTests: XCTestCase {

  func testMutableTableUsesCompoundCursor() {
    let (sql, args) = AgentSyncService.buildBatchQuery(
      tableName: "action_items",
      selectCols: "\"id\", \"updatedAt\"",
      appendOnly: false,
      lastId: 42,
      lastUpdatedAt: "2026-04-09T12:00:00",
      batchSize: 100
    )

    // Must include the compound clause and id-tiebreaker ordering — not a bare
    // strict `updatedAt > ?` that would skip same-timestamp rows.
    XCTAssertTrue(sql.contains("updatedAt > ? OR (updatedAt = ? AND id > ?)"), sql)
    XCTAssertTrue(sql.contains("ORDER BY updatedAt ASC, id ASC"), sql)
    XCTAssertEqual(
      args,
      [.text("2026-04-09T12:00:00"), .text("2026-04-09T12:00:00"), .int(42), .int(100)])
  }

  func testAppendOnlyTablePagesById() {
    let (sql, args) = AgentSyncService.buildBatchQuery(
      tableName: "screenshots",
      selectCols: "\"id\"",
      appendOnly: true,
      lastId: 7,
      lastUpdatedAt: "1970-01-01T00:00:00",
      batchSize: 100
    )

    XCTAssertTrue(sql.contains("WHERE id > ? ORDER BY id ASC"), sql)
    XCTAssertFalse(sql.contains("updatedAt"), sql)
    XCTAssertEqual(args, [.int(7), .int(100)])
  }
}
