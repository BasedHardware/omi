import Foundation

/// Lossless, deterministic storage helpers for additive ledger fields.
///
/// The local mirror deliberately keeps structured values as canonical JSON
/// strings inside the existing metadata map. This preserves unknown/future
/// rows without teaching SQLite or released clients a server-owned schema;
/// consumers must validate the schema and payload before projecting them.
enum MemoryLedgerMetadata {
  static let schemaVersionKey = "ledger_schema_version"
  static let triggerConditionJSONKey = "trigger_condition_json"
  static let objectEntityIDsJSONKey = "object_entity_ids_json"
  static let qualifiersJSONKey = "qualifiers_json"
  static let argumentsJSONKey = "arguments_json"
  static let maxTriggerConditionCharacters = 8_000

  static func canonicalJSONString(_ value: Any, maximumCharacters: Int? = nil) -> String? {
    guard JSONSerialization.isValidJSONObject(value),
      let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
      let json = String(data: data, encoding: .utf8)
    else { return nil }
    guard maximumCharacters.map({ json.count <= $0 }) ?? true else { return nil }
    return json
  }

  static func canonicalJSONData(
    from json: String?,
    maximumCharacters: Int = maxTriggerConditionCharacters,
    requireObject: Bool = true
  ) -> Data? {
    guard let json,
      let data = json.data(using: .utf8),
      let value = try? JSONSerialization.jsonObject(with: data),
      !requireObject || value is [String: Any],
      let canonical = canonicalJSONString(value, maximumCharacters: maximumCharacters)?.data(using: .utf8)
    else { return nil }
    return canonical
  }

  static func isSupportedVersion(_ metadata: [String: String]) -> Bool {
    metadata[schemaVersionKey] == "knowledge_ledger.v1"
  }

  /// Trigger payloads are never returned unless they are bounded JSON
  /// objects. A malformed, oversized, legacy, or future row therefore cannot
  /// accidentally become a local watchlist input.
  static func triggerConditionJSON(from metadata: [String: String]) -> Data? {
    guard isSupportedVersion(metadata),
      metadata["kind"] == "trigger",
      metadata["subject_scope"] == "primary_user",
      metadata["intent_backed"] == "true",
      metadata["status"] == nil || metadata["status"]?.lowercased() == "active",
      isBlank(metadata["invalid_at"]),
      isBlank(metadata["valid_to"]),
      isBlank(metadata["superseded_by"])
    else { return nil }
    return canonicalJSONData(
      from: metadata[triggerConditionJSONKey],
      maximumCharacters: maxTriggerConditionCharacters,
      requireObject: true
    )
  }

  private static func isBlank(_ value: String?) -> Bool {
    guard let value else { return true }
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return normalized.isEmpty || normalized == "null"
  }
}

/// Bounds and canonical serialization for optional memory evidence.
///
/// Evidence is useful for audit/review and future local rendering, but this
/// mirror intentionally has no prompt authority. Invalid, future-shaped, or
/// oversized payloads become an empty mirror while the memory text remains
/// readable.
enum MemoryLedgerEvidence {
  static let maxEvidenceEntries = 32
  static let maxEvidenceJSONBytes = 16 * 1024

  static func normalize(_ wire: [OmiAPI.Evidence]) -> [ServerMemoryEvidence]? {
    guard wire.count <= maxEvidenceEntries else { return nil }
    let values = wire.map(ServerMemoryEvidence.init)
    guard values.allSatisfy(isValid), canonicalJSONString(values) != nil else { return nil }
    return values
  }

  static func canonicalJSONString(_ values: [ServerMemoryEvidence]) -> String? {
    guard values.count <= maxEvidenceEntries else { return nil }
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    guard let data = try? encoder.encode(values), data.count <= maxEvidenceJSONBytes else { return nil }
    return String(data: data, encoding: .utf8)
  }

  static func decode(_ json: String?) -> [ServerMemoryEvidence] {
    guard let json,
      let data = json.data(using: .utf8),
      let values = try? JSONDecoder().decode([ServerMemoryEvidence].self, from: data),
      values.allSatisfy(isValid),
      canonicalJSONString(values) != nil
    else { return [] }
    return values
  }

  private static func isValid(_ value: ServerMemoryEvidence) -> Bool {
    !value.evidenceId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      && !value.independenceGroup.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }
}
