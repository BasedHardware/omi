import Foundation

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

actor ContextProactivityEngine {
  static let shared = ContextProactivityEngine(client: .shared, store: .shared)
  private let client: ProactiveLaneClient
  private let store: ContextBucketStore
  private var inFlightBuckets: Set<String> = []
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
    guard let bucketID = fence.bucketID, !inFlightBuckets.contains(bucketID) else { return }
    inFlightBuckets.insert(bucketID)
    defer { inFlightBuckets.remove(bucketID) }
    do { try await Task.sleep(nanoseconds: dwellNanoseconds) } catch { return }
    do { try await store.markVisitSettled(fence) } catch { return }
    guard await store.fenceIsValid(fence), let snapshot = await store.snapshot(for: fence) else { return }
    // Facts are the only source of notification worthiness. A bucket containing
    // ambient narrative alone cannot purchase a frontier-model call.
    guard snapshot.notifyWorthiness > 0, !snapshot.validatedFacts.isEmpty else { return }
    guard
      let currentFrame = await MainActor.run(body: {
        AssistantCoordinator.shared.trackedFrameForDirector(startedAt: fence.startedAt)
      })
    else { return }

    let gate = await MainActor.run { () -> ContextDeliveryGateInput in
      let components = Calendar.current.dateComponents([.hour, .minute], from: Date())
      return ContextDeliveryGateInput(
        masterEnabled: NotificationService.areNotificationsEnabled(),
        frequencyLevel: NotificationService.currentFrequencyLevel(),
        snoozed: FloatingControlBarManager.shared.isSnoozed,
        paywalled: AppState.isPaywalledEffective,
        minuteOfDay: (components.hour ?? 0) * 60 + (components.minute ?? 0),
        cooldownSeconds: AssistantSettings.shared.cooldownIntervalSeconds)
    }
    let attempt: ContextDeliveryAttempt
    do { attempt = try await store.beginDeliveryAttempt(fence: fence, snapshot: snapshot, gate: gate) } catch { return }
    guard attempt.reason == .allowed, let deliveryID = attempt.id else { return }

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
    do {
      let result = try await client.complete(
        operation: ModelQoS.Proactivity.reasoningOperation,
        prompt: prompt,
        imageData: currentFrame.jpegData,
        jsonSchema: Self.schema,
        cacheKey: "bucket:\(snapshot.bucketID):v\(snapshot.version)",
        maxCompletionTokens: 800)
      await ContextProactivityTelemetry.record(result)
      guard await store.fenceIsValid(fence) else { return }
      let decision = try JSONDecoder().decode(ContextDirectorDecision.self, from: Data(result.content.utf8)).clamped()
      let entryRefs = await store.validatedEntryRefs(
        decision.bucketEntryRefs, bucketID: snapshot.bucketID)
      let provenance: [String: Any] = [
        "bucket_id": snapshot.bucketID,
        "bucket_version_id": snapshot.versionID,
        "bucket_entry_refs": entryRefs,
        "fact_ids": decision.factIDs,
        "reasoning": decision.reasoning,
        "provider_model": result.providerModel,
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
      guard let ownerID = await MainActor.run(body: { RuntimeOwnerIdentity.currentOwnerId() }) else { return }
      let delivered = await MainActor.run {
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
          context: context)
      }
      try await store.completeDelivery(
        id: deliveryID, decisionType: decision.decision, provenanceJSON: provenanceJSON,
        message: decision.message, state: delivered ? "delivered" : "suppressed")
      if delivered, decision.decision == "task_candidate" {
        await CandidateSink.shared.graduateValidatedFacts(deliveryID: deliveryID, factIDs: decision.factIDs)
      }
    } catch {
      try? await store.completeDelivery(
        id: deliveryID, decisionType: "silence", provenanceJSON: "{\"failure\":\"network_or_parse\"}",
        message: nil, state: "failed")
      // Network and model failures are intentionally silent.
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
