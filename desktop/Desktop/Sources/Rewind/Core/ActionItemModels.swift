import Foundation
import GRDB

// MARK: - Action Item Record

/// Database record for action items/tasks with bidirectional sync support
/// Stores tasks from both local extraction (screenshots) and backend API
struct ActionItemRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?

    // Backend sync fields
    var backendId: String?              // Server action item ID
    var backendSynced: Bool

    // Core ActionItem fields
    var description: String
    var completed: Bool
    var deleted: Bool
    var source: String?                 // screenshot, conversation, omi
    var conversationId: String?
    var priority: String?               // high, medium, low
    var category: String?
    var tagsJson: String?               // JSON array: ["work", "code"]
    var deletedBy: String?              // "user", "ai_dedup"
    var dueAt: Date?
    var recurrenceRule: String?          // "daily", "weekdays", "weekly", "biweekly", "monthly"
    var recurrenceParentId: String?      // ID of original parent task in recurrence chain

    // Desktop extraction fields
    var screenshotId: Int64?
    var confidence: Double?
    var sourceApp: String?
    var windowTitle: String?
    var contextSummary: String?
    var currentActivity: String?
    var metadataJson: String?           // Additional extraction metadata
    var embedding: Data?                // 3072 Float32s for vector search (Gemini embedding-001)

    // Ordering (synced to backend)
    var sortOrder: Int?                  // Sort position within category
    var indentLevel: Int?                // 0-3 indent depth

    // Prioritization
    var relevanceScore: Int?             // 0-100 score from TaskPrioritizationService
    var scoredAt: Date?                  // When the score was last computed

    // Agent session persistence (local-only, not synced to backend)
    var agentStatus: String?             // "pending", "processing", "editing", "completed", "failed"
    var agentSessionName: String?        // tmux session name
    var agentPrompt: String?             // Prompt sent to Claude
    var agentPlan: String?               // Claude's response/plan
    var agentStartedAt: Date?            // When agent was launched
    var agentCompletedAt: Date?          // When agent finished
    var agentEditedFilesJson: String?    // JSON array of edited file paths

    // Chat session (local-only, not synced to backend)
    var chatSessionId: String?           // Firestore chat session ID for task-scoped chat

    // Promotion tracking
    var fromStaged: Bool                 // Whether this task was promoted from staged_tasks

    // Timestamps
    var createdAt: Date
    var updatedAt: Date

    static let databaseTableName = "action_items"

    // MARK: - Initialization

    init(
        id: Int64? = nil,
        backendId: String? = nil,
        backendSynced: Bool = false,
        description: String,
        completed: Bool = false,
        deleted: Bool = false,
        source: String? = nil,
        conversationId: String? = nil,
        priority: String? = nil,
        category: String? = nil,
        tagsJson: String? = nil,
        deletedBy: String? = nil,
        dueAt: Date? = nil,
        recurrenceRule: String? = nil,
        recurrenceParentId: String? = nil,
        screenshotId: Int64? = nil,
        confidence: Double? = nil,
        sourceApp: String? = nil,
        windowTitle: String? = nil,
        contextSummary: String? = nil,
        currentActivity: String? = nil,
        metadataJson: String? = nil,
        embedding: Data? = nil,
        sortOrder: Int? = nil,
        indentLevel: Int? = nil,
        relevanceScore: Int? = nil,
        scoredAt: Date? = nil,
        agentStatus: String? = nil,
        agentSessionName: String? = nil,
        agentPrompt: String? = nil,
        agentPlan: String? = nil,
        agentStartedAt: Date? = nil,
        agentCompletedAt: Date? = nil,
        agentEditedFilesJson: String? = nil,
        chatSessionId: String? = nil,
        fromStaged: Bool = false,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.backendId = backendId
        self.backendSynced = backendSynced
        self.description = description
        self.completed = completed
        self.deleted = deleted
        self.source = source
        self.conversationId = conversationId
        self.priority = priority
        self.category = category
        self.tagsJson = tagsJson
        self.deletedBy = deletedBy
        self.dueAt = dueAt
        self.recurrenceRule = recurrenceRule
        self.recurrenceParentId = recurrenceParentId
        self.screenshotId = screenshotId
        self.confidence = confidence
        self.sourceApp = sourceApp
        self.windowTitle = windowTitle
        self.contextSummary = contextSummary
        self.currentActivity = currentActivity
        self.metadataJson = metadataJson
        self.embedding = embedding
        self.sortOrder = sortOrder
        self.indentLevel = indentLevel
        self.relevanceScore = relevanceScore
        self.scoredAt = scoredAt
        self.agentStatus = agentStatus
        self.agentSessionName = agentSessionName
        self.agentPrompt = agentPrompt
        self.agentPlan = agentPlan
        self.agentStartedAt = agentStartedAt
        self.agentCompletedAt = agentCompletedAt
        self.agentEditedFilesJson = agentEditedFilesJson
        self.chatSessionId = chatSessionId
        self.fromStaged = fromStaged
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    // MARK: - Persistence Callbacks

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }

    // MARK: - Metadata Helpers

    /// Get metadata as dictionary
    var metadata: [String: Any]? {
        guard let json = metadataJson,
              let data = json.data(using: .utf8),
              let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return dict
    }

    /// Set metadata from dictionary
    mutating func setMetadata(_ metadata: [String: Any]?) {
        guard let metadata = metadata,
              let data = try? JSONSerialization.data(withJSONObject: metadata),
              let json = String(data: data, encoding: .utf8)
        else {
            metadataJson = nil
            return
        }
        metadataJson = json
    }

    // MARK: - Source Classification

    /// Parsed source classification from metadata
    var sourceClassification: TaskSourceClassification? {
        guard let meta = metadata,
              let cat = meta["source_category"] as? String,
              let sub = meta["source_subcategory"] as? String
        else { return nil }
        return TaskSourceClassification.from(category: cat, subcategory: sub)
    }

    // MARK: - Tag Helpers

    /// Get tags as array (decoded from JSON)
    var tags: [String] {
        guard let json = tagsJson,
              let data = json.data(using: .utf8),
              let array = try? JSONDecoder().decode([String].self, from: data)
        else { return [] }
        return array
    }

    /// Set tags from array
    mutating func setTags(_ tags: [String]) {
        if tags.isEmpty {
            tagsJson = nil
        } else if let data = try? JSONEncoder().encode(tags),
                  let json = String(data: data, encoding: .utf8) {
            tagsJson = json
        }
    }

    /// Check if record has a specific tag
    func hasTag(_ tag: String) -> Bool {
        tags.contains(tag)
    }

    // MARK: - Agent Edited Files Helpers

    /// Get edited files as array (decoded from JSON)
    var agentEditedFiles: [String] {
        guard let json = agentEditedFilesJson,
              let data = json.data(using: .utf8),
              let array = try? JSONDecoder().decode([String].self, from: data)
        else { return [] }
        return array
    }

    /// Set edited files from array
    mutating func setAgentEditedFiles(_ files: [String]) {
        if files.isEmpty {
            agentEditedFilesJson = nil
        } else if let data = try? JSONEncoder().encode(files),
                  let json = String(data: data, encoding: .utf8) {
            agentEditedFilesJson = json
        }
    }

    // MARK: - Relationships

    static let screenshot = belongsTo(Screenshot.self)

    var screenshot: QueryInterfaceRequest<Screenshot> {
        request(for: ActionItemRecord.screenshot)
    }
}

