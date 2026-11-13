import Foundation
import OmiCore
import OmiNetwork

/// Star, visibility, folders, reprocess, merge and delete with undo. Every change shows at once
/// and is rolled back if the backend refuses.
public extension ConversationsStore {
    enum MergeOutcome: Equatable, Sendable {
        /// The backend took it; the merged conversation replaces the sources shortly.
        case started(warning: String?)
        case needsTwo
        /// A conversation is still processing, already merging, or locked.
        case notReady
        case failed
    }

    /// The list's (or the remembered) copy of a conversation, so a change made anywhere shows everywhere.
    func current(_ conversation: Conversation) -> Conversation {
        conversations.first { $0.id == conversation.id } ?? filtered.first { $0.id == conversation.id }
            ?? known[conversation.id] ?? conversation
    }

    /// Keeps a conversation opened outside the list current (detail screens call it on load).
    func remember(_ conversation: Conversation) {
        known[conversation.id] = conversation
        replace(conversation)
    }

    func setStarred(_ id: String, _ starred: Bool) async {
        let edit = edit([id], keepInFilter: { filter != .starred || $0.isStarred }, change: { $0.isStarred = starred })
        do {
            try await api.setConversationStarred(id: id, starred: starred)
        } catch {
            revert(edit)
        }
    }

    /// `.shared` makes the link work for anyone who has it. Returns whether the backend agreed.
    @discardableResult
    func setVisibility(_ id: String, _ visibility: Conversation.Visibility) async -> Bool {
        let edit = edit([id]) { $0.visibility = visibility }
        do {
            try await api.setConversationVisibility(id: id, visibility: visibility)
            return true
        } catch {
            revert(edit)
            return false
        }
    }

    /// Moves into a folder, or out of every folder with `nil`.
    func move(_ ids: [String], to folderID: String?) async {
        guard !ids.isEmpty else { return }
        let edit = edit(Set(ids), keepInFilter: { filter.keeps($0) }, change: { $0.folderID = folderID })
        do {
            if let folderID, ids.count > 1 {
                try await api.moveConversations(ids: ids, toFolder: folderID)
            } else {
                for id in ids {
                    try await api.moveConversation(id: id, toFolder: folderID)
                }
            }
        } catch {
            revert(edit)
        }
        await loadFolders()
    }

    /// Summarizes again (also the retry for a failed summary), with one summary app when
    /// `appID` is given. Returns the new detail.
    @discardableResult
    func reprocess(_ id: String, appID: String? = nil) async -> ConversationDetail? {
        let edit = edit([id]) { $0.status = .processing }
        do {
            let detail = if let appID {
                try await api.reprocessConversation(id: id, appID: appID)
            } else {
                try await api.reprocessConversation(id: id)
            }
            replace(detail.conversation)
            if known[id] != nil { known[id] = detail.conversation }
            return detail
        } catch {
            revert(edit)
            return nil
        }
    }

    /// Merges into one new conversation, with the backend's constraints checked first.
    func merge(_ ids: [String]) async -> MergeOutcome {
        var seen = Set<String>()
        let ids = ids.filter { seen.insert($0).inserted }
        guard ids.count >= 2 else { return .needsTwo }
        let selected = ids.compactMap { id in visible.first { $0.id == id } ?? conversations.first { $0.id == id } }
        guard selected.allSatisfy(\.canMerge) else { return .notReady }
        let edit = edit(Set(ids)) { $0.status = .merging }
        do {
            let warning = try await api.mergeConversations(ids: ids)
            let delay = mergeRefreshDelay
            Task { [weak self] in
                try? await Task.sleep(for: delay)
                await self?.reloadAfterMerge()
            }
            return .started(warning: warning)
        } catch {
            revert(edit)
            return .failed
        }
    }

    // MARK: Delete with undo

    /// Takes the conversations off the list now; the backend delete waits `undoWindow` for
    /// `undoDelete()`. A second delete commits the first.
    func deleteWithUndo(_ ids: [String]) {
        let ids = ids.filter { id in visible.contains { $0.id == id } || conversations.contains { $0.id == id } }
        guard !ids.isEmpty else { return }
        if let earlier = pendingDeletion {
            deletionTask?.cancel()
            pendingDeletion = nil
            Task { await send(earlier) }
        }
        let hide = Set(ids)
        let removed = conversations.enumerated().filter { hide.contains($0.element.id) }.map { ($0.offset, $0.element) }
        let removedFiltered = filtered.enumerated().filter { hide.contains($0.element.id) }.map { ($0.offset, $0.element) }
        conversations.removeAll { hide.contains($0.id) }
        filtered.removeAll { hide.contains($0.id) }
        let pending = PendingDeletion(ids: ids, removed: removed, removedFiltered: removedFiltered)
        pendingDeletion = pending
        let window = undoWindow
        deletionTask = Task { [weak self] in
            try? await Task.sleep(for: window)
            guard !Task.isCancelled else { return }
            await self?.commitDeletion()
        }
    }

