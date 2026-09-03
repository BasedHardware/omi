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
    let completed: Bool?
  }

  struct Highlight: Decodable, Equatable {
    let topic: String?
    let emoji: String?
    let summary: String?
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
      memoryID = try container.decodeIfPresent(String.self, forKey: .memoryID) ?? ""
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
  /// Empty rather than optional: "the field is absent" and "the day produced nothing to review"
  /// are the same thing for every reader, and an older backend must not make the card ambiguous.
  let memoriesLearned: [LearnedMemory]

  enum CodingKeys: String, CodingKey {
    case id, date, headline, overview, stats, highlights
    case createdAt = "created_at"
    case dayEmoji = "day_emoji"
    case actionItems = "action_items"
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
    // A malformed entry must not cost the reader the whole summary, and a memory with no id
    // cannot be voted on or corrected, so it is not a review row at all.
    memoriesLearned =
      (try? container.decodeIfPresent([LearnedMemory].self, forKey: .memoriesLearned))
      .flatMap { $0 }?
      .filter { !$0.memoryID.isEmpty && !$0.content.isEmpty } ?? []
  }

  init(
    id: String, date: String?, createdAt: String? = nil, headline: String?, overview: String?,
    dayEmoji: String? = nil, stats: Stats? = nil, highlights: [Highlight]? = nil,
    actionItems: [ActionItem]? = nil, memoriesLearned: [LearnedMemory] = []
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
    self.memoriesLearned = memoriesLearned
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
}
