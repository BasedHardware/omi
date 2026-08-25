import Foundation

/// Checks every 60 seconds for recurring tasks that are due and triggers
/// AI chat investigations for each one via TaskChatCoordinator (agent bridge).
/// Dedup gate: `agentStartedAt` (stamped by investigateInBackground) limits
/// each task to one investigation per 4 hours — nothing advances `dueAt`, so
/// without the gate every due task would re-fire on every 60s tick forever.
@MainActor
class RecurringTaskScheduler {
  static let shared = RecurringTaskScheduler()

  private var timer: Timer?
  private var coordinator: TaskChatCoordinator?

  private init() {}

  /// Wire the canonical coordinator from `ViewModelContainer` before `start()`.
  func configure(taskChatCoordinator: TaskChatCoordinator) {
    coordinator = taskChatCoordinator
  }

  func start() {
    guard coordinator != nil else {
      log("RecurringTaskScheduler: taskChatCoordinator not configured — skipping start")
      return
    }
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
    guard let coordinator else { return }
    guard AuthState.shared.isSignedIn else { return }
    guard TaskAgentSettings.shared.isChatEnabled else { return }

    guard let tasks = try? await ActionItemStorage.shared.getDueRecurringTasks(),
      !tasks.isEmpty
    else { return }

    log("RecurringTaskScheduler: Found \(tasks.count) due recurring task(s)")

    for task in tasks where Self.shouldInvestigate(lastInvestigatedAt: task.agentStartedAt) {
      await coordinator.investigateInBackground(for: task)
    }
  }

  /// One investigation per task per 4 hours, all recurrence kinds.
  /// (The old daily-only gate also read `chatSessionId`, which nothing on
  /// the kernel path ever writes — it was permanently nil.)
  static func shouldInvestigate(lastInvestigatedAt: Date?, now: Date = Date()) -> Bool {
    guard let lastInvestigatedAt else { return true }
    return now.timeIntervalSince(lastInvestigatedAt) > 4 * 3600
  }
}
