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
  let wakeupBudgetPerDay: Int
  /// The server-owned wall-clock instant before which this standing trigger is
  /// ineligible. Date is an absolute instant, so offsets in the wire ISO-8601
  /// value cannot change the fence when it is evaluated locally.
  let snoozedUntil: Date?

  init(
    memoryID: String,
    itemRevision: Int,
    updatedAt: Date,
    triggerConditionJSON: String,
    action: JITTriggerSnapshotAction,
    wakeupBudgetPerDay: Int,
    snoozedUntil: Date? = nil
  ) {
    self.memoryID = memoryID
    self.itemRevision = itemRevision
    self.updatedAt = updatedAt
    self.triggerConditionJSON = triggerConditionJSON
    self.action = action
    self.wakeupBudgetPerDay = wakeupBudgetPerDay
    self.snoozedUntil = snoozedUntil
  }

  enum CodingKeys: String, CodingKey, CaseIterable {
    case memoryID = "memory_id"
    case itemRevision = "item_revision"
    case updatedAt = "updated_at"
    case triggerConditionJSON = "trigger_condition_json"
    case action
    case wakeupBudgetPerDay = "wakeup_budget_per_day"
    case snoozedUntil = "snoozed_until"
  }
}

struct JITTriggerEmbeddingPolicy: Codable, Equatable, Sendable {
  let enabled: Bool
  let matchSimilarity: Double
  let triageSimilarity: Double
  let modelID: String?
  let modelVersion: String?
  let language: String?

  enum CodingKeys: String, CodingKey, CaseIterable {
    case enabled
    case matchSimilarity = "match_similarity"
    case triageSimilarity = "triage_similarity"
    case modelID = "model_id"
    case modelVersion = "model_version"
    case language
  }

  init(
    enabled: Bool, matchSimilarity: Double, triageSimilarity: Double,
    modelID: String?, modelVersion: String?, language: String?
  ) {
    self.enabled = enabled
    self.matchSimilarity = matchSimilarity
    self.triageSimilarity = triageSimilarity
    self.modelID = modelID
    self.modelVersion = modelVersion
    self.language = language
  }

  init(from decoder: Decoder) throws {
    let raw = try decoder.container(keyedBy: JITPolicyDynamicKey.self)
    let allowed = Set(CodingKeys.allCases.map(\.stringValue))
    guard raw.allKeys.allSatisfy({ allowed.contains($0.stringValue) }) else {
      throw DecodingError.dataCorrupted(
        .init(codingPath: decoder.codingPath, debugDescription: "unknown embedding policy key"))
    }
    let container = try decoder.container(keyedBy: CodingKeys.self)
    self.init(
      enabled: try container.decode(Bool.self, forKey: .enabled),
      matchSimilarity: try container.decode(Double.self, forKey: .matchSimilarity),
      triageSimilarity: try container.decode(Double.self, forKey: .triageSimilarity),
      modelID: try container.decodeIfPresent(String.self, forKey: .modelID),
      modelVersion: try container.decodeIfPresent(String.self, forKey: .modelVersion),
      language: try container.decodeIfPresent(String.self, forKey: .language))
  }

  var isValid: Bool {
    guard matchSimilarity == 0.82, triageSimilarity == 0.74 else { return false }
    let identifiers = [modelID, modelVersion, language]
    if enabled {
      return identifiers.allSatisfy {
        guard let value = $0?.trimmingCharacters(in: .whitespacesAndNewlines) else { return false }
        return !value.isEmpty && value.count <= 80
      }
    }
    return identifiers.allSatisfy { $0 == nil }
  }

  static let disabled = JITTriggerEmbeddingPolicy(
    enabled: false, matchSimilarity: 0.82, triageSimilarity: 0.74,
    modelID: nil, modelVersion: nil, language: nil)
}

struct JITTriggerRuntimePolicy: Codable, Equatable, Sendable {
  let schemaVersion: String
  let plannedNotificationsPerTriggerPerDay: Int
  let totalProactiveNotificationsPerDay: Int
  let ambiguousNanoTriagesPerDay: Int
  let fullAgentTurnsPerCandidate: Int
  let maxCalendarEvents: Int
  let validForSeconds: Int
  let paidBoundaryRefreshRequired: Bool
  let embedding: JITTriggerEmbeddingPolicy

  enum CodingKeys: String, CodingKey, CaseIterable {
    case schemaVersion = "schema_version"
    case plannedNotificationsPerTriggerPerDay = "planned_notifications_per_trigger_per_day"
    case totalProactiveNotificationsPerDay = "total_proactive_notifications_per_day"
    case ambiguousNanoTriagesPerDay = "ambiguous_nano_triages_per_day"
    case fullAgentTurnsPerCandidate = "full_agent_turns_per_candidate"
    case maxCalendarEvents = "max_calendar_events"
    case validForSeconds = "valid_for_seconds"
    case paidBoundaryRefreshRequired = "paid_boundary_refresh_required"
    case embedding
  }

