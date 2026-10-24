import Foundation
import OmiCore
import OmiNetwork

/// Backend state for bulk delete, subtasks, export, share links and the Reminders sync.
public final class FakeTaskExtras: @unchecked Sendable {
    /// One entry per call, e.g. `batch-delete:t1+t2`, `layout:t2@1`, `export:todoist=t1`.
    public internal(set) var log: [String] = []
    /// Fails just these calls (by log prefix, e.g. `export`), leaving the rest working.
    public var failing: Set<String> = []
    /// Shares the fake backend knows by token.
    public var shares: [String: SharedTasks] = [:]
    public internal(set) var accepted: Set<String> = []
    public var pendingExport: [ActionItem] = []
    public internal(set) var syncUpdates: [TaskSyncUpdate] = []

    public init() {}
}

public extension FakeAPIClient {
    private func recordTask(_ kind: String, _ entry: String) throws {
        try lock.withLock {
            if let _error { throw _error }
            taskExtras.log.append("\(kind):\(entry)")
            if taskExtras.failing.contains(kind) { throw APIError.http(status: 500, body: kind) }
        }
    }

    private func updateTask(_ id: String, _ change: (inout ActionItem) -> Void) {
        lock.withLock {
            if let index = _tasks.firstIndex(where: { $0.id == id }) { change(&_tasks[index]) }
        }
    }

    func deleteActionItems(ids: [String]) async throws -> [String] {
        try recordTask("batch-delete", ids.joined(separator: "+"))
        return lock.withLock {
            let known = ids.filter { id in _tasks.contains { $0.id == id } }
            _tasks.removeAll { ids.contains($0.id) }
            return known
        }
    }

    func setTaskLayout(_ entries: [TaskLayout]) async throws {
        let described = entries.map { entry in
            "\(entry.id)" + (entry.indentLevel.map { "@\($0)" } ?? "") + (entry.sortOrder.map { "#\($0)" } ?? "")
        }
        try recordTask("layout", described.joined(separator: ","))
        for entry in entries {
            updateTask(entry.id) { task in
                if let level = entry.indentLevel { task.indentLevel = level }
                if let order = entry.sortOrder { task.sortOrder = order }
            }
        }
    }

    func createIntegrationTask(app: String, title: String, dueAt _: Date?) async throws {
        try recordTask("export", "\(app)=\(title)")
    }

    func markActionItemExported(id: String, platform: String, appleReminderID: String?) async throws {
        try recordTask("mark-exported", "\(id)>\(platform)")
        updateTask(id) { task in
            task.exportPlatform = platform
            task.appleReminderID = appleReminderID
        }
    }

    func shareActionItems(ids: [String]) async throws -> URL {
        try recordTask("share", ids.joined(separator: "+"))
        let token = "tok-\(ids.joined(separator: "-"))"
        let items = lock.withLock {
            _tasks.filter { ids.contains($0.id) }.map { SharedTasks.Item(description: $0.description, dueAt: $0.dueAt) }
        }
        lock.withLock { taskExtras.shares[token] = SharedTasks(token: token, senderName: "Alice", tasks: items) }
        return URL(string: "https://h.omi.me/tasks/\(token)")!
    }

    func sharedActionItems(token: String) async throws -> SharedTasks {
        try recordTask("shared", token)
        guard let share = lock.withLock({ taskExtras.shares[token] }) else { throw APIError.http(status: 404, body: "expired") }
        return share
    }

    func acceptSharedActionItems(token: String) async throws -> Int {
        try recordTask("accept", token)
        return try lock.withLock {
            guard let share = taskExtras.shares[token] else { throw APIError.http(status: 404, body: "expired") }
            guard taskExtras.accepted.insert(token).inserted else { throw APIError.http(status: 409, body: "already accepted") }
            for (index, item) in share.tasks.enumerated() {
                _tasks.insert(ActionItem(
                    id: "\(token)-\(index)", description: item.description, isCompleted: false, dueAt: item.dueAt,
                    conversationID: nil, owner: .user, workstreamID: nil, createdAt: Fixtures.now
                ), at: 0)
            }
            return share.tasks.count
        }
    }

    func connectTaskIntegration(_ key: String) async throws {
        try recordTask("connect", key)
        lock.withLock { _ = connectedIntegrations.insert(key) }
    }

    func pendingReminderSync() async throws -> PendingTaskSync {
        try recordTask("pending-sync", "apple_reminders")
        return lock.withLock {
            let pending = taskExtras.pendingExport.filter { !$0.isExported }
            let synced = _tasks.filter { $0.exportPlatform == "apple_reminders" && $0.appleReminderID != nil }
            return PendingTaskSync(pendingExport: pending, synced: synced)
        }
    }

    func syncActionItems(_ updates: [TaskSyncUpdate]) async throws {
        try recordTask("sync-batch", updates.map(\.id).joined(separator: "+"))
        lock.withLock { taskExtras.syncUpdates.append(contentsOf: updates) }
        for update in updates {
            updateTask(update.id) { task in
                if let description = update.description { task.description = description }
                if let completed = update.completed { task.isCompleted = completed }
                if case let .set(due) = update.due { task.dueAt = due }
                if let platform = update.exportPlatform { task.exportPlatform = platform }
                if let reminderID = update.appleReminderID { task.appleReminderID = reminderID }
            }
            lock.withLock {
                if let index = taskExtras.pendingExport.firstIndex(where: { $0.id == update.id }), let platform = update.exportPlatform {
                    taskExtras.pendingExport[index].exportPlatform = platform
                }
            }
        }
    }
}
