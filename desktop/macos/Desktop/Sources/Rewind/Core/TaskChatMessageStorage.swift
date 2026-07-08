import Foundation
import GRDB

// MARK: - Task Chat Message Record

/// Database record for task sidebar chat messages with embedding support and backend sync fields.
/// Each message belongs to a task (via taskId = action_items backendId).
struct TaskChatMessageRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?

    var taskId: String                    // action_items backendId
    var messageId: String                 // UUID from ChatMessage.id
    var sender: String                    // "user" or "ai"
    var messageText: String
    var contentBlocksJson: String?        // JSON-encoded content blocks for AI messages
    var resourcesJson: String?            // JSON-encoded attachment/artifact resources
    var embedding: Data?                  // 3072 Float32s for vector search (Gemini)

    var createdAt: Date
    var updatedAt: Date

    // Backend sync fields
    var backendSynced: Bool
    var backendMessageId: String?

    static let databaseTableName = "task_chat_messages"

    init(
        id: Int64? = nil,
        taskId: String,
        messageId: String,
        sender: String,
        messageText: String,
        contentBlocksJson: String? = nil,
        resourcesJson: String? = nil,
        embedding: Data? = nil,
        createdAt: Date = Date(),
        updatedAt: Date = Date(),
        backendSynced: Bool = false,
        backendMessageId: String? = nil
    ) {
        self.id = id
        self.taskId = taskId
        self.messageId = messageId
        self.sender = sender
        self.messageText = messageText
        self.contentBlocksJson = contentBlocksJson
        self.resourcesJson = resourcesJson
        self.embedding = embedding
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.backendSynced = backendSynced
        self.backendMessageId = backendMessageId
    }

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }

    // MARK: - ChatMessage Conversion

    /// Create a record from a ChatMessage for a given task
    static func from(_ message: ChatMessage, taskId: String) -> TaskChatMessageRecord {
        let senderStr = message.sender == .user ? "user" : "ai"

        // Encode content blocks as JSON for AI messages
        var blocksJson: String?
        if message.sender == .ai && !message.contentBlocks.isEmpty {
            blocksJson = encodeContentBlocks(message.contentBlocks)
        }
        let resourcesJson = ChatResource.encodeResourcesForPersistence(message.displayResources)

        return TaskChatMessageRecord(
            taskId: taskId,
            messageId: message.id,
            sender: senderStr,
            messageText: message.text,
            contentBlocksJson: blocksJson,
            resourcesJson: resourcesJson,
            createdAt: message.createdAt,
            updatedAt: Date()
        )
    }

    /// Convert back to a ChatMessage for UI display
    func toChatMessage() -> ChatMessage {
        let chatSender: ChatSender = sender == "user" ? .user : .ai
        let blocks = contentBlocksJson.flatMap { Self.decodeContentBlocks($0) } ?? []
        let resources = ChatResource.hydrateFileStates(
            resourcesJson.flatMap { ChatResource.decodeResourcesFromPersistence($0) } ?? []
        )

        return ChatMessage(
            id: messageId,
            text: messageText,
            createdAt: createdAt,
            sender: chatSender,
            isStreaming: false,
            contentBlocks: blocks,
            resources: resources
        )
    }

    // Resource JSON encoding lives on ChatResource (protocol layer).

    // MARK: - Content Block Serialization

    /// Encode ChatContentBlock array to JSON string
    private static func encodeContentBlocks(_ blocks: [ChatContentBlock]) -> String? {
        var encoded: [[String: Any]] = []
        for block in blocks {
            switch block {
            case .text(let id, let text):
                encoded.append(["type": "text", "id": id, "text": text])
            case .toolCall(let id, let name, let status, let toolUseId, let input, let output):
                // Three-way mapping: in-flight (.running, .slow, .stalled)
                // persists as "running" so reload resumes the spinner;
                // .completed → "completed"; .failed → "failed". .stalled
                // doesn't get its own code because it's a transient
                // detector-promoted state — on reload, a stalled turn is
                // already over and re-classifying as "failed" would be a
                // semantic change; keep it as "running" so existing UI
                // semantics persist. If the turn ended cleanly while the
                // tool was .slow/.stalled, completeRemainingToolCalls
                // would have already collapsed it to .completed before
                // persistence.
                let statusCode: String
                switch status {
                case .running, .slow, .stalled: statusCode = "running"
                case .completed: statusCode = "completed"
                case .failed: statusCode = "failed"
                }
                var dict: [String: Any] = [
                    "type": "toolCall",
                    "id": id,
                    "name": name,
                    "status": statusCode
                ]
                if let toolUseId { dict["toolUseId"] = toolUseId }
                if let input {
                    dict["inputSummary"] = input.summary
                    if let details = input.details { dict["inputDetails"] = details }
                }
                if let output { dict["output"] = output }
                encoded.append(dict)
            case .thinking(let id, let text):
                encoded.append(["type": "thinking", "id": id, "text": text])
            case .discoveryCard(let id, let title, let summary, let fullText):
                encoded.append(["type": "discoveryCard", "id": id, "title": title, "summary": summary, "fullText": fullText])
            case .agentSpawn(let id, let pillId, let sessionId, let runId, let title, let objective):
                var dict: [String: Any] = [
                    "type": "agentSpawn",
                    "id": id,
                    "sessionId": sessionId,
                    "runId": runId,
                    "title": title,
                    "objective": objective,
                ]
                if let pillId { dict["pillId"] = pillId.uuidString }
                encoded.append(dict)
            case .agentCompletion(let id, let pillId, let sessionId, let runId, let title, let promptSnippet, let output, let status):
                var dict: [String: Any] = [
                    "type": "agentCompletion",
                    "id": id,
                    "title": title,
                    "promptSnippet": promptSnippet,
                    "output": output,
                    "status": status,
                ]
                if let pillId { dict["pillId"] = pillId.uuidString }
                if let sessionId { dict["sessionId"] = sessionId }
                if let runId { dict["runId"] = runId }
                encoded.append(dict)
            }
        }
        guard let data = try? JSONSerialization.data(withJSONObject: encoded),
              let json = String(data: data, encoding: .utf8) else { return nil }
        return json
    }

    /// Decode JSON string back to ChatContentBlock array
    private static func decodeContentBlocks(_ json: String) -> [ChatContentBlock]? {
        guard let data = json.data(using: .utf8),
              let array = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else { return nil }

        var blocks: [ChatContentBlock] = []
        for dict in array {
            guard let type = dict["type"] as? String,
                  let id = dict["id"] as? String else { continue }

            switch type {
            case "text":
                let text = dict["text"] as? String ?? ""
                blocks.append(.text(id: id, text: text))
            case "toolCall":
                let name = dict["name"] as? String ?? ""
                let statusStr = dict["status"] as? String ?? "completed"
                // Reverse of the three-way write mapping. Unknown
                // strings fall back to .completed for forward-compat
                // with future status codes.
                let status: ToolCallStatus
                switch statusStr {
                case "running": status = .running
                case "completed": status = .completed
                case "failed": status = .failed
                default: status = .completed
                }
                let toolUseId = dict["toolUseId"] as? String
                let input: ToolCallInput?
                if let summary = dict["inputSummary"] as? String {
                    input = ToolCallInput(summary: summary, details: dict["inputDetails"] as? String)
                } else {
                    input = nil
                }
                let output = dict["output"] as? String
                blocks.append(.toolCall(id: id, name: name, status: status, toolUseId: toolUseId, input: input, output: output))
            case "thinking":
                let text = dict["text"] as? String ?? ""
                blocks.append(.thinking(id: id, text: text))
            case "discoveryCard":
                let title = dict["title"] as? String ?? ""
                let summary = dict["summary"] as? String ?? ""
                let fullText = dict["fullText"] as? String ?? ""
                blocks.append(.discoveryCard(id: id, title: title, summary: summary, fullText: fullText))
            case "agentSpawn":
                let pillId = (dict["pillId"] as? String).flatMap(UUID.init(uuidString:))
                let sessionId = dict["sessionId"] as? String ?? ""
                let runId = dict["runId"] as? String ?? ""
                let title = dict["title"] as? String ?? ""
                let objective = dict["objective"] as? String ?? ""
                blocks.append(
                    .agentSpawn(
                        id: id,
                        pillId: pillId,
                        sessionId: sessionId,
                        runId: runId,
                        title: title,
                        objective: objective
                    )
                )
            case "agentCompletion":
                let pillId = (dict["pillId"] as? String).flatMap(UUID.init(uuidString:))
                let sessionId = dict["sessionId"] as? String
                let runId = dict["runId"] as? String
                let title = dict["title"] as? String ?? ""
                let promptSnippet = dict["promptSnippet"] as? String ?? ""
                let output = dict["output"] as? String ?? ""
                let status = dict["status"] as? String ?? "completed"
                blocks.append(
                    .agentCompletion(
                        id: id,
                        pillId: pillId,
                        sessionId: sessionId,
                        runId: runId,
                        title: title,
                        promptSnippet: promptSnippet,
                        output: output,
                        status: status
                    )
                )
            default:
                break
            }
        }
        return blocks
    }
}

