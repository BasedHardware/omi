import Foundation

// MARK: - Action Item Model (Standalone)

/// Standalone action item stored in Firestore subcollection
/// Different from ActionItem which is embedded in conversation structured data
struct TaskActionItem: Codable, Identifiable, Equatable {
  let id: String
  let description: String
  let completed: Bool
  let createdAt: Date
  let updatedAt: Date?
  let dueAt: Date?
  let completedAt: Date?
  let conversationId: String?
  /// Source of the task: "screenshot", "transcription:omi", "transcription:desktop", "manual"
  let source: String?
  /// Priority: "high", "medium", "low"
  let priority: String?
  /// JSON metadata string containing extra info like source_app, confidence
  let metadata: String?
  /// Classification category: personal, work, feature, bug, code, research, communication, finance, health, other
  let category: String?
  /// Soft-delete: true if this task has been deleted by AI dedup
  let deleted: Bool?
  /// Who deleted: "user", "ai_dedup"
  let deletedBy: String?
  /// When the task was soft-deleted
  let deletedAt: Date?
  /// AI reason for deletion (dedup explanation)
  let deletedReason: String?
  /// ID of the task that was kept instead of this one
  let keptTaskId: String?
  /// ID of the goal this task is linked to
  let goalId: String?
  /// Whether this task was promoted from staged_tasks
  let fromStaged: Bool?
  /// Recurrence rule: "daily", "weekdays", "weekly", "biweekly", "monthly"
  let recurrenceRule: String?
  /// ID of original parent task in recurrence chain
  let recurrenceParentId: String?
  /// Canonical compatibility task identifier, when distinct from `id`.
  let taskId: String?
  /// Canonical lifecycle status: active, completed, cancelled, superseded.
  let taskStatus: String?
  /// Canonical ownership classification: user, other, unknown.
  let taskOwner: String?
  let workstreamId: String?
  let dueConfidence: Double?
  let provenance: [OmiAPI.EvidenceRef]?
  let supersededBy: String?

  // Ordering (synced to backend)
  var sortOrder: Int?  // Sort position within category
  var indentLevel: Int?  // 0-3 indent depth

  // Prioritization (stored locally, not synced to backend)
  var relevanceScore: Int?  // 0-100 relevance score from TaskPrioritizationService

  // Desktop extraction context (stored locally, not synced to backend)
  var contextSummary: String?  // Summary of screen context at extraction time
  var currentActivity: String?  // What user was doing when task was detected
  var agentEditedFiles: [String]?  // Files the agent previously edited

  // Agent execution tracking (stored locally, not synced to backend)
  var agentStatus: String?  // nil, "pending", "processing", "completed", "failed"
  var agentPrompt: String?  // The prompt sent to Claude
  var agentPlan: String?  // Claude's response/plan
  var agentSessionId: String?  // tmux session name for the Claude session
  var agentStartedAt: Date?  // When agent was launched
  var agentCompletedAt: Date?  // When agent finished

  // Chat session for task-scoped AI chat (stored locally, not synced to backend)
  var chatSessionId: String?

  /// Whether this task has an active recurrence rule
  var isRecurring: Bool {
    guard let rule = recurrenceRule, !rule.isEmpty else { return false }
    return true
  }

  /// Custom Equatable: compares only display-relevant fields.
  /// Skips `metadata` (JSON key ordering is non-deterministic after SQLite round-trip),
  /// `updatedAt` (set to Date() when nil on sync), and fields lost through SQLite.
  static func == (lhs: TaskActionItem, rhs: TaskActionItem) -> Bool {
    lhs.id == rhs.id && lhs.description == rhs.description && lhs.completed == rhs.completed
      && lhs.createdAt == rhs.createdAt && lhs.dueAt == rhs.dueAt && lhs.source == rhs.source
      && lhs.priority == rhs.priority && lhs.category == rhs.category && lhs.deleted == rhs.deleted
      && lhs.deletedBy == rhs.deletedBy && lhs.goalId == rhs.goalId
      && lhs.recurrenceRule == rhs.recurrenceRule
      && lhs.taskId == rhs.taskId && lhs.taskStatus == rhs.taskStatus
      && lhs.taskOwner == rhs.taskOwner && lhs.workstreamId == rhs.workstreamId
      && lhs.dueConfidence == rhs.dueConfidence && lhs.supersededBy == rhs.supersededBy
  }

