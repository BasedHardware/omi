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
}
