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
  private var dwellAdmission = ContextVisitDwellAdmission()
  private let dwellNanoseconds: UInt64

  init(
    client: ProactiveLaneClient,
    store: ContextBucketStore,
    dwellNanoseconds: UInt64 = 8_000_000_000
  ) {
    self.client = client
    self.store = store
    self.dwellNanoseconds = dwellNanoseconds
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
    let gate = await MainActor.run { () -> ContextDeliveryGateInput in
      let components = Calendar.current.dateComponents([.hour, .minute], from: Date())
      let frequencyLevel = NotificationService.currentFrequencyLevel()
      return ContextDeliveryGateInput(
        masterEnabled: NotificationService.areNotificationsEnabled(),
        frequencyLevel: frequencyLevel,
        snoozed: FloatingControlBarManager.shared.isSnoozed,
        paywalled: AppState.isPaywalledEffective,
        minuteOfDay: (components.hour ?? 0) * 60 + (components.minute ?? 0),
        activePeriod: NotificationService.currentActivePeriod(),
        cooldownSeconds: ContextDeliveryBudget.cooldownSeconds(frequencyLevel: frequencyLevel))
    }
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
    guard snapshot.notifyWorthiness > 0, !snapshot.validatedFacts.isEmpty else { return }
    guard
      let currentFrame = await MainActor.run(body: {
        AssistantCoordinator.shared.trackedFrameForDirector(startedAt: fence.startedAt)
      })
    else { return }

    let attempt: ContextDeliveryAttempt
    do { attempt = try await store.beginDeliveryAttempt(fence: fence, snapshot: snapshot, gate: gate) } catch { return }
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
      (TasksStore.shared.overdueTasks + TasksStore.shared.todaysTasks).prefix(20)
        .map { "- \($0.description)" }.joined(separator: "\n")
    }
    let stableBucket = String(data: ContextBucketPromptAssembler.assemble(snapshot), encoding: .utf8) ?? ""
    let prompt = """
      \(ScreenDerivedContent.untrustedPreamble)
      Decide whether interrupting now adds concrete value. Return silence unless the validated
      facts support a specific, timely action. Use only supplied bucket-entry refs.

      \(stableBucket)

      == OPEN OR OVERDUE TASKS ==
      \(taskContext)

      == CURRENT FRAME METADATA ==
      App: \(currentFrame.appName)
      Window: \(currentFrame.windowTitle ?? "")
      """
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
    do {
      let result = try await client.complete(
        operation: ModelQoS.Proactivity.reasoningOperation,
        prompt: prompt,
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
      let provenance: [String: Any] = [
        "bucket_id": snapshot.bucketID,
        "bucket_version_id": snapshot.versionID,
        "bucket_entry_refs": entryRefs,
        "fact_ids": decision.factIDs,
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
      guard !entryRefs.isEmpty else {
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
                factIDs: decision.factIDs,
                fence: fence,
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
        await completePresentedDelivery(
          deliveryID: deliveryID,
          decisionType: decision.decision,
          provenanceJSON: provenanceJSON,
          message: decision.message,
          factIDs: decision.factIDs,
          fence: fence,
          authorizationSnapshot: authorizationSnapshot)
      case .queued:
        // Keep the row policy-approved until the floating bar actually presents it.
        return
      case .suppressed, .windowUnavailable, .rejectedOwnerChange:
        try await store.completeDelivery(
          id: deliveryID, decisionType: decision.decision, provenanceJSON: provenanceJSON,
          message: decision.message, state: "suppressed")
      }
    } catch {
      await terminalize(
        deliveryID: deliveryID,
        decisionType: "silence",
        provenanceJSON: "{\"failure\":\"network_or_parse\"}",
        state: "failed")
      // Network and model failures are intentionally silent.
    }
  }

  private func terminalize(
    deliveryID: String,
    decisionType: String,
    provenanceJSON: String,
    state: String
  ) async {
    try? await store.completeDelivery(
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
    factIDs: [String],
    fence: ContextVisitFence,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async {
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
    do {
      try await store.completeDelivery(
        id: deliveryID, decisionType: decisionType, provenanceJSON: provenanceJSON,
        message: message, state: "delivered")
      if decisionType == "task_candidate" {
        await CandidateSink.shared.graduateValidatedFacts(
          deliveryID: deliveryID,
          factIDs: factIDs,
          authorizationSnapshot: authorizationSnapshot)
      }
    } catch {
      await terminalize(
        deliveryID: deliveryID,
        decisionType: decisionType,
        provenanceJSON: provenanceJSON,
        state: "failed")
    }
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
