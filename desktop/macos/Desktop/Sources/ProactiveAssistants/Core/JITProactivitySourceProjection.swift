import Darwin
import Foundation

extension AgentRuntimeProcess {
  /// The projection contains prompt bytes, so QA capture refuses to run unless
  /// the exact bundle-scoped runtime state is owner-only. This is a read-only
  /// preflight; normal app state is never chmod'd by the producer.
  static func hasPrivateJITQAStateDirectory(
    bundleIdentifier: String? = Bundle.main.bundleIdentifier,
    stateDirectory: URL? = nil,
    attributesProvider: ((String) -> [FileAttributeKey: Any]?)? = nil,
    requireDatabase: Bool = true
  ) -> Bool {
    guard bundleIdentifier == JITProactivitySourceProjection.qaBundleIdentifier else { return false }
    let directory =
      stateDirectory
      ?? URL(fileURLWithPath: defaultStateDirectory(bundleIdentifier: bundleIdentifier))
    let fileManager = FileManager.default
    guard pathHasNoSymbolicLinkComponent(directory.path),
      let directoryAttributes = attributes(
        atPath: directory.path, provider: attributesProvider),
      directoryAttributes[.type] as? FileAttributeType == .typeDirectory,
      isOwnedByCurrentUser(directoryAttributes),
      ((directoryAttributes[.posixPermissions] as? NSNumber)?.intValue ?? 0) & 0o777 == 0o700
    else { return false }

    let databaseURL = directory.appendingPathComponent("omi-agentd.sqlite3")
    let databasePaths = [
      databaseURL.path,
      databaseURL.path + "-wal",
      databaseURL.path + "-shm",
    ]
    // Before the agent daemon starts, a new QA state may not have a database
    // yet. Still inspect every expected path first so a dangling or target
    // symlink cannot hide behind FileManager.fileExists' follow behavior.
    if requireDatabase && !fileManager.fileExists(atPath: databaseURL.path) { return false }
    return databasePaths.allSatisfy { path in
      guard pathHasNoSymbolicLinkComponent(path) else { return false }
      guard let attributes = attributes(atPath: path, provider: attributesProvider),
        attributes[.type] as? FileAttributeType == .typeRegular
      else {
        // SQLite only creates WAL/SHM files while a write is active. Missing
        // sidecars are therefore private by construction.
        if path == databaseURL.path {
          return !requireDatabase && !fileManager.fileExists(atPath: path)
        }
        return !fileManager.fileExists(atPath: path)
      }
      return isOwnedByCurrentUser(attributes)
        && ((attributes[.posixPermissions] as? NSNumber)?.intValue ?? 0) & 0o777 == 0o600
    }
  }

  private static func attributes(
    atPath path: String,
    provider: ((String) -> [FileAttributeKey: Any]?)?
  ) -> [FileAttributeKey: Any]? {
    if let provider { return provider(path) }
    return try? FileManager.default.attributesOfItem(atPath: path)
  }

  private static func isOwnedByCurrentUser(_ attributes: [FileAttributeKey: Any]) -> Bool {
    guard let ownerAccountID = attributes[.ownerAccountID] as? NSNumber else { return false }
    return ownerAccountID.uint32Value == getuid()
  }

  private static func pathHasNoSymbolicLinkComponent(_ path: String) -> Bool {
    let fileManager = FileManager.default
    // `standardizedFileURL` resolves existing symlinks. That turns the
    // canonical `/private/tmp` spelling back into `/tmp` on macOS and can
    // make a safe physical fixture look like a symlink (or make a symlink
    // alias look physical). Keep the spelling supplied by the caller while
    // walking each component so liveness and aliasing are checked directly.
    var current = URL(fileURLWithPath: path)
    while current.path != "/" {
      if (try? fileManager.destinationOfSymbolicLink(atPath: current.path)) != nil {
        return false
      }
      current.deleteLastPathComponent()
    }
    return true
  }
}

