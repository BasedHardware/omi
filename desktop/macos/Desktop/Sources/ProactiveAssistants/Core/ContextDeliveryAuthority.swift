import Foundation
@preconcurrency import GRDB

struct ContextDeliveryGateInput: Equatable, Sendable {
  let masterEnabled: Bool
  let frequencyLevel: Int
  let snoozed: Bool
  let paywalled: Bool
  let minuteOfDay: Int
  let cooldownSeconds: TimeInterval
}

enum ContextDeliveryGateReason: String, Equatable, Sendable {
  case allowed, masterDisabled, frequencyDisabled, snoozed, paywalled, quietHours, cooldown, dailyBudget, duplicate
}

struct ContextDeliveryAttempt: Equatable, Sendable {
  let id: String?
  let reason: ContextDeliveryGateReason
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
}

enum ContextDeliveryBudget {
  static func dailyLimit(frequencyLevel: Int) -> Int {
    [0, 2, 4, 8, 12, 20][max(0, min(5, frequencyLevel))]
  }

  static func freeGate(input: ContextDeliveryGateInput) -> ContextDeliveryGateReason {
    if !input.masterEnabled { return .masterDisabled }
    if input.frequencyLevel == 0 { return .frequencyDisabled }
    if input.snoozed { return .snoozed }
    if input.paywalled { return .paywalled }
    if input.minuteOfDay >= 22 * 60 || input.minuteOfDay < 8 * 60 { return .quietHours }
    return .allowed
  }

  static func isCoolingDown(lastDeliveredAt: Date?, now: Date, cooldownSeconds: TimeInterval) -> Bool {
    guard cooldownSeconds > 0, let lastDeliveredAt else { return false }
    return now.timeIntervalSince(lastDeliveredAt) < cooldownSeconds
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
      let startOfDay = Calendar.current.startOfDay(for: now)
      let lastDeliveredAt = try Date.fetchOne(
        db, sql: "SELECT MAX(deliveredAt) FROM proactive_deliveries")
      guard
        !ContextDeliveryBudget.isCoolingDown(
          lastDeliveredAt: lastDeliveredAt, now: now, cooldownSeconds: gate.cooldownSeconds)
      else { return ContextDeliveryAttempt(id: nil, reason: .cooldown) }
      let attemptedToday =
        try Int.fetchOne(
          db,
          sql: "SELECT COUNT(*) FROM proactive_deliveries WHERE attemptedAt >= ?",
          arguments: [startOfDay]) ?? 0
      guard attemptedToday < ContextDeliveryBudget.dailyLimit(frequencyLevel: gate.frequencyLevel) else {
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

  func completeDelivery(
    id: String,
    decisionType: String,
    provenanceJSON: String,
    message: String?,
    state: String,
    now: Date = Date()
  ) async throws {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw ContextBucketStoreError.databaseUnavailable }
    let timestampColumn: String?
    switch state {
    case "model_completed": timestampColumn = "modelCompletedAt"
    case "policy_approved": timestampColumn = "policyApprovedAt"
    case "delivered": timestampColumn = "deliveredAt"
    default: timestampColumn = nil
    }
    try await pool.write { db in
      if let timestampColumn {
        try db.execute(
          sql:
            "UPDATE proactive_deliveries SET decisionType = ?, lifecycleState = ?, provenanceJson = ?, message = ?, \(timestampColumn) = ? WHERE id = ?",
          arguments: [decisionType, state, provenanceJSON, message, now, id])
      } else {
        try db.execute(
          sql:
            "UPDATE proactive_deliveries SET decisionType = ?, lifecycleState = ?, provenanceJson = ?, message = ? WHERE id = ?",
          arguments: [decisionType, state, provenanceJSON, message, id])
      }
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
