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

  func testDurableLedgerMirrorStagesPagesAndActivatesOnlyOnFinalPage() async throws {
    let authorization = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let first = makeMemory(id: "ledger-stage-first", metadata: canonicalMetadata())
    let second = makeMemory(id: "ledger-stage-second", metadata: canonicalMetadata())
    let epoch = String(repeating: "a", count: 64)

    let firstResult = try await MemoryStorage.shared.stageAuthoritativeKnowledgeLedgerMirrorPage(
      mirrorPage(
        ownerID: authorization.ownerID,
        epochID: epoch,
        commitSequence: 10,
        pageRevision: String(repeating: "b", count: 64),
        chainRevision: String(repeating: "c", count: 64),
        scannedCount: 1,
        projectedCount: 1,
        rows: [mirrorRow(first)],
        nextCursor: "cursor-one",
        finalPage: false),
      requestedCursor: nil,
      authorizationSnapshot: authorization)
    guard case .next("cursor-one") = firstResult else {
      return XCTFail("Expected the staged chain to request its next signed cursor")
    }
    let partialMembers = try await MemoryStorage.shared.getAuthoritativeKnowledgeLedgerMirrorMembers(
      ownerID: authorization.ownerID)
    XCTAssertTrue(partialMembers.isEmpty)

    let finalResult = try await MemoryStorage.shared.stageAuthoritativeKnowledgeLedgerMirrorPage(
      mirrorPage(
        ownerID: authorization.ownerID,
        epochID: epoch,
        commitSequence: 10,
        pageRevision: String(repeating: "d", count: 64),
        chainRevision: String(repeating: "e", count: 64),
        scannedCount: 2,
        projectedCount: 2,
        rows: [mirrorRow(second)],
        aliases: [
          KnowledgeLedgerMirrorAlias(
            aliasMemoryID: first.id,
            canonicalMemoryID: second.id,
            sourceMemoryID: first.id,
            reason: "superseded_by")
        ],
        nextCursor: nil,
        finalPage: true),
      requestedCursor: "cursor-one",
      authorizationSnapshot: authorization)
    guard case .activated(let receipt) = finalResult else {
      return XCTFail("Expected final-page activation")
    }
    XCTAssertEqual(receipt.rowCount, 2)
    let activatedMembers = try await MemoryStorage.shared.getAuthoritativeKnowledgeLedgerMirrorMembers(
      ownerID: authorization.ownerID)
    XCTAssertEqual(activatedMembers.map(\.memoryID), [first.id, second.id])
  }

  func testContentPurgedMirrorRowHardPurgesCachedMemoryButAbsentRowKeepsLegacyHistory() async throws {
    let authorization = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let retained = makeMemory(id: "ledger-retained-legacy", metadata: canonicalMetadata())
    let purged = makeMemory(id: "ledger-explicit-purge", metadata: canonicalMetadata())
    try await MemoryStorage.shared.syncServerMemories([retained, purged])

    let tombstone = KnowledgeLedgerMirrorRow(
      memoryID: purged.id,
      itemRevision: 2,
      status: "tombstoned",
      sourceState: "purged",
      canonicalMemoryID: nil,
      contentPurged: true,
      memory: nil)
    let epoch = String(repeating: "9", count: 64)
    _ = try await MemoryStorage.shared.stageAuthoritativeKnowledgeLedgerMirrorPage(
      mirrorPage(
        ownerID: authorization.ownerID,
        epochID: String(repeating: "8", count: 64),
        commitSequence: 19,
        pageRevision: String(repeating: "6", count: 64),
        chainRevision: String(repeating: "7", count: 64),
        scannedCount: 1,
        projectedCount: 1,
        rows: [mirrorRow(purged)],
        nextCursor: "stale-cursor",
        finalPage: false),
      requestedCursor: nil,
      authorizationSnapshot: authorization)
    let newerKnownAuthority = JITTriggerSnapshot(
      ownerID: authorization.ownerID,
      accountGeneration: 1,
      headCommitID: String(repeating: "f", count: 64),
      commitSequence: 20,
      snapshotRevision: String(repeating: "e", count: 64),
      complete: true,
      rows: [],
      failureReason: nil)
    let stagedAuthority = try await MemoryStorage.shared
      .stagedKnowledgeLedgerMirrorAuthority(ownerID: authorization.ownerID)
    XCTAssertFalse(stagedAuthority?.matches(newerKnownAuthority) == true)
    // This is the coordinator's resume guard: a pre-deletion cursor from the
    // old head is discarded before the newer tombstone head can activate.
    try await MemoryStorage.shared.clearKnowledgeLedgerMirrorStaging(ownerID: authorization.ownerID)
    let result = try await MemoryStorage.shared.stageAuthoritativeKnowledgeLedgerMirrorPage(
      mirrorPage(
        ownerID: authorization.ownerID,
        epochID: epoch,
        commitSequence: 20,
        pageRevision: String(repeating: "a", count: 64),
        chainRevision: String(repeating: "b", count: 64),
        scannedCount: 1,
        projectedCount: 1,
        rows: [tombstone],
        nextCursor: nil,
        finalPage: true),
      requestedCursor: nil,
      authorizationSnapshot: authorization)
    guard case .activated = result else { return XCTFail("purge tombstone must activate") }

    let purgedRecord = try await MemoryStorage.shared.getMemoryByBackendId(purged.id)
    let retainedRecord = try await MemoryStorage.shared.getMemoryByBackendId(retained.id)
    XCTAssertNil(purgedRecord)
    XCTAssertNotNil(retainedRecord)
    guard let database = await RewindDatabase.shared.getDatabaseQueue() else {
      return XCTFail("database queue unavailable")
    }
    let staleStageCount = try await database.read { db in
      try Int.fetchOne(
        db,
        sql: "SELECT COUNT(*) FROM jit_knowledge_ledger_mirror_staging_members WHERE ownerID = ?",
        arguments: [authorization.ownerID]) ?? -1
    }
    XCTAssertEqual(staleStageCount, 0)
    let members = try await MemoryStorage.shared.getAuthoritativeKnowledgeLedgerMirrorMembers(
      ownerID: authorization.ownerID)
    XCTAssertEqual(members.map(\.memoryID), [purged.id])
    XCTAssertTrue(members[0].contentPurged)
  }

  func testKnownAuthorityOverlapDiscardsOlderInFlightActivationBeforeTombstoneHead() async throws {
    let authorization = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let oldMemory = makeMemory(id: "ledger-overlap-deleted", metadata: canonicalMetadata())
    let oldEpoch = String(repeating: "a", count: 64)
    let newEpoch = String(repeating: "b", count: 64)
    let oldFirst = mirrorPage(
      ownerID: authorization.ownerID,
      epochID: oldEpoch,
      commitSequence: 10,
      headCommitID: "old-head",
      pageRevision: String(repeating: "c", count: 64),
      chainRevision: String(repeating: "d", count: 64),
      scannedCount: 1,
      projectedCount: 1,
      rows: [mirrorRow(oldMemory)],
      nextCursor: "old-next",
      finalPage: false)
    let oldFinal = mirrorPage(
      ownerID: authorization.ownerID,
      epochID: oldEpoch,
      commitSequence: 10,
      headCommitID: "old-head",
      pageRevision: String(repeating: "e", count: 64),
      chainRevision: String(repeating: "f", count: 64),
      scannedCount: 1,
      projectedCount: 1,
      rows: [],
      nextCursor: nil,
      finalPage: true)
    let tombstone = KnowledgeLedgerMirrorRow(
      memoryID: oldMemory.id,
      itemRevision: 2,
      status: "tombstoned",
      sourceState: "purged",
      canonicalMemoryID: nil,
      contentPurged: true,
      memory: nil)
    let newFinal = mirrorPage(
      ownerID: authorization.ownerID,
      epochID: newEpoch,
      commitSequence: 20,
      headCommitID: "new-head",
      pageRevision: String(repeating: "1", count: 64),
      chainRevision: String(repeating: "2", count: 64),
      scannedCount: 1,
      projectedCount: 1,
      rows: [tombstone],
      nextCursor: nil,
      finalPage: true)
    let knownAuthority = JITTriggerSnapshot(
      ownerID: authorization.ownerID,
      accountGeneration: 1,
      headCommitID: "new-head",
      commitSequence: 20,
      snapshotRevision: String(repeating: "3", count: 64),
      complete: true,
      rows: [],
      failureReason: nil)
    let gate = MirrorPageFetchGate()
    let fetcher = OverlapMirrorPageFetcher(
      oldFirst: oldFirst, oldFinal: oldFinal, newFinal: newFinal, gate: gate)
    let coordinator = KnowledgeLedgerMirrorCoordinator(
      pageFetcher: { cursor, authorizationSnapshot in
        try await fetcher.fetch(cursor: cursor, authorizationSnapshot: authorizationSnapshot)
      })

    let olderSync = Task {
      try await coordinator.sync(authorizationSnapshot: authorization)
    }
    await gate.waitUntilEntered()
    let fetchEntered = await gate.hasEntered
    XCTAssertTrue(fetchEntered)

    // The second call joins while the older nil-authority sync is suspended
    // between pages. Releasing it lets the old epoch activate, after which the
    // known-authority caller must immediately restart from the new head.
    let knownSync = Task {
      try await coordinator.sync(
        authorizationSnapshot: authorization, knownAuthority: knownAuthority)
    }
    await Task.yield()
    await Task.yield()
    await gate.release()
    _ = try await olderSync.value
    _ = try await knownSync.value

    let oldRecord = try await MemoryStorage.shared.getMemoryByBackendId(oldMemory.id)
    XCTAssertNil(oldRecord)
    let members = try await MemoryStorage.shared.getAuthoritativeKnowledgeLedgerMirrorMembers(
      ownerID: authorization.ownerID)
    XCTAssertEqual(members.map(\.memoryID), [oldMemory.id])
    XCTAssertTrue(members[0].contentPurged)
    let activeAuthority = try await MemoryStorage.shared
      .authoritativeKnowledgeLedgerMirrorAuthority(ownerID: authorization.ownerID)
    XCTAssertTrue(activeAuthority?.matches(knownAuthority) == true)
  }

  func testInterruptedOrLoopedLedgerMirrorChainPreservesPriorActiveEpoch() async throws {
    let authorization = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let active = makeMemory(id: "ledger-active-before-stage", metadata: canonicalMetadata())
    _ = try await MemoryStorage.shared.stageAuthoritativeKnowledgeLedgerMirrorPage(
      mirrorPage(
        ownerID: authorization.ownerID,
        epochID: String(repeating: "1", count: 64),
        commitSequence: 1,
        pageRevision: String(repeating: "2", count: 64),
        chainRevision: String(repeating: "3", count: 64),
        scannedCount: 1,
        projectedCount: 1,
        rows: [mirrorRow(active)],
        nextCursor: nil,
        finalPage: true),
      requestedCursor: nil,
      authorizationSnapshot: authorization)

    let staged = makeMemory(id: "ledger-incomplete-stage", metadata: canonicalMetadata())
    _ = try await MemoryStorage.shared.stageAuthoritativeKnowledgeLedgerMirrorPage(
      mirrorPage(
        ownerID: authorization.ownerID,
        epochID: String(repeating: "4", count: 64),
        commitSequence: 2,
        pageRevision: String(repeating: "5", count: 64),
        chainRevision: String(repeating: "6", count: 64),
        scannedCount: 1,
        projectedCount: 1,
        rows: [mirrorRow(staged)],
        nextCursor: "looping-cursor",
        finalPage: false),
      requestedCursor: nil,
      authorizationSnapshot: authorization)

    do {
      _ = try await MemoryStorage.shared.stageAuthoritativeKnowledgeLedgerMirrorPage(
        mirrorPage(
          ownerID: authorization.ownerID,
          epochID: String(repeating: "4", count: 64),
          commitSequence: 2,
          pageRevision: String(repeating: "7", count: 64),
          chainRevision: String(repeating: "8", count: 64),
          scannedCount: 1,
          projectedCount: 1,
          rows: [],
          nextCursor: "looping-cursor",
          finalPage: false),
        requestedCursor: "looping-cursor",
        authorizationSnapshot: authorization)
      XCTFail("Expected a repeated cursor to fail closed")
    } catch KnowledgeLedgerMirrorSyncError.invalidSnapshot {
      // Expected. The failed page transaction must not affect active state.
    }
    let preservedMembers = try await MemoryStorage.shared.getAuthoritativeKnowledgeLedgerMirrorMembers(
      ownerID: authorization.ownerID)
    let stagedMemory = try await MemoryStorage.shared.getMemoryByBackendId(staged.id)
    XCTAssertEqual(preservedMembers.map(\.memoryID), [active.id])
    XCTAssertNil(stagedMemory)
  }

  private func mirrorRow(_ memory: ServerMemory) -> KnowledgeLedgerMirrorRow {
    KnowledgeLedgerMirrorRow(
      memoryID: memory.id,
      itemRevision: 1,
      status: "active",
      sourceState: "active",
      canonicalMemoryID: nil,
      contentPurged: false,
      memory: memory)
  }

  private actor MirrorPageFetchGate {
    private var releaseContinuation: CheckedContinuation<Void, Never>?
    private var enteredContinuation: CheckedContinuation<Void, Never>?
    private var released = false
    private(set) var hasEntered = false

    func waitUntilEntered() async {
      if hasEntered { return }
      await withCheckedContinuation { continuation in
        enteredContinuation = continuation
      }
    }

    func waitUntilRelease() async {
      hasEntered = true
      enteredContinuation?.resume()
      enteredContinuation = nil
      if released { return }
      await withCheckedContinuation { continuation in
        releaseContinuation = continuation
      }
    }

    func release() {
      released = true
      releaseContinuation?.resume()
      releaseContinuation = nil
    }
  }

  private actor OverlapMirrorPageFetcher {
    private let oldFirst: KnowledgeLedgerMirrorPage
    private let oldFinal: KnowledgeLedgerMirrorPage
    private let newFinal: KnowledgeLedgerMirrorPage
    private let gate: MirrorPageFetchGate
    private var nilPageCalls = 0

    init(
      oldFirst: KnowledgeLedgerMirrorPage,
      oldFinal: KnowledgeLedgerMirrorPage,
      newFinal: KnowledgeLedgerMirrorPage,
      gate: MirrorPageFetchGate
    ) {
      self.oldFirst = oldFirst
      self.oldFinal = oldFinal
      self.newFinal = newFinal
      self.gate = gate
    }

    func fetch(
      cursor: String?, authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    ) async throws -> KnowledgeLedgerMirrorPage {
      guard authorizationSnapshot.ownerID == oldFirst.ownerID else {
        throw KnowledgeLedgerMirrorSnapshotError.ownerChanged
      }
      if cursor == nil {
        nilPageCalls += 1
        return nilPageCalls == 1 ? oldFirst : newFinal
      }
      guard cursor == "old-next" else {
        throw KnowledgeLedgerMirrorSnapshotError.invalidPage
      }
      await gate.waitUntilRelease()
      return oldFinal
    }
  }

  private func mirrorPage(
    ownerID: String,
    epochID: String,
    commitSequence: Int,
    headCommitID: String? = nil,
    pageRevision: String,
    chainRevision: String,
    scannedCount: Int,
    projectedCount: Int,
    rows: [KnowledgeLedgerMirrorRow],
    aliases: [KnowledgeLedgerMirrorAlias] = [],
    nextCursor: String?,
    finalPage: Bool
  ) -> KnowledgeLedgerMirrorPage {
    KnowledgeLedgerMirrorPage(
      schemaVersion: KnowledgeLedgerMirrorSnapshot.schemaVersion,
      ownerID: ownerID,
      accountGeneration: 1,
      sourceGeneration: 1,
      writerEpoch: 1,
      headCommitID: headCommitID ?? "head-\(commitSequence)",
      commitSequence: commitSequence,
      epochID: epochID,
      pageRevision: pageRevision,
      chainRevision: chainRevision,
      scannedCount: scannedCount,
      projectedCount: projectedCount,
      rows: rows,
      aliases: aliases,
      nextCursor: nextCursor,
      finalPage: finalPage,
      failureReason: nil)
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