/// Content-free accounting metadata for the actual nano request made during
/// JIT admission. The response body is deliberately absent: the source
/// projection carries the source-owned prompt separately, while durable
/// provider accounting remains joined by request ID downstream.
struct JITProactivityNanoBillingObservation: Equatable, Sendable {
  static let schemaVersion = "omi.jit.proactivity.nano_billing.v1"

  let dispatch: String
  let lane: JITProactivityLane
  let ownerID: String
  let accountGeneration: Int
  let snapshotRevision: String
  let budgetDay: String
  let contextID: String
  let candidateID: String
  let executionID: String?
  let outcome: String
  let operation: String
  let requestID: String?
  let provider: String?
  let providerModel: String?
  let providerResponseID: String?
  let fallbackClass: String?
  let inputTokens: Int?
  let outputTokens: Int?
  let totalTokens: Int?
  let cachedInputTokens: Int?
  let cacheWriteTokens: Int?
  let usageStatus: String
  let costStatus: String
  let estimatedCostMicroUSD: Int?
  let providerAttempts: Int?
  let attemptIDs: [String]

  init(
    dispatch: String,
    lane: JITProactivityLane,
    ownerID: String,
    accountGeneration: Int,
    snapshotRevision: String,
    budgetDay: String,
    contextID: String,
    candidateID: String,
    executionID: String?,
    outcome: String,
    operation: String,
    requestID: String?,
    provider: String?,
    providerModel: String?,
    providerResponseID: String?,
    fallbackClass: String?,
    inputTokens: Int?,
    outputTokens: Int?,
    totalTokens: Int?,
    cachedInputTokens: Int?,
    cacheWriteTokens: Int?,
    usageStatus: String,
    costStatus: String,
    estimatedCostMicroUSD: Int?,
    providerAttempts: Int?,
    attemptIDs: [String]
  ) {
    self.dispatch = dispatch
    self.lane = lane
    self.ownerID = ownerID
    self.accountGeneration = accountGeneration
    self.snapshotRevision = snapshotRevision
    self.budgetDay = budgetDay
    self.contextID = contextID
    self.candidateID = candidateID
    self.executionID = executionID
    self.outcome = outcome
    self.operation = operation
    self.requestID = requestID
    self.provider = provider
    self.providerModel = providerModel
    self.providerResponseID = providerResponseID
    self.fallbackClass = fallbackClass
    self.inputTokens = inputTokens
    self.outputTokens = outputTokens
    self.totalTokens = totalTokens
    self.cachedInputTokens = cachedInputTokens
    self.cacheWriteTokens = cacheWriteTokens
    self.usageStatus = usageStatus
    self.costStatus = costStatus
    self.estimatedCostMicroUSD = estimatedCostMicroUSD
    self.providerAttempts = providerAttempts
    self.attemptIDs = attemptIDs
  }

  static func notDispatched(
    lane: JITProactivityLane,
    ownerID: String,
    accountGeneration: Int,
    snapshotRevision: String,
    budgetDay: String,
    contextID: String,
    candidateID: String,
    executionID: String
  ) -> Self {
    Self(
      dispatch: "not_dispatched", lane: lane, ownerID: ownerID,
      accountGeneration: accountGeneration, snapshotRevision: snapshotRevision,
      budgetDay: budgetDay, contextID: contextID, candidateID: candidateID,
      executionID: executionID, outcome: "not_dispatched",
      operation: ModelQoS.Proactivity.extractionOperation,
      requestID: nil, provider: nil, providerModel: nil, providerResponseID: nil, fallbackClass: nil,
      inputTokens: nil, outputTokens: nil, totalTokens: nil,
      cachedInputTokens: nil, cacheWriteTokens: nil,
      usageStatus: "not_applicable", costStatus: "not_applicable",
      estimatedCostMicroUSD: nil, providerAttempts: 0, attemptIDs: [])
  }

