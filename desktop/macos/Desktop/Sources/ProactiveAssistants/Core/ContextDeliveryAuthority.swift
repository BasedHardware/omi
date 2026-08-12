import Foundation
@preconcurrency import GRDB

struct ContextDeliveryGateInput: Equatable, Sendable {
  let masterEnabled: Bool
  let frequencyLevel: Int
  let snoozed: Bool
  let paywalled: Bool
  let minuteOfDay: Int
  let activePeriod: NotificationActivePeriod
  let cooldownSeconds: TimeInterval
  let dailyLimit: Int
  let lastGlobalPresentationAt: Date?

  init(
    masterEnabled: Bool,
    frequencyLevel: Int,
    snoozed: Bool,
    paywalled: Bool,
    minuteOfDay: Int,
    activePeriod: NotificationActivePeriod = .defaultValue,
    cooldownSeconds: TimeInterval,
    dailyLimit: Int? = nil,
    lastGlobalPresentationAt: Date? = nil
  ) {
    self.masterEnabled = masterEnabled
    self.frequencyLevel = frequencyLevel
    self.snoozed = snoozed
    self.paywalled = paywalled
    self.minuteOfDay = minuteOfDay
    self.activePeriod = activePeriod
    self.cooldownSeconds = cooldownSeconds
    self.dailyLimit = max(
      0,
      dailyLimit ?? ContextDeliveryBudget.dailyLimit(frequencyLevel: frequencyLevel))
    self.lastGlobalPresentationAt = lastGlobalPresentationAt
  }
}

struct NotificationActivePeriod: Equatable, Sendable {
  static let defaultValue = NotificationActivePeriod(startMinute: 8 * 60, endMinute: 22 * 60)

  let startMinute: Int
  let endMinute: Int

  init(startMinute: Int, endMinute: Int) {
    self.startMinute = min(max(0, startMinute), 1439)
    self.endMinute = min(max(0, endMinute), 1439)
  }

  /// Equal endpoints are the explicit all-day encoding (any equal pair, including `00:00→00:00`
  /// and `06:00→06:00`). This is not a zero-width window.
  var isAllDay: Bool { startMinute == endMinute }

  func contains(minuteOfDay: Int) -> Bool {
    let minute = min(max(0, minuteOfDay), 1439)
    if isAllDay { return true }
    if startMinute < endMinute { return minute >= startMinute && minute < endMinute }
    // Overnight wrap, e.g. 06:00→03:00: active across midnight; quiet is the complement.
    return minute >= startMinute || minute < endMinute
  }
}

enum ContextDeliveryGateReason: String, Equatable, Sendable {
  case allowed, masterDisabled, frequencyDisabled, snoozed, paywalled, quietHours, cooldown, dailyBudget, duplicate
}

struct ContextDeliveryAttempt: Equatable, Sendable {
  let id: String?
  let reason: ContextDeliveryGateReason
}

enum ContextDeliveryLifecycle {
  /// Nonterminal ledger states that may still advance. Terminal
  /// `failed`/`suppressed`/`delivered` rows are immutable.
  static let advanceableStates: Set<String> = ["attempted", "model_completed", "policy_approved"]

  static func canAdvance(from lifecycleState: String) -> Bool {
    advanceableStates.contains(lifecycleState)
  }

  static let advanceableStateSQLList = "'attempted', 'model_completed', 'policy_approved'"
}

enum ContextDeliveryReconciliation {
  static func reconcileAbandoned(in db: Database, cutoff: Date) throws -> Int {
    try db.execute(
      sql: """
        UPDATE proactive_deliveries
        SET decisionType = 'silence', lifecycleState = 'failed',
            provenanceJson = '{"failure":"abandoned"}', message = NULL
        WHERE lifecycleState IN ('attempted', 'model_completed', 'policy_approved')
          AND attemptedAt <= ?
        """,
      arguments: [cutoff])
    return db.changesCount
  }