// MARK: - ActionItem Conversion

extension ActionItemRecord {
    /// Create a local record from an ActionItem (for caching API responses)
    static func from(_ item: ActionItem, conversationId: String? = nil) -> ActionItemRecord {
        return ActionItemRecord(
            backendId: item.id,
            backendSynced: true,
            description: item.description,
            completed: item.completed,
            deleted: item.deleted,
            source: nil,  // Not available from ActionItem
            conversationId: conversationId,
            priority: nil,  // Not in current ActionItem struct
            category: nil,  // Not in current ActionItem struct
            dueAt: nil,  // Not in current ActionItem struct
            screenshotId: nil,
            confidence: nil,
            sourceApp: nil,
            contextSummary: nil,
            currentActivity: nil,
            metadataJson: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
    }

    /// Create a local record from a TaskActionItem (for caching API responses with full data)
    static func from(_ item: TaskActionItem) -> ActionItemRecord {
        // Build tagsJson from item.tags
        let tagsJson: String?
        let itemTags = item.tags
        if !itemTags.isEmpty,
           let data = try? JSONEncoder().encode(itemTags),
           let json = String(data: data, encoding: .utf8) {
            tagsJson = json
        } else {
            tagsJson = nil
        }

        return ActionItemRecord(
            backendId: item.id,
            backendSynced: true,
            description: item.description,
            completed: item.completed,
            deleted: item.deleted ?? false,
            source: item.source,
            conversationId: item.conversationId,
            priority: item.priority,
            category: item.category,
            tagsJson: tagsJson,
            deletedBy: item.deletedBy,
            dueAt: item.dueAt,
            recurrenceRule: item.recurrenceRule,
            recurrenceParentId: item.recurrenceParentId,
            screenshotId: nil,
            confidence: nil,
            sourceApp: item.sourceApp,
            windowTitle: item.windowTitle,
            contextSummary: nil,
            currentActivity: nil,
            metadataJson: item.metadata,
            sortOrder: item.sortOrder,
            indentLevel: item.indentLevel,
            relevanceScore: item.relevanceScore,
            fromStaged: item.fromStaged ?? false,
            createdAt: item.createdAt,
            updatedAt: item.updatedAt ?? item.createdAt
        )
    }

    /// Update this record from an ActionItem (preserving local id and screenshotId)
    mutating func updateFrom(_ item: ActionItem) {
        self.backendId = item.id
        self.backendSynced = true
        self.description = item.description
        self.completed = item.completed
        self.deleted = item.deleted
        self.updatedAt = Date()
    }

    /// Update this record from a TaskActionItem (preserving local id and screenshotId)
    /// Note: Agent fields (agentStatus, agentSessionName, etc.) are NOT overwritten here.
    /// They are local-only state managed by TaskAgentManager and persisted separately.
    mutating func updateFrom(_ item: TaskActionItem) {
        self.backendId = item.id
        self.backendSynced = true
        self.description = item.description
        self.completed = item.completed
        self.deleted = item.deleted ?? false
        self.deletedBy = item.deletedBy
        self.source = item.source
        self.conversationId = item.conversationId
        self.priority = item.priority
        self.category = item.category
        self.dueAt = item.dueAt
        self.recurrenceRule = item.recurrenceRule
        self.recurrenceParentId = item.recurrenceParentId
        self.metadataJson = item.metadata
        if let staged = item.fromStaged {
            self.fromStaged = staged
        }

        // Only update updatedAt if the incoming timestamp is newer than local
        // This prevents sync from resetting local timestamps when backend data hasn't changed
        let incomingTimestamp = item.updatedAt ?? item.createdAt
        if incomingTimestamp > self.updatedAt {
            self.updatedAt = incomingTimestamp
        }

        // Sync tags from TaskActionItem
        let itemTags = item.tags
        if !itemTags.isEmpty,
           let data = try? JSONEncoder().encode(itemTags),
           let json = String(data: data, encoding: .utf8) {
            self.tagsJson = json
        }

        // Adopt API score when local record has none (avoids overwriting recent Gemini re-ranking)
        if self.relevanceScore == nil, let apiScore = item.relevanceScore {
            self.relevanceScore = apiScore
        }

        // Sync sort order and indent level from backend
        if let apiSortOrder = item.sortOrder {
            self.sortOrder = apiSortOrder
        }
        if let apiIndentLevel = item.indentLevel {
            self.indentLevel = apiIndentLevel
        }
    }

    /// Convert to ActionItem for UI display (simplified)
    func toActionItem() -> ActionItem {
        return ActionItem(
            description: description,
            completed: completed,
            deleted: deleted
        )
    }

    /// Convert to TaskActionItem for UI display (full data)
    /// Uses backendId if available, otherwise generates a local ID
    func toTaskActionItem() -> TaskActionItem {
        // Use backendId if available, otherwise use local ID prefixed with "local_"
        let taskId = backendId ?? "local_\(id ?? 0)"

        // Ensure metadata contains tags and window_title for TaskActionItem computed properties
        var finalMetadata = metadataJson
        let recordTags = tags
        let needsTagsUpdate = !recordTags.isEmpty
        let needsWindowTitleUpdate = windowTitle != nil

        if needsTagsUpdate || needsWindowTitleUpdate {
            var metaDict = metadata ?? [:]
            if needsTagsUpdate {
                metaDict["tags"] = recordTags
            }
            if let wt = windowTitle {
                metaDict["window_title"] = wt
            }
            if let data = try? JSONSerialization.data(withJSONObject: metaDict),
               let json = String(data: data, encoding: .utf8) {
                finalMetadata = json
            }
        }

        return TaskActionItem(
            id: taskId,
            description: description,
            completed: completed,
            createdAt: createdAt,
            updatedAt: updatedAt,
            dueAt: dueAt,
            completedAt: nil,  // Not stored locally
            conversationId: conversationId,
            source: source,
            priority: priority,
            metadata: finalMetadata,
            category: category,
            deleted: deleted,
            deletedBy: deletedBy,
            deletedAt: nil,  // Not stored locally
            deletedReason: nil,  // Not stored locally
            keptTaskId: nil,  // Not stored locally
            fromStaged: fromStaged,
            recurrenceRule: recurrenceRule,
            recurrenceParentId: recurrenceParentId,
            sortOrder: sortOrder,
            indentLevel: indentLevel,
            relevanceScore: relevanceScore,
            contextSummary: contextSummary,
            currentActivity: currentActivity,
            agentEditedFiles: agentEditedFiles.isEmpty ? nil : agentEditedFiles,
            agentStatus: agentStatus,
            agentPrompt: agentPrompt,
            agentPlan: agentPlan,
            agentSessionId: agentSessionName,
            agentStartedAt: agentStartedAt,
            agentCompletedAt: agentCompletedAt,
            chatSessionId: chatSessionId
        )
    }
}

// MARK: - Staged Task Record

/// Database record for staged tasks awaiting promotion to action_items.
/// Same schema as ActionItemRecord but without agent fields, stored in "staged_tasks" table.
struct StagedTaskRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?

