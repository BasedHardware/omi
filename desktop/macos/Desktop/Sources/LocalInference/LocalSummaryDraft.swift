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

  /// Guided generation honors `required` more tightly than the prompt.
  /// Map/reduce prompts ask for title, overview, sections, and action items;
  /// those four are required so AFM cannot omit them. `emoji`, `category`, and
  /// `events` stay optional.
  ///
  /// **The arrays are bounded, and that is load-bearing.** A
  /// `LanguageModelSession`'s transcript is prompt *plus* completion against one
  /// context window, so an unbounded array lets the model spend the window on its
  /// own output and overflow. Measured 2026-09-18 on live AFM: a map pass emitted
  /// 7 sections and 26 action items and the session threw
  /// `"The session's transcript exceeded the model's context size."` — while a
  /// *larger* prompt that happened to generate less succeeded. That is why the
  /// failure looked non-deterministic and unrelated to prompt size.
  ///
  /// The caps sit at or below `ClientProcessingContract`'s own limits (12 sections,
  /// 25 action items, 12 events), which truncate after assembly anyway. Generating
  /// items that are about to be discarded costs context we cannot spare.
  static let jsonSchema = schema(
    name: "client_processing_draft", maxSections: 8, maxEvents: 6, maxActionItems: 15)

  /// Tighter caps for a **map** pass, which summarizes one slice, not the meeting.
  ///
  /// The caps are the only bound on a completion: guided generation has no string
  /// length limit, so an 8-section / 15-item draft of one slice measured anywhere
  /// from 3 KB to 10 KB for the same prompt (2026-09-21, live AFM). The 10 KB draws
  /// overflowed the 8192-token prompt+completion window and the whole conversation
  /// fell back to the deterministic minimum after minutes of work. A slice does
  /// not have eight topics; the full caps apply where the whole meeting is in view
  /// (single pass and reduce). Smaller partials also keep the reduce prompt small.
  static let mapJSONSchema = schema(
    name: "client_processing_map_draft", maxSections: 5, maxEvents: 4, maxActionItems: 10)

  /// One authored property order for every profile: property order is generation
  /// order under both AFM guided generation and a llama.cpp grammar.
  private static func schema(
    name: String, maxSections: Int, maxEvents: Int, maxActionItems: Int
  ) -> LocalInferenceJSONSchema {
    LocalInferenceJSONSchema(
      name: name,
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
              "maxItems": \(maxSections),
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
              "maxItems": \(maxEvents),
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
              "maxItems": \(maxActionItems),
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
          "required": ["title", "overview", "sections", "action_items"]
        }
        """.utf8)
    )
  }
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
