import Foundation
import Observation
import OmiCore
import OmiNetwork

/// A reminder as the sync sees it.
public struct ReminderSnapshot: Equatable, Sendable {
    public let title: String
    public let isCompleted: Bool
    public let dueAt: Date?
    public let lastModified: Date?

    public init(title: String, isCompleted: Bool, dueAt: Date?, lastModified: Date?) {
        self.title = title
        self.isCompleted = isCompleted
        self.dueAt = dueAt
        self.lastModified = lastModified
    }
}

/// The Reminders app, behind a seam so the sync is tested without EventKit (`EventKitReminders`).
@MainActor
public protocol RemindersAdapter: AnyObject {
    var hasAccess: Bool { get }
    func requestAccess() async -> Bool
    /// Adds a reminder to Omi's list; returns its `calendarItemIdentifier`.
    func add(title: String, notes: String?, dueAt: Date?) throws -> String
    /// Nil when the reminder no longer exists.
    func reminder(_ id: String) -> ReminderSnapshot?
    func update(_ id: String, title: String?, due: TaskSyncUpdate.Due, completed: Bool?) throws
}

/// Two-way sync between tasks and an "Omi" list in Apple Reminders, with Flutter's semantics
/// (`apple_reminders_sync_service.dart`): turning it on makes Reminders the default task app, so
/// the backend marks new tasks `sync_requested`; on every foreground (30 s apart) those are added
/// as reminders and linked by `apple_reminder_id`. For linked tasks, done wins on either side, title
/// and due date follow whichever side changed last, and a reminder deleted in Reminders deletes its task.
@MainActor
@Observable
public final class RemindersSyncStore {
    public struct Stats: Equatable, Sendable {
        public var added = 0, completionsPulled = 0, completionsPushed = 0, pulled = 0, pushed = 0, unlinked = 0
    }

    public static let platform = "apple_reminders"

    public private(set) var isEnabled = false
    public private(set) var isSyncing = false
    /// The user said no to Reminders access (iOS Settings has to change it).
    public private(set) var accessDenied = false
    public private(set) var lastStats: Stats?
    /// Reloads the task list after the sync changed tasks.
    public var onTasksChanged: (@MainActor () async -> Void)?

    private let api: any APIClientProtocol
    private let adapter: any RemindersAdapter
    private let cooldown: TimeInterval
    private let clock: () -> Date
    private var lastSync: Date?

    public init(
        api: any APIClientProtocol, adapter: any RemindersAdapter, cooldown: TimeInterval = 30, clock: @escaping () -> Date = { .now }
    ) {
        self.api = api
        self.adapter = adapter
        self.cooldown = cooldown
        self.clock = clock
    }

    /// On when the backend has Reminders connected and this phone may use them.
    public func refresh() async {
        let connected = await (try? api.connectedTaskApps())?.contains(Self.platform) ?? false
        isEnabled = connected && adapter.hasAccess
    }

    /// Asks for access when turning on; returns the resulting state.
    @discardableResult
    public func setEnabled(_ enabled: Bool) async -> Bool {
        if !enabled {
            try? await api.disconnectIntegration(Integration(id: Self.platform, kind: .taskApp, isConnected: true))
            isEnabled = false
            return false
        }
        let granted = adapter.hasAccess ? true : await adapter.requestAccess()
        accessDenied = !granted
        guard granted else { return false }
        do {
            try await api.connectTaskIntegration(Self.platform)
        } catch {
            return false
        }
        isEnabled = true
        lastSync = nil
        await syncIfDue()
        return true
    }

    /// The foreground sync, at most once per `cooldown`.
    public func syncIfDue() async {
        guard isEnabled, adapter.hasAccess, !isSyncing else { return }
        if let lastSync, clock().timeIntervalSince(lastSync) < cooldown { return }
        isSyncing = true
        defer { isSyncing = false }
        guard let pending = try? await api.pendingReminderSync() else { return }
        let stats = await sync(pending)
        lastSync = clock()
        lastStats = stats
        if stats != Stats() { await onTasksChanged?() }
    }

    /// Adds one task as a reminder (Export › Reminders); the caller marks it exported.
    public func addReminder(for task: ActionItem) async -> String? {
        let granted = adapter.hasAccess ? true : await adapter.requestAccess()
        guard granted else { return nil }
        return try? adapter.add(title: task.description, notes: "From Omi", dueAt: task.dueAt)
    }

    func sync(_ pending: PendingTaskSync) async -> Stats {
        var stats = Stats()
        var updates: [TaskSyncUpdate] = []
        for task in pending.pendingExport where !task.isExported {
            // Linked before (the export mark was lost): keep that reminder instead of adding a second.
            if let linked = task.appleReminderID, adapter.reminder(linked) != nil {
                updates.append(TaskSyncUpdate(id: task.id, exportPlatform: Self.platform, appleReminderID: linked))
            } else if let id = try? adapter.add(title: task.description, notes: "From Omi", dueAt: task.dueAt) {
                updates.append(TaskSyncUpdate(id: task.id, exportPlatform: Self.platform, appleReminderID: id))
                stats.added += 1
            }
        }
        var deletions: [String] = []
        for task in pending.synced {
            guard let reminderID = task.appleReminderID else { continue }
            guard let reminder = adapter.reminder(reminderID) else {
                deletions.append(task.id)
                stats.unlinked += 1
                continue
            }
            if let update = reconcile(task, reminderID: reminderID, with: reminder, stats: &stats) { updates.append(update) }
        }
        if !updates.isEmpty { try? await api.syncActionItems(updates) }
        for id in deletions {
            try? await api.deleteActionItem(id: id)
        }
        return stats
    }

    /// One linked pair: what the backend needs (returned) and what the reminder needs (written here).
    private func reconcile(_ task: ActionItem, reminderID: String, with reminder: ReminderSnapshot, stats: inout Stats) -> TaskSyncUpdate? {
        var update = TaskSyncUpdate(id: task.id)
        if reminder.isCompleted, !task.isCompleted {
            update.completed = true
            stats.completionsPulled += 1
        } else if task.isCompleted, !reminder.isCompleted {
            try? adapter.update(reminderID, title: nil, due: .keep, completed: true)
            stats.completionsPushed += 1
        }
        let titleDiffers = !reminder.title.isEmpty && reminder.title != task.description
        let dueDiffers = Self.differ(task.dueAt, reminder.dueAt)
        if let modified = reminder.lastModified, let updated = task.updatedAt, modified > updated {
            if titleDiffers { update.description = reminder.title }
            if dueDiffers { update.due = .set(reminder.dueAt) }
            if titleDiffers || dueDiffers { stats.pulled += 1 }
        } else if task.updatedAt != nil, reminder.title != task.description || dueDiffers {
            try? adapter.update(
                reminderID, title: reminder.title != task.description ? task.description : nil,
                due: dueDiffers ? .set(task.dueAt) : .keep, completed: nil
            )
            stats.pushed += 1
        }
        let changed = update.completed != nil || update.description != nil || update.due != .keep
        return changed ? update : nil
    }

    /// Due dates within a minute of each other count as the same (Flutter `_dueDatesAreDifferent`).
    static func differ(_ lhs: Date?, _ rhs: Date?) -> Bool {
        switch (lhs, rhs) {
        case (nil, nil): false
        case let (lhs?, rhs?): abs(lhs.timeIntervalSince(rhs)) > 60
        default: true
        }
    }
}
