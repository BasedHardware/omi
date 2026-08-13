@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

final class ContextDeliveryAuthorityTests: XCTestCase {
  @MainActor
  func testProactiveBudgetMultiplierUsesCachedServerPlan() throws {
    let suiteName = "ContextDeliveryAuthorityTests.plan.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    XCTAssertEqual(FloatingBarUsageLimiter.proactiveBudgetMultiplier(defaults: defaults), 1)
    defaults.set(SubscriptionPlanType.operator.rawValue, forKey: .floatingBarCachedPlan)
    XCTAssertEqual(FloatingBarUsageLimiter.proactiveBudgetMultiplier(defaults: defaults), 2)
    defaults.set(SubscriptionPlanType.unlimited.rawValue, forKey: .floatingBarCachedPlan)
    XCTAssertEqual(FloatingBarUsageLimiter.proactiveBudgetMultiplier(defaults: defaults), 1)
    defaults.set(1_900_000_000, forKey: .floatingBarCachedDesktopGrandfatherUntil)
    XCTAssertEqual(
      FloatingBarUsageLimiter.proactiveBudgetMultiplier(
        defaults: defaults,
        now: Date(timeIntervalSince1970: 1_800_000_000)),
      2)
    XCTAssertEqual(
      FloatingBarUsageLimiter.proactiveBudgetMultiplier(
        defaults: defaults,
        now: Date(timeIntervalSince1970: 2_000_000_000)),
      1)
    defaults.set(SubscriptionPlanType.architect.rawValue, forKey: .floatingBarCachedPlan)
    XCTAssertEqual(FloatingBarUsageLimiter.proactiveBudgetMultiplier(defaults: defaults), 4)
  }

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
    XCTAssertEqual(
      (0...5).map { ContextDeliveryBudget.dailyLimit(frequencyLevel: $0, planMultiplier: 2) },
      [0, 20, 40, 80, 120, 200])
    XCTAssertEqual(ContextDeliveryBudget.dailyLimit(frequencyLevel: 5, planMultiplier: 4), 400)
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

