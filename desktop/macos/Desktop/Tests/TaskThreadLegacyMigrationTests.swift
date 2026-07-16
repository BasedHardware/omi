import GRDB
import XCTest

@testable import Omi_Computer

@MainActor
final class TaskThreadLegacyMigrationTests: XCTestCase {
  private var testUserID: String!
  private var userDirectory: URL!

  override func setUp() async throws {
    try await super.setUp()
    testUserID = "task-thread-migration-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await TaskChatMessageStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = testUserID
    await RewindDatabase.shared.configure(userId: testUserID)
    try await RewindDatabase.shared.initialize()
    let appSupport = FileManager.default.urls(
      for: .applicationSupportDirectory,
      in: .userDomainMask
    ).first!
    userDirectory =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserID, isDirectory: true)
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    await TaskChatMessageStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = nil
    if let userDirectory { try? FileManager.default.removeItem(at: userDirectory) }
    try await super.tearDown()
  }

  func testLegacyImportPagesAllImmutableRowsAndRemainsReadOnly() async throws {
    let databaseQueue = await RewindDatabase.shared.getDatabaseQueue()
    let db = try XCTUnwrap(databaseQueue)
    try await db.write { database in
      for index in 0..<235 {
        let sourceTaskID = index < 130 ? "legacy-task-a" : "legacy-task-b"
        try database.execute(
          sql: """
              INSERT INTO task_chat_messages (
                taskId, messageId, sender, messageText, createdAt, updatedAt, backendSynced
              ) VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
          arguments: [
            sourceTaskID,
            "message-\(index)",
            index.isMultiple(of: 2) ? "user" : "ai",
            "bounded message \(index)",
            Date(timeIntervalSince1970: TimeInterval(index)),
            Date(timeIntervalSince1970: TimeInterval(index)),
          ]
        )
      }
    }

    var cursor: TaskChatLegacyMessageCursor?
    var pageSizes: [Int] = []
    var imported: [TaskChatMessageRecord] = []
    while true {
      let page = try await TaskChatMessageStorage.shared.legacyMessagePage(
        fromTaskIds: ["legacy-task-a", "legacy-task-b"],
        workstreamId: "workstream-1",
        after: cursor
      )
      pageSizes.append(page.rows.count)
      imported.append(contentsOf: page.rows)
      guard page.rows.count == TaskChatLegacyCompatibilityMetadata.pageSize,
        let nextCursor = page.nextCursor
      else { break }
      cursor = nextCursor
    }
    let (legacyA, legacyB, workstreamCount) = try await db.read { database in
      let legacyA = try String.fetchAll(
        database,
        sql: "SELECT messageId FROM task_chat_messages WHERE taskId = ? ORDER BY createdAt, id",
        arguments: ["legacy-task-a"]
      )
      let legacyB = try String.fetchAll(
        database,
        sql: "SELECT messageId FROM task_chat_messages WHERE taskId = ? ORDER BY createdAt, id",
        arguments: ["legacy-task-b"]
      )
      let workstreamCount =
        try Int.fetchOne(
          database,
          sql: "SELECT COUNT(*) FROM task_chat_messages WHERE taskId = ?",
          arguments: ["workstream-1"]
        ) ?? 0
      return (legacyA, legacyB, workstreamCount)
    }

    XCTAssertEqual(pageSizes, [100, 100, 35])
    XCTAssertEqual(imported.map(\.messageId), (0..<235).map { "message-\($0)" })
    XCTAssertEqual(legacyA, (0..<130).map { "message-\($0)" })
    XCTAssertEqual(legacyB, (130..<235).map { "message-\($0)" })
    XCTAssertEqual(workstreamCount, 0, "compatibility import must not re-key or mutate legacy rows")
    XCTAssertEqual(TaskChatLegacyCompatibilityMetadata.owner, "desktop-task-chat")
    XCTAssertFalse(TaskChatLegacyCompatibilityMetadata.removalCondition.isEmpty)
    XCTAssertEqual(TaskChatLegacyCompatibilityMetadata.removeBy, "2026-10-01")
  }
}
