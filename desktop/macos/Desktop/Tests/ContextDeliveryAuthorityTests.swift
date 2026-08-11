@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

final class ContextDeliveryAuthorityTests: XCTestCase {
  func testFreeGatesAreSingleAuthorityInputs() {
    XCTAssertEqual(
      ContextDeliveryBudget.freeGate(
        input: .init(
          masterEnabled: true, frequencyLevel: 3, snoozed: false, paywalled: false, minuteOfDay: 12 * 60,
          cooldownSeconds: 30 * 60)),
      .allowed)
    XCTAssertEqual(
      ContextDeliveryBudget.freeGate(
        input: .init(
          masterEnabled: true, frequencyLevel: 3, snoozed: false, paywalled: false, minuteOfDay: 23 * 60,
          cooldownSeconds: 30 * 60)),
      .quietHours)
    XCTAssertEqual(ContextDeliveryBudget.dailyLimit(frequencyLevel: 5), 20)
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    XCTAssertTrue(
      ContextDeliveryBudget.isCoolingDown(
        lastDeliveredAt: now.addingTimeInterval(-60), now: now, cooldownSeconds: 30 * 60))
  }

  func testFreeGateBoundariesAndSuppressionInputs() {
    let base = ContextDeliveryGateInput(
      masterEnabled: true, frequencyLevel: 3, snoozed: false, paywalled: false,
      minuteOfDay: 8 * 60, cooldownSeconds: 30 * 60)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: base), .allowed)
    XCTAssertEqual(
      ContextDeliveryBudget.freeGate(
        input: .init(
          masterEnabled: true, frequencyLevel: 3, snoozed: false, paywalled: false,
          minuteOfDay: 22 * 60, cooldownSeconds: 0)), .quietHours)
    XCTAssertEqual(
      ContextDeliveryBudget.freeGate(
        input: .init(
          masterEnabled: false, frequencyLevel: 3, snoozed: false, paywalled: false,
          minuteOfDay: 12 * 60, cooldownSeconds: 0)), .masterDisabled)
    XCTAssertEqual(
      ContextDeliveryBudget.freeGate(
        input: .init(
          masterEnabled: true, frequencyLevel: 0, snoozed: false, paywalled: false,
          minuteOfDay: 12 * 60, cooldownSeconds: 0)), .frequencyDisabled)
    XCTAssertEqual(
      ContextDeliveryBudget.freeGate(
        input: .init(
          masterEnabled: true, frequencyLevel: 3, snoozed: true, paywalled: false,
          minuteOfDay: 12 * 60, cooldownSeconds: 0)), .snoozed)
    XCTAssertEqual(
      ContextDeliveryBudget.freeGate(
        input: .init(
          masterEnabled: true, frequencyLevel: 3, snoozed: false, paywalled: true,
          minuteOfDay: 12 * 60, cooldownSeconds: 0)), .paywalled)
  }

  func testCoolingDownHandlesMissingZeroAndElapsedCooldown() {
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    XCTAssertFalse(ContextDeliveryBudget.isCoolingDown(lastDeliveredAt: nil, now: now, cooldownSeconds: 30))
    XCTAssertFalse(
      ContextDeliveryBudget.isCoolingDown(
        lastDeliveredAt: now.addingTimeInterval(-1), now: now, cooldownSeconds: 0))
    XCTAssertFalse(
      ContextDeliveryBudget.isCoolingDown(
        lastDeliveredAt: now.addingTimeInterval(-30), now: now, cooldownSeconds: 30))
  }

  func testAbandonedReconciliationOnlyFailsOldNonterminalRows() throws {
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.execute(
        sql: """
          CREATE TABLE proactive_deliveries (
            id TEXT PRIMARY KEY,
            decisionType TEXT NOT NULL,
            lifecycleState TEXT NOT NULL,
            provenanceJson TEXT NOT NULL,
            message TEXT,
            attemptedAt DATETIME NOT NULL
          )
          """)
    }
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    try queue.write { db in
      for (id, state, attemptedAt) in [
        ("old_attempted", "attempted", now.addingTimeInterval(-901)),
        ("old_approved", "policy_approved", now.addingTimeInterval(-901)),
        ("recent_attempted", "attempted", now.addingTimeInterval(-899)),
        ("old_delivered", "delivered", now.addingTimeInterval(-901)),
      ] {
        try db.execute(
          sql:
            "INSERT INTO proactive_deliveries (id, decisionType, lifecycleState, provenanceJson, message, attemptedAt) VALUES (?, 'suggest', ?, '{}', 'body', ?)",
          arguments: [id, state, attemptedAt])
      }
      XCTAssertEqual(
        try ContextDeliveryReconciliation.reconcileAbandoned(
          in: db, cutoff: now.addingTimeInterval(-900)),
        2)
      let rows = try Row.fetchAll(
        db,
        sql: "SELECT id, lifecycleState, provenanceJson, message FROM proactive_deliveries ORDER BY id")
      XCTAssertEqual(rows[0]["lifecycleState"] as String, "failed")
      XCTAssertEqual(rows[0]["provenanceJson"] as String, "{\"failure\":\"abandoned\"}")
      XCTAssertNil(rows[0]["message"] as String?)
      XCTAssertEqual(rows[1]["lifecycleState"] as String, "failed")
      XCTAssertEqual(rows[2]["lifecycleState"] as String, "delivered")
      XCTAssertEqual(rows[3]["lifecycleState"] as String, "attempted")
    }
  }
}
