import Foundation

// MARK: - Task Priority

enum TaskPriority: String, Codable {
    case high
    case medium
    case low
}

// MARK: - Extracted Task

struct ExtractedTask: Codable {
    let title: String
    let description: String?
    let priority: TaskPriority
    let sourceApp: String
    let inferredDeadline: String?
    let confidence: Double

    enum CodingKeys: String, CodingKey {
        case title
        case description
        case priority
        case sourceApp = "source_app"
        case inferredDeadline = "inferred_deadline"
        case confidence
    }

    /// Convert to dictionary for Flutter
    func toDictionary() -> [String: Any] {
        var dict: [String: Any] = [
            "title": title,
            "priority": priority.rawValue,
            "sourceApp": sourceApp,
            "confidence": confidence
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
