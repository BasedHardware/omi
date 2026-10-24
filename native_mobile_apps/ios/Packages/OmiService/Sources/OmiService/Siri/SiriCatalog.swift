import Foundation
import OmiCore
import OmiNetwork

/// What Siri, Shortcuts and Spotlight reach in the app: lookups over the stores (the App Intents
/// entity queries) and the few things they do (ask, remember, add or finish a task). It runs in the
/// app's process on the same stores the screens use, so a change from Siri shows at once.
@MainActor
public struct SiriCatalog {
    public let conversations: ConversationsStore
    public let tasks: TasksStore
    public let memories: MemoriesStore
    public let chat: ChatStore

    /// How many items a picker or Spotlight suggestion list shows.
    public static let suggestionLimit = 12

    public init(conversations: ConversationsStore, tasks: TasksStore, memories: MemoriesStore, chat: ChatStore) {
        self.conversations = conversations
        self.tasks = tasks
        self.memories = memories
        self.chat = chat
    }

    // MARK: Lookups

    /// In the order asked, skipping ids that are gone; fetches a conversation older than the list.
    public func conversations(ids: [String]) async -> [Conversation] {
        if conversations.phase == .idle { await conversations.load() }
        var found: [Conversation] = []
        for id in ids {
            if let conversation = await conversations.conversation(id: id) { found.append(conversation) }
        }
        return found
    }

    /// Title or overview contains the text; the newest first.
    public func conversations(matching text: String) async -> [Conversation] {
        if conversations.phase == .idle { await conversations.load() }
        let query = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let usable = conversations.conversations.filter { $0.status == .completed }
        guard !query.isEmpty else { return Array(usable.prefix(Self.suggestionLimit)) }
        return usable.filter { $0.title.localizedStandardContains(query) || $0.overview.localizedStandardContains(query) }
    }

    public func tasks(ids: [String]) async -> [ActionItem] {
        await loadTasks()
        return ids.compactMap { id in tasks.tasks.first { $0.id == id } }
    }

    /// The user's own tasks containing the text; open ones only unless `includeCompleted`. Soonest due first.
    public func tasks(matching text: String, includeCompleted: Bool = false) async -> [ActionItem] {
        await loadTasks()
        let mine = tasks.matching(text).filter { $0.owner != .other && (includeCompleted || !$0.isCompleted) }
        return mine.sorted { ($0.dueAt ?? .distantFuture) < ($1.dueAt ?? .distantFuture) }
    }

    public func memories(ids: [String]) async -> [Memory] {
        await loadMemories()
        return ids.compactMap { id in memories.memories.first { $0.id == id } }
    }

