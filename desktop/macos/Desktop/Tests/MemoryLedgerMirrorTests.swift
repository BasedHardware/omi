import GRDB
import XCTest

@testable import Omi_Computer

final class MemoryLedgerMirrorTests: XCTestCase {
  private var userDir: URL?

  override func setUp() async throws {
    try await super.setUp()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memory-ledger-mirror")
    userDir = fixture.userDir
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
    try await super.tearDown()
  }

  func testCanonicalStructuredMetadataSurvivesServerRecordSQLiteAndReadRoundTrip() async throws {
    let memory = makeMemory(id: "ledger-roundtrip-\(UUID().uuidString)", metadata: canonicalMetadata())

    let record = MemoryRecord.from(memory)
    XCTAssertEqual(record.toServerMemory()?.ledgerMetadata, memory.ledgerMetadata)
    XCTAssertEqual(
      record.ledgerTriggerConditionJSON, MemoryLedgerMetadata.triggerConditionJSON(from: memory.ledgerMetadata))

    try await MemoryStorage.shared.syncServerMemory(memory)
    let persisted = try await MemoryStorage.shared.getMemoryByBackendId(memory.id)
    let read = try XCTUnwrap(persisted?.toServerMemory())
    XCTAssertEqual(read.ledgerMetadata, memory.ledgerMetadata)
    XCTAssertEqual(read.ledgerMetadata["object_entity_ids_json"], "[\"project-release\"]")
    XCTAssertEqual(
      read.ledgerMetadata["trigger_condition_json"],
      canonicalMetadata()[MemoryLedgerMetadata.triggerConditionJSONKey]
    )
  }