  enum CodingKeys: String, CodingKey {
    case id, description, completed, source, priority, metadata, category, deleted
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case dueAt = "due_at"
    case completedAt = "completed_at"
    case conversationId = "conversation_id"
    case deletedBy = "deleted_by"
    case deletedAt = "deleted_at"
    case deletedReason = "deleted_reason"
    case keptTaskId = "kept_task_id"
    case goalId = "goal_id"
    case fromStaged = "from_staged"
    case recurrenceRule = "recurrence_rule"
    case recurrenceParentId = "recurrence_parent_id"
    case taskId = "task_id"
    case taskStatus = "status"
    case taskOwner = "owner"
    case workstreamId = "workstream_id"
    case dueConfidence = "due_confidence"
    case provenance
    case supersededBy = "superseded_by"
    case sortOrder = "sort_order"
    case indentLevel = "indent_level"
    case relevanceScore = "relevance_score"
  }

  /// Memberwise initializer for creating instances programmatically
  init(
    id: String,
    description: String,
    completed: Bool,
    createdAt: Date,
    updatedAt: Date? = nil,
    dueAt: Date? = nil,
    completedAt: Date? = nil,
    conversationId: String? = nil,
    source: String? = nil,
    priority: String? = nil,
    metadata: String? = nil,
    category: String? = nil,
    deleted: Bool? = nil,
    deletedBy: String? = nil,
    deletedAt: Date? = nil,
    deletedReason: String? = nil,
    keptTaskId: String? = nil,
    goalId: String? = nil,
    fromStaged: Bool? = nil,
    recurrenceRule: String? = nil,
    recurrenceParentId: String? = nil,
    taskId: String? = nil,
    taskStatus: String? = nil,
    taskOwner: String? = nil,
    workstreamId: String? = nil,
    dueConfidence: Double? = nil,
    provenance: [OmiAPI.EvidenceRef]? = nil,
    supersededBy: String? = nil,
    sortOrder: Int? = nil,
    indentLevel: Int? = nil,
    relevanceScore: Int? = nil,
    contextSummary: String? = nil,
    currentActivity: String? = nil,
    agentEditedFiles: [String]? = nil,
    agentStatus: String? = nil,
    agentPrompt: String? = nil,
    agentPlan: String? = nil,
    agentSessionId: String? = nil,
    agentStartedAt: Date? = nil,
    agentCompletedAt: Date? = nil,
    chatSessionId: String? = nil
  ) {
    self.id = id
    self.description = description
    self.completed = completed
    self.createdAt = createdAt
    self.updatedAt = updatedAt
    self.dueAt = dueAt
    self.completedAt = completedAt
    self.conversationId = conversationId
    self.source = source
    self.priority = priority
    self.metadata = metadata
    self.category = category
    self.deleted = deleted
    self.deletedBy = deletedBy
    self.deletedAt = deletedAt
    self.deletedReason = deletedReason
    self.keptTaskId = keptTaskId
    self.goalId = goalId
    self.fromStaged = fromStaged
    self.recurrenceRule = recurrenceRule
    self.recurrenceParentId = recurrenceParentId
    self.taskId = taskId
    self.taskStatus = taskStatus
    self.taskOwner = taskOwner
    self.workstreamId = workstreamId
    self.dueConfidence = dueConfidence
    self.provenance = provenance
    self.supersededBy = supersededBy
    self.sortOrder = sortOrder
    self.indentLevel = indentLevel
    self.relevanceScore = relevanceScore
    self.contextSummary = contextSummary
    self.currentActivity = currentActivity
    self.agentEditedFiles = agentEditedFiles
    self.agentStatus = agentStatus
    self.agentPrompt = agentPrompt
    self.agentPlan = agentPlan
    self.agentSessionId = agentSessionId
    self.agentStartedAt = agentStartedAt
    self.agentCompletedAt = agentCompletedAt
    self.chatSessionId = chatSessionId
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    // Keep the generated app-client contract as the wire authority while the
    // domain model continues to carry desktop-only state and legacy aliases.
    let wire = try? OmiAPI.ActionItemResponse(from: decoder)
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let standard = ISO8601DateFormatter()
    func parseWireDate(_ value: String?) -> Date? {
      value.flatMap { fractional.date(from: $0) ?? standard.date(from: $0) }
    }

    id = try wire?.id ?? container.decode(String.self, forKey: .id)
    description = try wire?.description_ ?? container.decodeIfPresent(String.self, forKey: .description) ?? ""
    completed = try wire?.completed ?? container.decodeIfPresent(Bool.self, forKey: .completed) ?? false
    createdAt = try parseWireDate(wire?.createdAt)
      ?? container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
    updatedAt = try parseWireDate(wire?.updatedAt)
      ?? container.decodeIfPresent(Date.self, forKey: .updatedAt)
    dueAt = try parseWireDate(wire?.dueAt) ?? container.decodeIfPresent(Date.self, forKey: .dueAt)
    completedAt = try parseWireDate(wire?.completedAt)
      ?? container.decodeIfPresent(Date.self, forKey: .completedAt)
    conversationId = try wire?.conversationId ?? container.decodeIfPresent(String.self, forKey: .conversationId)
    source = try wire?.source ?? container.decodeIfPresent(String.self, forKey: .source)
    priority = try wire?.priority?.rawValue ?? container.decodeIfPresent(String.self, forKey: .priority)
    metadata = try container.decodeIfPresent(String.self, forKey: .metadata)
    category = try container.decodeIfPresent(String.self, forKey: .category)
    deleted = try container.decodeIfPresent(Bool.self, forKey: .deleted)
    deletedBy = try container.decodeIfPresent(String.self, forKey: .deletedBy)
    deletedAt = try container.decodeIfPresent(Date.self, forKey: .deletedAt)
    deletedReason = try container.decodeIfPresent(String.self, forKey: .deletedReason)
    keptTaskId = try container.decodeIfPresent(String.self, forKey: .keptTaskId)
    goalId = try wire?.goalId ?? container.decodeIfPresent(String.self, forKey: .goalId)
    fromStaged = try container.decodeIfPresent(Bool.self, forKey: .fromStaged)
    recurrenceRule = try wire?.recurrenceRule ?? container.decodeIfPresent(String.self, forKey: .recurrenceRule)
    recurrenceParentId = try wire?.recurrenceParentId ?? container.decodeIfPresent(String.self, forKey: .recurrenceParentId)
    taskId = try wire?.taskId ?? container.decodeIfPresent(String.self, forKey: .taskId)
    taskStatus = try wire?.status?.rawValue ?? container.decodeIfPresent(String.self, forKey: .taskStatus)
    taskOwner = try wire?.owner?.rawValue ?? container.decodeIfPresent(String.self, forKey: .taskOwner)
    workstreamId = try wire?.workstreamId ?? container.decodeIfPresent(String.self, forKey: .workstreamId)
    dueConfidence = try wire?.dueConfidence ?? container.decodeIfPresent(Double.self, forKey: .dueConfidence)
    provenance = try wire?.provenance ?? container.decodeIfPresent([OmiAPI.EvidenceRef].self, forKey: .provenance)
    supersededBy = try wire?.supersededBy ?? container.decodeIfPresent(String.self, forKey: .supersededBy)
    sortOrder = try wire?.sortOrder ?? container.decodeIfPresent(Int.self, forKey: .sortOrder)
    indentLevel = try wire?.indentLevel ?? container.decodeIfPresent(Int.self, forKey: .indentLevel)
    relevanceScore = try container.decodeIfPresent(Int.self, forKey: .relevanceScore)

    // Local-only fields, not decoded from API
    contextSummary = nil
    currentActivity = nil
    agentEditedFiles = nil
    agentStatus = nil
    agentPrompt = nil
    agentPlan = nil
    agentSessionId = nil
    agentStartedAt = nil
    agentCompletedAt = nil
  }

