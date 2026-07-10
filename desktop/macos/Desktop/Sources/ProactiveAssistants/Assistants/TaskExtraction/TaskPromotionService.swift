import Foundation

/// Event-driven service that promotes top-ranked staged tasks to action_items.
/// Fires when a user completes/deletes a task, on app startup, and on a 5-minute safety-net timer.
/// Purely programmatic — no AI calls. One task at a time via the backend promote endpoint.
actor TaskPromotionService {
    static let shared = TaskPromotionService()

    private let promotionDebounceInterval: TimeInterval = 30
    private var safetyTimer: Task<Void, Never>?
    private var isPromoting = false
    private var lastPromotedAt = Date.distantPast

    private init() {}

    // MARK: - Lifecycle

    /// Promote any pending staged tasks immediately on service start, then keep a
    /// short safety-net ticking to catch anything that slips through event-driven paths.
    func start() {
        Task { [weak self] in
            guard let self else { return }
            await self.startLegacyPromotion()
        }
    }

    private func startLegacyPromotion() async {
        startSafetyTimer()
        log("TaskPromotion: Legacy compatibility service started")
        await promoteIfNeeded()
    }

    private func legacyPromotionEnabled() async -> Bool {
        do {
            let control = try await APIClient.shared.getCandidateWorkflowControl()
            return TaskCaptureModePolicy.allowsLegacyPromotion(control.workflowMode)
        } catch {
            DesktopDiagnosticsManager.shared.recordFallback(
                area: "other",
                from: "workflow_control",
                to: "promotion_disabled",
                reason: "other",
                outcome: .degraded
            )
            return false
        }
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
                try? await Task.sleep(nanoseconds: 60 * 1_000_000_000)  // 60 seconds
                guard !Task.isCancelled else { break }
                guard let self = self else { break }
                log("TaskPromotion: Safety-net timer fired")
                await self.promoteIfNeeded(bypassDebounce: true)
            }
        }
    }

    // MARK: - Promotion

    /// Event-driven: called after task complete/delete, and on app startup.
    /// Loops calling the backend promote endpoint until it returns promoted=false
    /// (either cap reached or no staged tasks available).
    /// Returns the list of promoted tasks so callers can insert them directly.
    @discardableResult
    func promoteIfNeeded(bypassDebounce: Bool = false) async -> [TaskActionItem] {
        guard await legacyPromotionEnabled() else { return [] }
        guard !isPromoting else {
            log("TaskPromotion: Already promoting, skipping")
            return []
        }
        let secondsSinceLastPromotion = Date().timeIntervalSince(lastPromotedAt)
        guard bypassDebounce || secondsSinceLastPromotion >= promotionDebounceInterval else {
            log("TaskPromotion: Debounced — promoted \(Int(secondsSinceLastPromotion))s ago")
            return []
        }
        isPromoting = true
        defer { isPromoting = false }

        var promotedTasks: [TaskActionItem] = []
        // Promote at most one task per trigger. The safety timer plus explicit
        // task lifecycle events naturally fill the compatibility list quietly.
        let maxIterations = 1

        for _ in 0..<maxIterations {
            do {
                guard let response = try await TaskLegacyEffectGate.live.perform(.promotion, operation: {
                    try await APIClient.shared.promoteTopStagedTask()
                }) else {
                    log("TaskPromotion: Mode changed; stopping before promotion write")
                    break
                }

                if response.promoted, let promotedTask = response.promotedTask {
                    lastPromotedAt = Date()
                    promotedTasks.append(promotedTask)
                    log("TaskPromotion: Promoted task \(promotedTask.id) — \"\(promotedTask.description.prefix(60))\"")

                    // Sync promoted task to local ActionItemStorage
                    do {
                        let record = ActionItemRecord.from(promotedTask)
                        try await ActionItemStorage.shared.insertLocalActionItem(record)
                        log("TaskPromotion: Synced promoted task to local ActionItemStorage")
                    } catch {
                        log("TaskPromotion: Failed to sync promoted task locally: \(error)")
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

        if !promotedTasks.isEmpty {
            let count = promotedTasks.count
            log("TaskPromotion: Promoted \(count) tasks total")
            await MainActor.run {
                AnalyticsManager.shared.taskPromoted(taskCount: count)
            }
        }
        return promotedTasks
    }
}
