import GRDB
import XCTest

@testable import Omi_Computer

final class MemoryLedgerMirrorTests: XCTestCase {
  private var userDir: URL?
  private var fixture: RewindStorageTestIsolation.Fixture?
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot?

  override func setUp() async throws {
    try await super.setUp()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memory-ledger-mirror")
    self.fixture = fixture
    userDir = fixture.userDir
    authSnapshot = await MainActor.run { RewindStorageTestIsolation.captureAuthSnapshot() }
    await MainActor.run { RewindStorageTestIsolation.signInForTests(userId: fixture.testUserId) }
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: fixture.testUserId)
  }

  override func tearDown() async throws {
    if let authSnapshot {
      await MainActor.run { RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot) }
      RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
      RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: authSnapshot.userId)
    }
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
    try await super.tearDown()
  }

  func testCanonicalStructuredMetadataSurvivesServerRecordSQLiteAndReadRoundTrip() async throws {
    let memory = makeMemory(
      id: "ledger-roundtrip-\(UUID().uuidString)",
      metadata: canonicalMetadata(),
      evidence: [makeEvidence("ev-roundtrip")],
      evidenceIsExplicit: true
    )

    let record = MemoryRecord.from(memory)
    XCTAssertEqual(record.toServerMemory()?.ledgerMetadata, memory.ledgerMetadata)
    XCTAssertEqual(record.toServerMemory()?.evidence, memory.evidence)
    XCTAssertEqual(
      record.ledgerTriggerConditionJSON, MemoryLedgerMetadata.triggerConditionJSON(from: memory.ledgerMetadata))

    try await MemoryStorage.shared.syncServerMemory(memory)
    let persisted = try await MemoryStorage.shared.getMemoryByBackendId(memory.id)
    let read = try XCTUnwrap(persisted?.toServerMemory())
    XCTAssertEqual(read.ledgerMetadata, memory.ledgerMetadata)
    XCTAssertEqual(read.evidence, memory.evidence)
    XCTAssertEqual(read.evidence.first?.evidenceId, "ev-roundtrip")
    XCTAssertLessThanOrEqual(
      try XCTUnwrap(persisted?.ledgerEvidenceJson).utf8.count,
      MemoryLedgerEvidence.maxEvidenceJSONBytes
    )
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
      metadata: canonicalMetadata(city: "Initial city"),
      evidence: [makeEvidence("ev-initial")],
      evidenceIsExplicit: true
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
      status: "superseded",
      evidence: [makeEvidence("ev-closure")],
      evidenceIsExplicit: true
    )
    try await MemoryStorage.shared.syncServerMemories([staleServer])
    let afterStaleRecord = try await MemoryStorage.shared.getMemoryByBackendId(id)
    let afterStale = try XCTUnwrap(afterStaleRecord?.toServerMemory())
    XCTAssertEqual(afterStale.content, "Unrelated local edit")
    XCTAssertEqual(afterStale.updatedAt, Date(timeIntervalSince1970: 2_000))
    XCTAssertEqual(afterStale.ledgerMetadata, staleServer.ledgerMetadata)
    XCTAssertEqual(afterStale.evidence.map(\.evidenceId), ["ev-closure"])
    XCTAssertNil(afterStaleRecord?.ledgerTriggerConditionJSON, "A server closure must fail closed locally")
  }

  func testOmittedEvidenceDoesNotEraseExistingMirror() async throws {
    let id = "ledger-evidence-omitted-\(UUID().uuidString)"
    let initial = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 1_000),
      metadata: [:],
      evidence: [makeEvidence("ev-preserved")],
      evidenceIsExplicit: true
    )
    try await MemoryStorage.shared.syncServerMemory(initial)

    let compatibilityResponse = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 2_000),
      metadata: [:]
    )
    try await MemoryStorage.shared.syncServerMemory(compatibilityResponse)

    let persistedRecord = try await MemoryStorage.shared.getMemoryByBackendId(id)
    let persisted = try XCTUnwrap(persistedRecord)
    XCTAssertEqual(persisted.ledgerEvidence.map(\.evidenceId), ["ev-preserved"])
    XCTAssertEqual(persisted.toServerMemory()?.evidence.map(\.evidenceId), ["ev-preserved"])
  }

  func testExplicitEmptyEvidenceClearsMirrorAndSurvivesRoundTrip() async throws {
    let id = "ledger-evidence-clear-\(UUID().uuidString)"
    let initial = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 1_000),
      metadata: [:],
      evidence: [makeEvidence("ev-to-clear")],
      evidenceIsExplicit: true
    )
    try await MemoryStorage.shared.syncServerMemory(initial)

    let cleared = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 2_000),
      metadata: [:],
      evidence: [],
      evidenceIsExplicit: true
    )
    try await MemoryStorage.shared.syncServerMemory(cleared)

    let persistedRecord = try await MemoryStorage.shared.getMemoryByBackendId(id)
    let persisted = try XCTUnwrap(persistedRecord)
    XCTAssertEqual(persisted.ledgerEvidenceJson, "[]")
    XCTAssertTrue(persisted.toServerMemory()?.evidence.isEmpty == true)
    XCTAssertTrue(persisted.toServerMemory()?.evidenceIsExplicit == true)
  }

  func testInvalidEvidencePreservesPreviousMirror() async throws {
    let id = "ledger-evidence-invalid-\(UUID().uuidString)"
    let initial = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 1_000),
      metadata: [:],
      evidence: [makeEvidence("ev-preserved-through-invalid")],
      evidenceIsExplicit: true
    )
    try await MemoryStorage.shared.syncServerMemory(initial)

    let invalid = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 2_000),
      metadata: [:],
      evidenceState: .invalid
    )
    try await MemoryStorage.shared.syncServerMemory(invalid)

    let persistedRecord = try await MemoryStorage.shared.getMemoryByBackendId(id)
    let persisted = try XCTUnwrap(persistedRecord)
    XCTAssertEqual(persisted.ledgerEvidence.map(\.evidenceId), ["ev-preserved-through-invalid"])
  }

  func testLocalEditCannotAllowOlderActiveEvidenceAfterIdenticalNewerRedaction() async throws {
    let id = "ledger-evidence-redaction-fence-\(UUID().uuidString)"
    let initial = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 1_000),
      metadata: [:],
      evidence: [makeEvidence("ev-redaction", redactionStatus: "active")],
      evidenceIsExplicit: true
    )
    try await MemoryStorage.shared.syncServerMemory(initial)

    let newerRedacted = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 2_000),
      metadata: [:],
      evidence: [makeEvidence("ev-redaction", redactionStatus: "tombstoned")],
      evidenceIsExplicit: true
    )
    try await MemoryStorage.shared.syncServerMemory(newerRedacted)

    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      XCTFail("Database queue unavailable")
      return
    }
    try await dbQueue.write { database in
      guard var record = try MemoryRecord.filter(Column("backendId") == id).fetchOne(database) else {
        XCTFail("Expected local ledger row")
        return
      }
      record.content = "Unrelated local edit after redaction"
      record.updatedAt = Date(timeIntervalSince1970: 4_000)
      try record.update(database)
    }

    // This response has the same tombstone payload but a newer server
    // revision. It must advance the evidence fence even though the local
    // content edit makes the row newer than the response.
    let identicalNewerRedacted = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 3_000),
      metadata: [:],
      evidence: [makeEvidence("ev-redaction", redactionStatus: "tombstoned")],
      evidenceIsExplicit: true
    )
    try await MemoryStorage.shared.syncServerMemories([identicalNewerRedacted])

    let olderActive = makeMemory(
      id: id,
      updatedAt: Date(timeIntervalSince1970: 2_500),
      metadata: [:],
      evidence: [makeEvidence("ev-redaction", redactionStatus: "active")],
      evidenceIsExplicit: true
    )
    try await MemoryStorage.shared.syncServerMemories([olderActive])

    let persistedRecord = try await MemoryStorage.shared.getMemoryByBackendId(id)
    let persisted = try XCTUnwrap(persistedRecord)
    XCTAssertEqual(persisted.content, "Unrelated local edit after redaction")
    XCTAssertEqual(persisted.ledgerEvidence.first?.redactionStatus, "tombstoned")
    XCTAssertEqual(persisted.ledgerEvidenceRevision, Date(timeIntervalSince1970: 3_000))
  }

  func testRedactedEvidencePersistenceScrubsArtifactAndDevicePointers() async throws {
    let id = "ledger-evidence-redaction-sanitize-\(UUID().uuidString)"
    let memory = makeMemory(
      id: id,
      metadata: [:],
      evidence: [
        makeEvidence(
          "ev-private",
          group: "lineage-1",
          redactionStatus: "tombstoned",
          artifactRef: [
            "uri": OmiAnyCodable("gs://private-artifact"),
            "quote_ref": OmiAnyCodable("private-quote"),
          ],
          clientDeviceId: "device-private",
          sourceId: "source-1"
        )
      ],
      evidenceIsExplicit: true
    )

    try await MemoryStorage.shared.syncServerMemory(memory)

    let optionalRecord = try await MemoryStorage.shared.getMemoryByBackendId(id)
    let persistedRecord = try XCTUnwrap(optionalRecord)
    let json = try XCTUnwrap(persistedRecord.ledgerEvidenceJson)
    XCTAssertFalse(json.contains("gs://private-artifact"))
    XCTAssertFalse(json.contains("private-quote"))
    XCTAssertFalse(json.contains("device-private"))

    let persisted = try XCTUnwrap(persistedRecord.ledgerEvidence.first)
    XCTAssertEqual(persisted.evidenceId, "ev-private")
    XCTAssertEqual(persisted.independenceGroup, "lineage-1")
    XCTAssertEqual(persisted.sourceId, "source-1")
    XCTAssertEqual(persisted.sourceType, "conversation")
    XCTAssertEqual(persisted.redactionStatus, "tombstoned")
    XCTAssertNil(persisted.artifactRef)
    XCTAssertNil(persisted.clientDeviceId)
  }

  func testEvidenceMigrationPreservesPopulatedPreColumnMemories() throws {
    let queue = try DatabaseQueue()
    try queue.write { database in
      try database.create(table: "memories") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("backendId", .text)
        table.column("content", .text).notNull()
        table.column("updatedAt", .datetime).notNull()
      }
      try database.execute(
        sql: "INSERT INTO memories (backendId, content, updatedAt) VALUES (?, ?, ?)",
        arguments: ["pre-evidence-memory", "Keep this populated row", Date(timeIntervalSince1970: 42)]
      )
    }

    var migrator = DatabaseMigrator()
    RewindDatabase.registerMemoryLedgerEvidenceMigrations(on: &migrator)
    try migrator.migrate(queue)

    try queue.read { database in
      let columns = try database.columns(in: "memories").map(\.name)
      XCTAssertTrue(columns.contains("ledgerEvidenceJson"))
      XCTAssertTrue(columns.contains("ledgerEvidenceRevision"))
      let row = try Row.fetchOne(
        database,
        sql: "SELECT backendId, content, ledgerEvidenceJson, ledgerEvidenceRevision FROM memories WHERE backendId = ?",
        arguments: ["pre-evidence-memory"]
      )
      XCTAssertEqual(row?["backendId"] as String?, "pre-evidence-memory")
      XCTAssertEqual(row?["content"] as String?, "Keep this populated row")
      XCTAssertNil(row?["ledgerEvidenceJson"] as String?)
      XCTAssertNil(row?["ledgerEvidenceRevision"] as Date?)
    }
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

  func testAuthoritativeProjectionAbsenceRollsBackWithoutRevivingUserDeletion() async throws {
    let kept = makeMemory(id: "ledger-kept", metadata: canonicalMetadata())
    let temporarilyAbsent = makeMemory(id: "ledger-temporarily-absent", metadata: canonicalMetadata())
    let userDeleted = makeMemory(id: "ledger-user-deleted", metadata: canonicalMetadata())
    try await MemoryStorage.shared.syncServerMemories([kept, temporarilyAbsent, userDeleted])
    try await MemoryStorage.shared.deleteMemory(surfacedId: userDeleted.id)

    let authorization = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let firstProjection = KnowledgeLedgerPromptProjection(
      memories: [kept], hasAuthoritativeSnapshot: true)
    XCTAssertEqual(firstProjection.rows.map(\.id), [kept.id])
    XCTAssertFalse(firstProjection.rows.map(\.id).contains(temporarilyAbsent.id))
    let inserted = try await MemoryStorage.shared.syncAuthoritativeKnowledgeLedgerSnapshot(
      [kept], authorizationSnapshot: authorization)
    XCTAssertEqual(inserted, 0)

    // Compatibility/disabled/killed/stale-receipt fallback reads this exact
    // legacy cache on the next turn. Projection absence must not poison it.
    let compatibilityIDs = Set(try await MemoryStorage.shared.getLocalMemories(limit: 100).map(\.id))
    XCTAssertTrue(compatibilityIDs.contains(kept.id))
    XCTAssertTrue(compatibilityIDs.contains(temporarilyAbsent.id))
    XCTAssertFalse(compatibilityIDs.contains(userDeleted.id))

    let restoredProjection = KnowledgeLedgerPromptProjection(
      memories: [kept, temporarilyAbsent], hasAuthoritativeSnapshot: true)
    try await MemoryStorage.shared.syncAuthoritativeKnowledgeLedgerSnapshot(
      [kept, temporarilyAbsent], authorizationSnapshot: authorization)
    XCTAssertTrue(restoredProjection.rows.map(\.id).contains(temporarilyAbsent.id))
    let restoredRecord = try await MemoryStorage.shared.getMemoryByBackendId(temporarilyAbsent.id)
    XCTAssertFalse(try XCTUnwrap(restoredRecord).deleted)

    // A later ordinary reconciliation must not blanket-revive a genuine local
    // user deletion just because the server response raced it.
    try await MemoryStorage.shared.syncServerMemories([userDeleted])
    let deletedRecord = try await MemoryStorage.shared.getMemoryByBackendId(userDeleted.id)
    XCTAssertTrue(try XCTUnwrap(deletedRecord).deleted)
  }

  func testOwnerSwitchBeforeAuthoritativeSyncWritesNothing() async throws {
    let incoming = makeMemory(id: "ledger-stale-owner", metadata: canonicalMetadata())
    let authorization = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()

    do {
      _ = try await MemoryStorage.shared.syncAuthoritativeKnowledgeLedgerSnapshot(
        [incoming], authorizationSnapshot: authorization)
      XCTFail("Expected stale owner authority to fail closed")
    } catch KnowledgeLedgerMirrorSyncError.ownerChanged {
      // Expected.
    }

    let persisted = try await MemoryStorage.shared.getMemoryByBackendId(incoming.id)
    XCTAssertNil(persisted)
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: fixture?.testUserId)
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
    status: String? = nil,
    evidence: [ServerMemoryEvidence] = [],
    evidenceIsExplicit: Bool = false,
    evidenceState: ServerMemoryEvidenceState? = nil
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
      ledgerMetadata: metadata,
      evidence: evidence,
      evidenceIsExplicit: evidenceIsExplicit,
      evidenceState: evidenceState
    )
  }

  private func makeEvidence(
    _ id: String,
    group: String = "conversation-group",
    redactionStatus: String? = nil,
    artifactRef: [String: OmiAnyCodable]? = nil,
    clientDeviceId: String? = nil,
    sourceId: String? = nil
  ) -> ServerMemoryEvidence {
    ServerMemoryEvidence(
      OmiAPI.Evidence(
        artifactRef: artifactRef,
        clientDeviceId: clientDeviceId,
        evidenceId: id,
        independenceGroup: group,
        redactionStatus: redactionStatus,
        sourceId: sourceId,
        sourceSignal: "transcript",
        sourceType: "conversation"
      )
    )
  }
}
