import Foundation

enum TaskIntelligenceConfidenceBand: String {
  case low
  case medium
  case high
  case explicit

  static func forCapture(confidence: Double, explicit: Bool) -> Self {
    if explicit { return .explicit }
    if confidence >= 0.85 { return .high }
    if confidence >= 0.65 { return .medium }
    return .low
  }
}

enum TaskIntelligenceResolutionCode: String {
  case accepted
  case rejected
  case expired
}

struct TaskIntelligenceAttributionEvent {
  enum EventType: String {
    case candidateCaptured = "candidate_captured"
    case candidateResolved = "candidate_resolved"
    case interventionPresented = "intervention_presented"
    case feedbackRecorded = "feedback_recorded"
    case outcomeRecorded = "outcome_recorded"
  }

  enum Surface: String {
    case suggested
    case whatMattersNow = "what_matters_now"
  }

  let eventID: String
  let eventType: EventType
  let confidenceBand: TaskIntelligenceConfidenceBand?
  let candidateID: String?
  let taskID: String?
  let resolutionCode: TaskIntelligenceResolutionCode?
  let interventionID: String?
  let surface: Surface?
  let subjectKind: String?
  let subjectID: String?
  let feedbackAction: String?
  let feedbackReason: String?
  let outcomeCode: String?
  let attributionChainID: String?
  let occurredAt: Date

  static func candidateCaptured(
    candidateID: String,
    confidenceBand: TaskIntelligenceConfidenceBand,
    eventID: String = "attr-\(UUID().uuidString.lowercased())",
    occurredAt: Date = Date()
  ) -> Self {
    Self(
      eventID: eventID,
      eventType: .candidateCaptured,
      confidenceBand: confidenceBand,
      candidateID: candidateID,
      taskID: nil,
      resolutionCode: nil,
      interventionID: nil,
      surface: nil,
      subjectKind: nil,
      subjectID: nil,
      feedbackAction: nil,
      feedbackReason: nil,
      outcomeCode: nil,
      attributionChainID: nil,
      occurredAt: occurredAt
    )
  }

  static func candidateResolved(
    candidateID: String,
    taskID: String?,
    resolutionCode: TaskIntelligenceResolutionCode,
    eventID: String = "attr-\(UUID().uuidString.lowercased())",
    occurredAt: Date = Date()
  ) -> Self? {
    guard resolutionCode != .accepted || taskID != nil else { return nil }
    return Self(
      eventID: eventID,
      eventType: .candidateResolved,
      confidenceBand: nil,
      candidateID: candidateID,
      taskID: taskID,
      resolutionCode: resolutionCode,
      interventionID: nil,
      surface: nil,
      subjectKind: nil,
      subjectID: nil,
      feedbackAction: nil,
      feedbackReason: nil,
      outcomeCode: nil,
      attributionChainID: nil,
      occurredAt: occurredAt
    )
  }

  static func interventionPresented(
    interventionID: String,
    surface: Surface,
    subjectKind: String,
    subjectID: String,
    candidateID: String? = nil,
    attributionChainID: String? = nil,
    eventID: String = "attr-\(UUID().uuidString.lowercased())",
    occurredAt: Date = Date()
  ) -> Self {
    Self(
      eventID: eventID,
      eventType: .interventionPresented,
      confidenceBand: nil,
      candidateID: candidateID,
      taskID: nil,
      resolutionCode: nil,
      interventionID: interventionID,
      surface: surface,
      subjectKind: subjectKind,
      subjectID: subjectID,
      feedbackAction: nil,
      feedbackReason: nil,
      outcomeCode: nil,
      attributionChainID: attributionChainID,
      occurredAt: occurredAt
    )
  }

  static func feedbackRecorded(
    interventionID: String?,
    surface: Surface,
    action: String,
    reason: String? = nil,
    subjectKind: String,
    subjectID: String,
    candidateID: String? = nil,
    attributionChainID: String? = nil,
    eventID: String = "attr-\(UUID().uuidString.lowercased())",
    occurredAt: Date = Date()
  ) -> Self {
    Self(
      eventID: eventID,
      eventType: .feedbackRecorded,
      confidenceBand: nil,
      candidateID: candidateID,
      taskID: nil,
      resolutionCode: nil,
      interventionID: interventionID,
      surface: surface,
      subjectKind: subjectKind,
      subjectID: subjectID,
      feedbackAction: action,
      feedbackReason: reason,
      outcomeCode: nil,
      attributionChainID: attributionChainID,
      occurredAt: occurredAt
    )
  }

