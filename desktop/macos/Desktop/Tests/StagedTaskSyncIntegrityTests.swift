import GRDB
import XCTest

@testable import Omi_Computer

final class StagedTaskSyncIntegrityTests: XCTestCase {
  private var testUserId: String!
  private var userDir: URL!

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "staged-sync-test-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await StagedTaskStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    userDir =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    await StagedTaskStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = nil
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    try await super.tearDown()
  }

  func testMarkSyncedIsIdempotentWhenBackendIdAlreadyExists() async throws {
    let backendId = "backend-task-\(UUID().uuidString)"

    let canonical = try await StagedTaskStorage.shared.insertLocalStagedTask(
      StagedTaskRecord(
        backendId: backendId,
        backendSynced: true,
        description: "Canonical backend task",
        createdAt: Date().addingTimeInterval(-10),
        updatedAt: Date().addingTimeInterval(-10)))

    let duplicate = try await StagedTaskStorage.shared.insertLocalStagedTask(
      StagedTaskRecord(
        description: "Local duplicate awaiting sync",
        createdAt: Date(),
        updatedAt: Date()))

    guard let canonicalId = canonical.id, let duplicateId = duplicate.id else {
      return XCTFail("inserted staged tasks should have local ids")
    }

    try await StagedTaskStorage.shared.markSynced(id: duplicateId, backendId: backendId)

    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      return XCTFail("database should be initialized")
    }

    let rows = try await dbQueue.read { db in
      try Row.fetchAll(
        db,
        sql: "SELECT id, backendId, backendSynced FROM staged_tasks WHERE backendId = ?",
        arguments: [backendId])
    }
    XCTAssertEqual(rows.count, 1)
    XCTAssertEqual(rows[0]["id"] as? Int64, canonicalId)
    // backendSynced is a Bool stored as SQLite INTEGER (1); read it as Int64 to avoid a
    // failing `as? Bool` bridge on the raw column value.
    XCTAssertEqual(rows[0]["backendSynced"] as? Int64, 1)

    let duplicateExists = try await dbQueue.read { db in
      try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM staged_tasks WHERE id = ?", arguments: [duplicateId]) ?? 0
    }
    XCTAssertEqual(duplicateExists, 0)
  }
}
