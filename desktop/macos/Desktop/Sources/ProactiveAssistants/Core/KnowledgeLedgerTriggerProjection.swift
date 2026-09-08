import Foundation

/// A bounded, inert projection of the local ledger mirror.
///
/// This type deliberately owns neither storage nor scheduling. It only turns
/// server-authoritative rows into the existing pure trigger compiler input and
/// reports rows that must remain quarantined. Callers can adopt the result
/// later without making this projection a second authority.
struct KnowledgeLedgerTriggerWatchlistProjection: Equatable, Sendable {
  struct QuarantinedRow: Equatable, Sendable {
    let id: String
    let failure: KnowledgeLedgerTriggerProjectionFailure
  }

  let entries: [KnowledgeLedgerCompiledTrigger]
  let quarantined: [QuarantinedRow]
}

enum KnowledgeLedgerTriggerProjectionFailure: Error, Equatable, Sendable {
  case deletedRow
  case rejectedRow
  case missingBackendID
  case closedRow
  case malformed(String)
  case unsupportedSchema(String)
}

extension KnowledgeLedgerTriggerCompiler {
  /// Project a storage snapshot in newest-first order, using the backend ID as
  /// the identity key. Duplicate IDs are resolved before compilation so the
  /// result does not depend on SQLite/API iteration order.
  static func project(records: [MemoryRecord]) -> KnowledgeLedgerTriggerWatchlistProjection {
    let candidates = records.map { record in
      ProjectionCandidate(
        id: record.backendId?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "",
        updatedAt: record.updatedAt,
        tieBreaker: Self.tieBreaker(for: record),
        source: .record(record)
      )
    }
    return project(candidates)
  }

  /// Project already-decoded API rows with the same deterministic ordering and
  /// deduplication policy used for local records.
  static func project(memories: [ServerMemory]) -> KnowledgeLedgerTriggerWatchlistProjection {
    let candidates = memories.map { memory in
      ProjectionCandidate(
        id: memory.id.trimmingCharacters(in: .whitespacesAndNewlines),
        updatedAt: memory.updatedAt,
        tieBreaker: Self.tieBreaker(for: memory),
        source: .memory(memory)
      )
    }
    return project(candidates)
  }

  private enum ProjectionSource {
    case record(MemoryRecord)
    case memory(ServerMemory)
  }

  private struct ProjectionCandidate {
    let id: String
    let updatedAt: Date
    let tieBreaker: String
    let source: ProjectionSource
  }

  private static func project(_ input: [ProjectionCandidate]) -> KnowledgeLedgerTriggerWatchlistProjection {
    let candidates = input.sorted { lhs, rhs in
      if lhs.updatedAt != rhs.updatedAt { return lhs.updatedAt > rhs.updatedAt }
      if lhs.id != rhs.id { return lhs.id < rhs.id }
      return lhs.tieBreaker < rhs.tieBreaker
    }

    var seenIDs = Set<String>()
    var entries: [KnowledgeLedgerCompiledTrigger] = []
    var quarantined: [KnowledgeLedgerTriggerWatchlistProjection.QuarantinedRow] = []
    for candidate in candidates where seenIDs.insert(candidate.id).inserted {
      switch candidate.source {
      case .record(let record):
        switch compile(record: record, candidateID: candidate.id) {
        case .success(let entry): entries.append(entry)
        case .failure(let failure): quarantined.append(.init(id: candidate.id, failure: failure))
        }
      case .memory(let memory):
        switch compile(memory: memory, candidateID: candidate.id) {
        case .success(let entry): entries.append(entry)
        case .failure(let failure): quarantined.append(.init(id: candidate.id, failure: failure))
        }
      }
    }
    return KnowledgeLedgerTriggerWatchlistProjection(entries: entries, quarantined: quarantined)
  }

  private static func compile(
    record: MemoryRecord,
    candidateID: String
  ) -> Result<KnowledgeLedgerCompiledTrigger, KnowledgeLedgerTriggerProjectionFailure> {
    guard !candidateID.isEmpty else { return .failure(.missingBackendID) }
    guard !record.deleted else { return .failure(.deletedRow) }
    guard record.userReview != false else { return .failure(.rejectedRow) }
    guard let memory = record.toServerMemory() else {
      return .failure(.malformed("memory record cannot be represented as a server row"))
    }
    return compile(memory: memory, candidateID: candidateID, triggerConditionJSON: record.ledgerTriggerConditionJSON)
  }

  private static func compile(
    memory: ServerMemory,
    candidateID: String
  ) -> Result<KnowledgeLedgerCompiledTrigger, KnowledgeLedgerTriggerProjectionFailure> {
    guard !candidateID.isEmpty else { return .failure(.missingBackendID) }
    guard memory.userReview != false else { return .failure(.rejectedRow) }
    return compile(
      memory: memory,
      candidateID: candidateID,
      triggerConditionJSON: MemoryLedgerMetadata.triggerConditionJSON(from: memory.ledgerMetadata)
    )
  }

