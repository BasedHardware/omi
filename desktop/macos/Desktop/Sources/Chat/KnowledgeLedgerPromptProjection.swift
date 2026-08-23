import Foundation

/// The client-side prompt view of `knowledge_ledger.v1`.
///
/// This is a projection over the released memory mirror, not a second storage
/// authority. Rows without the canonical schema or required policy fields are
/// intentionally ignored during the migration window; treating an old row as
/// a current profile fact would be less safe than omitting it.
struct KnowledgeLedgerPromptProjection: Equatable, Sendable {
  static let schemaVersion = "knowledge_ledger.v1"
  static let profileCharacterBudget = 2_400
  static let playbookCharacterBudget = 800

  struct Row: Equatable, Sendable {
    let id: String
    let content: String
    let createdAt: Date
    let metadata: [String: String]

    init(id: String, content: String, createdAt: Date = Date(), metadata: [String: String] = [:]) {
      self.id = id
      self.content = content
      self.createdAt = createdAt
      self.metadata = metadata
    }

    init(memory: ServerMemory) {
      self.init(
        id: memory.id,
        content: memory.content,
        createdAt: memory.createdAt,
        metadata: memory.ledgerMetadata
      )
    }

    var schemaVersion: String? { metadata["ledger_schema_version"] }
    var kind: String? { metadata["kind"] }
    var subjectScope: String? { metadata["subject_scope"] }
    var slot: String? { Self.normalized(metadata["slot"]) }
    var intentBacked: Bool { metadata["intent_backed"] == "true" }
    var curationWeight: Int { Int(metadata["curation_weight"] ?? "") ?? 0 }
    var validAt: String { metadata["valid_at"] ?? "" }

    var isOpen: Bool {
      let status = metadata["status"]?.lowercased()
      guard status == nil || status == "active" else { return false }
      return Self.isBlank(metadata["invalid_at"])
        && Self.isBlank(metadata["valid_to"])
        && Self.isBlank(metadata["superseded_by"])
    }

    var trimmedContent: String { content.trimmingCharacters(in: .whitespacesAndNewlines) }

    private static func normalized(_ value: String?) -> String? {
      guard let value else { return nil }
      let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
      return trimmed.isEmpty ? nil : trimmed
    }

    private static func isBlank(_ value: String?) -> Bool {
      guard let value else { return true }
      let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
      return normalized.isEmpty || normalized == "null"
    }
  }

  let rows: [Row]

  /// A mixed snapshot is not migration proof. Falling back preserves the
  /// released prompt until every row in this bounded cache is ledger-shaped;
  /// one newly written ledger fact must never hide historical memories.
  var isCompleteLedgerSnapshot: Bool {
    !rows.isEmpty && rows.allSatisfy { $0.schemaVersion == Self.schemaVersion }
  }

  init(memories: [ServerMemory]) {
    self.init(rows: memories.map(Row.init(memory:)))
  }

  init(rows: [Row]) {
    self.rows = rows
  }

  /// Render the complete bounded context, or nil when no canonical row is
  /// present. The nil result is the fail-safe for old payloads.
  func render(
    userName: String?,
    marker: ((String) -> String?)? = nil
  ) -> String? {
    guard isCompleteLedgerSnapshot else { return nil }

    let facts = eligibleFacts
    let profileLines = boundedLines(
      facts.compactMap { row in
        guard let slot = row.slot else { return nil }
        let citation = marker?(row.id).map { " \($0)" } ?? ""
        return "\(slot): \(row.trimmedContent)\(citation)"
      },
      budget: Self.profileCharacterBudget
    )

    let displayName = userName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    let profile = profileLines.isEmpty ? "(no current slotted facts)" : profileLines
    var sections = ["Current profile for \(displayName.isEmpty ? "the user" : displayName):\n\(profile)"]
    let playbookLines = boundedLines(
      eligiblePlaybooks.map { row in
        let citation = marker?(row.id).map { " \($0)" } ?? ""
        return "\(row.id): \(row.trimmedContent)\(citation)"
      },
      budget: Self.playbookCharacterBudget
    )
    if !playbookLines.isEmpty {
      sections.append(
        "Available playbooks (call read_playbook for the body; do not infer it from the title):\n\(playbookLines)"
      )
    }
    return sections.joined(separator: "\n\n") + "\n"
  }

  /// Sources admitted into the citation ledger. Bodies and excluded rows are
  /// never represented here, so markers cannot grant them prompt authority.
  var citationSources: [ChatPromptCitationSource] {
    guard isCompleteLedgerSnapshot else { return [] }
    let factSources = eligibleFacts.map {
      ChatPromptCitationSource(
        kind: .memory,
        sourceID: $0.id,
        title: $0.slot ?? "Memory",
        preview: $0.trimmedContent,
        createdAt: ISO8601DateFormatter().string(from: $0.createdAt)
      )
    }
    let playbookSources = eligiblePlaybooks.map {
      ChatPromptCitationSource(
        kind: .memory,
        sourceID: $0.id,
        title: $0.trimmedContent,
        preview: $0.trimmedContent,
        createdAt: ISO8601DateFormatter().string(from: $0.createdAt)
      )
    }
    return factSources + playbookSources
  }

  private var eligibleFacts: [Row] {
    rows
      .filter {
        $0.schemaVersion == Self.schemaVersion
          && $0.kind == "fact"
          && $0.subjectScope == "primary_user"
          && $0.intentBacked
          && $0.isOpen
          && $0.slot != nil
          && !$0.trimmedContent.isEmpty
      }
      .sorted {
        if $0.curationWeight != $1.curationWeight { return $0.curationWeight > $1.curationWeight }
        if $0.slot != $1.slot { return ($0.slot ?? "") < ($1.slot ?? "") }
        if $0.validAt != $1.validAt { return $0.validAt < $1.validAt }
        return $0.id < $1.id
      }
  }

  private var eligiblePlaybooks: [Row] {
    rows
      .filter {
        $0.schemaVersion == Self.schemaVersion
          && $0.kind == "document"
          && $0.isOpen
          && !$0.trimmedContent.isEmpty
      }
      .sorted {
        if $0.curationWeight != $1.curationWeight { return $0.curationWeight > $1.curationWeight }
        if $0.trimmedContent != $1.trimmedContent { return $0.trimmedContent < $1.trimmedContent }
        return $0.id < $1.id
      }
  }

  private func boundedLines(_ lines: [String], budget: Int) -> String {
    var result: [String] = []
    var used = 0
    for line in lines {
      let separator = result.isEmpty ? 0 : 1
      guard used + separator + line.count <= budget else { continue }
      result.append(line)
      used += separator + line.count
    }
    return result.joined(separator: "\n")
  }
}
