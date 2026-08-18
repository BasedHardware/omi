import Foundation
@preconcurrency import GRDB

struct ContextDeliveryGateInput: Equatable, Sendable {
  let masterEnabled: Bool
  let frequencyLevel: Int
  let paywalled: Bool
  let cooldownSeconds: TimeInterval
  let dailyLimit: Int
  let lastGlobalPresentationAt: Date?

  init(
    masterEnabled: Bool,
    frequencyLevel: Int,
    paywalled: Bool,
    cooldownSeconds: TimeInterval,
    dailyLimit: Int? = nil,
    lastGlobalPresentationAt: Date? = nil
  ) {
    self.masterEnabled = masterEnabled
    self.frequencyLevel = frequencyLevel
    self.paywalled = paywalled
    self.cooldownSeconds = cooldownSeconds
    self.dailyLimit = max(
      0,
      dailyLimit ?? ContextDeliveryBudget.dailyLimit(frequencyLevel: frequencyLevel))
    self.lastGlobalPresentationAt = lastGlobalPresentationAt
  }
}

enum ContextDeliveryGateReason: String, Equatable, Sendable {
  case allowed, masterDisabled, frequencyDisabled, snoozed, paywalled, cooldown, dailyBudget, duplicate
}

struct ContextDeliveryAttempt: Equatable, Sendable {
  let id: String?
  let reason: ContextDeliveryGateReason
}

/// A successfully presented director notification for one bucket, used only as
/// bounded prompt context. This is a signal to the model, not a delivery gate.
struct ContextBucketRecentDelivery: Equatable, Sendable, Decodable, FetchableRecord {
  /// The prompt tells the director not to re-send a point it already delivered.
  /// Showing it six of them made that instruction unenforceable in practice —
  /// measured at 7 repeats in 34 deliveries. The block is now rendered with
  /// absolute timestamps, so it is byte-stable for a given delivery set and
  /// carrying more of it is close to free.
  static let promptCap = 15
  static let summaryCharacterLimit = 320
  /// Delivery memory outlives notification expiry so the director cannot
  /// forget, and re-send, a point it already delivered earlier in the day.
  static let memoryLookback: TimeInterval = 6 * 60 * 60

  let decisionType: String
  let message: String?
  let deliveredAt: Date
}

enum ContextDeliveryLifecycle {
  /// Inserted when a delivery attempt begins, and kept when the lane fails
  /// before a model decision. Not a choice to stay silent.
  static let unresolvedDecisionType = "pending"

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

  /// How long after a visit ends its in-flight director evaluation may still
  /// run to completion and deliver. Requiring `outcome = 'active'` at every
  /// stage meant any context switch killed the evaluation mid-flight — quota
  /// spent, nothing delivered — so users who task-switch fast could never
  /// receive a delivery. Notifications are context-free banners, so a recent
  /// departure does not invalidate the outcome; each stage re-checks freshness,
  /// which bounds how stale a departed visit's delivery can be.
  static let deliveryValidityWindowSeconds: TimeInterval = 60

  /// A departed visit's evaluation must ground on a frame from that visit, not
  /// the next context's screen. Frames captured at most this long after the
  /// visit ended still count as the visit's own capture.
  static let departedFrameCaptureEpsilonSeconds: TimeInterval = 2

  static func dailyLimit(frequencyLevel: Int, planMultiplier: Int = 1) -> Int {
    let base = [0, 10, 20, 40, 60, 100][max(0, min(5, frequencyLevel))]
    return base * max(1, planMultiplier)
  }

  /// Ceiling on candidate-sourced deliveries per 24-hour window, inside the
  /// overall daily budget.
  ///
  /// The rewritten candidate gate swung from a 4% to a 71% pass rate (n=7 —
  /// far too small to size the true rate, which is exactly why a ceiling is
  /// warranted while dogfood measures it): a gate that now returns parseable
  /// JSON will act on its own `show=true` default. Cooldown and the daily
  /// budget bound the total interruption rate, but not the *mix* — without a
  /// ceiling, armed candidates could crowd the entire budget. The check runs
  /// before the gate's model call, so a capped candidate costs no tokens and
  /// stays armed for a quieter window rather than being retired.
  static let candidateDailyShowCeiling = 8

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
    if input.paywalled { return .paywalled }
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
      // The daily budget caps user-visible interruptions. Evaluations that resolved
      // to silence or failed never reached the user, so they must not spend it — a
      // day of heavy screen activity would otherwise exhaust the budget on invisible
      // decisions and read as a dead feature. In-flight attempts still count until
      // they resolve, so a burst cannot over-reserve past the cap.
      let attemptedInWindow =
        try Int.fetchOne(
          db,
          sql: """
            SELECT COUNT(*) FROM proactive_deliveries
            WHERE attemptedAt >= ? AND lifecycleState NOT IN ('suppressed', 'failed')
            """,
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
            VALUES (?, ?, ?, ?, ?, 'attempted', '{}', ?, ?, ?)
          """,
        arguments: [
          id, fence.visitID, snapshot.bucketID, snapshot.versionID,
          ContextDeliveryLifecycle.unresolvedDecisionType, now,
          now.addingTimeInterval(30 * 24 * 60 * 60), now,
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

  /// Newest successfully presented notifications for this bucket within the
  /// delivery-memory lookback. Bounded so the director prompt cannot grow
  /// without limit. Failed/suppressed rows are excluded: the model should see
  /// what the user actually received. Lookback is on `deliveredAt`, not
  /// notification expiry, so a delivered point cannot be forgotten and re-sent
  /// once its banner expires.
  func recentDeliveredForBucket(
    bucketID: String,
    now: Date = Date(),
    limit: Int = ContextBucketRecentDelivery.promptCap
  ) async -> [ContextBucketRecentDelivery] {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return [] }
    let cap = max(0, min(limit, ContextBucketRecentDelivery.promptCap))
    guard cap > 0 else { return [] }
    return
      (try? await pool.read { db in
        try ContextBucketRecentDelivery.fetchAll(
          db,
          sql: """
            SELECT decisionType, message, deliveredAt FROM proactive_deliveries
            WHERE bucketID = ?
              AND lifecycleState = 'delivered'
              AND deliveredAt IS NOT NULL
              AND deliveredAt >= ?
            ORDER BY deliveredAt DESC
            LIMIT ?
            """,
          arguments: [
            bucketID, now.addingTimeInterval(-ContextBucketRecentDelivery.memoryLookback), cap,
          ])
      }) ?? []
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
