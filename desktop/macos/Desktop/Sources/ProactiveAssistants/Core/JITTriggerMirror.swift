import Foundation
@preconcurrency import GRDB

struct JITTriggerSnapshotAction: Codable, Equatable, Sendable {
  let type: String
  let prompt: String
}

struct JITTriggerSnapshotRow: Codable, Equatable, Sendable {
  let memoryID: String
  let itemRevision: Int
  let updatedAt: Date
  let triggerConditionJSON: String
  let action: JITTriggerSnapshotAction
  let wakeupBudgetPerDay: Int?

  enum CodingKeys: String, CodingKey {
    case memoryID = "memory_id"
    case itemRevision = "item_revision"
    case updatedAt = "updated_at"
    case triggerConditionJSON = "trigger_condition_json"
    case action
    case wakeupBudgetPerDay = "wakeup_budget_per_day"
  }
}

struct JITTriggerSnapshot: Codable, Equatable, Sendable {
  let ownerID: String
  let accountGeneration: Int
  let headCommitID: String
  let commitSequence: Int
  let snapshotRevision: String
  let complete: Bool
  let rows: [JITTriggerSnapshotRow]
  let failureReason: String?

  enum CodingKeys: String, CodingKey {
    case ownerID = "owner_id"
    case accountGeneration = "account_generation"
    case headCommitID = "head_commit_id"
    case commitSequence = "commit_sequence"
    case snapshotRevision = "snapshot_revision"
    case complete, rows
    case failureReason = "failure_reason"
  }
}

enum JITTriggerMirrorError: Error, Equatable {
  case incomplete
  case invalidIdentity
  case staleGeneration
  case staleRevision
  case conflictingRevision
  case malformedRow
  case databaseUnavailable
}

struct JITTriggerMirrorReceipt: Equatable, Sendable {
  let ownerID: String
  let accountGeneration: Int
  let commitSequence: Int
  let snapshotRevision: String
  let rowCount: Int
}

struct JITTriggerWakeupClaim: Equatable, Sendable {
  let continuityKey: String
  let triggerID: String
  let leaseToken: String
}

enum JITTriggerMirrorSchema {
  static func migrating(_ migrator: DatabaseMigrator, queue: DatabaseWriter) throws {
    var migrator = migrator
    registerMigration(on: &migrator)
    try migrator.migrate(queue)
  }

  static func registerMigration(on migrator: inout DatabaseMigrator) {
    migrator.registerMigration("createJITTriggerMirror") { db in
      try db.create(table: "jit_trigger_mirror") { table in
        table.column("memoryID", .text).primaryKey()
        table.column("accountGeneration", .integer).notNull()
        table.column("itemRevision", .integer).notNull()
        table.column("updatedAt", .datetime).notNull()
        table.column("conditionJSON", .text).notNull()
        table.column("actionType", .text).notNull()
        table.column("actionPrompt", .text).notNull()
        table.column("wakeupBudgetPerDay", .integer)
      }
      try db.create(table: "jit_trigger_snapshot_receipts") { table in
        table.column("ownerID", .text).primaryKey()
        table.column("accountGeneration", .integer).notNull()
        table.column("headCommitID", .text).notNull()
        table.column("commitSequence", .integer).notNull()
        table.column("snapshotRevision", .text).notNull()
        table.column("rowCount", .integer).notNull()
        table.column("updatedAt", .datetime).notNull()
      }
      try db.create(table: "jit_trigger_wakeup_receipts") { table in
        table.column("continuityKey", .text).primaryKey()
        table.column("triggerID", .text).notNull()
        table.column("lane", .text).notNull()
        table.column("budgetDay", .text).notNull()
        table.column("snapshotRevision", .text).notNull()
        table.column("observationFingerprint", .text).notNull()
        table.column("state", .text).notNull()
        table.column("leaseToken", .text)
        table.column("leaseExpiresAt", .datetime)
        table.column("updatedAt", .datetime).notNull()
      }
      try db.create(
        index: "idx_jit_trigger_wakeup_budget",
        on: "jit_trigger_wakeup_receipts",
        columns: ["triggerID", "budgetDay", "state"])
    }
    migrator.registerMigration("createJITAmbientContextState") { db in
      try db.create(table: "jit_ambient_context_state", ifNotExists: true) { table in
        table.column("contextID", .text).primaryKey()
        table.column("semanticFingerprint", .text).notNull()
        table.column("updatedAt", .datetime).notNull()
      }
    }
  }
}