  init(
    schemaVersion: String, plannedNotificationsPerTriggerPerDay: Int,
    totalProactiveNotificationsPerDay: Int, ambiguousNanoTriagesPerDay: Int,
    fullAgentTurnsPerCandidate: Int, maxCalendarEvents: Int, validForSeconds: Int,
    paidBoundaryRefreshRequired: Bool, embedding: JITTriggerEmbeddingPolicy
  ) {
    self.schemaVersion = schemaVersion
    self.plannedNotificationsPerTriggerPerDay = plannedNotificationsPerTriggerPerDay
    self.totalProactiveNotificationsPerDay = totalProactiveNotificationsPerDay
    self.ambiguousNanoTriagesPerDay = ambiguousNanoTriagesPerDay
    self.fullAgentTurnsPerCandidate = fullAgentTurnsPerCandidate
    self.maxCalendarEvents = maxCalendarEvents
    self.validForSeconds = validForSeconds
    self.paidBoundaryRefreshRequired = paidBoundaryRefreshRequired
    self.embedding = embedding
  }

  init(from decoder: Decoder) throws {
    let raw = try decoder.container(keyedBy: JITPolicyDynamicKey.self)
    let allowed = Set(CodingKeys.allCases.map(\.stringValue))
    guard raw.allKeys.allSatisfy({ allowed.contains($0.stringValue) }) else {
      throw DecodingError.dataCorrupted(
        .init(codingPath: decoder.codingPath, debugDescription: "unknown runtime policy key"))
    }
    let container = try decoder.container(keyedBy: CodingKeys.self)
    self.init(
      schemaVersion: try container.decode(String.self, forKey: .schemaVersion),
      plannedNotificationsPerTriggerPerDay: try container.decode(
        Int.self, forKey: .plannedNotificationsPerTriggerPerDay),
      totalProactiveNotificationsPerDay: try container.decode(
        Int.self, forKey: .totalProactiveNotificationsPerDay),
      ambiguousNanoTriagesPerDay: try container.decode(Int.self, forKey: .ambiguousNanoTriagesPerDay),
      fullAgentTurnsPerCandidate: try container.decode(Int.self, forKey: .fullAgentTurnsPerCandidate),
      maxCalendarEvents: try container.decode(Int.self, forKey: .maxCalendarEvents),
      validForSeconds: try container.decode(Int.self, forKey: .validForSeconds),
      paidBoundaryRefreshRequired: try container.decode(Bool.self, forKey: .paidBoundaryRefreshRequired),
      embedding: try container.decode(JITTriggerEmbeddingPolicy.self, forKey: .embedding))
  }

  var isValid: Bool {
    schemaVersion == "jit_trigger_policy.v1"
      && plannedNotificationsPerTriggerPerDay == 1
      && totalProactiveNotificationsPerDay == 3
      && ambiguousNanoTriagesPerDay == 8
      && fullAgentTurnsPerCandidate == 1
      && maxCalendarEvents == KnowledgeLedgerTriggerObservation.maxCalendarEvents
      && validForSeconds == 30
      && paidBoundaryRefreshRequired
      && embedding.isValid
  }

  static let ratifiedV1 = JITTriggerRuntimePolicy(
    schemaVersion: "jit_trigger_policy.v1",
    plannedNotificationsPerTriggerPerDay: 1,
    totalProactiveNotificationsPerDay: 3,
    ambiguousNanoTriagesPerDay: 8,
    fullAgentTurnsPerCandidate: 1,
    maxCalendarEvents: 32,
    validForSeconds: 30,
    paidBoundaryRefreshRequired: true,
    embedding: .disabled)
}