  static func observed(
    lane: JITProactivityLane,
    ownerID: String,
    accountGeneration: Int,
    snapshotRevision: String,
    budgetDay: String,
    contextID: String,
    candidateID: String,
    executionID: String?,
    triage: JITAmbientNanoTriage,
    transport: ProactiveLaneResponseObservation?
  ) -> Self {
    let failure = transport?.failure
    let outcome: String
    switch triage {
    case .approved: outcome = "approved"
    case .rejected: outcome = "rejected"
    case .unknown:
      if failure?.failure == "invalid_structured_output" || failure?.failure == "invalid_response"
        || failure?.failure == "decode"
      {
        outcome = "malformed"
      } else if failure?.failure == "quota_cooldown" {
        outcome = "quota"
      } else if failure != nil {
        outcome = "error"
      } else {
        outcome = "unknown"
      }
    }
    let input = transport?.usage?.inputTokens
    let output = transport?.usage?.outputTokens
    let usageStatus: String
    if input != nil && output != nil {
      usageStatus = "reported"
    } else if input != nil || output != nil {
      usageStatus = "partial"
    } else {
      usageStatus = "unknown"
    }
    return Self(
      dispatch: "observed", lane: lane, ownerID: ownerID,
      accountGeneration: accountGeneration, snapshotRevision: snapshotRevision,
      budgetDay: budgetDay, contextID: contextID, candidateID: candidateID,
      executionID: executionID, outcome: outcome,
      operation: transport?.operation ?? ModelQoS.Proactivity.extractionOperation,
      requestID: boundedIdentity(transport?.requestID),
      provider: boundedIdentity(transport?.provider),
      providerModel: boundedIdentity(transport?.providerModel),
      providerResponseID: boundedIdentity(transport?.providerResponseID),
      fallbackClass: boundedIdentity(transport?.fallbackClass),
      inputTokens: input, outputTokens: output, totalTokens: transport?.usage?.totalTokens,
      cachedInputTokens: transport?.usage?.reportedCachedTokens,
      cacheWriteTokens: transport?.usage?.reportedCacheWriteTokens,
      usageStatus: usageStatus,
      // The proactive envelope does not expose the gateway's rate card or
      // aggregate attempt receipt. Never infer cost from token counts.
      costStatus: "unknown", estimatedCostMicroUSD: nil,
      providerAttempts: nil, attemptIDs: [])
  }

  func withExecutionID(_ executionID: String) -> Self {
    Self(
      dispatch: dispatch, lane: lane, ownerID: ownerID,
      accountGeneration: accountGeneration, snapshotRevision: snapshotRevision,
      budgetDay: budgetDay, contextID: contextID, candidateID: candidateID,
      executionID: executionID, outcome: outcome, operation: operation,
      requestID: requestID, provider: provider, providerModel: providerModel,
      providerResponseID: providerResponseID,
      fallbackClass: fallbackClass, inputTokens: inputTokens, outputTokens: outputTokens,
      totalTokens: totalTokens, cachedInputTokens: cachedInputTokens,
      cacheWriteTokens: cacheWriteTokens, usageStatus: usageStatus,
      costStatus: costStatus, estimatedCostMicroUSD: estimatedCostMicroUSD,
      providerAttempts: providerAttempts, attemptIDs: attemptIDs)
  }

  var observationID: String {
    requestID ?? "candidate:\(candidateID)"
  }

