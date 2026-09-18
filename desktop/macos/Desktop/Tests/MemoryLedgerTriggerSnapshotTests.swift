import GRDB
import XCTest

@testable import Omi_Computer

final class MemoryLedgerTriggerSnapshotTests: XCTestCase {
  private var userDir: URL?

  override func setUp() async throws {
    try await super.setUp()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memory-ledger-snapshot")
    userDir = fixture.userDir
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
    try await super.tearDown()
  }

  func testSnapshotOrdersRowsAndReportsLocalTruncationWithoutClaimingAuthority() async throws {
    let suffix = UUID().uuidString
    let sameTime = Date(timeIntervalSince1970: 2_000)
    let rows = [
      makeMemory(
        id: "newer-fact-\(suffix)", updatedAt: Date(timeIntervalSince1970: 4_000), keyword: "fact", kind: "fact"),
      makeMemory(id: "snapshot-z-\(suffix)", updatedAt: sameTime, keyword: "z"),
      makeMemory(
        id: "middle-fact-\(suffix)", updatedAt: Date(timeIntervalSince1970: 3_000), keyword: "fact", kind: "fact"),
      makeMemory(id: "snapshot-old-\(suffix)", updatedAt: Date(timeIntervalSince1970: 1_000), keyword: "old"),
      makeMemory(id: "snapshot-a-\(suffix)", updatedAt: sameTime, keyword: "a"),
    ]
    try await MemoryStorage.shared.syncServerMemories(rows)

    let snapshot = try await MemoryStorage.shared.getCanonicalTriggerSnapshot(limit: 2)

    XCTAssertEqual(
      snapshot.projection.entries.map(\.id),
      ["snapshot-a-\(suffix)", "snapshot-z-\(suffix)"]
    )
    XCTAssertEqual(snapshot.diagnostics.localRowCount, 2)
    XCTAssertTrue(snapshot.diagnostics.hasMoreLocalRows)
    XCTAssertEqual(snapshot.diagnostics.completeness, .localCacheTruncated)
    XCTAssertFalse(snapshot.diagnostics.isAuthoritative)
    XCTAssertTrue(snapshot.diagnostics.quarantined.isEmpty)
  }

  func testSnapshotExhaustionIsLocalOnlyAndQuarantinesAClosedConflict() async throws {
    let id = "snapshot-conflict-\(UUID().uuidString)"
    let initial = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 1_000),
      keyword: "initial"
    )
    try await MemoryStorage.shared.syncServerMemory(initial)

    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      XCTFail("Database queue unavailable")
      return
    }
    try await dbQueue.write { database in
      guard var record = try MemoryRecord.filter(Column("backendId") == id).fetchOne(database) else {
        XCTFail("Expected mirrored trigger row")
        return
      }
      record.content = "Unrelated local edit"
      record.updatedAt = Date(timeIntervalSince1970: 2_000)
      try record.update(database)
    }

    let staleClosure = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 1_500),
      keyword: "closed",
      status: "superseded"
    )
    try await MemoryStorage.shared.syncServerMemories([staleClosure])

    let snapshot = try await MemoryStorage.shared.getCanonicalTriggerSnapshot(limit: 10)
    XCTAssertFalse(snapshot.projection.entries.contains { $0.id == id })
    XCTAssertEqual(
      snapshot.diagnostics.quarantined.first(where: { $0.id == id })?.failure,
      .closedRow
    )
    XCTAssertEqual(snapshot.diagnostics.completeness, .localCacheExhausted)
    XCTAssertFalse(snapshot.diagnostics.hasMoreLocalRows)
    XCTAssertFalse(snapshot.diagnostics.isAuthoritative)
  }

  func testSnapshotIncludesDeletionTombstonesAsQuarantineInsteadOfReactivation() async throws {
    let id = "snapshot-delete-\(UUID().uuidString)"
    try await MemoryStorage.shared.syncServerMemory(makeMemory(id: id, keyword: "delete"))
    _ = try await MemoryStorage.shared.syncServerMemoriesAndPruneAbsent([], within: .defaultAccess)

    let snapshot = try await MemoryStorage.shared.getCanonicalTriggerSnapshot(limit: 10)

    XCTAssertFalse(snapshot.projection.entries.contains { $0.id == id })
    XCTAssertEqual(
      snapshot.diagnostics.quarantined.first(where: { $0.id == id })?.failure,
      .deletedRow
    )
  }

  func testSnapshotRequiresAnExplicitPositiveBound() async throws {
    do {
      _ = try await MemoryStorage.shared.getCanonicalTriggerSnapshot(limit: 0)
      XCTFail("Expected invalid zero limit")
    } catch let error as MemoryLedgerTriggerSnapshotError {
      XCTAssertEqual(error, .invalidLimit(0))
    }
  }

  private func makeMemory(
    id: String,
    updatedAt: Date = Date(timeIntervalSince1970: 2),
    keyword: String,
    status: String = "active",
    kind: String = "trigger"
  ) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "Trigger \(id)",
      category: .workflow,
      tier: .longTerm,
      tierIsExplicit: true,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: updatedAt,
      conversationId: nil,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: false,
      scoring: nil,
      source: "desktop",
      confidence: nil,
      sourceApp: nil,
      contextSummary: nil,
      isRead: false,
      isDismissed: false,
      tags: [],
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: nil,
      windowTitle: nil,
      headline: nil,
      ledgerMetadata: [
        MemoryLedgerMetadata.schemaVersionKey: KnowledgeLedgerTriggerRow.schemaVersion,
        "kind": kind,
        "subject_scope": "primary_user",
        "intent_backed": "true",
        "status": status,
        MemoryLedgerMetadata.triggerConditionJSONKey:
          "{\"keywords\":[\"\(keyword)\"],\"schema_version\":\"jit_trigger.v1\"}",
      ]
    )
  }
}