private struct JITPolicyDynamicKey: CodingKey {
  let stringValue: String
  let intValue: Int?
  init?(stringValue: String) {
    self.stringValue = stringValue
    intValue = nil
  }
  init?(intValue: Int) {
    stringValue = String(intValue)
    self.intValue = intValue
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
  let policy: JITTriggerRuntimePolicy
  let failureReason: String?
  /// The profile timezone and current budget day used by the server's
  /// reservation transaction. Optional for compatibility with older servers.
  let budgetDay: String?
  let budgetTimezone: String?

  enum CodingKeys: String, CodingKey {
    case ownerID = "owner_id"
    case accountGeneration = "account_generation"
    case headCommitID = "head_commit_id"
    case commitSequence = "commit_sequence"
    case snapshotRevision = "snapshot_revision"
    case complete, rows, policy
    case failureReason = "failure_reason"
    case budgetDay = "budget_day"
    case budgetTimezone = "budget_timezone"
  }

  init(
    ownerID: String, accountGeneration: Int, headCommitID: String, commitSequence: Int,
    snapshotRevision: String, complete: Bool, rows: [JITTriggerSnapshotRow],
    policy: JITTriggerRuntimePolicy = .ratifiedV1, failureReason: String?,
    budgetDay: String? = nil, budgetTimezone: String? = nil
  ) {
    self.ownerID = ownerID
    self.accountGeneration = accountGeneration
    self.headCommitID = headCommitID
    self.commitSequence = commitSequence
    self.snapshotRevision = snapshotRevision
    self.complete = complete
    self.rows = rows
    self.policy = policy
    self.failureReason = failureReason
    self.budgetDay = budgetDay
    self.budgetTimezone = budgetTimezone
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
  let policy: JITTriggerRuntimePolicy

  init(
    ownerID: String, accountGeneration: Int, commitSequence: Int, snapshotRevision: String,
    rowCount: Int, policy: JITTriggerRuntimePolicy = .ratifiedV1
  ) {
    self.ownerID = ownerID
    self.accountGeneration = accountGeneration
    self.commitSequence = commitSequence
    self.snapshotRevision = snapshotRevision
    self.rowCount = rowCount
    self.policy = policy
  }
}

struct JITTriggerWakeupClaim: Equatable, Sendable {
  let continuityKey: String
  let triggerID: String
  let leaseToken: String
}

struct JITPlannedWakeupRequest: Equatable, Sendable {
  let continuityKey: String
  let triggerID: String
  let lane: JITProactivityLane
  let budgetDay: String
  let snapshotRevision: String
  let observationFingerprint: String
  let budget: Int?
  let now: Date
  let authority: JITTriggerMirrorReceipt
  let triggerRow: JITTriggerSnapshotRow
}

enum JITTriggerMirrorSchema {
  static func migrating(_ migrator: DatabaseMigrator, queue: DatabaseWriter) throws {
    var migrator = migrator
    registerMigration(on: &migrator)
    try migrator.migrate(queue)
  }

  static func registerMigration(on migrator: inout DatabaseMigrator) {
    // Every create here is `ifNotExists` on purpose: a dogfood machine can already carry these
    // tables from an earlier build of this branch, where the same schema shipped under a
    // different migration identifier. Without the guard the ladder dies on "table already
    // exists" and no later migration ever runs.
    migrator.registerMigration("createJITTriggerMirror") { db in
      try db.create(table: "jit_trigger_mirror", ifNotExists: true) { table in
        table.column("memoryID", .text).primaryKey()
        table.column("accountGeneration", .integer).notNull()
        table.column("itemRevision", .integer).notNull()
        table.column("updatedAt", .datetime).notNull()
        table.column("conditionJSON", .text).notNull()
        table.column("actionType", .text).notNull()
        table.column("actionPrompt", .text).notNull()
        table.column("wakeupBudgetPerDay", .integer)
      }
      try db.create(table: "jit_trigger_snapshot_receipts", ifNotExists: true) { table in
        table.column("ownerID", .text).primaryKey()
        table.column("accountGeneration", .integer).notNull()
        table.column("headCommitID", .text).notNull()
        table.column("commitSequence", .integer).notNull()
        table.column("snapshotRevision", .text).notNull()
        table.column("rowCount", .integer).notNull()
        table.column("updatedAt", .datetime).notNull()
      }
      try db.create(table: "jit_trigger_wakeup_receipts", ifNotExists: true) { table in
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
        columns: ["triggerID", "budgetDay", "state"],
        options: [.ifNotExists])
    }
    migrator.registerMigration("createJITAmbientContextState") { db in
      try db.create(table: "jit_ambient_context_state", ifNotExists: true) { table in
        table.column("contextID", .text).primaryKey()
        table.column("semanticFingerprint", .text).notNull()
        table.column("updatedAt", .datetime).notNull()
      }
    }
    migrator.registerMigration("addJITTriggerRuntimePolicy") { db in
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.sortedKeys]
      let defaultPolicyJSON = String(decoding: try encoder.encode(JITTriggerRuntimePolicy.ratifiedV1), as: UTF8.self)
      try db.alter(table: "jit_trigger_snapshot_receipts") { table in
        table.add(
          column: "policyJSON", .text
        ).notNull().defaults(to: defaultPolicyJSON)
      }
    }
    migrator.registerMigration("addJITTriggerSnoozedUntil") { db in
      try db.alter(table: "jit_trigger_mirror") { table in
        table.add(column: "snoozedUntil", .datetime)
      }
    }
    migrator.registerMigration("createJITKnowledgeLedgerMirror") { db in
      try db.create(table: "jit_knowledge_ledger_mirror_receipts", ifNotExists: true) { table in
        table.column("ownerID", .text).primaryKey()
        table.column("accountGeneration", .integer).notNull()
        table.column("sourceGeneration", .integer).notNull()
        table.column("writerEpoch", .integer).notNull()
        table.column("headCommitID", .text).notNull()
        table.column("commitSequence", .integer).notNull()
        table.column("epochID", .text).notNull()
        table.column("contentRevision", .text).notNull()
        table.column("chainRevision", .text).notNull()
        table.column("scannedCount", .integer).notNull()
        table.column("projectedCount", .integer).notNull()
        table.column("rowCount", .integer).notNull()
        table.column("aliasCount", .integer).notNull()
        table.column("updatedAt", .datetime).notNull()
      }
      try db.create(table: "jit_knowledge_ledger_mirror_members", ifNotExists: true) { table in
        table.column("ownerID", .text).notNull()
        table.column("memoryID", .text).notNull()
        table.column("itemRevision", .integer).notNull()
        table.column("status", .text).notNull()
        table.column("sourceState", .text).notNull()
        table.column("canonicalMemoryID", .text)
        table.column("contentPurged", .boolean).notNull()
        table.primaryKey(["ownerID", "memoryID"])
      }
      try db.create(table: "jit_knowledge_ledger_mirror_aliases", ifNotExists: true) { table in
        table.column("ownerID", .text).notNull()
        table.column("aliasMemoryID", .text).notNull()
        table.column("canonicalMemoryID", .text).notNull()
        table.column("sourceMemoryID", .text).notNull()
        table.column("reason", .text).notNull()
        table.primaryKey(["ownerID", "aliasMemoryID", "canonicalMemoryID", "reason"])
      }
      try db.create(
        index: "idx_jit_knowledge_ledger_canonical_alias",
        on: "jit_knowledge_ledger_mirror_aliases",
        columns: ["ownerID", "canonicalMemoryID"],
        options: [.ifNotExists])
    }
  }
}

actor JITTriggerMirror {
  static let shared = JITTriggerMirror()
  static let executionLeaseSeconds: TimeInterval = 300
  static let executionHeartbeatSeconds: TimeInterval = 60

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
    guard snapshot.complete, !snapshot.ownerID.isEmpty, !snapshot.snapshotRevision.isEmpty,
      snapshot.policy.isValid
    else {
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
        row.snoozedUntil.map({ $0.timeIntervalSinceReferenceDate.isFinite }) ?? true,
        let conditionData = row.triggerConditionJSON.data(using: .utf8),
        case .success(let compiled) = KnowledgeLedgerTriggerCompiler.compileAuthoritativeSnapshotRow(
          id: row.memoryID,
          triggerConditionJSON: conditionData,
          wakeupBudgetPerDay: row.wakeupBudgetPerDay,
          snoozedUntil: row.snoozedUntil),
        row.wakeupBudgetPerDay == snapshot.policy.plannedNotificationsPerTriggerPerDay,
        compiled.action
          == KnowledgeLedgerTriggerAction(
            type: row.action.type, prompt: row.action.prompt)
      else { throw JITTriggerMirrorError.malformedRow }
      try db.execute(
        sql: """
          INSERT INTO jit_trigger_mirror
            (memoryID, accountGeneration, itemRevision, updatedAt, conditionJSON, actionType, actionPrompt, wakeupBudgetPerDay, snoozedUntil)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(memoryID) DO UPDATE SET
            accountGeneration = excluded.accountGeneration,
            itemRevision = excluded.itemRevision,
            updatedAt = excluded.updatedAt,
            conditionJSON = excluded.conditionJSON,
            actionType = excluded.actionType,
            actionPrompt = excluded.actionPrompt,
            wakeupBudgetPerDay = excluded.wakeupBudgetPerDay,
            snoozedUntil = excluded.snoozedUntil
          """,
        arguments: [
          row.memoryID, snapshot.accountGeneration, row.itemRevision, row.updatedAt,
          row.triggerConditionJSON, row.action.type, row.action.prompt, row.wakeupBudgetPerDay,
          row.snoozedUntil,
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
    // The mirror is exhaustive and global to the active owner database. Keep
    // exactly one receipt authority so an old owner cannot pair its retained
    // receipt with an identical row installed by a later owner.
    try db.execute(
      sql: "DELETE FROM jit_trigger_snapshot_receipts WHERE ownerID != ?",
      arguments: [snapshot.ownerID])
    try db.execute(
      sql: """
        INSERT INTO jit_trigger_snapshot_receipts
          (ownerID, accountGeneration, headCommitID, commitSequence, snapshotRevision, rowCount, policyJSON, updatedAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ownerID) DO UPDATE SET
          accountGeneration = excluded.accountGeneration,
          headCommitID = excluded.headCommitID,
          commitSequence = excluded.commitSequence,
          snapshotRevision = excluded.snapshotRevision,
          rowCount = excluded.rowCount,
          policyJSON = excluded.policyJSON,
          updatedAt = excluded.updatedAt
        """,
      arguments: [
        snapshot.ownerID, snapshot.accountGeneration, snapshot.headCommitID,
        snapshot.commitSequence, snapshot.snapshotRevision, snapshot.rows.count,
        try Self.policyJSON(snapshot.policy), now,
      ])
    return JITTriggerMirrorReceipt(
      ownerID: snapshot.ownerID,
      accountGeneration: snapshot.accountGeneration,
      commitSequence: snapshot.commitSequence,
      snapshotRevision: snapshot.snapshotRevision,
      rowCount: snapshot.rows.count, policy: snapshot.policy)
  }

  private static func policyJSON(_ policy: JITTriggerRuntimePolicy) throws -> String {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    return String(decoding: try encoder.encode(policy), as: UTF8.self)
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
      let current = try Row.fetchOne(
        db,
        sql:
          "SELECT snapshotRevision, policyJSON FROM jit_trigger_snapshot_receipts WHERE ownerID = ? AND accountGeneration = ? AND commitSequence = ?",
        arguments: [receipt.ownerID, receipt.accountGeneration, receipt.commitSequence])
      guard let current,
        (current["snapshotRevision"] as String) == receipt.snapshotRevision,
        (current["policyJSON"] as String) == (try Self.policyJSON(receipt.policy))
      else { throw JITTriggerMirrorError.staleRevision }
      return try Row.fetchAll(
        db,
        sql:
          "SELECT memoryID, conditionJSON, wakeupBudgetPerDay, snoozedUntil FROM jit_trigger_mirror ORDER BY memoryID"
      )
      .map { row in
        let id: String = row["memoryID"]
        let json: String = row["conditionJSON"]
        let budget: Int? = row["wakeupBudgetPerDay"]
        let snoozedUntil: Date? = row["snoozedUntil"]
        guard let data = json.data(using: .utf8),
          case .success(let trigger) = KnowledgeLedgerTriggerCompiler.compileAuthoritativeSnapshotRow(
            id: id, triggerConditionJSON: data, wakeupBudgetPerDay: budget,
            snoozedUntil: snoozedUntil)
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

  func claimPlannedWakeup(_ request: JITPlannedWakeupRequest) async throws
    -> JITTriggerWakeupClaim?
  {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw JITTriggerMirrorError.databaseUnavailable }
    return try await pool.write { db in
      try Self.claimPlannedWakeup(request, in: db)
    }
  }

  func beginPlannedExecution(
    _ authority: JITPlannedExecutionAuthority,
    claim: JITTriggerWakeupClaim,
    now: Date = Date()
  ) async throws -> Bool {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw JITTriggerMirrorError.databaseUnavailable }
    return try await pool.write { db in
      try Self.beginPlannedExecution(
        authority, claim: claim, now: now, in: db)
    }
  }

  func beginAmbientExecution(
    claim: JITTriggerWakeupClaim,
    now: Date = Date()
  ) async throws -> Bool {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw JITTriggerMirrorError.databaseUnavailable }
    return try await pool.write { db in
      try Self.beginAmbientExecution(claim: claim, now: now, in: db)
    }
  }

  func renewExecutionLease(
    claim: JITTriggerWakeupClaim,
    now: Date = Date()
  ) async throws -> Bool {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw JITTriggerMirrorError.databaseUnavailable }
    return try await pool.write { db in
      try Self.renewExecutionLease(claim: claim, now: now, in: db)
    }
  }

  func wakeupCounts(
    triggerIDs: [String],
    budgetDay: String,
    now: Date
  ) async throws -> [String: Int] {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw JITTriggerMirrorError.databaseUnavailable }
    return try await pool.read { db in
      try Self.wakeupCounts(triggerIDs: triggerIDs, budgetDay: budgetDay, now: now, in: db)
    }
  }

