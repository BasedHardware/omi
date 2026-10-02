import Foundation

struct ScreenTaskResponse: Decodable {
  let screen_kind: String
  let context_summary: String
  let current_activity: String
  let tasks: [Item]

  struct Item: Decodable {
    let title: String
    let description: String
    let deadline: String
    let priority: TaskPriority
    let confidence: Double
    let relation: String
    let related_id: String
    let evidence: String
    let capture_kind: String
    let owner: String
    let concrete_deliverable: Bool
    let public_broadcast: Bool
    let direct_mention: Bool
    let ownership_confidence: Double
    let tags: [String]
    let source_category: String
    let source_subcategory: String
  }

  func results(app: String, context: [TaskSearchResult], today: String) throws -> [TaskExtractionResult] {
    guard ["open_conversation", "open_email_or_document", "list_or_overview", "other"].contains(screen_kind),
      tasks.count <= 8
    else { throw GeminiClient.GeminiClientError.invalidResponse }
    let ids = Set(context.filter { $0.status == "active" }.compactMap(\.taskID))
    if tasks.isEmpty {
      return [
        TaskExtractionResult(
          hasNewTask: false, task: nil, contextSummary: context_summary, currentActivity: current_activity)
      ]
    }
    return try tasks.map { item in
      let title = item.title.trimmingCharacters(in: .whitespacesAndNewlines)
      let count = title.split(whereSeparator: \.isWhitespace).count
      guard (6...15).contains(count), item.confidence.isFinite, (0...1).contains(item.confidence),
        item.ownership_confidence.isFinite, (0...1).contains(item.ownership_confidence),
        ["new", "duplicate", "refines", "completes"].contains(item.relation),
        ["explicit_command", "clear_commitment", "direct_request", "inferred_next_step", "already_done"].contains(
          item.capture_kind),
        ["user", "other", "unknown"].contains(item.owner),
        TaskSourceClassification.from(category: item.source_category, subcategory: item.source_subcategory) != nil,
        item.relation == "new" ? item.related_id.isEmpty : ids.contains(item.related_id),
        item.relation != "completes" || item.capture_kind == "already_done"
      else { throw GeminiClient.GeminiClientError.invalidResponse }
      let deadline = Self.deadline(item.deadline, today: today)
      let task = ExtractedTask(
        title: title, description: item.description, priority: item.priority, sourceApp: app,
        inferredDeadline: deadline, confidence: item.confidence, tags: item.tags,
        sourceCategory: item.source_category, sourceSubcategory: item.source_subcategory,
        captureKind: item.capture_kind, owner: item.owner, concreteDeliverable: item.concrete_deliverable,
        publicBroadcast: item.public_broadcast, directMention: item.direct_mention,
        alreadyDone: item.capture_kind == "already_done",
        duplicateOf: item.relation == "duplicate" ? item.related_id : nil,
        refinesTask: ["refines", "completes"].contains(item.relation) ? item.related_id : nil,
        ownershipConfidence: item.ownership_confidence
      )
      return TaskExtractionResult(
        hasNewTask: true, task: task, contextSummary: context_summary, currentActivity: current_activity)
    }
  }

  static func deadline(_ value: String, today: String) -> String? {
    guard !value.isEmpty, value >= today else { return nil }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "yyyy-MM-dd"
    formatter.isLenient = false
    guard let date = formatter.date(from: value), formatter.string(from: date) == value else { return nil }
    return value
  }
}

/// Vertex candidates carry camelCase on the existing proxy wire. Ignore thinking parts.
struct ScreenTaskGeminiResponse: Decodable {
  struct Candidate: Decodable {
    struct Content: Decodable {
      struct Part: Decodable {
        let text: String?
        let thought: Bool?
      }
      let parts: [Part]
    }
    let content: Content
    let finishReason: String?
  }
  let candidates: [Candidate]
  func text() throws -> String {
    guard let candidate = candidates.first, candidate.finishReason == nil || candidate.finishReason == "STOP" else {
      throw GeminiClient.GeminiClientError.invalidResponse
    }
    let text = candidate.content.parts.filter { $0.thought != true }.compactMap(\.text).joined()
    guard !text.isEmpty else { throw GeminiClient.GeminiClientError.invalidResponse }
    return text
  }
}
