import Foundation

/// Activation authority for the dark local trigger runtime.
///
/// This value is deliberately caller-supplied and pure. The eventual runtime
/// owner must derive it from the server rollout decision and the current
/// ``RuntimeOwnerIdentity`` lease; this evaluator never reads PostHog, starts a
/// timer, or turns a bounded local mirror into authority by itself.
struct KnowledgeLedgerTriggerRuntimeAuthority: Equatable, Sendable {
  enum Mode: String, Equatable, Sendable {
    case disabled
    case enabled
    case compatibilityRollback = "compatibility_rollback"
  }

  let mode: Mode
  let killSwitchEnabled: Bool
  let ownerID: String?
  let accountGeneration: Int?
  let snapshotOwnerID: String?
  let snapshotAccountGeneration: Int?
  let snapshotIsAuthoritative: Bool
  let authorizationIsCurrent: Bool

  static let defaultOff = KnowledgeLedgerTriggerRuntimeAuthority(
    mode: .disabled,
    killSwitchEnabled: false,
    ownerID: nil,
    accountGeneration: nil,
    snapshotOwnerID: nil,
    snapshotAccountGeneration: nil,
    snapshotIsAuthoritative: false,
    authorizationIsCurrent: false
  )
}

/// Identifies the only local embedding projection whose scores may satisfy an
/// embedding trigger. It carries no text or vector values.
struct KnowledgeLedgerTriggerEmbeddingContract: Equatable, Sendable {
  static let maxIdentifierCharacters = KnowledgeLedgerTriggerCompiler.maxTermCharacters

  let modelID: String
  let modelVersion: String
  let language: String
  let prototypeRevision: String

  init?(
    modelID: String, modelVersion: String, language: String = "und",
    prototypeRevision: String = "unknown"
  ) {
    let normalizedModelID = modelID.trimmingCharacters(in: .whitespacesAndNewlines)
    let normalizedModelVersion = modelVersion.trimmingCharacters(in: .whitespacesAndNewlines)
    let normalizedLanguage = language.trimmingCharacters(in: .whitespacesAndNewlines)
    let normalizedPrototypeRevision = prototypeRevision.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalizedModelID.isEmpty, !normalizedModelVersion.isEmpty,
      normalizedModelID.count <= Self.maxIdentifierCharacters,
      normalizedModelVersion.count <= Self.maxIdentifierCharacters,
      !normalizedLanguage.isEmpty, normalizedLanguage.count <= Self.maxIdentifierCharacters,
      !normalizedPrototypeRevision.isEmpty,
      normalizedPrototypeRevision.count <= Self.maxIdentifierCharacters
    else { return nil }
    self.modelID = normalizedModelID
    self.modelVersion = normalizedModelVersion
    self.language = normalizedLanguage
    self.prototypeRevision = normalizedPrototypeRevision
  }
}

enum KnowledgeLedgerTriggerRuntimeRejection: Equatable, Sendable {
  case staleAuthorization
  case missingOwner
  case invalidAccountGeneration
  case snapshotOwnerMismatch
  case snapshotGenerationMismatch
  case nonAuthoritativeSnapshot
  case invalidDay
  case watchlistBoundsExceeded
  case invalidWakeupCounter(String)
  case duplicateTriggerID(String)
}

enum KnowledgeLedgerTriggerRuntimeEntryRejection: Equatable, Sendable {
  case incompleteEmbeddingContract
  case embeddingModelMismatch
  case embeddingVersionMismatch
  case embeddingThresholdMismatch
}

struct KnowledgeLedgerTriggerRuntimeEntryResult: Equatable, Sendable {
  let triggerID: String
  let decision: KnowledgeLedgerTriggerDecision
}

struct KnowledgeLedgerTriggerRuntimeRejectedEntry: Equatable, Sendable {
  let triggerID: String
  let reason: KnowledgeLedgerTriggerRuntimeEntryRejection
}

/// The next bounded lane after deterministic local evaluation.
///
/// This is a routing decision, not execution authority. In particular,
/// `boundedPlannedTriage` does not call a model and `plannedTrigger` does not
/// start a full agent turn. Existing cost/quota and notification authority must
/// still admit those downstream operations.
enum KnowledgeLedgerTriggerRuntimeNextLane: String, Equatable, Sendable {
  case none
  case plannedTrigger = "planned_trigger"
  case boundedPlannedTriage = "bounded_planned_triage"
  case ambientFallback = "ambient_fallback"
}

struct KnowledgeLedgerTriggerRuntimeResult: Equatable, Sendable {
  enum Status: String, Equatable, Sendable {
    case inactive
    case rejected
    case evaluated
  }