    /// Puts the conversations back where they were; nothing reaches the backend.
    func undoDelete() {
        guard let pending = pendingDeletion else { return }
        deletionTask?.cancel()
        deletionTask = nil
        pendingDeletion = nil
        restore(pending)
    }

    /// Sends the waiting delete now. A conversation the backend refuses to delete comes back.
    func commitDeletion() async {
        guard let pending = pendingDeletion else { return }
        pendingDeletion = nil
        deletionTask?.cancel()
        deletionTask = nil
        await send(pending)
    }
}

extension ConversationsStore {
    func send(_ pending: PendingDeletion) async {
        var failed = Set<String>()
        for id in pending.ids {
            do {
                try await api.deleteConversation(id: id)
                known[id] = nil
            } catch {
                failed.insert(id)
            }
        }
        guard !failed.isEmpty else { return }
        restore(PendingDeletion(
            ids: pending.ids.filter(failed.contains),
            removed: pending.removed.filter { failed.contains($0.conversation.id) },
            removedFiltered: pending.removedFiltered.filter { failed.contains($0.conversation.id) }
        ))
    }
}

// MARK: Optimistic edits

extension ConversationsStore {
    /// The previous copies of what an optimistic change touched, to put back on failure.
    struct Edit {
        var main: [(index: Int, conversation: Conversation)] = []
        var filtered: [(index: Int, conversation: Conversation)] = []
        var known: [String: Conversation] = [:]
        var isEmpty: Bool {
            main.isEmpty && filtered.isEmpty && known.isEmpty
        }
    }

    /// Applies `change` to every copy of the conversations; ones that no longer match the filter
    /// (`keepInFilter`) leave the filtered list.
    func edit(_ ids: Set<String>, keepInFilter: (Conversation) -> Bool = { _ in true }, change: (inout Conversation) -> Void) -> Edit {
        var edit = Edit()
        for index in conversations.indices where ids.contains(conversations[index].id) {
            edit.main.append((index, conversations[index]))
            change(&conversations[index])
        }
        for index in filtered.indices.reversed() where ids.contains(filtered[index].id) {
            edit.filtered.append((index, filtered[index]))
            change(&filtered[index])
            if !keepInFilter(filtered[index]) { filtered.remove(at: index) }
        }
        edit.filtered.reverse()
        for id in ids {
            guard var copy = known[id] else { continue }
            edit.known[id] = copy
            change(&copy)
            known[id] = copy
        }
        return edit
    }

    func revert(_ edit: Edit) {
        for (index, old) in edit.main {
            if let current = conversations.firstIndex(where: { $0.id == old.id }) {
                conversations[current] = old
            } else {
                conversations.insert(old, at: min(index, conversations.count))
            }
        }
        for (index, old) in edit.filtered {
            if let current = filtered.firstIndex(where: { $0.id == old.id }) {
                filtered[current] = old
            } else {
                filtered.insert(old, at: min(index, filtered.count))
            }
        }
        for (id, old) in edit.known {
            known[id] = old
        }
    }

    /// Swaps in a fresher copy wherever the conversation is listed.
    func replace(_ conversation: Conversation) {
        if let index = conversations.firstIndex(where: { $0.id == conversation.id }) { conversations[index] = conversation }
        if let index = filtered.firstIndex(where: { $0.id == conversation.id }) { filtered[index] = conversation }
    }

    func restore(_ pending: PendingDeletion) {
        for (index, conversation) in pending.removed where !conversations.contains(where: { $0.id == conversation.id }) {
            conversations.insert(conversation, at: min(index, conversations.count))
        }
        for (index, conversation) in pending.removedFiltered where !filtered.contains(where: { $0.id == conversation.id }) {
            filtered.insert(conversation, at: min(index, filtered.count))
        }
    }

    func reloadAfterMerge() async {
        await load()
        if filter != .all { await reloadFiltered() }
    }
}

extension ConversationFilter {
    /// Whether a conversation still belongs in this filter after a local change.
    func keeps(_ conversation: Conversation) -> Bool {
        switch self {
        case .all: true
        case .starred: conversation.isStarred
        case let .folder(id): conversation.folderID == id
        }
    }
}
