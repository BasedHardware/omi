import Foundation

/// Structured output the local engine returns for one map or reduce pass.
/// Field names match the W1 wire so a well-behaved model can be stamped into
/// `OmiAPI.ClientProcessing` without a second translation layer.
struct LocalSummaryDraft: Codable, Sendable, Equatable {
  var title: String
  var overview: String
  var emoji: String?
  var category: String?
  var sections: [LocalSectionDraft]
  var events: [LocalEventDraft]
  var actionItems: [LocalActionItemDraft]

  enum CodingKeys: String, CodingKey {
    case title
    case overview
    case emoji
    case category
    case sections
    case events
    case actionItems = "action_items"
  }

  init(
    title: String,
    overview: String = "",
    emoji: String? = nil,
    category: String? = "other",
    sections: [LocalSectionDraft] = [],
    events: [LocalEventDraft] = [],
    actionItems: [LocalActionItemDraft] = []
  ) {
    self.title = title
    self.overview = overview
    self.emoji = emoji
    self.category = category
    self.sections = sections
    self.events = events
    self.actionItems = actionItems
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
    overview = try c.decodeIfPresent(String.self, forKey: .overview) ?? ""
    emoji = try c.decodeIfPresent(String.self, forKey: .emoji)
    category = try c.decodeIfPresent(String.self, forKey: .category)
    sections = try c.decodeIfPresent([LocalSectionDraft].self, forKey: .sections) ?? []
    events = try c.decodeIfPresent([LocalEventDraft].self, forKey: .events) ?? []
    actionItems = try c.decodeIfPresent([LocalActionItemDraft].self, forKey: .actionItems) ?? []
  }

  static let jsonSchema = LocalInferenceJSONSchema(
    name: "client_processing_draft",
    json: Data(
      """
      {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "overview": {"type": "string"},
          "emoji": {"type": "string"},
          "category": {"type": "string"},
          "sections": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "heading": {"type": "string"},
                "body_markdown": {"type": "string"}
              },
              "required": ["heading", "body_markdown"]
            }
          },
          "events": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "start": {"type": "string"},
                "duration": {"type": "integer"}
              },
              "required": ["title", "start", "duration"]
            }
          },
          "action_items": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "description": {"type": "string"},
                "completed": {"type": "boolean"}
              },
              "required": ["description"]
            }
          }
        },
        "required": ["title"]
      }
      """.utf8)
  )
}

struct LocalSectionDraft: Codable, Sendable, Equatable {
  var heading: String
  var bodyMarkdown: String

  enum CodingKeys: String, CodingKey {
    case heading
    case bodyMarkdown = "body_markdown"
  }
}

struct LocalEventDraft: Codable, Sendable, Equatable {
  var title: String
  var description: String
  var start: String
  var duration: Int

  enum CodingKeys: String, CodingKey {
    case title
    case description
    case start
    case duration
  }

  init(title: String, description: String = "", start: String, duration: Int) {
    self.title = title
    self.description = description
    self.start = start
    self.duration = duration
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    title = try c.decode(String.self, forKey: .title)
    description = try c.decodeIfPresent(String.self, forKey: .description) ?? ""
    start = try c.decode(String.self, forKey: .start)
    duration = try c.decodeIfPresent(Int.self, forKey: .duration) ?? 30
  }
}

struct LocalActionItemDraft: Codable, Sendable, Equatable {
  var description: String
  var completed: Bool

  init(description: String, completed: Bool = false) {
    self.description = description
    self.completed = completed
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    description = try c.decode(String.self, forKey: .description)
    completed = try c.decodeIfPresent(Bool.self, forKey: .completed) ?? false
  }
}