  var wireDictionary: [String: Any] {
    var object: [String: Any] = [
      "schema_version": Self.schemaVersion,
      "dispatch": dispatch,
      "lane": lane.rawValue,
      "owner_id": ownerID,
      "account_generation": accountGeneration,
      "snapshot_revision": snapshotRevision,
      "budget_day": budgetDay,
      "context_id": contextID,
      "candidate_id": candidateID,
      "outcome": outcome,
      "operation": operation,
      "usage_status": usageStatus,
      "cost_status": costStatus,
      "attempt_ids": attemptIDs,
    ]
    if let providerAttempts { object["provider_attempts"] = providerAttempts }
    if let executionID { object["execution_id"] = executionID }
    if let requestID { object["request_id"] = requestID }
    if let provider { object["provider"] = provider }
    if let providerModel { object["provider_model"] = providerModel }
    if let providerResponseID { object["provider_response_id"] = providerResponseID }
    if let fallbackClass { object["fallback_class"] = fallbackClass }
    if let inputTokens { object["input_tokens"] = inputTokens }
    if let outputTokens { object["output_tokens"] = outputTokens }
    if let totalTokens { object["total_tokens"] = totalTokens }
    if let cachedInputTokens { object["cached_input_tokens"] = cachedInputTokens }
    if let cacheWriteTokens { object["cache_write_tokens"] = cacheWriteTokens }
    if let estimatedCostMicroUSD { object["estimated_cost_micro_usd"] = estimatedCostMicroUSD }
    return object
  }
}

private func boundedIdentity(_ value: String?) -> String? {
  guard let value, !value.isEmpty, value.count <= 200,
    value.allSatisfy({ $0.isLetter || $0.isNumber || ".:/_-".contains($0) })
  else { return nil }
  return value
}

/// The response is staged briefly between the transport actor and the JIT
/// runtime, which adds lane/candidate/evaluation identity before persistence.
/// A missing response (for example a network failure before HTTP headers) is
/// intentionally represented by the runtime as an observed unknown outcome.
actor JITProactivityNanoCaptureStore {
  static let shared = JITProactivityNanoCaptureStore()
  private var responses: [String: ProactiveLaneResponseObservation] = [:]

  static func key(for context: JITAmbientRuntimeContext) -> String {
    "\(context.id):\(context.semanticFingerprint)"
  }

  func record(_ response: ProactiveLaneResponseObservation, for contextID: String) {
    responses[contextID] = response
  }

  func take(for contextID: String) -> ProactiveLaneResponseObservation? {
    defer { responses.removeValue(forKey: contextID) }
    return responses.removeValue(forKey: contextID)
  }
}

/// Private, qualification-only prompt materialization carried with the exact
/// agent run that admitted the JIT context snapshot. Prompt bytes stay in the
/// owner-scoped agent database; the runtime adds the snapshot hash when it
/// builds the durable run input.
struct JITProactivitySourceProjection: Equatable, Sendable {
  static let schemaVersion = "omi.jit.proactivity.source_projection.v1"
  static let qaBundleIdentifier = "com.omi.omi-jit-qa"
  static let qaOwnerID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
  /// The legacy projection intentionally covers the director prompt builders
  /// only. Retrieval, workstream pooling, and proactive-candidate short-circuits
  /// are recorded as disabled rather than represented by a hand-built prompt.
  static let legacyProjectionMode = "director_baseline_v1"

  static func capturePermitted(
    ownerID: String,
    bundleIdentifier: String? = Bundle.main.bundleIdentifier
  ) -> Bool {
    bundleIdentifier == qaBundleIdentifier && ownerID == qaOwnerID
  }

  let executionID: String
  let producerLane: JITProactivityLane
  let evaluationTime: String
  let timezone: String
  let contextID: String
  let legacyPrompt: String
  let legacyUncachedPrompt: String
  let nanoPrompt: String
  let fullPrompt: String
  /// Present for a real nano dispatch, or an observed planned path where the
  /// source explicitly proved that no nano dispatch occurred.
  let nanoBillingObservation: JITProactivityNanoBillingObservation?

