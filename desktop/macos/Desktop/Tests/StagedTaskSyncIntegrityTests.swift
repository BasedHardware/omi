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

  func testRevocationInsideInsertTransactionRollsBackForOwnerSwapAndSameUIDReauthorization() async throws {
    for sameUID in [false, true] {
      let probe = StorageRevocationProbe(owner: testUserId, sameUID: sameUID)
      let authorization = LocalMutationAuthorization { probe.validate() }
      do {
        _ = try await StagedTaskStorage.shared.insertLocalStagedTask(
          StagedTaskRecord(description: "synthetic old-owner task"), authorization: authorization)
        XCTFail("revoked transaction committed")
      } catch {}
      let queue = await RewindDatabase.shared.getDatabaseQueue()
      let db = try XCTUnwrap(queue)
      let count = try await db.read { database in
        try Int.fetchOne(database, sql: "SELECT COUNT(*) FROM staged_tasks") ?? 0
      }
      XCTAssertEqual(count, 0)
    }
  }

  func testRevokedReceiptAndDiscardCannotMutateOutbox() async throws {
    let record = try await StagedTaskStorage.shared.insertLocalStagedTask(
      StagedTaskRecord(description: "synthetic outbox", source: "candidate_outbox"))
    let id = try XCTUnwrap(record.id)
    let revoked = LocalMutationAuthorization { false }
    do {
      try await StagedTaskStorage.shared.markCanonicalReceipt(
        id: id, candidateID: "synthetic-candidate", status: "pending", taskID: nil, authorization: revoked)
      XCTFail("revoked receipt update succeeded")
    } catch {}
    do {
      try await StagedTaskStorage.shared.discardCanonicalOutbox(id: id, authorization: revoked)
      XCTFail("revoked discard succeeded")
    } catch {}
    let receipt = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(id: id)
    XCTAssertNil(receipt)
    let outbox = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    XCTAssertEqual(outbox.count, 1)
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

private final class StorageRevocationProbe: @unchecked Sendable {
  private let lock = NSLock()
  private let authority = RuntimeOwnerAuthorizationAuthority()
  private let snapshot: RuntimeOwnerAuthorizationSnapshot
  private let owner: String
  private let sameUID: Bool
  private var checks = 0
  init(owner: String, sameUID: Bool) {
    self.owner = owner
    self.sameUID = sameUID
    snapshot = authority.capture(ownerID: owner, expectedOwnerID: owner)!
  }
  func validate() -> Bool {
    lock.withLock {
      checks += 1
      // First check is admission, second acquires the commit lease, third runs inside SQLite.
      if checks == 3 {
        authority.beginTransition()
        authority.endTransition(ownerID: sameUID ? owner : "synthetic-other")
      }
      return authority.isCurrent(snapshot, ownerID: owner)
    }
  }
}
