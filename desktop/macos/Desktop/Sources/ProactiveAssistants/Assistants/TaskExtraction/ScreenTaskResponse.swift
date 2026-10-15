import Foundation

enum ScreenTaskFailure: Error {
  case invalidResponse, planGated, stopped, privacyRevoked, ownerRevoked, backpressure, providerOutage,
    gateBudgetCooldown
}

struct ScreenTaskResponse: Decodable {
  let screen_kind: String
  let context_summary: String
  let current_activity: String
  let tasks: [Item]
  let invalidItemCount: Int

  private enum CodingKeys: String, CodingKey { case screen_kind, context_summary, current_activity, tasks }
  init(from decoder: Decoder) throws {
    let root = try decoder.container(keyedBy: CodingKeys.self)
    screen_kind = try root.decode(String.self, forKey: .screen_kind)
    context_summary = try root.decode(String.self, forKey: .context_summary)
    current_activity = try root.decode(String.self, forKey: .current_activity)
    var items = try root.nestedUnkeyedContainer(forKey: .tasks)
    var valid: [Item] = []
    var rejected = 0
    while !items.isAtEnd {
      let itemDecoder = try items.superDecoder()
      if let item = try? Item(from: itemDecoder) { valid.append(item) } else { rejected += 1 }
    }
    tasks = valid
    invalidItemCount = rejected
  }

  struct Item: Codable {
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
      tasks.count <= 8, context_summary.count <= 96, current_activity.count <= 96
    else { throw ScreenTaskFailure.invalidResponse }
    let ids = Set(context.filter { $0.status == "active" }.compactMap(\.taskID))
    if tasks.isEmpty {
      return [
        TaskExtractionResult(
          hasNewTask: false, task: nil, contextSummary: context_summary, currentActivity: current_activity)
      ]
    }
    return tasks.compactMap { item in
      let title = item.title.trimmingCharacters(in: .whitespacesAndNewlines)
      let count = title.split(whereSeparator: \.isWhitespace).count
      guard (6...15).contains(count), item.confidence.isFinite, (0...1).contains(item.confidence),
        title.count <= 96, item.description.count <= 64, item.deadline.count <= 10,
        item.related_id.count <= 128, item.evidence.isEmpty,
        item.tags.count <= 3, item.tags.allSatisfy({ $0.count <= 16 }),
        item.ownership_confidence.isFinite, (0...1).contains(item.ownership_confidence),
        ["new", "duplicate", "refines", "completes"].contains(item.relation),
        ["explicit_command", "clear_commitment", "direct_request", "inferred_next_step", "already_done"].contains(
          item.capture_kind),
        ["user", "other", "unknown"].contains(item.owner),
        TaskSourceClassification.from(category: item.source_category, subcategory: item.source_subcategory) != nil,
        item.relation == "new" ? item.related_id.isEmpty : ids.contains(item.related_id),
        item.relation != "completes" || item.capture_kind == "already_done"
      else { return nil }
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
    formatter.dateFormat = "yyyy-MM-dd"  // omi-ux-allow: date-format-string -- Fixed extractor wire date, never user-facing UI.
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
    guard let candidate = candidates.first,
      candidate.finishReason == nil || ["STOP", "MAX_TOKENS"].contains(candidate.finishReason ?? "")
    else {
      throw ScreenTaskFailure.invalidResponse
    }
    let text = candidate.content.parts.filter { $0.thought != true }.compactMap(\.text).joined()
    guard !text.isEmpty else { throw ScreenTaskFailure.invalidResponse }
    return candidate.finishReason == "MAX_TOKENS" ? try ScreenTaskPartialJSON.completeItems(text) : text
  }
}

/// On output-cap truncation retain only fully closed JSON objects in the tasks array.
/// String escapes and nested arrays/objects are parsed structurally, never with a regex.
enum ScreenTaskPartialJSON {
  static func completeItems(_ text: String) throws -> String {
    if (try? JSONSerialization.jsonObject(with: Data(text.utf8))) != nil { return text }
    guard let tasksRange = text.range(of: "\"tasks\""),
      let arrayStart = text[tasksRange.upperBound...].firstIndex(of: "[")
    else { throw ScreenTaskFailure.invalidResponse }
    var depth = 0
    var inString = false
    var escaped = false
    var start: String.Index?
    var items: [Any] = []
    for index in text.indices where index > arrayStart {
      let character = text[index]
      if inString {
        if escaped {
          escaped = false
        } else if character == "\\" {
          escaped = true
        } else if character == "\"" {
          inString = false
        }
        continue
      }
      if character == "\"" {
        inString = true
        continue
      }
      if character == "{" {
        if depth == 0 { start = index }
        depth += 1
      } else if character == "}" {
        depth -= 1
        if depth == 0, let start,
          let item = try? JSONSerialization.jsonObject(with: Data(text[start...index].utf8))
        {
          items.append(item)
        }
      } else if character == "]", depth == 0 {
        break
      }
    }
    let recovered: [String: Any] = [
      "screen_kind": "other", "context_summary": "", "current_activity": "", "tasks": items,
    ]
    let data = try JSONSerialization.data(withJSONObject: recovered)
    guard let value = String(data: data, encoding: .utf8) else { throw ScreenTaskFailure.invalidResponse }
    return value
  }
}
