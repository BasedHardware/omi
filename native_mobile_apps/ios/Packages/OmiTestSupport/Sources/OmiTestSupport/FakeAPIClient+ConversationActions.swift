import Foundation
import OmiCore
import OmiNetwork

/// Backend state for star, folders, merge, reprocess, transcript edits and audio.
public final class FakeConversationActions: @unchecked Sendable {
    public var folders: [Folder] = [
        Folder(id: "f-work", name: "Work", icon: "💼", color: "#3B82F6", isSystem: true, order: 0, conversationCount: 0),
        Folder(id: "f-trips", name: "Trips", icon: "🧳", color: "#6B7280", isSystem: false, order: 1, conversationCount: 0),
    ]
    /// One entry per call, e.g. `star:c1=true`, `move:c1>f-work`.
    public internal(set) var log: [String] = []
    /// Fails just these calls (by log prefix, e.g. `star`), leaving the rest working.
    public var failing: Set<String> = []
    public var mergeWarning: String?
    /// Answers in order; the last one repeats.
    public var audio: [ConversationAudio] = [.unavailable]
    public var reprocessedOverview = "Reprocessed overview."

    public init() {}
}

public extension FakeAPIClient {
    private func record(_ kind: String, _ entry: String) throws {
        try lock.withLock {
            if let _error { throw _error }
            conversationActions.log.append("\(kind):\(entry)")
            if conversationActions.failing.contains(kind) { throw APIError.http(status: 500, body: kind) }
        }
    }

    private func updateConversation(_ id: String, _ change: (inout Conversation) -> Void) {
        lock.withLock {
            if let index = _conversations.firstIndex(where: { $0.id == id }) { change(&_conversations[index]) }
        }
    }

    func conversations(limit: Int, offset: Int, filter: ConversationFilter) async throws -> [Conversation] {
        let all = try await conversations(limit: Int.max, offset: 0)
        let matching = all.filter { conversation in
            switch filter {
            case .all: true
            case .starred: conversation.isStarred
            case let .folder(id): conversation.folderID == id
            }
        }
        return Array(matching.dropFirst(offset).prefix(limit))
    }

    func setConversationStarred(id: String, starred: Bool) async throws {
        try record("star", "\(id)=\(starred)")
        updateConversation(id) { $0.isStarred = starred }
    }

    func setConversationVisibility(id: String, visibility: Conversation.Visibility) async throws {
        try record("visibility", "\(id)=\(visibility.rawValue)")
        updateConversation(id) { $0.visibility = visibility }
    }

    /// Shared by the conversation actions and the speaker tests (each reads its own log).
    func reprocessConversation(id: String) async throws -> ConversationDetail {
        speakers.log.append("reprocess:\(id)")
        if speakers.failing.contains("reprocess") { throw APIError.http(status: 500, body: "reprocess") }
        try record("reprocess", id)
        let detail = try? await conversationDetail(id: id)
        var conversation = detail?.conversation ?? _conversations.first { $0.id == id }
            ?? Fixtures.conversation(id: id, title: "Conversation", minutesAgo: 10)
        conversation.status = .completed
        return ConversationDetail(
            conversation: conversation, summaryActionItems: [],
            transcript: speakers.transcripts[id] ?? detail?.transcript ?? [],
            summary: conversationActions.reprocessedOverview
        )
    }

    func mergeConversations(ids: [String]) async throws -> String? {
        try record("merge", ids.joined(separator: "+"))
        for id in ids {
            updateConversation(id) { $0.status = .merging }
        }
        return conversationActions.mergeWarning
    }

    func editTranscriptSegment(conversationID: String, segmentID: String, text: String) async throws {
        try record("segment", "\(conversationID)/\(segmentID)=\(text)")
    }

    func conversationAudio(id: String) async throws -> ConversationAudio {
        try record("audio", id)
        return lock.withLock {
            let actions = conversationActions
            return actions.audio.count > 1 ? actions.audio.removeFirst() : actions.audio.first ?? .unavailable
        }
    }

    func folders() async throws -> [Folder] {
        try record("folders", "list")
        return lock.withLock { conversationActions.folders }
    }

    func createFolder(_ draft: FolderDraft) async throws -> Folder {
        try record("create-folder", draft.name)
        return lock.withLock {
            let folder = Folder(
                id: "f-\(conversationActions.folders.count + 1)", name: draft.name, icon: draft.icon, color: draft.color,
                isSystem: false, order: conversationActions.folders.count, conversationCount: 0, description: draft.description
            )
            conversationActions.folders.append(folder)
            return folder
        }
    }

    func updateFolder(id: String, _ draft: FolderDraft) async throws -> Folder {
        try record("update-folder", "\(id)=\(draft.name)")
        return try lock.withLock {
            guard let index = conversationActions.folders.firstIndex(where: { $0.id == id }) else {
                throw APIError.http(status: 404, body: "folder")
            }
            conversationActions.folders[index].name = draft.name
            conversationActions.folders[index].icon = draft.icon
            conversationActions.folders[index].color = draft.color
            conversationActions.folders[index].description = draft.description
            return conversationActions.folders[index]
        }
    }

    func deleteFolder(id: String, moveTo folderID: String?) async throws {
        try record("delete-folder", "\(id)>\(folderID ?? "-")")
        lock.withLock { conversationActions.folders.removeAll { $0.id == id } }
    }

    func moveConversation(id: String, toFolder folderID: String?) async throws {
        try record("move", "\(id)>\(folderID ?? "-")")
        updateConversation(id) { $0.folderID = folderID }
    }

    func moveConversations(ids: [String], toFolder folderID: String) async throws {
        try record("bulk-move", "\(ids.joined(separator: "+"))>\(folderID)")
        for id in ids {
            updateConversation(id) { $0.folderID = folderID }
        }
    }
}
