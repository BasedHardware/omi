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
  /// Open tasks this notification is about, as supplied `task:<id>` handles.
  ///
  /// Optional for the same reason as `lookupQuery`: a response predating the
  /// field still decodes. Always filtered through
  /// `ContextDirectorTaskRefs.resolvable` before it is stored or rendered.
  var taskRefs: [String]? = nil

  enum CodingKeys: String, CodingKey {
    case decision, title, message, reasoning
    case bucketEntryRefs = "bucket_entry_refs"
    case factIDs = "fact_ids"
    case lookupQuery = "lookup_query"
    case taskRefs = "task_refs"
  }

  /// Retrieved-ref citations belong in `bucket_entry_refs`; the model
  /// occasionally inlines them into the visible text ("... omi.me/desktop.
  /// [memory:3fe5b70f-...]"), where they read as debris. Stripped
  /// deterministically rather than re-prompted.
  private static func strippingInlineRefs(_ text: String) -> String {
    text.replacingOccurrences(
      of: #"\s*\[(?:memory|conversation|chunk|entry|fact|task):[^\]]{1,200}\]"#,
      with: "",
      options: .regularExpression
    ).trimmingCharacters(in: .whitespacesAndNewlines)
  }

  func clamped() -> ContextDirectorDecision {
    ContextDirectorDecision(
      decision: decision,
      title: String(Self.strippingInlineRefs(title).prefix(120)),
      message: String(Self.strippingInlineRefs(message).prefix(600)),
      reasoning: String(reasoning.prefix(1_200)),
      bucketEntryRefs: bucketEntryRefs.prefix(20).map { String($0.prefix(200)) },
      factIDs: factIDs.prefix(20).map { String($0.prefix(200)) },
      lookupQuery: lookupQuery.map {
        String($0.prefix(ContextDirectorRetrievalHop.maximumQueryLength))
      },
      taskRefs: taskRefs.map {
        $0.prefix(ContextDirectorTaskRefs.maximumCount).map { String($0.prefix(200)) }
      })
  }
}

enum ContextDirectorEligibility {
  static func permitsEvaluation(of snapshot: ContextBucketSnapshot) -> Bool {
    snapshot.notifyWorthiness > 0 && !snapshot.validatedFacts.isEmpty
  }
}

