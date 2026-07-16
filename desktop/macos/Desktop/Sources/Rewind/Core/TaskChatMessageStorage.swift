import Foundation
@preconcurrency import GRDB

// MARK: - Task Chat Message Record

/// Database record for task sidebar chat messages with embedding support and backend sync fields.
/// `taskId` is a compatibility column name: canonical rows use the durable
/// workstream ID as their conversation key until Ticket 14 removes the legacy schema.
struct TaskChatMessageRecord: Codable, FetchableRecord, TableRecord, Identifiable {
  var id: Int64?

  var taskId: String  // action_items backendId
  var messageId: String  // UUID from ChatMessage.id
  var sender: String  // "user" or "ai"
  var messageText: String
  var contentBlocksJson: String?  // JSON-encoded content blocks for AI messages
  var resourcesJson: String?  // JSON-encoded attachment/artifact resources
  var embedding: Data?  // 3072 Float32s for vector search (Gemini)

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

struct TaskChatLegacyCompatibilityMetadata: Equatable {
  static let owner = "desktop-task-chat"
  static let removalCondition = "all supported desktop versions have checkpointed task chat into the kernel journal"
  static let removeBy = "2026-10-01"
  static let pageSize = 100
}

struct TaskChatLegacyMessageCursor: Equatable {
  let createdAt: Date
  let rowID: Int64
}

struct TaskChatLegacyMessagePage {
  let rows: [TaskChatMessageRecord]
  let nextCursor: TaskChatLegacyMessageCursor?
}

/// Actor-based storage for task chat messages with local-first persistence
actor TaskChatMessageStorage {
  static let shared = TaskChatMessageStorage()

  private var _dbQueue: DatabasePool?
  private var _dbGeneration = -1
  private var isInitialized = false

  private init() {}

  func invalidateCache() {
    _dbQueue = nil
    isInitialized = false
  }

  private func ensureInitialized() async throws -> DatabasePool {
    if let db = _dbQueue, await RewindDatabase.shared.poolGeneration() == _dbGeneration {
      return db
    }

    do {
      try await RewindDatabase.shared.initialize()
    } catch {
      log("TaskChatMessageStorage: Database initialization failed: \(error.localizedDescription)")
      throw error
    }

    let (queue, generation) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let db = queue else {
      throw TaskChatMessageStorageError.databaseNotInitialized
    }

    _dbQueue = db
    _dbGeneration = generation
    isInitialized = true
    return db
  }

  /// Read-only compatibility source for the one-time kernel import. Every SQL
  /// read is capped at 100 immutable rows; callers checkpoint only after they
  /// have consumed pages through the terminal short page.
  func legacyMessagePage(
    fromTaskIds taskIds: [String],
    workstreamId: String,
    after cursor: TaskChatLegacyMessageCursor? = nil
  ) async throws -> TaskChatLegacyMessagePage {
    let keys = Array(Set(taskIds + [workstreamId]))
    guard !keys.isEmpty else {
      return TaskChatLegacyMessagePage(rows: [], nextCursor: nil)
    }
    let db = try await ensureInitialized()
    return try await db.read { database in
      let placeholders = Array(repeating: "?", count: keys.count).joined(separator: ",")
      var arguments: [DatabaseValueConvertible] = keys
      let cursorClause: String
      if let cursor {
        cursorClause = "AND (createdAt > ? OR (createdAt = ? AND id > ?))"
        arguments.append(cursor.createdAt)
        arguments.append(cursor.createdAt)
        arguments.append(cursor.rowID)
      } else {
        cursorClause = ""
      }
      arguments.append(TaskChatLegacyCompatibilityMetadata.pageSize)
      let rows = try TaskChatMessageRecord.fetchAll(
        database,
        sql: """
              SELECT * FROM task_chat_messages
              WHERE taskId IN (\(placeholders))
              \(cursorClause)
              ORDER BY createdAt ASC, id ASC
              LIMIT ?
          """,
        arguments: StatementArguments(arguments)
      )
      let nextCursor = rows.last.flatMap { row -> TaskChatLegacyMessageCursor? in
        guard let rowID = row.id else { return nil }
        return TaskChatLegacyMessageCursor(createdAt: row.createdAt, rowID: rowID)
      }
      return TaskChatLegacyMessagePage(rows: rows, nextCursor: nextCursor)
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