  let status: Status
  let rejection: KnowledgeLedgerTriggerRuntimeRejection?
  let nextLane: KnowledgeLedgerTriggerRuntimeNextLane
  let matches: [KnowledgeLedgerTriggerRuntimeEntryResult]
  let ambiguous: [KnowledgeLedgerTriggerRuntimeEntryResult]
  let noMatches: [KnowledgeLedgerTriggerRuntimeEntryResult]
  let rejectedEntries: [KnowledgeLedgerTriggerRuntimeRejectedEntry]
  let projectionQuarantine: [KnowledgeLedgerTriggerWatchlistProjection.QuarantinedRow]
}

/// Compiles the authoritative local projection into one deterministic runtime
/// decision. It performs no I/O, persistence, scheduling, telemetry, model
/// inference, notification, or full-agent wakeup.
enum KnowledgeLedgerTriggerWatchlistRuntime {
  // Must remain aligned with backend/utils/memory/jit_trigger_snapshot.py.
  // A complete server snapshot may contain this many active triggers.
  static let maxWatchlistEntries = 500
  static let maxWakeupCounterCandidates = 500

  static func evaluate(
    projection: KnowledgeLedgerTriggerWatchlistProjection,
    observation: KnowledgeLedgerTriggerObservation,
    day: String,
    authority: KnowledgeLedgerTriggerRuntimeAuthority = .defaultOff,
    embeddingContract: KnowledgeLedgerTriggerEmbeddingContract? = nil,
    embeddingPolicy: JITTriggerEmbeddingPolicy? = nil,
    wakeupsUsedByTrigger: [String: Int] = [:]
  ) -> KnowledgeLedgerTriggerRuntimeResult {
    // Rollback authority must win before inspecting any new-runtime state.
    // A corrupt or oversized dark snapshot is irrelevant when the JIT lane is
    // disabled and must never strand the established ambient fallback.
    if authority.mode != .enabled || authority.killSwitchEnabled {
      return result(
        status: .inactive,
        nextLane: .ambientFallback,
        projection: projection,
        preserveQuarantine: false)
    }
    guard projection.entries.count <= maxWatchlistEntries,
      projection.quarantined.count <= maxWatchlistEntries,
      projection.entries.count + projection.quarantined.count <= maxWatchlistEntries,
      wakeupsUsedByTrigger.count <= maxWakeupCounterCandidates
    else {
      return rejected(.watchlistBoundsExceeded, projection: projection, preserveQuarantine: false)
    }
    for (triggerID, used) in wakeupsUsedByTrigger.sorted(by: { $0.key < $1.key })
    where used < 0 || used == Int.max {
      return rejected(.invalidWakeupCounter(triggerID), projection: projection, preserveQuarantine: false)
    }
    guard authority.authorizationIsCurrent else {
      return rejected(.staleAuthorization, projection: projection)
    }
    guard let ownerID = boundedOwnerID(authority.ownerID), boundedOwnerID(authority.snapshotOwnerID) != nil else {
      return rejected(.missingOwner, projection: projection)
    }
    guard let accountGeneration = authority.accountGeneration, accountGeneration >= 0,
      let snapshotGeneration = authority.snapshotAccountGeneration, snapshotGeneration >= 0
    else {
      return rejected(.invalidAccountGeneration, projection: projection)
    }
    guard ownerID == authority.snapshotOwnerID?.trimmingCharacters(in: .whitespacesAndNewlines) else {
      return rejected(.snapshotOwnerMismatch, projection: projection)
    }
    guard accountGeneration == snapshotGeneration else {
      return rejected(.snapshotGenerationMismatch, projection: projection)
    }
    guard authority.snapshotIsAuthoritative else {
      return rejected(.nonAuthoritativeSnapshot, projection: projection)
    }
    guard isValidDay(day) else { return rejected(.invalidDay, projection: projection) }
    let sortedEntries = projection.entries.sorted { $0.id < $1.id }
    var seenIDs = Set<String>()
    for entry in sortedEntries where !seenIDs.insert(entry.id).inserted {
      return rejected(.duplicateTriggerID(entry.id), projection: projection)
    }

    var matches: [KnowledgeLedgerTriggerRuntimeEntryResult] = []
    var ambiguous: [KnowledgeLedgerTriggerRuntimeEntryResult] = []
    var noMatches: [KnowledgeLedgerTriggerRuntimeEntryResult] = []
    var rejectedEntries: [KnowledgeLedgerTriggerRuntimeRejectedEntry] = []
    let eligibilityNow = observation.occurredAt ?? Date()
    for entry in sortedEntries {
      // Snooze is a server-owned absolute instant carried by the authoritative
      // snapshot. Keep this eligibility fence here as well as at paid claim so
      // every watchlist caller suppresses the standing trigger before expiry.
      if let snoozedUntil = entry.snoozedUntil,
        eligibilityNow < snoozedUntil
      {
        continue
      }
      if embeddingPolicy?.enabled != false,
        let rejection = embeddingRejection(for: entry, contract: embeddingContract)
      {
        rejectedEntries.append(.init(triggerID: entry.id, reason: rejection))
        continue
      }
      let decision = KnowledgeLedgerTriggerEvaluator.evaluate(
        entry,
        observation: observation,
        day: day,
        wakeupsUsed: max(0, wakeupsUsedByTrigger[entry.id] ?? 0),
        embeddingEvaluationEnabled: embeddingPolicy?.enabled != false,
        embeddingTriageSimilarity: embeddingPolicy?.enabled == true
          ? embeddingPolicy?.triageSimilarity : nil
      )
      let item = KnowledgeLedgerTriggerRuntimeEntryResult(triggerID: entry.id, decision: decision)
      switch decision.status {
      case .match: matches.append(item)
      case .ambiguous: ambiguous.append(item)
      case .noMatch: noMatches.append(item)
      }
    }

    let nextLane: KnowledgeLedgerTriggerRuntimeNextLane
    if !matches.isEmpty {
      nextLane = .plannedTrigger
    } else if !ambiguous.isEmpty {
      nextLane = .boundedPlannedTriage
    } else if !rejectedEntries.isEmpty || !projection.quarantined.isEmpty {
      // Ambient is authorized only after every authoritative planned entry
      // safely proves no-match. An unevaluable or quarantined entry leaves
      // planned authority unresolved and must not purchase another lane.
      nextLane = .none
    } else {
      // A complete watchlist with no match — including a complete *empty*
      // watchlist — hands off to the ambient lane. Owner decision 2026-09-01:
      // suppressing empty watchlists (#12452) left every JIT-admitted account
      // without a standing trigger with zero proactive output, while the
      // legacy director was bypassed. Ambient spend stays bounded by
      // JITAmbientPacingPolicy and the server-authoritative daily budgets.
      nextLane = .ambientFallback
    }
    return KnowledgeLedgerTriggerRuntimeResult(
      status: .evaluated,
      rejection: nil,
      nextLane: nextLane,
      matches: matches,
      ambiguous: ambiguous,
      noMatches: noMatches,
      rejectedEntries: rejectedEntries,
      projectionQuarantine: projection.quarantined
    )
  }

