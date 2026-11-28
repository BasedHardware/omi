import Foundation
import OmiCore
import OmiNetwork

public extension FakeAPIClient {

    func createActionItem(description: String, dueAt: Date?) async throws -> ActionItem {
        if let _error { throw _error }
        lock.withLock { editLog.append("task:\(description)") }
        return ActionItem(
            id: "new-\(description)", description: description, isCompleted: false, dueAt: dueAt,
            conversationID: nil, owner: .user, workstreamID: nil, createdAt: Fixtures.now
        )
    }

    func updateActionItem(id: String, description: String, dueAt: Date?) async throws -> ActionItem {
        try lock.withLock {
            if let _error { throw _error }
            editLog.append("update-task:\(id)=\(description)")
            guard let index = _tasks.firstIndex(where: { $0.id == id }) else { throw APIError.http(status: 404, body: "") }
            _tasks[index].description = description
            _tasks[index].dueAt = dueAt
            return _tasks[index]
        }
    }

    /// Logs `status-task:<id>=<status>[><supersededBy>]`.
    func setActionItemStatus(id: String, status: ActionItem.Status, supersededBy: String?) async throws {
        try lock.withLock {
            if let _error { throw _error }
            editLog.append("status-task:\(id)=\(status.rawValue)" + (supersededBy.map { ">\($0)" } ?? ""))
            guard let index = _tasks.firstIndex(where: { $0.id == id }) else { throw APIError.http(status: 404, body: "") }
            _tasks[index].status = status
            _tasks[index].isCompleted = status == .completed
            _tasks[index].supersededBy = supersededBy
        }
    }

    func deleteActionItem(id: String) async throws {
        try lock.withLock {
            if let _error { throw _error }
            editLog.append("delete-task:\(id)")
            _tasks.removeAll { $0.id == id }
        }
    }

    func editMemory(id: String, content: String) async throws {
        if let _error { throw _error }
        lock.withLock { editLog.append("memory:\(id)=\(content)") }
    }

    func deleteMemory(id: String) async throws {
        if let _error { throw _error }
        lock.withLock { editLog.append("delete-memory:\(id)") }
    }

    func renameConversation(id: String, title: String) async throws {
        if let _error { throw _error }
        lock.withLock { editLog.append("rename:\(id)=\(title)") }
    }

    func deleteConversation(id: String) async throws {
        if let _error { throw _error }
        lock.withLock { editLog.append("delete-conversation:\(id)") }
    }

    func dailySummaries(limit _: Int) async throws -> [DailySummary] {
        summaries
    }

    func createDailySummary(date: String) async throws -> DailySummary? {
        lock.withLock { editLog.append("recap:\(date)") }
        return nil
    }

    func deleteDailySummary(id: String) async throws {
        try lock.withLock {
            if let _error { throw _error }
            editLog.append("delete-recap:\(id)")
        }
    }
}

// MARK: Voice

public extension FakeAPIClient {
    func openTranscribeStream(language _: String) async throws -> any LiveTranscriptionChannel {
        if let failure = lock.withLock({ _error }) { throw failure }
        return liveChannel
    }

    func hasSpeechProfile() async throws -> Bool {
        lock.withLock { uploadedVoice != nil }
    }

    func uploadSpeechProfile(wav: Data) async throws {
        if let failure = lock.withLock({ _error }) { throw failure }
        lock.withLock { uploadedVoice = wav }
    }

    func createMemory(content: String, category: String) async throws -> Memory {
        try lock.withLock {
            if let _error { throw _error }
            createdMemories.append(content)
            let memory = Memory(
                id: "new-memory-\(createdMemories.count)", content: content, headline: nil,
                category: category, createdAt: Fixtures.now, conversationID: nil
            )
            _memories.insert(memory, at: 0)
            return memory
        }
    }
}
