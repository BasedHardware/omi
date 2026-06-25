import Foundation

/// Compatibility status surface for Omi task-chat agents.
///
/// The runtime projection is the lifecycle authority. This registry only keeps
/// task titles and forwards old call sites while tool output migrates.
@MainActor
final class TaskAgentStatusRegistry {
  static let shared = TaskAgentStatusRegistry()

  enum Status: String {
    case idle
    case running
    case completed
    case failed
    case stopped
    case timedOut = "timed_out"
  }

  struct Snapshot: Encodable {
    let taskId: String
    let title: String?
    let status: String
    let statusText: String?
    let lastError: String?
    let updatedAt: String
  }

  private struct Entry {
    var taskId: String
    var title: String?
    var statusText: String?
    var lastError: String?
    var updatedAt: Date
  }

  private var entries: [String: Entry] = [:]
  private let maxSnapshotEntries = 20
  private let maxRetainedEntries = 100
  private let encoder: JSONEncoder
  private var signOutObserver: NSObjectProtocol?

  private init() {
    encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    signOutObserver = NotificationCenter.default.addObserver(
      forName: .userDidSignOut,
      object: nil,
      queue: nil
    ) { [weak self] _ in
      Task { @MainActor in
        self?.reset()
      }
    }
  }

  func registerTask(taskId: String, title: String?) {
    var entry = entries[taskId] ?? Entry(
      taskId: taskId,
      title: nil,
      statusText: nil,
      lastError: nil,
      updatedAt: Date())
    if let title, !title.isEmpty {
      entry.title = title
    }
    entry.updatedAt = Date()
    entries[taskId] = entry
    pruneIfNeeded()
  }

  func markRunning(taskId: String, title: String? = nil, statusText: String = "Responding...") {
    update(taskId: taskId, title: title, statusText: statusText, lastError: nil)
    AgentRuntimeStatusStore.shared.updateActivity(surface: .taskChat(taskId: taskId), statusText: statusText)
  }

  func updateStatus(taskId: String, statusText: String?) {
    guard var entry = entries[taskId] else { return }
    entry.statusText = statusText
    entry.updatedAt = Date()
    entries[taskId] = entry
    AgentRuntimeStatusStore.shared.updateActivity(surface: .taskChat(taskId: taskId), statusText: statusText)
    pruneIfNeeded()
  }

  func markCompleted(taskId: String) {
    update(taskId: taskId, statusText: nil, lastError: nil)
  }

  func markFailed(taskId: String, error: String) {
    update(taskId: taskId, statusText: nil, lastError: error)
    AgentRuntimeStatusStore.shared.recordLocalFailure(surface: .taskChat(taskId: taskId), error: error)
  }

  func markStopped(taskId: String) {
    update(taskId: taskId, statusText: nil, lastError: "Stopped by user")
    AgentRuntimeStatusStore.shared.recordLocalCancellation(surface: .taskChat(taskId: taskId))
  }

  func reset() {
    entries.removeAll()
  }

  func snapshotJSON() -> String {
    let payload: [String: [Snapshot]] = ["task_agents": snapshots()]
    guard let data = try? encoder.encode(payload), let json = String(data: data, encoding: .utf8) else {
      return "{\"task_agents\":[]}"
    }
    return json
  }

  func combinedSnapshotJSON() -> String {
    struct CombinedSnapshot: Encodable {
      let task_agents: [Snapshot]
      let floating_agent_pills: [AgentPillsManager.Snapshot]
    }

    let payload = CombinedSnapshot(
      task_agents: snapshots(),
      floating_agent_pills: AgentPillsManager.shared.snapshots()
    )
    guard let data = try? encoder.encode(payload), let json = String(data: data, encoding: .utf8) else {
      return "{\"task_agents\":[],\"floating_agent_pills\":[]}"
    }
    return json
  }

  func voiceSummary() -> String {
    let recent = snapshots()
      .prefix(5)

    guard !recent.isEmpty else {
      return "No task agents are running or recently finished."
    }

    let lines = recent.map { snapshot -> String in
      let title = (snapshot.title?.isEmpty == false ? snapshot.title! : "Untitled task")
      var parts = ["\(title): \(snapshot.status.replacingOccurrences(of: "_", with: " "))"]
      if let statusText = snapshot.statusText, !statusText.isEmpty {
        parts.append(statusText)
      }
      if let lastError = snapshot.lastError, !lastError.isEmpty {
        parts.append("error: \(lastError)")
      }
      return "- " + parts.joined(separator: "; ")
    }

    return "Recent task agents:\n" + lines.joined(separator: "\n")
  }

  func combinedSummary() -> String {
    let taskSummary = voiceSummary()
    let pillSummary = AgentPillsManager.shared.statusSummary()
    return "\(taskSummary)\n\n\(pillSummary)"
  }

  private func snapshots() -> [Snapshot] {
    let projectionSnapshots = AgentRuntimeStatusStore.shared.taskProjections(limit: maxSnapshotEntries).map { projection in
      let taskId = projection.surface.externalRefId
      let entry = entries[taskId]
      return Snapshot(
        taskId: taskId,
        title: entry?.title,
        status: taskStatus(for: projection.status),
        statusText: projection.statusText ?? entry?.statusText,
        lastError: projection.errorMessage ?? entry?.lastError,
        updatedAt: ISO8601DateFormatter().string(from: projection.updatedAt))
    }

    let projectedTaskIds = Set(projectionSnapshots.map(\.taskId))
    let titleOnlySnapshots = entries.values
      .filter { !projectedTaskIds.contains($0.taskId) }
      .sorted { $0.updatedAt > $1.updatedAt }
      .prefix(max(0, maxSnapshotEntries - projectionSnapshots.count))
      .map { entry in
        Snapshot(
          taskId: entry.taskId,
          title: entry.title,
          status: "idle",
          statusText: entry.statusText,
          lastError: entry.lastError,
          updatedAt: ISO8601DateFormatter().string(from: entry.updatedAt))
      }

    return projectionSnapshots + titleOnlySnapshots
  }

  private func update(
    taskId: String,
    title: String? = nil,
    statusText: String?,
    lastError: String?
  ) {
    var entry = entries[taskId] ?? Entry(
      taskId: taskId,
      title: nil,
      statusText: nil,
      lastError: nil,
      updatedAt: Date())
    if let title, !title.isEmpty {
      entry.title = title
    }
    entry.statusText = statusText
    entry.lastError = lastError
    entry.updatedAt = Date()
    entries[taskId] = entry
    pruneIfNeeded()
  }

  private func pruneIfNeeded() {
    guard entries.count > maxRetainedEntries else { return }
    let retainedIds = Set(
      entries.values
        .sorted { $0.updatedAt > $1.updatedAt }
        .prefix(maxRetainedEntries)
        .map(\.taskId)
    )
    entries = entries.filter { retainedIds.contains($0.key) }
  }

  private func taskStatus(for status: AgentRunProjectionStatus) -> String {
    switch status {
    case .succeeded:
      return Status.completed.rawValue
    case .failed:
      return Status.failed.rawValue
    case .cancelled:
      return Status.stopped.rawValue
    case .timedOut:
      return Status.timedOut.rawValue
    case .queued, .starting, .running, .waitingInput, .waitingApproval, .cancelling:
      return Status.running.rawValue
    case .idle, .orphaned:
      return Status.idle.rawValue
    }
  }
}
