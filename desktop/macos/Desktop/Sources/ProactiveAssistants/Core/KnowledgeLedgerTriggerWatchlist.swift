import CryptoKit
import Foundation

/// The local trigger projection of `knowledge_ledger.v1`.
///
/// This is deliberately a pure evaluator.  It consumes a bounded row and
/// caller-supplied observations, but owns no cache, timer, network client, or
/// model.  The shipped proactivity lane can adopt this seam later without
/// making the trigger evaluator a second storage authority.
struct KnowledgeLedgerTriggerRow: Equatable, Sendable {
  static let schemaVersion = "knowledge_ledger.v1"

  let id: String
  let ledgerSchemaVersion: String
  let kind: String
  let status: String
  let subjectScope: String
  let intentBacked: Bool
  let triggerConditionJSON: Data
  let supersededBy: String?
  let invalidAt: String?
  let validTo: String?
  let modelID: String?
  let modelVersion: String?
  let threshold: Double?
  let wakeupBudgetPerDay: Int?

  init(
    id: String,
    triggerCondition: [String: Any],
    ledgerSchemaVersion: String = KnowledgeLedgerTriggerRow.schemaVersion,
    kind: String = "trigger",
    status: String = "active",
    subjectScope: String = "primary_user",
    intentBacked: Bool = true,
    supersededBy: String? = nil,
    invalidAt: String? = nil,
    validTo: String? = nil,
    modelID: String? = nil,
    modelVersion: String? = nil,
    threshold: Double? = nil,
    wakeupBudgetPerDay: Int? = nil
  ) throws {
    guard JSONSerialization.isValidJSONObject(triggerCondition) else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("trigger condition is not JSON")
    }
    self.init(
      id: id,
      triggerConditionJSON: try JSONSerialization.data(withJSONObject: triggerCondition, options: [.sortedKeys]),
      ledgerSchemaVersion: ledgerSchemaVersion,
      kind: kind,
      status: status,
      subjectScope: subjectScope,
      intentBacked: intentBacked,
      supersededBy: supersededBy,
      invalidAt: invalidAt,
      validTo: validTo,
      modelID: modelID,
      modelVersion: modelVersion,
      threshold: threshold,
      wakeupBudgetPerDay: wakeupBudgetPerDay
    )
  }

  init(
    id: String,
    triggerConditionJSON: Data,
    ledgerSchemaVersion: String = KnowledgeLedgerTriggerRow.schemaVersion,
    kind: String = "trigger",
    status: String = "active",
    subjectScope: String = "primary_user",
    intentBacked: Bool = true,
    supersededBy: String? = nil,
    invalidAt: String? = nil,
    validTo: String? = nil,
    modelID: String? = nil,
    modelVersion: String? = nil,
    threshold: Double? = nil,
    wakeupBudgetPerDay: Int? = nil
  ) {
    self.id = id
    self.ledgerSchemaVersion = ledgerSchemaVersion
    self.kind = kind
    self.status = status
    self.subjectScope = subjectScope
    self.intentBacked = intentBacked
    self.triggerConditionJSON = triggerConditionJSON
    self.supersededBy = supersededBy
    self.invalidAt = invalidAt
    self.validTo = validTo
    self.modelID = modelID
    self.modelVersion = modelVersion
    self.threshold = threshold
    self.wakeupBudgetPerDay = wakeupBudgetPerDay
  }

  var isOpen: Bool {
    status.caseInsensitiveCompare("active") == .orderedSame
      && Self.isBlank(supersededBy)
      && Self.isBlank(invalidAt)
      && Self.isBlank(validTo)
  }

  private static func isBlank(_ value: String?) -> Bool {
    guard let value else { return true }
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return normalized.isEmpty || normalized == "null"
  }
}

struct KnowledgeLedgerTriggerMetadata: Equatable, Sendable {
  let modelID: String?
  let modelVersion: String?
  let threshold: Double?
  let wakeupBudgetPerDay: Int?
}

struct KnowledgeLedgerTriggerAction: Codable, Equatable, Sendable {
  static let maximumPromptCharacters = 2_000

  let type: String
  let prompt: String

  var isValid: Bool {
    type == "agent_prompt"
      && !prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      && prompt.count <= Self.maximumPromptCharacters
  }
}

struct KnowledgeLedgerTriggerCalendarEvent: Codable, Equatable, Hashable, Sendable {
  let title: String
  let eventType: String
}

struct KnowledgeLedgerTriggerObservation: Codable, Equatable, Sendable {
  static let maxEventIDCharacters = 128
  static let maxTextCharacters = 8_000
  static let maxEntityLabels = 64
  static let maxEntityLabelCandidates = 256
  static let maxEntityLabelCharacters = 120
  static let maxSelectorCharacters = 120
  static let maxCalendarEvents = 32
  static let maxCalendarEventCandidates = 128
  static let maxCalendarFieldCharacters = 160
  static let maxEmbeddingScores = 32
  static let maxEmbeddingScoreCandidates = 128
  static let maxEmbeddingKeyCharacters = 80