  private static func compile(
    memory: ServerMemory,
    candidateID: String,
    triggerConditionJSON: Data?
  ) -> Result<KnowledgeLedgerCompiledTrigger, KnowledgeLedgerTriggerProjectionFailure> {
    let metadata = memory.ledgerMetadata
    let schemaVersion = metadata[MemoryLedgerMetadata.schemaVersionKey] ?? ""
    guard schemaVersion == KnowledgeLedgerTriggerRow.schemaVersion else {
      return .failure(.unsupportedSchema(schemaVersion))
    }

    let status = metadata["status"] ?? "active"
    guard metadata["kind"] == "trigger",
      metadata["subject_scope"] == "primary_user",
      metadata["intent_backed"] == "true",
      status.caseInsensitiveCompare("active") == .orderedSame,
      isBlank(metadata["invalid_at"]),
      isBlank(metadata["valid_to"]),
      isBlank(metadata["superseded_by"])
    else {
      return .failure(.closedRow)
    }
    guard let triggerConditionJSON else {
      return .failure(.malformed("trigger condition is missing, malformed, or oversized"))
    }

    switch parseRowMetadata(metadata) {
    case .failure(let failure): return .failure(failure)
    case .success(let rowMetadata):
      let row = KnowledgeLedgerTriggerRow(
        id: candidateID,
        triggerConditionJSON: triggerConditionJSON,
        ledgerSchemaVersion: schemaVersion,
        kind: metadata["kind"] ?? "",
        status: status,
        subjectScope: metadata["subject_scope"] ?? "",
        intentBacked: metadata["intent_backed"] == "true",
        supersededBy: metadata["superseded_by"],
        invalidAt: metadata["invalid_at"],
        validTo: metadata["valid_to"],
        modelID: rowMetadata.modelID,
        modelVersion: rowMetadata.modelVersion,
        threshold: rowMetadata.threshold,
        wakeupBudgetPerDay: rowMetadata.wakeupBudgetPerDay
      )
      switch compile(row) {
      case .success(let entry): return .success(entry)
      case .failure(let failure): return .failure(map(failure))
      }
    }
  }

  private struct ParsedMetadata {
    let modelID: String?
    let modelVersion: String?
    let threshold: Double?
    let wakeupBudgetPerDay: Int?
  }

  private static func parseRowMetadata(
    _ metadata: [String: String]
  ) -> Result<ParsedMetadata, KnowledgeLedgerTriggerProjectionFailure> {
    let modelID = tryOptionalString(metadata["model_id"], key: "model_id")
    let modelVersion = tryOptionalString(metadata["model_version"], key: "model_version")
    let threshold = tryOptionalDouble(metadata["threshold"], key: "threshold")
    let wakeupBudget = tryOptionalInt(metadata["wakeup_budget_per_day"], key: "wakeup_budget_per_day")
    switch (modelID, modelVersion, threshold, wakeupBudget) {
    case (.failure(let failure), _, _, _), (_, .failure(let failure), _, _),
      (_, _, .failure(let failure), _), (_, _, _, .failure(let failure)):
      return .failure(failure)
    case (.success(let modelID), .success(let modelVersion), .success(let threshold), .success(let wakeupBudget)):
      return .success(
        ParsedMetadata(
          modelID: modelID,
          modelVersion: modelVersion,
          threshold: threshold,
          wakeupBudgetPerDay: wakeupBudget
        ))
    }
  }

  private static func tryOptionalString(
    _ value: String?,
    key: String
  ) -> Result<String?, KnowledgeLedgerTriggerProjectionFailure> {
    guard let value else { return .success(nil) }
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return .failure(.malformed("\(key) is empty")) }
    return .success(trimmed)
  }

  private static func tryOptionalDouble(
    _ value: String?,
    key: String
  ) -> Result<Double?, KnowledgeLedgerTriggerProjectionFailure> {
    guard let value else { return .success(nil) }
    guard let parsed = Double(value), parsed.isFinite else {
      return .failure(.malformed("\(key) is invalid"))
    }
    return .success(parsed)
  }

  private static func tryOptionalInt(
    _ value: String?,
    key: String
  ) -> Result<Int?, KnowledgeLedgerTriggerProjectionFailure> {
    guard let value else { return .success(nil) }
    guard let parsed = Int(value) else { return .failure(.malformed("\(key) is invalid")) }
    return .success(parsed)
  }

  private static func map(
    _ failure: KnowledgeLedgerTriggerCompileFailure
  ) -> KnowledgeLedgerTriggerProjectionFailure {
    switch failure {
    case .closedRow: return .closedRow
    case .unsupportedSchema(let version): return .unsupportedSchema(version)
    case .malformed(let reason): return .malformed(reason)
    }
  }

  private static func isBlank(_ value: String?) -> Bool {
    guard let value else { return true }
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return normalized.isEmpty || normalized == "null"
  }

  private static func tieBreaker(for memory: ServerMemory) -> String {
    let metadata = MemoryLedgerMetadata.canonicalJSONString(memory.ledgerMetadata) ?? ""
    return [memory.content, memory.category.rawValue, metadata].joined(separator: "\u{1f}")
  }

  private static func tieBreaker(for record: MemoryRecord) -> String {
    let metadata =
      record.toServerMemory().map { MemoryLedgerMetadata.canonicalJSONString($0.ledgerMetadata) ?? "" } ?? ""
    return [record.content, record.category, metadata].joined(separator: "\u{1f}")
  }
}
