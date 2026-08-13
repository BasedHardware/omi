import Foundation
@preconcurrency import GRDB

struct ContextDirectorDecision: Codable, Equatable, Sendable {
  let decision: String
  let title: String
  let message: String
  let reasoning: String
  let bucketEntryRefs: [String]
  let factIDs: [String]

  enum CodingKeys: String, CodingKey {
    case decision, title, message, reasoning
    case bucketEntryRefs = "bucket_entry_refs"
    case factIDs = "fact_ids"
  }

  func clamped() -> ContextDirectorDecision {
    ContextDirectorDecision(
      decision: decision,
      title: String(title.prefix(120)),
      message: String(message.prefix(600)),
      reasoning: String(reasoning.prefix(1_200)),
      bucketEntryRefs: bucketEntryRefs.prefix(20).map { String($0.prefix(200)) },
      factIDs: factIDs.prefix(20).map { String($0.prefix(200)) })
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
  private var dwellAdmission = ContextVisitDwellAdmission()
  private let dwellNanoseconds: UInt64

  init(
    client: ProactiveLaneClient,
    store: ContextBucketStore,
    dwellNanoseconds: UInt64 = 8_000_000_000,
    presentationPreflight: @escaping @Sendable (String) async -> OwnerBoundNotificationPresentationResult = {
      ownerID in
      await NotificationService.shared.contextDirectorPresentationPreflight(ownerID: ownerID)
    }
  ) {
    self.client = client
    self.store = store
    self.dwellNanoseconds = dwellNanoseconds
    self.presentationPreflight = presentationPreflight
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
    let prompt = ContextProactivityPromptBuilder.directorStablePrompt(snapshot: snapshot)
    let uncachedPrompt = ContextProactivityPromptBuilder.directorVolatilePrompt(
      tasks: taskContext,
      frame: currentFrame)
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
    do {
      let result = try await client.complete(
        operation: ModelQoS.Proactivity.reasoningOperation,
        prompt: prompt,
        uncachedPrompt: uncachedPrompt,
        imageData: currentFrame.jpegData,
        jsonSchema: Self.schema,
        cacheKey: "bucket:\(snapshot.bucketID):v\(snapshot.version)",
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
      let decision = try JSONDecoder().decode(ContextDirectorDecision.self, from: Data(result.content.utf8)).clamped()
      let entryRefs = await store.validatedEntryRefs(
        decision.bucketEntryRefs, bucketID: snapshot.bucketID)
      let factIDs =
        decision.decision == "silence"
        ? []
        : await store.validatedFactIDs(
          decision.factIDs,
          snapshotFacts: snapshot.validatedFacts,
          bucketID: snapshot.bucketID)
      let provenance: [String: Any] = [
        "bucket_id": snapshot.bucketID,
        "bucket_version_id": snapshot.versionID,
        "bucket_entry_refs": entryRefs,
        "fact_ids": factIDs,
        "reasoning": decision.reasoning,
        "provider_model": ContextProactivityTelemetry.boundedProviderModel(result.providerModel),
        "cached_tokens": result.usage.cachedTokens,
        "cache_write_tokens": result.usage.cacheWriteTokens,
      ]
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
      var graduationSucceeded = true
      if decision.decision == "task_candidate" {
        graduationSucceeded = await CandidateSink.shared.graduateValidatedFacts(
          deliveryID: deliveryID,
          factIDs: factIDs,
          authorizationSnapshot: authorizationSnapshot)
      }
      guard
        CandidateSinkDeliveryGate.mayPresentInteractively(
          decisionType: decision.decision,
          graduationSucceeded: graduationSucceeded)
      else {
        log("Context director suppressed before presentation: candidate_graduation_failed")
        try await store.completeDelivery(
          id: deliveryID,
          decisionType: "silence",
          provenanceJSON: "{\"failure\":\"candidate_graduation_failed\"}",
          message: decision.message,
          state: "failed")
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
      let presentation = await MainActor.run {
        let context = FloatingBarNotificationContext(
          sourceTitle: decision.title,
          assistantId: "context-director",
          contextSummary: decision.reasoning,
          detail: entryRefs.joined(separator: ", "),
          provenanceRef: deliveryID)
        return NotificationService.shared.presentContextDirectorNotification(
          ownerID: ownerID,
          title: decision.title,
          message: decision.message,
          decisionType: decision.decision,
          context: context,
          onPresented: { [weak self] in
            guard let self else { return }
            Task {
              await self.completePresentedDelivery(
                deliveryID: deliveryID,
                decisionType: decision.decision,
                provenanceJSON: provenanceJSON,
                message: decision.message,
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
      snoozed: FloatingControlBarManager.shared.isSnoozed,
      paywalled: AppState.isPaywalledEffective,
      cooldownSeconds: ContextDeliveryBudget.cooldownSeconds(frequencyLevel: frequencyLevel),
      dailyLimit: ContextDeliveryBudget.dailyLimit(
        frequencyLevel: frequencyLevel,
        planMultiplier: FloatingBarUsageLimiter.proactiveBudgetMultiplier()),
      lastGlobalPresentationAt: NotificationService.shared.lastProactivePresentationAtForCurrentOwner())
  }

  static var schema: [String: Any] {
    [
      "type": "object",
      "properties": [
        "decision": ["type": "string", "enum": ["suggest", "insight", "task_candidate", "resurface", "silence"]],
        "title": ["type": "string"],
        "message": ["type": "string"],
        "reasoning": ["type": "string"],
        "bucket_entry_refs": ["type": "array", "items": ["type": "string"]],
        "fact_ids": ["type": "array", "items": ["type": "string"]],
      ],
      "required": ["decision", "title", "message", "reasoning", "bucket_entry_refs", "fact_ids"],
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