  init(
    executionID: String,
    producerLane: JITProactivityLane,
    evaluationTime: String,
    timezone: String,
    contextID: String,
    legacyPrompt: String,
    legacyUncachedPrompt: String,
    nanoPrompt: String,
    fullPrompt: String,
    nanoBillingObservation: JITProactivityNanoBillingObservation? = nil
  ) {
    self.executionID = executionID
    self.producerLane = producerLane
    self.evaluationTime = evaluationTime
    self.timezone = timezone
    self.contextID = contextID
    self.legacyPrompt = legacyPrompt
    self.legacyUncachedPrompt = legacyUncachedPrompt
    self.nanoPrompt = nanoPrompt
    self.fullPrompt = fullPrompt
    self.nanoBillingObservation = nanoBillingObservation
  }

  /// Builds a projection only for the fixed QA bundle and owner. The exact
  /// budget and temporal tuple are copied from the admitted execution so a
  /// replay cannot be assembled from an operator-selected clock or context.
  static func makeIfPermitted(
    execution: JITPlannedExecution,
    ownerID: String,
    contextID: String,
    legacyPrompt: String,
    legacyUncachedPrompt: String,
    nanoPrompt: String,
    fullPrompt: String,
    nanoBillingObservation: JITProactivityNanoBillingObservation? = nil,
    bundleIdentifier: String? = Bundle.main.bundleIdentifier
  ) -> Self? {
    let admittedNanoBillingObservation = nanoBillingObservation ?? execution.nanoBillingObservation
    guard bundleIdentifier == qaBundleIdentifier,
      ownerID == qaOwnerID,
      let budget = execution.agentBudget,
      budget.contractVersion == JITProactivityAgentBudget.cloudQAContractVersion,
      !contextID.isEmpty,
      !legacyPrompt.isEmpty,
      !legacyUncachedPrompt.isEmpty,
      !nanoPrompt.isEmpty,
      !fullPrompt.isEmpty,
      admittedNanoBillingObservation != nil,
      let temporal = execution.temporalContext,
      let evaluatedAt = temporal.evaluatedAt,
      let timezone = temporal.timezoneIdentifier,
      temporal.timeZone != nil
    else { return nil }

    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    formatter.timeZone = temporal.timeZone
    return Self(
      executionID: budget.executionID,
      producerLane: execution.lane,
      evaluationTime: formatter.string(from: evaluatedAt),
      timezone: timezone,
      contextID: contextID,
      legacyPrompt: legacyPrompt,
      legacyUncachedPrompt: legacyUncachedPrompt,
      nanoPrompt: nanoPrompt,
      fullPrompt: fullPrompt,
      nanoBillingObservation: admittedNanoBillingObservation)
  }

  /// The dictionary is restricted to JSON values and is sent only through
  /// the QA JIT request. The agent runtime adds `evidence_sha256` and the
  /// matching hash after it has built the admitted context snapshot.
  var wireDictionary: [String: Any] {
    var object: [String: Any] = [
      "schema_version": Self.schemaVersion,
      "owner_id": Self.qaOwnerID,
      "execution_id": executionID,
      "producer_lane": producerLane.rawValue,
      "matched_input": [
        "evaluation_time": evaluationTime,
        "timezone": timezone,
        "context_id": contextID,
      ],
      "legacy": [
        "prompt": legacyPrompt,
        "uncached_prompt": legacyUncachedPrompt,
        "projection_mode": Self.legacyProjectionMode,
        "source_builders": [
          "ContextProactivityPromptBuilder.directorStablePrompt",
          "ContextProactivityPromptBuilder.directorVolatilePrompt",
        ],
        "flags": [
          "allow_lookup=false",
          "include_interject_copy_budgets=false",
          "workstream_pooling=false",
          "proactive_candidates=false",
        ],
      ],
      "nano": [
        "prompt": nanoPrompt,
        "source_builder": "JITProactivityPromptBuilder.nanoTriagePrompt",
      ],
      "full": [
        "prompt": fullPrompt,
        "source_builder": "JITProactivityPromptBuilder.fullTurnPrompt",
      ],
    ]
    if let nanoBillingObservation {
      object["nano_billing"] = nanoBillingObservation.wireDictionary
    }
    return object
  }
}
