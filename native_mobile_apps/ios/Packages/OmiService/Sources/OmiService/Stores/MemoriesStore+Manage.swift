import Foundation
import OmiCore
import OmiNetwork

/// Flutter's memory management: undo delete (`memory_delete_undo`), visibility per memory and for
/// all (`memory_management_sheet`), baseline pin (`memory_edit_sheet`), "Is this right?" review
/// (`memory_item`) and delete all. Every change is optimistic and rolls back on failure.
public extension MemoriesStore {
    var publicCount: Int {
        memories.count { $0.visibility == .public }
    }

    var privateCount: Int {
        memories.count { $0.visibility == .private }
    }

    /// A memory the backend has a real doubt about (a contradiction, someone else as the subject,
    /// out of date, unclearly heard) and the user has not answered yet; not every new memory.
    func needsReview(_ memory: Memory, now _: Date = .now) -> Bool {
        MemoryReviewRule.needsReview(memory)
    }

    // MARK: Undo delete

    /// Takes the memory off the list now; the backend delete waits `undoWindow` for `undoDelete()`.
    /// A second delete commits the first.
    func deleteWithUndo(_ id: String) {
        guard let index = memories.firstIndex(where: { $0.id == id }) else { return }
        if let earlier = pendingDeletion {
            deletionTask?.cancel()
            pendingDeletion = nil
            Task { await send(earlier) }
        }
        let pending = PendingDeletion(memory: memories.remove(at: index), index: index)
        pendingDeletion = pending
        let window = undoWindow
        deletionTask = Task { [weak self] in
            try? await Task.sleep(for: window)
            guard !Task.isCancelled, let self, pendingDeletion == pending else { return }
            pendingDeletion = nil
            await send(pending)
        }
    }

    func undoDelete() {
        guard let pending = pendingDeletion else { return }
        deletionTask?.cancel()
        deletionTask = nil
        pendingDeletion = nil
        memories.insert(pending.memory, at: min(pending.index, memories.count))
    }

    /// Sends a waiting delete at once (tests; leaving the screen).
    func commitPendingDeletion() async {
        guard let pending = pendingDeletion else { return }
        deletionTask?.cancel()
        deletionTask = nil
        pendingDeletion = nil
        await send(pending)
    }

    private func send(_ pending: PendingDeletion) async {
        do {
            try await api.deleteMemory(id: pending.memory.id)
        } catch {
            lastError = String(describing: error)
            memories.insert(pending.memory, at: min(pending.index, memories.count))
        }
    }

    // MARK: Visibility, baseline, review

    func setVisibility(_ id: String, _ visibility: Memory.Visibility) async {
        await change(id, apply: { $0.visibility = visibility }, request: {
            try await $0.setMemoryVisibility(id: id, visibility: visibility)
        })
    }

    /// Flutter has no bulk endpoint: one request per memory that differs. Returns whether all took.
    @discardableResult
    func setAllVisibility(_ visibility: Memory.Visibility) async -> Bool {
        lastError = nil
        var allTook = true
        for memory in memories where memory.visibility != visibility {
            do {
                try await api.setMemoryVisibility(id: memory.id, visibility: visibility)
                if let index = memories.firstIndex(where: { $0.id == memory.id }) { memories[index].visibility = visibility }
            } catch {
                allTook = false
                lastError = String(describing: error)
            }
        }
        return allTook
    }

    func setBaseline(_ id: String, pinned: Bool) async {
        await change(id, apply: { $0.isBaseline = pinned }, request: { try await $0.setMemoryBaseline(id: id, pinned: pinned) })
    }

    /// "Is this right?": right keeps it as reviewed; wrong discards it on the backend, so it leaves
    /// the list. Addressed by id alone: a caller that has the id but not the loaded row (the chat's
    /// review card) still votes, and the load that follows reads the verdict back.
    func review(_ id: String, isRight: Bool) async {
        lastError = nil
        let index = memories.firstIndex(where: { $0.id == id })
        let previous = index.map { memories[$0] }
        if let index {
            if isRight {
                memories[index].reviewed = true
                memories[index].userReview = true
            } else {
                memories.remove(at: index)
            }
        }
        do {
            try await api.reviewMemory(id: id, isRight: isRight)
        } catch {
            lastError = String(describing: error)
            guard let previous else { return }
            if let current = memories.firstIndex(where: { $0.id == id }) {
                memories[current] = previous
            } else {
                memories.insert(previous, at: min(index ?? 0, memories.count))
            }
        }
    }

    // MARK: Delete all

    /// Every memory, for good (Settings › Data & Privacy). Returns whether the backend took it.
    @discardableResult
    func deleteAll() async -> Bool {
        lastError = nil
        do {
            try await api.deleteAllMemories()
            deletionTask?.cancel()
            pendingDeletion = nil
            memories = []
            phase = .loaded
            return true
        } catch {
            lastError = String(describing: error)
            return false
        }
    }

    private func change(
        _ id: String, apply: (inout Memory) -> Void, request: (any APIClientProtocol) async throws -> Void
    ) async {
        guard let index = memories.firstIndex(where: { $0.id == id }) else { return }
        let previous = memories[index]
        apply(&memories[index])
        lastError = nil
        do {
            try await request(api)
        } catch {
            lastError = String(describing: error)
            if let current = memories.firstIndex(where: { $0.id == id }) { memories[current] = previous }
        }
    }
}