  let eventID: String?
  let text: String
  let entityLabels: [String]
  let appName: String?
  let windowTitle: String?
  let occurredAt: Date?
  let calendarEvents: [KnowledgeLedgerTriggerCalendarEvent]
  let embeddingScores: [String: Double]

  private enum CodingKeys: String, CodingKey {
    case eventID
    case text
    case entityLabels
    case appName
    case windowTitle
    case occurredAt
    case calendarEvents
    case embeddingScores
  }

  init(
    eventID: String? = nil,
    text: String = "",
    entityLabels: [String] = [],
    appName: String? = nil,
    windowTitle: String? = nil,
    occurredAt: Date? = nil,
    calendarEvents: [KnowledgeLedgerTriggerCalendarEvent] = [],
    embeddingScores: [String: Double] = [:]
  ) {
    self.eventID = eventID.flatMap { Self.boundedIdentifier($0, limit: Self.maxEventIDCharacters) }
    self.text = String(text.prefix(Self.maxTextCharacters))
    let entityLabelCandidates =
      entityLabels.count <= Self.maxEntityLabelCandidates ? entityLabels : []
    self.entityLabels = Array(
      Set(entityLabelCandidates.compactMap { Self.boundedNormalized($0, limit: Self.maxEntityLabelCharacters) })
        .sorted()
        .prefix(Self.maxEntityLabels)
    )
    self.appName = appName.flatMap { Self.boundedNormalized($0, limit: Self.maxSelectorCharacters) }
    self.windowTitle = windowTitle.flatMap { Self.boundedNormalized($0, limit: Self.maxSelectorCharacters) }
    self.occurredAt = occurredAt
    let calendarEventCandidates =
      calendarEvents.count <= Self.maxCalendarEventCandidates ? calendarEvents : []
    self.calendarEvents = Array(
      Set(
        calendarEventCandidates.compactMap { event -> KnowledgeLedgerTriggerCalendarEvent? in
          let title = Self.boundedNormalized(event.title, limit: Self.maxCalendarFieldCharacters) ?? ""
          let eventType = Self.boundedNormalized(event.eventType, limit: Self.maxCalendarFieldCharacters) ?? ""
          guard !title.isEmpty || !eventType.isEmpty else { return nil }
          return KnowledgeLedgerTriggerCalendarEvent(title: title, eventType: eventType)
        }
      )
      .sorted {
        if $0.title != $1.title { return $0.title < $1.title }
        return $0.eventType < $1.eventType
      }
      .prefix(Self.maxCalendarEvents)
    )
    var normalizedScores: [String: Double] = [:]
    let embeddingScoreCandidates =
      embeddingScores.count <= Self.maxEmbeddingScoreCandidates ? embeddingScores : [:]
    for pair in embeddingScoreCandidates.sorted(by: { $0.key < $1.key }) {
      guard let key = Self.boundedIdentifier(pair.key, limit: Self.maxEmbeddingKeyCharacters), pair.value.isFinite,
        (0...1).contains(pair.value)
      else { continue }
      // Whitespace-normalized duplicate keys are ambiguous. Keeping the lower
      // score is deterministic and fail-closed: normalization can never turn a
      // non-match into a match.
      normalizedScores[key] = min(normalizedScores[key] ?? pair.value, pair.value)
    }
    var boundedScores: [String: Double] = [:]
    for pair in normalizedScores.sorted(by: { $0.key < $1.key }).prefix(Self.maxEmbeddingScores) {
      boundedScores[pair.key] = pair.value
    }
    self.embeddingScores = boundedScores
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    self.init(
      eventID: try container.decodeIfPresent(String.self, forKey: .eventID),
      text: try container.decodeIfPresent(String.self, forKey: .text) ?? "",
      entityLabels: try container.decodeIfPresent([String].self, forKey: .entityLabels) ?? [],
      appName: try container.decodeIfPresent(String.self, forKey: .appName),
      windowTitle: try container.decodeIfPresent(String.self, forKey: .windowTitle),
      occurredAt: try container.decodeIfPresent(Date.self, forKey: .occurredAt),
      calendarEvents: try container.decodeIfPresent([KnowledgeLedgerTriggerCalendarEvent].self, forKey: .calendarEvents)
        ?? [],
      embeddingScores: try container.decodeIfPresent([String: Double].self, forKey: .embeddingScores) ?? [:]
    )
  }

  var fingerprint: String {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    encoder.dateEncodingStrategy = .iso8601
    let data = (try? encoder.encode(self)) ?? Data()
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
  }

  private static func boundedIdentifier(_ value: String, limit: Int) -> String? {
    let candidate = value.prefix(limit + 1)
    guard candidate.count <= limit else { return nil }
    let normalized = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty else { return nil }
    return normalized
  }

