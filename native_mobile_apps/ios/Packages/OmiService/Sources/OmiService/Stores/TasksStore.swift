import Foundation
import Observation
import OmiCore
import OmiNetwork

/// Tasks across all conversations. Mirrors `action_items_provider.dart`, grouped for the new
/// Tasks tab: mine by due date, waiting on others, done.
@MainActor
@Observable
public final class TasksStore {
    public enum Phase: Equatable, Sendable { case idle, loading, loaded, failed(String) }

    public enum Bucket: String, CaseIterable, Sendable {
        case overdue, today, upcoming, someday, waitingOnOthers, completed
    }

    public private(set) var phase: Phase = .idle
    public internal(set) var tasks: [ActionItem] = []
    /// Set when a change failed and was rolled back.
    public internal(set) var lastError: String?
    /// Deleted rows waiting out the undo window (`TasksStore+Undo.swift`).
    public internal(set) var pendingDeletion: PendingTaskDeletion?
    var deletionTask: Task<Void, Never>?
    let undoWindow: Duration
    /// Tasks someone shared by link, shown in a sheet until added or dismissed (`TasksStore+Sharing.swift`).
    public internal(set) var incomingShare: SharedTasks?
    /// A short outcome to show as a toast (export done, shared tasks added, …).
    public internal(set) var notice: TaskNotice?
    /// Adds a task to Apple Reminders and returns the reminder's id; set by the app (RemindersSyncStore).
    public var reminderExporter: (@MainActor (ActionItem) async -> String?)?

    /// Task id → hidden from Home until then ("Later"; `TasksStore+Inbox.swift`). Local only.
    public internal(set) var snoozes: [String: Date] = [:]
    /// Today's tidy-up suggestion, until applied or put off (`TasksStore+TidyUp.swift`).
    public internal(set) var tidyUp: TaskTidyUp.Proposal?
    public internal(set) var isTidyingUp = false
    /// The last tidy-up without `defaults` (tests).
    var lastTidyUpInMemory: Double = 0
    /// Where the tidy-up writes the agent's raw answer (Settings › Developer › logs).
    public var log: DebugLog?
    /// Snoozes, the tidy-up's day and its suggestion; nil keeps them in memory (tests).
    let defaults: UserDefaults?

    let api: any APIClientProtocol
    let calendar: Calendar
    private let pageSize: Int

    /// `pageSize` 500 is the backend maximum; fewer pages also stay under the list rate limit.
    public init(
        api: any APIClientProtocol, calendar: Calendar = .current, pageSize: Int = 500, undoWindow: Duration = .seconds(5),
        defaults: UserDefaults? = nil, log: DebugLog? = nil
    ) {
        self.log = log
        self.api = api
        self.calendar = calendar
        self.pageSize = pageSize
        self.undoWindow = undoWindow
        self.defaults = defaults
        restoreInbox()
    }

    /// Every task: pages until one comes back short.
    public func load() async {
        if tasks.isEmpty { phase = .loading }
        do {
            let all = try await Paging.all(pageSize: pageSize) { try await api.actionItems(limit: $0, offset: $1) }
            // Rows waiting out their undo window stay hidden, and so do tasks that are gone for the
            // user: cancelled ("Not a task") and merged into another one.
            let hidden = Set(pendingDeletion?.ids ?? [])
            tasks = all.filter { !hidden.contains($0.id) && $0.status != .cancelled && $0.status != .superseded }
            phase = .loaded
        } catch {
            phase = .failed(String(describing: error))
        }
    }

