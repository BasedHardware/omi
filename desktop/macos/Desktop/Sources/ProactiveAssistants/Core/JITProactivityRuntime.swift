import CryptoKit
import Foundation

private func defaultJITNanoTriage(
  context: JITAmbientRuntimeContext,
  snapshot: RuntimeOwnerAuthorizationSnapshot
) async -> JITAmbientNanoTriage {
  let captureID = JITProactivityNanoCaptureStore.key(for: context)
  let captureEnabled = JITProactivitySourceProjection.capturePermitted(ownerID: snapshot.ownerID)
  let observer: (@Sendable (ProactiveLaneResponseObservation) async -> Void)? =
    captureEnabled
    ? { @Sendable (observation: ProactiveLaneResponseObservation) async -> Void in
      await JITProactivityNanoCaptureStore.shared.record(observation, for: captureID)
    }
    : nil
  do {
    let result = try await ProactiveLaneClient.shared.complete(
      operation: ModelQoS.Proactivity.extractionOperation,
      prompt: JITProactivityPromptBuilder.nanoTriagePrompt(context: context),
      imageData: nil,
      jsonSchema: [
        "type": "object",
        "properties": ["approved": ["type": "boolean"]],
        "required": ["approved"],
        "additionalProperties": false,
      ],
      maxCompletionTokens: 120,
      authorizationSnapshot: snapshot,
      responseObserver: observer)
    let metadata = ProactiveLaneResponseObservation.successful(statusCode: 200, result: result)
    guard let data = result.content.data(using: String.Encoding.utf8),
      let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      let approved = object["approved"] as? Bool
    else {
      if captureEnabled {
        await JITProactivityNanoCaptureStore.shared.record(
          metadata.withFailure(
            ProactiveLaneFailureClassification(
              failure: "invalid_structured_output", status: 200, errorType: nil)),
          for: captureID)
      }
      return .unknown
    }
    return approved ? .approved : .rejected
  } catch {
    return .unknown
  }
}

struct JITPlannedExecution: Equatable, Sendable {
  let lane: JITProactivityLane
  let triggerID: String
  let continuityKey: String
  let prompt: String
  let claim: JITTriggerWakeupClaim
  /// Planned turns retain the exact authority that purchased their claim so the delivery path can
  /// revalidate it immediately before starting model work. Ambient turns have no ledger trigger.
  let plannedAuthority: JITPlannedExecutionAuthority?
  let candidateID: String
  let accountGeneration: Int
  let policy: JITTriggerRuntimePolicy
  /// Standing intent the ambient context matched at admission. Grounds the
  /// full turn and is recorded in local provenance; planned turns carry none.
  var derivedIntent: JITDerivedIntentMatch = .none
  /// Captured before asynchronous delivery and never recomputed later.
  var temporalContext: JITProactivityTemporalContext? = nil
  var agentBudget: JITProactivityAgentBudget? = nil
  /// Exact nano prompt materialized at admission. Ambient turns use the prompt
  /// that was actually triaged; planned turns retain the same source-owned
  /// materialization for the bounded counterfactual replay projection.
  var nanoPrompt: String? = nil
  /// Actual transport/accounting metadata when admission dispatched nano, or
  /// an explicit no-dispatch marker for a deterministic planned turn.
  var nanoBillingObservation: JITProactivityNanoBillingObservation? = nil
}

struct JITAmbientNanoClaimRequest: Equatable, Sendable {
  let contextID: String
  let semanticFingerprint: String
  let budgetDay: String
  let snapshotRevision: String
  let budget: Int
  let now: Date
}

struct JITPlannedExecutionAuthority: Equatable, Sendable {
  let receipt: JITTriggerMirrorReceipt
  let triggerRow: JITTriggerSnapshotRow
}

struct JITAmbientRuntimeContext: Equatable, Sendable {
  let id: String
  let semanticFingerprint: String
  let locallyRelevant: Bool
  let boundedEvidence: String
  var temporalContext: JITProactivityTemporalContext? = nil

  var permitsNanoTriage: Bool {
    !id.isEmpty && semanticFingerprint.count == 64 && locallyRelevant && !boundedEvidence.isEmpty
  }

  static func semanticFingerprint(contextID: String, validatedFacts: [String]) -> String {
    let facts = validatedFacts.map {
      $0.split(whereSeparator: \.isWhitespace).joined(separator: " ").lowercased()
    }.filter { !$0.isEmpty }.sorted().prefix(20)
    return JITProactivityReservation.opaqueIdentifier(
      ["semantic", contextID.lowercased()] + facts,
      installationIdentity: ClientDeviceService.shared.installationIdentity)
  }
}