  func testOlderServerLedgerClosureOverridesNewerUnrelatedLocalEdit() async throws {
    let id = "ledger-conflict-\(UUID().uuidString)"
    let initialServer = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 1_000),
      metadata: canonicalMetadata(city: "Initial city")
    )
    try await MemoryStorage.shared.syncServerMemory(initialServer)

    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      XCTFail("Database queue unavailable")
      return
    }
    try await dbQueue.write { database in
      guard var record = try MemoryRecord.filter(Column("backendId") == id).fetchOne(database) else {
        XCTFail("Expected local ledger row")
        return
      }
      // Simulate an unrelated local edit. Ledger fields themselves are never
      // locally authored, so the server remains authoritative for them.
      record.content = "Unrelated local edit"
      record.updatedAt = Date(timeIntervalSince1970: 2_000)
      try record.update(database)
    }

    let staleServer = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 1_500),
      metadata: canonicalMetadata(city: "Server closure"),
      status: "superseded"
    )
    try await MemoryStorage.shared.syncServerMemories([staleServer])
    let afterStaleRecord = try await MemoryStorage.shared.getMemoryByBackendId(id)
    let afterStale = try XCTUnwrap(afterStaleRecord?.toServerMemory())
    XCTAssertEqual(afterStale.content, "Unrelated local edit")
    XCTAssertEqual(afterStale.updatedAt, Date(timeIntervalSince1970: 2_000))
    XCTAssertEqual(afterStale.ledgerMetadata, staleServer.ledgerMetadata)
    XCTAssertNil(afterStaleRecord?.ledgerTriggerConditionJSON, "A server closure must fail closed locally")
  }

  func testAbsentLedgerRowIsSoftDeletedWithoutErasingMirrorMetadata() async throws {
    let memory = makeMemory(id: "ledger-delete-\(UUID().uuidString)", metadata: canonicalMetadata())
    try await MemoryStorage.shared.syncServerMemory(memory)

    let removed = try await MemoryStorage.shared.syncServerMemoriesAndPruneAbsent(
      [],
      within: .defaultAccess
    )
    XCTAssertEqual(removed, 1)

    let deletedRecord = try await MemoryStorage.shared.getMemoryByBackendId(memory.id)
    let record = try XCTUnwrap(deletedRecord)
    XCTAssertTrue(record.deleted)
    XCTAssertEqual(record.toServerMemory()?.ledgerMetadata, memory.ledgerMetadata)
    XCTAssertNil(record.ledgerTriggerConditionJSON, "A tombstoned row must not reactivate a local trigger")
    let visible = try await MemoryStorage.shared.getLocalMemories(limit: 100)
    XCTAssertFalse(visible.contains { $0.id == memory.id })
  }

  func testLegacyAndFutureRowsRemainStoredButTriggerProjectionFailsClosed() async throws {
    let legacy = MemoryRecord.from(makeMemory(id: "ledger-legacy", metadata: [:]))
    XCTAssertFalse(MemoryLedgerMetadata.isSupportedVersion(legacy.toServerMemory()?.ledgerMetadata ?? [:]))
    XCTAssertNil(legacy.ledgerTriggerConditionJSON)

    var futureMetadata = canonicalMetadata()
    futureMetadata[MemoryLedgerMetadata.schemaVersionKey] = "knowledge_ledger.v2"
    let future = MemoryRecord.from(makeMemory(id: "ledger-future", metadata: futureMetadata))
    XCTAssertFalse(MemoryLedgerMetadata.isSupportedVersion(future.toServerMemory()?.ledgerMetadata ?? [:]))
    XCTAssertNil(future.ledgerTriggerConditionJSON)
    XCTAssertEqual(
      future.toServerMemory()?.ledgerMetadata[MemoryLedgerMetadata.triggerConditionJSONKey],
      futureMetadata[MemoryLedgerMetadata.triggerConditionJSONKey]
    )

    var malformedMetadata = canonicalMetadata()
    malformedMetadata[MemoryLedgerMetadata.triggerConditionJSONKey] = "{not-json"
    let malformed = MemoryRecord.from(makeMemory(id: "ledger-malformed", metadata: malformedMetadata))
    XCTAssertNil(malformed.ledgerTriggerConditionJSON)

    var missingStatusMetadata = canonicalMetadata()
    missingStatusMetadata.removeValue(forKey: "status")
    XCTAssertNotNil(
      MemoryRecord.from(makeMemory(id: "ledger-missing-status", metadata: missingStatusMetadata))
        .ledgerTriggerConditionJSON
    )

    var closedMetadata = canonicalMetadata()
    closedMetadata["status"] = "superseded"
    XCTAssertNil(
      MemoryRecord.from(makeMemory(id: "ledger-closed", metadata: closedMetadata)).ledgerTriggerConditionJSON)

    var rejected = MemoryRecord.from(makeMemory(id: "ledger-rejected", metadata: canonicalMetadata()))
    rejected.userReview = false
    XCTAssertNil(rejected.ledgerTriggerConditionJSON)

    var thirdPartyMetadata = canonicalMetadata()
    thirdPartyMetadata["subject_scope"] = "third_party"
    XCTAssertNil(
      MemoryRecord.from(makeMemory(id: "ledger-third-party", metadata: thirdPartyMetadata)).ledgerTriggerConditionJSON
    )

    let legacyMemory = makeMemory(id: "ledger-legacy-read-\(UUID().uuidString)", metadata: [:])
    let futureMemory = makeMemory(id: "ledger-future-read-\(UUID().uuidString)", metadata: futureMetadata)
    try await MemoryStorage.shared.syncServerMemories([legacyMemory, futureMemory])
    let persistedFutureRecord = try await MemoryStorage.shared.getMemoryByBackendId(futureMemory.id)
    let persistedFuture = try XCTUnwrap(persistedFutureRecord)
    XCTAssertEqual(persistedFuture.toServerMemory()?.ledgerMetadata, futureMetadata)
    XCTAssertNil(persistedFuture.ledgerTriggerConditionJSON)
  }

  private func canonicalMetadata(city: String = "Brooklyn") -> [String: String] {
    [
      "ledger_schema_version": "knowledge_ledger.v1",
      "kind": "trigger",
      "subject_scope": "primary_user",
      "subject_entity_id": "user",
      "intent_backed": "true",
      "curation_weight": "4",
      "status": "active",
      "valid_at": "2026-06-21T10:00:00Z",
      "write_reason": "standing_trigger",
      "object_entity_ids_json": "[\"project-release\"]",
      "trigger_condition_json":
        "{\"entity_aliases\":{\"release_owner\":[\"David\",\"dave\"]},\"keywords\":[\"release\"],\"schema_version\":\"jit_trigger.v1\"}",
      "city": city,
    ]
  }

  private func makeMemory(
    id: String,
    updatedAt: Date = Date(timeIntervalSince1970: 2),
    metadata: [String: String],
    status: String? = nil
  ) -> ServerMemory {
    var metadata = metadata
    if let status { metadata["status"] = status }
    return ServerMemory(
      id: id,
      content: "Ledger row \(id)",
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
      ledgerMetadata: metadata
    )
  }
}
