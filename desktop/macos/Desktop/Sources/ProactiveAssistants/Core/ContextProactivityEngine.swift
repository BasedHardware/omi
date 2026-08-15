import Foundation
@preconcurrency import GRDB

struct ContextDirectorDecision: Codable, Equatable, Sendable {
  let decision: String
  let title: String
  let message: String
  let reasoning: String
  let bucketEntryRefs: [String]
  let factIDs: [String]
  /// Request for the single retrieval hop; empty or absent means none.
  ///
  /// Optional so a response predating this field still decodes: synthesized
  /// `Decodable` uses `decodeIfPresent` for optionals. `var` with a default
  /// keeps the memberwise initializer source-compatible for existing callers
  /// (same pattern as `BucketExtraction.destination`).
  var lookupQuery: String? = nil

  enum CodingKeys: String, CodingKey {
    case decision, title, message, reasoning
    case bucketEntryRefs = "bucket_entry_refs"
    case factIDs = "fact_ids"
    case lookupQuery = "lookup_query"
  }

  func clamped() -> ContextDirectorDecision {
    ContextDirectorDecision(
      decision: decision,
      title: String(title.prefix(120)),
      message: String(message.prefix(600)),
      reasoning: String(reasoning.prefix(1_200)),
      bucketEntryRefs: bucketEntryRefs.prefix(20).map { String($0.prefix(200)) },
      factIDs: factIDs.prefix(20).map { String($0.prefix(200)) },
      lookupQuery: lookupQuery.map {
        String($0.prefix(ContextDirectorRetrievalHop.maximumQueryLength))
      })
  }
}

enum ContextDirectorEligibility {
  static func permitsEvaluation(of snapshot: ContextBucketSnapshot) -> Bool {
    snapshot.notifyWorthiness > 0 && !snapshot.validatedFacts.isEmpty
  }
}

enum ContextDirectorGrounding {
  static func permitsNonSilence(entryRefs: [String], factIDs: [String]) -> Bool {
    !entryRefs.isEmpty && !factIDs.isEmpty
  }
}

enum ContextDirectorTaskSelection {
  static let maximumCount = 20
  static let futureHorizon: TimeInterval = 48 * 60 * 60

  static func select(from tasks: [TaskActionItem], now: Date) -> [ContextDirectorTaskContext] {
    let cutoff = now.addingTimeInterval(futureHorizon)
    return
      tasks
      .filter { task in
        !task.completed && !task.isRetired && !task.isPendingSuggestion
      }
      .sorted { lhs, rhs in
        let leftIsReference = lhs.dueAt.map { $0 > cutoff } ?? false
        let rightIsReference = rhs.dueAt.map { $0 > cutoff } ?? false
        if leftIsReference != rightIsReference { return !leftIsReference }
        let left = lhs.dueAt ?? .distantFuture
        let right = rhs.dueAt ?? .distantFuture
        if left != right { return left < right }
        return lhs.createdAt > rhs.createdAt
      }
      .prefix(maximumCount)
      .map { ContextDirectorTaskContext(description: $0.description, dueAt: $0.dueAt) }
  }
}

