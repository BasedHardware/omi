import Foundation

/// Service that re-ranks staged tasks by relevance to the user's profile,
/// goals, and task engagement history. Runs every hour and sends a bounded,
/// rotating window of staged tasks to Gemini.
/// Scores are persisted to SQLite staged_tasks table, then synced to backend.
actor TaskPrioritizationService {
  static let shared = TaskPrioritizationService()

  private var geminiClient: GeminiClient?
  private var timer: Task<Void, Never>?
  private var isRunning = false
  private(set) var isScoringInProgress = false

  // Persisted to UserDefaults so they survive app restarts
  private static let fullRunKey = "TaskPrioritize.lastFullRunTime"
  private static let fullAttemptKey = "TaskPrioritize.lastFullAttemptTime"
  private static let batchCursorKey = "TaskPrioritize.nextBatchStartIndex"

  private var lastFullRunTime: Date? {
    didSet { UserDefaults.standard.set(lastFullRunTime, forKey: Self.fullRunKey) }
  }

  private var lastFullAttemptTime: Date? {
    didSet { UserDefaults.standard.set(lastFullAttemptTime, forKey: Self.fullAttemptKey) }
  }

  private var nextBatchStartIndex: Int {
    didSet { UserDefaults.standard.set(nextBatchStartIndex, forKey: Self.batchCursorKey) }
  }

  // Configuration
  private let startupDelaySeconds: TimeInterval = 90
  private let checkIntervalSeconds: TimeInterval = 300  // Check every 5 minutes
  private let minimumTaskCount = 2
  private let runPolicy = TaskPrioritizationRunPolicy.production

  private var geminiClientInitAttempted = false

  private init() {
    // Restore persisted timestamps
    self.lastFullRunTime = UserDefaults.standard.object(forKey: Self.fullRunKey) as? Date
    self.lastFullAttemptTime = UserDefaults.standard.object(forKey: Self.fullAttemptKey) as? Date
    self.nextBatchStartIndex = UserDefaults.standard.integer(forKey: Self.batchCursorKey)
    // Don't eagerly init GeminiClient — API key may not be available yet

    if let last = self.lastFullRunTime {
      let hoursAgo = Int(Date().timeIntervalSince(last) / 3600)
      log("TaskPrioritize: Last full rescore was \(hoursAgo)h ago")
    } else {
      log("TaskPrioritize: No previous full rescore recorded")
    }

    if let lastAttempt = self.lastFullAttemptTime {
      let minutesAgo = Int(Date().timeIntervalSince(lastAttempt) / 60)
      log("TaskPrioritize: Last rescore attempt was \(minutesAgo)m ago")
    }
  }

  /// Lazy-initialize GeminiClient; retries if APIKeyService hasn't loaded yet.
  private func getGeminiClient() -> GeminiClient? {
    if let client = geminiClient { return client }
    guard APIKeyService.keysAvailable || !geminiClientInitAttempted else { return nil }
    geminiClientInitAttempted = true
    do {
      let client = try GeminiClient(model: ModelQoS.Gemini.lightweight, workload: .maintenance)
      geminiClient = client
      return client
    } catch {
      if !APIKeyService.keysAvailable { geminiClientInitAttempted = false }
      log("TaskPrioritize: Failed to initialize GeminiClient: \(error)")
      return nil
    }
  }

  // MARK: - Lifecycle

  func start() {
    guard !isRunning else { return }
    isRunning = true
    log("TaskPrioritize: Service started")

    timer = Task { [weak self] in
      guard let self else { return }
      // Startup delay
      try? await Task.sleep(nanoseconds: UInt64(startupDelaySeconds * 1_000_000_000))

      while !Task.isCancelled {
        await self.checkAndRescore()
        try? await Task.sleep(nanoseconds: UInt64(checkIntervalSeconds * 1_000_000_000))
      }
    }
  }

  private func legacyRankingEnabled() async -> Bool {
    await TaskLegacyEffectGate.live.isAllowed(.ranking)
  }

  func stop() {
    guard isRunning else { return }
    timer?.cancel()
    timer = nil
    isRunning = false
    log("TaskPrioritize: Service stopped")
  }

  private func checkAndRescore() async {
    guard await legacyRankingEnabled() else {
      log("TaskPrioritize: Canonical or unresolved mode; staged ranking skipped")
      return
    }
    // Regenerate AI user profile if >24h old (runs daily)
    await regenerateProfileIfNeeded()

    if runPolicy.shouldStartScheduledRun(
      now: Date(),
      lastSuccessfulRun: lastFullRunTime,
      lastAttempt: lastFullAttemptTime
    ) {
      await runFullRescore()
    }
  }

  /// Check if the AI user profile needs regeneration (>24h old) and regenerate if so
  private func regenerateProfileIfNeeded() async {
    guard await AIUserProfileService.shared.shouldGenerate() else { return }
    do {
      _ = try await AIUserProfileService.shared.generateProfile()
      log("TaskPrioritize: Regenerated AI user profile (daily)")
    } catch {
      log("TaskPrioritize: AI user profile generation failed: \(error.localizedDescription)")
    }
  }

  /// Force a full re-scoring (e.g. from settings button).
  func forceFullRescore() async {
    guard await legacyRankingEnabled() else { return }
    lastFullRunTime = nil
    await runFullRescore()
  }

  // MARK: - Bounded Rescore (Hourly)

  /// Send a bounded, rotating window of staged tasks to Gemini, and get back only
  /// the ones that need re-ranking. A persisted attempt time prevents a failed
  /// model response from being retried by every five-minute scheduler check.
  private func runFullRescore() async {
    guard await legacyRankingEnabled() else {
      log("TaskPrioritize: Canonical or unresolved mode; staged ranking skipped")
      return
    }
    guard !isScoringInProgress else {
      log("TaskPrioritize: [FULL] Skipping — scoring already in progress")
      return
    }
    guard let client = getGeminiClient() else {
      log("TaskPrioritize: Skipping full rescore — Gemini client not initialized")
      return
    }

    isScoringInProgress = true
    defer { isScoringInProgress = false }

    lastFullAttemptTime = Date()
    log("TaskPrioritize: [FULL] Starting bounded hourly rescore of staged tasks")

    // Get ALL staged tasks (not action_items)
    let allTasks: [TaskActionItem]
    do {
      allTasks = try await StagedTaskStorage.shared.getAllStagedTasks(limit: 10000)
    } catch {
      log("TaskPrioritize: [FULL] Failed to fetch staged tasks: \(error)")
      return
    }

    log("TaskPrioritize: [FULL] Found \(allTasks.count) staged tasks")

    guard allTasks.count >= minimumTaskCount else {
      log("TaskPrioritize: [FULL] Only \(allTasks.count) staged tasks, skipping")
      nextBatchStartIndex = 0
      lastFullRunTime = Date()
      return
    }

    // Fetch context
    let (referenceContext, profile, goals) = await fetchContext()

    // Build the current ranking: tasks ordered by relevanceScore ASC (1 = top)
    let sortedTasks = allTasks.sorted { a, b in
      let scoreA = a.relevanceScore ?? Int.max
      let scoreB = b.relevanceScore ?? Int.max
      return scoreA < scoreB
    }

    let taskWindow = runPolicy.window(from: sortedTasks, startingAt: nextBatchStartIndex)
    guard !taskWindow.items.isEmpty else {
      log("TaskPrioritize: [FULL] No tasks selected for bounded rescore")
      return
    }

    let positionedTasks = taskWindow.items.enumerated().map { offset, task in
      PositionedTask(position: taskWindow.startIndex + offset + 1, task: task)
    }
    let requestBatches = runPolicy.requestBatches(from: positionedTasks)

    // Build context sections
    var contextParts: [String] = []

    if let profile = profile, !profile.isEmpty {
      contextParts.append("USER PROFILE:\n\(profile)")
    }

    if !goals.isEmpty {
      let goalsText = goals.enumerated().map { (i, goal) in
        var text = "\(i + 1). \(goal.title)"
        if let desc = goal.description {
          text += " — \(desc)"
        }
        text += " (\(Int(goal.progress))% complete)"
        return text
      }.joined(separator: "\n")
      contextParts.append("ACTIVE GOALS:\n\(goalsText)")
    }

    if !referenceContext.isEmpty {
      contextParts.append(referenceContext)
    }

    let contextSection = contextParts.isEmpty ? "" : contextParts.joined(separator: "\n\n") + "\n\n"

    let systemPrompt = """
      You are a task prioritization assistant. You review a ranked task list and identify \
      tasks that are misranked. Be selective — only return tasks that genuinely need to move. \
      If the ranking looks reasonable, return an empty list. Be decisive about pushing noise \
      and vague tasks down and promoting urgent, goal-aligned tasks up.
      """

    let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
      type: "object",
      properties: [
        "reranked_tasks": .init(
          type: "array",
          description: "Tasks that need to be moved, with new positions",
          items: .init(
            type: "object",
            properties: [
              "task_id": .init(type: "string", description: "The task ID"),
              "new_position": .init(type: "integer", description: "New rank position (1 = most important)"),
            ],
            required: ["task_id", "new_position"]
          )
        ),
        "reasoning": .init(type: "string", description: "Brief explanation of major ranking changes"),
      ],
      required: ["reranked_tasks", "reasoning"]
    )

    log(
      "TaskPrioritize: [FULL] Scoring positions \(taskWindow.startIndex + 1)-\(taskWindow.endIndex) "
        + "of \(sortedTasks.count) in \(requestBatches.count) bounded request(s)"
    )

    var validReranks: [ReRankingResponse.ReRankedTask] = []
    for (batchIndex, batch) in requestBatches.enumerated() {
      let taskLines = batch.map { positioned -> String in
        let task = positioned.task
        var parts = ["\(positioned.position). [id:\(task.id)] \(task.description)"]
        if let priority = task.priority {
          parts.append("[\(priority)]")
        }
        if let due = task.dueAt {
          let formatter = ISO8601DateFormatter()
          parts.append("[due: \(formatter.string(from: due))]")
        }
        return parts.joined(separator: " ")
      }.joined(separator: "\n")

      let prompt = """
        Review this window of the user's staged task ranking. The complete ranking has \
        \(sortedTasks.count) tasks (1 = most important), and this request contains global \
        positions \(batch.first?.position ?? 0)-\(batch.last?.position ?? 0).

        Identify tasks in THIS WINDOW that are MISRANKED — tasks whose current position \
        doesn't match their actual importance. Only return tasks that need to move. Do not \
        return tasks that are already well-positioned, and never return a task not shown below.

        Consider:
        1. Alignment with the user's goals and current priorities
        2. Time urgency (due date proximity)
        3. Actionability — specific tasks rank higher than vague ones
        4. Real-world importance (financial, health, commitments to others)
        5. Most AI-extracted tasks are noise — push vague/irrelevant tasks down

        \(contextSection)CURRENT TASK RANKING WINDOW (global positions):
        \(taskLines)

        Return ONLY tasks from this window that need re-ranking, with their new GLOBAL position \
        numbers. New positions are relative to the complete list (1 to \(sortedTasks.count)). \
        Return no more than \(runPolicy.maxTasksPerRequest) tasks.
        """

      let responseText: String
      do {
        responseText = try await client.sendRequest(
          prompt: prompt,
          systemPrompt: systemPrompt,
          responseSchema: responseSchema
        )
      } catch {
        log("TaskPrioritize: [FULL] Gemini request \(batchIndex + 1) failed: \(error)")
        return
      }

      let truncated = responseText.prefix(500)
      log(
        "TaskPrioritize: [FULL] Gemini response \(batchIndex + 1) (\(responseText.count) chars): "
          + "\(truncated)\(responseText.count > 500 ? "..." : "")"
      )

      guard let data = responseText.data(using: .utf8) else {
        log("TaskPrioritize: [FULL] Failed to convert response \(batchIndex + 1) to data")
        return
      }

      let result: ReRankingResponse
      do {
        result = try JSONDecoder().decode(ReRankingResponse.self, from: data)
      } catch {
        log("TaskPrioritize: [FULL] Failed to parse re-ranking response \(batchIndex + 1): \(error)")
        return
      }

      log(
        "TaskPrioritize: [FULL] Gemini returned \(result.rerankedTasks.count) tasks to re-rank "
          + "from request \(batchIndex + 1)"
      )
      if !result.reasoning.isEmpty {
        log("TaskPrioritize: [FULL] Reasoning \(batchIndex + 1): \(result.reasoning.prefix(300))")
      }

      let validIds = Set(batch.map { $0.task.id })
      let batchReranks = result.rerankedTasks.filter { validIds.contains($0.taskId) }
      if batchReranks.count != result.rerankedTasks.count {
        log(
          "TaskPrioritize: [FULL] Filtered out "
            + "\(result.rerankedTasks.count - batchReranks.count) invalid task IDs from request \(batchIndex + 1)"
        )
      }
      validReranks.append(contentsOf: batchReranks)
    }

    if !validReranks.isEmpty {
      let reranks = validReranks.map { (backendId: $0.taskId, newPosition: $0.newPosition) }
      do {
        let applied: Bool =
          try await TaskLegacyEffectGate.live.perform(.ranking) {
            try await StagedTaskStorage.shared.applySelectiveReranking(reranks)
            return true
          } ?? false
        guard applied else {
          log("TaskPrioritize: Mode changed; stopping before ranking write")
          return
        }
        log("TaskPrioritize: [FULL] Applied selective re-ranking for \(validReranks.count) staged tasks")
      } catch {
        log("TaskPrioritize: [FULL] Failed to apply re-ranking: \(error)")
        return
      }
    } else {
      log("TaskPrioritize: [FULL] No tasks need re-ranking, current order is good")
    }

    nextBatchStartIndex = taskWindow.nextStartIndex
    lastFullRunTime = Date()

    // Sync all staged scores to backend
    await syncAllScoresToBackend()

    log("TaskPrioritize: [FULL] Done.")
  }

  /// Sync all scored staged tasks to the backend
  private func syncAllScoresToBackend() async {
    do {
      let scores = try await StagedTaskStorage.shared.getAllScoredTasks()
      guard !scores.isEmpty else { return }
      let synced: Bool =
        try await TaskLegacyEffectGate.live.perform(.ranking) {
          try await APIClient.shared.batchUpdateStagedScores(scores)
          return true
        } ?? false
      guard synced else {
        log("TaskPrioritize: Mode changed; stopping before score sync")
        return
      }
      log("TaskPrioritize: Synced \(scores.count) staged scores to backend")
    } catch {
      logError("TaskPrioritize: Failed to sync staged scores to backend", error: error)
    }
  }

  // MARK: - Shared Context Fetching

  private func fetchContext() async -> (referenceContext: String, profile: String?, goals: [Goal]) {
    let userProfile = await AIUserProfileService.shared.getLatestProfile()

    let goals: [Goal]
    do {
      goals = try await APIClient.shared.getGoals()
    } catch {
      log("TaskPrioritize: Failed to fetch goals: \(error)")
      goals = []
    }

    let referenceTasks: [TaskActionItem]
    do {
      referenceTasks = try await ActionItemStorage.shared.getLocalActionItems(
        limit: 100,
        completed: true
      )
    } catch {
      log("TaskPrioritize: Failed to fetch reference tasks: \(error)")
      referenceTasks = []
    }
    let referenceContext = buildReferenceContext(referenceTasks)

    return (referenceContext, userProfile?.profileText, goals)
  }

  // MARK: - Context Builders

  private func buildReferenceContext(_ tasks: [TaskActionItem]) -> String {
    guard !tasks.isEmpty else { return "" }

    let completed = tasks.filter { !($0.description.isEmpty) }.prefix(50)
    guard !completed.isEmpty else { return "" }

    let lines = completed.map { task -> String in
      "- [completed] \(task.description)"
    }.joined(separator: "\n")

    return "TASKS THE USER HAS COMPLETED (for reference — do NOT rank these):\n\(lines)"
  }
}