  private static func boundedNormalized(_ value: String, limit: Int) -> String? {
    // Four raw characters per retained character leaves room for ordinary
    // whitespace normalization without traversing attacker-sized strings.
    let candidate = value.prefix(limit * 4)
    let normalized = candidate.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ").lowercased()
    guard !normalized.isEmpty else { return nil }
    return String(normalized.prefix(limit))
  }
}

enum KnowledgeLedgerTriggerCompileFailure: Error, Equatable, Sendable {
  case closedRow
  case malformed(String)
  case unsupportedSchema(String)
}

enum KnowledgeLedgerTriggerDecisionStatus: String, Equatable, Sendable {
  case match
  case ambiguous
  case noMatch
}

struct KnowledgeLedgerTriggerDecision: Equatable, Sendable {
  let status: KnowledgeLedgerTriggerDecisionStatus
  let reason: String
  let matchedConditions: [String]
  let missingConditions: [String]
  let matchedFraction: Double
  let observationFingerprint: String
  let wakeupBudgetDay: String
  let wakeupsUsed: Int
  let wakeupBudgetPerDay: Int?
}

struct KnowledgeLedgerCompiledTrigger: Equatable, Sendable {
  let id: String
  let metadata: KnowledgeLedgerTriggerMetadata
  let matchMode: MatchMode
  let entities: [String: [String]]
  let ambiguousAliases: [String: [String]]
  let keywords: [String]
  let regexes: [NSRegularExpression]
  let apps: [String]
  let windows: [String]
  let time: TimeCondition?
  let calendar: CalendarCondition?
  let embedding: EmbeddingCondition?
  let action: KnowledgeLedgerTriggerAction?
  let snoozedUntil: Date?

  enum MatchMode: String, Equatable, Sendable {
    case all
    case any
  }

  struct TimeCondition: Equatable, Sendable {
    let weekdays: [Int]
    let start: Int
    let end: Int
    let timezone: TimeZone
  }

  struct CalendarCondition: Equatable, Sendable {
    let eventKeywords: [String]
    let eventTypes: [String]
  }

  struct EmbeddingCondition: Equatable, Sendable {
    let prototypeID: String
    let prototypeRevision: String
    let modelID: String
    let modelVersion: String
    let language: String
    let minSimilarity: Double
  }

  static func == (lhs: Self, rhs: Self) -> Bool {
    lhs.id == rhs.id
      && lhs.metadata == rhs.metadata
      && lhs.matchMode == rhs.matchMode
      && lhs.entities == rhs.entities
      && lhs.ambiguousAliases == rhs.ambiguousAliases
      && lhs.keywords == rhs.keywords
      && lhs.regexes.map(\.pattern) == rhs.regexes.map(\.pattern)
      && lhs.apps == rhs.apps
      && lhs.windows == rhs.windows
      && lhs.time == rhs.time
      && lhs.calendar == rhs.calendar
      && lhs.embedding == rhs.embedding
      && lhs.action == rhs.action
      && lhs.snoozedUntil == rhs.snoozedUntil
  }
}

struct KnowledgeLedgerTriggerEvaluator {
  private enum ConditionResult: Equatable {
    case matched
    case failed
    case missing
  }

