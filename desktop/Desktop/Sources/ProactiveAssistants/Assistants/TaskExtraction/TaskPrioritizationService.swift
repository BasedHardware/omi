import Foundation

/// Service that re-ranks staged tasks by relevance to the user's profile,
/// goals, and task engagement history. Runs every hour, sends ALL staged tasks
/// to Gemini and receives back ONLY the tasks that need re-ranking.
/// Scores are persisted to SQLite staged_tasks table, then synced to backend.
actor TaskPrioritizationService {
    static let shared = TaskPrioritizationService()

    private var backendService: BackendProactiveService?
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

        if let last = self.lastFullRunTime {
            let hoursAgo = Int(Date().timeIntervalSince(last) / 3600)
            log("TaskPrioritize: Last full rescore was \(hoursAgo)h ago")
        } else {
            log("TaskPrioritize: No previous full rescore recorded")
        }
    }

    /// Set the backend service for Phase 2 server-side reranking.
    func configure(backendService: BackendProactiveService) {
        self.backendService = backendService
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

    /// Request server-side reranking via backend WebSocket.
    private func runFullRescore() async {
        guard !isScoringInProgress else {
            log("TaskPrioritize: [FULL] Skipping — scoring already in progress")
            return
        }
        guard let service = backendService else {
            log("TaskPrioritize: Skipping full rescore — backend service not configured")
            return
        }

        isScoringInProgress = true
        defer { isScoringInProgress = false }

        log("TaskPrioritize: [FULL] Starting server-side rescore")

        do {
            let result = try await service.rerankTasks()

            if result.updatedTasks.isEmpty {
                log("TaskPrioritize: [FULL] No tasks need re-ranking, current order is good")
                lastFullRunTime = Date()
                return
            }

            // Parse server response into reranking tuples
            let reranks: [(backendId: String, newPosition: Int)] = result.updatedTasks.compactMap { dict in
                guard let id = dict["id"] as? String,
                      let newPos = dict["new_position"] as? Int else { return nil }
                return (backendId: id, newPosition: newPos)
            }

            if !reranks.isEmpty {
                do {
                    try await StagedTaskStorage.shared.applySelectiveReranking(reranks)
                    log("TaskPrioritize: [FULL] Applied server re-ranking for \(reranks.count) staged tasks")
                } catch {
                    log("TaskPrioritize: [FULL] Failed to apply re-ranking: \(error)")
                }
            }
        } catch {
            log("TaskPrioritize: [FULL] Server reranking failed: \(error)")
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

}
