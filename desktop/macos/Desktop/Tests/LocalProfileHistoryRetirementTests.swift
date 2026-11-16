import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

/// The retired local profile history is read and dropped by the profile service's salvage,
/// never by a migration: the newest row may be the only copy of an unsynced profile or edit.
final class LocalProfileHistoryRetirementTests: XCTestCase {
  private typealias Retirement = LocalProfileHistoryRetirement

  private let day1 = Date(timeIntervalSince1970: 1_794_817_800)
  private var day2: Date { day1.addingTimeInterval(86_400) }

  // MARK: - Database

  func testContentsReadTheNewestRowOfTheReleasedSchema() throws {
    let queue = try makeReleasedDatabase()
    try queue.write { db in
      try insert(db, text: "older", generatedAt: day1, synced: true)
      try insert(db, text: "newest", generatedAt: day2, synced: false)
    }

    let contents = try queue.read { try Retirement.contents($0) }
    XCTAssertEqual(contents, .history(newest: .init(text: "newest", generatedAt: day2, backendSynced: false)))
  }

  func testContentsDistinguishAnEmptyTableFromARetiredOne() throws {
    let queue = try makeReleasedDatabase()
    XCTAssertEqual(try queue.read { try Retirement.contents($0) }, .history(newest: nil))
    XCTAssertEqual(try DatabaseQueue().read { try Retirement.contents($0) }, .retired)
  }

  func testMalformedNewestRowDoesNotCrash() throws {
    let queue = try makeReleasedDatabase()
    try queue.write { db in
      try db.execute(
        sql: "INSERT INTO ai_user_profiles (profileText, dataSourcesUsed, generatedAt) VALUES ('text', 1, 'yesterday')")
    }
    XCTAssertEqual(try queue.read { try Retirement.contents($0) }, .history(newest: nil))
  }

  func testDropRemovesTheTableAndItsIndexAndKeepsOtherTables() throws {
    let queue = try makeReleasedDatabase()
    try queue.write { db in
      try insert(db, text: "stale", generatedAt: day1, synced: true)
      try db.execute(sql: "CREATE TABLE memories (id TEXT PRIMARY KEY); INSERT INTO memories VALUES ('sentinel');")
      try Retirement.drop(db)
      try Retirement.drop(db)
    }

    try queue.read { db in
      XCTAssertEqual(try Retirement.contents(db), .retired)
      XCTAssertNil(
        try String.fetchOne(db, sql: "SELECT name FROM sqlite_master WHERE name = 'idx_ai_user_profiles_generated'"))
      XCTAssertEqual(try String.fetchOne(db, sql: "SELECT id FROM memories"), "sentinel")
    }
  }

  func testTheChatSchemaPromptNeverListsTheRetiredTable() {
    XCTAssertTrue(ChatPrompts.excludedTables.contains(Retirement.table))
    XCTAssertNil(ChatPrompts.tableAnnotations[Retirement.table])
    XCTAssertNil(ChatPrompts.columnAnnotations[Retirement.table])
  }

  // MARK: - Upload decision

  func testUnsyncedRowNewerThanTheBackendNeedsUpload() {
    let row = Retirement.Row(text: "local", generatedAt: day2, backendSynced: false)
    XCTAssertTrue(row.needsUpload(over: cloud(generatedAt: day1, source: "backend")))
    XCTAssertTrue(row.needsUpload(over: nil), "the backend has no profile at all")
  }

  func testSyncedOrOlderOrBlankRowsDoNotNeedUpload() {
    let synced = Retirement.Row(text: "local", generatedAt: day2, backendSynced: true)
    XCTAssertFalse(synced.needsUpload(over: cloud(generatedAt: day1, source: "backend")))
    XCTAssertFalse(synced.needsUpload(over: nil), "a synced row the backend lacks was deleted there")
    let older = Retirement.Row(text: "local", generatedAt: day1, backendSynced: false)
    XCTAssertFalse(older.needsUpload(over: cloud(generatedAt: day2, source: "backend")))
    let blank = Retirement.Row(text: " \n", generatedAt: day2, backendSynced: false)
    XCTAssertFalse(blank.needsUpload(over: nil))
    let undated = Retirement.Row(text: "local", generatedAt: day2, backendSynced: false)
    XCTAssertFalse(undated.needsUpload(over: cloud(generatedAt: nil, source: "client")))
  }

  /// Released builds edited the row in place and never cleared `backendSynced`, so an edit
  /// whose mirror failed shows as the mirrored generation with different text.
  func testFailedEditOfAMirroredGenerationNeedsUpload() {
    let edited = Retirement.Row(
      text: "my correction", generatedAt: day1.addingTimeInterval(0.0004), backendSynced: true)
    XCTAssertTrue(edited.needsUpload(over: cloud(generatedAt: day1, source: nil)))
    XCTAssertTrue(edited.needsUpload(over: cloud(generatedAt: day1, source: "client")))
    XCTAssertFalse(edited.needsUpload(over: cloud(text: "my correction", generatedAt: day1, source: nil)))
    XCTAssertFalse(
      edited.needsUpload(over: cloud(generatedAt: day1, source: "user_edit")),
      "a profile the current backend or a current client wrote is authoritative")
  }

  // MARK: - Helpers

  private func cloud(text: String = "cloud", generatedAt: Date?, source: String?) -> Retirement.CloudState {
    Retirement.CloudState(text: text, generatedAt: generatedAt, source: source)
  }

  /// The table as released builds created it (migration `createAIUserProfiles`).
  private func makeReleasedDatabase() throws -> DatabaseQueue {
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.create(table: "ai_user_profiles") { t in
        t.autoIncrementedPrimaryKey("id")
        t.column("profileText", .text).notNull()
        t.column("dataSourcesUsed", .integer).notNull()
        t.column("backendSynced", .boolean).notNull().defaults(to: false)
        t.column("generatedAt", .datetime).notNull()
      }
      try db.create(index: "idx_ai_user_profiles_generated", on: "ai_user_profiles", columns: ["generatedAt"])
    }
    return queue
  }

  private func insert(_ db: Database, text: String, generatedAt: Date, synced: Bool) throws {
    try db.execute(
      sql:
        "INSERT INTO ai_user_profiles (profileText, dataSourcesUsed, backendSynced, generatedAt) VALUES (?, 1, ?, ?)",
      arguments: [text, synced, generatedAt])
  }
}