/// Runtime admission for the additive JIT lane. An enabled owner must first
/// reconcile one complete authoritative snapshot. Planned standing intent is
/// evaluated and durably claimed before any full turn can be purchased.
actor JITProactivityRuntime {
  static let shared = JITProactivityRuntime()

  typealias FlagResolver = @Sendable (RuntimeOwnerAuthorizationSnapshot) async -> JITProactivityFlags
  typealias SnapshotResolver = @Sendable (RuntimeOwnerAuthorizationSnapshot) async throws -> JITTriggerSnapshot
  typealias NanoTriage =
    @Sendable (
      JITAmbientRuntimeContext, RuntimeOwnerAuthorizationSnapshot
    ) async -> JITAmbientNanoTriage
  typealias ReconcileSnapshot =
    @Sendable (JITTriggerSnapshot, RuntimeOwnerAuthorizationSnapshot) async throws -> JITTriggerMirrorReceipt
  typealias CompileSnapshot =
    @Sendable (JITTriggerMirrorReceipt, RuntimeOwnerAuthorizationSnapshot) async throws ->
    [KnowledgeLedgerCompiledTrigger]
  typealias ReadWakeupCounts = @Sendable ([String], String, Date) async throws -> [String: Int]
  typealias ClaimWakeup =
    @Sendable (JITPlannedWakeupRequest) async throws -> JITTriggerWakeupClaim?
  typealias BeginPlannedExecution =
    @Sendable (JITPlannedExecutionAuthority, JITTriggerWakeupClaim) async throws -> Bool
  typealias AuthorizationCurrent = @Sendable (RuntimeOwnerAuthorizationSnapshot) -> Bool
  typealias Reserve =
    @Sendable (JITProactivityReservation, RuntimeOwnerAuthorizationSnapshot) async -> Bool
  typealias DerivedIntentResolver =
    @Sendable (KnowledgeLedgerTriggerObservation, RuntimeOwnerAuthorizationSnapshot) async ->
    JITDerivedIntentMatch
  typealias AmbientNanoUsageReader = @Sendable (String, Date) async throws -> JITAmbientNanoUsage
  typealias ClaimAmbientNano = @Sendable (JITAmbientNanoClaimRequest) async throws -> JITTriggerWakeupClaim?
  private let flags: FlagResolver
  private let snapshots: SnapshotResolver
  private let mirror: JITTriggerMirror
  private let nanoTriage: NanoTriage
  private let reconcileSnapshot: ReconcileSnapshot?
  private let compileSnapshot: CompileSnapshot?
  private let readWakeupCounts: ReadWakeupCounts?
  private let claimPlannedWakeup: ClaimWakeup?
  private let beginPlannedExecution: BeginPlannedExecution?
  private let authorizationCurrent: AuthorizationCurrent
  private let reserve: Reserve
  private let derivedIntent: DerivedIntentResolver
  private let ambientNanoUsage: AmbientNanoUsageReader?
  private let claimAmbientNano: ClaimAmbientNano?
  private let nanoCaptureStore: JITProactivityNanoCaptureStore
  /// Trusted evaluation clock. Production uses the process clock; tests inject
  /// a fixed value so budget-day and pacing decisions remain hermetic. This is
  /// deliberately separate from an observation's captured event time.
  private let evaluationNow: @Sendable () -> Date
  private var pending: [String: JITPlannedExecution] = [:]
  private struct ExecutionHeartbeat {
    let leaseToken: String
    let task: Task<Void, Never>
  }
  private var executionHeartbeats: [String: ExecutionHeartbeat] = [:]
  /// Last server-side nano reservation denial per budget day. The server's
  /// budget is shared across devices, so a denial means the day is exhausted
  /// somewhere; retrying on every qualifying visit was a request storm (238
  /// denied attempts on one dogfood day). Process-local on purpose: the
  /// authoritative counter lives on the server.
  private var ambientServerDenials: [String: Date] = [:]
  static let ambientServerDenialBackoff: TimeInterval = 30 * 60
  /// Budget-day formatting runs on every context-visit admission; formatter
  /// construction is too expensive to repeat there. Actor-isolated, rebuilt
  /// only when the system timezone changes.
  private var cachedDayFormatter: (timezone: TimeZone, formatter: DateFormatter)?

  init(
    flags: @escaping FlagResolver = { snapshot in
      await ProactiveLaneClient.shared.jitProactivityFlags(authorizationSnapshot: snapshot)
    },
    snapshots: @escaping SnapshotResolver = { snapshot in
      try await ProactiveLaneClient.shared.fetchJITTriggerSnapshot(authorizationSnapshot: snapshot)
    },
    nanoTriage: @escaping NanoTriage = defaultJITNanoTriage,
    mirror: JITTriggerMirror = .shared,
    reconcileSnapshot: ReconcileSnapshot? = nil,
    compileSnapshot: CompileSnapshot? = nil,
    readWakeupCounts: ReadWakeupCounts? = nil,
    claimPlannedWakeup: ClaimWakeup? = nil,
    beginPlannedExecution: BeginPlannedExecution? = nil,
    reserve: @escaping Reserve = { reservation, snapshot in
      await JITProactivityReservationClient.shared.reserve(
        reservation, authorizationSnapshot: snapshot)
    },
    authorizationCurrent: @escaping AuthorizationCurrent = { snapshot in
      RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot)
    },
    derivedIntent: @escaping DerivedIntentResolver = { observation, snapshot in
      await JITDerivedWatchlistSource.shared.match(
        observation: observation, ownerID: snapshot.ownerID, now: observation.occurredAt ?? Date())
    },
    ambientNanoUsage: AmbientNanoUsageReader? = nil,
    claimAmbientNano: ClaimAmbientNano? = nil,
    nanoCaptureStore: JITProactivityNanoCaptureStore = .shared,
    evaluationNow: @escaping @Sendable () -> Date = Date.init
  ) {
    self.flags = flags
    self.derivedIntent = derivedIntent
    self.ambientNanoUsage = ambientNanoUsage
    self.claimAmbientNano = claimAmbientNano
    self.nanoCaptureStore = nanoCaptureStore
    self.evaluationNow = evaluationNow
    self.snapshots = snapshots
    self.nanoTriage = nanoTriage
    self.mirror = mirror
    self.reconcileSnapshot = reconcileSnapshot
    self.compileSnapshot = compileSnapshot
    self.readWakeupCounts = readWakeupCounts
    self.claimPlannedWakeup = claimPlannedWakeup
    self.beginPlannedExecution = beginPlannedExecution
    self.reserve = reserve
    self.authorizationCurrent = authorizationCurrent
  }

  func admission(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    observation: KnowledgeLedgerTriggerObservation,
    ambient: JITAmbientRuntimeContext? = nil
  ) async -> JITProactivityDecision {
    await admission(
      authorizationSnapshot: authorizationSnapshot,
      ambient: ambient,
      observationProvider: { observation })
  }

  /// Admission for callers whose observation inputs cost something real to build — the calendar
  /// leg goes to EventKit on every context visit. The provider runs only after the rollout gate
  /// admits this owner, so a default-off install performs no such work. The non-admitted decision
  /// never reads the observation, so deferring it is behaviour-preserving for admitted owners.
  func admission(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    ambient: JITAmbientRuntimeContext? = nil,
    observationProvider: @Sendable () async -> KnowledgeLedgerTriggerObservation
  ) async -> JITProactivityDecision {
    let resolved = await flags(authorizationSnapshot)
    guard resolved.permitsNewLane else {
      return JITProactivityPolicy.decide(flags: resolved, planned: [], ambient: [])
    }
    let observation = await observationProvider()
    do {
      let snapshot = try await snapshots(authorizationSnapshot)
      let receipt = try await reconcile(snapshot, authorizationSnapshot: authorizationSnapshot)
      let allTriggers = try await compiledSnapshot(
        receipt: receipt, authorizationSnapshot: authorizationSnapshot)
      let evaluationTime = evaluationNow()
      let eventTime = observation.occurredAt
      // Snooze eligibility is evaluated inside the watchlist runtime so a
      // snoozed-only snapshot stays a standing watchlist (ambient after miss),
      // not an empty one. Wakeup counters still skip ineligible IDs.
      let eligibleTriggers = allTriggers.filter { trigger in
        guard let snoozedUntil = trigger.snoozedUntil else { return true }
        return evaluationTime >= snoozedUntil
      }
      guard let day = day(for: evaluationTime, budgetTimezone: snapshot.budgetTimezone) else {
        return .suppressed(reason: "budget_authority_unavailable")
      }
      let counts = try await wakeupCounts(
        triggerIDs: eligibleTriggers.map(\.id), budgetDay: day, now: evaluationTime)
      let receiptMatchesSnapshot =
        snapshot.complete
        && receipt.ownerID == snapshot.ownerID
        && receipt.accountGeneration == snapshot.accountGeneration
        && receipt.commitSequence == snapshot.commitSequence
        && receipt.snapshotRevision == snapshot.snapshotRevision
        && receipt.rowCount == snapshot.rows.count
        && receipt.policy == snapshot.policy
        && snapshot.policy.isValid
      let authority = KnowledgeLedgerTriggerRuntimeAuthority(
        mode: .enabled,
        killSwitchEnabled: false,
        ownerID: authorizationSnapshot.ownerID,
        accountGeneration: snapshot.accountGeneration,
        snapshotOwnerID: snapshot.ownerID,
        snapshotAccountGeneration: receipt.accountGeneration,
        snapshotIsAuthoritative: receiptMatchesSnapshot,
        authorizationIsCurrent: authorizationCurrent(authorizationSnapshot))
      let runtimeResult = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
        projection: .init(entries: allTriggers, quarantined: []),
        observation: observation,
        day: day,
        authority: authority,
        // No local model/version contract is available at this boundary.
        embeddingContract: nil,
        embeddingPolicy: snapshot.policy.embedding,
        wakeupsUsedByTrigger: counts)
      guard runtimeResult.status == .evaluated else {
        return .suppressed(reason: "planned_runtime_rejected")
      }
      let winner: KnowledgeLedgerTriggerRuntimeEntryResult
      var admittedNanoObservation: JITProactivityNanoBillingObservation? = nil
      var plannedNanoWasDispatched = false
      switch runtimeResult.nextLane {
      case .ambientFallback:
        return await admitAmbient(
          context: ambient,
          observation: observation,
          receipt: receipt,
          budgetTimezone: snapshot.budgetTimezone,
          budgetContractVersion: resolved.budgetContractVersion,
          evaluationTime: evaluationTime,
          authorizationSnapshot: authorizationSnapshot)
      case .boundedPlannedTriage:
        guard let ambiguous = runtimeResult.ambiguous.first else {
          return .suppressed(reason: "planned_match_ambiguous")
        }
        let plannedNano = await approvePlannedAmbiguity(
          ambiguous, observation: observation, snapshot: snapshot,
          temporalContext: Self.temporalContext(
            capturedAt: eventTime, evaluatedAt: evaluationTime,
            timezoneIdentifier: snapshot.budgetTimezone),
          authorizationSnapshot: authorizationSnapshot)
        guard plannedNano.approved else { return .suppressed(reason: "planned_match_ambiguous") }
        admittedNanoObservation = plannedNano.observation
        plannedNanoWasDispatched = true
        winner = ambiguous
      case .none:
        if allTriggers.isEmpty {
          // Defensive: the watchlist runtime already routes a complete empty
          // watchlist to ambient. An account with no standing trigger is the
          // common case, not a reason for silence.
          return await admitAmbient(
            context: ambient,
            observation: observation,
            receipt: receipt,
            budgetTimezone: snapshot.budgetTimezone,
            budgetContractVersion: resolved.budgetContractVersion,
            evaluationTime: evaluationTime,
            authorizationSnapshot: authorizationSnapshot)
        }
        return .suppressed(reason: "planned_runtime_rejected")
      case .plannedTrigger:
        guard let matched = runtimeResult.matches.first else {
          return .suppressed(reason: "planned_runtime_rejected")
        }
        winner = matched
      }
      guard let trigger = allTriggers.first(where: { $0.id == winner.triggerID }),
        let triggerRow = snapshot.rows.first(where: { $0.memoryID == winner.triggerID }),
        let action = trigger.action,
        action.isValid
      else {
        return .suppressed(reason: "planned_action_invalid")
      }
      // The evaluator may use a deterministic content fingerprint internally,
      // but the mirror and reservation payloads must never retain that raw
      // digest. Bind it to the random installation key before it crosses the
      // local persistence or server boundary.
      let continuityFingerprint = Self.opaqueObservationFingerprint(
        winner.decision.observationFingerprint)
      // One receipt identifies one planned occurrence, not a context forever.
      // Day permits a recurring standing trigger to run again; trigger and
      // authoritative snapshot revision admit changed actions; the normalized
      // observation fingerprint suppresses duplicates within that occurrence.
      let continuityKey = Self.plannedContinuityKey(
        triggerID: trigger.id,
        snapshotRevision: receipt.snapshotRevision,
        budgetDay: day,
        observationFingerprint: continuityFingerprint)
      guard pending[continuityKey] == nil, executionHeartbeats[continuityKey] == nil else {
        return .suppressed(reason: "planned_duplicate_or_budget")
      }
      guard
        let claim = try await claimWakeup(
          continuityKey: continuityKey,
          triggerID: trigger.id,
          lane: .planned,
          budgetDay: day,
          snapshotRevision: receipt.snapshotRevision,
          observationFingerprint: continuityFingerprint,
          budget: trigger.metadata.wakeupBudgetPerDay,
          now: evaluationTime,
          authority: receipt,
          triggerRow: triggerRow)
      else { return .suppressed(reason: "planned_duplicate_or_budget") }
      let candidateID = JITProactivityReservation.identifier(
        "planned", trigger.id, continuityFingerprint, day)
      let temporalContext = Self.temporalContext(
        capturedAt: eventTime, evaluatedAt: evaluationTime,
        timezoneIdentifier: snapshot.budgetTimezone)
      let nanoContext = JITAmbientRuntimeContext(
        id: "planned:\(trigger.id)",
        semanticFingerprint: continuityFingerprint,
        locallyRelevant: true,
        boundedEvidence: String(observation.text.prefix(8_000)),
        temporalContext: temporalContext)
      let plannedNanoObservation = admittedNanoObservation?.withExecutionID(candidateID)
      let nanoBillingObservation =
        plannedNanoObservation
        ?? (plannedNanoWasDispatched
          ? JITProactivityNanoBillingObservation.observed(
            lane: .planned,
            ownerID: authorizationSnapshot.ownerID,
            accountGeneration: snapshot.accountGeneration,
            snapshotRevision: receipt.snapshotRevision,
            budgetDay: day,
            contextID: nanoContext.id,
            candidateID: candidateID,
            executionID: candidateID,
            triage: .approved,
            transport: nil)
          : nil)
        ?? JITProactivityNanoBillingObservation.notDispatched(
          lane: .planned,
          ownerID: authorizationSnapshot.ownerID,
          accountGeneration: snapshot.accountGeneration,
          snapshotRevision: receipt.snapshotRevision,
          budgetDay: day,
          contextID: nanoContext.id,
          candidateID: candidateID,
          executionID: candidateID)
      await recordNanoBillingObservation(nanoBillingObservation)
      pending[continuityKey] = JITPlannedExecution(
        lane: .planned,
        triggerID: trigger.id,
        continuityKey: continuityKey,
        prompt: action.prompt,
        claim: claim,
        plannedAuthority: JITPlannedExecutionAuthority(receipt: receipt, triggerRow: triggerRow),
        candidateID: candidateID,
        accountGeneration: snapshot.accountGeneration,
        policy: snapshot.policy,
        temporalContext: temporalContext,
        agentBudget: JITProactivityAgentBudget(
          contractVersion: resolved.budgetContractVersion, executionID: candidateID),
        nanoPrompt: JITProactivityPromptBuilder.nanoTriagePrompt(context: nanoContext),
        nanoBillingObservation: nanoBillingObservation)
      return .deliver(lane: .planned, id: trigger.id, continuityKey: continuityKey)
    } catch {
      return .suppressed(reason: "authoritative_snapshot_unavailable")
    }
  }

  /// Signed-in startup mirror sync: fetch and reconcile the authoritative
  /// trigger snapshot before any context visit exists, so the snapshot (and
  /// its receipt) never depends on screen capture being live, a
  /// notify-worthy visit, or calendar access. Shares admission's
  /// flag → fetch → reconcile chain and its fail-closed gate; a non-permitting
  /// authority performs no snapshot read. No evaluation, no delivery — the
  /// next context visit still owns those. One shot per signed-in startup:
  /// a transport failure is logged (bounded, content-free) and retried only
  /// by the next owner change or launch.
  func syncTriggerSnapshot(authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot) async {
    let resolved = await flags(authorizationSnapshot)
    // Publish the handoff before the first context visit so the legacy focus
    // assistant and the JIT lane never overlap for an admitted owner.
    let ownerID = authorizationSnapshot.ownerID
    let permits = resolved.permitsNewLane
    await MainActor.run { JITProactivityLaneState.update(ownerID: ownerID, active: permits) }
    guard permits else { return }
    do {
      let snapshot = try await snapshots(authorizationSnapshot)
      _ = try await reconcile(snapshot, authorizationSnapshot: authorizationSnapshot)
    } catch {
      NSLog(
        "JIT trigger snapshot: startup sync failed error_type=%@",
        ProactiveLaneFailureClassification.boundedNetworkErrorType(error))
    }
  }

  private func approvePlannedAmbiguity(
    _ ambiguous: KnowledgeLedgerTriggerRuntimeEntryResult,
    observation: KnowledgeLedgerTriggerObservation,
    snapshot: JITTriggerSnapshot,
    temporalContext: JITProactivityTemporalContext,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async -> (approved: Bool, observation: JITProactivityNanoBillingObservation?) {
    let opaqueFingerprint = Self.opaqueObservationFingerprint(
      ambiguous.decision.observationFingerprint)
    let candidateID = JITProactivityReservation.identifier(
      "planned-ambiguity", ambiguous.triggerID, opaqueFingerprint)
    guard
      await reserve(
        JITProactivityReservation(
          eventID: JITProactivityReservation.identifier("nano", candidateID),
          candidateID: candidateID, operation: .nanoTriage,
          accountGeneration: snapshot.accountGeneration,
          triggerMemoryID: nil, triggerRevision: nil),
        authorizationSnapshot)
    else { return (false, nil) }
    let context = JITAmbientRuntimeContext(
      id: "planned:\(ambiguous.triggerID)",
      semanticFingerprint: opaqueFingerprint,
      locallyRelevant: true,
      boundedEvidence: String(observation.text.prefix(8_000)),
      temporalContext: temporalContext)
    let triage = await nanoTriage(context, authorizationSnapshot)
    let observation = await finishNanoCapture(
      lane: .planned,
      ownerID: authorizationSnapshot.ownerID,
      accountGeneration: snapshot.accountGeneration,
      snapshotRevision: snapshot.snapshotRevision,
      budgetDay: day(for: temporalContext.evaluatedAt ?? Date(), budgetTimezone: snapshot.budgetTimezone) ?? "unknown",
      context: context,
      candidateID: candidateID,
      executionID: nil,
      triage: triage)
    return (triage == .approved, observation)
  }

  private func finishNanoCapture(
    lane: JITProactivityLane,
    ownerID: String,
    accountGeneration: Int,
    snapshotRevision: String,
    budgetDay: String,
    context: JITAmbientRuntimeContext,
    candidateID: String,
    executionID: String?,
    triage: JITAmbientNanoTriage
  ) async -> JITProactivityNanoBillingObservation? {
    guard JITProactivitySourceProjection.capturePermitted(ownerID: ownerID) else { return nil }
    let transport = await nanoCaptureStore.take(for: JITProactivityNanoCaptureStore.key(for: context))
    let observation = JITProactivityNanoBillingObservation.observed(
      lane: lane,
      ownerID: ownerID,
      accountGeneration: accountGeneration,
      snapshotRevision: snapshotRevision,
      budgetDay: budgetDay,
      contextID: context.id,
      candidateID: candidateID,
      executionID: executionID,
      triage: triage,
      transport: transport)
    await recordNanoBillingObservation(observation)
    return observation
  }

  private func recordNanoBillingObservation(_ observation: JITProactivityNanoBillingObservation) async {
    guard JITProactivitySourceProjection.capturePermitted(ownerID: observation.ownerID) else { return }
    await mirror.recordNanoBillingObservation(observation)
  }

  private func reconcile(
    _ snapshot: JITTriggerSnapshot,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> JITTriggerMirrorReceipt {
    if let reconcileSnapshot {
      return try await reconcileSnapshot(snapshot, authorizationSnapshot)
    }
    return try await mirror.reconcile(snapshot, authorizationSnapshot: authorizationSnapshot)
  }

  private func compiledSnapshot(
    receipt: JITTriggerMirrorReceipt,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> [KnowledgeLedgerCompiledTrigger] {
    if let compileSnapshot { return try await compileSnapshot(receipt, authorizationSnapshot) }
    return try await mirror.compiledSnapshot(
      receipt: receipt, authorizationSnapshot: authorizationSnapshot)
  }

  private func wakeupCounts(triggerIDs: [String], budgetDay: String, now: Date) async throws -> [String: Int] {
    if let readWakeupCounts { return try await readWakeupCounts(triggerIDs, budgetDay, now) }
    return try await mirror.wakeupCounts(triggerIDs: triggerIDs, budgetDay: budgetDay, now: now)
  }

  private func claimWakeup(
    continuityKey: String,
    triggerID: String,
    lane: JITProactivityLane,
    budgetDay: String,
    snapshotRevision: String,
    observationFingerprint: String,
    budget: Int?,
    now: Date,
    authority: JITTriggerMirrorReceipt,
    triggerRow: JITTriggerSnapshotRow
  ) async throws -> JITTriggerWakeupClaim? {
    let request = JITPlannedWakeupRequest(
      continuityKey: continuityKey,
      triggerID: triggerID,
      lane: lane,
      budgetDay: budgetDay,
      snapshotRevision: snapshotRevision,
      observationFingerprint: observationFingerprint,
      budget: budget,
      now: now,
      authority: authority,
      triggerRow: triggerRow)
    if let claimPlannedWakeup {
      return try await claimPlannedWakeup(request)
    }
    return try await mirror.claimPlannedWakeup(request)
  }

  private func admitAmbient(
    context: JITAmbientRuntimeContext?,
    observation: KnowledgeLedgerTriggerObservation,
    receipt: JITTriggerMirrorReceipt,
    budgetTimezone: String?,
    budgetContractVersion: String?,
    evaluationTime: Date,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async -> JITProactivityDecision {
    guard let context, context.permitsNanoTriage else {
      return .suppressed(reason: "ambient_local_gate")
    }
    let eventTime = observation.occurredAt
    let temporalContext =
      context.temporalContext
      ?? Self.temporalContext(
        capturedAt: eventTime,
        evaluatedAt: evaluationTime,
        timezoneIdentifier: budgetTimezone)
    let opaqueContextID = Self.opaqueAmbientContextID(context.id)
    let opaqueSemanticFingerprint = Self.opaqueObservationFingerprint(context.semanticFingerprint)
    let retainedContext = JITAmbientRuntimeContext(
      id: opaqueContextID,
      semanticFingerprint: opaqueSemanticFingerprint,
      locallyRelevant: context.locallyRelevant,
      boundedEvidence: context.boundedEvidence,
      temporalContext: temporalContext)
    guard let day = day(for: evaluationTime, budgetTimezone: budgetTimezone) else {
      return .suppressed(reason: "budget_authority_unavailable")
    }
    if let deniedAt = ambientServerDenials[day],
      evaluationTime.timeIntervalSince(deniedAt) < Self.ambientServerDenialBackoff
    {
      return .suppressed(reason: "ambient_server_denied")
    }
    // Standing intent is resolved before any spend decision so the pacing
    // policy can prioritise it. It reads local tables only.
    let derived = await derivedIntent(observation, authorizationSnapshot)
    let usage: JITAmbientNanoUsage
    do {
      usage = try await readAmbientNanoUsage(budgetDay: day, now: evaluationTime)
    } catch {
      return .suppressed(reason: "ambient_nano_receipt_unavailable")
    }
    switch JITAmbientPacingPolicy.decide(
      JITAmbientPacingInput(
        usedToday: usage.used,
        budget: receipt.policy.ambiguousNanoTriagesPerDay,
        lastSpentAt: usage.lastSpentAt,
        now: evaluationTime,
        derivedIntentMatched: !derived.isEmpty))
    {
    case .spend:
      break
    case .exhausted:
      return .suppressed(reason: "ambient_nano_budget")
    case .deferred(let reason):
      // The context is not consumed: its fingerprint stays unrecorded, so the
      // same change can be triaged at a later delivery moment.
      return .suppressed(reason: reason)
    }
    let nanoClaim: JITTriggerWakeupClaim?
    do {
      nanoClaim = try await claimNano(
        JITAmbientNanoClaimRequest(
          contextID: retainedContext.id,
          semanticFingerprint: retainedContext.semanticFingerprint,
          budgetDay: day,
          snapshotRevision: receipt.snapshotRevision,
          budget: receipt.policy.ambiguousNanoTriagesPerDay,
          now: evaluationTime))
    } catch {
      return .suppressed(reason: "ambient_nano_receipt_unavailable")
    }
    guard let nanoClaim else { return .suppressed(reason: "ambient_nano_budget") }
    let candidateID = JITProactivityReservation.identifier(
      "ambient", retainedContext.id, retainedContext.semanticFingerprint, day)
    guard
      await reserve(
        JITProactivityReservation(
          eventID: JITProactivityReservation.identifier("nano", candidateID),
          candidateID: candidateID, operation: .nanoTriage,
          accountGeneration: receipt.accountGeneration,
          triggerMemoryID: nil, triggerRevision: nil),
        authorizationSnapshot)
    else {
      await mirror.finishWakeup(nanoClaim, delivered: false)
      ambientServerDenials[day] = evaluationTime
      return .suppressed(reason: "ambient_nano_budget")
    }
    let triage = await nanoTriage(retainedContext, authorizationSnapshot)
    // A candidate ID exists while nano admission is being evaluated, but a
    // full-run execution does not exist until the wakeup claim succeeds.
    // Keep the receipt candidate-joined until then; this preserves the
    // distinction between an observed nano request and a full replay that
    // never started.
    let nanoBillingObservation = await finishNanoCapture(
      lane: .ambient,
      ownerID: authorizationSnapshot.ownerID,
      accountGeneration: receipt.accountGeneration,
      snapshotRevision: receipt.snapshotRevision,
      budgetDay: day,
      context: retainedContext,
      candidateID: candidateID,
      executionID: nil,
      triage: triage)
    // Every provider attempt, including unknown/malformed, spends the bounded
    // nano budget so a flaky response cannot create an unbounded retry loop.
    guard
      await mirror.completeAmbientNanoAttempt(
        nanoClaim,
        contextID: retainedContext.id,
        semanticFingerprint: retainedContext.semanticFingerprint)
    else { return .suppressed(reason: "ambient_nano_receipt_unavailable") }
    guard triage == .approved else {
      return .suppressed(reason: "ambient_nano_rejected")
    }
    let continuityKey = "jit-context:\(retainedContext.semanticFingerprint)"
    guard pending[continuityKey] == nil, executionHeartbeats[continuityKey] == nil else {
      return .suppressed(reason: "ambient_duplicate_or_budget")
    }
    let claimed: JITTriggerWakeupClaim?
    do {
      claimed = try await mirror.claimWakeup(
        continuityKey: continuityKey,
        triggerID: "ambient:\(retainedContext.id)",
        lane: .ambient,
        budgetDay: day,
        snapshotRevision: receipt.snapshotRevision,
        observationFingerprint: retainedContext.semanticFingerprint,
        // One ambient full turn per stable semantic context/day. Planned
        // triggers retain their explicit ledger budget and always arbitrate first.
        budget: receipt.policy.fullAgentTurnsPerCandidate,
        now: evaluationTime)
    } catch {
      return .suppressed(reason: "ambient_receipt_unavailable")
    }
    guard let claim = claimed else { return .suppressed(reason: "ambient_duplicate_or_budget") }
    let admittedNanoBillingObservation = nanoBillingObservation?.withExecutionID(candidateID)
    if let admittedNanoBillingObservation {
      await recordNanoBillingObservation(admittedNanoBillingObservation)
    }
    pending[continuityKey] = JITPlannedExecution(
      lane: .ambient,
      triggerID: "ambient:\(retainedContext.id)",
      continuityKey: continuityKey,
      prompt: """
        Find at most one genuinely useful, non-obvious proactive insight from the current validated
        context. It must change the user's next action. Do not merely recap, praise, or create a
        permanent trigger. Use task_candidate only when a concrete actionable task is supported.
        """,
      claim: claim,
      plannedAuthority: nil,
      candidateID: candidateID,
      accountGeneration: receipt.accountGeneration,
      policy: receipt.policy,
      derivedIntent: derived,
      temporalContext: temporalContext,
      agentBudget: JITProactivityAgentBudget(
        contractVersion: budgetContractVersion, executionID: candidateID),
      nanoPrompt: JITProactivityPromptBuilder.nanoTriagePrompt(context: retainedContext),
      nanoBillingObservation: admittedNanoBillingObservation)
    return .deliver(lane: .ambient, id: context.id, continuityKey: continuityKey)
  }

  private func claimNano(_ request: JITAmbientNanoClaimRequest) async throws -> JITTriggerWakeupClaim? {
    if let claimAmbientNano { return try await claimAmbientNano(request) }
    return try await mirror.claimAmbientNanoChange(
      contextID: request.contextID,
      semanticFingerprint: request.semanticFingerprint,
      budgetDay: request.budgetDay,
      snapshotRevision: request.snapshotRevision,
      budget: request.budget,
      now: request.now)
  }

  private func readAmbientNanoUsage(budgetDay: String, now: Date) async throws -> JITAmbientNanoUsage {
    if let ambientNanoUsage { return try await ambientNanoUsage(budgetDay, now) }
    return try await mirror.ambientNanoUsage(budgetDay: budgetDay, now: now)
  }

  func takeExecution(continuityKey: String) -> JITPlannedExecution? {
    pending.removeValue(forKey: continuityKey)
  }

  /// This is the final planned-trigger authority fence and must run immediately before the agent
  /// turn starts. A newer reconciliation may have deleted or changed a trigger after admission
  /// returned a delivery decision but before the coordinator completed its other local gates.
  func beginExecution(_ execution: JITPlannedExecution) async -> Bool {
    let began: Bool
    do {
      if execution.lane == .planned {
        guard let authority = execution.plannedAuthority else { return false }
        if let beginPlannedExecution {
          began = try await beginPlannedExecution(authority, execution.claim)
        } else {
          began = try await mirror.beginPlannedExecution(
            authority, claim: execution.claim)
        }
      } else {
        began = try await mirror.beginAmbientExecution(claim: execution.claim)
      }
    } catch {
      return false
    }
    guard began else { return false }
    startExecutionHeartbeat(for: execution.claim)
    return true
  }

  func finish(_ execution: JITPlannedExecution, delivered: Bool) async {
    if executionHeartbeats[execution.claim.continuityKey]?.leaseToken == execution.claim.leaseToken {
      executionHeartbeats.removeValue(forKey: execution.claim.continuityKey)?.task.cancel()
    }
    await mirror.finishWakeup(execution.claim, delivered: delivered)
  }

  private func startExecutionHeartbeat(for claim: JITTriggerWakeupClaim) {
    executionHeartbeats.removeValue(forKey: claim.continuityKey)?.task.cancel()
    let mirror = mirror
    let task = Task {
      let clock = ContinuousClock()
      while !Task.isCancelled {
        do {
          try await clock.sleep(for: .seconds(JITTriggerMirror.executionHeartbeatSeconds))
        } catch {
          return
        }
        guard !Task.isCancelled else { return }
        do {
          guard try await mirror.renewExecutionLease(claim: claim) else { return }
        } catch {
          // The local database may be briefly unavailable during owner-bound reinitialization.
          // Keep retrying inside the existing lease window; finish or owner teardown cancels us.
          continue
        }
      }
    }
    executionHeartbeats[claim.continuityKey] = ExecutionHeartbeat(
      leaseToken: claim.leaseToken, task: task)
  }

  static func plannedContinuityKey(
    triggerID: String,
    snapshotRevision: String,
    budgetDay: String,
    observationFingerprint: String
  ) -> String {
    ["jit-planned", triggerID, snapshotRevision, budgetDay, observationFingerprint]
      .joined(separator: ":")
  }

  private static func opaqueObservationFingerprint(_ fingerprint: String) -> String {
    JITProactivityReservation.identifier("observation", fingerprint)
  }

  private static func opaqueAmbientContextID(_ contextID: String) -> String {
    JITProactivityReservation.identifier("ambient-context", contextID)
  }

  private static func temporalContext(
    capturedAt: Date?, evaluatedAt: Date?, timezoneIdentifier: String?
  ) -> JITProactivityTemporalContext {
    JITProactivityTemporalContext(
      capturedAt: capturedAt,
      evaluatedAt: evaluatedAt,
      timezoneIdentifier: timezoneIdentifier.flatMap { TimeZone(identifier: $0) != nil ? $0 : nil })
  }

  private func day(for date: Date, budgetTimezone: String? = nil) -> String? {
    let timezone: TimeZone
    if let budgetTimezone {
      guard let resolved = TimeZone(identifier: budgetTimezone) else { return nil }
      timezone = resolved
    } else {
      timezone = TimeZone.current
    }
    if let cached = cachedDayFormatter, cached.timezone == timezone {
      return cached.formatter.string(from: date)
    }
    let formatter = DateFormatter()
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = timezone
    formatter.dateFormat = "yyyy-MM-dd"
    cachedDayFormatter = (timezone, formatter)
    return formatter.string(from: date)
  }

}
