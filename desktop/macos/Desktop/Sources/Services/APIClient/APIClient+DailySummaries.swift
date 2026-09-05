import Foundation

// MARK: - Daily summaries (read)

/// One generated daily summary, as served by `GET /v1/users/daily-summaries`.
///
/// Mirrors the backend's `DailySummaryResponse` (`backend/routers/users.py`). Every field is
/// optional on the wire; the desktop only renders what is present. Dates stay as the backend's
/// strings: `date` is `YYYY-MM-DD` and `createdAt` is ISO 8601, and neither needs arithmetic here.
struct DailySummaryRecord: Decodable, Identifiable, Equatable {
  struct Stats: Decodable, Equatable {
    let totalConversations: Int?
    let totalDurationMinutes: Int?
    let actionItemsCount: Int?
    let memoriesCreated: Int?
    let actionItemsCreated: Int?
    let watchingMinutes: Int?
    let proactiveMoments: Int?

    enum CodingKeys: String, CodingKey {
      case totalConversations = "total_conversations"
      case totalDurationMinutes = "total_duration_minutes"
      case actionItemsCount = "action_items_count"
      case memoriesCreated = "memories_created"
      case actionItemsCreated = "action_items_created"
      case watchingMinutes = "watching_minutes"
      case proactiveMoments = "proactive_moments"
    }
  }

  struct ActionItem: Decodable, Equatable {
    let description: String?
    let priority: String?
    /// The conversation the task came from, when the backend resolved one. The dedicated recap
    /// page deep-links it; nothing else reads it.
    let sourceConversationId: String?
    let completed: Bool?

    enum CodingKeys: String, CodingKey {
      case description, priority, completed
      case sourceConversationId = "source_conversation_id"
    }

    init(
      description: String?, priority: String? = nil, sourceConversationId: String? = nil,
      completed: Bool? = nil
    ) {
      self.description = description
      self.priority = priority
      self.sourceConversationId = sourceConversationId
      self.completed = completed
    }
  }

  struct Highlight: Decodable, Equatable {
    let topic: String?
    let emoji: String?
    let summary: String?
    /// Every conversation the day's discussion of this topic drew on, so the recap page can open
    /// the source instead of asserting the summary line.
    let conversationIds: [String]?

    enum CodingKeys: String, CodingKey {
      case topic, emoji, summary
      case conversationIds = "conversation_ids"
    }

    init(
      topic: String?, emoji: String? = nil, summary: String? = nil,
      conversationIds: [String]? = nil
    ) {
      self.topic = topic
      self.emoji = emoji
      self.summary = summary
      self.conversationIds = conversationIds
    }
  }

  /// A question the day left open. `conversation_id` points at the conversation that raised it.
  struct UnresolvedQuestion: Decodable, Equatable {
    let question: String?
    let conversationId: String?

    enum CodingKeys: String, CodingKey {
      case question
      case conversationId = "conversation_id"
    }
  }

  /// A decision the day settled. `conversation_id` points at the conversation that produced it.
  struct DecisionMade: Decodable, Equatable {
    let decision: String?
    let conversationId: String?

    enum CodingKeys: String, CodingKey {
      case decision
      case conversationId = "conversation_id"
    }
  }

  /// One learning from the day, as LLM prose. Unlike `LearnedMemory` it addresses no memory row,
  /// so it renders as text with an optional source link and nothing more.
  struct KnowledgeNugget: Decodable, Equatable {
    let insight: String?
    let conversationId: String?

    enum CodingKeys: String, CodingKey {
      case insight
      case conversationId = "conversation_id"
    }
  }

  /// One memory the day actually produced, addressed by its canonical id.
  ///
  /// This is the identity `knowledge_nuggets` never had. `knowledge_nuggets` is LLM prose about
  /// the day; a `LearnedMemory` is a row in the memory store, so the card can show what Omi
  /// actually stored and the owner can accept, reject, or correct it through the existing memory
  /// endpoints. Review state (`user_review` / `edited`) is deliberately *not* on the wire here:
  /// clients read it live from the memory, so a vote on the phone shows on the Mac.
  struct LearnedMemory: Decodable, Equatable {
    let memoryID: String
    let content: String
    let category: String
    let capturedAt: String?

    enum CodingKeys: String, CodingKey {
      case memoryID = "memory_id"
      case content, category
      case capturedAt = "captured_at"
    }

    init(from decoder: Decoder) throws {
      let container = try decoder.container(keyedBy: CodingKeys.self)
      // Trimmed at the wire: every reader treats a blank id as "not a review row", and a
      // whitespace-only id would otherwise pass each of those emptiness checks.
      memoryID = (try container.decodeIfPresent(String.self, forKey: .memoryID) ?? "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
      content = try container.decodeIfPresent(String.self, forKey: .content) ?? ""
      category = try container.decodeIfPresent(String.self, forKey: .category) ?? ""
      capturedAt = try container.decodeIfPresent(String.self, forKey: .capturedAt)
    }

    init(memoryID: String, content: String, category: String = "", capturedAt: String? = nil) {
      self.memoryID = memoryID
      self.content = content
      self.category = category
      self.capturedAt = capturedAt
    }
  }