// MARK: - Task Chat Message Storage

/// Actor-based storage for task chat messages with local-first persistence
actor TaskChatMessageStorage {
    static let shared = TaskChatMessageStorage()

    private var _dbQueue: DatabasePool?
    private var isInitialized = false

    private init() {}

    func invalidateCache() {
        _dbQueue = nil
        isInitialized = false
    }

    private func ensureInitialized() async throws -> DatabasePool {
        if let db = _dbQueue {
            return db
        }

        do {
            try await RewindDatabase.shared.initialize()
        } catch {
            log("TaskChatMessageStorage: Database initialization failed: \(error.localizedDescription)")
            throw error
        }

        guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
            throw TaskChatMessageStorageError.databaseNotInitialized
        }

        _dbQueue = db
        isInitialized = true
        return db
    }

    // MARK: - Insert

    /// Save a single message for a task
    @discardableResult
    func insert(_ record: TaskChatMessageRecord) async throws -> TaskChatMessageRecord {
        let db = try await ensureInitialized()
        let result = try await db.write { database -> TaskChatMessageRecord in
            let record = record
            try record.insert(database)
            return record
        }
        return result
    }

    /// Save a ChatMessage for a task (convenience)
    @discardableResult
    func saveMessage(_ message: ChatMessage, taskId: String) async throws -> TaskChatMessageRecord {
        let record = TaskChatMessageRecord.from(message, taskId: taskId)
        let db = try await ensureInitialized()
        let result = try await db.write { database -> TaskChatMessageRecord in
            let record = record
            try record.insert(database)
            return record
        }
        return result
    }

    // MARK: - Query

    /// Get all messages for a task, ordered by creation time
    func getMessages(forTaskId taskId: String) async throws -> [TaskChatMessageRecord] {
        let db = try await ensureInitialized()
        return try await db.read { database in
            try TaskChatMessageRecord
                .filter(Column("taskId") == taskId)
                .order(Column("createdAt").asc)
                .fetchAll(database)
        }
    }

    // MARK: - Update

    /// Update a message's text and content blocks (for finalizing streamed AI messages)
    func updateMessage(messageId: String, text: String, contentBlocksJson: String?) async throws {
        let db = try await ensureInitialized()
        try await db.write { database in
            try database.execute(
                sql: """
                    UPDATE task_chat_messages
                    SET messageText = ?, contentBlocksJson = ?, updatedAt = ?
                    WHERE messageId = ?
                """,
                arguments: [text, contentBlocksJson, Date(), messageId]
            )
        }
    }

    /// Update embedding for a message
    func updateEmbedding(messageId: String, embedding: Data) async throws {
        let db = try await ensureInitialized()
        try await db.write { database in
            try database.execute(
                sql: "UPDATE task_chat_messages SET embedding = ?, updatedAt = ? WHERE messageId = ?",
                arguments: [embedding, Date(), messageId]
            )
        }
    }

    /// Mark a message as synced with backend
    func markSynced(messageId: String, backendMessageId: String) async throws {
        let db = try await ensureInitialized()
        try await db.write { database in
            try database.execute(
                sql: """
                    UPDATE task_chat_messages
                    SET backendSynced = 1, backendMessageId = ?, updatedAt = ?
                    WHERE messageId = ?
                """,
                arguments: [backendMessageId, Date(), messageId]
            )
        }
    }

    // MARK: - Delete

    /// Delete all messages for a task
    func deleteMessages(forTaskId taskId: String) async throws {
        let db = try await ensureInitialized()
        try await db.write { database in
            try database.execute(
                sql: "DELETE FROM task_chat_messages WHERE taskId = ?",
                arguments: [taskId]
            )
        }
    }

    // MARK: - Search

    /// Full-text search across task chat messages
    func search(query: String, taskId: String? = nil, limit: Int = 20) async throws -> [TaskChatMessageRecord] {
        let db = try await ensureInitialized()
        return try await db.read { database in
            var sql = """
                SELECT task_chat_messages.*
                FROM task_chat_messages
                JOIN task_chat_messages_fts ON task_chat_messages.id = task_chat_messages_fts.rowid
                WHERE task_chat_messages_fts MATCH ?
            """
            var arguments: [DatabaseValueConvertible] = [query]

            if let taskId {
                sql += " AND task_chat_messages.taskId = ?"
                arguments.append(taskId)
            }

            sql += " ORDER BY rank LIMIT ?"
            arguments.append(limit)

            return try TaskChatMessageRecord.fetchAll(
                database,
                sql: sql,
                arguments: StatementArguments(arguments)
            )
        }
    }
}

// MARK: - TableDocumented

extension TaskChatMessageRecord: TableDocumented {
    static var tableDescription: String { ChatPrompts.tableAnnotations["task_chat_messages"]! }
    static var columnDescriptions: [String: String] { ChatPrompts.columnAnnotations["task_chat_messages"] ?? [:] }
}

// MARK: - Error

enum TaskChatMessageStorageError: LocalizedError {
    case databaseNotInitialized

    var errorDescription: String? {
        switch self {
        case .databaseNotInitialized:
            return "Task chat message storage database is not initialized"
        }
    }
}