  static func outcomeRecorded(
    interventionID: String?,
    surface: Surface,
    outcomeCode: String,
    subjectKind: String,
    subjectID: String,
    candidateID: String? = nil,
    attributionChainID: String,
    eventID: String = "attr-\(UUID().uuidString.lowercased())",
    occurredAt: Date = Date()
  ) -> Self {
    Self(
      eventID: eventID,
      eventType: .outcomeRecorded,
      confidenceBand: nil,
      candidateID: candidateID,
      taskID: nil,
      resolutionCode: nil,
      interventionID: interventionID,
      surface: surface,
      subjectKind: subjectKind,
      subjectID: subjectID,
      feedbackAction: nil,
      feedbackReason: nil,
      outcomeCode: outcomeCode,
      attributionChainID: attributionChainID,
      occurredAt: occurredAt
    )
  }

  var analyticsProperties: [String: Any] {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    var properties: [String: Any] = [
      "schema_version": 1,
      "event_id": eventID,
      "event_type": eventType.rawValue,
      "source_class": "screen",
      "occurred_at": formatter.string(from: occurredAt),
    ]
    if let confidenceBand { properties["confidence_band"] = confidenceBand.rawValue }
    if let candidateID { properties["candidate_id"] = candidateID }
    if let taskID { properties["task_id"] = taskID }
    if let resolutionCode { properties["resolution_code"] = resolutionCode.rawValue }
    if let interventionID { properties["intervention_id"] = interventionID }
    if let surface { properties["surface"] = surface.rawValue }
    if let subjectKind { properties["subject_kind"] = subjectKind }
    if let subjectID { properties["subject_id"] = subjectID }
    if let feedbackAction { properties["feedback_action"] = feedbackAction }
    if let feedbackReason { properties["feedback_reason"] = feedbackReason }
    if let outcomeCode { properties["outcome_code"] = outcomeCode }
    if let attributionChainID { properties["attribution_chain_id"] = attributionChainID }
    return properties
  }
}

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
    case .direct_request: return [.message, .meeting, .mention, .commitment]
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
  case commitment
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
  let captureKind: String?
  let owner: String?
  let concreteDeliverable: Bool?
  let publicBroadcast: Bool?
  let directMention: Bool?
  let alreadyDone: Bool?
  let duplicateOf: String?
  let refinesTask: String?
  let ownershipConfidence: Double?

  /// Compatibility-only. Screen extraction no longer assigns global ordering.
  var relevanceScore: Int? { nil }

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
    case captureKind = "capture_kind"
    case owner
    case concreteDeliverable = "concrete_deliverable"
    case publicBroadcast = "public_broadcast"
    case directMention = "direct_mention"
    case alreadyDone = "already_done"
    case duplicateOf = "duplicate_of"
    case refinesTask = "refines_task"
    case ownershipConfidence = "ownership_confidence"
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
      "sourceSubcategory": sourceSubcategory,
      "captureKind": captureKind ?? "direct_request",
      "owner": owner ?? "unknown",
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
      "currentActivity": currentActivity,
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
  /// Descriptions of tasks already staged locally (not yet promoted to the
  /// backend). Presented as "already captured — do not re-extract" evidence
  /// WITHOUT an updatable id: staged tasks have no backend id, so exposing them
  /// in the id'd active list (previously all as `id:0`) let the model emit
  /// `duplicate_of:0` and drive an update against a non-existent task.
  let stagedTaskDescriptions: [String]
  let goals: [Goal]
}

/// Result from vector/FTS search during tool-calling extraction
struct TaskSearchResult: Codable {
  let id: Int64
  let description: String
  let status: String  // "active", "completed", "deleted"
  let similarity: Double?  // cosine similarity (nil for FTS-only matches)
  let matchType: String  // "vector", "fts", "both"
  let relevanceScore: Int?  // relevance ranking score (higher = more important)

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
      "timestamp": ISO8601DateFormatter().string(from: timestamp),
    ]
    if let task = task {
      dict["task"] = task.toDictionary()
    }
    return dict
  }
}
