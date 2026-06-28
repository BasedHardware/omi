import Foundation

// MARK: - Task Source Classification

/// High-level category for where a task originated
enum TaskSourceCategory: String, Codable, CaseIterable {
    case direct_request
    case self_generated
    case calendar_driven
    case reactive
    case external_system
    case other

    var label: String {
        switch self {
        case .direct_request: return "Direct Request"
        case .self_generated: return "Self-Generated"
        case .calendar_driven: return "Calendar-Driven"
        case .reactive: return "Reactive"
        case .external_system: return "External System"
        case .other: return "Other"
        }
    }

    var icon: String {
        switch self {
        case .direct_request: return "bubble.left.fill"
        case .self_generated: return "lightbulb.fill"
        case .calendar_driven: return "calendar"
        case .reactive: return "exclamationmark.triangle.fill"
        case .external_system: return "server.rack"
        case .other: return "questionmark.circle"
        }
    }

    var validSubcategories: [TaskSourceSubcategory] {
        switch self {
        case .direct_request: return [.message, .meeting, .mention]
        case .self_generated: return [.idea, .reminder, .goal_subtask]
        case .calendar_driven: return [.event_prep, .recurring, .deadline]
        case .reactive: return [.error, .notification, .observation]
        case .external_system: return [.project_tool, .alert, .documentation]
        case .other: return [.other]
        }
    }
}

/// Subcategory for task source — flat enum, each belongs to one or more categories
enum TaskSourceSubcategory: String, Codable, CaseIterable {
    // direct_request
    case message
    case meeting
    case mention
    // self_generated
    case idea
    case reminder
    case goal_subtask
    // calendar_driven
    case event_prep
    case recurring
    case deadline
    // reactive
    case error
    case notification
    case observation
    // external_system
    case project_tool
    case alert
    case documentation
    // universal
    case other
}

/// Holds a validated category + subcategory pair
struct TaskSourceClassification: Equatable {
    let category: TaskSourceCategory
    let subcategory: TaskSourceSubcategory

    var isValid: Bool {
        category.validSubcategories.contains(subcategory) || subcategory == .other
    }

    var displayString: String {
        "\(category.label) / \(subcategory.rawValue)"
    }

    var rawString: String {
        "\(category.rawValue)/\(subcategory.rawValue)"
    }

    static func from(rawString: String) -> TaskSourceClassification? {
        let parts = rawString.split(separator: "/")
        guard parts.count == 2,
              let cat = TaskSourceCategory(rawValue: String(parts[0])),
              let sub = TaskSourceSubcategory(rawValue: String(parts[1]))
        else { return nil }
        return TaskSourceClassification(category: cat, subcategory: sub)
    }

    static func from(category: String?, subcategory: String?) -> TaskSourceClassification? {
        guard let catStr = category, let subStr = subcategory,
              let cat = TaskSourceCategory(rawValue: catStr),
              let sub = TaskSourceSubcategory(rawValue: subStr)
        else { return nil }
        return TaskSourceClassification(category: cat, subcategory: sub)
    }
}

// MARK: - Task Priority

enum TaskPriority: String, Codable {
    case high
    case medium
    case low
}

// MARK: - Extracted Task

/// Task category for classification
enum TaskClassification: String, Codable, CaseIterable {
    case personal
    case work
    case feature
    case bug
    case code
    case research
    case communication
    case finance
    case health
    case other

    /// Categories that should trigger Claude agent execution
    static let agentCategories: Set<TaskClassification> = [.feature, .bug, .code]

    /// Check if this category should trigger an agent (any category can trigger)
    var shouldTriggerAgent: Bool {
        true
    }

    /// User-friendly display label
    var label: String {
        switch self {
        case .personal: return "Personal"
        case .work: return "Work"
        case .feature: return "Feature"
        case .bug: return "Bug"
        case .code: return "Code"
        case .research: return "Research"
        case .communication: return "Communication"
        case .finance: return "Finance"
        case .health: return "Health"
        case .other: return "Other"
        }
    }

    /// Icon name for the category
    var icon: String {
        switch self {
        case .personal: return "person.fill"
        case .work: return "briefcase.fill"
        case .feature: return "sparkles"
        case .bug: return "ladybug.fill"
        case .code: return "chevron.left.forwardslash.chevron.right"
        case .research: return "magnifyingglass"
        case .communication: return "message.fill"
        case .finance: return "dollarsign.circle.fill"
        case .health: return "heart.fill"
        case .other: return "folder.fill"
        }
    }