  private static func embeddingRejection(
    for trigger: KnowledgeLedgerCompiledTrigger,
    contract: KnowledgeLedgerTriggerEmbeddingContract?
  ) -> KnowledgeLedgerTriggerRuntimeEntryRejection? {
    guard let embedding = trigger.embedding else { return nil }
    guard let contract
    else { return .incompleteEmbeddingContract }
    guard embedding.modelID == contract.modelID else { return .embeddingModelMismatch }
    guard embedding.modelVersion == contract.modelVersion,
      embedding.language == contract.language,
      embedding.prototypeRevision == contract.prototypeRevision
    else { return .embeddingVersionMismatch }
    guard embedding.minSimilarity == 0.82 else { return .embeddingThresholdMismatch }
    return nil
  }

  private static func boundedOwnerID(_ ownerID: String?) -> String? {
    guard let ownerID else { return nil }
    let normalized = ownerID.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty, normalized.count <= 128 else { return nil }
    return normalized
  }

  private static func isValidDay(_ day: String) -> Bool {
    guard day.count == 10 else { return false }
    let parts = day.split(separator: "-", omittingEmptySubsequences: false)
    guard parts.map(\.count) == [4, 2, 2], parts.allSatisfy({ $0.allSatisfy(\.isNumber) }),
      let year = Int(parts[0]), let month = Int(parts[1]), let dayOfMonth = Int(parts[2])
    else { return false }
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(secondsFromGMT: 0) ?? .gmt
    guard let date = calendar.date(from: DateComponents(year: year, month: month, day: dayOfMonth)) else {
      return false
    }
    let resolved = calendar.dateComponents([.year, .month, .day], from: date)
    return resolved.year == year && resolved.month == month && resolved.day == dayOfMonth
  }

  private static func rejected(
    _ rejection: KnowledgeLedgerTriggerRuntimeRejection,
    projection: KnowledgeLedgerTriggerWatchlistProjection,
    preserveQuarantine: Bool = true
  ) -> KnowledgeLedgerTriggerRuntimeResult {
    result(
      status: .rejected,
      rejection: rejection,
      nextLane: .none,
      projection: projection,
      preserveQuarantine: preserveQuarantine)
  }

  private static func result(
    status: KnowledgeLedgerTriggerRuntimeResult.Status,
    rejection: KnowledgeLedgerTriggerRuntimeRejection? = nil,
    nextLane: KnowledgeLedgerTriggerRuntimeNextLane,
    projection: KnowledgeLedgerTriggerWatchlistProjection,
    preserveQuarantine: Bool = true
  ) -> KnowledgeLedgerTriggerRuntimeResult {
    KnowledgeLedgerTriggerRuntimeResult(
      status: status,
      rejection: rejection,
      nextLane: nextLane,
      matches: [],
      ambiguous: [],
      noMatches: [],
      rejectedEntries: [],
      projectionQuarantine: preserveQuarantine ? projection.quarantined : []
    )
  }
}
