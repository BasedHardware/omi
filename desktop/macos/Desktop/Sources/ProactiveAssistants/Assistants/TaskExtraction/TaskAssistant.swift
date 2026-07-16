import Foundation

/// Task extraction assistant that identifies tasks and action items from screen content
/// Uses single-stage Gemini tool calling with vector + FTS5 search for deduplication
actor TaskAssistant: ProactiveAssistant {
  // MARK: - ProactiveAssistant Protocol

  nonisolated let identifier = "task-extraction"
  nonisolated let displayName = "Task Extractor"

  nonisolated static func discoveryEnabled(settingsEnabled: Bool, notificationsEnabled: Bool) -> Bool {
    settingsEnabled
  }

  var isEnabled: Bool {
    get async {
      await MainActor.run {
        // Attention settings never gate quiet discovery.
        Self.discoveryEnabled(
          settingsEnabled: TaskAssistantSettings.shared.isEnabled,
          notificationsEnabled: TaskAssistantSettings.shared.notificationsEnabled
        )
      }
    }
  }

  // MARK: - Properties

  private let geminiClient: GeminiClient
  private var isRunning = false
  private var previousTasks: [ExtractedTask] = []  // Last 10 extracted tasks for context
  private let maxPreviousTasks = 10
  private var currentApp: String?
  private var processingTask: Task<Void, Never>?

  // MARK: - Event-Driven Trigger System
  private enum TriggerEvent {
    case contextSwitch(CapturedFrame)  // departing frame from context being left
    case timerFallback(CapturedFrame)  // latest frame after extraction interval
  }

  private let triggerStream: AsyncStream<TriggerEvent>
  private let triggerContinuation: AsyncStream<TriggerEvent>.Continuation

  /// Always holds the most recent frame for fallback timer use
  private var latestFrame: CapturedFrame?
  /// Fallback timer that fires after extractionInterval if no context switch occurs
  private var fallbackTimerTask: Task<Void, Never>?
  // Per-(app, normalized-window) timestamp of the last yielded context switch.
  // Replaces the old global throttle so 10 different chats in <60s all flow through,
  // while bouncing back to the same chat re-uses the cached analysis.
  private var lastAnalyzedByKey: [String: Date] = [:]

  /// Apps where new content arrives while the user stays in-app, so a context-switch
  /// trigger is too slow. Frames arriving for these apps fire analysis immediately
  /// (subject to the per-window dedupe TTL below).
  private static let messagingFastPathApps: Set<String> = [
    "Telegram",
    "Messages",
    "iMessage",
    "WhatsApp",
    "Signal",
    "Slack",
    "Discord",
    "Messenger",
  ]

  private static let messagingFastPathDelay: TimeInterval = 15.0

  // Cached goals (refreshed every 5 minutes)
  private var cachedGoals: [Goal] = []
  private var lastGoalsRefresh: Date = .distantPast
  private let goalsRefreshInterval: TimeInterval = 300

  // MARK: - Due Date Helpers

  /// Parse an inferred deadline string into a Date, or default to end of today.
  /// Tries ISO8601, then common natural language patterns.
  private func parseDueDate(from inferredDeadline: String?) -> Date? {
    guard let deadline = inferredDeadline, !deadline.isEmpty else {
      return nil
    }
    let startOfToday = Calendar.current.startOfDay(for: Date())

    // Try ISO8601 first (e.g. "2025-10-04T14:00:00Z")
    let iso = ISO8601DateFormatter()
    if let date = iso.date(from: deadline) {
      if date < startOfToday {
        log(
          "Task: Rejected past due date '\(deadline)' → \(date). Today is \(Date()). Due dates must be today or in the future."
        )
        return nil
      }
      return date
    }
    // Try common date formats
    let formats = [
      "yyyy-MM-dd'T'HH:mm:ssZ",
      "yyyy-MM-dd'T'HH:mm:ss",
      "yyyy-MM-dd HH:mm:ss",
      "yyyy-MM-dd",
      "MM/dd/yyyy",
      "MMMM d, yyyy",
      "MMM d, yyyy",
      "MMMM d",
      "MMM d",
    ]
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    for format in formats {
      formatter.dateFormat = format
      if let date = formatter.date(from: deadline) {
        if date < startOfToday {
          log(
            "Task: Rejected past due date '\(deadline)' → \(date). Today is \(Date()). Due dates must be today or in the future."
          )
          return nil
        }
        return date
      }
    }

    // Fallback: try macOS natural language date parsing (handles "Thursday", "next week", etc.)
    let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.date.rawValue)
    if let match = detector?.firstMatch(in: deadline, range: NSRange(deadline.startIndex..., in: deadline)),
      let date = match.date
    {
      // Validate that the parsed date is not in the past
      let startOfToday = Calendar.current.startOfDay(for: Date())
      if date < startOfToday {
        log(
          "Task: Rejected past due date '\(deadline)' → \(date). Today is \(Date()). Due dates must be today or in the future."
        )
        return nil
      }
      return date
    }

    log("Task: Could not parse inferred_deadline '\(deadline)', skipping deadline")
    return nil
  }

  /// Returns 11:59 PM today in the user's local timezone
  private static func endOfToday() -> Date {
    let calendar = Calendar.current
    let startOfDay = calendar.startOfDay(for: Date())
    return calendar.date(bySettingHour: 23, minute: 59, second: 0, of: startOfDay) ?? startOfDay
  }

  /// Get the current system prompt from settings (accessed on MainActor for thread safety)
  private var systemPrompt: String {
    get async {
      await MainActor.run {
        TaskAssistantSettings.shared.analysisPrompt
      }
    }
  }

  /// Get the extraction interval from settings
  private var extractionInterval: TimeInterval {
    get async {
      await MainActor.run {
        TaskAssistantSettings.shared.extractionInterval
      }
    }
  }

  /// Get the minimum confidence threshold from settings
  private var minConfidence: Double {
    get async {
      await MainActor.run {
        TaskAssistantSettings.shared.minConfidence
      }
    }
  }

  // MARK: - Initialization

  init(apiKey: String? = nil) throws {
    self.geminiClient = try GeminiClient(
      apiKey: apiKey, model: ModelQoS.Gemini.taskExtraction, fallbackModel: "gemini-2.5-flash")

    let (stream, continuation) = AsyncStream.makeStream(of: TriggerEvent.self, bufferingPolicy: .bufferingNewest(1))
    self.triggerStream = stream
    self.triggerContinuation = continuation

    // Start processing loop + embedding index
    Task {
      await self.startProcessing()
      await self.initializeEmbeddings()
    }
  }

  // MARK: - Embedding Lifecycle

  /// Load embedding index and kick off backfill
  private func initializeEmbeddings() async {
    await EmbeddingService.shared.loadIndex()
    // Backfill in background
    Task {
      await EmbeddingService.shared.backfillIfNeeded()
    }
  }

  // MARK: - Processing

  private func startProcessing() {
    isRunning = true
    processingTask = Task {
      await retryCanonicalOutbox()
      await processLoop()
    }
  }

  private func retryCanonicalOutbox() async {
    let records: [StagedTaskRecord]
    do {
      records = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    } catch {
      logError("Task: Failed to load canonical capture outbox", error: error)
      return
    }
    for record in records {
      let metadata = record.metadata ?? [:]
      let formatter = ISO8601DateFormatter()
      formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
      let task = ExtractedTask(
        title: record.description,
        description: metadata["reasoning"] as? String,
        priority: TaskPriority(rawValue: record.priority ?? "medium") ?? .medium,
        sourceApp: record.sourceApp ?? "Unknown",
        inferredDeadline: record.dueAt.map { formatter.string(from: $0) },
        confidence: record.confidence ?? 0.5,
        tags: record.tags,
        sourceCategory: metadata["source_category"] as? String ?? "other",
        sourceSubcategory: metadata["source_subcategory"] as? String ?? "other",
        captureKind: metadata["capture_kind"] as? String,
        owner: metadata["owner"] as? String,
        concreteDeliverable: metadata["concrete_deliverable"] as? Bool,
        publicBroadcast: metadata["public_broadcast"] as? Bool,
        directMention: metadata["direct_mention"] as? Bool,
        alreadyDone: metadata["already_done"] as? Bool,
        duplicateOf: metadata["duplicate_of"] as? String,
        refinesTask: metadata["refines_task"] as? String,
        ownershipConfidence: metadata["ownership_confidence"] as? Double
      )
      await syncTaskToBackend(
        task: task,
        taskResult: TaskExtractionResult(
          hasNewTask: true,
          task: task,
          contextSummary: record.contextSummary ?? "",
          currentActivity: record.currentActivity ?? ""
        ),
        localRecord: record,
        windowTitle: record.windowTitle
      )
    }
  }

  private func processLoop() async {
    log("Task assistant started (event-driven)")

    for await trigger in triggerStream {
      guard isRunning else { break }

      let (frame, triggerType): (CapturedFrame, String) = {
        switch trigger {
        case .contextSwitch(let f): return (f, "context_switch")
        case .timerFallback(let f): return (f, "timer_fallback")
        }
      }()

      log("Task: Processing \(triggerType) trigger from \(frame.appName) (window: \(frame.windowTitle ?? "nil"))")

      // Cancel fallback timer before processing
      fallbackTimerTask?.cancel()
      fallbackTimerTask = nil

      await processFrame(frame)

      // Start a new fallback timer after processing
      startFallbackTimer()
    }

    log("Task assistant stopped")
  }

  /// Start (or restart) the fallback timer that fires after extractionInterval
  private func startFallbackTimer() {
    fallbackTimerTask?.cancel()
    fallbackTimerTask = Task {
      let interval = await self.extractionInterval
      try? await Task.sleep(nanoseconds: UInt64(interval * 1_000_000_000))
      guard !Task.isCancelled else { return }
      guard let frame = self.latestFrame else { return }
      log("Task: Fallback timer fired after \(Int(interval))s")
      self.triggerContinuation.yield(.timerFallback(frame))
    }
  }

  // MARK: - Test Analysis (for test runner)

  /// Run the extraction pipeline on arbitrary JPEG data without side effects (no saving, no events).
  /// Used by the test runner to replay past screenshots.
  /// Returns (results, searchCount) — results is one entry per extracted task plus one
  /// terminator entry (no_task_found/reject_task) when no tasks were extracted.
  func testAnalyze(jpegData: Data, appName: String) async throws -> ([TaskExtractionResult], Int) {
    return try await extractTaskSingleStage(from: jpegData, appName: appName)
  }

  // MARK: - ProactiveAssistant Protocol Methods

  func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool {
    return true
  }

  func analyze(frame: CapturedFrame) async -> AssistantResult? {
    // Defense-in-depth: skip Rewind privacy-excluded apps (password managers, keychains)
    if RewindSettings.shared.isAppExcluded(frame.appName) {
      return nil
    }

    // Only analyze apps on the whitelist
    let allowed = await MainActor.run { TaskAssistantSettings.shared.isAppAllowed(frame.appName) }
    if !allowed {
      return nil
    }

    // For browser apps, also check window title against enabled heuristics
    let windowAllowed = await MainActor.run {
      TaskAssistantSettings.shared.isWindowAllowed(appName: frame.appName, windowTitle: frame.windowTitle)
    }
    if !windowAllowed {
      return nil
    }

    // Store as latest frame (used by fallback timer and context switch)
    latestFrame = frame

    // Start fallback timer if not already running
    if fallbackTimerTask == nil {
      startFallbackTimer()
    }

    // Fast in-app trigger: for messaging apps, arm a ~15s timer keyed to the
    // current (app, window). Lets a new chat message turn into a task without
    // requiring the user to leave the app.
    armFastFallbackIfNeeded(frame: frame)

    return nil
  }

  /// For messaging apps, fire analysis immediately when a frame for a fresh window
  /// arrives (subject to the per-window dedupe TTL). Lets chat content turn into a task
  /// without requiring the user to leave the app. Non-messaging apps continue to rely on
  /// the regular context-switch + fallback-timer path.
  private func armFastFallbackIfNeeded(frame: CapturedFrame) {
    guard Self.messagingFastPathApps.contains(frame.appName) else { return }

    let key = Self.analyzedKey(for: frame)

    // Per-window dedupe — same chat within the TTL is suppressed; the next eligible
    // frame fires immediately.
    if let last = lastAnalyzedByKey[key] {
      let elapsed = Date().timeIntervalSince(last)
      if elapsed < Self.messagingFastPathDelay {
        return
      }
    }

    log("Task: Fast in-app trigger firing immediately for messaging window '\(key)'")
    lastAnalyzedByKey[key] = Date()
    triggerContinuation.yield(.timerFallback(frame))
  }

  func handleResult(_ result: AssistantResult, sendEvent: @escaping (String, [String: Any]) -> Void) async {
    guard let taskResult = result as? TaskExtractionResult else { return }
    await handleResultWithScreenshot(taskResult, screenshotId: nil, appName: "Unknown", sendEvent: sendEvent)
  }

  /// Handle result with screenshot ID for SQLite storage
  private func handleResultWithScreenshot(
    _ taskResult: TaskExtractionResult,
    screenshotId: Int64?,
    appName: String,
    windowTitle: String? = nil,
    sendEvent: @escaping (String, [String: Any]) -> Void
  ) async {
    // Save observation for every result (fire-and-forget)
    let observationApp = taskResult.task?.sourceApp ?? appName
    let observation = ObservationRecord(
      screenshotId: screenshotId,
      appName: observationApp,
      contextSummary: taskResult.contextSummary,
      currentActivity: taskResult.currentActivity,
      hasTask: taskResult.hasNewTask,
      taskTitle: taskResult.task?.title,
      sourceCategory: taskResult.task?.sourceCategory,
      sourceSubcategory: taskResult.task?.sourceSubcategory,
      createdAt: Date()
    )
    let observationAuthorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot()
    Task {
      guard let observationAuthorizationSnapshot else { return }
      do {
        try await ActionItemStorage.shared.insertObservation(
          observation,
          authorization: LocalMutationAuthorization {
            RuntimeOwnerIdentity.isAuthorizationCurrent(
              observationAuthorizationSnapshot
            )
          }
        )
      } catch {
        if RuntimeOwnerIdentity.isAuthorizationCurrent(observationAuthorizationSnapshot) {
          logError("Task: Failed to insert observation", error: error)
        }
      }
    }

    guard taskResult.hasNewTask, let task = taskResult.task else {
      return
    }

    let threshold = await minConfidence
    let confidencePercent = Int(task.confidence * 100)

    guard task.confidence >= threshold else {
      log("Task: [\(confidencePercent)% < \(Int(threshold * 100))%] Filtered: \"\(task.title)\"")
      return
    }

    log("Task: [\(confidencePercent)% conf.] \"\(task.title)\"")

    previousTasks.insert(task, at: 0)
    if previousTasks.count > maxPreviousTasks {
      previousTasks.removeLast()
    }

    // Persist a hidden outbox row before any backend work.
    let extractionRecord = await saveTaskToSQLite(
      task: task,
      screenshotId: screenshotId,
      contextSummary: taskResult.contextSummary,
      windowTitle: windowTitle
    )

    await syncTaskToBackend(
      task: task,
      taskResult: taskResult,
      localRecord: extractionRecord,
      windowTitle: windowTitle
    )

    await MainActor.run {
      AnalyticsManager.shared.taskExtracted(taskCount: 1)
    }

    sendEvent(
      "taskExtracted",
      [
        "assistant": identifier,
        "task": task.toDictionary(),
        "contextSummary": taskResult.contextSummary,
      ])
  }

  /// Generate embedding for a newly saved staged task and store it
  private func generateEmbeddingForTask(id: Int64, text: String) async {
    do {
      let embedding = try await EmbeddingService.shared.embed(text: text)
      let data = await EmbeddingService.shared.floatsToData(embedding)
      try await StagedTaskStorage.shared.updateEmbedding(id: id, embedding: data)
      await EmbeddingService.shared.addToIndex(source: .staged, id: id, embedding: embedding)
      log("Task: Generated embedding for staged task \(id)")
    } catch {
      logError("Task: Failed to generate embedding for staged task \(id)", error: error)
    }
  }

  /// Save extracted task to staged_tasks SQLite table
  private func saveTaskToSQLite(
    task: ExtractedTask,
    screenshotId: Int64?,
    contextSummary: String,
    windowTitle: String? = nil
  ) async -> StagedTaskRecord? {
    var metadata: [String: Any] = [
      "tags": task.tags,
      "context_summary": contextSummary,
      "source_category": task.sourceCategory,
      "source_subcategory": task.sourceSubcategory,
      "capture_kind": task.captureKind ?? "direct_request",
      "owner": task.owner ?? "unknown",
      "concrete_deliverable": task.concreteDeliverable ?? false,
      "public_broadcast": task.publicBroadcast ?? false,
      "direct_mention": task.directMention ?? false,
      "already_done": task.alreadyDone ?? false,
      "ownership_confidence": task.ownershipConfidence ?? 0.5,
    ]
    if let duplicateOf = task.duplicateOf { metadata["duplicate_of"] = duplicateOf }
    if let refinesTask = task.refinesTask { metadata["refines_task"] = refinesTask }
    if let primaryTag = task.primaryTag {
      metadata["category"] = primaryTag
    }
    if let deadline = task.inferredDeadline {
      metadata["inferred_deadline"] = deadline
    }
    if let windowTitle = windowTitle {
      metadata["window_title"] = windowTitle
    }

    let metadataJson: String?
    if let data = try? JSONSerialization.data(withJSONObject: metadata),
      let json = String(data: data, encoding: .utf8)
    {
      metadataJson = json
    } else {
      metadataJson = nil
    }

    let tagsJson: String?
    if let data = try? JSONEncoder().encode(task.tags),
      let json = String(data: data, encoding: .utf8)
    {
      tagsJson = json
    } else {
      tagsJson = nil
    }

    let dueAt = parseDueDate(from: task.inferredDeadline)

    let record = StagedTaskRecord(
      backendSynced: false,
      description: task.title,
      // The row is born hidden and retryable. Mode resolution may later
      // convert it to legacy staging, but a crash can never expose a local
      // Candidate that canonical authority has not received.
      source: "candidate_outbox",
      priority: task.priority.rawValue,
      category: task.primaryTag,
      tagsJson: tagsJson,
      dueAt: dueAt,
      screenshotId: screenshotId,
      confidence: task.confidence,
      sourceApp: task.sourceApp,
      windowTitle: windowTitle,
      contextSummary: contextSummary,
      metadataJson: metadataJson,
      relevanceScore: nil,
      scoredAt: nil
    )

    do {
      let inserted = try await StagedTaskStorage.shared.insertLocalStagedTask(record)
      log("Task: Saved retryable capture outbox row (id: \(inserted.id ?? -1))")
      return inserted
    } catch {
      logError("Task: Failed to save to staged_tasks", error: error)
      return nil
    }
  }

  /// Deliver the local outbox row through the mode-owned backend authority.
  private func syncTaskToBackend(
    task: ExtractedTask,
    taskResult: TaskExtractionResult,
    localRecord: StagedTaskRecord?,
    windowTitle: String? = nil
  ) async {
    guard let localRecord, let localID = localRecord.id else {
      log("Task: Capture outbox persistence failed; refusing an untracked backend write")
      return
    }
    do {
      // Hide the row before mode resolution. A transient backend failure must
      // leave retry state, never an independently actionable local Candidate.
      let control = try await APIClient.shared.getCandidateWorkflowControl()
      guard let mode = control.workflowMode else {
        log("Task: Workflow control omitted mode; capture remains retryable")
        return
      }

      if mode == .read {
        guard let generation = control.accountGeneration else {
          log("Task: Workflow control omitted generation; capture remains retryable")
          return
        }
        let decision = ScreenCandidateAdapter.adapt(
          task: task,
          dueAt: parseDueDate(from: task.inferredDeadline),
          localEvidenceID: "screen-\(localRecord.screenshotId ?? localID)",
          deviceID: ClientDeviceService.shared.clientDeviceId
        )
        guard decision.candidate != nil else {
          try await StagedTaskStorage.shared.discardCanonicalOutbox(id: localID)
          return
        }
        let delivery = CanonicalScreenCandidateDelivery(
          client: APICanonicalScreenCandidateClient()
        )
        guard
          let canonicalState = try await delivery.deliver(
            decision,
            localID: localID,
            deviceID: ClientDeviceService.shared.deviceIdHash,
            accountGeneration: generation
          )
        else { return }
        let canonicalStatus = canonicalState.status
        let canonicalTaskID = canonicalState.taskID
        try await StagedTaskStorage.shared.markCanonicalReceipt(
          id: localID,
          candidateID: canonicalState.candidateID,
          status: canonicalStatus.rawValue,
          taskID: canonicalTaskID
        )
        let confidenceBand = TaskIntelligenceConfidenceBand.forCapture(
          confidence: task.confidence,
          explicit: task.captureKind == "explicit_command"
        )
        let capturedAttribution = TaskIntelligenceAttributionEvent.candidateCaptured(
          candidateID: canonicalState.candidateID,
          confidenceBand: confidenceBand
        )
        let resolvedAttribution: TaskIntelligenceAttributionEvent? = {
          if canonicalStatus == .accepted, let canonicalTaskID {
            return .candidateResolved(
              candidateID: canonicalState.candidateID,
              taskID: canonicalTaskID,
              resolutionCode: .accepted
            )
          }
          if canonicalStatus == .rejected {
            return .candidateResolved(
              candidateID: canonicalState.candidateID,
              taskID: nil,
              resolutionCode: .rejected
            )
          }
          if canonicalStatus == .expired {
            return .candidateResolved(
              candidateID: canonicalState.candidateID,
              taskID: nil,
              resolutionCode: .expired
            )
          }
          return nil
        }()
        await MainActor.run {
          AnalyticsManager.shared.taskIntelligenceAttribution(capturedAttribution)
          if let resolvedAttribution {
            AnalyticsManager.shared.taskIntelligenceAttribution(resolvedAttribution)
          }
        }
        log(
          "Task: Canonical capture reconciled candidate=\(canonicalState.candidateID) outcome=\(decision.outcome.rawValue)"
        )
        return
      }

      guard TaskCaptureModePolicy.usesLegacyStaging(mode) else {
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "other",
          from: "workflow_control",
          to: "capture_deferred",
          reason: "other",
          outcome: .degraded
        )
        log("Task: Unknown workflow mode; capture remains retryable")
        return
      }

      let shadowOutcome = ScreenCapturePolicy.evaluate(ScreenCandidateAdapter.facts(for: task))
      if mode == .shadow {
        log("Task: Shadow capture outcome=\(shadowOutcome.rawValue)")
      }
      var metadata: [String: Any] = [
        "source_app": task.sourceApp,
        "confidence": task.confidence,
        "context_summary": taskResult.contextSummary,
        "current_activity": taskResult.currentActivity,
        "tags": task.tags,
        "source_category": task.sourceCategory,
        "source_subcategory": task.sourceSubcategory,
      ]
      if let primaryTag = task.primaryTag {
        metadata["category"] = primaryTag
      }
      if let reasoning = task.description {
        metadata["reasoning"] = reasoning
      }
      if let deadline = task.inferredDeadline {
        metadata["inferred_deadline"] = deadline
      }
      if let windowTitle = windowTitle {
        metadata["window_title"] = windowTitle
      }

      let dueAt = parseDueDate(from: task.inferredDeadline)

      let response = try await APIClient.shared.createStagedTask(
        description: task.title,
        dueAt: dueAt,
        source: "screenshot",
        priority: task.priority.rawValue,
        category: task.primaryTag,
        metadata: metadata,
        relevanceScore: nil
      )

      log("Task: Synced to staged_tasks backend (id: \(response.id))")
      try await StagedTaskStorage.shared.markSynced(
        id: localID,
        backendId: response.id,
        source: "screenshot"
      )
      Task {
        await self.generateEmbeddingForTask(id: localID, text: task.title)
      }
      Task {
        await TaskPromotionService.shared.promoteIfNeeded()
      }
    } catch {
      logError("Task: Candidate outbox delivery failed; will retry", error: error)
    }
  }

  func onAppSwitch(newApp: String) async {
    if newApp != currentApp {
      if let currentApp = currentApp {
        log("Task: APP SWITCH: \(currentApp) -> \(newApp)")
      } else {
        log("Task: Active app: \(newApp)")
      }
      currentApp = newApp
    }
  }

  func onContextSwitch(departingFrame: CapturedFrame?, newApp: String, newWindowTitle: String?) async {
    // Use latestFrame if departing frame is unavailable or stale (from a different app due to delay periods)
    let frame: CapturedFrame? = {
      if let departing = departingFrame {
        return departing
      }
      return latestFrame
    }()

    guard let frame = frame else {
      log("Task: Context switch but no frame available")
      return
    }

    // Defense-in-depth: skip Rewind privacy-excluded apps
    if RewindSettings.shared.isAppExcluded(frame.appName) {
      log("Task: Context switch from Rewind-excluded app '\(frame.appName)', skipping")
      fallbackTimerTask?.cancel()
      fallbackTimerTask = nil
      return
    }

    // Check frame's app is on the whitelist
    let allowed = await MainActor.run { TaskAssistantSettings.shared.isAppAllowed(frame.appName) }
    if !allowed {
      log("Task: Context switch from non-whitelisted app '\(frame.appName)', skipping")
      // Still cancel fallback timer on any context switch
      fallbackTimerTask?.cancel()
      fallbackTimerTask = nil
      return
    }

    // Check window is allowed for browser apps
    let windowAllowed = await MainActor.run {
      TaskAssistantSettings.shared.isWindowAllowed(appName: frame.appName, windowTitle: frame.windowTitle)
    }
    if !windowAllowed {
      log("Task: Context switch from filtered browser window, skipping")
      fallbackTimerTask?.cancel()
      fallbackTimerTask = nil
      return
    }

    log("Task: Context switch from \(frame.appName) (window: \(frame.windowTitle ?? "nil")) -> \(newApp)")

    // Per-window dedupe instead of one global cooldown. A different chat / window /
    // browser tab has a different key, so 10 chats with 10 people in <60s all flow
    // through. Re-entering the same chat within the dedupe window is skipped (the
    // semantic dedupe inside the Claude prompt already catches duplicate tasks if
    // we ever do re-analyze the same window later).
    // Messaging apps use a shorter dedupe so a new message in the same chat doesn't
    // wait a full minute before getting re-analyzed.
    let analysisDelay = await MainActor.run { AssistantSettings.shared.analysisDelay }
    let dedupeKey = Self.analyzedKey(for: frame)
    let dedupeTTL: TimeInterval =
      Self.messagingFastPathApps.contains(frame.appName)
      ? Self.messagingFastPathDelay
      : TimeInterval(analysisDelay)
    let now = Date()
    if dedupeTTL > 0, let last = lastAnalyzedByKey[dedupeKey] {
      let elapsed = now.timeIntervalSince(last)
      if elapsed < dedupeTTL {
        log(
          "Task: Context switch dedupe — already analyzed '\(dedupeKey)' \(Int(elapsed))s ago (<\(Int(dedupeTTL))s), skipping"
        )
        fallbackTimerTask?.cancel()
        fallbackTimerTask = nil
        return
      }
    }

    // Cancel fallback timer — context switch replaces it
    fallbackTimerTask?.cancel()
    fallbackTimerTask = nil

    // Yield context switch trigger with the frame
    lastAnalyzedByKey[dedupeKey] = now
    pruneStaleDedupeEntries(now: now, ttl: TimeInterval(max(analysisDelay, 60) * 5))
    triggerContinuation.yield(.contextSwitch(frame))
  }

  /// Normalize (app, window) into a stable dedupe key. Strips Telegram-style trailing
  /// counters and collapses whitespace so the same chat across reopens hashes the same.
  static func analyzedKey(for frame: CapturedFrame) -> String {
    let app = frame.appName.lowercased()
    let title = normalizedWindowTitle(frame.windowTitle)
    return "\(app)::\(title)"
  }

  private static func normalizedWindowTitle(_ title: String?) -> String {
    guard let raw = title, !raw.isEmpty else { return "" }
    var t = raw.lowercased()
    // Strip Telegram-style trailing message counters: " (247887)" / "(247887)".
    if let range = t.range(of: #"\s*\(\d+\)\s*$"#, options: .regularExpression) {
      t.removeSubrange(range)
    }
    // Collapse whitespace runs so " foo   bar " == "foo bar".
    t = t.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    return t
  }

  private func pruneStaleDedupeEntries(now: Date, ttl: TimeInterval) {
    let cutoff = now.addingTimeInterval(-ttl)
    lastAnalyzedByKey = lastAnalyzedByKey.filter { $0.value >= cutoff }
  }

  func clearPendingWork() async {
    fallbackTimerTask?.cancel()
    fallbackTimerTask = nil
    log("Task: Cleared fallback timer")
  }

  func stop() async {
    isRunning = false
    fallbackTimerTask?.cancel()
    fallbackTimerTask = nil
    triggerContinuation.finish()
    processingTask?.cancel()
    latestFrame = nil
  }

  // MARK: - Single-Stage Analysis with Tool Calling

  private func processFrame(_ frame: CapturedFrame) async {
    let enabled = await isEnabled
    guard enabled else {
      log("Task: Skipping analysis (disabled)")
      return
    }

    log("Task: Analyzing frame from \(frame.appName)...")
    do {
      let (results, searchCount) = try await extractTaskSingleStage(from: frame.jpegData, appName: frame.appName)
      guard !results.isEmpty else {
        log("Task: Analysis returned no results")
        return
      }

      let extractedCount = results.filter { $0.hasNewTask }.count
      log(
        "Task: Analysis complete - results: \(results.count) (extracted: \(extractedCount)), context: \(results.first?.contextSummary ?? ""), searches: \(searchCount)"
      )

      for result in results {
        await handleResultWithScreenshot(
          result, screenshotId: frame.screenshotId, appName: frame.appName, windowTitle: frame.windowTitle
        ) { type, data in
          Task { @MainActor in
            AssistantCoordinator.shared.sendEvent(type: type, data: data)
          }
        }
      }
    } catch {
      logError("Task extraction error", error: error)
    }
  }

  /// Loop-based extraction: image analysis + iterative tool calling. A single frame can
  /// contain multiple distinct commitments (e.g. two unrelated asks in one chat) — the
  /// loop accumulates every extract_task call instead of stopping after the first.
  /// reject_task on one candidate no longer kills the whole frame; the loop keeps going
  /// until no_task_found terminates it or the iteration budget is exhausted.
  /// Returns (results, searchCount) — one TaskExtractionResult per extract_task plus a
  /// terminator result when zero tasks were extracted.
  private func extractTaskSingleStage(from jpegData: Data, appName: String) async throws -> (
    [TaskExtractionResult], Int
  ) {
    // 1. Gather context
    let context = await refreshContext()

    // 2. Build prompt with injected context
    let dateFormatter = DateFormatter()
    dateFormatter.dateFormat = "yyyy-MM-dd (EEEE)"
    let todayStr = dateFormatter.string(from: Date())

    var prompt =
      "Screenshot from \(appName). Today is \(todayStr). Analyze this screenshot for any unaddressed request directed at the user.\n\n"

    // For messaging apps, add an extra reminder about conversation analysis
    let messagingApps: Set<String> = ["Telegram", "WhatsApp", "\u{200E}WhatsApp", "Messages", "Slack", "Discord"]
    if messagingApps.contains(appName) {
      prompt += """
        REMINDER — THIS IS A MESSAGING APP:
        - If this screenshot shows a chat sidebar/conversation list rather than an open conversation, SKIP entirely.
        - If it shows an open conversation, read the FULL conversation flow between the user and the other person.
        - LEFT-SIDE messages = from the other person. RIGHT-SIDE/colored = from the user.
        - PRIORITY: Look for where the user AGREED or COMMITTED to doing something the other person asked.
          Example: Other person says "Can you send me the report?" → User replies "Sure, will do" → Extract task: "Send [person] the report"
        - ALSO: Look for incoming requests the user hasn't responded to yet.
        - The task title should describe what was asked for, naming the other person in the conversation.

        """
    }

    // Inject AI user profile for context
    if let profile = await AIUserProfileService.shared.getLatestProfile() {
      prompt += "USER PROFILE (who this user is — use for context, not as a task source):\n"
      prompt += profile.profileText + "\n\n"
    }

    if !context.activeTasks.isEmpty {
      prompt +=
        "ACTIVE TASKS (use only for semantic duplicate/refinement evidence; never globally rank new captures):\n"
      for (i, task) in context.activeTasks.enumerated() {
        let pri = task.priority.map { " [\($0)]" } ?? ""
        prompt += "\(i + 1). [id:\(task.id)] \(task.description)\(pri)\n"
      }
      prompt += "\n"
    }

    if !context.completedTasks.isEmpty {
      prompt +=
        "RECENTLY COMPLETED TASKS (user engaged with these — this is the kind of task the user finds valuable. Extract similar types of tasks, just not exact duplicates of these specific ones):\n"
      for (i, task) in context.completedTasks.enumerated() {
        prompt += "\(i + 1). \(task.description)\n"
      }
      prompt += "\n"
    }

    if !context.deletedTasks.isEmpty {
      prompt += "USER-DELETED TASKS (user explicitly rejected these — do not re-extract similar):\n"
      for (i, task) in context.deletedTasks.enumerated() {
        prompt += "\(i + 1). \(task.description)\n"
      }
      prompt += "\n"
    }

    if !context.goals.isEmpty {
      prompt += "ACTIVE GOALS:\n"
      for (i, goal) in context.goals.enumerated() {
        prompt += "\(i + 1). \(goal.title)"
        if let desc = goal.description {
          prompt += " — \(desc)"
        }
        prompt += "\n"
      }
      prompt += "\n"
    }

    prompt += """
      Analyze this screenshot. If you see a potential request, search for duplicates first.
      If there is clearly no request on screen (~90% of screenshots), call no_task_found immediately.

      CANONICAL CAPTURE POLICY (overrides older/custom duplicate instructions):
      - A matching active task is evidence, not a reason to discard the observation.
      - Exact duplicate with useful new evidence: call extract_task with duplicate_of set to its task id.
      - A follow-up that changes an active task: call extract_task with refines_task set to its task id.
      - Evidence that an active task was completed: call extract_task with capture_kind already_done and refines_task set to its task id.
      - Use reject_task only for a previously rejected/deleted item or a true no-op with no useful new evidence.
      """

    // 3. Define 5 tools
    let tools = GeminiTool(functionDeclarations: [
      GeminiTool.FunctionDeclaration(
        name: "search_similar",
        description:
          "Search for semantically similar existing tasks using vector similarity. Call this when you see a potential request and want to check for duplicates.",
        parameters: GeminiTool.FunctionDeclaration.Parameters(
          type: "object",
          properties: [
            "query": .init(type: "string", description: "A concise description of the potential task to search for")
          ],
          required: ["query"]
        )
      ),
      GeminiTool.FunctionDeclaration(
        name: "search_keywords",
        description:
          "Search for existing tasks matching specific keywords. Use this for precise keyword-based matching complementing vector search.",
        parameters: GeminiTool.FunctionDeclaration.Parameters(
          type: "object",
          properties: [
            "query": .init(type: "string", description: "Keywords to search for in existing tasks")
          ],
          required: ["query"]
        )
      ),
      GeminiTool.FunctionDeclaration(
        name: "no_task_found",
        description:
          "Call this when there is no actionable request on screen. This is the most common outcome (~90% of screenshots). Use for: code editors, terminals, settings, media players, dashboards, or any screen without a direct request from another person or AI.",
        parameters: GeminiTool.FunctionDeclaration.Parameters(
          type: "object",
          properties: [
            "context_summary": .init(type: "string", description: "Brief summary of what the user is looking at"),
            "current_activity": .init(type: "string", description: "What the user is actively doing"),
          ],
          required: ["context_summary", "current_activity"]
        )
      ),
      GeminiTool.FunctionDeclaration(
        name: "extract_task",
        description:
          "Emit canonical capture facts for a new task, enrichment, update, or completion. Call ONLY after searching. All fields are required.",
        parameters: GeminiTool.FunctionDeclaration.Parameters(
          type: "object",
          properties: [
            "title": .init(
              type: "string",
              description:
                "Verb-first task title, 6–15 words. MUST name a specific person/project/artifact and a concrete action. If you can't write 6+ specific words, call no_task_found instead."
            ),
            "description": .init(
              type: "string", description: "Additional context about the task. Empty string if none."),
            "priority": .init(type: "string", description: "Task priority", enumValues: ["high", "medium", "low"]),
            "tags": .init(type: "array", description: "1-3 relevant tags", items: .init(type: "string")),
            "source_app": .init(type: "string", description: "App where the task was found"),
            "inferred_deadline": .init(
              type: "string",
              description:
                "Deadline in yyyy-MM-dd format (e.g. '2025-10-04'). Resolve relative references like 'Thursday' or 'next week' to an actual date. Empty string if no deadline."
            ),
            "confidence": .init(type: "number", description: "Confidence score 0.0-1.0"),
            "context_summary": .init(type: "string", description: "Brief summary of what user is looking at"),
            "current_activity": .init(type: "string", description: "What the user is actively doing"),
            "source_category": .init(
              type: "string", description: "Where the task originated",
              enumValues: [
                "direct_request", "self_generated", "calendar_driven", "reactive", "external_system", "other",
              ]),
            "source_subcategory": .init(
              type: "string", description: "Specific origin within category",
              enumValues: [
                "message", "meeting", "mention", "commitment", "idea", "reminder", "goal_subtask", "event_prep",
                "recurring", "deadline", "error", "notification", "observation", "project_tool", "alert",
                "documentation", "other",
              ]),
            "capture_kind": .init(
              type: "string", description: "Shared capture-policy fact",
              enumValues: [
                "explicit_command", "clear_commitment", "direct_request", "inferred_next_step", "already_done",
              ]),
            "owner": .init(
              type: "string", description: "Who owns the action", enumValues: ["user", "other", "unknown"]),
            "concrete_deliverable": .init(
              type: "boolean", description: "Whether the action has a concrete deliverable"),
            "public_broadcast": .init(type: "boolean", description: "True for an unowned public-channel request"),
            "direct_mention": .init(type: "boolean", description: "True when the user was directly mentioned"),
            "duplicate_of": .init(
              type: "string", description: "Existing canonical task id when duplicate; empty otherwise"),
            "refines_task": .init(
              type: "string", description: "Existing canonical task id when this refines it; empty otherwise"),
            "ownership_confidence": .init(type: "number", description: "Owner confidence 0.0-1.0"),
          ],
          required: [
            "title", "description", "priority", "tags", "source_app", "inferred_deadline", "confidence",
            "context_summary", "current_activity", "source_category", "source_subcategory", "capture_kind", "owner",
            "concrete_deliverable", "public_broadcast", "direct_mention", "duplicate_of", "refines_task",
            "ownership_confidence",
          ]
        )
      ),
      GeminiTool.FunctionDeclaration(
        name: "reject_task",
        description:
          "Reject only a previously rejected/deleted item or a no-op with no useful new evidence. Active duplicates, refinements, and newly observed completion must use extract_task.",
        parameters: GeminiTool.FunctionDeclaration.Parameters(
          type: "object",
          properties: [
            "reason": .init(
              type: "string",
              description: "Why this task was rejected (e.g. 'duplicate of existing active task', 'already completed')"),
            "context_summary": .init(type: "string", description: "Brief summary of what user is looking at"),
            "current_activity": .init(type: "string", description: "What the user is actively doing"),
          ],
          required: ["reason", "context_summary", "current_activity"]
        )
      ),
    ])

    // 4. Get system prompt
    let currentSystemPrompt = await systemPrompt

    // 5. Build initial contents
    // Wrap base64 encoding in autoreleasepool — Swift concurrency doesn't
    // drain autorelease pools, causing bridged NSString objects to accumulate.
    var contents: [GeminiImageToolRequest.Content] = autoreleasepool {
      let base64Data = jpegData.base64EncodedString()
      return [
        GeminiImageToolRequest.Content(
          role: "user",
          parts: [
            GeminiImageToolRequest.Part(text: prompt),
            GeminiImageToolRequest.Part(mimeType: "image/jpeg", data: base64Data),
          ]
        )
      ]
    }

    // 6. Tool-calling loop (max 8 iterations — enough headroom for 2-3 distinct
    // commitments per frame each doing search + extract).
    var searchCount = 0
    var extractedResults: [TaskExtractionResult] = []
    var lastContextSummary = ""
    var lastCurrentActivity = ""

    toolLoop: for iteration in 0..<8 {
      let result = try await geminiClient.sendImageToolLoop(
        contents: contents,
        systemPrompt: currentSystemPrompt,
        tools: [tools],
        forceToolCall: iteration == 0,
        thinkingBudget: 1024
      )

      guard let toolCall = result.toolCalls.first else {
        log("Task: No tool call received on iteration \(iteration), breaking")
        break
      }

      switch toolCall.name {
      case "no_task_found":
        let contextSummary = toolCall.arguments["context_summary"] as? String ?? "No task on screen"
        let currentActivity = toolCall.arguments["current_activity"] as? String ?? "Unknown"
        log("Task: no_task_found — \(contextSummary)")
        if !extractedResults.isEmpty {
          // Already extracted at least one task — terminator can be implicit, just return.
          return (extractedResults, searchCount)
        }
        return (
          [
            TaskExtractionResult(
              hasNewTask: false,
              task: nil,
              contextSummary: contextSummary,
              currentActivity: currentActivity
            )
          ], searchCount
        )

      case "extract_task":
        let title = toolCall.arguments["title"] as? String ?? ""
        let contextSummary = toolCall.arguments["context_summary"] as? String ?? ""
        let currentActivity = toolCall.arguments["current_activity"] as? String ?? ""

        // --- Hard validation: reject vague titles and ask the model to retry ---
        let titleWords = title.split(separator: " ").count
        let validationError = Self.validateTaskTitle(title, wordCount: titleWords)
        if let error = validationError {
          log("Task: Title rejected (\(error)): \"\(title)\"")

          // Feed rejection back into the loop so the model can retry with more specifics
          contents.append(
            GeminiImageToolRequest.Content(
              role: "model",
              parts: [
                GeminiImageToolRequest.Part(
                  functionCall: .init(
                    name: toolCall.name, args: toolCall.arguments as? [String: String] ?? ["title": title]),
                  thoughtSignature: toolCall.thoughtSignature
                )
              ]
            ))
          contents.append(
            GeminiImageToolRequest.Content(
              role: "user",
              parts: [
                GeminiImageToolRequest.Part(
                  functionResponse: .init(
                    name: toolCall.name,
                    response: .init(
                      result: """
                        REJECTED: \(error). \
                        Your title was: "\(title)" (\(titleWords) words). \
                        Either rewrite with 6+ words including a specific person/project name and concrete action, \
                        or call no_task_found if you cannot be more specific.
                        """)
                  ))
              ]
            ))
          continue
        }

        let description = toolCall.arguments["description"] as? String
        let priorityStr = toolCall.arguments["priority"] as? String ?? "medium"
        let priority = TaskPriority(rawValue: priorityStr) ?? .medium
        let tags: [String]
        if let tagArray = toolCall.arguments["tags"] as? [Any] {
          tags = tagArray.compactMap { $0 as? String }
        } else {
          tags = []
        }
        let sourceApp = toolCall.arguments["source_app"] as? String ?? appName
        let inferredDeadline = toolCall.arguments["inferred_deadline"] as? String
        let confidence: Double
        if let confValue = toolCall.arguments["confidence"] as? Double {
          confidence = confValue
        } else if let confInt = toolCall.arguments["confidence"] as? Int {
          confidence = Double(confInt)
        } else {
          confidence = 0.5
        }
        let sourceCategory = toolCall.arguments["source_category"] as? String ?? "other"
        let sourceSubcategory = toolCall.arguments["source_subcategory"] as? String ?? "other"
        let captureKind = toolCall.arguments["capture_kind"] as? String
        let owner = toolCall.arguments["owner"] as? String
        let concreteDeliverable = toolCall.arguments["concrete_deliverable"] as? Bool
        let publicBroadcast = toolCall.arguments["public_broadcast"] as? Bool
        let directMention = toolCall.arguments["direct_mention"] as? Bool
        let duplicateOf = (toolCall.arguments["duplicate_of"] as? String).flatMap { $0.isEmpty ? nil : $0 }
        let refinesTask = (toolCall.arguments["refines_task"] as? String).flatMap { $0.isEmpty ? nil : $0 }
        let ownershipConfidence =
          (toolCall.arguments["ownership_confidence"] as? Double)
          ?? (toolCall.arguments["ownership_confidence"] as? Int).map(Double.init)

        let task = ExtractedTask(
          title: title,
          description: description?.isEmpty == true ? nil : description,
          priority: priority,
          sourceApp: sourceApp,
          inferredDeadline: inferredDeadline?.isEmpty == true ? nil : inferredDeadline,
          confidence: confidence,
          tags: tags,
          sourceCategory: sourceCategory,
          sourceSubcategory: sourceSubcategory,
          captureKind: captureKind,
          owner: owner,
          concreteDeliverable: concreteDeliverable,
          publicBroadcast: publicBroadcast,
          directMention: directMention,
          alreadyDone: captureKind == "already_done",
          duplicateOf: duplicateOf,
          refinesTask: refinesTask,
          ownershipConfidence: ownershipConfidence
        )

        log(
          "Task: extract_task — \"\(title)\" (confidence: \(confidence), priority: \(priorityStr), capture: \(captureKind ?? "unknown"))"
        )
        extractedResults.append(
          TaskExtractionResult(
            hasNewTask: true,
            task: task,
            contextSummary: contextSummary,
            currentActivity: currentActivity
          ))
        lastContextSummary = contextSummary
        lastCurrentActivity = currentActivity
        // Feed an acknowledgement back so the model can decide whether to extract
        // more commitments or stop with no_task_found.
        contents.append(
          GeminiImageToolRequest.Content(
            role: "model",
            parts: [
              GeminiImageToolRequest.Part(
                functionCall: .init(name: toolCall.name, args: ["title": title]),
                thoughtSignature: toolCall.thoughtSignature
              )
            ]
          ))
        contents.append(
          GeminiImageToolRequest.Content(
            role: "user",
            parts: [
              GeminiImageToolRequest.Part(
                functionResponse: .init(
                  name: toolCall.name,
                  response: .init(
                    result: """
                      EXTRACTED: "\(title)". \
                      Now look at the SAME screenshot again — is there ANOTHER distinct, unrelated commitment from a different request or different deliverable? \
                      (Same person asking for two different things counts as two tasks.) \
                      If yes, search_similar for the next one and extract it. \
                      If no other commitment remains, call no_task_found.
                      """)
                ))
            ]
          ))
        continue

      case "reject_task":
        let reason = toolCall.arguments["reason"] as? String ?? "Unknown reason"
        let contextSummary = toolCall.arguments["context_summary"] as? String ?? ""
        let currentActivity = toolCall.arguments["current_activity"] as? String ?? ""
        log("Task: reject_task — \(reason)")
        lastContextSummary = contextSummary
        lastCurrentActivity = currentActivity
        // reject_task no longer kills the frame — Claude may have only rejected one
        // of several commitments. Feed the rejection back and let it look for others.
        contents.append(
          GeminiImageToolRequest.Content(
            role: "model",
            parts: [
              GeminiImageToolRequest.Part(
                functionCall: .init(name: toolCall.name, args: ["reason": reason]),
                thoughtSignature: toolCall.thoughtSignature
              )
            ]
          ))
        contents.append(
          GeminiImageToolRequest.Content(
            role: "user",
            parts: [
              GeminiImageToolRequest.Part(
                functionResponse: .init(
                  name: toolCall.name,
                  response: .init(
                    result: """
                      REJECTED that candidate (duplicate / already tracked). \
                      Look at the SAME screenshot again — is there ANOTHER distinct, unrelated commitment that is NOT a duplicate of any existing task? \
                      If yes, search_similar for it and extract it. \
                      If no other commitment remains, call no_task_found.
                      """)
                ))
            ]
          ))
        continue

      case "search_similar":
        let query = toolCall.arguments["query"] as? String ?? ""
        searchCount += 1
        log("Task: search_similar query: \"\(query)\"")
        let searchResults = await executeVectorSearch(query: query)
        log("Task: Vector search returned \(searchResults.count) results")

        let searchResultsJson: String
        if let data = try? JSONEncoder().encode(searchResults),
          let json = String(data: data, encoding: .utf8)
        {
          searchResultsJson = json
        } else {
          searchResultsJson = "[]"
        }

        // Append model's tool call + function response to contents
        contents.append(
          GeminiImageToolRequest.Content(
            role: "model",
            parts: [
              GeminiImageToolRequest.Part(
                functionCall: .init(name: toolCall.name, args: ["query": query]),
                thoughtSignature: toolCall.thoughtSignature
              )
            ]
          ))
        contents.append(
          GeminiImageToolRequest.Content(
            role: "user",
            parts: [
              GeminiImageToolRequest.Part(
                functionResponse: .init(
                  name: toolCall.name,
                  response: .init(result: searchResultsJson)
                ))
            ]
          ))
        continue

      case "search_keywords":
        let query = toolCall.arguments["query"] as? String ?? ""
        searchCount += 1
        log("Task: search_keywords query: \"\(query)\"")
        let searchResults = await executeKeywordSearch(query: query)
        log("Task: Keyword search returned \(searchResults.count) results")

        let searchResultsJson: String
        if let data = try? JSONEncoder().encode(searchResults),
          let json = String(data: data, encoding: .utf8)
        {
          searchResultsJson = json
        } else {
          searchResultsJson = "[]"
        }

        // Append model's tool call + function response to contents
        contents.append(
          GeminiImageToolRequest.Content(
            role: "model",
            parts: [
              GeminiImageToolRequest.Part(
                functionCall: .init(name: toolCall.name, args: ["query": query]),
                thoughtSignature: toolCall.thoughtSignature
              )
            ]
          ))
        contents.append(
          GeminiImageToolRequest.Content(
            role: "user",
            parts: [
              GeminiImageToolRequest.Part(
                functionResponse: .init(
                  name: toolCall.name,
                  response: .init(result: searchResultsJson)
                ))
            ]
          ))
        continue

      default:
        // `break` alone only exits the switch, so the loop re-sent the
        // identical request up to 7 more times (cost + latency) on an
        // unknown tool call. Break the labeled loop to actually abort.
        log("Task: Unknown tool call: \(toolCall.name), breaking")
        break toolLoop
      }
    }

    log(
      "Task: Completed in \(searchCount) searches (loop exhausted without terminal tool), extracted: \(extractedResults.count)"
    )
    if !extractedResults.isEmpty {
      return (extractedResults, searchCount)
    }
    // No extracts and no terminator — return a synthetic no-task result so the caller
    // still saves an observation row for telemetry.
    return (
      [
        TaskExtractionResult(
          hasNewTask: false,
          task: nil,
          contextSummary: lastContextSummary.isEmpty ? "Analysis incomplete" : lastContextSummary,
          currentActivity: lastCurrentActivity.isEmpty ? "Unknown" : lastCurrentActivity
        )
      ], searchCount
    )
  }

  // MARK: - Title Validation

  /// Validates a task title for minimum specificity. Returns an error message if invalid, nil if OK.
  private static func validateTaskTitle(_ title: String, wordCount: Int) -> String? {
    let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)

    // Must not be empty
    if trimmed.isEmpty {
      return "Title is empty"
    }

    // Minimum 6 words
    if wordCount < 6 {
      return "Title too short (\(wordCount) words, minimum 6)"
    }

    // Reject titles that are purely generic verbs with no specifics
    let genericPatterns: [String] = [
      "investigate", "check logs", "clean up", "look into",
      "look through", "update to", "fix the", "review the",
      "check the", "modify the", "track the",
    ]
    let lowered = trimmed.lowercased()
    for pattern in genericPatterns {
      // If the entire title is just a generic pattern (possibly with 1-2 filler words), reject
      if lowered == pattern || (wordCount <= 4 && lowered.hasPrefix(pattern)) {
        return "Title too generic (matches vague pattern '\(pattern)')"
      }
    }

    // Must contain at least one capitalized proper noun (person, project, app name)
    // Heuristic: after the first word (verb), there should be at least one word starting with uppercase
    let words = trimmed.split(separator: " ")
    let hasProperNoun = words.dropFirst().contains { word in
      guard let first = word.first else { return false }
      return first.isUppercase
    }
    if !hasProperNoun {
      return "Title lacks a specific name (person, project, or app) — no proper nouns found after the verb"
    }

    return nil
  }

  // MARK: - Context & Search

  /// Refresh context from local SQLite + cached goals
  private func refreshContext() async -> TaskExtractionContext {
    var topRelevanceTasks: [(id: Int64, description: String, priority: String?, relevanceScore: Int?)] = []
    var recentTasks: [(id: Int64, description: String, priority: String?, relevanceScore: Int?)] = []
    var completedTasks: [(id: Int64, description: String)] = []
    var deletedTasks: [(id: Int64, description: String)] = []

    // Query both action_items (promoted + manual) and staged_tasks for full context
    do {
      topRelevanceTasks = try await ActionItemStorage.shared.getTopRelevanceTasks(limit: 30)
    } catch {
      logError("Task: Failed to load top relevance tasks", error: error)
    }

    do {
      recentTasks = try await ActionItemStorage.shared.getRecentActiveTasks(limit: 30)
    } catch {
      logError("Task: Failed to load recent tasks", error: error)
    }

    // Also include staged tasks for dedup context
    do {
      let stagedTasks = try await StagedTaskStorage.shared.getAllStagedTasks(limit: 30)
      let stagedAsTuples = stagedTasks.map { task in
        (id: Int64(0), description: task.description, priority: task.priority, relevanceScore: task.relevanceScore)
      }
      recentTasks.append(contentsOf: stagedAsTuples)
    } catch {
      logError("Task: Failed to load staged tasks for context", error: error)
    }

    // Merge: top relevance tasks first, then recent ones not already included
    let topIds = Set(topRelevanceTasks.map { $0.id })
    let activeTasks = topRelevanceTasks + recentTasks.filter { !topIds.contains($0.id) }

    do {
      completedTasks = try await ActionItemStorage.shared.getRecentCompletedTasks(limit: 10)
    } catch {
      logError("Task: Failed to load completed tasks", error: error)
    }

    do {
      deletedTasks = try await ActionItemStorage.shared.getRecentDeletedTasks(limit: 10, deletedBy: "user")
    } catch {
      logError("Task: Failed to load deleted tasks", error: error)
    }

    // Refresh goals if stale
    let timeSinceGoals = Date().timeIntervalSince(lastGoalsRefresh)
    if timeSinceGoals >= goalsRefreshInterval {
      do {
        cachedGoals = try await APIClient.shared.getGoals()
        lastGoalsRefresh = Date()
        log("Task: Refreshed \(cachedGoals.count) goals")
      } catch {
        logError("Task: Failed to refresh goals", error: error)
      }
    }

    return TaskExtractionContext(
      activeTasks: activeTasks,
      completedTasks: completedTasks,
      deletedTasks: deletedTasks,
      goals: cachedGoals
    )
  }

  /// Execute vector similarity search
  private func executeVectorSearch(query: String) async -> [TaskSearchResult] {
    var results: [TaskSearchResult] = []

    do {
      let queryEmbedding = try await EmbeddingService.shared.embed(text: query)
      let vectorResults = await EmbeddingService.shared.searchSimilar(query: queryEmbedding, topK: 10)

      for result in vectorResults where result.similarity > 0.3 {
        // Resolve against the exact table the embedding came from — the
        // index key now carries its source, so no more guessing/fallback
        // that returned an unrelated task on a rowid collision.
        switch result.source {
        case .actionItem:
          if let record = try await ActionItemStorage.shared.getActionItem(id: result.id) {
            let status: String
            if record.deleted {
              status = "deleted"
            } else if record.completed {
              status = "completed"
            } else {
              status = "active"
            }

            results.append(
              TaskSearchResult(
                id: result.id,
                description: record.description,
                status: status,
                similarity: Double(result.similarity),
                matchType: "vector",
                relevanceScore: record.relevanceScore
              ))
          }
        case .staged:
          if let staged = try await StagedTaskStorage.shared.getStagedTask(id: result.id) {
            let status: String
            if staged.deleted {
              status = "deleted"
            } else if staged.completed {
              status = "completed"
            } else {
              status = "active"
            }

            results.append(
              TaskSearchResult(
                id: result.id,
                description: staged.description,
                status: status,
                similarity: Double(result.similarity),
                matchType: "vector",
                relevanceScore: staged.relevanceScore
              ))
          }
        }
      }
    } catch {
      logError("Task: Vector search failed", error: error)
    }

    return results.sorted { ($0.similarity ?? 0) > ($1.similarity ?? 0) }
  }

  /// Execute FTS5 keyword search (searches both action_items and staged_tasks)
  private func executeKeywordSearch(query: String) async -> [TaskSearchResult] {
    var results: [TaskSearchResult] = []

    do {
      let words = query.components(separatedBy: .whitespaces)
        .map { $0.filter { $0.isLetter || $0.isNumber } }  // Strip FTS5 special chars (- : * " etc.)
        .filter { $0.count >= 3 }
      let ftsQuery = words.map { "\($0)*" }.joined(separator: " OR ")

      if !ftsQuery.isEmpty {
        // Search action_items (promoted + manual)
        let ftsResults = try await ActionItemStorage.shared.searchFTS(
          query: ftsQuery,
          limit: 10,
          includeCompleted: true,
          includeDeleted: true
        )

        for result in ftsResults {
          let status: String
          if result.deleted {
            status = "deleted"
          } else if result.completed {
            status = "completed"
          } else {
            status = "active"
          }

          results.append(
            TaskSearchResult(
              id: result.id,
              description: result.description,
              status: status,
              similarity: nil,
              matchType: "fts",
              relevanceScore: result.relevanceScore
            ))
        }

        // Also search staged_tasks
        let stagedResults = try await StagedTaskStorage.shared.searchFTS(
          query: ftsQuery,
          limit: 10
        )
        for result in stagedResults {
          results.append(
            TaskSearchResult(
              id: result.id,
              description: result.description,
              status: "active",
              similarity: nil,
              matchType: "fts",
              relevanceScore: result.relevanceScore
            ))
        }
      }
    } catch {
      logError("Task: FTS search failed", error: error)
    }

    return results
  }
}