    /// Color for the category
    var color: String {
        switch self {
        case .personal: return "#9CA3AF"
        case .work: return "#9CA3AF"
        case .feature: return "#9CA3AF"
        case .bug: return "#9CA3AF"
        case .code: return "#9CA3AF"
        case .research: return "#9CA3AF"
        case .communication: return "#9CA3AF"
        case .finance: return "#9CA3AF"
        case .health: return "#9CA3AF"
        case .other: return "#6B7280"
        }
    }
}

struct ExtractedTask: Codable {
    let title: String
    let description: String?
    let priority: TaskPriority
    let sourceApp: String
    let inferredDeadline: String?
    let confidence: Double
    let tags: [String]
    let sourceCategory: String
    let sourceSubcategory: String
    let relevanceScore: Int?

    enum CodingKeys: String, CodingKey {
        case title
        case description
        case priority
        case sourceApp = "source_app"
        case inferredDeadline = "inferred_deadline"
        case confidence
        case tags
        case sourceCategory = "source_category"
        case sourceSubcategory = "source_subcategory"
        case relevanceScore = "relevance_score"
    }

    /// Primary tag (first tag) for backward compatibility
    var primaryTag: String? {
        tags.first
    }

    /// Parsed source classification
    var sourceClassification: TaskSourceClassification? {
        TaskSourceClassification.from(category: sourceCategory, subcategory: sourceSubcategory)
    }

    /// Check if this task should trigger agent execution (any task can trigger)
    var shouldTriggerAgent: Bool {
        true
    }

    /// Convert to dictionary for Flutter
    func toDictionary() -> [String: Any] {
        var dict: [String: Any] = [
            "title": title,
            "priority": priority.rawValue,
            "sourceApp": sourceApp,
            "confidence": confidence,
            "tags": tags.map { $0 },
            "category": primaryTag ?? "other",
            "sourceCategory": sourceCategory,
            "sourceSubcategory": sourceSubcategory
        ]
        if let description = description {
            dict["description"] = description
        }
        if let deadline = inferredDeadline {
            dict["inferredDeadline"] = deadline
        }
        return dict
    }
}

// MARK: - Task Extraction Result

struct TaskExtractionResult: Codable, AssistantResult {
    let hasNewTask: Bool
    let task: ExtractedTask?
    let contextSummary: String
    let currentActivity: String

    enum CodingKeys: String, CodingKey {
        case hasNewTask = "has_new_task"
        case task
        case contextSummary = "context_summary"
        case currentActivity = "current_activity"
    }

    /// Convert to dictionary for Flutter
    func toDictionary() -> [String: Any] {
        var dict: [String: Any] = [
            "hasNewTask": hasNewTask,
            "contextSummary": contextSummary,
            "currentActivity": currentActivity
        ]
        if let task = task {
            dict["task"] = task.toDictionary()
        }
        return dict
    }
}

// MARK: - Task Extraction Context (for single-stage pipeline)

/// Context injected into the extraction prompt for deduplication
struct TaskExtractionContext {
    let activeTasks: [(id: Int64, description: String, priority: String?, relevanceScore: Int?)]
    let completedTasks: [(id: Int64, description: String)]
    let deletedTasks: [(id: Int64, description: String)]
    let goals: [Goal]
}

/// Result from vector/FTS search during tool-calling extraction
struct TaskSearchResult: Codable {
    let id: Int64
    let description: String
    let status: String          // "active", "completed", "deleted"
    let similarity: Double?     // cosine similarity (nil for FTS-only matches)
    let matchType: String       // "vector", "fts", "both"
    let relevanceScore: Int?    // relevance ranking score (higher = more important)

    enum CodingKeys: String, CodingKey {
        case id, description, status, similarity
        case matchType = "match_type"
        case relevanceScore = "relevance_score"
    }
}

// MARK: - Task Event (for Flutter communication)

struct TaskEvent {
    let eventType: TaskEventType
    let task: ExtractedTask?
    let contextSummary: String?
    let timestamp: Date

    enum TaskEventType: String {
        case taskExtracted = "taskExtracted"
        case taskUpdated = "taskUpdated"
        case taskCompleted = "taskCompleted"
        case activityChanged = "activityChanged"
    }

    init(eventType: TaskEventType, result: TaskExtractionResult) {
        self.eventType = eventType
        self.task = result.task
        self.contextSummary = result.contextSummary
        self.timestamp = Date()
    }

    /// Convert to dictionary for Flutter EventChannel
    func toDictionary() -> [String: Any] {
        var dict: [String: Any] = [
            "eventType": eventType.rawValue,
            "contextSummary": contextSummary ?? "",
            "timestamp": ISO8601DateFormatter().string(from: timestamp)
        ]
        if let task = task {
            dict["task"] = task.toDictionary()
        }
        return dict
    }
}