    public func memories(matching text: String) async -> [Memory] {
        await loadMemories()
        let query = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return Array(memories.memories.prefix(Self.suggestionLimit)) }
        return memories.memories.filter { $0.content.localizedStandardContains(query) }
    }

    public func folders(ids: [String]) async -> [Folder] {
        await loadFolders()
        return ids.compactMap { id in conversations.folders.first { $0.id == id } }
    }

    public func folders(matching text: String) async -> [Folder] {
        await loadFolders()
        let query = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let sorted = conversations.folders.sorted { $0.order < $1.order }
        return query.isEmpty ? sorted : sorted.filter { $0.name.localizedStandardContains(query) }
    }

    // MARK: Actions

    public enum Failure: Error, Equatable, Sendable {
        /// Nothing to work with (an empty question, memory or task).
        case empty
        /// The backend refused or could not be reached.
        case notSaved
        /// The task is not (or no longer) in the list.
        case unknownTask
    }

    /// Saves a memory the user dictated (Flutter's "Remember in Omi"); "that …" is dropped.
    @discardableResult
    public func remember(_ text: String) async throws(Failure) -> Memory {
        let value = SiriText.memory(text)
        guard !value.isEmpty else { throw .empty }
        guard await memories.add(value), let saved = memories.memories.first else { throw .notSaved }
        return saved
    }

    @discardableResult
    public func createTask(_ title: String, dueAt: Date?) async throws(Failure) -> ActionItem {
        let value = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { throw .empty }
        guard await tasks.add(value, dueAt: dueAt), let saved = tasks.tasks.first else { throw .notSaved }
        return saved
    }

    /// Marks the task done; already done is fine.
    public func complete(taskID: String) async throws(Failure) {
        await loadTasks()
        guard let task = tasks.tasks.first(where: { $0.id == taskID }) else { throw .unknownTask }
        guard !task.isCompleted else { return }
        await tasks.setCompleted(taskID, true)
        guard tasks.tasks.first(where: { $0.id == taskID })?.isCompleted == true else { throw .notSaved }
    }

    public enum Answer: Equatable, Sendable {
        case answered(String)
        /// A question that should be a memory ("remember that …"): Remember is the safer shortcut.
        case useRemember
        case empty
        /// The chat is answering something else right now.
        case busy
        case failed(ChatMessage.Failure?)
    }

    /// Asks Omi in the main chat, as the Ask bar does, and waits for the whole answer, so Siri can
    /// speak it and the chat shows it later (Flutter posts Siri questions to `v2/messages` too).
    public func ask(_ question: String, timeout: Duration = .seconds(25)) async -> Answer {
        let value = SiriText.question(question)
        guard !value.isEmpty else { return .empty }
        guard !SiriText.isRememberRequest(value) else { return .useRemember }
        guard !chat.isStreaming else { return .busy }
        // Without the attachments the Ask bar may be holding for its own next message.
        guard chat.send(value, files: []) else { return .busy }
        let deadline = ContinuousClock.now.advanced(by: timeout)
        while chat.isStreaming, ContinuousClock.now < deadline {
            try? await Task.sleep(for: .milliseconds(100))
        }
        guard !chat.isStreaming else {
            chat.cancel()
            return .failed(.timeout)
        }
        guard let reply = chat.messages.last, reply.sender == .omi else { return .failed(nil) }
        let text = reply.text.trimmingCharacters(in: .whitespacesAndNewlines)
        if let failure = reply.failure { return .failed(failure) }
        return text.isEmpty ? .failed(.couldNotAnswer) : .answered(text)
    }

    private func loadTasks() async {
        if tasks.phase != .loaded { await tasks.load() }
    }

    private func loadMemories() async {
        if memories.phase != .loaded { await memories.load() }
    }

    private func loadFolders() async {
        if conversations.folders.isEmpty { await conversations.loadFolders() }
    }
}

/// How Siri's words become what Omi stores or answers (Flutter's `cleanedSiriQuestion`,
/// `cleanedMemory` and `spokenAnswer`).
public enum SiriText {
    /// Siri sometimes passes the invocation along ("ask Omi about my day").
    public static func question(_ text: String) -> String {
        var result = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let prefixes = ["ask omi about ", "ask omi ", "ask about ", "ask ", "frag omi nach ", "frag omi ", "frage omi "]
        if let prefix = prefixes.first(where: { result.lowercased().hasPrefix($0) }) {
            result = String(result.dropFirst(prefix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return result
    }

    /// "Remember that I parked on level 3" saves "I parked on level 3".
    public static func memory(_ text: String) -> String {
        var result = text.trimmingCharacters(in: .whitespacesAndNewlines)
        for prefix in ["that ", "dass "] where result.lowercased().hasPrefix(prefix) {
            result = String(result.dropFirst(prefix.count))
        }
        return result.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public static func isRememberRequest(_ question: String) -> Bool {
        let lower = question.lowercased()
        return ["remember ", "to remember ", "merk dir ", "merke dir "].contains { lower.hasPrefix($0) }
    }

    /// Siri reads at most this many characters; the whole answer stays in the chat.
    public static let spokenLimit = 450

    /// "Search and answer" keeps it to a sentence or two.
    public static let shortLimit = 200

    /// The answer, cut at a word near the limit, with `more` (where the rest is) appended when cut.
    public static func spoken(_ answer: String, more: String, limit: Int = spokenLimit) -> String {
        let trimmed = answer.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > limit else { return trimmed }
        let head = trimmed.prefix(max(0, limit - more.count - 2))
        let cut = head.lastIndex(where: \.isWhitespace).map { head[..<$0] } ?? head
        return cut.trimmingCharacters(in: .whitespacesAndNewlines) + "… " + more
    }
}
