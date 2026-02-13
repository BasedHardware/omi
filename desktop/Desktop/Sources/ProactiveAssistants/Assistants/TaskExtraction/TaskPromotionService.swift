import Foundation

/// Event-driven service that promotes top-ranked staged tasks to action_items.
/// Fires when a user completes/deletes a task, on app startup, and on a 5-minute safety-net timer.
/// Purely programmatic — no AI calls. One task at a time via the backend promote endpoint.
actor TaskPromotionService {
    static let shared = TaskPromotionService()

    private let targetCount = 5
    private var safetyTimer: Task<Void, Never>?
    private var isPromoting = false

    private init() {}

    // MARK: - Lifecycle

    /// Start the 5-minute safety-net timer
    func start() {
        startSafetyTimer()
        log("TaskPromotion: Service started")
    }

    func stop() {
        safetyTimer?.cancel()
        safetyTimer = nil
        log("TaskPromotion: Service stopped")
    }

    private func startSafetyTimer() {
        safetyTimer?.cancel()
        safetyTimer = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 5 * 60 * 1_000_000_000)  // 5 minutes
                guard !Task.isCancelled else { break }
                guard let self = self else { break }
                log("TaskPromotion: Safety-net timer fired")
                await self.promoteIfNeeded()
            }
        }
    }

    // MARK: - Promotion

    /// Event-driven: called after task complete/delete, and on app startup.
    /// Loops calling the backend promote endpoint until it returns promoted=false
    /// (either cap reached or no staged tasks available).
    func promoteIfNeeded() async {
        guard !isPromoting else {
            log("TaskPromotion: Already promoting, skipping")
            return
        }
        isPromoting = true
        defer { isPromoting = false }

        var totalPromoted = 0
        let maxIterations = targetCount  // Safety cap

        for _ in 0..<maxIterations {
            do {
                let response = try await APIClient.shared.promoteTopStagedTask()

                if response.promoted, let promotedTask = response.promotedTask {
                    totalPromoted += 1
                    log("TaskPromotion: Promoted task \(promotedTask.id) — \"\(promotedTask.description.prefix(60))\"")

                    // Sync promoted task to local ActionItemStorage
                    do {
                        let record = ActionItemRecord.from(promotedTask)
                        try await ActionItemStorage.shared.insertLocalActionItem(record)
                        log("TaskPromotion: Synced promoted task to local ActionItemStorage")
                    } catch {
                        log("TaskPromotion: Failed to sync promoted task locally: \(error)")
                    }

                    // Delete from local StagedTaskStorage (if it was there)
                    if response.promotedTask?.id != nil {
                        // The staged task had a different backend ID before promotion,
                        // but we can try to match by description since the backend already
                        // deleted the staged task from Firestore
                    }
                } else {
                    let reason = response.reason ?? "cap reached or no staged tasks"
                    log("TaskPromotion: No more promotions — \(reason)")
                    break
                }
            } catch {
                log("TaskPromotion: Promote API call failed: \(error)")
                break
            }
        }

        if totalPromoted > 0 {
            log("TaskPromotion: Promoted \(totalPromoted) tasks total")
        }
    }

    /// App startup: ensure minimum tasks are present
    func ensureMinimumOnStartup() async {
        log("TaskPromotion: Checking minimum on startup")
        await promoteIfNeeded()
    }
}