  static func wakeupCounts(
    triggerIDs: [String],
    budgetDay: String,
    now: Date,
    in db: Database
  ) throws -> [String: Int] {
    let boundedIDs = Array(Set(triggerIDs)).sorted()
    guard boundedIDs.count <= KnowledgeLedgerTriggerWatchlistRuntime.maxWakeupCounterCandidates,
      boundedIDs.allSatisfy({ !$0.isEmpty })
    else { throw JITTriggerMirrorError.malformedRow }
    guard !boundedIDs.isEmpty else { return [:] }
    let placeholders = boundedIDs.map { _ in "?" }.joined(separator: ",")
    var arguments: [DatabaseValueConvertible?] = boundedIDs
    arguments.append(budgetDay)
    arguments.append(now)
    return try Row.fetchAll(
      db,
      sql: """
        SELECT triggerID, COUNT(*) AS used
        FROM jit_trigger_wakeup_receipts
        WHERE triggerID IN (\(placeholders)) AND budgetDay = ?
          AND (state = 'delivered' OR (state IN ('claimed', 'executing') AND leaseExpiresAt > ?))
        GROUP BY triggerID
        """,
      arguments: StatementArguments(arguments)
    ).reduce(into: [:]) { counts, row in
      let triggerID: String = row["triggerID"]
      let used: Int = row["used"]
      counts[triggerID] = used
    }
  }