extension ContextBucketStore {
  func activeFenceIsValid(_ fence: ContextVisitFence) async -> Bool {
    let (pool, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool, poolEpoch == fence.poolEpoch else { return false }
    do {
      return try await pool.read { db in
        try Bool.fetchOne(
          db,
          sql: """
            SELECT EXISTS(
              SELECT 1 FROM context_visits
              WHERE id = ? AND contextGeneration = ? AND poolEpoch = ? AND outcome = 'active'
            )
            """,
          arguments: [fence.visitID, fence.contextGeneration, fence.poolEpoch]) ?? false
      }
    } catch {
      return false
    }
  }
}

actor ContextProactivityEngine {
  static let shared = ContextProactivityEngine(client: .shared, store: .shared)
  private let client: ProactiveLaneClient
  private let store: ContextBucketStore
  private let presentationPreflight: @Sendable (String) async -> OwnerBoundNotificationPresentationResult
  private let retrieve: @Sendable (String, RuntimeOwnerAuthorizationSnapshot) async -> [ContextRetrievedItem]
  private var dwellAdmission = ContextVisitDwellAdmission()
  private let dwellNanoseconds: UInt64

  init(
    client: ProactiveLaneClient,
    store: ContextBucketStore,
    dwellNanoseconds: UInt64 = 8_000_000_000,
    presentationPreflight: @escaping @Sendable (String) async -> OwnerBoundNotificationPresentationResult = {
      ownerID in
      await NotificationService.shared.contextDirectorPresentationPreflight(ownerID: ownerID)
    },
    retrieve: @escaping @Sendable (String, RuntimeOwnerAuthorizationSnapshot) async -> [ContextRetrievedItem] = {
      query, authorizationSnapshot in
      await ContextDirectorRetrievalExecutor.retrieve(
        query: query, authorizationSnapshot: authorizationSnapshot)
    }
  ) {
    self.client = client
    self.store = store
    self.dwellNanoseconds = dwellNanoseconds
    self.presentationPreflight = presentationPreflight
    self.retrieve = retrieve
  }

  func contextEntered(_ fence: ContextVisitFence) async {
    guard fence.bucketID != nil else { return }
    guard let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return }
    guard dwellAdmission.begin(visitID: fence.visitID) else { return }
    defer { dwellAdmission.finish(visitID: fence.visitID) }
    do { try await Task.sleep(nanoseconds: dwellNanoseconds) } catch { return }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    do { try await store.markVisitSettled(fence) } catch { return }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    let gate = await MainActor.run { Self.liveDeliveryGateInput() }
    // Settle the visit so quiet-period activity remains part of the context ledger, then stop
    // before snapshot assembly, frame lookup, task projection, or the director model request.
    let preflightReason = ContextDeliveryBudget.freeGate(input: gate)
    guard preflightReason == .allowed else {
      log("Context director suppressed before preparation: \(preflightReason.rawValue)")
      return
    }
    guard
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      await store.activeFenceIsValid(fence),
      let snapshot = await store.snapshot(for: fence)
    else { return }
    // Facts are the only source of notification worthiness. A bucket containing
    // ambient narrative alone cannot purchase a frontier-model call.
    guard ContextDirectorEligibility.permitsEvaluation(of: snapshot) else { return }
    guard
      let currentFrame = await MainActor.run(body: {
        AssistantCoordinator.shared.trackedFrameForDirector(startedAt: fence.startedAt)
      })
    else { return }

    guard let ownerID = await MainActor.run(body: { RuntimeOwnerIdentity.currentOwnerId() }) else { return }
    let attemptPreflight = await presentationPreflight(ownerID)
    guard Self.presentationSurfaceAvailable(attemptPreflight) else {
      log("Context director suppressed before attempt: presentation_unavailable")
      return
    }

    let attemptGate = await MainActor.run { Self.liveDeliveryGateInput() }
    let attemptReason = ContextDeliveryBudget.freeGate(input: attemptGate)
    guard attemptReason == .allowed else {
      log("Context director suppressed before attempt: \(attemptReason.rawValue)")
      return
    }

    let attempt: ContextDeliveryAttempt
    do {
      attempt = try await store.beginDeliveryAttempt(fence: fence, snapshot: snapshot, gate: attemptGate)
    } catch { return }
    guard attempt.reason == .allowed, let deliveryID = attempt.id else {
      log("Context director suppressed: \(attempt.reason.rawValue)")
      return
    }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      await terminalize(
        deliveryID: deliveryID,
        decisionType: "silence",
        provenanceJSON: "{\"failure\":\"stale_owner\"}",
        state: "failed")
      return
    }

