import Foundation
import GRDB

// MARK: - Extraction Type

/// Types of proactive extractions
enum ExtractionType: String, Codable, CaseIterable {
    case memory
    case task
    case advice
}

// MARK: - Proactive Extraction Record

/// Database record for memories, tasks, and advice extracted from screenshots
struct ProactiveExtractionRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var screenshotId: Int64?
    var type: ExtractionType
    var content: String
    var category: String?
    var confidence: Double?
    var reasoning: String?
    var sourceApp: String
    var contextSummary: String?
    var priority: String?
    var isRead: Bool
    var isDismissed: Bool
    var backendId: String?
    var backendSynced: Bool
    var createdAt: Date
    var updatedAt: Date

    static let databaseTableName = "proactive_extractions"

    // MARK: - Initialization

    init(
        id: Int64? = nil,
        screenshotId: Int64? = nil,
        type: ExtractionType,
        content: String,
        category: String? = nil,
        confidence: Double? = nil,
        reasoning: String? = nil,
        sourceApp: String,
        contextSummary: String? = nil,
        priority: String? = nil,
        isRead: Bool = false,
        isDismissed: Bool = false,
        backendId: String? = nil,
        backendSynced: Bool = false,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.screenshotId = screenshotId
        self.type = type
        self.content = content
        self.category = category
        self.confidence = confidence
        self.reasoning = reasoning
        self.sourceApp = sourceApp
        self.contextSummary = contextSummary
        self.priority = priority
        self.isRead = isRead
        self.isDismissed = isDismissed
        self.backendId = backendId
        self.backendSynced = backendSynced
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    // MARK: - Persistence Callbacks

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }

    // MARK: - Relationships

    static let screenshot = belongsTo(Screenshot.self)

    var screenshot: QueryInterfaceRequest<Screenshot> {
        request(for: ProactiveExtractionRecord.screenshot)
    }
}

// MARK: - Focus Session Record

/// Database record for focus tracking sessions
struct FocusSessionRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var screenshotId: Int64?
    var status: String // "focused" or "distracted"
    var appOrSite: String
    var windowTitle: String?
    var description: String
    var message: String?
    var durationSeconds: Int?
    var backendId: String?
    var backendSynced: Bool
    var createdAt: Date

    static let databaseTableName = "focus_sessions"

    // MARK: - Initialization

    init(
        id: Int64? = nil,
        screenshotId: Int64? = nil,
        status: String,
        appOrSite: String,
        windowTitle: String? = nil,
        description: String,
        message: String? = nil,
        durationSeconds: Int? = nil,
        backendId: String? = nil,
        backendSynced: Bool = false,
        createdAt: Date = Date()
    ) {
        self.id = id
        self.screenshotId = screenshotId
        self.status = status
        self.appOrSite = appOrSite
        self.windowTitle = windowTitle
        self.description = description
        self.message = message
        self.durationSeconds = durationSeconds
        self.backendId = backendId
        self.backendSynced = backendSynced
        self.createdAt = createdAt
    }

    // MARK: - Persistence Callbacks

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }

    // MARK: - Computed Properties

    var isFocused: Bool {
        status == "focused"
    }

    var isDistracted: Bool {
        status == "distracted"
    }

    // MARK: - Relationships

    static let screenshot = belongsTo(Screenshot.self)

    var screenshot: QueryInterfaceRequest<Screenshot> {
        request(for: FocusSessionRecord.screenshot)
    }
}

// MARK: - Task Dedup Log Record

/// Database record for AI-driven task deduplication deletions
struct TaskDedupLogRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var deletedTaskId: String
    var deletedDescription: String
    var keptTaskId: String
    var keptDescription: String
    var reason: String
    var deletedAt: Date

    static let databaseTableName = "task_dedup_log"

    init(
        id: Int64? = nil,
        deletedTaskId: String,
        deletedDescription: String,
        keptTaskId: String,
        keptDescription: String,
        reason: String,
        deletedAt: Date = Date()
    ) {
        self.id = id
        self.deletedTaskId = deletedTaskId
        self.deletedDescription = deletedDescription
        self.keptTaskId = keptTaskId
        self.keptDescription = keptDescription
        self.reason = reason
        self.deletedAt = deletedAt
    }

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}

// MARK: - Screenshot Extensions for Relationships

extension Screenshot {
    static let extractions = hasMany(ProactiveExtractionRecord.self)
    static let focusSessions = hasMany(FocusSessionRecord.self)

    var extractions: QueryInterfaceRequest<ProactiveExtractionRecord> {
        request(for: Screenshot.extractions)
    }

    var focusSessions: QueryInterfaceRequest<FocusSessionRecord> {
        request(for: Screenshot.focusSessions)
    }
}

// MARK: - Extraction with Screenshot

/// Combined extraction and screenshot data for UI display
struct ExtractionWithScreenshot {
    let extraction: ProactiveExtractionRecord
    let screenshot: Screenshot?

    var imagePath: String? {
        screenshot?.imagePath
    }

    var screenshotTimestamp: Date? {
        screenshot?.timestamp
    }
}

// MARK: - Focus Session with Screenshot

/// Combined focus session and screenshot data for UI display
struct FocusSessionWithScreenshot {
    let session: FocusSessionRecord
    let screenshot: Screenshot?

    var imagePath: String? {
        screenshot?.imagePath
    }

    var screenshotTimestamp: Date? {
        screenshot?.timestamp
    }
}
