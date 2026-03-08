import Foundation

/// Service that periodically scans staged tasks and uses Gemini AI to detect
/// and remove semantic duplicates BEFORE they are promoted to action items.
/// Only operates on staged_tasks — never touches action_items.
actor TaskDeduplicationService {
    static let shared = TaskDeduplicationService()

    private var backendService: BackendProactiveService?
    private var timer: Task<Void, Never>?
    private var isRunning = false
    private var lastRunTime: Date?

    // Configuration
    private let intervalSeconds: TimeInterval = 3600    // 1 hour
    private let startupDelaySeconds: TimeInterval = 60  // 60s delay at app launch
    private let cooldownSeconds: TimeInterval = 1800    // 30-min cooldown
    private let minimumTaskCount = 3

    private init() {}

    /// Set the backend service for Phase 2 server-side deduplication.
    func configure(backendService: BackendProactiveService) {
        self.backendService = backendService
    }

    // MARK: - Lifecycle

    func start() {
        guard !isRunning else { return }
        isRunning = true
        log("TaskDedup: Service started (staged tasks only)")

        timer = Task { [weak self] in
            // Startup delay
            try? await Task.sleep(nanoseconds: UInt64(60 * 1_000_000_000))

            while !Task.isCancelled {
                guard let self = self else { break }

                // Check cooldown
                if let lastRun = await self.lastRunTime,
                   Date().timeIntervalSince(lastRun) < self.cooldownSeconds {
                    let remaining = self.cooldownSeconds - Date().timeIntervalSince(lastRun)
                    try? await Task.sleep(nanoseconds: UInt64(remaining * 1_000_000_000))
                    continue
                }

                await self.runDeduplication()

                // Wait for next interval
                try? await Task.sleep(nanoseconds: UInt64(self.intervalSeconds * 1_000_000_000))
            }
        }
    }

    func stop() {
        guard isRunning else { return }
        timer?.cancel()
        timer = nil
        isRunning = false
        log("TaskDedup: Service stopped")
    }

    // MARK: - Deduplication Logic

    private func runDeduplication() async {
        guard let service = backendService else {
            log("TaskDedup: Skipping - backend service not configured")
            return
        }

        lastRunTime = Date()
        log("TaskDedup: Starting server-side deduplication")

        do {
            let result = try await service.deduplicateTasks()

            if result.deletedIds.isEmpty {
                log("TaskDedup: No duplicates found")
                return
            }

            log("TaskDedup: Server deleted \(result.deletedIds.count) duplicates. Reason: \(result.reason)")

            // Log each deletion locally
            for deleteId in result.deletedIds {
                let logRecord = TaskDedupLogRecord(
                    deletedTaskId: deleteId,
                    deletedDescription: "server-side dedup",
                    keptTaskId: "",
                    keptDescription: "",
                    reason: result.reason,
                    deletedAt: Date()
                )
                do {
                    try await ProactiveStorage.shared.insertDedupLogRecord(logRecord)
                } catch {
                    log("TaskDedup: Failed to log deletion record: \(error)")
                }
            }
        } catch {
            log("TaskDedup: Server deduplication failed: \(error)")
        }
    }
}