    let taskContext = await MainActor.run {
      ContextDirectorTaskSelection.select(
        from: TasksStore.shared.incompleteTasks,
        now: currentFrame.captureTime)
    }
    let recentDeliveries = await store.recentDeliveredForBucket(
      bucketID: snapshot.bucketID, now: currentFrame.captureTime)
    // Read once and use for the whole visit: schema, prompt, and hop admission
    // must agree, and a mid-visit flag flip must not desynchronize them. With
    // the flag off, schema and prompt are byte-identical to the pre-hop build.
    let retrievalHopEnabled = await MainActor.run { ContextBucketsFeature.isRetrievalHopEnabled }
    let prompt = ContextProactivityPromptBuilder.directorStablePrompt(
      snapshot: snapshot, allowLookup: retrievalHopEnabled)
    let uncachedPrompt = ContextProactivityPromptBuilder.directorVolatilePrompt(
      tasks: taskContext,
      frame: currentFrame,
      recentDeliveries: recentDeliveries)
    guard
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      await store.activeFenceIsValid(fence)
    else {
      await terminalize(
        deliveryID: deliveryID,
        decisionType: "silence",
        provenanceJSON: "{\"failure\":\"stale_visit\"}",
        state: "failed")
      return
    }
    // Settings can change while snapshot/frame/task context is assembled. Rebuild the
    // free gate immediately before the paid model call so disabling notifications,
    // snoozing, or becoming paywalled never spends director budget.
    let evaluationGate = await MainActor.run { Self.liveDeliveryGateInput() }
    let evaluationReason = ContextDeliveryBudget.freeGate(input: evaluationGate)
    guard evaluationReason == .allowed else {
      log("Context director suppressed before model: \(evaluationReason.rawValue)")
      await terminalize(
        deliveryID: deliveryID,
        decisionType: "silence",
        provenanceJSON: "{\"failure\":\"pre_model_gate\"}",
        state: "suppressed")
      return
    }
    let cacheKey = "bucket:\(snapshot.bucketID):v\(snapshot.version)"
    do {
      var result = try await client.complete(
        operation: ModelQoS.Proactivity.reasoningOperation,
        prompt: prompt,
        uncachedPrompt: uncachedPrompt,
        imageData: currentFrame.jpegData,
        jsonSchema: Self.schema(allowLookup: retrievalHopEnabled),
        cacheKey: cacheKey,
        maxCompletionTokens: 800,
        authorizationSnapshot: authorizationSnapshot)
      await ContextProactivityTelemetry.record(result)
      guard
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
        await store.activeFenceIsValid(fence)
      else {
        await terminalize(
          deliveryID: deliveryID,
          decisionType: "silence",
          provenanceJSON: "{\"failure\":\"stale_visit\"}",
          state: "failed")
        return
      }
      let firstDecision = try JSONDecoder().decode(
        ContextDirectorDecision.self, from: Data(result.content.utf8)
      ).clamped()
      var decision = firstDecision
      var retrievedRefAllowlist: Set<String> = []
      var retrievalProvenance: [String: Any]? = nil
      // The single bounded retrieval hop: at most one retrieval and one further
      // director call per visit, and only when the director asked for one.
      // `plan` is the sole admission and this is the sole second call site, so
      // a second response requesting another lookup has nowhere to loop to.
      if let lookupQuery = ContextDirectorRetrievalHop.plan(
        lookupQuery: firstDecision.lookupQuery,
        flagEnabled: retrievalHopEnabled,
        priorHops: 0)
      {
        let hop = await performRetrievalHop(
          query: lookupQuery,
          stablePrompt: prompt,
          volatilePrompt: uncachedPrompt,
          imageData: currentFrame.jpegData,
          cacheKey: cacheKey,
          fence: fence,
          authorizationSnapshot: authorizationSnapshot)
        // A failed, empty, or gated hop keeps the first decision untouched:
        // retrieval may upgrade a decision, never lose one.
        decision = ContextDirectorRetrievalHop.finalDecision(
          first: firstDecision, second: hop.decision)
        retrievedRefAllowlist = hop.allowedRefs
        retrievalProvenance = hop.provenance
        if let secondResult = hop.result { result = secondResult }
        // The owner/fence guard above ran before the hop, and the hop spans a
        // retrieval round trip plus a second model call. Ownership can be revoked
        // or the visit can end inside that window, so the same guard must run
        // again before anything is persisted — otherwise falling back to the
        // first decision would deliver against context the pre-hop code would
        // have refused. Re-checked here rather than trusting the hop to report
        // staleness, so a future failure path cannot quietly bypass it.
        guard
          RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
          await store.activeFenceIsValid(fence)
        else {
          await terminalize(
            deliveryID: deliveryID,
            decisionType: "silence",
            provenanceJSON: "{\"failure\":\"stale_visit\"}",
            state: "failed")
          return
        }
      }
      // Bucket refs keep today's validation path untouched; retrieved-namespace
      // refs validate only against the allowlist of items quoted to this very
      // call, which is empty unless the hop completed.
      let citedRefs = ContextDirectorRetrievalHop.partitionCitedRefs(decision.bucketEntryRefs)
      let entryRefs = await store.validatedEntryRefs(
        citedRefs.bucket, bucketID: snapshot.bucketID)
      let retrievedRefs = ContextDirectorRetrievalHop.validatedRetrievedRefs(
        citedRefs.retrieved, allowed: retrievedRefAllowlist)
      let factIDs =
        decision.decision == "silence"
        ? []
        : await store.validatedFactIDs(
          decision.factIDs,
          snapshotFacts: snapshot.validatedFacts,
          bucketID: snapshot.bucketID)
      var provenance: [String: Any] = [
        "bucket_id": snapshot.bucketID,
        "bucket_version_id": snapshot.versionID,
        "bucket_entry_refs": entryRefs,
        "fact_ids": factIDs,
        "reasoning": decision.reasoning,
        "provider_model": ContextProactivityTelemetry.boundedProviderModel(result.providerModel),
        "cached_tokens": result.usage.cachedTokens,
        "cache_write_tokens": result.usage.cacheWriteTokens,
      ]
      if var hopProvenance = retrievalProvenance {
        hopProvenance["cited_refs"] = retrievedRefs
        provenance["retrieval"] = hopProvenance
      }
      let provenanceData = try JSONSerialization.data(withJSONObject: provenance, options: [.sortedKeys])
      let provenanceJSON = String(data: provenanceData, encoding: .utf8) ?? "{}"
      try await store.completeDelivery(
        id: deliveryID, decisionType: decision.decision, provenanceJSON: provenanceJSON,
        message: decision.message, state: "model_completed")
      if decision.decision == "silence" {
        try await store.completeDelivery(
          id: deliveryID, decisionType: decision.decision, provenanceJSON: provenanceJSON,
          message: nil, state: "suppressed")
        return
      }
      // Deliberately evaluated on bucket refs alone: a delivery must still stand
      // on at least one bucket entry and one validated bucket fact, exactly as
      // before the retrieval hop existed. Retrieved refs are additive citations
      // and can never substitute for bucket grounding.
      guard ContextDirectorGrounding.permitsNonSilence(entryRefs: entryRefs, factIDs: factIDs) else {
        try await store.completeDelivery(
          id: deliveryID, decisionType: "silence", provenanceJSON: provenanceJSON,
          message: nil, state: "suppressed")
        return
      }
      try await store.completeDelivery(
        id: deliveryID, decisionType: decision.decision, provenanceJSON: provenanceJSON,
        message: decision.message, state: "policy_approved")
      guard
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
        await store.activeFenceIsValid(fence),
        let ownerID = await MainActor.run(body: { RuntimeOwnerIdentity.currentOwnerId() })
      else {
        await terminalize(
          deliveryID: deliveryID,
          decisionType: "silence",
          provenanceJSON: "{\"failure\":\"stale_visit\"}",
          state: "failed")
        return
      }
      // Rebuild free-gate inputs immediately before presentation so a mid-flight
      // master-off / quiet-hours / snooze / paywall change still suppresses.
      let presentationGate = await MainActor.run { Self.liveDeliveryGateInput() }
      let presentationReason = ContextDeliveryBudget.freeGate(input: presentationGate)
      guard presentationReason == .allowed else {
        log("Context director suppressed before presentation: \(presentationReason.rawValue)")
        try await store.completeDelivery(
          id: deliveryID, decisionType: decision.decision, provenanceJSON: provenanceJSON,
          message: decision.message, state: "suppressed")
        return
      }
      let finalPresentationPreflight = await presentationPreflight(ownerID)
      guard finalPresentationPreflight == .queued else {
        log("Context director suppressed before graduation: presentation_unavailable")
        try await store.completeDelivery(
          id: deliveryID,
          decisionType: decision.decision,
          provenanceJSON: provenanceJSON,
          message: decision.message,
          state: "suppressed")
        return
      }
      // Durable canonical candidates must exist before an interactive
      // task_candidate notification can be queued or tapped.
      var graduation = CandidateGraduationReason.graduated
      if decision.decision == "task_candidate" {
        graduation = await CandidateSink.shared.graduateValidatedFacts(
          deliveryID: deliveryID,
          factIDs: factIDs,
          authorizationSnapshot: authorizationSnapshot)
      }
      guard
        CandidateSinkDeliveryGate.mayPresentInteractively(
          decisionType: decision.decision,
          graduation: graduation)
      else {
        await recordGraduationFailure(
          deliveryID: deliveryID,
          decisionType: decision.decision,
          provenanceJSON: provenanceJSON,
          message: decision.message,
          reason: graduation)
        return
      }
      // Graduation and system-surface preflight can both await. Rebuild every
      // free gate once more at the actual handoff so master-off, snooze, paywall,
      // or another proactive presentation wins the race.
      let handoffGate = await MainActor.run { Self.liveDeliveryGateInput() }
      guard ContextDeliveryBudget.freeGate(input: handoffGate) == .allowed else {
        try await store.completeDelivery(
          id: deliveryID, decisionType: decision.decision, provenanceJSON: provenanceJSON,
          message: decision.message, state: "suppressed")
        return
      }
      // The bounded hop is the last writer of `decision`, so hand the main actor
      // the settled value rather than this actor's mutable binding: the callbacks
      // below outlive the handoff, and capturing the variable makes their reads
      // race with any later write to it.
      let presentedDecision = decision
      let presentation = await MainActor.run {
        let context = FloatingBarNotificationContext(
          sourceTitle: presentedDecision.title,
          assistantId: "context-director",
          contextSummary: presentedDecision.reasoning,
          detail: (entryRefs + retrievedRefs).joined(separator: ", "),
          provenanceRef: deliveryID)
        return NotificationService.shared.presentContextDirectorNotification(
          ownerID: ownerID,
          title: presentedDecision.title,
          message: presentedDecision.message,
          decisionType: presentedDecision.decision,
          context: context,
          onPresented: { [weak self] in
            guard let self else { return }
            Task {
              await self.completePresentedDelivery(
                deliveryID: deliveryID,
                decisionType: presentedDecision.decision,
                provenanceJSON: provenanceJSON,
                message: presentedDecision.message,
                authorizationSnapshot: authorizationSnapshot)
            }
          },
          onDropped: { [weak self] in
            guard let self else { return }
            Task {
              await self.terminalize(
                deliveryID: deliveryID,
                decisionType: "silence",
                provenanceJSON: "{\"failure\":\"notification_dropped\"}",
                state: "failed")
            }
          })
      }
      switch presentation {
      case .presented:
        // Immediate presentation invokes onPresented; queued presentation invokes it later.
        return
      case .queued:
        // Keep the row policy-approved until the floating bar actually presents it.
        return
      case .suppressed, .windowUnavailable, .rejectedOwnerChange:
        // showNotification invokes onDropped exactly once for these refusal paths.
        return
      }
    } catch {
      await recordDirectorFailure(deliveryID: deliveryID, error: error)
      // Network and model failures stay user-silent; provenance carries the class.
    }
  }

  private struct RetrievalHopOutcome {
    /// The final decision from the second call, or nil when the first stands.
    let decision: ContextDirectorDecision?
    /// Refs of the items actually quoted to the second call. Empty otherwise,
    /// so retrieved-namespace citations fail closed whenever no hop completed.
    let allowedRefs: Set<String>
    let provenance: [String: Any]
    let result: ProactiveLaneResult?
  }

  /// Runs retrieval and, when it returned anything, exactly one more director
  /// call. Non-throwing on purpose: every failure path returns a nil decision,
  /// which leaves the already-decoded first decision in force. The provenance
  /// object always records what the hop attempted so a delivered citation of a
  /// retrieved ref remains auditable from the delivery row alone.
  private func performRetrievalHop(
    query: String,
    stablePrompt: String,
    volatilePrompt: String,
    imageData: Data?,
    cacheKey: String,
    fence: ContextVisitFence,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async -> RetrievalHopOutcome {
    func abandoned(_ items: [ContextRetrievedItem], failure: String?) -> RetrievalHopOutcome {
      RetrievalHopOutcome(
        decision: nil,
        allowedRefs: [],
        provenance: ContextDirectorRetrievalHop.provenance(
          query: query, items: items, citedRefs: [], hopCompleted: false, failure: failure),
        result: nil)
    }
    let items = await retrieve(query, authorizationSnapshot)
    guard let section = ContextDirectorRetrievalHop.promptSection(query: query, items: items) else {
      return abandoned(items, failure: "empty_results")
    }
    guard
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      await store.activeFenceIsValid(fence)
    else { return abandoned(items, failure: "stale_visit") }
    // Retrieval awaited the network; rebuild the free gate before the second
    // paid call so disabling notifications, snoozing, or becoming paywalled
    // mid-hop never spends more director budget.
    let hopGate = await MainActor.run { Self.liveDeliveryGateInput() }
    guard ContextDeliveryBudget.freeGate(input: hopGate) == .allowed else {
      return abandoned(items, failure: "pre_model_gate")
    }
    do {
      // Identical stable prompt and cache key as the first call, so the second
      // call re-reads the same cached prefix. The retrieved section is volatile
      // and rides only in the uncached suffix, below the volatile prompt, which
      // keeps it under the untrusted preamble that opens the stable prompt.
      let result = try await client.complete(
        operation: ModelQoS.Proactivity.reasoningOperation,
        prompt: stablePrompt,
        uncachedPrompt: volatilePrompt + "\n\n" + section,
        imageData: imageData,
        jsonSchema: Self.schema(allowLookup: true),
        cacheKey: cacheKey,
        maxCompletionTokens: 800,
        authorizationSnapshot: authorizationSnapshot)
      await ContextProactivityTelemetry.record(result)
      let decision = try JSONDecoder().decode(
        ContextDirectorDecision.self, from: Data(result.content.utf8)
      ).clamped()
      return RetrievalHopOutcome(
        decision: decision,
        allowedRefs: Set(items.map(\.ref)),
        provenance: ContextDirectorRetrievalHop.provenance(
          query: query, items: items, citedRefs: [], hopCompleted: true, failure: nil),
        result: result)
    } catch {
      let classification = ProactiveLaneFailureClassification.classify(error)
      log("Context director retrieval hop failed, keeping first decision: \(classification.logDescription)")
      return abandoned(items, failure: classification.failure)
    }
  }

  func recordGraduationFailure(
    deliveryID: String,
    decisionType: String,
    provenanceJSON: String,
    message: String?,
    reason: CandidateGraduationReason
  ) async {
    log(
      "Context director suppressed before presentation: candidate_graduation_failed reason=\(reason.rawValue)"
    )
    _ = try? await store.completeDelivery(
      id: deliveryID,
      decisionType: decisionType,
      provenanceJSON: CandidateGraduationProvenance.mergingFailure(
        into: provenanceJSON, reason: reason),
      message: message,
      state: "failed")
  }

  func recordDirectorFailure(deliveryID: String, error: Error) async {
    let classification = ProactiveLaneFailureClassification.classify(error)
    log(
      "Context director \(ModelQoS.Proactivity.reasoningOperation) failed: \(classification.logDescription)")
    await terminalize(
      deliveryID: deliveryID,
      decisionType: "silence",
      provenanceJSON: classification.provenanceJSON,
      state: "failed")
  }

  nonisolated static func presentationSurfaceAvailable(
    _ result: OwnerBoundNotificationPresentationResult
  ) -> Bool {
    result == .queued
  }

  private func terminalize(
    deliveryID: String,
    decisionType: String,
    provenanceJSON: String,
    state: String
  ) async {
    // completeDelivery returns whether an advanceable row moved; terminalize is best-effort.
    _ = try? await store.completeDelivery(
      id: deliveryID,
      decisionType: decisionType,
      provenanceJSON: provenanceJSON,
      message: nil,
      state: state)
  }

  private func completePresentedDelivery(
    deliveryID: String,
    decisionType: String,
    provenanceJSON: String,
    message: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async {
    // onPresented is the authoritative observation that the interruption became
    // visible. A queued card can legitimately paint after its source visit has
    // ended, so only owner isolation remains relevant at this boundary.
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      await terminalize(
        deliveryID: deliveryID,
        decisionType: "silence",
        provenanceJSON: "{\"failure\":\"stale_owner\"}",
        state: "failed")
      return
    }
    do {
      let advanced = try await store.completeDelivery(
        id: deliveryID, decisionType: decisionType, provenanceJSON: provenanceJSON,
        message: message, state: "delivered")
      // A late onPresented after failed/suppressed must not revive delivery state.
      // task_candidate graduation already ran before presentation.
      guard advanced else { return }
    } catch {
      await terminalize(
        deliveryID: deliveryID,
        decisionType: decisionType,
        provenanceJSON: provenanceJSON,
        state: "failed")
    }
  }

  @MainActor
  static func liveDeliveryGateInput() -> ContextDeliveryGateInput {
    let frequencyLevel = NotificationService.currentFrequencyLevel()
    return ContextDeliveryGateInput(
      masterEnabled: NotificationService.areNotificationsEnabled(),
      frequencyLevel: frequencyLevel,
      paywalled: AppState.isPaywalledEffective,
      cooldownSeconds: ContextDeliveryBudget.cooldownSeconds(frequencyLevel: frequencyLevel),
      dailyLimit: ContextDeliveryBudget.dailyLimit(
        frequencyLevel: frequencyLevel,
        planMultiplier: FloatingBarUsageLimiter.proactiveBudgetMultiplier()),
      lastGlobalPresentationAt: NotificationService.shared.lastProactivePresentationAtForCurrentOwner())
  }

  static var schema: [String: Any] { schema(allowLookup: false) }

  static func schema(allowLookup: Bool) -> [String: Any] {
    var properties: [String: Any] = [
      "decision": ["type": "string", "enum": ["suggest", "insight", "task_candidate", "resurface", "silence"]],
      "title": ["type": "string"],
      "message": ["type": "string"],
      "reasoning": ["type": "string"],
      "bucket_entry_refs": ["type": "array", "items": ["type": "string"]],
      "fact_ids": ["type": "array", "items": ["type": "string"]],
    ]
    var required = ["decision", "title", "message", "reasoning", "bucket_entry_refs", "fact_ids"]
    if allowLookup {
      // Strict structured output requires every declared property to be listed
      // as required, so the prompt tells the model to answer "" for no lookup.
      // With the retrieval flag off the field is absent entirely, keeping the
      // request byte-identical to today.
      properties["lookup_query"] = ["type": "string"]
      required.append("lookup_query")
    }
    return [
      "type": "object",
      "properties": properties,
      "required": required,
      "additionalProperties": false,
    ]
  }
}

struct ContextVisitDwellAdmission {
  private var inFlightVisitIDs: Set<Int64> = []

  mutating func begin(visitID: Int64) -> Bool {
    inFlightVisitIDs.insert(visitID).inserted
  }

  mutating func finish(visitID: Int64) {
    inFlightVisitIDs.remove(visitID)
  }
}