  /// Fail-closed lifecycle update: never revive terminal failed/suppressed/delivered rows.
  @discardableResult
  static func complete(
    in db: Database,
    id: String,
    decisionType: String,
    provenanceJSON: String,
    message: String?,
    state: String,
    timestampColumn: String?,
    now: Date
  ) throws -> Bool {
    if let timestampColumn {
      try db.execute(
        sql: """
          UPDATE proactive_deliveries
          SET decisionType = ?, lifecycleState = ?, provenanceJson = ?, message = ?, \(timestampColumn) = ?
          WHERE id = ? AND lifecycleState IN (\(ContextDeliveryLifecycle.advanceableStateSQLList))
          """,
        arguments: [decisionType, state, provenanceJSON, message, now, id])
    } else {
      try db.execute(
        sql: """
          UPDATE proactive_deliveries
          SET decisionType = ?, lifecycleState = ?, provenanceJson = ?, message = ?
          WHERE id = ? AND lifecycleState IN (\(ContextDeliveryLifecycle.advanceableStateSQLList))
          """,
        arguments: [decisionType, state, provenanceJSON, message, id])
    }
    return db.changesCount > 0
  }
}

enum ContextDeliveryBudget {
  /// Align the device-side director budget with the backend proactive facade's
  /// 24-hour Redis window (`_QUOTA_WINDOW_SECONDS`), not local midnight.
  static let dailyWindowSeconds: TimeInterval = 24 * 60 * 60

  static func dailyLimit(frequencyLevel: Int, planMultiplier: Int = 1) -> Int {
    let base = [0, 10, 20, 40, 60, 100][max(0, min(5, frequencyLevel))]
    return base * max(1, planMultiplier)
  }

  static func cooldownSeconds(frequencyLevel: Int) -> TimeInterval {
    switch frequencyLevel {
    case 1: return 60 * 60
    case 2: return 30 * 60
    case 3: return 10 * 60
    case 4: return 3 * 60
    default: return 0
    }
  }

  static func freeGate(input: ContextDeliveryGateInput) -> ContextDeliveryGateReason {
    if !input.masterEnabled { return .masterDisabled }
    if input.frequencyLevel == 0 { return .frequencyDisabled }
    if input.snoozed { return .snoozed }
    if input.paywalled { return .paywalled }
    if !input.activePeriod.contains(minuteOfDay: input.minuteOfDay) { return .quietHours }
    return .allowed
  }

  /// Cooldown holds on the latest successful delivery *or* an in-flight attempt so
  /// concurrent visits cannot both reserve director quota in the same window.
  static func cooldownAnchor(
    lastDeliveredAt: Date?,
    latestInFlightAttemptedAt: Date?,
    lastGlobalPresentationAt: Date? = nil
  ) -> Date? {
    [lastDeliveredAt, latestInFlightAttemptedAt, lastGlobalPresentationAt]
      .compactMap { $0 }
      .max()
  }

  static func isCoolingDown(lastDeliveredAt: Date?, now: Date, cooldownSeconds: TimeInterval) -> Bool {
    isCoolingDown(
      lastDeliveredAt: lastDeliveredAt,
      latestInFlightAttemptedAt: nil,
      now: now,
      cooldownSeconds: cooldownSeconds)
  }

  static func isCoolingDown(
    lastDeliveredAt: Date?,
    latestInFlightAttemptedAt: Date?,
    now: Date,
    cooldownSeconds: TimeInterval
  ) -> Bool {
    guard cooldownSeconds > 0,
      let anchor = cooldownAnchor(
        lastDeliveredAt: lastDeliveredAt,
        latestInFlightAttemptedAt: latestInFlightAttemptedAt)
    else { return false }
    return now.timeIntervalSince(anchor) < cooldownSeconds
  }

  static func dailyWindowStart(now: Date, windowSeconds: TimeInterval = dailyWindowSeconds) -> Date {
    now.addingTimeInterval(-max(0, windowSeconds))
  }
}