    // Backend sync fields
    var backendId: String?
    var backendSynced: Bool

    // Core fields
    var description: String
    var completed: Bool
    var deleted: Bool
    var source: String?
    var conversationId: String?
    var priority: String?
    var category: String?
    var tagsJson: String?
    var deletedBy: String?
    var dueAt: Date?

    // Desktop extraction fields
    var screenshotId: Int64?
    var confidence: Double?
    var sourceApp: String?
    var windowTitle: String?
    var contextSummary: String?
    var currentActivity: String?
    var metadataJson: String?
    var embedding: Data?

    // Prioritization
    var relevanceScore: Int?
    var scoredAt: Date?

    // Timestamps
    var createdAt: Date
    var updatedAt: Date

    static let databaseTableName = "staged_tasks"

    init(
        id: Int64? = nil,
        backendId: String? = nil,
        backendSynced: Bool = false,
        description: String,
        completed: Bool = false,
        deleted: Bool = false,
        source: String? = nil,
        conversationId: String? = nil,
        priority: String? = nil,
        category: String? = nil,
        tagsJson: String? = nil,
        deletedBy: String? = nil,
        dueAt: Date? = nil,
        screenshotId: Int64? = nil,
        confidence: Double? = nil,
        sourceApp: String? = nil,
        windowTitle: String? = nil,
        contextSummary: String? = nil,
        currentActivity: String? = nil,
        metadataJson: String? = nil,
        embedding: Data? = nil,
        relevanceScore: Int? = nil,
        scoredAt: Date? = nil,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.backendId = backendId
        self.backendSynced = backendSynced
        self.description = description
        self.completed = completed
        self.deleted = deleted
        self.source = source
        self.conversationId = conversationId
        self.priority = priority
        self.category = category
        self.tagsJson = tagsJson
        self.deletedBy = deletedBy
        self.dueAt = dueAt
        self.screenshotId = screenshotId
        self.confidence = confidence
        self.sourceApp = sourceApp
        self.windowTitle = windowTitle
        self.contextSummary = contextSummary
        self.currentActivity = currentActivity
        self.metadataJson = metadataJson
        self.embedding = embedding
        self.relevanceScore = relevanceScore
        self.scoredAt = scoredAt
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }

