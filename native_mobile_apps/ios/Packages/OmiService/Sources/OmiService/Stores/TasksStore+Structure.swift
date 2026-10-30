import Foundation
import OmiCore

/// Subtasks (indent / outdent) and the one-day view. Flutter keeps a flat list with an
/// `indent_level` per row: a row belongs to the nearest row above it with a smaller level.
public extension TasksStore {
    static let maxIndent = 3

    /// One level deeper is allowed only under a row above it in the same section (Flutter
    /// `_showTaskMenu`: `index <= 0 ? 0 : min(previous.indentLevel + 1, 3)`).
    func canIndent(_ id: String, now: Date = .now) -> Bool {
        guard let (rows, index) = placement(of: id, now: now), index > 0 else { return false }
        return rows[index].indentLevel < min(rows[index - 1].indentLevel + 1, Self.maxIndent)
    }

    func canOutdent(_ id: String) -> Bool {
        (tasks.first { $0.id == id }?.indentLevel ?? 0) > 0
    }

    func indent(_ id: String, now: Date = .now) async {
        guard canIndent(id, now: now), let task = tasks.first(where: { $0.id == id }) else { return }
        await setIndent(id, to: task.indentLevel + 1, now: now)
    }

    func outdent(_ id: String, now: Date = .now) async {
        guard let task = tasks.first(where: { $0.id == id }), task.indentLevel > 0 else { return }
        await setIndent(id, to: task.indentLevel - 1, now: now)
    }

    /// Display depth per row: never more than one below the row above (the first row is a parent),
    /// so a subtask whose parent sits in another section or is filtered out still reads correctly.
    func displayIndents(_ rows: [ActionItem]) -> [String: Int] {
        var result: [String: Int] = [:]
        var previous = -1
        for row in rows {
            let level = min(row.indentLevel, previous + 1, Self.maxIndent)
            result[row.id] = max(level, 0)
            previous = max(level, 0)
        }
        return result
    }

    /// The rows under `id` in its section (each following row deeper than it), for selecting a
    /// parent with its subtasks.
    func descendants(of id: String, now: Date = .now) -> [String] {
        guard let (rows, index) = placement(of: id, now: now) else { return [] }
        let level = rows[index].indentLevel
        return Array(rows[(index + 1)...].prefix { $0.indentLevel > level }.map(\.id))
    }

    /// A day's tasks: due that day, and the others added that day (Flutter `DayTasksPage` lists
    /// what was created on the day; due dates are what the Tasks tab groups by, so both show).
    func day(_ date: Date) -> (due: [ActionItem], added: [ActionItem]) {
        let due = tasks.filter { $0.dueAt.map { calendar.isDate($0, inSameDayAs: date) } ?? false }
        let added = tasks.filter { task in
            !due.contains { $0.id == task.id } && (task.createdAt.map { calendar.isDate($0, inSameDayAs: date) } ?? false)
        }
        let key = { (task: ActionItem) in (task.isCompleted ? 1 : 0, task.dueAt ?? task.createdAt ?? .distantPast) }
        let order = { (lhs: ActionItem, rhs: ActionItem) in key(lhs) < key(rhs) }
        return (due.sorted(by: order), added.sorted(by: order))
    }

    /// The section's rows in display order and the row's index in it.
    private func placement(of id: String, now: Date) -> ([ActionItem], Int)? {
        guard let task = tasks.first(where: { $0.id == id }) else { return nil }
        let target = bucket(of: task, now: now)
        guard let rows = sections(now: now).first(where: { $0.bucket == target })?.tasks,
              let index = rows.firstIndex(where: { $0.id == id })
        else { return nil }
        return (rows, index)
    }

    /// Optimistic: the new level and, so the parent stays above it, the section's current order
    /// as `sort_order` (Flutter numbers rows 1000, 2000, …). Rolls back if the backend refuses.
    private func setIndent(_ id: String, to level: Int, now: Date) async {
        guard let (rows, _) = placement(of: id, now: now) else { return }
        let before = tasks
        var entries: [TaskLayout] = []
        for (offset, row) in rows.enumerated() {
            let order = (offset + 1) * 1000
            let newLevel = row.id == id ? level : nil
            guard row.sortOrder != order || newLevel != nil else { continue }
            entries.append(TaskLayout(id: row.id, sortOrder: row.sortOrder == order ? nil : order, indentLevel: newLevel))
            if let index = tasks.firstIndex(where: { $0.id == row.id }) {
                tasks[index].sortOrder = order
                if let newLevel { tasks[index].indentLevel = newLevel }
            }
        }
        lastError = nil
        do {
            try await api.setTaskLayout(entries)
        } catch {
            tasks = before
            lastError = String(describing: error)
        }
    }
}
