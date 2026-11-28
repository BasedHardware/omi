import Foundation
import OmiCore

/// What a task action reports back, shown once as a toast.
public struct TaskNotice: Equatable, Identifiable, Sendable {
    public enum Kind: Equatable, Sendable {
        /// `count` tasks sent to `app`; `failed` did not make it.
        case exported(app: String, count: Int, failed: Int)
        /// Everything chosen was exported before.
        case alreadyExported
        case exportFailed(app: String)
        case sharedAdded(Int)
        case shareExpired
        case shareFailed
        case shareLinkFailed
    }

    public let id = UUID()
    public let kind: Kind

    public init(_ kind: Kind) {
        self.kind = kind
    }

    public static func == (lhs: TaskNotice, rhs: TaskNotice) -> Bool { lhs.id == rhs.id }
}

/// Export to the user's task app (Flutter `ActionItemExportService`), share links and accepting
/// shared tasks (`AcceptSharedTasksSheet`).
public extension TasksStore {
    static let appleReminders = "apple_reminders"

    /// Sends each task to `app` (a backend key: todoist, asana, clickup, google_tasks, or
    /// apple_reminders through `reminderExporter`) and marks it exported. Tasks exported before are skipped.
    @discardableResult
    func export(_ ids: [String], to app: String) async -> TaskNotice.Kind {
        let chosen = tasks.filter { ids.contains($0.id) }
        let pending = chosen.filter { !$0.isExported }
        guard !pending.isEmpty else {
            let kind: TaskNotice.Kind = chosen.isEmpty ? .exportFailed(app: app) : .alreadyExported
            notice = TaskNotice(kind)
            return kind
        }
        var exported = 0
        for task in pending where await exportOne(task, to: app) {
            exported += 1
        }
        let kind: TaskNotice.Kind = exported == 0
            ? .exportFailed(app: app)
            : .exported(app: app, count: exported, failed: pending.count - exported)
        notice = TaskNotice(kind)
        return kind
    }

    /// "Export all open": my open tasks that were not exported yet.
    @discardableResult
    func exportAllOpen(to app: String) async -> TaskNotice.Kind {
        await export(tasks.filter { !$0.isCompleted && $0.owner != .other }.map(\.id), to: app)
    }

    /// The public link for these tasks, or nil (and a notice) when the backend refuses.
    func shareLink(for ids: [String]) async -> URL? {
        do {
            return try await api.shareActionItems(ids: ids)
        } catch {
            notice = TaskNotice(.shareLinkFailed)
            return nil
        }
    }

    /// A shared link was opened: loads what it holds for the accept sheet.
    func openShare(token: String) async {
        do {
            let share = try await api.sharedActionItems(token: token)
            if share.tasks.isEmpty {
                notice = TaskNotice(.shareExpired)
            } else {
                incomingShare = share
            }
        } catch {
            notice = TaskNotice(.shareExpired)
        }
    }

    /// Adds the shared tasks to this account; returns whether it worked.
    @discardableResult
    func acceptShare() async -> Bool {
        guard let share = incomingShare else { return false }
        do {
            let count = try await api.acceptSharedActionItems(token: share.token)
            incomingShare = nil
            notice = TaskNotice(.sharedAdded(count))
            await load()
            return true
        } catch {
            notice = TaskNotice(.shareFailed)
            return false
        }
    }

    func dismissShare() {
        incomingShare = nil
    }

    func clearNotice(_ shown: TaskNotice) {
        if notice == shown { notice = nil }
    }

    private func exportOne(_ task: ActionItem, to app: String) async -> Bool {
        do {
            var reminderID: String?
            if app == Self.appleReminders {
                guard let exporter = reminderExporter, let id = await exporter(task) else { return false }
                reminderID = id
            } else {
                try await api.createIntegrationTask(app: app, title: task.description, dueAt: task.dueAt)
            }
            try await api.markActionItemExported(id: task.id, platform: app, appleReminderID: reminderID)
            if let index = tasks.firstIndex(where: { $0.id == task.id }) {
                tasks[index].exportPlatform = app
                tasks[index].appleReminderID = reminderID
            }
            return true
        } catch {
            lastError = String(describing: error)
            return false
        }
    }
}