  /// Evaluate one observation without mutating any state.  The caller owns
  /// `wakeupsUsed`; returning the next count keeps double-runs deterministic
  /// and avoids introducing a second persistence authority on the client.
  static func evaluate(
    _ trigger: KnowledgeLedgerCompiledTrigger,
    observation: KnowledgeLedgerTriggerObservation,
    day: String,
    wakeupsUsed: Int = 0,
    embeddingEvaluationEnabled: Bool = true,
    embeddingTriageSimilarity: Double? = nil
  ) -> KnowledgeLedgerTriggerDecision {
    let text = normalize(observation.text)
    var results: [String: ConditionResult] = [:]
    func record(_ key: String, _ value: Bool?) {
      switch value {
      case .some(let matched): results[key] = matched ? .matched : .failed
      case .none: results[key] = .missing
      }
    }

    for entity in trigger.entities.keys.sorted() {
      let aliases = trigger.entities[entity] ?? []
      let matched = aliases.filter { alias in
        observation.entityLabels.contains(alias) || containsTerm(text, alias)
      }
      record("entity:\(entity)", matched.contains { trigger.ambiguousAliases[$0] != nil } ? nil : !matched.isEmpty)
    }
    if !trigger.keywords.isEmpty {
      record("keywords", trigger.keywords.contains { containsTerm(text, $0) })
    }
    if !trigger.regexes.isEmpty {
      let range = NSRange(location: 0, length: observation.text.utf16.count)
      record("regex", trigger.regexes.contains { $0.firstMatch(in: observation.text, range: range) != nil })
    }
    if !trigger.apps.isEmpty {
      record("app", observation.appName.map { trigger.apps.contains(normalize($0)) })
    }
    if !trigger.windows.isEmpty {
      let window = normalize(observation.windowTitle ?? "")
      record("window", window.isEmpty ? false : trigger.windows.contains { window.contains($0) })
    }
    if let time = trigger.time {
      record("time", timeMatches(time, observation.occurredAt))
    }
    if let calendar = trigger.calendar {
      record("calendar", calendarMatches(calendar, observation.calendarEvents))
    }
    if let embedding = trigger.embedding {
      if !embeddingEvaluationEnabled {
        // Disabled scorer policy is a deterministic no-match, never ambiguity
        // and never implicit permission for a model call.
        record("embedding:\(embedding.prototypeID)", false)
      } else if let score = observation.embeddingScores[embedding.prototypeID] {
        if score >= embedding.minSimilarity {
          record("embedding:\(embedding.prototypeID)", true)
        } else if let embeddingTriageSimilarity, score >= embeddingTriageSimilarity {
          record("embedding:\(embedding.prototypeID)", nil)
        } else {
          record("embedding:\(embedding.prototypeID)", false)
        }
      } else {
        record("embedding:\(embedding.prototypeID)", nil)
      }
    }

    let matched = results.keys.sorted().filter { results[$0] == .matched }
    let missing = results.keys.sorted().filter { results[$0] == .missing }
    let hasFalse = results.values.contains { $0 == .failed }
    let conditionStatus: KnowledgeLedgerTriggerDecisionStatus
    let conditionReason: String
    switch trigger.matchMode {
    case .all:
      if hasFalse {
        conditionStatus = .noMatch
        conditionReason = "condition_not_satisfied"
      } else if !missing.isEmpty {
        conditionStatus = .ambiguous
        conditionReason = "insufficient_or_ambiguous_context"
      } else {
        conditionStatus = .match
        conditionReason = "all_conditions_satisfied"
      }
    case .any:
      if !matched.isEmpty {
        conditionStatus = .match
        conditionReason = "one_condition_satisfied"
      } else if !missing.isEmpty {
        conditionStatus = .ambiguous
        conditionReason = "insufficient_or_ambiguous_context"
      } else {
        conditionStatus = .noMatch
        conditionReason = "no_condition_satisfied"
      }
    }

    // The project has not ratified a default trigger budget. Preserve and
    // enforce an explicit row value when present; otherwise report counting
    // state without inventing policy.
    let budget = trigger.metadata.wakeupBudgetPerDay
    let safeUsed = max(0, wakeupsUsed)
    let budgetExhausted = conditionStatus == .match && budget.map { safeUsed >= $0 } == true
    let status = budgetExhausted ? .noMatch : conditionStatus
    let reason = budgetExhausted ? "wakeup_budget_exhausted" : conditionReason
    let nextUsed = conditionStatus == .match && !budgetExhausted ? safeUsed + 1 : safeUsed
    _ = day  // The caller's key is intentionally outside this pure evaluator.
    return KnowledgeLedgerTriggerDecision(
      status: status,
      reason: reason,
      matchedConditions: matched,
      missingConditions: missing,
      matchedFraction: results.isEmpty ? 0 : Double(matched.count) / Double(results.count),
      observationFingerprint: observation.fingerprint,
      wakeupBudgetDay: day,
      wakeupsUsed: nextUsed,
      wakeupBudgetPerDay: budget
    )
  }

  private static func normalize(_ value: String) -> String {
    value.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ").lowercased()
  }

  private static func containsTerm(_ text: String, _ term: String) -> Bool {
    guard !term.isEmpty else { return false }
    var searchStart = text.startIndex
    while searchStart < text.endIndex,
      let range = text.range(
        of: term,
        options: [.caseInsensitive],
        range: searchStart..<text.endIndex
      )
    {
      let beforeIsWord = range.lowerBound > text.startIndex && isWord(text[text.index(before: range.lowerBound)])
      let afterIsWord = range.upperBound < text.endIndex && isWord(text[range.upperBound])
      if !beforeIsWord && !afterIsWord { return true }
      searchStart = range.upperBound
    }
    return false
  }

  private static func isWord(_ character: Character) -> Bool {
    character.isLetter || character.isNumber || character == "_"
  }

  private static func timeMatches(_ condition: KnowledgeLedgerCompiledTrigger.TimeCondition, _ date: Date?) -> Bool? {
    guard let date else { return nil }
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = condition.timezone
    let components = calendar.dateComponents([.weekday, .hour, .minute, .second], from: date)
    // Calendar weekday is Sunday=1; the ledger contract is Monday=0.
    let isoWeekday = ((components.weekday ?? 1) + 5) % 7
    if !condition.weekdays.isEmpty && !condition.weekdays.contains(isoWeekday) { return false }
    let seconds = (components.hour ?? 0) * 3_600 + (components.minute ?? 0) * 60 + (components.second ?? 0)
    return condition.start <= condition.end
      ? seconds >= condition.start && seconds <= condition.end
      : seconds >= condition.start || seconds <= condition.end
  }