    // MARK: - Metadata Helpers

    var metadata: [String: Any]? {
        guard let json = metadataJson,
              let data = json.data(using: .utf8),
              let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return dict
    }

    mutating func setMetadata(_ metadata: [String: Any]?) {
        guard let metadata = metadata,
              let data = try? JSONSerialization.data(withJSONObject: metadata),
              let json = String(data: data, encoding: .utf8)
        else {
            metadataJson = nil
            return
        }
        metadataJson = json
    }

    // MARK: - Tag Helpers

    var tags: [String] {
        guard let json = tagsJson,
              let data = json.data(using: .utf8),
              let array = try? JSONDecoder().decode([String].self, from: data)
        else { return [] }
        return array
    }

    mutating func setTags(_ tags: [String]) {
        if tags.isEmpty {
            tagsJson = nil
        } else if let data = try? JSONEncoder().encode(tags),
                  let json = String(data: data, encoding: .utf8) {
            tagsJson = json
        }
    }

    // MARK: - Conversions

    /// Convert to TaskActionItem for UI/API use
    func toTaskActionItem() -> TaskActionItem {
        let taskId = backendId ?? "staged_\(id ?? 0)"

        var finalMetadata = metadataJson
        let recordTags = tags
        if !recordTags.isEmpty || windowTitle != nil {
            var metaDict = self.metadata ?? [:]
            if !recordTags.isEmpty { metaDict["tags"] = recordTags }
            if let wt = windowTitle { metaDict["window_title"] = wt }
            if let data = try? JSONSerialization.data(withJSONObject: metaDict),
               let json = String(data: data, encoding: .utf8) {
                finalMetadata = json
            }
        }

        return TaskActionItem(
            id: taskId,
            description: description,
            completed: completed,
            createdAt: createdAt,
            updatedAt: updatedAt,
            dueAt: dueAt,
            completedAt: nil,
            conversationId: conversationId,
            source: source,
            priority: priority,
            metadata: finalMetadata,
            category: category,
            deleted: deleted,
            deletedBy: deletedBy,
            deletedAt: nil,
            deletedReason: nil,
            keptTaskId: nil,
            sortOrder: nil,
            indentLevel: nil,
            relevanceScore: relevanceScore,
            contextSummary: contextSummary,
            currentActivity: currentActivity,
            agentEditedFiles: nil,
            agentStatus: nil,
            agentPrompt: nil,
            agentPlan: nil,
            agentSessionId: nil,
            agentStartedAt: nil,
            agentCompletedAt: nil,
            chatSessionId: nil
        )
    }

