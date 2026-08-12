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
    XCTAssertEqual(
      (0...5).map { ContextDeliveryBudget.dailyLimit(frequencyLevel: $0) },
      [0, 10, 20, 40, 60, 100]
    )
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

  func testActivePeriodSupportsDaytimeOvernightAndAllDayWindows() {
    let daytime = NotificationActivePeriod(startMinute: 8 * 60, endMinute: 22 * 60)
    XCTAssertTrue(daytime.contains(minuteOfDay: 8 * 60))
    XCTAssertTrue(daytime.contains(minuteOfDay: 21 * 60 + 59))
    XCTAssertFalse(daytime.contains(minuteOfDay: 22 * 60))

    let overnight = NotificationActivePeriod(startMinute: 20 * 60, endMinute: 6 * 60)
    XCTAssertTrue(overnight.contains(minuteOfDay: 23 * 60))
    XCTAssertTrue(overnight.contains(minuteOfDay: 5 * 60 + 59))
    XCTAssertFalse(overnight.contains(minuteOfDay: 12 * 60))

    let allDay = NotificationActivePeriod(startMinute: 0, endMinute: 0)
    XCTAssertTrue(allDay.contains(minuteOfDay: 0))
    XCTAssertTrue(allDay.contains(minuteOfDay: 23 * 60 + 59))
  }

  @MainActor
  func testActivePeriodDefaultsAndPersistenceClampMinutes() {
    let suiteName = "ContextDeliveryAuthorityTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      XCTFail("failed to create isolated defaults suite")
      return
    }
    defer { defaults.removePersistentDomain(forName: suiteName) }

    XCTAssertEqual(NotificationService.currentActivePeriod(defaults: defaults), .defaultValue)
    defaults.set(-30, forKey: NotificationService.activePeriodStartDefaultsKey)
    defaults.set(1_500, forKey: NotificationService.activePeriodEndDefaultsKey)
    XCTAssertEqual(
      NotificationService.currentActivePeriod(defaults: defaults),
      NotificationActivePeriod(startMinute: 0, endMinute: 1439))
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

  func testFrequencyCooldownMatchesNotificationSpacingAndMaximumHasNoThrottle() {
    XCTAssertEqual(ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 0), 0)
    XCTAssertEqual(ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 1), 60 * 60)
    XCTAssertEqual(ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 2), 30 * 60)
    XCTAssertEqual(ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 3), 10 * 60)
    XCTAssertEqual(ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 4), 3 * 60)
    XCTAssertEqual(ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 5), 0)
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
