import XCTest
import GRDB

@testable import Omi_Computer

final class ActionItemsFTSRepairTests: XCTestCase {
  private var testUserId: String!
  private var userDir: URL!

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "action-items-fts-repair-test-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await ActionItemStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    userDir = appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    await ActionItemStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = nil
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    try await super.tearDown()
  }

  func testLocalInsertRepairsMissingActionItemsFTSWithoutDroppingDurableRows() async throws {
    let existing = try await ActionItemStorage.shared.insertLocalActionItem(
      ActionItemRecord(description: "preserve existing durable row", source: "test"))
    XCTAssertNotNil(existing.id)

    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      return XCTFail("database should be initialized")
    }

    try await dbQueue.write { db in
      try db.execute(sql: "DROP TABLE action_items_fts")
    }

    let repaired = try await ActionItemStorage.shared.insertLocalActionItem(
      ActionItemRecord(description: "insert after fts repair", source: "test"))
    XCTAssertNotNil(repaired.id)

    let durableDescriptions = try await dbQueue.read { db in
      try String.fetchAll(
        db,
        sql: "SELECT description FROM action_items ORDER BY id")
    }
    XCTAssertEqual(durableDescriptions, [
      "preserve existing durable row",
      "insert after fts repair"
    ])

    let ftsDescriptions = try await dbQueue.read { db in
      try String.fetchAll(
        db,
        sql: """
          SELECT action_items.description
          FROM action_items_fts
          JOIN action_items ON action_items_fts.rowid = action_items.id
          WHERE action_items_fts MATCH 'repair OR durable'
          ORDER BY action_items.id
          """)
    }
    XCTAssertEqual(ftsDescriptions, durableDescriptions)
  }

  func testRepairRebuildsDroppedActionItemsFTSFromDurableRows() async throws {
    let existing = try await ActionItemStorage.shared.insertLocalActionItem(
      ActionItemRecord(description: "direct repair durable row", source: "test"))
    XCTAssertNotNil(existing.id)

    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      return XCTFail("database should be initialized")
    }

    try await dbQueue.write { db in
      try db.execute(sql: "DROP TABLE action_items_fts")
    }

    try await RewindDatabase.shared.repairActionItemsFTS(in: dbQueue, reason: "direct repair test")

    let matches = try await dbQueue.read { db in
      try String.fetchAll(
        db,
        sql: """
          SELECT action_items.description
          FROM action_items_fts
          JOIN action_items ON action_items_fts.rowid = action_items.id
          WHERE action_items_fts MATCH 'direct'
          ORDER BY action_items.id
          """)
    }
    XCTAssertEqual(matches, ["direct repair durable row"])
  }
}
