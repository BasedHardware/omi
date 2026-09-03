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

  let id: String
  let date: String?
  let createdAt: String?
  let headline: String?
  let overview: String?
  let dayEmoji: String?
  let stats: Stats?
  let highlights: [Highlight]?
  let actionItems: [ActionItem]?

  enum CodingKeys: String, CodingKey {
    case id, date, headline, overview, stats, highlights
    case createdAt = "created_at"
    case dayEmoji = "day_emoji"
    case actionItems = "action_items"
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
  }

  init(
    id: String, date: String?, createdAt: String? = nil, headline: String?, overview: String?,
    dayEmoji: String? = nil, stats: Stats? = nil, highlights: [Highlight]? = nil,
    actionItems: [ActionItem]? = nil
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
