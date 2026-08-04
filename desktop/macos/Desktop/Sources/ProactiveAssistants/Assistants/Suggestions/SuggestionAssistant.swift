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
  nonisolated let displayName = "Live Suggestions"

  var isEnabled: Bool {
    get async {
      await MainActor.run { SuggestionAssistantSettings.shared.isEnabled }
    }
  }

  /// Opt into frames during the coordinator's post-context-switch delay.
  ///
  /// The shared delay (`AssistantSettings.analysisDelay`, 60s) exists so assistants do
  /// not analyze while the user is still moving around. A minute is far too long for a
  /// suggestion about the screen in front of you, so this assistant takes the frames and
  /// enforces its own, much shorter settle window instead (`settleInterval`).
  var needsFrameDuringDelay: Bool {
    get async { true }
  }

  // MARK: - Properties

  private let geminiClient: GeminiClient
  private let telemetryModel: SuggestionAssistantTelemetry.Model

  /// How long the user must stay in a context before it is worth spending on. People
  /// switch apps hundreds of times a day and almost none of those are a request for
  /// advice; half a minute of dwell is the difference between passing through a window and
  /// working in it.
  private static let requiredDwell: TimeInterval = 30.0

  /// Hard ceiling on paid evaluations per day, so cost is a number we choose rather than a
  /// function of how much the user alt-tabs.
  private static let dailyEvaluationBudget = 40

  /// Frames are still accepted this early so dwell can be measured from the switch.
  private let settleInterval: TimeInterval = 6.0

  private var dailyBudget = SuggestionDailyBudget()

  /// Set by `onContextSwitch`, consumed by the first frame that passes the gate.
  private var pendingContextSwitchAt: Date?
  private var pendingApp: String?
  private var pendingWindowTitle: String?

  private var lastEvaluationAt: Date?
  private var recentSuggestions: [String] = []
  private let maxRecentSuggestions = 10

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
      fallbackModel: "gemini-2.5-flash"
    )
    telemetryModel = SuggestionAssistantTelemetry.Model(configuredModel: model)
  }

  // MARK: - Trigger

  func onContextSwitch(departingFrame: CapturedFrame?, newApp: String, newWindowTitle: String?) async {
    pendingContextSwitchAt = Date()
    pendingApp = newApp
    pendingWindowTitle = newWindowTitle
  }

  /// Every branch here is mechanical. No model call happens until all of them pass, which
  /// is what makes the cost contract testable.
  func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool {
    guard let switchedAt = pendingContextSwitchAt else { return false }
    guard Date().timeIntervalSince(switchedAt) >= settleInterval else { return false }
    return true
  }

  func analyze(frame: CapturedFrame) async -> AssistantResult? {
    guard pendingContextSwitchAt != nil else { return nil }

    let enabled = await isEnabled
    let excluded = await MainActor.run { SuggestionAssistantSettings.shared.isAppExcluded(frame.appName) }
    let snoozed = await MainActor.run { FloatingControlBarManager.shared.isSnoozed }
    let cooldown = await cooldownInterval

    let now = Date()
    let dwell = pendingContextSwitchAt.map { now.timeIntervalSince($0) } ?? 0

    let decision = SuggestionGatePolicy.decide(
      isEnabled: enabled,
      isAppExcluded: excluded,
      isSnoozed: snoozed,
      now: now,
      lastEvaluationAt: lastEvaluationAt,
      cooldown: cooldown,
      dwell: dwell,
      requiredDwell: Self.requiredDwell,
      evaluationsToday: dailyBudget.countToday(now: now),
      dailyBudget: Self.dailyEvaluationBudget
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
    clearPendingContext()
    lastEvaluationAt = now
    dailyBudget.recordEvaluation(now: now)

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

  private static func describeCommitment(_ task: TaskActionItem) -> String {
    guard let dueAt = task.dueAt else { return task.description }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withFullDate]
    return "\(task.description) (due \(formatter.string(from: dueAt)))"
  }

  /// One line per past screen: when, where, and a snippet of what was on it.
  private static func describeScreen(_ screenshot: Screenshot, excluding frame: CapturedFrame) -> String? {
    // Skip screens from the same window the user is looking at now — the model can already
    // see that, and it crowds out genuinely older context.
    if let title = screenshot.windowTitle, title == frame.windowTitle { return nil }

    let formatter = DateFormatter()
    formatter.dateFormat = "MMM d HH:mm"
    let when = formatter.string(from: screenshot.timestamp)
    let where_ = screenshot.windowTitle.map { "\(screenshot.appName) — \($0)" } ?? screenshot.appName
    guard let ocr = screenshot.ocrText, !ocr.isEmpty else { return "\(when) · \(where_)" }
    let snippet = ocr.replacingOccurrences(of: "\n", with: " ").prefix(200)
    return "\(when) · \(where_): \(snippet)"
  }

  /// Derive a search term from the window title, which is where the topic or person lives.
  /// Reuses the shared normalizer so spinners, timers and unread counts do not become
  /// search noise.
  private static func groundingSearchTerm(for frame: CapturedFrame) -> String? {
    guard let normalized = ContextDetection.normalizeWindowTitle(frame.windowTitle) else { return nil }
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
          latency: Date().timeIntervalSince(startedAt)
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
          + recentSuggestions.joined(separator: "\n")
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
    guard let result = result as? SuggestionResult else { return }
    guard result.hasSuggestion, let suggestion = result.suggestion else {
      log("Suggestion: nothing worth saying — \(result.currentActivity)")
      return
    }
    let telemetryIdentity = SuggestionAssistantTelemetry.NotificationIdentity(result.telemetryIdentity)

    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else {
      await emitDeliveryOutcome(.rejectedOwner, identity: telemetryIdentity)
      return
    }

    let threshold = await minConfidence
    guard suggestion.confidence >= threshold else {
      await emitDeliveryOutcome(.filteredLowConfidence, identity: telemetryIdentity)
      log(
        "Suggestion: below bar [\(Int(suggestion.confidence * 100))% < \(Int(threshold * 100))%] "
          + "\"\(suggestion.suggestion)\""
      )
      return
    }

    guard !SuggestionDeduplication.isDuplicate(suggestion.suggestion, of: recentSuggestions) else {
      await emitDeliveryOutcome(.filteredDuplicate, identity: telemetryIdentity)
      log("Suggestion: duplicate of a recent suggestion — \"\(suggestion.suggestion)\"")
      return
    }

    guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else {
      await emitDeliveryOutcome(.rejectedOwner, identity: telemetryIdentity)
      return
    }

    recentSuggestions.append(suggestion.suggestion)
    if recentSuggestions.count > maxRecentSuggestions {
      recentSuggestions.removeFirst(recentSuggestions.count - maxRecentSuggestions)
    }

    await deliver(
      suggestion,
      result: result,
      ownerID: ownerID,
      telemetryIdentity: telemetryIdentity
    )
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
      sourceTitle: "Suggestion",
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
        title: "Suggestion",
        message: suggestion.suggestion,
        assistantId: identifier,
        context: context,
        suggestionTelemetryIdentity: telemetryIdentity
      )
    }
  }

  // MARK: - Lifecycle

  func clearPendingWork() async {
    clearPendingContext()
  }

  func stop() async {
    clearPendingContext()
    recentSuggestions.removeAll()
  }
}

private enum SuggestionEvaluationError: Error {
  case invalidResponse
}