  private static func calendarMatches(
    _ condition: KnowledgeLedgerCompiledTrigger.CalendarCondition,
    _ events: [KnowledgeLedgerTriggerCalendarEvent]
  ) -> Bool? {
    guard !events.isEmpty else { return nil }
    return events.contains { event in
      let title = normalize(event.title)
      let eventType = normalize(event.eventType)
      return condition.eventKeywords.contains { containsTerm(title, $0) }
        || condition.eventTypes.contains(eventType)
    }
  }
}

enum KnowledgeLedgerTriggerCompiler {
  static let maxConditionKeys = 12
  static let maxTermCharacters = 80
  static let maxKeywords = 32
  static let maxRegexes = 8
  static let maxApps = 16
  static let maxWindows = 16

  static func compile(_ row: KnowledgeLedgerTriggerRow, snoozedUntil: Date? = nil) -> Result<
    KnowledgeLedgerCompiledTrigger, KnowledgeLedgerTriggerCompileFailure
  > {
    guard row.ledgerSchemaVersion == KnowledgeLedgerTriggerRow.schemaVersion else {
      return .failure(.unsupportedSchema(row.ledgerSchemaVersion))
    }
    guard row.kind == "trigger", row.subjectScope == "primary_user", row.intentBacked, row.isOpen else {
      return .failure(.closedRow)
    }
    let id = row.id.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !id.isEmpty, id.count <= 128 else { return .failure(.malformed("trigger id is invalid")) }
    guard let metadata = metadata(for: row) else { return .failure(.malformed("trigger metadata is invalid")) }
    do {
      try StrictJSONKeyValidator.validate(row.triggerConditionJSON)
      let payload = try JSONDecoder().decode(ConditionPayload.self, from: row.triggerConditionJSON)
      let compiled = try compile(payload: payload, rowID: id, metadata: metadata, snoozedUntil: snoozedUntil)
      return .success(compiled)
    } catch let failure as KnowledgeLedgerTriggerCompileFailure {
      return .failure(failure)
    } catch {
      return .failure(.malformed("trigger condition is malformed"))
    }
  }

  private static func metadata(for row: KnowledgeLedgerTriggerRow) -> KnowledgeLedgerTriggerMetadata? {
    if let modelID = row.modelID,
      modelID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || modelID.count > maxTermCharacters
    {
      return nil
    }
    if let modelVersion = row.modelVersion,
      modelVersion.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || modelVersion.count > maxTermCharacters
    {
      return nil
    }
    if let threshold = row.threshold, !threshold.isFinite || !(0...1).contains(threshold) { return nil }
    if let budget = row.wakeupBudgetPerDay, !(0...1000).contains(budget) { return nil }
    return KnowledgeLedgerTriggerMetadata(
      modelID: row.modelID,
      modelVersion: row.modelVersion,
      threshold: row.threshold,
      wakeupBudgetPerDay: row.wakeupBudgetPerDay
    )
  }

  private static func compile(
    payload: ConditionPayload,
    rowID: String,
    metadata: KnowledgeLedgerTriggerMetadata,
    snoozedUntil: Date?
  ) throws -> KnowledgeLedgerCompiledTrigger {
    guard payload.schemaVersion == "jit_trigger.v1" else {
      throw KnowledgeLedgerTriggerCompileFailure.unsupportedSchema(payload.schemaVersion)
    }
    guard let mode = KnowledgeLedgerCompiledTrigger.MatchMode(rawValue: payload.matchMode) else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("match_mode is invalid")
    }
    guard payload.entityAliases.count <= maxConditionKeys,
      payload.keywords.count <= maxKeywords,
      payload.regex.count <= maxRegexes,
      payload.apps.count <= maxApps,
      payload.windows.count <= maxWindows
    else { throw KnowledgeLedgerTriggerCompileFailure.malformed("trigger bounds exceeded") }

    let entities = try normalizedEntities(payload.entityAliases)
    let keywords = try normalizedTerms(payload.keywords)
    let apps = try normalizedTerms(payload.apps)
    let windows = try normalizedTerms(payload.windows)
    let regexes = try payload.regex.map { pattern -> NSRegularExpression in
      guard pattern.count <= 160, !unsafeRegex(pattern) else {
        throw KnowledgeLedgerTriggerCompileFailure.malformed("unsafe regex")
      }
      guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else {
        throw KnowledgeLedgerTriggerCompileFailure.malformed("invalid regex")
      }
      return regex
    }.sorted { $0.pattern < $1.pattern }