    /// Create from ActionItemRecord (for migration)
    static func from(_ record: ActionItemRecord) -> StagedTaskRecord {
        return StagedTaskRecord(
            backendId: nil,  // Will get new backendId when synced to staged_tasks
            backendSynced: false,
            description: record.description,
            completed: record.completed,
            deleted: record.deleted,
            source: record.source,
            conversationId: record.conversationId,
            priority: record.priority,
            category: record.category,
            tagsJson: record.tagsJson,
            deletedBy: record.deletedBy,
            dueAt: record.dueAt,
            screenshotId: record.screenshotId,
            confidence: record.confidence,
            sourceApp: record.sourceApp,
            windowTitle: record.windowTitle,
            contextSummary: record.contextSummary,
            currentActivity: record.currentActivity,
            metadataJson: record.metadataJson,
            embedding: record.embedding,
            relevanceScore: record.relevanceScore,
            scoredAt: record.scoredAt,
            createdAt: record.createdAt,
            updatedAt: record.updatedAt
        )
    }

    /// Create from a TaskActionItem (for caching API responses)
    static func from(_ item: TaskActionItem) -> StagedTaskRecord {
        let tagsJson: String?
        let itemTags = item.tags
        if !itemTags.isEmpty,
           let data = try? JSONEncoder().encode(itemTags),
           let json = String(data: data, encoding: .utf8) {
            tagsJson = json
        } else {
            tagsJson = nil
        }

        return StagedTaskRecord(
            backendId: item.id,
            backendSynced: true,
            description: item.description,
            completed: item.completed,
            deleted: item.deleted ?? false,
            source: item.source,
            conversationId: item.conversationId,
            priority: item.priority,
            category: item.category,
            tagsJson: tagsJson,
            deletedBy: item.deletedBy,
            dueAt: item.dueAt,
            screenshotId: nil,
            confidence: nil,
            sourceApp: item.sourceApp,
            windowTitle: item.windowTitle,
            contextSummary: nil,
            currentActivity: nil,
            metadataJson: item.metadata,
            relevanceScore: item.relevanceScore,
            createdAt: item.createdAt,
            updatedAt: item.updatedAt ?? item.createdAt
        )
    }
}

// MARK: - Action Item Storage Error

enum ActionItemStorageError: LocalizedError {
    case databaseNotInitialized
    case recordNotFound
    case syncFailed(String)

    var errorDescription: String? {
        switch self {
        case .databaseNotInitialized:
            return "Action item storage database is not initialized"
        case .recordNotFound:
            return "Action item record not found"
        case .syncFailed(let message):
            return "Sync failed: \(message)"
        }
    }
}
