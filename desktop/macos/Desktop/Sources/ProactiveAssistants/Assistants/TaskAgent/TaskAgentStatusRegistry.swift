import Foundation

/// In-memory status surface for Omi task-chat agents.
///
/// Main/floating chat runs in a separate bridge from task chats, so without a
/// small shared registry the assistant cannot answer questions like "what are
/// your subagents doing?" or diagnose task-agent timeouts/errors.
@MainActor
final class TaskAgentStatusRegistry {
  static let shared = TaskAgentStatusRegistry()

  enum Status: String {
    case idle
    case running
    case completed
    case failed
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
    var status: Status
    var statusText: String?
    var lastError: String?
    var updatedAt: Date
  }

  private var entries: [String: Entry] = [:]
  private let encoder: JSONEncoder

  private init() {
    encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
  }

  func registerTask(taskId: String, title: String?) {
    var entry = entries[taskId] ?? Entry(
      taskId: taskId,
      title: nil,
      status: .idle,
      statusText: nil,
      lastError: nil,
      updatedAt: Date())
    if let title, !title.isEmpty {
      entry.title = title
    }
    entry.updatedAt = Date()
    entries[taskId] = entry
  }

  func markRunning(taskId: String, title: String? = nil, statusText: String = "Responding...") {
    update(taskId: taskId, title: title, status: .running, statusText: statusText, lastError: nil)
  }

  func updateStatus(taskId: String, statusText: String?) {
    guard var entry = entries[taskId] else { return }
    entry.statusText = statusText
    entry.updatedAt = Date()
    entries[taskId] = entry
  }

  func markCompleted(taskId: String) {
    update(taskId: taskId, status: .completed, statusText: nil, lastError: nil)
  }

  func markFailed(taskId: String, error: String) {
    let lower = error.lowercased()
    let status: Status = lower.contains("took too long") || lower.contains("timeout") ? .timedOut : .failed
    update(taskId: taskId, status: status, statusText: nil, lastError: error)
  }

  func snapshotJSON() -> String {
    let snapshots = entries.values
      .sorted { $0.updatedAt > $1.updatedAt }
      .map { entry in
        Snapshot(
          taskId: entry.taskId,
          title: entry.title,
          status: entry.status.rawValue,
          statusText: entry.statusText,
          lastError: entry.lastError,
          updatedAt: ISO8601DateFormatter().string(from: entry.updatedAt))
      }

    let payload: [String: [Snapshot]] = ["task_agents": snapshots]
    guard let data = try? encoder.encode(payload), let json = String(data: data, encoding: .utf8) else {
      return "{\"task_agents\":[]}"
    }
    return json
  }

  private func update(
    taskId: String,
    title: String? = nil,
    status: Status,
    statusText: String?,
    lastError: String?
  ) {
    var entry = entries[taskId] ?? Entry(
      taskId: taskId,
      title: nil,
      status: .idle,
      statusText: nil,
      lastError: nil,
      updatedAt: Date())
    if let title, !title.isEmpty {
      entry.title = title
    }
    entry.status = status
    entry.statusText = statusText
    entry.lastError = lastError
    entry.updatedAt = Date()
    entries[taskId] = entry
  }
}