extension ContextBucketStore {
  /// Fail closed for deliveries whose producer disappeared during an account
  /// switch, crash, or queued-notification reset. This is deliberately
  /// conservative: only rows older than the timeout and still in a
  /// nonterminal lifecycle are reconciled.
  @discardableResult
  func reconcileAbandonedDeliveries(
    now: Date = Date(), timeout: TimeInterval = 15 * 60
  ) async throws -> Int {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw ContextBucketStoreError.databaseUnavailable }
    let cutoff = now.addingTimeInterval(-max(0, timeout))
    return try await pool.write { db in
      try ContextDeliveryReconciliation.reconcileAbandoned(in: db, cutoff: cutoff)
    }
  }

  func beginDeliveryAttempt(
    fence: ContextVisitFence,
    snapshot: ContextBucketSnapshot,
    gate: ContextDeliveryGateInput,
    now: Date = Date()
  ) async throws -> ContextDeliveryAttempt {
    let freeReason = ContextDeliveryBudget.freeGate(input: gate)
    guard freeReason == .allowed else { return ContextDeliveryAttempt(id: nil, reason: freeReason) }
    let (pool, generation) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool, generation == fence.poolEpoch else { throw ContextBucketStoreError.staleFence }
    return try await pool.write { db in
      let duplicate =
        try Bool.fetchOne(
          db,
          sql: "SELECT EXISTS(SELECT 1 FROM proactive_deliveries WHERE visitID = ? AND bucketVersionID = ?)",
          arguments: [fence.visitID, snapshot.versionID]) ?? false
      guard !duplicate else { return ContextDeliveryAttempt(id: nil, reason: .duplicate) }
      let lastDeliveredAt = try Date.fetchOne(
        db, sql: "SELECT MAX(deliveredAt) FROM proactive_deliveries")
      let latestInFlightAttemptedAt = try Date.fetchOne(
        db,
        sql: """
          SELECT MAX(attemptedAt) FROM proactive_deliveries
          WHERE lifecycleState IN (\(ContextDeliveryLifecycle.advanceableStateSQLList))
          """)
      guard
        !ContextDeliveryBudget.isCoolingDown(
          lastDeliveredAt: ContextDeliveryBudget.cooldownAnchor(
            lastDeliveredAt: lastDeliveredAt,
            latestInFlightAttemptedAt: nil,
            lastGlobalPresentationAt: gate.lastGlobalPresentationAt),
          latestInFlightAttemptedAt: latestInFlightAttemptedAt,
          now: now,
          cooldownSeconds: gate.cooldownSeconds)
      else { return ContextDeliveryAttempt(id: nil, reason: .cooldown) }
      let windowStart = ContextDeliveryBudget.dailyWindowStart(now: now)
      let attemptedInWindow =
        try Int.fetchOne(
          db,
          sql: "SELECT COUNT(*) FROM proactive_deliveries WHERE attemptedAt >= ?",
          arguments: [windowStart]) ?? 0
      guard attemptedInWindow < gate.dailyLimit else {
        return ContextDeliveryAttempt(id: nil, reason: .dailyBudget)
      }
      let id = UUID().uuidString.lowercased()
      try db.execute(
        sql: """
          INSERT INTO proactive_deliveries
            (id, visitID, bucketID, bucketVersionID, decisionType, lifecycleState,
             provenanceJson, attemptedAt, expiresAt, createdAt)
          VALUES (?, ?, ?, ?, 'pending', 'attempted', '{}', ?, ?, ?)
          """,
        arguments: [
          id, fence.visitID, snapshot.bucketID, snapshot.versionID, now, now.addingTimeInterval(30 * 24 * 60 * 60), now,
        ])
      return ContextDeliveryAttempt(id: id, reason: .allowed)
    }
  }

  /// Advances a nonterminal delivery row. Returns `false` when the row is
  /// missing or already terminal so late callbacks cannot revive it.
  @discardableResult
  func completeDelivery(
    id: String,
    decisionType: String,
    provenanceJSON: String,
    message: String?,
    state: String,
    now: Date = Date()
  ) async throws -> Bool {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw ContextBucketStoreError.databaseUnavailable }
    let timestampColumn: String?
    switch state {
    case "model_completed": timestampColumn = "modelCompletedAt"
    case "policy_approved": timestampColumn = "policyApprovedAt"
    case "delivered": timestampColumn = "deliveredAt"
    default: timestampColumn = nil
    }
    return try await pool.write { db in
      try ContextDeliveryReconciliation.complete(
        in: db,
        id: id,
        decisionType: decisionType,
        provenanceJSON: provenanceJSON,
        message: message,
        state: state,
        timestampColumn: timestampColumn,
        now: now)
    }
  }

  func deliveryProvenance(id: String, now: Date = Date()) async -> String? {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return nil }
    return try? await pool.read { db in
      try String.fetchOne(
        db,
        sql: "SELECT provenanceJson FROM proactive_deliveries WHERE id = ? AND expiresAt > ?",
        arguments: [id, now])
    }
  }
}