    /// A task the user writes down themselves. Returns whether the backend took it.
    @discardableResult
    public func add(_ description: String, dueAt: Date?) async -> Bool {
        let text = description.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return false }
        lastError = nil
        do {
            tasks.insert(try await api.createActionItem(description: text, dueAt: dueAt), at: 0)
            return true
        } catch {
            lastError = String(describing: error)
            return false
        }
    }

    /// Tasks whose text contains the query (case and diacritics insensitive).
    public func matching(_ query: String) -> [ActionItem] {
        let query = query.trimmingCharacters(in: .whitespaces)
        guard !query.isEmpty else { return tasks }
        return tasks.filter { $0.description.localizedStandardContains(query) }
    }

    /// Optimistic: flips immediately, rolls back if the backend refuses.
    public func setCompleted(_ id: String, _ completed: Bool) async {
        guard let index = tasks.firstIndex(where: { $0.id == id }) else { return }
        tasks[index].isCompleted = completed
        lastError = nil
        do {
            try await api.setActionItem(id: id, completed: completed)
        } catch {
            if let index = tasks.firstIndex(where: { $0.id == id }) { tasks[index].isCompleted = !completed }
            lastError = String(describing: error)
        }
    }

    /// Optimistic edit of text and due date (`nil` clears it); rolls back if the backend refuses.
    /// Returns whether it was saved.
    @discardableResult
    public func update(_ id: String, description: String, dueAt: Date?) async -> Bool {
        let text = description.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let index = tasks.firstIndex(where: { $0.id == id }) else { return false }
        let previous = tasks[index]
        tasks[index].description = text
        tasks[index].dueAt = dueAt
        lastError = nil
        do {
            let saved = try await api.updateActionItem(id: id, description: text, dueAt: dueAt)
            if let index = tasks.firstIndex(where: { $0.id == id }) { tasks[index] = saved }
            return true
        } catch {
            if let index = tasks.firstIndex(where: { $0.id == id }) { tasks[index] = previous }
            lastError = String(describing: error)
            return false
        }
    }

    /// Optimistic delete; the task comes back if the backend refuses.
    public func delete(_ id: String) async {
        guard let index = tasks.firstIndex(where: { $0.id == id }) else { return }
        let removed = tasks.remove(at: index)
        lastError = nil
        do {
            try await api.deleteActionItem(id: id)
        } catch {
            tasks.insert(removed, at: min(index, tasks.count))
            lastError = String(describing: error)
        }
    }

    public func bucket(of task: ActionItem, now: Date = .now) -> Bucket {
        if task.isCompleted { return .completed }
        if task.owner == .other { return .waitingOnOthers }
        guard let due = task.dueAt else { return .someday }
        let today = calendar.startOfDay(for: now)
        if due < today { return .overdue }
        if calendar.isDate(due, inSameDayAs: now) { return .today }
        return .upcoming
    }

    /// Non-empty buckets in display order. Rows placed by hand (`sortOrder > 0`, set when a subtask is
    /// indented) come first in their order, as in Flutter; the rest by due date, then creation.
    public func sections(matching query: String = "", now: Date = .now) -> [(bucket: Bucket, tasks: [ActionItem])] {
        let grouped = Dictionary(grouping: matching(query)) { bucket(of: $0, now: now) }
        return Bucket.allCases.compactMap { bucket in
            guard let items = grouped[bucket], !items.isEmpty else { return nil }
            return (bucket, items.sorted(by: Self.displayOrder))
        }
    }

    static func displayOrder(_ lhs: ActionItem, _ rhs: ActionItem) -> Bool {
        switch (lhs.sortOrder > 0, rhs.sortOrder > 0) {
        case (true, true) where lhs.sortOrder != rhs.sortOrder: return lhs.sortOrder < rhs.sortOrder
        case (true, false): return true
        case (false, true): return false
        default:
            let left = (lhs.dueAt ?? .distantFuture, lhs.createdAt ?? .distantPast)
            return left < (rhs.dueAt ?? .distantFuture, rhs.createdAt ?? .distantPast)
        }
    }

    /// Open tasks that need attention now (overdue first, then today), for the Today briefing.
    public func focus(now: Date = .now, limit: Int = 3) -> [ActionItem] {
        sections(now: now)
            .filter { $0.bucket == .overdue || $0.bucket == .today }
            .flatMap(\.tasks)
            .prefix(limit)
            .map(\.self)
    }

    /// The canonical tasks that came out of one conversation ("next steps").
    public func tasks(forConversation id: String) -> [ActionItem] {
        tasks.filter { $0.conversationID == id && $0.owner != .other }
            .sorted { !$0.isCompleted && $1.isCompleted }
    }

    /// What others committed to in that conversation.
    public func othersTasks(forConversation id: String) -> [ActionItem] {
        tasks.filter { $0.conversationID == id && $0.owner == .other }
    }
}
