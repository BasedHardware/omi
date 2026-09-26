@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

final class JITTriggerMirrorTests: XCTestCase {
  /// The JIT mirror's create-table migrations must survive a machine that already carries the
  /// tables from an earlier build of this branch, where the same schema shipped under a
  /// different migration identifier and so left no row in `grdb_migrations`.
  func testJITTriggerMirrorSchemaSurvivesPreExistingTables() throws {
    let queue = try DatabaseQueue()
    try queue.write { database in
      // The pre-`snoozedUntil` shape an earlier build of this branch installed.
      try database.create(table: "jit_trigger_mirror") { table in
        table.column("memoryID", .text).primaryKey()
        table.column("accountGeneration", .integer).notNull()
        table.column("itemRevision", .integer).notNull()
        table.column("updatedAt", .datetime).notNull()
        table.column("conditionJSON", .text).notNull()
        table.column("actionType", .text).notNull()
        table.column("actionPrompt", .text).notNull()
        table.column("wakeupBudgetPerDay", .integer)
      }
      try database.create(table: "jit_knowledge_ledger_mirror_receipts") { table in
        table.column("ownerID", .text).primaryKey()
      }
    }

    var migrator = DatabaseMigrator()
    JITTriggerMirrorSchema.registerMigration(on: &migrator)
    XCTAssertNoThrow(try migrator.migrate(queue))

    try queue.read { database in
      XCTAssertTrue(try database.columns(in: "jit_trigger_mirror").contains { $0.name == "snoozedUntil" })
      XCTAssertTrue(try database.tableExists("jit_knowledge_ledger_mirror_members"))
      XCTAssertTrue(try database.tableExists("jit_ambient_context_state"))
      XCTAssertTrue(try database.tableExists("jit_nano_billing_observations"))
    }
  }

  func testNanoBillingObservationPersistsOnlyBoundedAccountingFields() throws {
    let queue = try migratedQueue()
    let observation = JITProactivityNanoBillingObservation(
      dispatch: "observed",
      lane: .ambient,
      ownerID: "qa-owner",
      accountGeneration: 3,
      snapshotRevision: "revision",
      budgetDay: "2026-09-06",
      contextID: "context-1",
      candidateID: "candidate-1",
      executionID: "execution-1",
      outcome: "unknown",
      operation: "proactive_extraction",
      requestID: "request-1",
      provider: "openai",
      providerModel: "gpt-5-nano",
      providerResponseID: "response-1",
      fallbackClass: "unknown",
      inputTokens: nil,
      outputTokens: nil,
      totalTokens: nil,
      cachedInputTokens: nil,
      cacheWriteTokens: nil,
      usageStatus: "unknown",
      costStatus: "unknown",
      estimatedCostMicroUSD: nil,
      providerAttempts: nil,
      attemptIDs: [])
    try queue.write { db in
      try JITTriggerMirror.recordNanoBillingObservation(observation, in: db)
    }
    try queue.read { db in
      let row = try XCTUnwrap(
        Row.fetchOne(
          db,
          sql:
            "SELECT outcome, requestID, providerResponseID, inputTokens, costStatus, attemptIDsJSON FROM jit_nano_billing_observations WHERE observationID = ?",
          arguments: [observation.observationID]))
      XCTAssertEqual(row["outcome"] as String, "unknown")
      XCTAssertEqual(row["requestID"] as String, "request-1")
      XCTAssertEqual(row["providerResponseID"] as String, "response-1")
      XCTAssertNil(row["inputTokens"] as Int?)
      XCTAssertEqual(row["costStatus"] as String, "unknown")
      XCTAssertEqual(row["attemptIDsJSON"] as String, "[]")
    }
  }

  func testSnoozedUntilDecodesTimezoneAwareAndMalformedValueFailsClosed() throws {
    let expiry = Date(timeIntervalSince1970: 1_787_572_800)
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    let encoded = try encoder.encode(row(id: "snoozed", snoozedUntil: expiry))
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    var malformed = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
    malformed["snoozed_until"] = "2026-08-24T08:00:00-04:00"
    let offsetDecoded = try decoder.decode(
      JITTriggerSnapshotRow.self,
      from: JSONSerialization.data(withJSONObject: malformed))
    let expectedOffset = try XCTUnwrap(
      ISO8601DateFormatter().date(from: "2026-08-24T12:00:00Z"))
    XCTAssertEqual(offsetDecoded.snoozedUntil, expectedOffset)

    malformed["snoozed_until"] = "not-an-instant"
    XCTAssertThrowsError(
      try decoder.decode(
        JITTriggerSnapshotRow.self,
        from: JSONSerialization.data(withJSONObject: malformed)))
  }