// MARK: - Run Bounds

struct TaskPrioritizationRunPolicy: Sendable {
  struct Window<Element> {
    let items: [Element]
    let startIndex: Int
    let endIndex: Int
    let nextStartIndex: Int
  }

  static let production = TaskPrioritizationRunPolicy(
    successfulRunInterval: 3600,
    failedAttemptBackoff: 3600,
    maxTasksPerRequest: 100,
    maxRequestsPerRun: 2
  )

  let successfulRunInterval: TimeInterval
  let failedAttemptBackoff: TimeInterval
  let maxTasksPerRequest: Int
  let maxRequestsPerRun: Int

  var maxTasksPerRun: Int { maxTasksPerRequest * maxRequestsPerRun }

  func shouldStartScheduledRun(
    now: Date,
    lastSuccessfulRun: Date?,
    lastAttempt: Date?
  ) -> Bool {
    let successIntervalElapsed =
      lastSuccessfulRun.map { now.timeIntervalSince($0) >= successfulRunInterval } ?? true
    let attemptBackoffElapsed =
      lastAttempt.map { now.timeIntervalSince($0) >= failedAttemptBackoff } ?? true
    return successIntervalElapsed && attemptBackoffElapsed
  }

  func window<Element>(from items: [Element], startingAt persistedStartIndex: Int) -> Window<Element> {
    guard !items.isEmpty else {
      return Window(items: [], startIndex: 0, endIndex: 0, nextStartIndex: 0)
    }

    let startIndex = items.indices.contains(persistedStartIndex) ? persistedStartIndex : 0
    let endIndex = min(startIndex + maxTasksPerRun, items.count)
    let nextStartIndex = endIndex == items.count ? 0 : endIndex
    return Window(
      items: Array(items[startIndex..<endIndex]),
      startIndex: startIndex,
      endIndex: endIndex,
      nextStartIndex: nextStartIndex
    )
  }

  func requestBatches<Element>(from items: [Element]) -> [[Element]] {
    guard !items.isEmpty else { return [] }
    return stride(from: 0, to: items.count, by: maxTasksPerRequest).map { startIndex in
      let endIndex = min(startIndex + maxTasksPerRequest, items.count)
      return Array(items[startIndex..<endIndex])
    }
  }
}

private struct PositionedTask {
  let position: Int
  let task: TaskActionItem
}

// MARK: - Response Models

private struct ReRankingResponse: Codable {
  let rerankedTasks: [ReRankedTask]
  let reasoning: String

  struct ReRankedTask: Codable {
    let taskId: String
    let newPosition: Int

    enum CodingKeys: String, CodingKey {
      case taskId = "task_id"
      case newPosition = "new_position"
    }
  }

  enum CodingKeys: String, CodingKey {
    case rerankedTasks = "reranked_tasks"
    case reasoning
  }
}
