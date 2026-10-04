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
      && maxCalendarEvents == 32
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
    migrator.registerMigration("createJITNanoBillingObservations") { db in
      try db.create(table: "jit_nano_billing_observations", ifNotExists: true) { table in
        table.column("observationID", .text).primaryKey()
        table.column("ownerID", .text).notNull()
        table.column("accountGeneration", .integer).notNull()
        table.column("snapshotRevision", .text).notNull()
        table.column("budgetDay", .text).notNull()
        table.column("lane", .text).notNull()
        table.column("contextID", .text).notNull()
        table.column("candidateID", .text).notNull()
        table.column("executionID", .text)
        table.column("dispatch", .text).notNull()
        table.column("outcome", .text).notNull()
        table.column("operation", .text).notNull()
        table.column("requestID", .text)
        table.column("provider", .text)
        table.column("providerModel", .text)
        table.column("providerResponseID", .text)
        table.column("fallbackClass", .text)
        table.column("inputTokens", .integer)
        table.column("outputTokens", .integer)
        table.column("totalTokens", .integer)
        table.column("cachedInputTokens", .integer)
        table.column("cacheWriteTokens", .integer)
        table.column("usageStatus", .text).notNull()
        table.column("costStatus", .text).notNull()
        table.column("estimatedCostMicroUSD", .integer)
        table.column("providerAttempts", .integer)
        table.column("attemptIDsJSON", .text).notNull()
        table.column("updatedAt", .datetime).notNull()
      }
      try db.create(
        index: "idx_jit_nano_billing_execution",
        on: "jit_nano_billing_observations",
        columns: ["ownerID", "executionID"],
        options: [.ifNotExists])
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
