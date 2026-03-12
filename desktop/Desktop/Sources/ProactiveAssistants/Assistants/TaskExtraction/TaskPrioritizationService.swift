import Foundation

/// Service that re-ranks staged tasks by relevance to the user's profile,
/// goals, and task engagement history. Runs every hour, sends ALL staged tasks
/// to Gemini and receives back ONLY the tasks that need re-ranking.
/// Scores are persisted to SQLite staged_tasks table, then synced to backend.
actor TaskPrioritizationService {
    static let shared = TaskPrioritizationService()

    private var geminiClient: GeminiClient?
    private var timer: Task<Void, Never>?
    private var isRunning = false
    private(set) var isScoringInProgress = false

    // Persisted to UserDefaults so they survive app restarts
    private static let fullRunKey = "TaskPrioritize.lastFullRunTime"

    private var lastFullRunTime: Date? {
        didSet { UserDefaults.standard.set(lastFullRunTime, forKey: Self.fullRunKey) }
    }

    // Configuration
    private let fullRescoreInterval: TimeInterval = 3600   // 1 hour
    private let startupDelaySeconds: TimeInterval = 90
    private let checkIntervalSeconds: TimeInterval = 300    // Check every 5 minutes
    private let minimumTaskCount = 2

    private init() {
        // Restore persisted timestamps
        self.lastFullRunTime = UserDefaults.standard.object(forKey: Self.fullRunKey) as? Date

        do {
            self.geminiClient = try GeminiClient(model: "gemini-pro-latest")
        } catch {
            log("TaskPrioritize: Failed to initialize GeminiClient: \(error)")
            self.geminiClient = nil
        }

        if let last = self.lastFullRunTime {
            let hoursAgo = Int(Date().timeIntervalSince(last) / 3600)
            log("TaskPrioritize: Last full rescore was \(hoursAgo)h ago")
        } else {
            log("TaskPrioritize: No previous full rescore recorded")
        }
    }

    // MARK: - Lifecycle

    func start() {
        guard !isRunning else { return }
        isRunning = true
        log("TaskPrioritize: Service started")

        timer = Task { [weak self] in
            // Startup delay
            try? await Task.sleep(nanoseconds: UInt64(90 * 1_000_000_000))

            while !Task.isCancelled {
                guard let self = self else { break }
                await self.checkAndRescore()
                try? await Task.sleep(nanoseconds: UInt64(300 * 1_000_000_000))
            }
        }
    }

    func stop() {
        guard isRunning else { return }
        timer?.cancel()
        timer = nil
        isRunning = false
        log("TaskPrioritize: Service stopped")
    }

    private func checkAndRescore() async {
        // Regenerate AI user profile if >24h old (runs daily)
        await regenerateProfileIfNeeded()

        let now = Date()
        let timeSinceFull = lastFullRunTime.map { now.timeIntervalSince($0) } ?? .infinity
        if timeSinceFull >= fullRescoreInterval {
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
        lastFullRunTime = nil
        await runFullRescore()
    }

    // MARK: - Full Rescore (Hourly)

    /// Send ALL staged tasks to Gemini, get back only the ones that need re-ranking
    private func runFullRescore() async {
        guard !isScoringInProgress else {
            log("TaskPrioritize: [FULL] Skipping — scoring already in progress")
            return
        }
        guard let client = geminiClient else {
            log("TaskPrioritize: Skipping full rescore — Gemini client not initialized")
            return
        }

        isScoringInProgress = true
        defer { isScoringInProgress = false }

        log("TaskPrioritize: [FULL] Starting hourly rescore of staged tasks")

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

        // Build task list for the prompt with current positions
        let taskLines = sortedTasks.enumerated().map { (index, task) -> String in
            var parts = ["\(index + 1). [id:\(task.id)] \(task.description)"]
            if let priority = task.priority {
                parts.append("[\(priority)]")
            }
            if let due = task.dueAt {
                let formatter = ISO8601DateFormatter()
                parts.append("[due: \(formatter.string(from: due))]")
            }
            return parts.joined(separator: " ")
        }.joined(separator: "\n")

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

        let prompt = """
        Review the user's staged task list (ranked 1 = most important, \(sortedTasks.count) = least important).

        Identify tasks that are MISRANKED — tasks whose current position doesn't match their actual importance.
        Only return tasks that need to move. Do NOT return tasks that are already well-positioned.

        Consider:
        1. Alignment with the user's goals and current priorities
        2. Time urgency (due date proximity)
        3. Actionability — specific tasks rank higher than vague ones
        4. Real-world importance (financial, health, commitments to others)
        5. Most AI-extracted tasks are noise — push vague/irrelevant tasks down

        \(contextSection)CURRENT TASK RANKING (1 = most important):
        \(taskLines)

        Return ONLY the tasks that need re-ranking, with their new position numbers.
        New positions should be relative to the current list size (1 to \(sortedTasks.count)).
        """

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
                            "new_position": .init(type: "integer", description: "New rank position (1 = most important)")
                        ],
                        required: ["task_id", "new_position"]
                    )
                ),
                "reasoning": .init(type: "string", description: "Brief explanation of major ranking changes")
            ],
            required: ["reranked_tasks", "reasoning"]
        )

        log("TaskPrioritize: [FULL] Sending \(sortedTasks.count) staged tasks to Gemini")

        let responseText: String
        do {
            responseText = try await client.sendRequest(
                prompt: prompt,
                systemPrompt: systemPrompt,
                responseSchema: responseSchema
            )
        } catch {
            log("TaskPrioritize: [FULL] Gemini request failed: \(error)")
            return
        }

        let truncated = responseText.prefix(500)
        log("TaskPrioritize: [FULL] Gemini response (\(responseText.count) chars): \(truncated)\(responseText.count > 500 ? "..." : "")")

        guard let data = responseText.data(using: .utf8) else {
            log("TaskPrioritize: [FULL] Failed to convert response to data")
            return
        }

        let result: ReRankingResponse
        do {
            result = try JSONDecoder().decode(ReRankingResponse.self, from: data)
        } catch {
            log("TaskPrioritize: [FULL] Failed to parse re-ranking response: \(error)")
            return
        }

        log("TaskPrioritize: [FULL] Gemini returned \(result.rerankedTasks.count) tasks to re-rank")
        if !result.reasoning.isEmpty {
            log("TaskPrioritize: [FULL] Reasoning: \(result.reasoning.prefix(300))")
        }

        // Validate: only keep task IDs that exist in our list
        let validIds = Set(allTasks.map { $0.id })
        let validReranks = result.rerankedTasks.filter { validIds.contains($0.taskId) }

        if validReranks.count != result.rerankedTasks.count {
            log("TaskPrioritize: [FULL] Filtered out \(result.rerankedTasks.count - validReranks.count) invalid task IDs")
        }

        if !validReranks.isEmpty {
            let reranks = validReranks.map { (backendId: $0.taskId, newPosition: $0.newPosition) }
            do {
                try await StagedTaskStorage.shared.applySelectiveReranking(reranks)
                log("TaskPrioritize: [FULL] Applied selective re-ranking for \(validReranks.count) staged tasks")
            } catch {
                log("TaskPrioritize: [FULL] Failed to apply re-ranking: \(error)")
            }
        } else {
            log("TaskPrioritize: [FULL] No tasks need re-ranking, current order is good")
        }

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
            try await APIClient.shared.batchUpdateStagedScores(scores)
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
