import Foundation
import OmiCore

/// Rows a delete took away, with where they were, until the undo window closes.
public struct PendingTaskDeletion: Equatable, Sendable {
    public struct Removed: Equatable, Sendable {
        let index: Int
        let task: ActionItem
    }

    public let ids: [String]
    let removed: [Removed]
}

/// Delete with Undo (Flutter `task_delete_undo.dart`), bulk actions and Clear completed.
public extension TasksStore {
    /// Hides the tasks now; the backend delete runs after `undoWindow` unless `undoDelete()` comes
    /// first. A second delete sends the first one right away.
    func deleteWithUndo(_ ids: [String]) {
        let hide = Set(ids)
        let removed = tasks.enumerated().filter { hide.contains($0.element.id) }
            .map { PendingTaskDeletion.Removed(index: $0.offset, task: $0.element) }
        guard !removed.isEmpty else { return }
        if let earlier = pendingDeletion {
            deletionTask?.cancel()
            pendingDeletion = nil
            Task { await send(earlier) }
        }
        tasks.removeAll { hide.contains($0.id) }
        pendingDeletion = PendingTaskDeletion(ids: removed.map(\.task.id), removed: removed)
        let window = undoWindow
        deletionTask = Task { [weak self] in
            try? await Task.sleep(for: window)
            guard !Task.isCancelled else { return }
            await self?.commitDeletion()
        }
    }

    /// Puts the tasks back where they were; nothing reaches the backend.
    func undoDelete() {
        guard let pending = pendingDeletion else { return }
        deletionTask?.cancel()
        deletionTask = nil
        pendingDeletion = nil
        restore(pending.removed)
    }

    /// Sends the waiting delete now. Tasks the backend refuses to delete come back.
    func commitDeletion() async {
        guard let pending = pendingDeletion else { return }
        pendingDeletion = nil
        deletionTask?.cancel()
        deletionTask = nil
        await send(pending)
    }

    /// Every finished task, deleted with Undo.
    func clearCompleted() {
        deleteWithUndo(tasks.filter(\.isCompleted).map(\.id))
    }

    /// Marks many tasks done (or open) at once; each rolls back on its own if the backend refuses.
    func setCompleted(_ ids: [String], _ completed: Bool) async {
        for id in ids where tasks.contains(where: { $0.id == id && $0.isCompleted != completed }) {
            await setCompleted(id, completed)
        }
    }

    internal func send(_ pending: PendingTaskDeletion) async {
        lastError = nil
        var deleted: Set<String>
        do {
            if pending.ids.count == 1 {
                try await api.deleteActionItem(id: pending.ids[0])
                deleted = Set(pending.ids)
            } else {
                deleted = try Set(await api.deleteActionItems(ids: pending.ids))
            }
        } catch {
            deleted = []
            lastError = String(describing: error)
        }
        let failed = pending.removed.filter { !deleted.contains($0.task.id) }
        if !failed.isEmpty, lastError == nil { lastError = "not deleted: \(failed.map(\.task.id))" }
        restore(failed)
    }

    private func restore(_ removed: [PendingTaskDeletion.Removed]) {
        for entry in removed where !tasks.contains(where: { $0.id == entry.task.id }) {
            tasks.insert(entry.task, at: min(entry.index, tasks.count))
        }
    }
}
