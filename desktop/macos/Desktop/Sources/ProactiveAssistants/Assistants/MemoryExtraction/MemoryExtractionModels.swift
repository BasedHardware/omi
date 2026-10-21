import Foundation

// MARK: - Memory Category

enum ExtractedMemoryCategory: String, Codable, Sendable {
  case system
  case interesting
}

// MARK: - Extracted Memory

struct ExtractedMemory: Codable, Sendable {
  let content: String
  let category: ExtractedMemoryCategory
  let sourceApp: String
  let confidence: Double
  let subjectScope: MemorySubjectScope?
  let subjectEvidence: MemorySubjectEvidence?
  let containsCredentialOrIdentifier: Bool?

  enum CodingKeys: String, CodingKey {
    case content
    case category
    case sourceApp = "source_app"
    case confidence
    case subjectScope = "subject_scope"
    case subjectEvidence = "subject_evidence"
    case containsCredentialOrIdentifier = "contains_credential_or_identifier"
  }

  init(
    content: String,
    category: ExtractedMemoryCategory,
    sourceApp: String,
    confidence: Double,
    subjectScope: MemorySubjectScope? = nil,
    subjectEvidence: MemorySubjectEvidence? = nil,
    containsCredentialOrIdentifier: Bool? = nil
  ) {
    self.content = content
    self.category = category
    self.sourceApp = sourceApp
    self.confidence = confidence
    self.subjectScope = subjectScope
    self.subjectEvidence = subjectEvidence
    self.containsCredentialOrIdentifier = containsCredentialOrIdentifier
  }

  /// Convert to dictionary for Flutter
  func toDictionary() -> [String: Any] {
    var payload: [String: Any] = [
      "content": content,
      "category": category.rawValue,
      "sourceApp": sourceApp,
      "confidence": confidence,
    ]
    if let subjectScope { payload["subjectScope"] = subjectScope.rawValue }
    if let subjectEvidence { payload["subjectEvidence"] = subjectEvidence.rawValue }
    if let containsCredentialOrIdentifier {
      payload["containsCredentialOrIdentifier"] = containsCredentialOrIdentifier
    }
    return payload
  }
}

// MARK: - Memory Extraction Result

struct MemoryExtractionResult: Codable, AssistantResult, Sendable {
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
      "currentActivity": currentActivity,
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
      "timestamp": ISO8601DateFormatter().string(from: timestamp),
    ]
    if let memory = memory {
      dict["memory"] = memory.toDictionary()
    }
    return dict
  }
}