  func testSnoozedUntilPaidClaimRejectsBeforeExpiryAndAllowsAtExactInstant() throws {
    let queue = try migratedQueue()
    let expiry = Date(timeIntervalSince1970: 200)
    let currentRow = row(id: "snoozed", snoozedUntil: expiry)
    let receipt = try queue.write { db in
      try JITTriggerMirror.reconcile(
        snapshot(sequence: 4, revision: "revision-with-snooze", rows: [currentRow]),
        in: db, now: Date(timeIntervalSince1970: 100))
    }

    let before = try queue.write { db in
      try JITTriggerMirror.claimPlannedWakeup(
        plannedRequest(
          continuityKey: "before", receipt: receipt, triggerRow: currentRow,
          now: expiry.addingTimeInterval(-0.001)),
        in: db)
    }
    XCTAssertNil(before)

    let atExpiry = try queue.write { db in
      try JITTriggerMirror.claimPlannedWakeup(
        plannedRequest(
          continuityKey: "at-expiry", receipt: receipt, triggerRow: currentRow, now: expiry),
        in: db)
    }
    XCTAssertNotNil(atExpiry)
  }

  func testRuntimePolicyDecodingIsStrictAndReconciliationRequiresRowAgreement() throws {
    let encoded = try JSONEncoder().encode(JITTriggerRuntimePolicy.ratifiedV1)
    let decoded = try JSONDecoder().decode(JITTriggerRuntimePolicy.self, from: encoded)
    XCTAssertEqual(decoded, .ratifiedV1)
    XCTAssertTrue(decoded.isValid)

    var object = try XCTUnwrap(
      JSONSerialization.jsonObject(with: encoded) as? [String: Any])
    object["unknown_policy"] = true
    XCTAssertThrowsError(
      try JSONDecoder().decode(
        JITTriggerRuntimePolicy.self,
        from: JSONSerialization.data(withJSONObject: object)))

    object.removeValue(forKey: "unknown_policy")
    object["total_proactive_notifications_per_day"] = 4
    let nonRatified = try JSONDecoder().decode(
      JITTriggerRuntimePolicy.self,
      from: JSONSerialization.data(withJSONObject: object))
    XCTAssertFalse(nonRatified.isValid)

    let queue = try migratedQueue()
    let mismatched = JITTriggerSnapshotRow(
      memoryID: "mismatch", itemRevision: 1, updatedAt: Date(),
      triggerConditionJSON:
        "{\"action\":{\"prompt\":\"Do it\",\"type\":\"agent_prompt\"},\"keywords\":[\"release\"],\"schema_version\":\"jit_trigger.v1\"}",
      action: JITTriggerSnapshotAction(type: "agent_prompt", prompt: "Do it"),
      wakeupBudgetPerDay: 2)
    XCTAssertThrowsError(
      try queue.write { db in
        _ = try JITTriggerMirror.reconcile(
          snapshot(sequence: 1, revision: "policy", rows: [mismatched]),
          in: db, now: Date())
      }
    ) { error in
      XCTAssertEqual(error as? JITTriggerMirrorError, .malformedRow)
    }
  }

  func testExhaustiveSnapshotPrunesDeletedRowsAndRejectsConflictingReceipt() throws {
    let queue = try migratedQueue()
    let first = snapshot(sequence: 4, revision: "revision-4", rows: [row(id: "a"), row(id: "b")])
    try queue.write { db in
      _ = try JITTriggerMirror.reconcile(first, in: db, now: Date(timeIntervalSince1970: 1))
    }
    let deletion = snapshot(sequence: 5, revision: "revision-5", rows: [row(id: "b", revision: 2)])
    try queue.write { db in
      _ = try JITTriggerMirror.reconcile(deletion, in: db, now: Date(timeIntervalSince1970: 2))
    }
    let ids = try queue.read { db in
      try String.fetchAll(db, sql: "SELECT memoryID FROM jit_trigger_mirror ORDER BY memoryID")
    }
    XCTAssertEqual(ids, ["b"])

    XCTAssertThrowsError(
      try queue.write { db in
        _ = try JITTriggerMirror.reconcile(
          snapshot(sequence: 5, revision: "different", rows: []), in: db, now: Date())
      }
    ) { error in
      XCTAssertEqual(error as? JITTriggerMirrorError, .conflictingRevision)
    }
  }