  /// Today's ambient nano spend, read from the same receipts that enforce the
  /// daily cap, so pacing and the cap can never disagree about what was bought.
  func ambientNanoUsage(budgetDay: String, now: Date) async throws -> JITAmbientNanoUsage {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw JITTriggerMirrorError.databaseUnavailable }
    return try await pool.read { db in
      try Self.ambientNanoUsage(budgetDay: budgetDay, now: now, in: db)
    }
  }

  static func ambientNanoUsage(budgetDay: String, now: Date, in db: Database) throws -> JITAmbientNanoUsage {
    let row = try Row.fetchOne(
      db,
      sql: """
        SELECT COUNT(*) AS used, MAX(updatedAt) AS lastSpentAt
        FROM jit_trigger_wakeup_receipts
        WHERE triggerID = 'ambient-nano' AND budgetDay = ?
          AND (state = 'delivered' OR (state IN ('claimed', 'executing') AND leaseExpiresAt > ?))
        """,
      arguments: [budgetDay, now])
    let used: Int = row?["used"] ?? 0
    let lastSpentAt: Date? = row?["lastSpentAt"]
    return JITAmbientNanoUsage(used: used, lastSpentAt: used > 0 ? lastSpentAt : nil)
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
    return claim
  }

  func completeAmbientNanoAttempt(
    _ claim: JITTriggerWakeupClaim,
    contextID: String,
    semanticFingerprint: String,
    now: Date = Date()
  ) async -> Bool {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return false }
    return
      (try? await pool.write { db in
        try Self.completeAmbientNanoAttempt(
          claim, contextID: contextID, semanticFingerprint: semanticFingerprint, now: now, in: db)
      }) ?? false
  }

  static func completeAmbientNanoAttempt(
    _ claim: JITTriggerWakeupClaim,
    contextID: String,
    semanticFingerprint: String,
    now: Date,
    in db: Database
  ) throws -> Bool {
    guard
      claim.triggerID == "ambient-nano",
      claim.continuityKey == "jit-nano:\(contextID):\(semanticFingerprint)",
      let row = try Row.fetchOne(
        db,
        sql: """
            SELECT state, leaseToken FROM jit_trigger_wakeup_receipts
            WHERE continuityKey = ?
          """,
        arguments: [claim.continuityKey]),
      let state: String = row["state"],
      let leaseToken: String? = row["leaseToken"],
      state == "claimed",
      leaseToken == claim.leaseToken
    else { return false }
    try db.execute(
      sql: """
          UPDATE jit_trigger_wakeup_receipts
          SET state = 'delivered', leaseToken = NULL, leaseExpiresAt = NULL, updatedAt = ?
          WHERE continuityKey = ? AND leaseToken = ? AND state = 'claimed'
        """,
      arguments: [now, claim.continuityKey, claim.leaseToken])
    guard db.changesCount == 1 else { return false }
    try db.execute(
      sql: """
          INSERT INTO jit_ambient_context_state (contextID, semanticFingerprint, updatedAt)
          VALUES (?, ?, ?)
          ON CONFLICT(contextID) DO UPDATE SET
            semanticFingerprint = excluded.semanticFingerprint,
            updatedAt = excluded.updatedAt
        """,
      arguments: [contextID, semanticFingerprint, now])
    return true
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
      if state == "delivered"
        || (["claimed", "executing"].contains(state) && (leaseExpiresAt ?? .distantPast) > now)
      {
        return nil
      }
    }
    let used: Int =
      try Int.fetchOne(
        db,
        sql: """
          SELECT COUNT(*) FROM jit_trigger_wakeup_receipts
          WHERE triggerID = ? AND budgetDay = ?
            AND (state = 'delivered' OR (state IN ('claimed', 'executing') AND leaseExpiresAt > ?))
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

  static func claimPlannedWakeup(
    _ request: JITPlannedWakeupRequest,
    leaseSeconds: TimeInterval = 180,
    in db: Database
  ) throws -> JITTriggerWakeupClaim? {
    let authority = request.authority
    guard request.lane == .planned,
      request.snapshotRevision == authority.snapshotRevision,
      request.triggerID == request.triggerRow.memoryID,
      let receipt = try Row.fetchOne(
        db,
        sql: """
          SELECT accountGeneration, commitSequence, snapshotRevision, rowCount
          FROM jit_trigger_snapshot_receipts WHERE ownerID = ?
          """,
        arguments: [authority.ownerID]),
      (receipt["accountGeneration"] as Int) == authority.accountGeneration,
      (receipt["commitSequence"] as Int) == authority.commitSequence,
      (receipt["snapshotRevision"] as String) == authority.snapshotRevision,
      (receipt["rowCount"] as Int) == authority.rowCount,
      let current = try Row.fetchOne(
        db,
        sql: """
          SELECT accountGeneration, itemRevision, updatedAt, conditionJSON,
                 actionType, actionPrompt, wakeupBudgetPerDay, snoozedUntil
          FROM jit_trigger_mirror WHERE memoryID = ?
          """,
        arguments: [request.triggerID]),
      (current["accountGeneration"] as Int) == authority.accountGeneration,
      (current["itemRevision"] as Int) == request.triggerRow.itemRevision,
      (current["updatedAt"] as Date) == request.triggerRow.updatedAt,
      (current["conditionJSON"] as String) == request.triggerRow.triggerConditionJSON,
      (current["actionType"] as String) == request.triggerRow.action.type,
      (current["actionPrompt"] as String) == request.triggerRow.action.prompt,
      (current["wakeupBudgetPerDay"] as Int?) == request.triggerRow.wakeupBudgetPerDay,
      (current["snoozedUntil"] as Date?) == request.triggerRow.snoozedUntil,
      request.triggerRow.snoozedUntil.map({ request.now >= $0 }) ?? true
    else { return nil }
    return try claimWakeup(
      continuityKey: request.continuityKey,
      triggerID: request.triggerID,
      lane: request.lane,
      budgetDay: request.budgetDay,
      snapshotRevision: request.snapshotRevision,
      observationFingerprint: request.observationFingerprint,
      budget: request.budget,
      now: request.now,
      leaseSeconds: leaseSeconds,
      in: db)
  }

  static func beginPlannedExecution(
    _ authority: JITPlannedExecutionAuthority,
    claim: JITTriggerWakeupClaim,
    now: Date,
    in db: Database
  ) throws -> Bool {
    let receipt = authority.receipt
    let triggerRow = authority.triggerRow
    guard claim.triggerID == triggerRow.memoryID,
      let currentReceipt = try Row.fetchOne(
        db,
        sql: """
          SELECT accountGeneration, commitSequence, snapshotRevision, rowCount
          FROM jit_trigger_snapshot_receipts WHERE ownerID = ?
          """,
        arguments: [receipt.ownerID]),
      (currentReceipt["accountGeneration"] as Int) == receipt.accountGeneration,
      (currentReceipt["commitSequence"] as Int) == receipt.commitSequence,
      (currentReceipt["snapshotRevision"] as String) == receipt.snapshotRevision,
      (currentReceipt["rowCount"] as Int) == receipt.rowCount,
      let currentTrigger = try Row.fetchOne(
        db,
        sql: """
          SELECT accountGeneration, itemRevision, updatedAt, conditionJSON,
                 actionType, actionPrompt, wakeupBudgetPerDay, snoozedUntil
          FROM jit_trigger_mirror WHERE memoryID = ?
          """,
        arguments: [claim.triggerID]),
      (currentTrigger["accountGeneration"] as Int) == receipt.accountGeneration,
      (currentTrigger["itemRevision"] as Int) == triggerRow.itemRevision,
      (currentTrigger["updatedAt"] as Date) == triggerRow.updatedAt,
      (currentTrigger["conditionJSON"] as String) == triggerRow.triggerConditionJSON,
      (currentTrigger["actionType"] as String) == triggerRow.action.type,
      (currentTrigger["actionPrompt"] as String) == triggerRow.action.prompt,
      (currentTrigger["wakeupBudgetPerDay"] as Int?) == triggerRow.wakeupBudgetPerDay,
      (currentTrigger["snoozedUntil"] as Date?) == triggerRow.snoozedUntil,
      triggerRow.snoozedUntil.map({ now >= $0 }) ?? true,
      let wakeup = try Row.fetchOne(
        db,
        sql: """
          SELECT lane, snapshotRevision, state, leaseToken, leaseExpiresAt
          FROM jit_trigger_wakeup_receipts WHERE continuityKey = ? AND triggerID = ?
          """,
        arguments: [claim.continuityKey, claim.triggerID]),
      (wakeup["lane"] as String) == JITProactivityLane.planned.rawValue,
      (wakeup["snapshotRevision"] as String) == receipt.snapshotRevision,
      (wakeup["state"] as String) == "claimed",
      (wakeup["leaseToken"] as String?) == claim.leaseToken,
      ((wakeup["leaseExpiresAt"] as Date?) ?? .distantPast) > now
    else { return false }
    // This state transition is the durable execution-start boundary. A reconciliation that commits
    // before it makes the transaction fail closed; one that commits afterward cannot retroactively
    // revoke a turn whose model-work lease has already started.
    try db.execute(
      sql: """
        UPDATE jit_trigger_wakeup_receipts
        SET state = 'executing', leaseExpiresAt = ?, updatedAt = ?
        WHERE continuityKey = ? AND triggerID = ? AND leaseToken = ? AND state = 'claimed'
        """,
      arguments: [
        now.addingTimeInterval(executionLeaseSeconds), now,
        claim.continuityKey, claim.triggerID, claim.leaseToken,
      ])
    return db.changesCount == 1
  }

  static func beginAmbientExecution(
    claim: JITTriggerWakeupClaim,
    now: Date,
    in db: Database
  ) throws -> Bool {
    guard
      let wakeup = try Row.fetchOne(
        db,
        sql: """
          SELECT lane, state, leaseToken, leaseExpiresAt
          FROM jit_trigger_wakeup_receipts WHERE continuityKey = ? AND triggerID = ?
          """,
        arguments: [claim.continuityKey, claim.triggerID]),
      (wakeup["lane"] as String) == JITProactivityLane.ambient.rawValue,
      (wakeup["state"] as String) == "claimed",
      (wakeup["leaseToken"] as String?) == claim.leaseToken,
      ((wakeup["leaseExpiresAt"] as Date?) ?? .distantPast) > now
    else { return false }
    try db.execute(
      sql: """
        UPDATE jit_trigger_wakeup_receipts
        SET state = 'executing', leaseExpiresAt = ?, updatedAt = ?
        WHERE continuityKey = ? AND triggerID = ? AND leaseToken = ? AND state = 'claimed'
        """,
      arguments: [
        now.addingTimeInterval(executionLeaseSeconds), now,
        claim.continuityKey, claim.triggerID, claim.leaseToken,
      ])
    return db.changesCount == 1
  }

  static func renewExecutionLease(
    claim: JITTriggerWakeupClaim,
    now: Date,
    in db: Database
  ) throws -> Bool {
    try db.execute(
      sql: """
        UPDATE jit_trigger_wakeup_receipts
        SET leaseExpiresAt = ?, updatedAt = ?
        WHERE continuityKey = ? AND triggerID = ? AND leaseToken = ? AND state = 'executing'
        """,
      arguments: [
        now.addingTimeInterval(executionLeaseSeconds), now,
        claim.continuityKey, claim.triggerID, claim.leaseToken,
      ])
    return db.changesCount == 1
  }

  func finishWakeup(_ claim: JITTriggerWakeupClaim, delivered: Bool, now: Date = Date()) async {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return }
    try? await pool.write { db in
      try db.execute(
        sql: """
          UPDATE jit_trigger_wakeup_receipts
          SET state = ?, leaseToken = NULL, leaseExpiresAt = NULL, updatedAt = ?
          WHERE continuityKey = ? AND leaseToken = ? AND state IN ('claimed', 'executing')
          """,
        arguments: [delivered ? "delivered" : "failed", now, claim.continuityKey, claim.leaseToken])
    }
  }
}

extension KnowledgeLedgerTriggerCompiler {
  static func compileAuthoritativeSnapshotRow(
    id: String,
    triggerConditionJSON: Data,
    wakeupBudgetPerDay: Int?,
    snoozedUntil: Date? = nil
  ) -> Result<KnowledgeLedgerCompiledTrigger, KnowledgeLedgerTriggerCompileFailure> {
    compile(
      KnowledgeLedgerTriggerRow(
        id: id,
        triggerConditionJSON: triggerConditionJSON,
        wakeupBudgetPerDay: wakeupBudgetPerDay),
      snoozedUntil: snoozedUntil)
  }
}
