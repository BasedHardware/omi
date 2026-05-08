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
    /// Returns the list of promoted tasks so callers can insert them directly.
    @discardableResult
    func promoteIfNeeded(shouldNotify: Bool = true) async -> [TaskActionItem] {
        guard !isPromoting else {
            log("TaskPromotion: Already promoting, skipping")
            return []
        }
        isPromoting = true
        defer { isPromoting = false }

        var promotedTasks: [TaskActionItem] = []
        // Promote at most one task per trigger. Bursting up to targetCount
        // promotions in a single fire posted up to 5 "New task" notifications
        // back-to-back, which users perceived as spam. The 5-minute safety
        // timer + on-complete/on-delete events naturally fill the user's
        // task list one item at a time.
        let maxIterations = 1

        for _ in 0..<maxIterations {
            do {
                let response = try await APIClient.shared.promoteTopStagedTask()

                if response.promoted, let promotedTask = response.promotedTask {
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

                    // Send notification for the promoted task
                    let notificationsEnabled = await MainActor.run {
                        TaskAssistantSettings.shared.notificationsEnabled
                    }
                    if shouldNotify && notificationsEnabled {
                        let message = "New task: \(promotedTask.description)"
                        let context = Self.buildNotificationContext(from: promotedTask)
                        await MainActor.run {
                            NotificationService.shared.sendNotification(
                                title: "Task",
                                message: message,
                                assistantId: "task",
                                context: context
                            )
                        }
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

    // MARK: - Notification Context

    /// Build a `FloatingBarNotificationContext` so the floating bar follow-up chat
    /// can explain exactly which task the notification was about, rather than guessing
    /// from recent conversation history.
    private static func buildNotificationContext(from task: TaskActionItem) -> FloatingBarNotificationContext {
        let sourceApp = Self.parseSourceApp(from: task.metadata)
        let reasoning = Self.buildReasoning(from: task)
        return FloatingBarNotificationContext(
            sourceTitle: "Task",
            assistantId: "task",
            sourceApp: sourceApp,
            windowTitle: nil,
            contextSummary: task.contextSummary,
            currentActivity: task.currentActivity,
            reasoning: reasoning,
            detail: task.description
        )
    }

    private static func parseSourceApp(from metadataJson: String?) -> String? {
        guard let json = metadataJson,
              let data = json.data(using: .utf8),
              let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        let app = parsed["source_app"] as? String
        return (app?.isEmpty == false) ? app : nil
    }

    private static func buildReasoning(from task: TaskActionItem) -> String? {
        var parts: [String] = []
        if let priority = task.priority, !priority.isEmpty {
            parts.append("priority=\(priority)")
        }
        if let category = task.category, !category.isEmpty {
            parts.append("category=\(category)")
        }
        if let dueAt = task.dueAt {
            let formatter = ISO8601DateFormatter()
            parts.append("due=\(formatter.string(from: dueAt))")
        }
        if let source = task.source, !source.isEmpty {
            parts.append("source=\(source)")
        }
        return parts.isEmpty ? nil : "Promoted from staged tasks (" + parts.joined(separator: ", ") + ")"
    }
}
