import Foundation

/// Checks every 60 seconds for recurring tasks that are due and triggers
/// AI chat investigations for each one via TaskChatCoordinator (ACP bridge).
/// Dedup is automatic — investigateInBackground skips tasks with existing messages.
@MainActor
class RecurringTaskScheduler {
    static let shared = RecurringTaskScheduler()

    private var timer: Timer?
    private let coordinator: TaskChatCoordinator

    private init() {
        let provider = ChatProvider()
        coordinator = TaskChatCoordinator(chatProvider: provider)
    }

    func start() {
        guard timer == nil else { return }
        log("RecurringTaskScheduler: Starting (60s interval)")
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.checkDueTasks()
            }
        }
        // Also run immediately on start
        Task { await checkDueTasks() }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        log("RecurringTaskScheduler: Stopped")
    }

    private func checkDueTasks() async {
        guard AuthState.shared.isSignedIn else { return }
        guard TaskAgentSettings.shared.isChatEnabled else { return }

        guard let tasks = try? await ActionItemStorage.shared.getDueRecurringTasks(),
              !tasks.isEmpty else { return }

        log("RecurringTaskScheduler: Found \(tasks.count) due recurring task(s)")

        // Separate daily tasks for special handling
        let dailyTasks = tasks.filter { $0.recurrenceRule == "daily" }
        let otherTasks = tasks.filter { $0.recurrenceRule != "daily" }

        // Handle daily tasks with lighter touch - just check if investigation already exists
        for task in dailyTasks {
            // Only investigate if no recent chat session exists
            // (can't use || with await because the rhs is an @autoclosure)
            let needsInvestigation: Bool
            if task.chatSessionId == nil {
                needsInvestigation = true
            } else {
                needsInvestigation = await shouldReinvestigateDaily(task: task)
            }
            if needsInvestigation {
                await coordinator.investigateInBackground(for: task)
            }
        }

        // Handle other recurring tasks normally
        for task in otherTasks {
            await coordinator.investigateInBackground(for: task)
        }
    }

    /// Check if a daily task should be re-investigated (less frequent than other tasks)
    private func shouldReinvestigateDaily(task: TaskActionItem) async -> Bool {
        // For daily tasks, only re-investigate if more than 4 hours have passed
        // to avoid overwhelming the user with daily task investigations
        guard let lastInvestigation = task.agentStartedAt else { return true }
        let hoursSinceLastInvestigation = Date().timeIntervalSince(lastInvestigation) / 3600
        return hoursSinceLastInvestigation > 4
    }
}