enum ContextDirectorGrounding {
  /// Grounding requirement, per decision type.
  ///
  /// The old rule demanded a bucket-entry ref AND a validated-fact ref for every
  /// non-silence decision. But a resurface grounds on an *open task* — supplied
  /// in the prompt, not citable as a bucket entry — connected to the current
  /// context, so its natural citation is the validated fact(s) evidencing the
  /// connection, with no entry ref at all. Measured on two independent
  /// installations: every suppressed row with non-empty fact_ids is a decision
  /// the model made to speak that this guard overrode (the silence path forcibly
  /// empties fact_ids), and there were 9 of them in our dogfood window and 7 of
  /// 76 on an independent beta install — including "This is an overdue open task
  /// with a timely connection to the active overnight fleetctl workflow", the
  /// exact class resurface exists for. Cross-workstream pooling being enabled
  /// did not prevent the vetoes, so the guard itself was the cause.
  ///
  /// Deliberately NOT relaxed to a blanket OR: insight, suggest, and
  /// task_candidate make new claims about bucket content and keep the full
  /// anti-hallucination invariant (at least one entry ref and one fact ref).
  /// Resurface requires at least one citation of either kind — never zero.
  ///
  /// Retrieved refs are the one exception, for insight and suggest only. A
  /// retrieved ref validates against the allowlist of items the retrieval hop
  /// quoted to this very call, so it carries the same anti-hallucination
  /// guarantee as a bucket citation — but for content that by construction has
  /// no bucket entry or fact (the answer to a question the user is writing
  /// lives in their history, not in this screen's bucket). Before this
  /// exception, every retrieval-hop answer was structurally undeliverable:
  /// 10 of 10 hop evaluations in one 48h dogfood window ended suppressed,
  /// including one whose reasoning said the retrieved context "directly helps".
  /// task_candidate and resurface stay bucket-grounded: neither is the
  /// answer-delivery case, so each keeps its existing invariant unchanged.
  static func permitsNonSilence(
    decision: String, entryRefs: [String], factIDs: [String], retrievedRefs: [String] = []
  ) -> Bool {
    if decision == "resurface" {
      return !entryRefs.isEmpty || !factIDs.isEmpty
    }
    if decision == "insight" || decision == "suggest", !retrievedRefs.isEmpty {
      return true
    }
    return !entryRefs.isEmpty && !factIDs.isEmpty
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
      .map { ContextDirectorTaskContext(id: $0.id, description: $0.description, dueAt: $0.dueAt) }
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
    dwellNanoseconds: UInt64 = 2_000_000_000,
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
      await ContextProactivityTelemetry.recordGateRejection(reason: preflightReason, stage: .preflight)
      return
    }
    // Run-to-completion: a settled visit's evaluation survives a context switch
    // for a bounded window (the visit stays "fresh" while active or briefly
    // after a completed departure), so fast task-switchers can still receive
    // what their quota already paid for. Every later stage re-checks freshness.
    let freshness = await store.fenceFreshness(fence)
    guard
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      freshness.fresh,
      let snapshot = await store.snapshot(for: fence)
    else { return }
    // Facts are the only source of notification worthiness. A bucket containing
    // ambient narrative alone cannot purchase a frontier-model call.
    guard ContextDirectorEligibility.permitsEvaluation(of: snapshot) else { return }
    // After a departure the latest tracked frame can be the NEXT context's
    // screen. Sample the frame first, then re-read freshness and bound the
    // sample against it: the transition persists `endedAt` before the next
    // context's frame is tracked, so a bound applied to a post-sampling
    // freshness read cannot admit the wrong screen — while a bound computed
    // from the pre-snapshot read above could, when the switch lands between
    // that read and this lookup.
    guard
      let frameSample = await MainActor.run(body: {
        AssistantCoordinator.shared.trackedFrameForDirector(startedAt: fence.startedAt)
      })
    else { return }
    let frameFreshness = await store.fenceFreshness(fence)
    guard
      frameFreshness.fresh,
      AssistantCoordinator.frameMayGroundDirector(
        captureTime: frameSample.frame.captureTime,
        storedAt: frameSample.storedAt,
        startedAt: fence.startedAt,
        endedAt: frameFreshness.endedAt)
    else { return }
    await evaluateAndDeliver(
      fence: fence,
      snapshot: snapshot,
      currentFrame: frameSample.frame,
      authorizationSnapshot: authorizationSnapshot)
  }

  /// Departure-triggered evaluation: a departure extraction that just validated
  /// a notify-worthy fact evaluates the departed bucket immediately, grounded
  /// on the departing frame the extraction already holds, instead of waiting
  /// for the next revisit's dwell. Callers gate on
  /// `ContextDepartureEvaluationPolicy`; every delivery gate below and the
  /// freshness window still apply, so a departure older than the validity
  /// window dies exactly like any other stale evaluation. The dwell admission
  /// set serializes this against a still-running `contextEntered` evaluation of
  /// the same visit.
  func evaluateAfterDeparture(fence: ContextVisitFence, departingFrame: CapturedFrame) async {
    guard fence.bucketID != nil else { return }
    guard let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
      log("DepartureEvalDebug: no authorization snapshot")
      return
    }
    guard dwellAdmission.begin(visitID: fence.visitID) else {
      log("DepartureEvalDebug: dwell admission refused for visit \(fence.visitID)")
      return
    }
    defer { dwellAdmission.finish(visitID: fence.visitID) }
    let gate = await MainActor.run { Self.liveDeliveryGateInput() }
    let preflightReason = ContextDeliveryBudget.freeGate(input: gate)
    guard preflightReason == .allowed else {
      log("Context director suppressed before departure evaluation: \(preflightReason.rawValue)")
      return
    }
    let freshness = await store.fenceFreshness(fence)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      log("DepartureEvalDebug: authorization changed")
      return
    }
    guard freshness.fresh else {
      log("DepartureEvalDebug: fence stale")
      return
    }
    guard let snapshot = await store.snapshot(for: fence) else {
      log("DepartureEvalDebug: no snapshot")
      return
    }
    guard ContextDirectorEligibility.permitsEvaluation(of: snapshot) else {
      log(
        "DepartureEvalDebug: ineligible snapshot worthiness=\(snapshot.notifyWorthiness) facts=\(snapshot.validatedFacts.count)"
      )
      return
    }
    log("DepartureEvalDebug: proceeding to evaluateAndDeliver")
    await evaluateAndDeliver(
      fence: fence,
      snapshot: snapshot,
      currentFrame: departingFrame,
      authorizationSnapshot: authorizationSnapshot)
  }

  /// The shared post-settle tail of the director pipeline: presentation
  /// preflight, gate rebuilds, budget reservation, the model call (plus the
  /// bounded retrieval hop), grounding validation, and the presentation
  /// handoff. `contextEntered` reaches it after dwell/settle/frame lookup;
  /// `evaluateAfterDeparture` reaches it with the departing frame.
  private func evaluateAndDeliver(
    fence: ContextVisitFence,
    snapshot: ContextBucketSnapshot,
    currentFrame: CapturedFrame,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async {
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
      await ContextProactivityTelemetry.recordGateRejection(reason: attemptReason, stage: .attempt)
      return
    }

    let attempt: ContextDeliveryAttempt
    do {
      attempt = try await store.beginDeliveryAttempt(fence: fence, snapshot: snapshot, gate: attemptGate)
    } catch { return }
    guard attempt.reason == .allowed, let deliveryID = attempt.id else {
      log("Context director suppressed: \(attempt.reason.rawValue)")
      await ContextProactivityTelemetry.recordGateRejection(reason: attempt.reason, stage: .reservation)
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
    var recentDeliveries = await store.recentDeliveredForBucket(
      bucketID: snapshot.bucketID, now: currentFrame.captureTime)
    // The related-workstream section: validated facts from sibling buckets of
    // the visit's live workstream, quality-gated and quoted as non-citable
    // context. Read the flag once so section, dedup, and provenance agree; with
    // the flag off (or no live tag) the prompt is byte-identical to today.
    let workstreamPoolingEnabled = await MainActor.run {
      ContextBucketsFeature.isWorkstreamPoolingEnabled
    }
    var workstreamSection: String? = nil
    var workstreamProvenance: [String: Any]? = nil
    var pooledFactIDs: Set<String> = []
    if workstreamPoolingEnabled,
      let liveTag = await store.liveWorkstreamTag(for: fence, now: currentFrame.captureTime)
    {
      let selected = ContextWorkstreamPooling.select(
        await store.workstreamPool(
          tag: liveTag, excludingBucketID: snapshot.bucketID, now: currentFrame.captureTime),
        now: currentFrame.captureTime)
      if !selected.isEmpty {
        workstreamSection = ContextWorkstreamPooling.promptSection(
          tag: liveTag, items: selected, now: currentFrame.captureTime)
        pooledFactIDs = Set(selected.map(\.factID))
        workstreamProvenance = [
          "tag": liveTag,
          "pooled_fact_ids": selected.map(\.factID),
        ]
      }
      // Tag-aware dedup: with pooling, the same cross-app point is reachable
      // from every bucket carrying this tag, so sibling deliveries join the
      // bucket's own under the same prompt cap.
      let workstreamDeliveries = await store.recentDeliveredForWorkstream(
        tag: liveTag, excludingBucketID: snapshot.bucketID, now: currentFrame.captureTime)
      recentDeliveries = Array(
        (recentDeliveries + workstreamDeliveries)
          .sorted { $0.deliveredAt > $1.deliveredAt }
          .prefix(ContextBucketRecentDelivery.promptCap))
    }
    let candidatesEnabled = await MainActor.run {
      ContextBucketsFeature.isProactiveCandidatesEnabled
    }
    if candidatesEnabled {
      let tags = await store.workstreamTags(for: snapshot.bucketID)
      if !tags.isEmpty {
        // Lookup is cross-bucket by durable assignment; bucket-scoped delivery
        // memory would re-send a sibling's already-shown point.
        let assignedDeliveries = await store.recentDeliveredForAssignedWorkstreams(
          tags: tags, excludingBucketID: snapshot.bucketID, now: currentFrame.captureTime)
        recentDeliveries = Array(
          (recentDeliveries + assignedDeliveries)
            .sorted { $0.deliveredAt > $1.deliveredAt }
            .prefix(ContextBucketRecentDelivery.promptCap))
      }
      let armed = await store.armedCandidates(
        bucketID: snapshot.bucketID, tags: tags, now: currentFrame.captureTime)
      // A candidate can sit armed for up to 12 hours; the fact(s) it was
      // grounded in at write time may since have expired, been rejected, or
      // been superseded. Revalidate every grounding id against the current
      // bucket_facts state before treating a candidate as deliverable, so a
      // decayed candidate falls through to the director instead of gating
      // and presenting stale text with stale citations. Decline the stale
      // row so it cannot block the reconciler from writing a replacement.
      var grounded: [ContextProactiveCandidate] = []
      for candidate in armed {
        if await store.groundingFactIDsAreCurrentlyValid(
          candidate.groundingFactIDs, bucketID: candidate.bucketID, now: currentFrame.captureTime)
        {
          grounded.append(candidate)
        } else {
          await store.declineCandidate(id: candidate.id, now: currentFrame.captureTime)
        }
      }
      let recentMessages = recentDeliveries.compactMap(\.message)
      // A question the user is typing RIGHT NOW outranks resurfacing an armed
      // candidate: the candidate short-circuit used to consume the evaluation
      // (and with the candidate show ceiling exhausted, silence it), so the
      // typed question never reached the director or its forced retrieval —
      // the bucket went permanently mute for answers while any candidate
      // stayed armed. The candidate stays armed for the next quiet evaluation.
      let pendingUserQuestion =
        await MainActor.run { ContextBucketsFeature.isRetrievalHopEnabled }
        && ContextDirectorRetrievalHop.forcedLookupQuery(
          validatedFacts: snapshot.validatedFacts) != nil
      if !pendingUserQuestion,
        let candidate = ContextProactiveCandidateLookup.firstDeliverable(
          candidates: grounded, recentMessages: recentMessages)
      {
        await evaluateCandidateAndDeliver(
          candidate: candidate,
          deliveryID: deliveryID,
          fence: fence,
          snapshot: snapshot,
          currentFrame: currentFrame,
          recentDeliveries: recentDeliveries,
          authorizationSnapshot: authorizationSnapshot,
          ownerID: ownerID)
        return
      }
    }
    // Read once and use for the whole visit: schema, prompt, and hop admission
    // must agree, and a mid-visit flag flip must not desynchronize them. With
    // the flag off, schema and prompt are byte-identical to the pre-hop build.
    let retrievalHopEnabled = await MainActor.run { ContextBucketsFeature.isRetrievalHopEnabled }
    if !retrievalHopEnabled {
      let diag = await MainActor.run {
        "enabled=\(ContextBucketsFeature.isEnabled) nonprod=\(AppBuild.isNonProduction) env=\(ProcessInfo.processInfo.environment["OMI_FORCE_BUCKET_RETRIEVAL"] ?? "unset")"
      }
      log("ForcedLookupDebug: retrieval hop DISABLED (\(diag))")
    }
    let prompt = ContextProactivityPromptBuilder.directorStablePrompt(
      snapshot: snapshot, allowLookup: retrievalHopEnabled)
    let envSignal = await MainActor.run {
      EnvironmentalSpeakerAnalyzer.analyze(segments: LiveTranscriptMonitor.shared.segments)
    }
    var volatileExtras = workstreamSection.map { "\n\n" + $0 } ?? ""
    if candidatesEnabled {
      let selected = ContextWorkstreamPooling.selectRecent(
        await store.recentContextPool(
          excludingBucketID: snapshot.bucketID, now: currentFrame.captureTime),
        now: currentFrame.captureTime)
      let fresh = selected.filter { !pooledFactIDs.contains($0.factID) }
      if let section = ContextWorkstreamPooling.recentContextPromptSection(
        items: fresh, now: currentFrame.captureTime)
      {
        volatileExtras += "\n\n" + section
      }
    }
    let uncachedPrompt =
      ContextProactivityPromptBuilder.directorVolatilePrompt(
        tasks: taskContext,
        frame: currentFrame,
        recentDeliveries: recentDeliveries,
        visitCount: snapshot.visitCount,
        environmentalSignal: envSignal)
      + volatileExtras
    guard
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      await store.fenceFreshness(fence).fresh
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
      await ContextProactivityTelemetry.recordGateRejection(reason: evaluationReason, stage: .preModel)
      await terminalize(
        deliveryID: deliveryID,
        decisionType: "silence",
        provenanceJSON: "{\"failure\":\"pre_model_gate\"}",
        state: "suppressed")
      return
    }
    let cacheKey = ContextPromptCacheKey.director
    // Forced retrieval: a validated user-authored-question fact skips the
    // first bare call and evaluates once WITH the retrieved answer attached.
    // The bare first call proved stochastically willing to silence a typed
    // question on the repetition/already-visible checks across live runs,
    // while the retrieval-attached form delivered every time — so when the
    // client can already see the question in the validated facts, asking the
    // model whether to look it up is a coin flip that costs the delivery.
    var forcedRetrievalAllowlist: Set<String> = []
    var forcedRetrievalItems: [ContextRetrievedItem] = []
    var forcedRetrievalProvenance: [String: Any]? = nil
    var forcedLookup: ContextDirectorRetrievalHop.ForcedLookup? = nil
    var effectiveUncachedPrompt = uncachedPrompt
    if retrievalHopEnabled {
      log("ForcedLookupDebug: facts=\(snapshot.validatedFacts.count)")
    }
    if retrievalHopEnabled,
      let lookup = ContextDirectorRetrievalHop.forcedLookupQuery(
        validatedFacts: snapshot.validatedFacts)
    {
      log(
        "ForcedLookupDebug: firing queryChars=\(lookup.query.count) questionFacts=\(lookup.questionFactIDs.count)"
      )
      forcedLookup = lookup
      let items = await retrieve(lookup.query, authorizationSnapshot)
      if let section = ContextDirectorRetrievalHop.promptSection(query: lookup.query, items: items) {
        // A direct question invalidates the anti-nagging guard by design, and
        // in live runs the model kept reading the identical answer cards in
        // the recent-deliveries list as "delivered repeatedly" and silencing.
        // The forced evaluation therefore omits that list mechanically instead
        // of asking the model to discount it. Every other volatile section
        // (workstream, recent-context pool) is preserved so pooling context
        // and its provenance stay truthful.
        let answerPrompt = ContextProactivityPromptBuilder.directorVolatilePrompt(
          tasks: taskContext,
          frame: currentFrame,
          recentDeliveries: [],
          visitCount: snapshot.visitCount,
          environmentalSignal: envSignal)
        effectiveUncachedPrompt = answerPrompt + volatileExtras + "\n\n" + section
        forcedRetrievalAllowlist = Set(items.map(\.ref))
        forcedRetrievalItems = items
        forcedRetrievalProvenance = ContextDirectorRetrievalHop.provenance(
          query: lookup.query, items: items, citedRefs: [], hopCompleted: true, failure: nil)
      }
    }
    do {
      var result = try await client.complete(
        operation: ModelQoS.Proactivity.reasoningOperation,
        prompt: prompt,
        uncachedPrompt: effectiveUncachedPrompt,
        imageData: currentFrame.jpegData,
        jsonSchema: Self.schema(allowLookup: retrievalHopEnabled),
        cacheKey: cacheKey,
        maxCompletionTokens: 800,
        authorizationSnapshot: authorizationSnapshot)
      await ContextProactivityTelemetry.record(result)
      guard
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
        await store.fenceFreshness(fence).fresh
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
      var retrievedRefAllowlist: Set<String> = forcedRetrievalAllowlist
      var retrievalProvenance: [String: Any]? = forcedRetrievalProvenance
      // The single bounded retrieval hop: at most one retrieval and one further
      // director call per visit, and only when the director asked for one.
      // `plan` is the sole admission and this is the sole second call site, so
      // a second response requesting another lookup has nowhere to loop to.
      if let lookupQuery = ContextDirectorRetrievalHop.plan(
        lookupQuery: firstDecision.lookupQuery,
        flagEnabled: retrievalHopEnabled,
        priorHops: forcedLookup == nil ? 0 : 1)
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
          await store.fenceFreshness(fence).fresh
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
      var retrievedRefs = ContextDirectorRetrievalHop.validatedRetrievedRefs(
        citedRefs.retrieved, allowed: retrievedRefAllowlist)
      // Forced-question answers: attribute the citation the model omitted when
      // the message provably carries retrieved content (see impliedCitations).
      if retrievedRefs.isEmpty, !forcedRetrievalItems.isEmpty,
        decision.decision == "insight" || decision.decision == "suggest"
      {
        retrievedRefs = ContextDirectorRetrievalHop.impliedCitations(
          message: decision.message, items: forcedRetrievalItems,
          question: forcedLookup?.query ?? "")
      }
      let factIDs =
        decision.decision == "silence"
        ? []
        : await store.validatedFactIDs(
          decision.factIDs,
          snapshotFacts: snapshot.validatedFacts,
          bucketID: snapshot.bucketID)
      // Filtered against the tasks actually supplied on this visit. An invented
      // handle would render in chat as a "Task is no longer available"
      // tombstone instead of failing visibly, so an unresolvable ref is dropped
      // here rather than stored. Silence carries none, matching `factIDs`.
      let taskRefs =
        decision.decision == "silence"
        ? []
        : ContextDirectorTaskRefs.resolvable(decision.taskRefs ?? [], supplied: taskContext)
      var provenance: [String: Any] = [
        "bucket_id": snapshot.bucketID,
        "bucket_version_id": snapshot.versionID,
        "bucket_entry_refs": entryRefs,
        "fact_ids": factIDs,
        "task_refs": taskRefs,
        "reasoning": decision.reasoning,
        "provider_model": ContextProactivityTelemetry.boundedProviderModel(result.providerModel),
        "cached_tokens": result.usage.cachedTokens,
        "cache_write_tokens": result.usage.cacheWriteTokens,
      ]
      if var hopProvenance = retrievalProvenance {
        hopProvenance["cited_refs"] = retrievedRefs
        provenance["retrieval"] = hopProvenance
      }
      if let workstreamProvenance {
        provenance["workstream"] = workstreamProvenance
      }
      let provenanceData = try JSONSerialization.data(withJSONObject: provenance, options: [.sortedKeys])
      let provenanceJSON = String(data: provenanceData, encoding: .utf8) ?? "{}"
      try await store.completeDelivery(
        id: deliveryID, decisionType: decision.decision, provenanceJSON: provenanceJSON,
        message: decision.message, state: "model_completed")
      await ContextProactivityTelemetry.recordDirectorDecision(decision.decision)
      if decision.decision == "silence" {
        try await store.completeDelivery(
          id: deliveryID, decisionType: decision.decision, provenanceJSON: provenanceJSON,
          message: nil, state: "suppressed")
        if forcedLookup == nil {
          // Silence with no forced lookup right after typing is the signature
          // of an extraction that missed the typed question; the plugin may
          // grant one re-extraction for the burst (see
          // ContextDwellRefreshPolicy.questionRescueGrant).
          await MainActor.run {
            NotificationCenter.default.post(
              name: ProactiveAssistantsPlugin.contextEvalSilentWithoutLookup, object: nil)
          }
        }
        return
      }
      // Retrieved refs are hop-allowlist-validated above, so an insight or
      // suggest citing one is grounded in content actually quoted to the model
      // — the answer-delivery case bucket refs cannot cover. When the guard
      // vetoes, the row records what the model actually decided and why it was
      // suppressed — a forced silence was previously indistinguishable from a
      // model-chosen one, which made the veto rate invisible until it was
      // recovered from the fact_ids side effect.
      guard
        ContextDirectorGrounding.permitsNonSilence(
          decision: decision.decision, entryRefs: entryRefs, factIDs: factIDs,
          retrievedRefs: retrievedRefs)
      else {
        provenance["suppression_reason"] = "grounding_veto"
        provenance["model_decision"] = decision.decision
        let vetoData = try JSONSerialization.data(withJSONObject: provenance, options: [.sortedKeys])
        try await store.completeDelivery(
          id: deliveryID, decisionType: "silence",
          provenanceJSON: String(data: vetoData, encoding: .utf8) ?? provenanceJSON,
          message: nil, state: "suppressed")
        return
      }
      try await store.completeDelivery(
        id: deliveryID, decisionType: decision.decision, provenanceJSON: provenanceJSON,
        message: decision.message, state: "policy_approved")
      guard
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
        await store.fenceFreshness(fence).fresh,
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
        await ContextProactivityTelemetry.recordGateRejection(
          reason: presentationReason, stage: .presentation)
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
      let handoffReason = ContextDeliveryBudget.freeGate(input: handoffGate)
      guard handoffReason == .allowed else {
        await ContextProactivityTelemetry.recordGateRejection(reason: handoffReason, stage: .handoff)
        try await store.completeDelivery(
          id: deliveryID, decisionType: decision.decision, provenanceJSON: provenanceJSON,
          message: decision.message, state: "suppressed")
        return
      }
      // The bounded hop is the last writer of `decision`, so hand the main actor
      // the settled value rather than this actor's mutable binding: the callbacks
      // below outlive the handoff, and capturing the variable makes their reads
      // race with any later write to it.
      let answeredQuestionFactIDs = ContextDirectorRetrievalHop.consumableQuestionFacts(
        forced: forcedLookup,
        retrievalCompleted: forcedRetrievalProvenance != nil,
        citedRetrievedRefs: retrievedRefs)
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
                authorizationSnapshot: authorizationSnapshot,
                consumeFactIDs: answeredQuestionFactIDs)
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

  /// Deterministic candidate + small yes/no gate. `show == false` (or a
  /// malformed/failed gate) suppresses and returns — the director is not also
  /// run, so one visit never pays for two decisions.
  private func evaluateCandidateAndDeliver(
    candidate: ContextProactiveCandidate,
    deliveryID: String,
    fence: ContextVisitFence,
    snapshot: ContextBucketSnapshot,
    currentFrame: CapturedFrame,
    recentDeliveries: [ContextBucketRecentDelivery],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    ownerID: String
  ) async {
    let evaluationGate = await MainActor.run { Self.liveDeliveryGateInput() }
    let evaluationReason = ContextDeliveryBudget.freeGate(input: evaluationGate)
    guard evaluationReason == .allowed else {
      log("Context candidate gate suppressed before model: \(evaluationReason.rawValue)")
      await ContextProactivityTelemetry.recordGateRejection(reason: evaluationReason, stage: .preModel)
      await terminalize(
        deliveryID: deliveryID,
        decisionType: "silence",
        provenanceJSON: "{\"failure\":\"pre_model_gate\"}",
        state: "suppressed")
      return
    }
    // Candidate-mix ceiling, checked before the gate's model call so a capped
    // candidate costs no tokens. The candidate is deliberately NOT declined:
    // it stays armed for a window with headroom, unlike a gate refusal, which
    // retires it. The visit's delivery row still terminates as suppressed.
    let candidateShows = await store.candidateDeliveriesInWindow(now: currentFrame.captureTime)
    guard candidateShows < ContextDeliveryBudget.candidateDailyShowCeiling else {
      log("Context candidate suppressed before model: candidate_show_ceiling")
      await terminalize(
        deliveryID: deliveryID,
        decisionType: "silence",
        provenanceJSON: "{\"failure\":\"candidate_show_ceiling\"}",
        state: "suppressed")
      // A ceiling-capped candidate consumed an evaluation that may have been
      // owed to a typed question the extraction missed — the same rescue as a
      // silent director evaluation applies.
      await MainActor.run {
        NotificationCenter.default.post(
          name: ProactiveAssistantsPlugin.contextEvalSilentWithoutLookup, object: nil)
      }
      return
    }
    guard
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      await store.fenceFreshness(fence).fresh
    else {
      await terminalize(
        deliveryID: deliveryID,
        decisionType: "silence",
        provenanceJSON: "{\"failure\":\"stale_visit\"}",
        state: "failed")
      return
    }
    // The facts the candidate was written from, not just this visit's facts:
    // the gate is judging a claim made at write time, and without its original
    // evidence it could only compare the claim against the current screen —
    // which is how 13 of 14 live rejections came to read "not supported by the
    // current screen" for candidates that were correct when written.
    let groundingFacts = await store.groundingFactStatements(
      candidate.groundingFactIDs, bucketID: candidate.bucketID)
    do {
      let result = try await client.complete(
        operation: ModelQoS.Proactivity.reasoningOperation,
        prompt: ContextProactiveCandidateGate.prompt(
          message: candidate.message,
          groundingFacts: groundingFacts,
          validatedFacts: snapshot.validatedFacts,
          recentDeliveries: recentDeliveries),
        imageData: currentFrame.jpegData,
        jsonSchema: ContextProactiveCandidateGate.schema,
        // 400, not 120: the reasoning model bills its thinking into completion
        // tokens. Measured directly against the same model with this exact
        // prompt shape: at 120 the call finished with `finish_reason=length`,
        // 120/120 tokens spent on reasoning, and EMPTY content in 2 of 3
        // attempts — which parses as malformed and silently suppresses the
        // candidate. At 400 every attempt finished clean (33-174 reasoning
        // tokens plus the small JSON body). Live provenance shows the same
        // degenerate shape (a bare "false" reason) at the old cap.
        maxCompletionTokens: 400,
        authorizationSnapshot: authorizationSnapshot)
      await ContextProactivityTelemetry.record(result)
      // The gate awaited the model; ownership can be revoked or the visit can
      // end inside that window, exactly as for the director's own call.
      // Re-check before parsing or persisting anything.
      guard
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
        await store.fenceFreshness(fence).fresh
      else {
        await terminalize(
          deliveryID: deliveryID,
          decisionType: "silence",
          provenanceJSON: "{\"failure\":\"stale_visit\"}",
          state: "failed")
        return
      }
      // An unparseable body is not a decision. The reasoning model bills its
      // thinking into completion tokens, so a budget that runs out returns
      // `finish_reason=length` with empty content — which is silence about the
      // question, not an answer of "no". Treating it as "no" retired the
      // candidate permanently (`declineCandidate` below), so one truncated call
      // destroyed a notification that no later visit could ever recover.
      // Suppress this visit, leave the candidate armed, and let a later visit
      // ask again or let it expire on its own.
      guard let decision = ContextProactiveCandidateGate.parse(result.content) else {
        try await store.completeDelivery(
          id: deliveryID, decisionType: "silence",
          provenanceJSON: "{\"reason\":\"malformed_gate_response\",\"source\":\"candidate\"}",
          message: nil, state: "suppressed")
        return
      }
      let reason = String(decision.reason.prefix(1_200))
      var provenance: [String: Any] = [
        "source": "candidate",
        "candidate_id": candidate.id,
        "reason": reason,
      ]
      if let tag = candidate.workstreamTag {
        provenance["workstream"] = tag
      } else {
        provenance["workstream"] = NSNull()
      }
      let provenanceData = try JSONSerialization.data(
        withJSONObject: provenance, options: [.sortedKeys])
      let provenanceJSON = String(data: provenanceData, encoding: .utf8) ?? "{}"
      guard decision.show else {
        // A declined candidate must not be re-selected (and re-billed for
        // another paid gate call) on every later visit until it naturally
        // expires: retire it now instead of leaving it armed.
        await store.declineCandidate(id: candidate.id, now: currentFrame.captureTime)
        try await store.completeDelivery(
          id: deliveryID, decisionType: "silence", provenanceJSON: provenanceJSON,
          message: nil, state: "suppressed")
        return
      }
      let message = String(candidate.message.prefix(600))
      let title = String(message.prefix(120))
      try await store.completeDelivery(
        id: deliveryID, decisionType: "insight", provenanceJSON: provenanceJSON,
        message: message, state: "model_completed")
      await ContextProactivityTelemetry.recordDirectorDecision("insight")
      try await store.completeDelivery(
        id: deliveryID, decisionType: "insight", provenanceJSON: provenanceJSON,
        message: message, state: "policy_approved")
      guard
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
        await store.fenceFreshness(fence).fresh
      else {
        await terminalize(
          deliveryID: deliveryID,
          decisionType: "silence",
          provenanceJSON: "{\"failure\":\"stale_visit\"}",
          state: "failed")
        return
      }
      let presentationGate = await MainActor.run { Self.liveDeliveryGateInput() }
      let presentationReason = ContextDeliveryBudget.freeGate(input: presentationGate)
      guard presentationReason == .allowed else {
        log("Context candidate suppressed before presentation: \(presentationReason.rawValue)")
        await ContextProactivityTelemetry.recordGateRejection(
          reason: presentationReason, stage: .presentation)
        try await store.completeDelivery(
          id: deliveryID, decisionType: "insight", provenanceJSON: provenanceJSON,
          message: message, state: "suppressed")
        return
      }
      let finalPresentationPreflight = await presentationPreflight(ownerID)
      guard finalPresentationPreflight == .queued else {
        log("Context candidate suppressed before graduation: presentation_unavailable")
        try await store.completeDelivery(
          id: deliveryID, decisionType: "insight", provenanceJSON: provenanceJSON,
          message: message, state: "suppressed")
        return
      }
      let handoffGate = await MainActor.run { Self.liveDeliveryGateInput() }
      let handoffReason = ContextDeliveryBudget.freeGate(input: handoffGate)
      guard handoffReason == .allowed else {
        await ContextProactivityTelemetry.recordGateRejection(reason: handoffReason, stage: .handoff)
        try await store.completeDelivery(
          id: deliveryID, decisionType: "insight", provenanceJSON: provenanceJSON,
          message: message, state: "suppressed")
        return
      }
      // Every gate between the model's `show` decision and here can still
      // suppress the delivery. Consume the candidate only now, once nothing
      // ahead of the actual presentation call can drop it silently — so a
      // suppression above this line leaves the candidate armed for the next
      // visit instead of losing it for its whole remaining lifetime.
      let consumed = await store.consumeCandidate(id: candidate.id, now: currentFrame.captureTime)
      guard consumed else {
        try await store.completeDelivery(
          id: deliveryID, decisionType: "silence", provenanceJSON: provenanceJSON,
          message: nil, state: "suppressed")
        return
      }
      let factIDs = candidate.groundingFactIDs.map { "fact:\($0)" }
      let presentation = await MainActor.run {
        let context = FloatingBarNotificationContext(
          sourceTitle: title,
          assistantId: "context-director",
          contextSummary: reason,
          detail: factIDs.joined(separator: ", "),
          provenanceRef: deliveryID)
        return NotificationService.shared.presentContextDirectorNotification(
          ownerID: ownerID,
          title: title,
          message: message,
          decisionType: "insight",
          context: context,
          onPresented: { [weak self] in
            guard let self else { return }
            Task {
              await self.completePresentedDelivery(
                deliveryID: deliveryID,
                decisionType: "insight",
                provenanceJSON: provenanceJSON,
                message: message,
                authorizationSnapshot: authorizationSnapshot)
            }
          },
          onDropped: { [weak self] in
            guard let self else { return }
            Task {
              // Claimed at consume time; this callback means it was never shown.
              await self.store.restoreCandidate(
                id: candidate.id, now: currentFrame.captureTime)
              await self.terminalize(
                deliveryID: deliveryID,
                decisionType: "silence",
                provenanceJSON: "{\"failure\":\"notification_dropped\"}",
                state: "failed")
            }
          })
      }
      switch presentation {
      case .presented, .queued:
        return
      case .suppressed, .windowUnavailable, .rejectedOwnerChange:
        // onDropped already ran (and restores) for these refusal paths.
        return
      }
    } catch {
      await recordDirectorFailure(deliveryID: deliveryID, error: error)
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
      await store.fenceFreshness(fence).fresh
    else { return abandoned(items, failure: "stale_visit") }
    // Retrieval awaited the network; rebuild the free gate before the second
    // paid call so disabling notifications, snoozing, or becoming paywalled
    // mid-hop never spends more director budget.
    let hopGate = await MainActor.run { Self.liveDeliveryGateInput() }
    let hopReason = ContextDeliveryBudget.freeGate(input: hopGate)
    guard hopReason == .allowed else {
      await ContextProactivityTelemetry.recordGateRejection(reason: hopReason, stage: .retrievalHop)
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
      decisionType: ContextDeliveryLifecycle.unresolvedDecisionType,
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
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    consumeFactIDs: [String] = []
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
      // A delivered answer consumes its question fact: an unanswered fact
      // re-forces retrieval on every dwell refresh with the anti-repetition
      // list omitted, repeating the identical card until the fact expired.
      // Expiring it also lets a RE-typed question re-validate (the duplicate
      // check ignores expired facts), so asking again still gets an answer.
      for factID in consumeFactIDs {
        try? await store.expireFact(id: factID)
      }
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

  /// `title` and `message` are the only two fields the user ever reads, and they
  /// were the only two declared as bare strings. A delivered notification read
  /// "Insight / PR blocked, needs review" — the decision type answered back as a
  /// title, and a body naming no pull request — which nothing in the schema or
  /// the prompt forbade.
  ///
  /// These descriptions were measured together with the prompt's naming rule
  /// (see `ContextProactivityPromptBuilder.directorStablePrompt`). Alone they
  /// took title naming from 34/58 to 60/61 spoken runs but cost body naming
  /// (58/58 → 57/61): the model moved the identifier into the title instead of
  /// carrying it in both. The prompt rule is what holds both at 67/67, so the two
  /// halves ship together and neither should be removed on its own.
  static func schema(allowLookup: Bool) -> [String: Any] {
    var properties: [String: Any] = [
      "decision": ["type": "string", "enum": ["suggest", "insight", "task_candidate", "resurface", "silence"]],
      "title": [
        "type": "string",
        "description":
          "The specific thing this is about, as the supplied context names it: the pull request "
          + "number and repository, the sender and subject of the thread, the title of the "
          + "document, the file and branch, the name and time of the meeting. Never a category "
          + "word such as \"Insight\", \"Suggestion\", or \"Task\". Empty only when the decision "
          + "is silence.",
      ],
      "message": [
        "type": "string",
        "description":
          "What the user should know or do, written so it still makes sense away from the screen "
          + "that produced it. Name the same specific thing the title names, then say what "
          + "changed or what to do about it. A message that identifies only a category -- \"PR "
          + "blocked\", \"respond to the email\", \"document needs review\" -- is useless. Empty "
          + "only when the decision is silence.",
      ],
      "reasoning": ["type": "string"],
      "bucket_entry_refs": ["type": "array", "items": ["type": "string"]],
      "fact_ids": ["type": "array", "items": ["type": "string"]],
      // Strict structured output requires every declared property to be
      // required, so the contract tells the model to answer [] for "about none
      // of the listed tasks" rather than omitting the key.
      "task_refs": ["type": "array", "items": ["type": "string"]],
    ]
    var required = [
      "decision", "title", "message", "reasoning", "bucket_entry_refs", "fact_ids", "task_refs",
    ]
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

/// Admission for the departure-triggered director evaluation: only a departure
/// extraction that just validated a fact at or above the worthiness threshold,
/// with the feature flag on, buys an immediate evaluation of the departed
/// bucket. Everything else waits for the next revisit's dwell as before.
enum ContextDepartureEvaluationPolicy {
  static let worthinessThreshold = 0.6

  static func triggers(maximumValidatedWorthiness: Double, flagEnabled: Bool) -> Bool {
    flagEnabled && maximumValidatedWorthiness >= worthinessThreshold
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
