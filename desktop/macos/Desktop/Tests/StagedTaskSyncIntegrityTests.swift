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
      let probe = try StorageRevocationProbe(owner: testUserId, sameUID: sameUID)
      let authorization = LocalMutationAuthorization { probe.validate() }
      do {
        _ = try await StagedTaskStorage.shared.insertLocalStagedTask(
          StagedTaskRecord(description: "synthetic old-owner task"), authorization: authorization)
        XCTFail("revoked transaction committed")
      } catch LocalMutationAuthorizationError.revoked {
      } catch {
        XCTFail("Unexpected storage failure: \(error)")
      }
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
    } catch LocalMutationAuthorizationError.revoked {
    } catch {
      XCTFail("Unexpected storage failure: \(error)")
    }
    do {
      try await StagedTaskStorage.shared.discardCanonicalOutbox(id: id, authorization: revoked)
      XCTFail("revoked discard succeeded")
    } catch LocalMutationAuthorizationError.revoked {
    } catch {
      XCTFail("Unexpected storage failure: \(error)")
    }
    let receipt = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(id: id)
    XCTAssertNil(receipt)
    let outbox = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    XCTAssertEqual(outbox.count, 1)
  }

  @MainActor func testDeferredReceiptRetainsProvenanceAndClaimsCompletionOnlyOnceAcrossReloadAndDuplicateRows()
    async throws
  {
    var emitted: [[String: Any]] = []
    let ownerID = try XCTUnwrap(testUserId)
    let emit: @MainActor (String, ScreenTaskDeliveryCompletion, Bool) -> Void = { owner, completion, deferred in
      XCTAssertEqual(owner, ownerID)
      emitted.append(completion.properties(deferred: deferred))
    }
    for extractor in ["gemini_3_8", "legacy"] {
      let provenance = ScreenTaskDeliveryProvenance(extractor: extractor, gateOutcome: "rejected", auditSample: true)
      var metadata: [String: Any] = ["context_summary": "synthetic private content"]
      provenance.store(in: &metadata)
      var row = StagedTaskRecord(description: "synthetic private task", source: "candidate_outbox")
      row.setMetadata(metadata)
      let inserted = try await StagedTaskStorage.shared.insertLocalStagedTask(row)
      let id = try XCTUnwrap(inserted.id)
      // A failed delivery leaves a durable row; reconstruct the retry from SQLite after a pool reload.
      await StagedTaskStorage.shared.invalidateCache()
      let rows = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
      let reloaded = try XCTUnwrap(rows.first { $0.id == id })
      XCTAssertEqual(ScreenTaskDeliveryProvenance(metadata: reloaded.metadata ?? [:]), provenance)
      let candidate = "synthetic-\(extractor)"
      let first = try await ScreenTaskReceiptDelivery.complete(
        id: id, candidateID: candidate, status: "pending", taskID: nil, ownerID: ownerID, deferred: true, emit: emit)
      let event = try XCTUnwrap(first)
      XCTAssertEqual(event.provenance, provenance)
      let properties = event.properties(deferred: true)
      XCTAssertEqual(properties["delivery_path"] as? String, "deferred")
      XCTAssertEqual(properties["pending_delivered"] as? Int, 1)
      XCTAssertEqual(
        Set(properties.keys),
        Set([
          "schema_version", "extractor", "gate_outcome", "audit_sample", "delivery_status", "pending_delivered",
          "delivery_path",
        ]))
      XCTAssertFalse(String(describing: properties).contains("synthetic"))
      await StagedTaskStorage.shared.invalidateCache()
      let replay = try await ScreenTaskReceiptDelivery.complete(
        id: id, candidateID: candidate, status: "pending", taskID: nil, ownerID: ownerID, deferred: true, emit: emit)
      XCTAssertNil(replay)
      let duplicate = try await StagedTaskStorage.shared.insertLocalStagedTask(row)
      let duplicateID = try XCTUnwrap(duplicate.id)
      let coalesced = try await ScreenTaskReceiptDelivery.complete(
        id: duplicateID, candidateID: candidate, status: "pending", taskID: nil, ownerID: ownerID, deferred: true,
        emit: emit)
      XCTAssertNil(coalesced, "canonical receipt reuse must not count another delivered suggestion")
      let outbox = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
      XCTAssertFalse(outbox.contains { $0.id == id || $0.id == duplicateID })
    }
    XCTAssertEqual(emitted.count, 2, "exactly one completion for each original candidate, including all replays")
    XCTAssertEqual(emitted.map { $0["extractor"] as? String }, ["gemini_3_8", "legacy"])
    XCTAssertTrue(emitted.allSatisfy { $0["delivery_path"] as? String == "deferred" })
  }

  func testConcurrentReceiptReplaysClaimOnlyOneCompletion() async throws {
    let row = try await StagedTaskStorage.shared.insertLocalStagedTask(
      StagedTaskRecord(description: "synthetic task", source: "candidate_outbox"))
    let id = try XCTUnwrap(row.id)
    async let first = StagedTaskStorage.shared.markCanonicalReceipt(
      id: id, candidateID: "synthetic-concurrent", status: "pending", taskID: nil)
    async let second = StagedTaskStorage.shared.markCanonicalReceipt(
      id: id, candidateID: "synthetic-concurrent", status: "pending", taskID: nil)
    let claims = try await [first, second]
    XCTAssertEqual(claims.compactMap { $0 }.count, 1)
    XCTAssertEqual(claims.compactMap { $0 }.first?.status, "pending")
  }

  func testCompletionProvenanceBoundsUnknownValuesAndNonPendingReceiptsDoNotCountSuggestions() async throws {
    let provenance = ScreenTaskDeliveryProvenance(metadata: [
      "screen_task_delivery_provenance": [
        "extractor": "synthetic secret task", "gate_outcome": "synthetic secret window", "audit_sample": true,
      ]
    ])
    XCTAssertEqual(provenance.extractor, "unknown")
    XCTAssertEqual(provenance.gateOutcome, "none")
    XCTAssertFalse(provenance.auditSample)
    var metadata: [String: Any] = [:]
    provenance.store(in: &metadata)
    var row = StagedTaskRecord(description: "synthetic task", source: "candidate_outbox")
    row.setMetadata(metadata)
    let inserted = try await StagedTaskStorage.shared.insertLocalStagedTask(row)
    let completion = try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: XCTUnwrap(inserted.id), candidateID: "synthetic-resolved", status: "accepted", taskID: "synthetic-task")
    XCTAssertEqual(try XCTUnwrap(completion).properties(deferred: false)["pending_delivered"] as? Int, 0)
    XCTAssertEqual(try XCTUnwrap(completion).properties(deferred: false)["delivery_path"] as? String, "immediate")
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
  init(owner: String, sameUID: Bool) throws {
    self.owner = owner
    self.sameUID = sameUID
    snapshot = try XCTUnwrap(authority.capture(ownerID: owner, expectedOwnerID: owner))
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