  /// Categories that trigger Claude agent execution
  static let agentCategories: Set<String> = ["feature", "bug", "code"]

  /// Get tags array from metadata or fall back to single category
  var tags: [String] {
    // First try to get tags from metadata JSON
    if let metadata = metadata,
      let data = metadata.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let metaTags = json["tags"] as? [String], !metaTags.isEmpty
    {
      return metaTags
    }
    // Fall back to single category for backward compat
    if let category = category {
      return [category]
    }
    return []
  }

  /// Check if this task should trigger an agent (any task can trigger)
  var shouldTriggerAgent: Bool {
    return true
  }

  /// Parsed source classification from metadata
  var sourceClassification: TaskSourceClassification? {
    guard let metadata = metadata,
      let data = metadata.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let cat = json["source_category"] as? String,
      let sub = json["source_subcategory"] as? String
    else { return nil }
    return TaskSourceClassification.from(category: cat, subcategory: sub)
  }

  /// Parse metadata JSON to extract source app name
  var sourceApp: String? {
    guard let metadata = metadata,
      let data = metadata.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }
    return json["source_app"] as? String
  }

  /// Parse metadata JSON to extract window title
  var windowTitle: String? {
    guard let metadata = metadata,
      let data = metadata.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }
    return json["window_title"] as? String
  }

  /// Parse metadata JSON to extract confidence score
  var confidence: Double? {
    guard let metadata = metadata,
      let data = metadata.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }
    return json["confidence"] as? Double
  }

  /// Parse full metadata JSON dictionary
  var parsedMetadata: [String: Any]? {
    guard let metadata = metadata,
      let data = metadata.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }
    return json
  }

  /// Whether this task has detail metadata worth showing (beyond tags/category already visible as badges)
  var hasDetailMetadata: Bool {
    guard let json = parsedMetadata else { return false }
    let displayedKeys: Set<String> = ["tags", "category", "source_category", "source_subcategory"]
    return json.keys.contains(where: { !displayedKeys.contains($0) })
  }

  /// Display-friendly source label
  var sourceLabel: String {
    guard let source = source else { return "Task" }
    switch source {
    case "screenshot": return "Screen"
    case "transcription:omi": return "omi"
    case "transcription:desktop": return "Desktop"
    case "transcription:phone": return "Phone"
    case "manual": return "Manual"
    default: return "Task"
    }
  }

  /// Display label: app name for screenshot tasks, generic label otherwise
  var sourceAppLabel: String {
    if source == "screenshot", let app = sourceApp {
      return app
    }
    return sourceLabel
  }

  /// System icon name for source
  var sourceIcon: String {
    guard let source = source else { return "list.bullet" }
    switch source {
    case "screenshot": return "camera.fill"
    case "transcription:omi": return "waveform"
    case "transcription:desktop": return "desktopcomputer"
    case "transcription:phone": return "iphone"
    case "manual": return "square.and.pencil"
    default: return "list.bullet"
    }
  }

  /// Display-friendly category label
  var categoryLabel: String {
    guard let category = category else { return "" }
    return category.capitalized
  }

  /// System icon name for category
  var categoryIcon: String {
    guard let category = category else { return "folder.fill" }
    switch category {
    case "feature": return "sparkles"
    case "bug": return "ladybug.fill"
    case "code": return "chevron.left.forwardslash.chevron.right"
    case "work": return "briefcase.fill"
    case "personal": return "person.fill"
    case "research": return "magnifyingglass"
    case "communication": return "bubble.left.fill"
    case "finance": return "dollarsign.circle.fill"
    case "health": return "heart.fill"
    default: return "folder.fill"
    }
  }

  /// Color for category badge
  var categoryColor: String {
    guard let category = category else { return "gray" }
    switch category {
    case "feature": return "gray"
    case "bug": return "red"
    case "code": return "blue"
    case "work": return "orange"
    case "personal": return "green"
    case "research": return "cyan"
    case "communication": return "indigo"
    case "finance": return "yellow"
    case "health": return "pink"
    default: return "gray"
    }
  }

  /// All meaningful task data formatted for chat context.
  /// Add new fields here when they're added to the struct so chat always gets everything.
  var chatContext: String {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .short

    var lines: [String] = []

    // Core
    lines.append("Task: \(description)")
    if let category = category { lines.append("Category: \(category)") }
    if !tags.isEmpty { lines.append("Tags: \(tags.joined(separator: ", "))") }
    if let priority = priority { lines.append("Priority: \(priority)") }
    lines.append("Status: \(completed ? "completed" : "active")")
    lines.append("Created: \(formatter.string(from: createdAt))")
    if let dueAt = dueAt { lines.append("Due: \(formatter.string(from: dueAt))") }
    if let completedAt = completedAt {
      lines.append("Completed: \(formatter.string(from: completedAt))")
    }

    // Source & origin
    if let source = source { lines.append("Source: \(sourceLabel) (\(source))") }
    if let app = sourceApp { lines.append("Source app: \(app)") }
    if let title = windowTitle { lines.append("Window title: \(title)") }
    if let conf = confidence {
      lines.append("Extraction confidence: \(String(format: "%.0f%%", conf * 100))")
    }

    // Screen context at extraction time
    if let ctx = contextSummary, !ctx.isEmpty { lines.append("Context when detected: \(ctx)") }
    if let act = currentActivity, !act.isEmpty { lines.append("User activity: \(act)") }

    // Relationships
    if let convId = conversationId { lines.append("Conversation ID: \(convId)") }
    if let goalId = goalId { lines.append("Linked goal: \(goalId)") }

    // Agent work
    if let status = agentStatus { lines.append("Agent status: \(status)") }
    if let prompt = agentPrompt, !prompt.isEmpty {
      lines.append("Agent prompt: \(String(prompt.prefix(1000)))")
    }
    if let plan = agentPlan, !plan.isEmpty {
      lines.append("Agent plan:\n\(String(plan.prefix(2000)))")
    }
    if let files = agentEditedFiles, !files.isEmpty {
      lines.append("Files edited by agent: \(files.joined(separator: ", "))")
    }

    // Raw metadata (catches anything not explicitly listed above)
    if let meta = parsedMetadata {
      let coveredKeys: Set<String> = [
        "tags", "source_app", "window_title", "confidence",
        "source_category", "source_subcategory",
      ]
      let extra = meta.filter { !coveredKeys.contains($0.key) }
      if !extra.isEmpty {
        let pairs = extra.map { "\($0.key): \($0.value)" }.sorted()
        lines.append("Additional metadata: \(pairs.joined(separator: ", "))")
      }
    }

    return lines.joined(separator: "\n")
  }
}