    let conditionCount =
      entities.count + (keywords.isEmpty ? 0 : 1) + (regexes.isEmpty ? 0 : 1)
      + (apps.isEmpty ? 0 : 1) + (windows.isEmpty ? 0 : 1)
      + (payload.time == nil ? 0 : 1) + (payload.calendar == nil ? 0 : 1) + (payload.embedding == nil ? 0 : 1)
    guard conditionCount > 0, conditionCount <= maxConditionKeys else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("trigger must contain 1..12 conditions")
    }

    let ambiguous = ambiguousAliases(entities)
    let time = try payload.time.map { try KnowledgeLedgerCompiledTrigger.TimeCondition($0) }
    let calendar = try payload.calendar.map { try KnowledgeLedgerCompiledTrigger.CalendarCondition($0) }
    let embedding = try payload.embedding.map { try KnowledgeLedgerCompiledTrigger.EmbeddingCondition($0) }
    return KnowledgeLedgerCompiledTrigger(
      id: rowID,
      metadata: metadata,
      matchMode: mode,
      entities: entities,
      ambiguousAliases: ambiguous,
      keywords: keywords,
      regexes: regexes,
      apps: apps,
      windows: windows,
      time: time,
      calendar: calendar,
      embedding: embedding,
      action: payload.action,
      snoozedUntil: snoozedUntil
    )
  }

  private static func normalizedEntities(_ raw: [String: [String]]) throws -> [String: [String]] {
    var result: [String: [String]] = [:]
    for (rawEntity, rawAliases) in raw {
      let entity = normalize(rawEntity)
      guard !entity.isEmpty, rawAliases.count <= 16 else {
        throw KnowledgeLedgerTriggerCompileFailure.malformed("entity aliases invalid")
      }
      let aliases = try normalizedTerms(rawAliases)
      guard !aliases.isEmpty else { throw KnowledgeLedgerTriggerCompileFailure.malformed("entity aliases empty") }
      result[entity] = aliases
    }
    return result
  }

  private static func normalizedTerms(_ raw: [String]) throws -> [String] {
    let terms = raw.map(normalize).filter { !$0.isEmpty }
    guard terms.allSatisfy({ $0.count <= maxTermCharacters }) else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("trigger term too long")
    }
    return Array(Set(terms)).sorted()
  }

  private static func ambiguousAliases(_ entities: [String: [String]]) -> [String: [String]] {
    var owners: [String: [String]] = [:]
    for entity in entities.keys.sorted() {
      for alias in entities[entity] ?? [] { owners[alias, default: []].append(entity) }
    }
    return owners.filter { $0.value.count > 1 }.mapValues { $0.sorted() }
  }

  private static func normalize(_ value: String) -> String {
    value.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ").lowercased()
  }

  private static func unsafeRegex(_ pattern: String) -> Bool {
    pattern.range(of: #"\\[1-9]|\(\?(?:[=!<]|P=)"#, options: .regularExpression) != nil
      || pattern.range(of: #"\([^)]*(?:\*|\+|\{\d+(?:,\d*)?\})[^)]*\)(?:\*|\+|\{)"#, options: .regularExpression) != nil
  }
}

/// JSONDecoder exposes a set of keyed fields, so duplicate object keys have
/// already disappeared by the time a Decodable initializer runs. Trigger
/// conditions are an authority boundary: reject duplicates in every nested
/// object before decoding instead of accepting an implementation-defined
/// first/last value.
private struct StrictJSONKeyValidator {
  private enum ValidationError: Error {
    case malformed
    case duplicateKey
  }

  private let bytes: [UInt8]
  private var index = 0

  static func validate(_ data: Data) throws {
    var parser = StrictJSONKeyValidator(bytes: Array(data))
    try parser.parseValue()
    parser.skipWhitespace()
    guard parser.index == parser.bytes.count else { throw ValidationError.malformed }
  }

  private mutating func parseValue() throws {
    skipWhitespace()
    guard let byte = current else { throw ValidationError.malformed }
    switch byte {
    case UInt8(ascii: "{"):
      try parseObject()
    case UInt8(ascii: "["):
      try parseArray()
    case UInt8(ascii: "\""):
      _ = try parseString()
    default:
      try parsePrimitive()
    }
  }

  private mutating func parseObject() throws {
    try consume(UInt8(ascii: "{"))
    skipWhitespace()
    if consumeIfPresent(UInt8(ascii: "}")) { return }
    var keys = Set<String>()
    while true {
      skipWhitespace()
      guard current == UInt8(ascii: "\"") else { throw ValidationError.malformed }
      let key = try parseString()
      guard keys.insert(key).inserted else { throw ValidationError.duplicateKey }
      skipWhitespace()
      try consume(UInt8(ascii: ":"))
      try parseValue()
      skipWhitespace()
      if consumeIfPresent(UInt8(ascii: "}")) { return }
      try consume(UInt8(ascii: ","))
    }
  }

  private mutating func parseArray() throws {
    try consume(UInt8(ascii: "["))
    skipWhitespace()
    if consumeIfPresent(UInt8(ascii: "]")) { return }
    while true {
      try parseValue()
      skipWhitespace()
      if consumeIfPresent(UInt8(ascii: "]")) { return }
      try consume(UInt8(ascii: ","))
    }
  }

  private mutating func parseString() throws -> String {
    let start = index
    try consume(UInt8(ascii: "\""))
    var escaped = false
    while let byte = current {
      index += 1
      if escaped {
        escaped = false
      } else if byte == UInt8(ascii: "\\") {
        escaped = true
      } else if byte == UInt8(ascii: "\"") {
        let token = Data(bytes[start..<index])
        guard let value = try? JSONDecoder().decode(String.self, from: token) else {
          throw ValidationError.malformed
        }
        return value
      } else if byte < 0x20 {
        throw ValidationError.malformed
      }
    }
    throw ValidationError.malformed
  }

  private mutating func parsePrimitive() throws {
    let start = index
    while let byte = current,
      !Self.whitespace.contains(byte),
      byte != UInt8(ascii: ","),
      byte != UInt8(ascii: "]"),
      byte != UInt8(ascii: "}")
    {
      index += 1
    }
    guard index > start else { throw ValidationError.malformed }
  }

  private mutating func skipWhitespace() {
    while let byte = current, Self.whitespace.contains(byte) { index += 1 }
  }

  private mutating func consume(_ expected: UInt8) throws {
    guard consumeIfPresent(expected) else { throw ValidationError.malformed }
  }

  private mutating func consumeIfPresent(_ expected: UInt8) -> Bool {
    guard current == expected else { return false }
    index += 1
    return true
  }

  private var current: UInt8? {
    index < bytes.count ? bytes[index] : nil
  }

  private static let whitespace: Set<UInt8> = [0x20, 0x09, 0x0A, 0x0D]
}

private struct ConditionPayload: Decodable {
  let schemaVersion: String
  let matchMode: String
  let entityAliases: [String: [String]]
  let keywords: [String]
  let regex: [String]
  let apps: [String]
  let windows: [String]
  let time: TimePayload?
  let calendar: CalendarPayload?
  let embedding: EmbeddingPayload?
  let action: KnowledgeLedgerTriggerAction?

  enum CodingKeys: String, CodingKey, CaseIterable {
    case schemaVersion = "schema_version"
    case matchMode = "match_mode"
    case entityAliases = "entity_aliases"
    case keywords
    case regex
    case apps
    case windows
    case time
    case calendar
    case embedding
    case action
  }

  init(from decoder: Decoder) throws {
    let rawContainer = try decoder.container(keyedBy: AnyCodingKey.self)
    let allowed = Set(CodingKeys.allCases.map(\.stringValue))
    guard rawContainer.allKeys.allSatisfy({ allowed.contains($0.stringValue) }) else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("unknown trigger condition key")
    }
    let container = try decoder.container(keyedBy: CodingKeys.self)
    if container.allKeys.count != Set(container.allKeys.map(\.stringValue)).count {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("duplicate condition keys")
    }
    schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? "jit_trigger.v1"
    matchMode = try container.decodeIfPresent(String.self, forKey: .matchMode) ?? "all"
    entityAliases = try container.decodeIfPresent([String: [String]].self, forKey: .entityAliases) ?? [:]
    keywords = try container.decodeIfPresent([String].self, forKey: .keywords) ?? []
    regex = try container.decodeIfPresent([String].self, forKey: .regex) ?? []
    apps = try container.decodeIfPresent([String].self, forKey: .apps) ?? []
    windows = try container.decodeIfPresent([String].self, forKey: .windows) ?? []
    time = try container.decodeIfPresent(TimePayload.self, forKey: .time)
    calendar = try container.decodeIfPresent(CalendarPayload.self, forKey: .calendar)
    embedding = try container.decodeIfPresent(EmbeddingPayload.self, forKey: .embedding)
    action = try container.decodeIfPresent(KnowledgeLedgerTriggerAction.self, forKey: .action)
    if let action, !action.isValid {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("trigger action is invalid")
    }
  }
}

