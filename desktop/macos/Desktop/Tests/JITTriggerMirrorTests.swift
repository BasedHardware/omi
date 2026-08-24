@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

final class JITTriggerMirrorTests: XCTestCase {
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

  private func row(id: String, revision: Int = 1) -> JITTriggerSnapshotRow {
    let prompt = "Tell me the next release step"
    let condition = """
      {"action":{"prompt":"\(prompt)","type":"agent_prompt"},"keywords":["release"],"match_mode":"all","schema_version":"jit_trigger.v1"}
      """
    return JITTriggerSnapshotRow(
      memoryID: id, itemRevision: revision, updatedAt: Date(timeIntervalSince1970: 10),
      triggerConditionJSON: condition,
      action: JITTriggerSnapshotAction(type: "agent_prompt", prompt: prompt),
      wakeupBudgetPerDay: 1)
  }

  private func plannedRequest(
    continuityKey: String = "planned", receipt: JITTriggerMirrorReceipt,
    triggerRow: JITTriggerSnapshotRow
  ) -> JITPlannedWakeupRequest {
    JITPlannedWakeupRequest(
      continuityKey: continuityKey, triggerID: triggerRow.memoryID, lane: .planned,
      budgetDay: "2026-08-24", snapshotRevision: receipt.snapshotRevision,
      observationFingerprint: "fingerprint", budget: triggerRow.wakeupBudgetPerDay,
      now: Date(timeIntervalSince1970: 100), authority: receipt, triggerRow: triggerRow)
  }
}
