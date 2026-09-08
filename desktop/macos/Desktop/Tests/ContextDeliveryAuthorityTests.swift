@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

final class ContextDeliveryAuthorityTests: XCTestCase {
  /// Context-director decisions ride the same category toggles the Settings pane shows
  /// (Focus, Task, Insight, Memory, Integration, Meeting Summary). Each internal kind
  /// must be gated by exactly its category's toggle; `.general` (functional alerts) is never
  /// category-gated.
  func testDirectorDecisionsAreGatedByTheirCategoryToggle() {
    func allows(
      _ kind: ProactiveNotificationKind, focus: Bool = true, task: Bool = true, insight: Bool = true,
      memory: Bool = true, integration: Bool = true, meetingSummary: Bool = true
    ) -> Bool {
      NotificationService.categoryToggleAllows(
        kind: kind, focusEnabled: focus, taskEnabled: task,
        insightEnabled: insight, memoryEnabled: memory, integrationEnabled: integration,
        meetingSummaryEnabled: meetingSummary)
    }
    // Focus toggle owns the focus-nudge assistant alone.
    XCTAssertFalse(allows(.suggestion, focus: false))
    XCTAssertTrue(allows(.suggestion, task: false, insight: false, memory: false))
    // Task toggle owns task candidates.
    XCTAssertFalse(allows(.task, task: false))
    XCTAssertTrue(allows(.task, focus: false, insight: false, memory: false))
    // The meeting-summary toggle owns the post-meeting share card alone.
    XCTAssertFalse(allows(.meetingNotes, meetingSummary: false))
    XCTAssertTrue(allows(.meetingNotes, focus: false, task: false, insight: false, memory: false))
    // Insight toggle owns insights, tips, resurfaced items, and generated goals.
    XCTAssertFalse(allows(.insight, insight: false))
    XCTAssertFalse(allows(.resurface, insight: false))
    XCTAssertFalse(allows(.goal, insight: false))
    // Memory toggle owns memory extraction.
    XCTAssertFalse(allows(.memory, memory: false))
    // Integration toggle owns connect-an-app offers.
    XCTAssertFalse(allows(.integration, integration: false))
    XCTAssertTrue(allows(.integration, focus: false, task: false, insight: false, memory: false))
    // Functional alerts sit outside the taxonomy.
    XCTAssertTrue(
      allows(.general, focus: false, task: false, insight: false, memory: false, integration: false))
    // The director's decision strings resolve into the gated kinds; "suggest" is a
    // generic tip, which the taxonomy files under Insight.
    XCTAssertEqual(ProactiveNotificationKind.from(decisionType: "suggest"), .insight)
    XCTAssertEqual(ProactiveNotificationKind.from(decisionType: "task_candidate"), .task)
    XCTAssertEqual(ProactiveNotificationKind.from(decisionType: "resurface"), .resurface)
  }

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
          masterEnabled: true, frequencyLevel: 3, paywalled: false,
          cooldownSeconds: 30 * 60)),
      .allowed)
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
      masterEnabled: true, frequencyLevel: 3, paywalled: false,
      cooldownSeconds: 30 * 60)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: base), .allowed)
    XCTAssertEqual(
      ContextDeliveryBudget.freeGate(
        input: .init(
          masterEnabled: false, frequencyLevel: 3, paywalled: false,
          cooldownSeconds: 0)), .masterDisabled)
    XCTAssertEqual(
      ContextDeliveryBudget.freeGate(
        input: .init(
          masterEnabled: true, frequencyLevel: 0, paywalled: false,
          cooldownSeconds: 0)), .frequencyDisabled)
    XCTAssertEqual(
      ContextDeliveryBudget.freeGate(
        input: .init(
          masterEnabled: true, frequencyLevel: 3, paywalled: true,
          cooldownSeconds: 0)), .paywalled)
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

  func testDailyBudgetUsesRollingTwentyFourHourWindowNotLocalMidnight() throws {
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    let windowStart = ContextDeliveryBudget.dailyWindowStart(now: now)
    XCTAssertEqual(windowStart, now.addingTimeInterval(-24 * 60 * 60))
    // The contrast is with *a* local midnight, so it is drawn against a pinned zone rather than the
    // machine's: an assertion that reads `TimeZone.current` states a different thing on every runner.
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
    XCTAssertNotEqual(windowStart, calendar.startOfDay(for: now))
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