  func testMalformedReplacementRollsBackWithoutDeletingPriorMirror() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      _ = try JITTriggerMirror.reconcile(
        snapshot(sequence: 1, revision: "one", rows: [row(id: "safe")]), in: db, now: Date())
    }
    var malformed = row(id: "unsafe")
    malformed = JITTriggerSnapshotRow(
      memoryID: malformed.memoryID,
      itemRevision: malformed.itemRevision,
      updatedAt: malformed.updatedAt,
      triggerConditionJSON: malformed.triggerConditionJSON,
      action: JITTriggerSnapshotAction(type: "agent_prompt", prompt: "different action"),
      wakeupBudgetPerDay: malformed.wakeupBudgetPerDay)
    XCTAssertThrowsError(
      try queue.write { db in
        _ = try JITTriggerMirror.reconcile(
          snapshot(sequence: 2, revision: "two", rows: [malformed]), in: db, now: Date())
      })
    let ids = try queue.read { db in try String.fetchAll(db, sql: "SELECT memoryID FROM jit_trigger_mirror") }
    XCTAssertEqual(ids, ["safe"])
  }

  func testWakeupLeaseDeduplicatesAcrossLanesAndCanRecoverAfterCrash() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 100)
    let first = try queue.write { db in
      try JITTriggerMirror.claimWakeup(
        continuityKey: "shared", triggerID: "trigger", lane: .planned,
        budgetDay: "2026-08-24", snapshotRevision: "r", observationFingerprint: "f",
        budget: 1, now: now, leaseSeconds: 30, in: db)
    }
    XCTAssertNotNil(first)
    let raced = try queue.write { db in
      try JITTriggerMirror.claimWakeup(
        continuityKey: "shared", triggerID: "ambient", lane: .ambient,
        budgetDay: "2026-08-24", snapshotRevision: "r", observationFingerprint: "f",
        budget: 1, now: now.addingTimeInterval(1), leaseSeconds: 30, in: db)
    }
    XCTAssertNil(raced)
    let recovered = try queue.write { db in
      try JITTriggerMirror.claimWakeup(
        continuityKey: "shared", triggerID: "trigger", lane: .planned,
        budgetDay: "2026-08-24", snapshotRevision: "r", observationFingerprint: "f",
        budget: 1, now: now.addingTimeInterval(31), leaseSeconds: 30, in: db)
    }
    XCTAssertNotNil(recovered)
    XCTAssertNotEqual(first?.leaseToken, recovered?.leaseToken)
  }

  func testAmbientExecutionUsesTheSameRenewableRunningLease() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 100)
    let claim = try XCTUnwrap(
      queue.write { db in
        try JITTriggerMirror.claimWakeup(
          continuityKey: "ambient", triggerID: "ambient:bucket", lane: .ambient,
          budgetDay: "2026-08-24", snapshotRevision: "r", observationFingerprint: "f",
          budget: 1, now: now, in: db)
      })

    let began = try queue.write { db in
      try JITTriggerMirror.beginAmbientExecution(
        claim: claim, now: now.addingTimeInterval(1), in: db)
    }
    let renewed = try queue.write { db in
      try JITTriggerMirror.renewExecutionLease(
        claim: claim, now: now.addingTimeInterval(250), in: db)
    }
    let duplicate = try queue.write { db in
      try JITTriggerMirror.claimWakeup(
        continuityKey: "ambient", triggerID: "ambient:bucket", lane: .ambient,
        budgetDay: "2026-08-24", snapshotRevision: "r", observationFingerprint: "f",
        budget: 1, now: now.addingTimeInterval(500), in: db)
    }

    XCTAssertTrue(began)
    XCTAssertTrue(renewed)
    XCTAssertNil(duplicate)
  }

  func testPlannedClaimAtomicallyRejectsEverySnapshotAuthorityMismatch() throws {
    let queue = try migratedQueue()
    let currentRow = row(id: "trigger")
    let current = snapshot(sequence: 4, revision: "revision-4", rows: [currentRow])
    let receipt = try queue.write { db in
      try JITTriggerMirror.reconcile(current, in: db, now: Date())
    }
    let mismatches = [
      JITTriggerMirrorReceipt(
        ownerID: "other", accountGeneration: receipt.accountGeneration,
        commitSequence: receipt.commitSequence, snapshotRevision: receipt.snapshotRevision,
        rowCount: receipt.rowCount),
      JITTriggerMirrorReceipt(
        ownerID: receipt.ownerID, accountGeneration: receipt.accountGeneration + 1,
        commitSequence: receipt.commitSequence, snapshotRevision: receipt.snapshotRevision,
        rowCount: receipt.rowCount),
      JITTriggerMirrorReceipt(
        ownerID: receipt.ownerID, accountGeneration: receipt.accountGeneration,
        commitSequence: receipt.commitSequence + 1, snapshotRevision: receipt.snapshotRevision,
        rowCount: receipt.rowCount),
      JITTriggerMirrorReceipt(
        ownerID: receipt.ownerID, accountGeneration: receipt.accountGeneration,
        commitSequence: receipt.commitSequence, snapshotRevision: "other-revision",
        rowCount: receipt.rowCount),
      JITTriggerMirrorReceipt(
        ownerID: receipt.ownerID, accountGeneration: receipt.accountGeneration,
        commitSequence: receipt.commitSequence, snapshotRevision: receipt.snapshotRevision,
        rowCount: receipt.rowCount + 1),
    ]

    for (index, mismatch) in mismatches.enumerated() {
      let claim = try queue.write { db in
        try JITTriggerMirror.claimPlannedWakeup(
          plannedRequest(
            continuityKey: "mismatch-\(index)", receipt: mismatch, triggerRow: currentRow),
          in: db)
      }
      XCTAssertNil(claim, "authority mismatch \(index) must fail closed")
    }
    let inserted = try queue.read { db in
      try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM jit_trigger_wakeup_receipts") ?? -1
    }
    XCTAssertEqual(inserted, 0)
  }

  func testPlannedClaimRejectsDeletedOrChangedMirrorMembership() throws {
    for mutation in [
      "DELETE FROM jit_trigger_mirror WHERE memoryID = 'trigger'",
      "UPDATE jit_trigger_mirror SET actionPrompt = 'changed' WHERE memoryID = 'trigger'",
      "UPDATE jit_trigger_mirror SET itemRevision = itemRevision + 1 WHERE memoryID = 'trigger'",
    ] {
      let queue = try migratedQueue()
      let currentRow = row(id: "trigger")
      let receipt = try queue.write { db in
        let receipt = try JITTriggerMirror.reconcile(
          snapshot(sequence: 4, revision: "revision-4", rows: [currentRow]),
          in: db, now: Date())
        try db.execute(sql: mutation)
        return receipt
      }

      let claim = try queue.write { db in
        try JITTriggerMirror.claimPlannedWakeup(
          plannedRequest(receipt: receipt, triggerRow: currentRow), in: db)
      }

      XCTAssertNil(claim, "stale membership must fail closed after: \(mutation)")
    }
  }

  func testPlannedClaimChecksAuthorityAndMembershipBeforeAtomicInsert() throws {
    let queue = try migratedQueue()
    let currentRow = row(id: "trigger")
    let receipt = try queue.write { db in
      try JITTriggerMirror.reconcile(
        snapshot(sequence: 4, revision: "revision-4", rows: [currentRow]),
        in: db, now: Date())
    }

    let claim = try queue.write { db in
      try JITTriggerMirror.claimPlannedWakeup(
        plannedRequest(receipt: receipt, triggerRow: currentRow), in: db)
    }

    XCTAssertNotNil(claim)
  }

  func testExecutionStartAtomicallyConsumesOneCurrentPlannedClaim() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 100)
    let currentRow = row(id: "trigger")
    let receipt = try queue.write { db in
      try JITTriggerMirror.reconcile(
        snapshot(sequence: 4, revision: "revision-4", rows: [currentRow]),
        in: db, now: now)
    }
    let claim = try XCTUnwrap(
      queue.write { db in
        try JITTriggerMirror.claimPlannedWakeup(
          plannedRequest(receipt: receipt, triggerRow: currentRow), in: db)
      })
    let authority = JITPlannedExecutionAuthority(receipt: receipt, triggerRow: currentRow)

    let began = try queue.write { db in
      try JITTriggerMirror.beginPlannedExecution(
        authority, claim: claim, now: now.addingTimeInterval(1), in: db)
    }
    let replay = try queue.write { db in
      try JITTriggerMirror.beginPlannedExecution(
        authority, claim: claim, now: now.addingTimeInterval(2), in: db)
    }
    let renewed = try queue.write { db in
      try JITTriggerMirror.renewExecutionLease(
        claim: claim, now: now.addingTimeInterval(250), in: db)
    }
    let stateAndExpiry = try queue.read { db -> (String?, Date?) in
      let row = try Row.fetchOne(
        db, sql: "SELECT state, leaseExpiresAt FROM jit_trigger_wakeup_receipts WHERE continuityKey = ?",
        arguments: [claim.continuityKey])
      return (row?["state"], row?["leaseExpiresAt"])
    }
    let duplicateWhileRunning = try queue.write { db in
      try JITTriggerMirror.claimPlannedWakeup(
        plannedRequest(receipt: receipt, triggerRow: currentRow),
        in: db)
    }
    let recoveredAfterHeartbeatStops = try queue.write { db in
      let request = plannedRequest(
        continuityKey: claim.continuityKey, receipt: receipt, triggerRow: currentRow)
      return try JITTriggerMirror.claimPlannedWakeup(
        JITPlannedWakeupRequest(
          continuityKey: request.continuityKey, triggerID: request.triggerID, lane: request.lane,
          budgetDay: request.budgetDay, snapshotRevision: request.snapshotRevision,
          observationFingerprint: request.observationFingerprint, budget: request.budget,
          now: now.addingTimeInterval(551), authority: request.authority,
          triggerRow: request.triggerRow),
        in: db)
    }

    XCTAssertTrue(began)
    XCTAssertFalse(replay)
    XCTAssertTrue(renewed)
    XCTAssertEqual(stateAndExpiry.0, "executing")
    XCTAssertEqual(stateAndExpiry.1, now.addingTimeInterval(550))
    XCTAssertNil(duplicateWhileRunning)
    XCTAssertNotNil(recoveredAfterHeartbeatStops)
    XCTAssertNotEqual(recoveredAfterHeartbeatStops?.leaseToken, claim.leaseToken)
  }

  func testOwnerTransitionCannotReuseOldReceiptAgainstIdenticalMirrorRow() throws {
    let queue = try migratedQueue()
    let currentRow = row(id: "trigger")
    let oldReceipt = try queue.write { db in
      try JITTriggerMirror.reconcile(
        snapshot(sequence: 4, revision: "revision-4", rows: [currentRow]),
        in: db, now: Date())
    }
    let replacement = JITTriggerSnapshot(
      ownerID: "new-owner", accountGeneration: 3, headCommitID: "new-head",
      commitSequence: 4, snapshotRevision: "new-revision", complete: true,
      rows: [currentRow], failureReason: nil)
    try queue.write { db in
      _ = try JITTriggerMirror.reconcile(replacement, in: db, now: Date())
    }

    let staleClaim = try queue.write { db in
      try JITTriggerMirror.claimPlannedWakeup(
        plannedRequest(receipt: oldReceipt, triggerRow: currentRow), in: db)
    }

    XCTAssertNil(staleClaim)
  }

  func testNewAccountGenerationClearsPriorContinuityBudget() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      _ = try JITTriggerMirror.reconcile(
        snapshot(sequence: 1, revision: "old", rows: [row(id: "trigger")]),
        in: db, now: Date())
      _ = try JITTriggerMirror.claimWakeup(
        continuityKey: "prior", triggerID: "trigger", lane: .planned,
        budgetDay: "2026-08-24", snapshotRevision: "old", observationFingerprint: "f",
        budget: 1, now: Date(), in: db)
      _ = try JITTriggerMirror.claimAmbientNanoChange(
        contextID: "prior-bucket", semanticFingerprint: "prior-semantic",
        budgetDay: "2026-08-24", snapshotRevision: "old", budget: 8, now: Date(), in: db)
      _ = try JITTriggerMirror.reconcile(
        snapshot(generation: 4, sequence: 0, revision: "reset", rows: []),
        in: db, now: Date())
    }
    let receiptCount = try queue.read { db in
      try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM jit_trigger_wakeup_receipts") ?? -1
    }
    let ambientCount = try queue.read { db in
      try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM jit_ambient_context_state") ?? -1
    }
    XCTAssertEqual(receiptCount, 0)
    XCTAssertEqual(ambientCount, 0)
  }

  func testAmbientNanoBudgetCountsDistinctAttemptsAndStopsBeforeAnotherProviderCall() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      for index in 0..<2 {
        let claim = try JITTriggerMirror.claimWakeup(
          continuityKey: "nano:\(index)", triggerID: "ambient-nano", lane: .ambient,
          budgetDay: "2026-08-24", snapshotRevision: "r", observationFingerprint: "f\(index)",
          budget: 2, now: Date(), in: db)
        XCTAssertNotNil(claim)
        try db.execute(
          sql: "UPDATE jit_trigger_wakeup_receipts SET state = 'delivered' WHERE continuityKey = ?",
          arguments: ["nano:\(index)"])
      }
      let exhausted = try JITTriggerMirror.claimWakeup(
        continuityKey: "nano:2", triggerID: "ambient-nano", lane: .ambient,
        budgetDay: "2026-08-24", snapshotRevision: "r", observationFingerprint: "f2",
        budget: 2, now: Date(), in: db)
      XCTAssertNil(exhausted)
    }
  }

  func testWakeupCountsIncludeDeliveredLiveClaimsAndExecutingButExcludeExpiredAndFailed() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 1_000)
    try queue.write { db in
      for (key, triggerID, state, expiry) in [
        ("delivered", "a", "delivered", now.addingTimeInterval(-10)),
        ("live", "a", "claimed", now.addingTimeInterval(10)),
        ("executing", "a", "executing", now.addingTimeInterval(10)),
        ("expired", "a", "claimed", now.addingTimeInterval(-1)),
        ("failed", "a", "failed", now.addingTimeInterval(10)),
        ("other", "b", "delivered", now.addingTimeInterval(10)),
      ] {
        try db.execute(
          sql: """
            INSERT INTO jit_trigger_wakeup_receipts
              (continuityKey, triggerID, lane, budgetDay, snapshotRevision, observationFingerprint,
               state, leaseToken, leaseExpiresAt, updatedAt)
            VALUES (?, ?, 'planned', '2026-08-24', 'r', 'f', ?, 'token', ?, ?)
            """,
          arguments: [key, triggerID, state, expiry, now])
      }
    }

    let counts = try queue.read { db in
      try JITTriggerMirror.wakeupCounts(
        triggerIDs: ["b", "a", "a"], budgetDay: "2026-08-24", now: now, in: db)
    }

    XCTAssertEqual(counts, ["a": 3, "b": 1])
  }

  func testWakeupCountsRejectMoreThanSnapshotBound() throws {
    let queue = try migratedQueue()
    let triggerIDs = (0...KnowledgeLedgerTriggerWatchlistRuntime.maxWakeupCounterCandidates).map {
      "trigger-\($0)"
    }
    XCTAssertThrowsError(
      try queue.read { db in
        try JITTriggerMirror.wakeupCounts(
          triggerIDs: triggerIDs, budgetDay: "2026-08-24", now: Date(), in: db)
      }
    ) { error in
      XCTAssertEqual(error as? JITTriggerMirrorError, .malformedRow)
    }
  }

  func testAmbientSemanticStateAdvancesOnlyAfterProviderAttemptAndCrashCanRecover() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 100)
    try queue.write { db in
      let first = try JITTriggerMirror.claimAmbientNanoChange(
        contextID: "bucket", semanticFingerprint: "stable", budgetDay: "2026-08-24",
        snapshotRevision: "r", budget: 8, now: now, in: db)
      XCTAssertNotNil(first)
      XCTAssertEqual(
        try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM jit_ambient_context_state"), 0)

      let beforeLeaseExpiry = try JITTriggerMirror.claimAmbientNanoChange(
        contextID: "bucket", semanticFingerprint: "stable", budgetDay: "2026-08-24",
        snapshotRevision: "r", budget: 8, now: now.addingTimeInterval(1), in: db)
      XCTAssertNil(beforeLeaseExpiry)

      let recovered = try JITTriggerMirror.claimAmbientNanoChange(
        contextID: "bucket", semanticFingerprint: "stable", budgetDay: "2026-08-24",
        snapshotRevision: "r", budget: 8, now: now.addingTimeInterval(181), in: db)
      XCTAssertNotNil(recovered)
      XCTAssertNotEqual(first?.leaseToken, recovered?.leaseToken)
      guard let recovered else {
        return XCTFail("expired ambient lease should be recoverable")
      }
      XCTAssertTrue(
        try JITTriggerMirror.completeAmbientNanoAttempt(
          recovered, contextID: "bucket", semanticFingerprint: "stable",
          now: now.addingTimeInterval(182), in: db))

      let unchangedAfterCompletion = try JITTriggerMirror.claimAmbientNanoChange(
        contextID: "bucket", semanticFingerprint: "stable", budgetDay: "2026-08-24",
        snapshotRevision: "r", budget: 8, now: now.addingTimeInterval(183), in: db)
      let changedAfterCompletion = try JITTriggerMirror.claimAmbientNanoChange(
        contextID: "bucket", semanticFingerprint: "changed", budgetDay: "2026-08-24",
        snapshotRevision: "r", budget: 8, now: now.addingTimeInterval(184), in: db)

      XCTAssertNil(unchangedAfterCompletion)
      XCTAssertNotNil(changedAfterCompletion)
    }
  }

  func testPlannedContinuityRecursAcrossDaysAndSnapshotRevisions() {
    let first = JITProactivityRuntime.plannedContinuityKey(
      triggerID: "standing", snapshotRevision: "r1", budgetDay: "2026-08-24",
      observationFingerprint: "same")
    XCTAssertEqual(
      first,
      JITProactivityRuntime.plannedContinuityKey(
        triggerID: "standing", snapshotRevision: "r1", budgetDay: "2026-08-24",
        observationFingerprint: "same"))
    XCTAssertNotEqual(
      first,
      JITProactivityRuntime.plannedContinuityKey(
        triggerID: "standing", snapshotRevision: "r1", budgetDay: "2026-08-25",
        observationFingerprint: "same"))
    XCTAssertNotEqual(
      first,
      JITProactivityRuntime.plannedContinuityKey(
        triggerID: "standing", snapshotRevision: "r2", budgetDay: "2026-08-24",
        observationFingerprint: "same"))
  }

  private func migratedQueue() throws -> DatabaseQueue {
    let queue = try DatabaseQueue()
    var migrator = DatabaseMigrator()
    JITTriggerMirrorSchema.registerMigration(on: &migrator)
    try migrator.migrate(queue)
    return queue
  }

  private func snapshot(
    generation: Int = 3, sequence: Int, revision: String, rows: [JITTriggerSnapshotRow]
  ) -> JITTriggerSnapshot {
    JITTriggerSnapshot(
      ownerID: "owner", accountGeneration: generation, headCommitID: "head-\(sequence)",
      commitSequence: sequence, snapshotRevision: revision, complete: true, rows: rows,
      failureReason: nil)
  }

  private func row(
    id: String, revision: Int = 1, snoozedUntil: Date? = nil
  ) -> JITTriggerSnapshotRow {
    let prompt = "Tell me the next release step"
    let condition = """
      {"action":{"prompt":"\(prompt)","type":"agent_prompt"},"keywords":["release"],"match_mode":"all","schema_version":"jit_trigger.v1"}
      """
    return JITTriggerSnapshotRow(
      memoryID: id, itemRevision: revision, updatedAt: Date(timeIntervalSince1970: 10),
      triggerConditionJSON: condition,
      action: JITTriggerSnapshotAction(type: "agent_prompt", prompt: prompt),
      wakeupBudgetPerDay: 1,
      snoozedUntil: snoozedUntil)
  }

  private func plannedRequest(
    continuityKey: String = "planned", receipt: JITTriggerMirrorReceipt,
    triggerRow: JITTriggerSnapshotRow,
    now: Date = Date(timeIntervalSince1970: 100)
  ) -> JITPlannedWakeupRequest {
    JITPlannedWakeupRequest(
      continuityKey: continuityKey, triggerID: triggerRow.memoryID, lane: .planned,
      budgetDay: "2026-08-24", snapshotRevision: receipt.snapshotRevision,
      observationFingerprint: "fingerprint", budget: triggerRow.wakeupBudgetPerDay,
      now: now, authority: receipt, triggerRow: triggerRow)
  }
}
