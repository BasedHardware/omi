import Foundation
import OmiCore

/// Home's task cards: "Later" (a local snooze, the backend's due date stays), "Not a task" and
/// merges (the backend's canonical status), and the condensed cards themselves.
public extension TasksStore {
    static let snoozesKey = "omi.taskSnoozes"

    /// Open tasks after the client rules ("All tasks (n)" counts these with the full list).
    var openCount: Int {
        tasks.filter(\.isOpen).count
    }

    /// "Later": off Home until tomorrow morning; the due date on the backend does not move.
    func snooze(_ ids: [String], now: Date = .now) {
        let tomorrow = calendar.date(byAdding: .day, value: 1, to: calendar.startOfDay(for: now)) ?? now.addingTimeInterval(86400)
        for id in ids {
            snoozes[id] = tomorrow
        }
        // Expired ones go, so the list never grows.
        snoozes = snoozes.filter { $0.value > now }
        saveSnoozes()
    }

    func unsnooze(_ ids: [String]) {
        for id in ids {
            snoozes[id] = nil
        }
        saveSnoozes()
    }

    /// Every task on a card done at once (the duplicates are the same task).
    func complete(_ ids: [String]) async {
        for id in ids {
            await setCompleted(id, true)
        }
    }

    /// "Not a task": cancelled on the backend (the learning signal); it disappears everywhere.
    func markNotTask(_ ids: [String]) async {
        for id in ids {
            await setStatus(id, .cancelled)
        }
    }

    /// Optimistic: a completed task stays (ticked off), a cancelled or merged one leaves the list;
    /// rolls back if the backend refuses. Returns whether it was saved.
    @discardableResult
    func setStatus(_ id: String, _ status: ActionItem.Status, supersededBy: String? = nil) async -> Bool {
        guard let index = tasks.firstIndex(where: { $0.id == id }) else { return false }
        let previous = tasks[index]
        if status == .completed || status == .active {
            tasks[index].isCompleted = status == .completed
        } else {
            tasks.remove(at: index)
        }
        lastError = nil
        do {
            try await api.setActionItemStatus(id: id, status: status, supersededBy: supersededBy)
            return true
        } catch {
            if let current = tasks.firstIndex(where: { $0.id == id }) {
                tasks[current] = previous
            } else {
                tasks.insert(previous, at: min(index, tasks.count))
            }
            lastError = String(describing: error)
            return false
        }
    }

    internal func restoreInbox() {
        if let stored = defaults?.dictionary(forKey: Self.snoozesKey) as? [String: Double] {
            snoozes = stored.mapValues { Date(timeIntervalSince1970: $0) }.filter { $0.value > .now }
        }
        restoreTidyUp()
    }

    private func saveSnoozes() {
        defaults?.set(snoozes.mapValues(\.timeIntervalSince1970), forKey: Self.snoozesKey)
    }
}
