import Foundation
import OmiCore

/// Where a task came from: its conversation (from the loaded list, else fetched) and the words
/// it was extracted from, so every task can say why it exists.
public extension ConversationsStore {
    /// The task's source conversation when known (the loaded list or a detail fetched for it).
    func source(of task: ActionItem) -> Conversation? {
        guard let id = task.conversationID else { return nil }
        return current(id: id) ?? sourceDetails[id]?.conversation
    }

    /// The transcript words (or the context line) the task was extracted from, once its
    /// conversation's detail is loaded (`loadSources`).
    func quote(of task: ActionItem) -> String? {
        guard let id = task.conversationID, let detail = sourceDetails[id] else { return nil }
        return ConversationDigest.quote(forTask: task.description, in: detail)
    }

    /// Loads the details behind these tasks (each conversation once, at most `limit`, newest
    /// tasks first), so their rows can show where they came from.
    func loadSources(for tasks: [ActionItem], limit: Int = 20) async {
        var ids: [String] = []
        for task in tasks.sorted(by: { ($0.createdAt ?? .distantPast) > ($1.createdAt ?? .distantPast) }) {
            guard let id = task.conversationID, sourceDetails[id] == nil, !ids.contains(id) else { continue }
            ids.append(id)
            if ids.count == limit { break }
        }
        for id in ids {
            if let detail = try? await api.conversationDetail(id: id) { sourceDetails[id] = detail }
        }
    }

    private func current(id: String) -> Conversation? {
        known[id] ?? conversations.first { $0.id == id }
    }
}