    let allDayMidnight = NotificationActivePeriod(startMinute: 0, endMinute: 0)
    XCTAssertTrue(allDayMidnight.isAllDay)
    XCTAssertTrue(allDayMidnight.contains(minuteOfDay: 0))
    XCTAssertTrue(allDayMidnight.contains(minuteOfDay: 23 * 60 + 59))
  }

  func testEqualActivePeriodEndpointsMeanAllDayNotEmptyWindow() {
    // Setting start == end (including 06:00→06:00) is the explicit all-day encoding,
    // not a zero-width window and not "only at that minute".
    let equalSix = NotificationActivePeriod(startMinute: 6 * 60, endMinute: 6 * 60)
    XCTAssertTrue(equalSix.isAllDay)
    XCTAssertTrue(equalSix.contains(minuteOfDay: 3 * 60))
    XCTAssertTrue(equalSix.contains(minuteOfDay: 6 * 60))
    XCTAssertTrue(equalSix.contains(minuteOfDay: 15 * 60))
    XCTAssertTrue(equalSix.contains(minuteOfDay: 23 * 60 + 59))
  }

  func testOvernightActivePeriodPreservesSixToThreeActiveAndQuietComplement() {
    // Product contract: 06:00→03:00 stays active overnight; 03:00→06:00 is the quiet gap.
    let active = NotificationActivePeriod(startMinute: 6 * 60, endMinute: 3 * 60)
    XCTAssertFalse(active.isAllDay)
    XCTAssertTrue(active.contains(minuteOfDay: 6 * 60))
    XCTAssertTrue(active.contains(minuteOfDay: 23 * 60))
    XCTAssertTrue(active.contains(minuteOfDay: 2 * 60 + 59))
    XCTAssertFalse(active.contains(minuteOfDay: 3 * 60))
    XCTAssertFalse(active.contains(minuteOfDay: 5 * 60 + 59))

    let quietComplement = NotificationActivePeriod(startMinute: 3 * 60, endMinute: 6 * 60)
    XCTAssertTrue(quietComplement.contains(minuteOfDay: 3 * 60))
    XCTAssertTrue(quietComplement.contains(minuteOfDay: 5 * 60 + 59))
    XCTAssertFalse(quietComplement.contains(minuteOfDay: 6 * 60))
    XCTAssertFalse(quietComplement.contains(minuteOfDay: 2 * 60))
  }

  func testActivePeriodAllDayLabelSurfacesEqualEndpoints() {
    XCTAssertEqual(
      SettingsControlMetrics.notificationActivePeriodSummaryLabel(
        startMinute: 6 * 60, endMinute: 6 * 60),
      "All day")
    XCTAssertEqual(
      SettingsControlMetrics.notificationActivePeriodSubtitle(
        startMinute: 6 * 60, endMinute: 6 * 60),
      "All day — proactive notifications may appear any time")
    XCTAssertNil(
      SettingsControlMetrics.notificationActivePeriodSummaryLabel(
        startMinute: 6 * 60, endMinute: 3 * 60))
    XCTAssertEqual(
      SettingsControlMetrics.notificationActivePeriodSubtitle(
        startMinute: 6 * 60, endMinute: 3 * 60),
      "When proactive notifications may appear (24-hour time)")
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

  @MainActor
  func testActivePeriodHelperGatesMinutesOutsideConfiguredWindow() throws {
    let suiteName = "ContextDeliveryAuthorityTests.activePeriod.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      XCTFail("failed to create isolated defaults suite")
      return
    }
    defer { defaults.removePersistentDomain(forName: suiteName) }

    defaults.set(8 * 60, forKey: NotificationService.activePeriodStartDefaultsKey)
    defaults.set(22 * 60, forKey: NotificationService.activePeriodEndDefaultsKey)

    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(secondsFromGMT: 0))
    let noon = try XCTUnwrap(calendar.date(from: DateComponents(year: 2026, month: 8, day: 12, hour: 12)))
    let late = try XCTUnwrap(calendar.date(from: DateComponents(year: 2026, month: 8, day: 12, hour: 23)))

    XCTAssertTrue(
      NotificationService.isWithinActivePeriod(now: noon, calendar: calendar, defaults: defaults))
    XCTAssertFalse(
      NotificationService.isWithinActivePeriod(now: late, calendar: calendar, defaults: defaults),
      "active period must suppress proactive paths outside the configured window")
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

  func testCooldownAnchorIncludesInFlightAttempts() {
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    let delivered = now.addingTimeInterval(-60 * 60)
    let inFlight = now.addingTimeInterval(-30)
    XCTAssertEqual(
      ContextDeliveryBudget.cooldownAnchor(lastDeliveredAt: delivered, latestInFlightAttemptedAt: inFlight),
      inFlight)
    XCTAssertTrue(
      ContextDeliveryBudget.isCoolingDown(
        lastDeliveredAt: delivered,
        latestInFlightAttemptedAt: inFlight,
        now: now,
        cooldownSeconds: 10 * 60))
    XCTAssertFalse(
      ContextDeliveryBudget.isCoolingDown(
        lastDeliveredAt: delivered,
        latestInFlightAttemptedAt: now.addingTimeInterval(-11 * 60),
        now: now,
        cooldownSeconds: 10 * 60))

    let otherAssistantPresentation = now.addingTimeInterval(-5)
    XCTAssertEqual(
      ContextDeliveryBudget.cooldownAnchor(
        lastDeliveredAt: delivered,
        latestInFlightAttemptedAt: inFlight,
        lastGlobalPresentationAt: otherAssistantPresentation),
      otherAssistantPresentation,
      "director reservation must share the newest global proactive presentation clock")
  }

  func testDailyBudgetUsesRollingTwentyFourHourWindowNotLocalMidnight() {
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    let windowStart = ContextDeliveryBudget.dailyWindowStart(now: now)
    XCTAssertEqual(windowStart, now.addingTimeInterval(-24 * 60 * 60))
    XCTAssertNotEqual(windowStart, Calendar.current.startOfDay(for: now))
  }

  func testFrequencyCooldownMatchesNotificationSpacingAndMaximumHasNoThrottle() {
    XCTAssertEqual(ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 0), 0)
    XCTAssertEqual(ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 1), 60 * 60)
    XCTAssertEqual(ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 2), 30 * 60)
    XCTAssertEqual(ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 3), 10 * 60)
    XCTAssertEqual(ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 4), 3 * 60)
    XCTAssertEqual(ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 5), 0)
  }

  func testTerminalFailedOrSuppressedDeliveryCannotBeRevived() throws {
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
            deliveredAt DATETIME
          )
          """)
      try db.execute(
        sql: """
          INSERT INTO proactive_deliveries
            (id, decisionType, lifecycleState, provenanceJson, message, deliveredAt)
          VALUES
            ('failed_row', 'suggest', 'failed', '{"failure":"dropped"}', NULL, NULL),
            ('suppressed_row', 'suggest', 'suppressed', '{}', 'body', NULL),
            ('approved_row', 'suggest', 'policy_approved', '{}', 'body', NULL)
          """)
      XCTAssertFalse(
        try ContextDeliveryReconciliation.complete(
          in: db,
          id: "failed_row",
          decisionType: "suggest",
          provenanceJSON: "{}",
          message: "late",
          state: "delivered",
          timestampColumn: "deliveredAt",
          now: Date(timeIntervalSince1970: 1_800_000_000)))
      XCTAssertFalse(
        try ContextDeliveryReconciliation.complete(
          in: db,
          id: "suppressed_row",
          decisionType: "suggest",
          provenanceJSON: "{}",
          message: "late",
          state: "delivered",
          timestampColumn: "deliveredAt",
          now: Date(timeIntervalSince1970: 1_800_000_000)))
      XCTAssertTrue(
        try ContextDeliveryReconciliation.complete(
          in: db,
          id: "approved_row",
          decisionType: "suggest",
          provenanceJSON: "{}",
          message: "shown",
          state: "delivered",
          timestampColumn: "deliveredAt",
          now: Date(timeIntervalSince1970: 1_800_000_000)))
      let rows = try Row.fetchAll(
        db,
        sql: "SELECT id, lifecycleState, message FROM proactive_deliveries ORDER BY id")
      XCTAssertEqual(rows[0]["id"] as String, "approved_row")
      XCTAssertEqual(rows[0]["lifecycleState"] as String, "delivered")
      XCTAssertEqual(rows[0]["message"] as String, "shown")
      XCTAssertEqual(rows[1]["lifecycleState"] as String, "failed")
      XCTAssertNil(rows[1]["message"] as String?)
      XCTAssertEqual(rows[2]["lifecycleState"] as String, "suppressed")
    }
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
