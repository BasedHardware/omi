import Foundation
import GRDB

// MARK: - Task Chat Message Record

/// Database record for task sidebar chat messages with embedding support and backend sync fields.
/// `taskId` is a compatibility column name: canonical rows use the durable
/// workstream ID as their conversation key until Ticket 14 removes the legacy schema.
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
            blocksJson = ChatContentBlockCodec.encode(message.contentBlocks)
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
        let blocks = contentBlocksJson.flatMap { ChatContentBlockCodec.decode($0) } ?? []
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
    // Content-block encode/decode lives on ChatContentBlockCodec.
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

    /// Canonical write path. Persists the workstream conversation key in the
    /// compatibility `taskId` column without treating task identity as session truth.
    @discardableResult
    func saveMessage(_ message: ChatMessage, workstreamId: String) async throws -> TaskChatMessageRecord {
        try await saveMessage(message, taskId: workstreamId)
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

    func getMessages(forWorkstreamId workstreamId: String) async throws -> [TaskChatMessageRecord] {
        try await getMessages(forTaskId: workstreamId)
    }

    /// Bounded compatibility migration from the old per-task chat key to the
    /// canonical workstream conversation key. Older rows remain available only
    /// to the Ticket-14 cleanup path and are never replayed into model context.
    func migrateLegacyMessages(
        fromTaskId taskId: String,
        toWorkstreamId workstreamId: String,
        limit: Int = 100
    ) async throws -> Int {
        try await migrateLegacyMessages(
            fromTaskIds: [taskId],
            toWorkstreamId: workstreamId,
            limit: limit
        )
    }

    /// Coalesces legacy histories from every task currently scoped to a
    /// workstream. The limit applies across all source tasks, not per task.
    func migrateLegacyMessages(
        fromTaskIds taskIds: [String],
        toWorkstreamId workstreamId: String,
        limit: Int = 100
    ) async throws -> Int {
        let sourceTaskIds = Array(Set(taskIds)).filter { $0 != workstreamId }
        guard !sourceTaskIds.isEmpty else { return 0 }
        let db = try await ensureInitialized()
        return try await db.write { database in
            let sourcePlaceholders = Array(repeating: "?", count: sourceTaskIds.count).joined(separator: ",")
            var selectArguments: [DatabaseValueConvertible] = sourceTaskIds
            selectArguments.append(max(1, min(limit, 100)))
            let ids = try Int64.fetchAll(
                database,
                sql: """
                    SELECT id FROM task_chat_messages
                    WHERE taskId IN (\(sourcePlaceholders))
                    ORDER BY createdAt DESC
                    LIMIT ?
                """,
                arguments: StatementArguments(selectArguments)
            )
            guard !ids.isEmpty else { return 0 }
            let placeholders = Array(repeating: "?", count: ids.count).joined(separator: ",")
            var arguments: [DatabaseValueConvertible] = [workstreamId, Date()]
            arguments.append(contentsOf: ids)
            try database.execute(
                sql: "UPDATE task_chat_messages SET taskId = ?, updatedAt = ? WHERE id IN (\(placeholders))",
                arguments: StatementArguments(arguments)
            )
            return ids.count
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