actor JITTriggerMirror {
  static let shared = JITTriggerMirror()

  func reconcile(
    _ snapshot: JITTriggerSnapshot,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> JITTriggerMirrorReceipt {
    guard snapshot.complete else { throw JITTriggerMirrorError.incomplete }
    guard snapshot.ownerID == authorizationSnapshot.ownerID,
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      snapshot.accountGeneration >= 0,
      snapshot.commitSequence >= 0,
      !snapshot.snapshotRevision.isEmpty
    else { throw JITTriggerMirrorError.invalidIdentity }
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw JITTriggerMirrorError.databaseUnavailable }
    let receipt = try await pool.write { db in
      try Self.reconcile(snapshot, in: db, now: Date())
    }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw JITTriggerMirrorError.invalidIdentity
    }
    return receipt
  }

  static func reconcile(_ snapshot: JITTriggerSnapshot, in db: Database, now: Date) throws
    -> JITTriggerMirrorReceipt
  {
    guard snapshot.complete, !snapshot.ownerID.isEmpty, !snapshot.snapshotRevision.isEmpty else {
      throw JITTriggerMirrorError.incomplete
    }
    if let prior = try Row.fetchOne(
      db,
      sql:
        "SELECT accountGeneration, commitSequence, snapshotRevision FROM jit_trigger_snapshot_receipts WHERE ownerID = ?",
      arguments: [snapshot.ownerID])
    {
      let generation: Int = prior["accountGeneration"]
      let sequence: Int = prior["commitSequence"]
      let revision: String = prior["snapshotRevision"]
      if snapshot.accountGeneration < generation { throw JITTriggerMirrorError.staleGeneration }
      if snapshot.accountGeneration == generation, snapshot.commitSequence < sequence {
        throw JITTriggerMirrorError.staleRevision
      }
      if snapshot.accountGeneration == generation, snapshot.commitSequence == sequence,
        snapshot.snapshotRevision != revision
      {
        throw JITTriggerMirrorError.conflictingRevision
      }
      if snapshot.accountGeneration > generation {
        // An account reset is a new authority epoch. Old wakeup receipts must
        // neither disclose prior continuity nor consume the new epoch's budget.
        try db.execute(sql: "DELETE FROM jit_trigger_wakeup_receipts")
        try db.execute(sql: "DELETE FROM jit_ambient_context_state")
      }
    }

    var seen = Set<String>()
    for row in snapshot.rows {
      guard seen.insert(row.memoryID).inserted,
        !row.memoryID.isEmpty,
        row.itemRevision > 0,
        row.action.type == "agent_prompt",
        !row.action.prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
        row.action.prompt.count <= KnowledgeLedgerTriggerAction.maximumPromptCharacters,
        let conditionData = row.triggerConditionJSON.data(using: .utf8),
        case .success(let compiled) = KnowledgeLedgerTriggerCompiler.compileAuthoritativeSnapshotRow(
          id: row.memoryID,
          triggerConditionJSON: conditionData,
          wakeupBudgetPerDay: row.wakeupBudgetPerDay),
        compiled.action
          == KnowledgeLedgerTriggerAction(
            type: row.action.type, prompt: row.action.prompt)
      else { throw JITTriggerMirrorError.malformedRow }
      try db.execute(
        sql: """
          INSERT INTO jit_trigger_mirror
            (memoryID, accountGeneration, itemRevision, updatedAt, conditionJSON, actionType, actionPrompt, wakeupBudgetPerDay)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(memoryID) DO UPDATE SET
            accountGeneration = excluded.accountGeneration,
            itemRevision = excluded.itemRevision,
            updatedAt = excluded.updatedAt,
            conditionJSON = excluded.conditionJSON,
            actionType = excluded.actionType,
            actionPrompt = excluded.actionPrompt,
            wakeupBudgetPerDay = excluded.wakeupBudgetPerDay
          """,
        arguments: [
          row.memoryID, snapshot.accountGeneration, row.itemRevision, row.updatedAt,
          row.triggerConditionJSON, row.action.type, row.action.prompt, row.wakeupBudgetPerDay,
        ])
    }
    if seen.isEmpty {
      try db.execute(sql: "DELETE FROM jit_trigger_mirror")
    } else {
      let placeholders = seen.map { _ in "?" }.joined(separator: ",")
      try db.execute(
        sql: "DELETE FROM jit_trigger_mirror WHERE memoryID NOT IN (\(placeholders))",
        arguments: StatementArguments(seen.sorted()))
    }
    try db.execute(
      sql: """
        INSERT INTO jit_trigger_snapshot_receipts
          (ownerID, accountGeneration, headCommitID, commitSequence, snapshotRevision, rowCount, updatedAt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ownerID) DO UPDATE SET
          accountGeneration = excluded.accountGeneration,
          headCommitID = excluded.headCommitID,
          commitSequence = excluded.commitSequence,
          snapshotRevision = excluded.snapshotRevision,
          rowCount = excluded.rowCount,
          updatedAt = excluded.updatedAt
        """,
      arguments: [
        snapshot.ownerID, snapshot.accountGeneration, snapshot.headCommitID,
        snapshot.commitSequence, snapshot.snapshotRevision, snapshot.rows.count, now,
      ])
    return JITTriggerMirrorReceipt(
      ownerID: snapshot.ownerID,
      accountGeneration: snapshot.accountGeneration,
      commitSequence: snapshot.commitSequence,
      snapshotRevision: snapshot.snapshotRevision,
      rowCount: snapshot.rows.count)
  }

  func compiledSnapshot(
    receipt: JITTriggerMirrorReceipt,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> [KnowledgeLedgerCompiledTrigger] {
    guard receipt.ownerID == authorizationSnapshot.ownerID,
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    else { throw JITTriggerMirrorError.invalidIdentity }
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw JITTriggerMirrorError.databaseUnavailable }
    return try await pool.read { db in
      let current: String? = try String.fetchOne(
        db,
        sql:
          "SELECT snapshotRevision FROM jit_trigger_snapshot_receipts WHERE ownerID = ? AND accountGeneration = ? AND commitSequence = ?",
        arguments: [receipt.ownerID, receipt.accountGeneration, receipt.commitSequence])
      guard current == receipt.snapshotRevision else { throw JITTriggerMirrorError.staleRevision }
      return try Row.fetchAll(
        db,
        sql: "SELECT memoryID, conditionJSON, wakeupBudgetPerDay FROM jit_trigger_mirror ORDER BY memoryID"
      )
      .map { row in
        let id: String = row["memoryID"]
        let json: String = row["conditionJSON"]
        let budget: Int? = row["wakeupBudgetPerDay"]
        guard let data = json.data(using: .utf8),
          case .success(let trigger) = KnowledgeLedgerTriggerCompiler.compileAuthoritativeSnapshotRow(
            id: id, triggerConditionJSON: data, wakeupBudgetPerDay: budget)
        else { throw JITTriggerMirrorError.malformedRow }
        return trigger
      }
    }
  }

  func claimWakeup(
    continuityKey: String,
    triggerID: String,
    lane: JITProactivityLane,
    budgetDay: String,
    snapshotRevision: String,
    observationFingerprint: String,
    budget: Int?,
    now: Date,
    leaseSeconds: TimeInterval = 180
  ) async throws -> JITTriggerWakeupClaim? {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw JITTriggerMirrorError.databaseUnavailable }
    return try await pool.write { db in
      try Self.claimWakeup(
        continuityKey: continuityKey, triggerID: triggerID, lane: lane, budgetDay: budgetDay,
        snapshotRevision: snapshotRevision, observationFingerprint: observationFingerprint,
        budget: budget, now: now, leaseSeconds: leaseSeconds, in: db)
    }
  }

  func claimAmbientNanoChange(
    contextID: String,
    semanticFingerprint: String,
    budgetDay: String,
    snapshotRevision: String,
    budget: Int,
    now: Date
  ) async throws -> JITTriggerWakeupClaim? {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw JITTriggerMirrorError.databaseUnavailable }
    return try await pool.write { db in
      try Self.claimAmbientNanoChange(
        contextID: contextID,
        semanticFingerprint: semanticFingerprint,
        budgetDay: budgetDay,
        snapshotRevision: snapshotRevision,
        budget: budget,
        now: now,
        in: db)
    }
  }

  static func claimAmbientNanoChange(
    contextID: String,
    semanticFingerprint: String,
    budgetDay: String,
    snapshotRevision: String,
    budget: Int,
    now: Date,
    in db: Database
  ) throws -> JITTriggerWakeupClaim? {
    guard !contextID.isEmpty, !semanticFingerprint.isEmpty else { return nil }
    let prior: String? = try String.fetchOne(
      db,
      sql: "SELECT semanticFingerprint FROM jit_ambient_context_state WHERE contextID = ?",
      arguments: [contextID])
    guard prior != semanticFingerprint else { return nil }
    guard
      let claim = try claimWakeup(
        continuityKey: "jit-nano:\(contextID):\(semanticFingerprint)",
        triggerID: "ambient-nano",
        lane: .ambient,
        budgetDay: budgetDay,
        snapshotRevision: snapshotRevision,
        observationFingerprint: semanticFingerprint,
        budget: budget,
        now: now,
        in: db)
    else { return nil }
    try db.execute(
      sql: """
        INSERT INTO jit_ambient_context_state (contextID, semanticFingerprint, updatedAt)
        VALUES (?, ?, ?)
        ON CONFLICT(contextID) DO UPDATE SET
          semanticFingerprint = excluded.semanticFingerprint,
          updatedAt = excluded.updatedAt
        """,
      arguments: [contextID, semanticFingerprint, now])
    return claim
  }

  static func claimWakeup(
    continuityKey: String,
    triggerID: String,
    lane: JITProactivityLane,
    budgetDay: String,
    snapshotRevision: String,
    observationFingerprint: String,
    budget: Int?,
    now: Date,
    leaseSeconds: TimeInterval = 180,
    in db: Database
  ) throws -> JITTriggerWakeupClaim? {
    if let existing = try Row.fetchOne(
      db,
      sql: "SELECT state, leaseExpiresAt FROM jit_trigger_wakeup_receipts WHERE continuityKey = ?",
      arguments: [continuityKey])
    {
      let state: String = existing["state"]
      let leaseExpiresAt: Date? = existing["leaseExpiresAt"]
      if state == "delivered" || (state == "claimed" && (leaseExpiresAt ?? .distantPast) > now) {
        return nil
      }
    }
    let used: Int =
      try Int.fetchOne(
        db,
        sql: """
          SELECT COUNT(*) FROM jit_trigger_wakeup_receipts
          WHERE triggerID = ? AND budgetDay = ?
            AND (state = 'delivered' OR (state = 'claimed' AND leaseExpiresAt > ?))
          """,
        arguments: [triggerID, budgetDay, now]) ?? 0
    if let budget, used >= budget { return nil }
    let token = UUID().uuidString
    try db.execute(
      sql: """
        INSERT INTO jit_trigger_wakeup_receipts
          (continuityKey, triggerID, lane, budgetDay, snapshotRevision, observationFingerprint, state, leaseToken, leaseExpiresAt, updatedAt)
        VALUES (?, ?, ?, ?, ?, ?, 'claimed', ?, ?, ?)
        ON CONFLICT(continuityKey) DO UPDATE SET
          triggerID = excluded.triggerID, lane = excluded.lane, budgetDay = excluded.budgetDay,
          snapshotRevision = excluded.snapshotRevision,
          observationFingerprint = excluded.observationFingerprint,
          state = 'claimed', leaseToken = excluded.leaseToken,
          leaseExpiresAt = excluded.leaseExpiresAt, updatedAt = excluded.updatedAt
        """,
      arguments: [
        continuityKey, triggerID, lane.rawValue, budgetDay, snapshotRevision,
        observationFingerprint, token, now.addingTimeInterval(max(30, leaseSeconds)), now,
      ])
    return JITTriggerWakeupClaim(continuityKey: continuityKey, triggerID: triggerID, leaseToken: token)
  }

  func finishWakeup(_ claim: JITTriggerWakeupClaim, delivered: Bool, now: Date = Date()) async {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return }
    try? await pool.write { db in
      try db.execute(
        sql: """
          UPDATE jit_trigger_wakeup_receipts
          SET state = ?, leaseToken = NULL, leaseExpiresAt = NULL, updatedAt = ?
          WHERE continuityKey = ? AND leaseToken = ? AND state = 'claimed'
          """,
        arguments: [delivered ? "delivered" : "failed", now, claim.continuityKey, claim.leaseToken])
    }
  }
}

extension KnowledgeLedgerTriggerCompiler {
  static func compileAuthoritativeSnapshotRow(
    id: String,
    triggerConditionJSON: Data,
    wakeupBudgetPerDay: Int?
  ) -> Result<KnowledgeLedgerCompiledTrigger, KnowledgeLedgerTriggerCompileFailure> {
    compile(
      KnowledgeLedgerTriggerRow(
        id: id,
        triggerConditionJSON: triggerConditionJSON,
        wakeupBudgetPerDay: wakeupBudgetPerDay))
  }
}
