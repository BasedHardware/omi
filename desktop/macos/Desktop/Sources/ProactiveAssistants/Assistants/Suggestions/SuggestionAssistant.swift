import AppKit
import Foundation

/// Live proactive suggestions.
///
/// Unlike `InsightAssistant`, which polls on a 600s timer regardless of what the user is
/// doing, this assistant is purely event-driven: it evaluates only when the user lands in
/// a new context and has settled there. An idle user costs nothing, which is the cost
/// contract established by `4584c0a9` ("no notifications → no screen analysis").
///
/// It is also grounded. Before judging, it assembles what Omi already knows — memories,
/// open commitments — so a suggestion can carry information that is not already on the
/// user's screen. That is the difference between a card worth reading and the ~25%
/// click-through that got the old surface switched off by default in `48239de8`.
actor SuggestionAssistant: ProactiveAssistant {
  // MARK: - ProactiveAssistant Protocol

  nonisolated let identifier = "suggestion"
  nonisolated let displayName = "Focus Notifications"

  var isEnabled: Bool {
    get async {
      // Deliberately independent of ContextBucketsFeature. The buckets rollout gated this
      // on `!ContextBucketsFeature.isEnabled`, betting the context director would replace
      // live suggestions — it delivered almost nothing, and with the flag at 100% of all
      // users focus nudges went silent fleet-wide with no error logged (Aug 13–14 2026).
      // If the director is ever meant to replace this assistant again, that must be an
      // explicit, evidenced change — never a side effect of a rollout flag.
      await MainActor.run {
        SuggestionAssistantSettings.shared.isEnabled
      }
    }
  }

  /// Opt into frames during the coordinator's post-context-switch delay.
  ///
  /// The shared delay (`AssistantSettings.analysisDelay`, 60s) exists so assistants do
  /// not analyze while the user is still moving around. A minute is far too long for a
  /// suggestion about the screen in front of you, so this assistant takes the frames and
  /// enforces its own, much shorter settle window instead (`SuggestionPacing.settleInterval`).
  var needsFrameDuringDelay: Bool {
    get async { true }
  }

  // MARK: - Properties

  private let geminiClient: GeminiClient
  private let telemetryModel: SuggestionAssistantTelemetry.Model

  /// Last observed notification frequency level, refreshed on every context switch and
  /// evaluation so synchronous gates can pace by level without an actor hop per frame.
  /// Defaults to Balanced so a not-yet-read level never triggers Maximum pacing.
  private var cachedFrequencyLevel: Int = 3

  private var dailyBudget = SuggestionDailyBudget()

  /// Set by `onContextSwitch`, consumed by the first frame that passes the gate.
  private var pendingContextSwitchAt: Date?
  private var pendingApp: String?
  private var pendingWindowTitle: String?

  private var lastEvaluationAt: Date?
  private var recentSuggestions: [SuggestionDeduplication.Remembered] = []

  /// The commitments handed to the evaluation currently in flight, kept so delivery can
  /// hold a `commitment` nudge to what the model was actually shown.
  private var commitmentsInFlight: [String] = []

  /// Goals, cached because grounding must stay off the network — a fetch on this path would
  /// blow through the window in which a suggestion is still about the current screen. A
  /// stale-but-present list is worth far more here than a fresh one that arrives late.
  private var cachedGoals: [String] = []
  /// The authorization the cached goals were fetched under. Revalidated at read time, not
  /// just at write time: an account switch between the fetch and the next evaluation must
  /// not put one user's goals in another user's prompt.
  private var cachedGoalsSnapshot: RuntimeOwnerAuthorizationSnapshot?
  private var lastGoalsRefresh = Date.distantPast
  private let goalsRefreshInterval: TimeInterval = 600

  private var cooldownInterval: TimeInterval {
    get async { await MainActor.run { SuggestionAssistantSettings.shared.cooldownInterval } }
  }

  private var minConfidence: Double {
    get async { await MainActor.run { SuggestionAssistantSettings.shared.minConfidence } }
  }

  private var systemPrompt: String {
    get async { await MainActor.run { SuggestionAssistantSettings.shared.analysisPrompt } }
  }

  // MARK: - Initialization

  init(apiKey: String? = nil) throws {
    let model = ModelQoS.Gemini.suggestions
    self.geminiClient = try GeminiClient(
      apiKey: apiKey,
      model: model,
      fallbackModel: "gemini-2.5-flash",
      workload: .maintenance
    )
    telemetryModel = SuggestionAssistantTelemetry.Model(configuredModel: model)
  }

  // MARK: - Trigger

  func onContextSwitch(departingFrame: CapturedFrame?, newApp: String, newWindowTitle: String?) async {
    pendingContextSwitchAt = SuggestionDwellAnchor.anchor(
      current: pendingContextSwitchAt,
      currentApp: pendingApp,
      currentWindowTitle: pendingWindowTitle,
      newApp: newApp,
      newWindowTitle: newWindowTitle,
      now: Date()
    )
    pendingApp = newApp
    pendingWindowTitle = newWindowTitle
    // Refreshed per switch so the synchronous `shouldAnalyze` gate can pace by level
    // without hopping actors on every frame.
    cachedFrequencyLevel = await MainActor.run { NotificationService.currentFrequencyLevel() }
  }

  /// Every branch here is mechanical. No model call happens until all of them pass, which
  /// is what makes the cost contract testable.
  func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool {
    guard let switchedAt = pendingContextSwitchAt else { return false }
    let settle = SuggestionPacing.settleInterval(frequencyLevel: cachedFrequencyLevel)
    guard Date().timeIntervalSince(switchedAt) >= settle else { return false }
    return true
  }

  func analyze(frame: CapturedFrame) async -> AssistantResult? {
    guard pendingContextSwitchAt != nil else { return nil }

    let enabled = await isEnabled
    let excluded = await MainActor.run { SuggestionAssistantSettings.shared.isAppExcluded(frame.appName) }
    let level = await MainActor.run { NotificationService.currentFrequencyLevel() }
    cachedFrequencyLevel = level
    let cooldown = SuggestionPacing.cooldown(base: await cooldownInterval, frequencyLevel: level)

    let now = Date()
    let dwell = pendingContextSwitchAt.map { now.timeIntervalSince($0) } ?? 0

    let decision = SuggestionGatePolicy.decide(
      isEnabled: enabled,
      isAppExcluded: excluded,
      now: now,
      lastEvaluationAt: SuggestionPacing.effectiveLastEvaluation(
        lastEvaluationAt: lastEvaluationAt,
        anchor: pendingContextSwitchAt,
        frequencyLevel: level),
      cooldown: cooldown,
      dwell: dwell,
      requiredDwell: SuggestionPacing.requiredDwell(frequencyLevel: level),
      evaluationsToday: dailyBudget.countToday(now: now),
      dailyBudget: SuggestionPacing.dailyEvaluationBudget(frequencyLevel: level)
    )

    guard decision.allowsEvaluation else {
      await MainActor.run {
        AnalyticsManager.shared.suggestionAssistantGateOutcome(.init(decision))
      }
      // Dwell and cooldown are "not yet", so the pending context survives to be retried on
      // a later frame. Everything else is "not at all" and is consumed here, otherwise a
      // blocked context re-checks on every capture tick.
      if decision != .skippedCooldown && decision != .skippedDwell {
        clearPendingContext()
      }
      log("Suggestion: skipped (\(decision)) app=\(frame.appName)")
      return nil
    }

    // Grounding is assembled BEFORE the spend decision, because it is free and it is the
    // spend decision. If Omi knows nothing about this context it has no advantage over the
    // user's own eyes, and a suggestion from that position is the ~25%-CTR noise that got
    // the old surface switched off.
    let grounding = await assembleGrounding(for: frame)
    guard !grounding.isEmpty else {
      clearPendingContext()
      await MainActor.run {
        AnalyticsManager.shared.suggestionAssistantGateOutcome(.noGrounding)
      }
      log("Suggestion: skipped (skippedNoGrounding) app=\(frame.appName)")
      return nil
    }

    await MainActor.run {
      AnalyticsManager.shared.suggestionAssistantGateOutcome(.eligible)
    }
    // Calm levels consume the context: one evaluation per arrival, then quiet until the
    // user moves somewhere new. Maximum re-arms so staying on the same feed keeps
    // producing nudges every cooldown interval — that sustained cadence is the level's
    // entire point, and cooldown + the daily budget still bound the spend.
    if !SuggestionPacing.rearmsAfterEvaluation(frequencyLevel: level) {
      clearPendingContext()
    }
    lastEvaluationAt = now
    dailyBudget.recordEvaluation(now: now)
    commitmentsInFlight = grounding.openCommitments

    do {
      return try await evaluate(frame: frame, grounding: grounding)
    } catch {
      logError("Suggestion: evaluation failed", error: error)
      return nil
    }
  }

  private func clearPendingContext() {
    pendingContextSwitchAt = nil
    pendingApp = nil
    pendingWindowTitle = nil
  }

  // MARK: - Grounding

  /// Assemble what Omi already knows, scoped to the current context.
  ///
  /// Every source here is on-device and FTS- or memory-backed, in the low-millisecond
  /// range. Nothing on this path touches the network: embedding search and the backend
  /// tool endpoints are deliberately excluded, because a 30s embed timeout would blow
  /// straight through the window in which a suggestion is still about the current screen.
  ///
  /// Best-effort by design — a source that fails contributes nothing rather than blocking
  /// the card, since a well-grounded suggestion that arrives after the user has moved on
  /// is worth less than a thinner one that arrives in time.
  private func assembleGrounding(for frame: CapturedFrame) async -> SuggestionGrounding {
    var grounding = SuggestionGrounding()

    // Overdue and due-today work is relevant regardless of what is on screen, and reading
    // it is free — it is already resident in the store.
    let alwaysRelevant = await MainActor.run {
      (TasksStore.shared.overdueTasks + TasksStore.shared.todaysTasks)
        .prefix(15)
        .map(Self.describeCommitment)
    }
    grounding.openCommitments = Array(alwaysRelevant)

    grounding.goals = currentOwnerGoals()
    refreshGoalsIfStale()

    // The window title is the topic or person the user is looking at. Without it there is
    // nothing to scope a search by, so the context-specific sources are skipped entirely
    // rather than searched with a meaningless query.
    guard let searchTerm = Self.groundingSearchTerm(for: frame) else {
      return grounding
    }

    let lookbackStart = Date().addingTimeInterval(-30 * 24 * 60 * 60)

    do {
      let commitments = try await ActionItemStorage.shared.searchFTS(
        query: searchTerm,
        limit: 10,
        includeCompleted: false
      )
      let scoped = commitments.map(\.description).filter { !grounding.openCommitments.contains($0) }
      grounding.openCommitments.append(contentsOf: scoped)
    } catch {
      logError("Suggestion: commitment grounding unavailable", error: error)
    }

    do {
      let memories = try await MemoryStorage.shared.searchLocalMemories(query: searchTerm, limit: 15)
      grounding.memories = memories.map(\.content)
    } catch {
      logError("Suggestion: memory grounding unavailable", error: error)
    }

    do {
      let screens = try await RewindDatabase.shared.search(
        query: searchTerm,
        startDate: lookbackStart,
        limit: 12
      )
      grounding.relatedScreens = screens.compactMap { Self.describeScreen($0, excluding: frame) }
    } catch {
      logError("Suggestion: screen-history grounding unavailable", error: error)
    }

    return grounding
  }

  /// Describe a commitment the way a person would say it out loud.
  ///
  /// Fire-and-forget goal refresh. Never awaited by grounding: the next evaluation gets the
  /// fresher list, this one is not delayed for it.
  ///
  /// Owner-scoped end to end. Goals are personal, and `getGoals()` documents that its
  /// short-lived shared cache is **not** owner-validated — an unsnapshotted call can hand
  /// back the previous account's goals, which would then sit in this cache and be pasted
  /// into the next owner's prompt for up to `goalsRefreshInterval`. So: capture a snapshot,
  /// fetch under it, and store only if that authorization is still current on arrival.
  private func refreshGoalsIfStale() {
    guard Date().timeIntervalSince(lastGoalsRefresh) >= goalsRefreshInterval else { return }
    guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
      cachedGoals = []
      cachedGoalsSnapshot = nil
      return
    }
    lastGoalsRefresh = Date()
    Task { [weak self] in
      do {
        let goals = try await APIClient.shared.getGoals(authorizationSnapshot: snapshot)
        let titles = goals.compactMap { goal -> String? in
          let title = goal.title.trimmingCharacters(in: .whitespacesAndNewlines)
          return title.isEmpty ? nil : title
        }
        await self?.storeGoals(titles, snapshot: snapshot)
      } catch {
        logError("Suggestion: goal grounding unavailable", error: error)
      }
    }
  }

  /// Drop the result outright if the account changed while the fetch was in flight.
  private func storeGoals(_ goals: [String], snapshot: RuntimeOwnerAuthorizationSnapshot) {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot) else {
      cachedGoals = []
      cachedGoalsSnapshot = nil
      lastGoalsRefresh = .distantPast
      log("Suggestion: dropped goal grounding from a superseded owner")
      return
    }
    cachedGoals = goals
    cachedGoalsSnapshot = snapshot
  }

  /// Cached goals, but only if they still belong to whoever is signed in right now.
  private func currentOwnerGoals() -> [String] {
    guard let snapshot = cachedGoalsSnapshot,
      RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot)
    else {
      if !cachedGoals.isEmpty {
        log("Suggestion: discarded cached goals after an owner change")
      }
      cachedGoals = []
      cachedGoalsSnapshot = nil
      lastGoalsRefresh = .distantPast
      return []
    }
    return cachedGoals
  }

  /// Describe a commitment the way a person would say it out loud.
  ///
  /// This string is what the model quotes, so an absolute date here comes back out in the
  /// card as "call dad (due 2026-08-10)" — a database row read aloud. Worse, the raw
  /// `ISO8601DateFormatter` rendered in UTC, so anything due after 8pm Eastern printed as
  /// *tomorrow*; the model then scored a due-today task as not-yet-urgent and it fell under
  /// the confidence bar. Relative phrasing fixes the voice and the timezone in one move,
  /// and it is what the model actually needs — it reasons about urgency, not calendars.
  private static func describeCommitment(_ task: TaskActionItem) -> String {
    guard let dueAt = task.dueAt else { return task.description }
    return "\(task.description) — \(SuggestionDueDescription.phrase(for: dueAt))"
  }

  /// One line per past screen: when, where, and a snippet of what was on it.
  private static func describeScreen(_ screenshot: Screenshot, excluding frame: CapturedFrame) -> String? {
    // Skip screens from the same window the user is looking at now — the model can already
    // see that, and it crowds out genuinely older context.
    if let title = screenshot.windowTitle, title == frame.windowTitle { return nil }

    let formatter = DateFormatter()
    formatter.dateFormat = "MMM d HH:mm"
    let when = formatter.string(from: screenshot.timestamp)
    let location = screenshot.windowTitle.map { "\(screenshot.appName) — \($0)" } ?? screenshot.appName
    guard let ocr = screenshot.ocrText, !ocr.isEmpty else { return "\(when) · \(location)" }
    let snippet = ocr.replacingOccurrences(of: "\n", with: " ").prefix(200)
    return "\(when) · \(location): \(snippet)"
  }

  /// Derive a search term from the window title, which is where the topic or person lives.
  /// Reuses the shared normalizer so spinners, timers and unread counts do not become
  /// search noise.
  private static func groundingSearchTerm(for frame: CapturedFrame) -> String? {
    guard let normalized = ContextDetection.normalizeWindowTitle(frame.windowTitle, appName: frame.appName) else {
      return nil
    }
    // Must be sanitized before it reaches FTS5 — see SuggestionSearchTerm.
    let sanitized = SuggestionSearchTerm.sanitize(normalized)
    // Very short titles ("Inbox", "New Tab") carry no signal worth searching on.
    guard sanitized.count >= 4 else { return nil }
    return sanitized
  }

  // MARK: - Judgment

  private func evaluate(frame: CapturedFrame, grounding: SuggestionGrounding) async throws -> SuggestionResult? {
    let prompt = buildPrompt(frame: frame, grounding: grounding)
    let systemPrompt = await systemPrompt
    let preview = SuggestionFramePreview.downscaledJPEG(from: frame.jpegData)
    let identity = SuggestionAssistantTelemetry.Identity()
    let shape = SuggestionAssistantTelemetry.EvaluationShape(
      model: telemetryModel,
      previewData: preview,
      grounding: grounding
    )
    await MainActor.run {
      AnalyticsManager.shared.suggestionAssistantEvaluationStarted(identity: identity, shape: shape)
    }

    let startedAt = Date()
    do {
      let response = try await geminiClient.sendRequest(
        prompt: prompt,
        imageData: preview,
        systemPrompt: systemPrompt,
        responseSchema: Self.responseSchema
      )
      guard let data = response.data(using: .utf8) else {
        throw SuggestionEvaluationError.invalidResponse
      }

      var result = try JSONDecoder().decode(SuggestionResult.self, from: data)
      let producedSuggestion = result.hasSuggestion && result.suggestion != nil
      let completedIdentity = producedSuggestion ? identity.withSuggestion() : identity
      result.telemetryIdentity = completedIdentity
      await MainActor.run {
        AnalyticsManager.shared.suggestionAssistantEvaluationCompleted(
          identity: completedIdentity,
          shape: shape,
          latency: Date().timeIntervalSince(startedAt),
          producedSuggestion: producedSuggestion
        )
      }
      return result
    } catch {
      await MainActor.run {
        AnalyticsManager.shared.suggestionAssistantEvaluationFailed(
          identity: identity,
          shape: shape,
          latency: Date().timeIntervalSince(startedAt),
          reason: SuggestionAssistantTelemetry.EvaluationFailureReason(error)
        )
      }
      throw error
    }
  }

  private func buildPrompt(frame: CapturedFrame, grounding: SuggestionGrounding) -> String {
    var sections: [String] = []

    sections.append(
      """
      == WHAT THE USER IS DOING RIGHT NOW ==
      App: \(frame.appName)
      Window: \(frame.windowTitle ?? "(no title)")
      The attached screenshot is their screen at this moment.
      """
    )

    let groundingText = grounding.promptSections()
    if !groundingText.isEmpty {
      sections.append(groundingText)
    }

    if !recentSuggestions.isEmpty {
      sections.append(
        "== RECENT SUGGESTIONS (do not repeat these) ==\n"
          + recentSuggestions.map(\.text).joined(separator: "\n")
      )
    }

    return sections.joined(separator: "\n\n")
  }

  private static let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
    type: "object",
    properties: [
      "has_suggestion": .init(
        type: "boolean",
        description: "True only if there is something genuinely worth saying right now."
      ),
      "suggestion": .init(
        type: "object",
        properties: [
          "suggestion": .init(type: "string", description: "The suggestion, under 100 characters."),
          "reasoning": .init(
            type: "string",
            description: "Why this is worth an interruption. Cite the specific thing on screen or in memory."
          ),
          "category": .init(
            type: "string",
            enum: ["commitment", "mistake", "opportunity", "connection", "other"],
            description: "Category of the suggestion."
          ),
          "confidence": .init(type: "number", description: "0.0-1.0 confidence."),
        ],
        required: ["suggestion", "category", "confidence"]
      ),
      "context_summary": .init(type: "string", description: "Brief summary of what the user is looking at."),
      "current_activity": .init(type: "string", description: "High-level description of the user's activity."),
    ],
    required: ["has_suggestion", "context_summary", "current_activity"]
  )

  // MARK: - Delivery

  func handleResult(_ result: AssistantResult, sendEvent: @escaping @Sendable (String, [String: Any]) -> Void) async {
    _ = await resolveDelivery(result, sendEvent: sendEvent)
  }

  /// Runs the delivery decision and reports what actually happened.
  ///
  /// The return value exists because "the model produced a suggestion" and "the user saw a
  /// card" are different claims. A probe that reports the former as success will call the
  /// delivery path verified while the confidence bar, dedup, or the commitment guard was
  /// silently dropping every card.
  @discardableResult
  private func resolveDelivery(
    _ result: AssistantResult,
    sendEvent: @escaping @Sendable (String, [String: Any]) -> Void
  ) async -> SuggestionAssistantTelemetry.DeliveryOutcome? {
    guard let result = result as? SuggestionResult else { return nil }
    guard result.hasSuggestion, let suggestion = result.suggestion else {
      log("Suggestion: nothing worth saying — \(result.currentActivity)")
      return nil
    }
    let telemetryIdentity = SuggestionAssistantTelemetry.NotificationIdentity(result.telemetryIdentity)
    let ownerID = RuntimeOwnerIdentity.currentOwnerId()
    let threshold = SuggestionPacing.minConfidence(
      base: await minConfidence, frequencyLevel: cachedFrequencyLevel)

    let outcome = SuggestionDeliveryPolicy.decide(
      hasOwner: ownerID != nil,
      confidence: suggestion.confidence,
      threshold: threshold,
      isDuplicate: SuggestionDeduplication.isDuplicate(
        suggestion.suggestion, of: recentSuggestions.map(\.text)),
      isGroundedCommitment: SuggestionCommitmentGuard.isGrounded(
        suggestion: suggestion.suggestion,
        category: suggestion.category,
        openCommitments: commitmentsInFlight
      )
    )

    let percent = Int(suggestion.confidence * 100)
    switch outcome {
    case .rejectedOwner:
      await emitDeliveryOutcome(.rejectedOwner, identity: telemetryIdentity)
      return outcome
    case .filteredLowConfidence:
      await emitDeliveryOutcome(.filteredLowConfidence, identity: telemetryIdentity)
      log("Suggestion: below bar [\(percent)% < \(Int(threshold * 100))%] \"\(suggestion.suggestion)\"")
      return outcome
    case .filteredDuplicate:
      await emitDeliveryOutcome(.filteredDuplicate, identity: telemetryIdentity)
      log("Suggestion: duplicate of a recent suggestion — \"\(suggestion.suggestion)\"")
      return outcome
    case .filteredUngroundedCommitment:
      await emitDeliveryOutcome(.filteredUngroundedCommitment, identity: telemetryIdentity)
      log(
        "Suggestion: ungrounded commitment [\(percent)%] — "
          + "no open commitment matches \"\(suggestion.suggestion)\""
      )
      return outcome
    case .delivered:
      break
    }

    // Re-read the owner immediately before delivering: an account switch between the
    // decision and the card must not put one user's commitment on another user's screen.
    guard let ownerID, RuntimeOwnerIdentity.currentOwnerId() == ownerID else {
      await emitDeliveryOutcome(.rejectedOwner, identity: telemetryIdentity)
      return .rejectedOwner
    }

    recentSuggestions = SuggestionDeduplication.remembering(
      .init(text: suggestion.suggestion, category: suggestion.category),
      in: recentSuggestions,
      frequencyLevel: cachedFrequencyLevel
    )

    await deliver(
      suggestion,
      result: result,
      ownerID: ownerID,
      telemetryIdentity: telemetryIdentity
    )
    return .delivered
  }

  private func emitDeliveryOutcome(
    _ outcome: SuggestionAssistantTelemetry.DeliveryOutcome,
    identity: SuggestionAssistantTelemetry.NotificationIdentity?
  ) async {
    guard let identity else { return }
    await MainActor.run {
      AnalyticsManager.shared.suggestionAssistantDeliveryOutcome(outcome, identity: identity)
    }
  }

  private func deliver(
    _ suggestion: ExtractedSuggestion,
    result: SuggestionResult,
    ownerID: String,
    telemetryIdentity: SuggestionAssistantTelemetry.NotificationIdentity?
  ) async {
    let context = FloatingBarNotificationContext(
      sourceTitle: "Focus",
      assistantId: identifier,
      sourceApp: nil,
      windowTitle: nil,
      contextSummary: result.contextSummary,
      currentActivity: result.currentActivity,
      reasoning: suggestion.reasoning,
      detail: suggestion.suggestion
    )

    log("Suggestion: delivering [\(Int(suggestion.confidence * 100))%] \"\(suggestion.suggestion)\"")

    await MainActor.run {
      NotificationService.shared.sendNotification(
        ownerID: ownerID,
        title: "Focus",
        message: suggestion.suggestion,
        assistantId: identifier,
        context: context,
        suggestionTelemetryIdentity: telemetryIdentity
      )
    }
  }

  // MARK: - Automation probe

  /// Run grounding → evaluation → delivery on a supplied frame, bypassing only the dwell
  /// and cooldown gates.
  ///
  /// Those two gates are pure functions with their own tests; everything downstream of them
  /// — real commitments from the store, the real prompt, a real model call, the confidence
  /// bar, dedup, the commitment guard, and real delivery through `NotificationService` — is
  /// the part that cannot be proven without spending money, and is therefore the part worth
  /// a probe. Verifying it otherwise requires holding a leisure window frontmost for 30s,
  /// which an agent cannot do without taking the user's focus.
  func probeEvaluateAndDeliver(
    frame: CapturedFrame,
    sendEvent: @escaping @Sendable (String, [String: Any]) -> Void
  ) async -> [String: String] {
    // The probe bypasses only timing gates for intentional QA. It retains every
    // privacy, user-choice, and spend boundary before the screenshot reaches a model.
    let assistantEnabled = await isEnabled
    let gateState = await MainActor.run {
      (
        SuggestionAssistantSettings.shared.isAppExcluded(frame.appName),
        NotificationService.areNotificationsEnabled(),
        NotificationService.currentFrequencyLevel()
      )
    }
    let now = Date()
    let decision = SuggestionGatePolicy.decide(
      isEnabled: assistantEnabled,
      isAppExcluded: gateState.0,
      now: now,
      lastEvaluationAt: nil,
      cooldown: 0,
      dwell: SuggestionPacing.requiredDwell(frequencyLevel: gateState.2),
      requiredDwell: SuggestionPacing.requiredDwell(frequencyLevel: gateState.2),
      evaluationsToday: dailyBudget.countToday(now: now),
      dailyBudget: SuggestionPacing.dailyEvaluationBudget(frequencyLevel: gateState.2))
    guard gateState.1, gateState.2 > 0, decision.allowsEvaluation else {
      if !gateState.1 { return ["outcome": "skipped_notifications_disabled"] }
      if gateState.2 == 0 { return ["outcome": "skipped_frequency_off"] }
      return ["outcome": SuggestionAssistantTelemetry.GateOutcome(decision).rawValue]
    }

    let grounding = await assembleGrounding(for: frame)
    commitmentsInFlight = grounding.openCommitments

    guard !grounding.isEmpty else {
      return ["outcome": "no_grounding", "commitments": "0"]
    }

    dailyBudget.recordEvaluation(now: now)

    let result: SuggestionResult?
    do {
      result = try await evaluate(frame: frame, grounding: grounding)
    } catch {
      return ["outcome": "evaluation_failed", "error": "\(error)"]
    }

    guard let result else {
      return ["outcome": "no_result", "commitments": "\(grounding.openCommitments.count)"]
    }
    guard result.hasSuggestion, let suggestion = result.suggestion else {
      return [
        "outcome": "declined",
        "activity": result.currentActivity,
        "commitments": "\(grounding.openCommitments.count)",
      ]
    }

    // Report what delivery actually did, not that a suggestion existed. `outcome` is
    // "delivered" only when a card reached NotificationService.
    let delivery = await resolveDelivery(result, sendEvent: sendEvent)

    return [
      "outcome": delivery?.rawValue ?? "no_delivery_decision",
      "delivered": delivery == .delivered ? "true" : "false",
      "suggestion": suggestion.suggestion,
      "category": suggestion.category.rawValue,
      "confidence": "\(Int(suggestion.confidence * 100))",
      "commitments": "\(grounding.openCommitments.count)",
      "goals": "\(grounding.goals.count)",
    ]
  }

  // MARK: - Lifecycle

  func clearPendingWork() async {
    clearPendingContext()
  }

  func stop() async {
    clearPendingContext()
    recentSuggestions.removeAll()
    commitmentsInFlight.removeAll()
    cachedGoals.removeAll()
    cachedGoalsSnapshot = nil
    lastGoalsRefresh = .distantPast
  }
}

private enum SuggestionEvaluationError: Error {
  case invalidResponse
}
