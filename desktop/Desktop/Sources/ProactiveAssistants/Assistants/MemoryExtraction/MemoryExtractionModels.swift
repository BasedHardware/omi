import Foundation

// MARK: - Memory Category

enum ExtractedMemoryCategory: String, Codable {
    case system
    case interesting
}

// MARK: - Extracted Memory

struct ExtractedMemory: Codable {
    let content: String
    let category: ExtractedMemoryCategory
    let sourceApp: String
    let confidence: Double

    enum CodingKeys: String, CodingKey {
        case content
        case category
        case sourceApp = "source_app"
        case confidence
    }

    /// Convert to dictionary for Flutter
    func toDictionary() -> [String: Any] {
        return [
            "content": content,
            "category": category.rawValue,
            "sourceApp": sourceApp,
            "confidence": confidence
        ]
    }
}

// MARK: - Memory Extraction Result

struct MemoryExtractionResult: Codable, AssistantResult {
    let hasNewMemory: Bool
    let memories: [ExtractedMemory]
    let contextSummary: String
    let currentActivity: String

    enum CodingKeys: String, CodingKey {
        case hasNewMemory = "has_new_memory"
        case memories
        case contextSummary = "context_summary"
        case currentActivity = "current_activity"
    }

    /// Convert to dictionary for Flutter
    func toDictionary() -> [String: Any] {
        return [
            "hasNewMemory": hasNewMemory,
            "memories": memories.map { $0.toDictionary() },
            "contextSummary": contextSummary,
            "currentActivity": currentActivity
        ]
    }
}

// MARK: - Memory Event (for Flutter communication)

struct MemoryEvent {
    let eventType: MemoryEventType
    let memory: ExtractedMemory?
    let contextSummary: String?
    let timestamp: Date

    enum MemoryEventType: String {
        case memoryExtracted = "memoryExtracted"
        case memoryUpdated = "memoryUpdated"
        case memoryDeleted = "memoryDeleted"
    }

    init(eventType: MemoryEventType, memory: ExtractedMemory?, contextSummary: String?) {
        self.eventType = eventType
        self.memory = memory
        self.contextSummary = contextSummary
        self.timestamp = Date()
    }

    /// Convert to dictionary for Flutter EventChannel
    func toDictionary() -> [String: Any] {
        var dict: [String: Any] = [
            "eventType": eventType.rawValue,
            "contextSummary": contextSummary ?? "",
            "timestamp": ISO8601DateFormatter().string(from: timestamp)
        ]
        if let memory = memory {
            dict["memory"] = memory.toDictionary()
        }
        return dict
    }
}