private struct TimePayload: Decodable {
  let weekdays: [Int]
  let start: String
  let end: String
  let timezone: String

  enum CodingKeys: String, CodingKey, CaseIterable { case weekdays, start, end, timezone }

  init(from decoder: Decoder) throws {
    let rawContainer = try decoder.container(keyedBy: AnyCodingKey.self)
    let allowed = Set(CodingKeys.allCases.map(\.stringValue))
    guard rawContainer.allKeys.allSatisfy({ allowed.contains($0.stringValue) }) else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("unknown time condition key")
    }
    let container = try decoder.container(keyedBy: CodingKeys.self)
    weekdays = try container.decodeIfPresent([Int].self, forKey: .weekdays) ?? []
    start = try container.decode(String.self, forKey: .start)
    end = try container.decode(String.self, forKey: .end)
    timezone = try container.decodeIfPresent(String.self, forKey: .timezone) ?? "UTC"
  }
}

private struct CalendarPayload: Decodable {
  let eventKeywords: [String]
  let eventTypes: [String]

  enum CodingKeys: String, CodingKey, CaseIterable {
    case eventKeywords = "event_keywords"
    case eventTypes = "event_types"
  }

  init(from decoder: Decoder) throws {
    let rawContainer = try decoder.container(keyedBy: AnyCodingKey.self)
    let allowed = Set(CodingKeys.allCases.map(\.stringValue))
    guard rawContainer.allKeys.allSatisfy({ allowed.contains($0.stringValue) }) else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("unknown calendar condition key")
    }
    let container = try decoder.container(keyedBy: CodingKeys.self)
    eventKeywords = try container.decodeIfPresent([String].self, forKey: .eventKeywords) ?? []
    eventTypes = try container.decodeIfPresent([String].self, forKey: .eventTypes) ?? []
  }
}

