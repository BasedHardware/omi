import Foundation

/// Tasks someone shared by link (`GET v1/action-items/shared/{token}`), before they are accepted.
public struct SharedTasks: Identifiable, Hashable, Sendable {
    public struct Item: Hashable, Sendable {
        public let description: String
        public let dueAt: Date?

        public init(description: String, dueAt: Date?) {
            self.description = description
            self.dueAt = dueAt
        }
    }

    public let token: String
    public let senderName: String?
    public let tasks: [Item]

    public var id: String { token }

    public init(token: String, senderName: String?, tasks: [Item]) {
        self.token = token
        self.senderName = senderName
        self.tasks = tasks
    }
}

/// A row's place in the Tasks list (`PATCH v1/action-items/batch`); nil fields stay as they are.
public struct TaskLayout: Hashable, Sendable {
    public let id: String
    public let sortOrder: Int?
    public let indentLevel: Int?

    public init(id: String, sortOrder: Int? = nil, indentLevel: Int? = nil) {
        self.id = id
        self.sortOrder = sortOrder
        self.indentLevel = indentLevel
    }
}

/// One task's change from a Reminders sync (`PATCH v1/action-items/sync-batch`); nil fields stay.
public struct TaskSyncUpdate: Hashable, Sendable {
    public enum Due: Hashable, Sendable { case keep, set(Date?) }

    public let id: String
    public var description: String?
    public var completed: Bool?
    public var due: Due
    public var exportPlatform: String?
    public var appleReminderID: String?

    public init(
        id: String,
        description: String? = nil,
        completed: Bool? = nil,
        due: Due = .keep,
        exportPlatform: String? = nil,
        appleReminderID: String? = nil
    ) {
        self.id = id
        self.description = description
        self.completed = completed
        self.due = due
        self.exportPlatform = exportPlatform
        self.appleReminderID = appleReminderID
    }
}

/// What a Reminders sync works on (`GET v1/action-items/pending-sync`): tasks Omi asked to send
/// (`sync_requested`, not exported yet) and tasks already linked to a reminder.
public struct PendingTaskSync: Hashable, Sendable {
    public let pendingExport: [ActionItem]
    public let synced: [ActionItem]

    public init(pendingExport: [ActionItem], synced: [ActionItem]) {
        self.pendingExport = pendingExport
        self.synced = synced
    }
}