  let id: String
  let date: String?
  let createdAt: String?
  let headline: String?
  let overview: String?
  let dayEmoji: String?
  let stats: Stats?
  let highlights: [Highlight]?
  let actionItems: [ActionItem]?
  let unresolvedQuestions: [UnresolvedQuestion]?
  let decisionsMade: [DecisionMade]?
  let knowledgeNuggets: [KnowledgeNugget]?
  /// Empty rather than optional: "the field is absent" and "the day produced nothing to review"
  /// are the same thing for every reader, and an older backend must not make the card ambiguous.
  let memoriesLearned: [LearnedMemory]

  enum CodingKeys: String, CodingKey {
    case id, date, headline, overview, stats, highlights
    case createdAt = "created_at"
    case dayEmoji = "day_emoji"
    case actionItems = "action_items"
    case unresolvedQuestions = "unresolved_questions"
    case decisionsMade = "decisions_made"
    case knowledgeNuggets = "knowledge_nuggets"
    case memoriesLearned = "memories_learned"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    // `id` is optional on the wire; a record without one cannot be opened or deduplicated, so
    // synthesize a stable identity from the date rather than dropping the whole summary.
    let wireID = try container.decodeIfPresent(String.self, forKey: .id)
    date = try container.decodeIfPresent(String.self, forKey: .date)
    id = wireID ?? "date:\(date ?? "unknown")"
    createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
    headline = try container.decodeIfPresent(String.self, forKey: .headline)
    overview = try container.decodeIfPresent(String.self, forKey: .overview)
    dayEmoji = try container.decodeIfPresent(String.self, forKey: .dayEmoji)
    stats = try container.decodeIfPresent(Stats.self, forKey: .stats)
    highlights = try container.decodeIfPresent([Highlight].self, forKey: .highlights)
    actionItems = try container.decodeIfPresent([ActionItem].self, forKey: .actionItems)
    unresolvedQuestions = try container.decodeIfPresent(
      [UnresolvedQuestion].self, forKey: .unresolvedQuestions)
    decisionsMade = try container.decodeIfPresent([DecisionMade].self, forKey: .decisionsMade)
    knowledgeNuggets = try container.decodeIfPresent(
      [KnowledgeNugget].self, forKey: .knowledgeNuggets)
    // A malformed entry must not cost the reader the whole summary, and a memory with no id
    // cannot be voted on or corrected, so it is not a review row at all. Entries decode
    // independently: one bad element drops itself, not every valid row beside it. The outer
    // `try?` still absorbs a `memories_learned` that is not an array at all.
    memoriesLearned =
      (try? container.decodeIfPresent([LenientLearnedMemory].self, forKey: .memoriesLearned))
      .flatMap { $0 }?
      .compactMap(\.value)
      .filter { !$0.memoryID.isEmpty && !$0.content.isEmpty } ?? []
  }

  init(
    id: String, date: String?, createdAt: String? = nil, headline: String?, overview: String?,
    dayEmoji: String? = nil, stats: Stats? = nil, highlights: [Highlight]? = nil,
    actionItems: [ActionItem]? = nil, unresolvedQuestions: [UnresolvedQuestion]? = nil,
    decisionsMade: [DecisionMade]? = nil, knowledgeNuggets: [KnowledgeNugget]? = nil,
    memoriesLearned: [LearnedMemory] = []
  ) {
    self.id = id
    self.date = date
    self.createdAt = createdAt
    self.headline = headline
    self.overview = overview
    self.dayEmoji = dayEmoji
    self.stats = stats
    self.highlights = highlights
    self.actionItems = actionItems
    self.unresolvedQuestions = unresolvedQuestions
    self.decisionsMade = decisionsMade
    self.knowledgeNuggets = knowledgeNuggets
    self.memoriesLearned = memoriesLearned
  }
}

/// One `memories_learned` element, decoded so that its own failure is local to it.
private struct LenientLearnedMemory: Decodable {
  let value: DailySummaryRecord.LearnedMemory?

  init(from decoder: Decoder) throws {
    value = try? DailySummaryRecord.LearnedMemory(from: decoder)
  }
}

struct DailySummariesListResponse: Decodable {
  let summaries: [DailySummaryRecord]
}

extension APIClient {
  /// Newest-first daily summaries for the signed-in user. The backend caps `limit` at 100.
  func getDailySummaries(limit: Int = 7) async throws -> [DailySummaryRecord] {
    let bounded = min(max(limit, 1), 100)
    let response: DailySummariesListResponse = try await get("v1/users/daily-summaries?limit=\(bounded)")
    return response.summaries
  }

  /// One recap by id. The recap route persists identity only, so the page it
  /// opens re-reads the record by id — a relaunch onto the route re-fetches
  /// rather than restoring stale text.
  func getDailySummary(id: String) async throws -> DailySummaryRecord {
    try await get("v1/users/daily-summaries/\(id)")
  }

  /// Generate (or return) a recap for a local calendar date. No push is sent.
  func createDailySummary(date: String) async throws -> DailySummaryRecord {
    struct Body: Encodable { let date: String }
    return try await post(
      "v1/users/daily-summaries", body: Body(date: date), requestTimeout: 180)
  }

  /// Re-run summary generation for an existing recap and overwrite it in place. No push.
  func regenerateDailySummary(id: String) async throws -> DailySummaryRecord {
    struct EmptyBody: Encodable {}
    return try await post(
      "v1/users/daily-summaries/\(id)/regenerate", body: EmptyBody(), requestTimeout: 180)
  }
}