private struct EmbeddingPayload: Decodable {
  let prototypeID: String
  let prototypeRevision: String
  let modelID: String
  let modelVersion: String
  let language: String
  let minSimilarity: Double

  enum CodingKeys: String, CodingKey, CaseIterable {
    case prototypeID = "prototype_id"
    case prototypeRevision = "prototype_revision"
    case modelID = "model_id"
    case modelVersion = "model_version"
    case language
    case minSimilarity = "min_similarity"
  }

  init(from decoder: Decoder) throws {
    let rawContainer = try decoder.container(keyedBy: AnyCodingKey.self)
    let allowed = Set(CodingKeys.allCases.map(\.stringValue))
    guard rawContainer.allKeys.allSatisfy({ allowed.contains($0.stringValue) }) else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("unknown embedding condition key")
    }
    let container = try decoder.container(keyedBy: CodingKeys.self)
    prototypeID = try container.decode(String.self, forKey: .prototypeID)
    prototypeRevision = try container.decode(String.self, forKey: .prototypeRevision)
    modelID = try container.decode(String.self, forKey: .modelID)
    modelVersion = try container.decode(String.self, forKey: .modelVersion)
    language = try container.decode(String.self, forKey: .language)
    minSimilarity = try container.decodeIfPresent(Double.self, forKey: .minSimilarity) ?? 0.82
  }
}

private struct AnyCodingKey: CodingKey {
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

extension KnowledgeLedgerCompiledTrigger.TimeCondition {
  fileprivate init(_ payload: TimePayload) throws {
    guard payload.weekdays.allSatisfy({ (0...6).contains($0) }), let timezone = TimeZone(identifier: payload.timezone)
    else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("time condition invalid")
    }
    let start = try Self.seconds(payload.start)
    let end = try Self.seconds(payload.end)
    self.init(weekdays: Array(Set(payload.weekdays)).sorted(), start: start, end: end, timezone: timezone)
  }

  private static func seconds(_ value: String) throws -> Int {
    let parts = value.split(separator: ":").compactMap { Int($0) }
    guard (2...3).contains(parts.count), parts[0] >= 0, parts[0] <= 23, parts[1] >= 0, parts[1] <= 59,
      parts.count == 2 || (parts[2] >= 0 && parts[2] <= 59)
    else { throw KnowledgeLedgerTriggerCompileFailure.malformed("time value invalid") }
    return parts[0] * 3_600 + parts[1] * 60 + (parts.count == 3 ? parts[2] : 0)
  }
}

extension KnowledgeLedgerCompiledTrigger.CalendarCondition {
  fileprivate init(_ payload: CalendarPayload) throws {
    let keywords = try KnowledgeLedgerTriggerCompiler.normalizedTermsForNested(payload.eventKeywords)
    let eventTypes = try KnowledgeLedgerTriggerCompiler.normalizedTermsForNested(payload.eventTypes)
    guard !keywords.isEmpty || !eventTypes.isEmpty else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("calendar condition empty")
    }
    guard keywords.count + eventTypes.count <= 32 else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("calendar condition too large")
    }
    self.init(eventKeywords: keywords, eventTypes: eventTypes)
  }
}

extension KnowledgeLedgerCompiledTrigger.EmbeddingCondition {
  fileprivate init(_ payload: EmbeddingPayload) throws {
    let prototypeID = payload.prototypeID.trimmingCharacters(in: .whitespacesAndNewlines)
    let attestations = [
      payload.prototypeRevision, payload.modelID, payload.modelVersion, payload.language,
    ].map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
    guard !prototypeID.isEmpty, prototypeID.count <= 80,
      attestations.allSatisfy({ !$0.isEmpty && $0.count <= 80 }),
      payload.minSimilarity == 0.82
    else { throw KnowledgeLedgerTriggerCompileFailure.malformed("embedding condition invalid") }
    self.init(
      prototypeID: prototypeID, prototypeRevision: attestations[0], modelID: attestations[1],
      modelVersion: attestations[2], language: attestations[3],
      minSimilarity: payload.minSimilarity)
  }
}

extension KnowledgeLedgerTriggerCompiler {
  fileprivate static func normalizedTermsForNested(_ raw: [String]) throws -> [String] {
    let normalized = raw.map { $0.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ").lowercased() }
      .filter { !$0.isEmpty }
    guard normalized.allSatisfy({ $0.count <= maxTermCharacters }) else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("nested trigger term too long")
    }
    return Array(Set(normalized)).sorted()
  }
}
