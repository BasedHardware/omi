import Foundation
import OmiWAL

// MARK: - Goal Models

/// Type of goal measurement
enum GoalType: String, Codable, CaseIterable {
  case boolean = "boolean"
  case scale = "scale"
  case numeric = "numeric"

  var displayName: String {
    switch self {
    case .boolean: return "Done/Not Done"
    case .scale: return "Scale"
    case .numeric: return "Numeric"
    }
  }
}
/// User goal
struct Goal: Codable, Identifiable {
  let id: String
  let title: String
  let description: String?
  let goalType: GoalType
  let targetValue: Double
  var currentValue: Double
  let minValue: Double
  let maxValue: Double
  let unit: String?
  let isActive: Bool
  let createdAt: Date
  let updatedAt: Date
  let completedAt: Date?
  let source: String?

  enum CodingKeys: String, CodingKey {
    case id, title, description, unit, source
    case goalType = "goal_type"
    case targetValue = "target_value"
    case currentValue = "current_value"
    case minValue = "min_value"
    case maxValue = "max_value"
    case isActive = "is_active"
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case completedAt = "completed_at"
  }

  init(from decoder: Decoder) throws {
    // Schema authority: OmiAPI.GoalResponse (generated from app-client OpenAPI).
    // The domain model layers on client-only fields (description, completedAt,
    // source) the backend REST schema does not expose, read via the same
    // container with tolerant fallbacks.
    let container = try decoder.container(keyedBy: CodingKeys.self)
    // Wire DTO required fields (created_at, title, etc.) are stricter than the
    // legacy decoder; use try? and fall back to the container for tolerance.
    let wire = try? OmiAPI.GoalResponse(from: decoder)

    id = try wire?.id ?? container.decodeIfPresent(String.self, forKey: .id) ?? ""
    title = try wire?.title ?? container.decodeIfPresent(String.self, forKey: .title) ?? ""
    description = try container.decodeIfPresent(String.self, forKey: .description)
    goalType =
      GoalType(rawValue: try wire?.goalType ?? container.decodeIfPresent(String.self, forKey: .goalType) ?? "")
      ?? .boolean
    targetValue = try wire?.targetValue ?? container.decodeIfPresent(Double.self, forKey: .targetValue) ?? 0
    currentValue = try wire?.currentValue ?? container.decodeIfPresent(Double.self, forKey: .currentValue) ?? 0
    minValue = try wire?.minValue ?? container.decodeIfPresent(Double.self, forKey: .minValue) ?? 0
    maxValue = try wire?.maxValue ?? container.decodeIfPresent(Double.self, forKey: .maxValue) ?? 0
    unit = try wire?.unit ?? container.decodeIfPresent(String.self, forKey: .unit)
    isActive = try wire?.isActive ?? container.decodeIfPresent(Bool.self, forKey: .isActive) ?? true
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let std = ISO8601DateFormatter()
    let createdAtString = wire?.createdAt
    createdAt = (createdAtString.flatMap { f.date(from: $0) ?? std.date(from: $0) }) ?? Date()
    let updatedAtString = wire?.updatedAt
    updatedAt = (updatedAtString.flatMap { f.date(from: $0) ?? std.date(from: $0) }) ?? createdAt
    completedAt = try container.decodeIfPresent(Date.self, forKey: .completedAt)
    source = try container.decodeIfPresent(String.self, forKey: .source)
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.container(keyedBy: CodingKeys.self)
    try container.encode(id, forKey: .id)
    try container.encode(title, forKey: .title)
    try container.encodeIfPresent(description, forKey: .description)
    try container.encode(goalType, forKey: .goalType)
    try container.encode(targetValue, forKey: .targetValue)
    try container.encode(currentValue, forKey: .currentValue)
    try container.encode(minValue, forKey: .minValue)
    try container.encode(maxValue, forKey: .maxValue)
    try container.encodeIfPresent(unit, forKey: .unit)
    try container.encode(isActive, forKey: .isActive)
    try container.encode(createdAt, forKey: .createdAt)
    try container.encode(updatedAt, forKey: .updatedAt)
    try container.encodeIfPresent(completedAt, forKey: .completedAt)
    try container.encodeIfPresent(source, forKey: .source)
  }

  /// Progress as a percentage (0-100), based on targetValue
  var progress: Double {
    guard targetValue != minValue else { return 0 }
    let pct = ((currentValue - minValue) / (targetValue - minValue)) * 100.0
    return min(max(pct, 0), 100)
  }

  /// Whether the goal is completed
  var isCompleted: Bool {
    currentValue >= targetValue
  }

  /// Formatted progress text
  var progressText: String {
    switch goalType {
    case .boolean:
      return isCompleted ? "Done" : "Not Done"
    case .scale, .numeric:
      if let unit = unit {
        return "\(Int(currentValue))/\(Int(targetValue)) \(unit)"
      }
      return "\(Int(currentValue))/\(Int(targetValue))"
    }
  }
}

/// Daily score calculation result
struct DailyScore: Codable {
  let score: Double
  let completedTasks: Int
  let totalTasks: Int
  let date: String

  enum CodingKeys: String, CodingKey {
    case score, date
    case completedTasks = "completed_tasks"
    case totalTasks = "total_tasks"
  }

  /// Score formatted as percentage
  var scorePercentage: String {
    return "\(Int(score))%"
  }

  /// Whether this is a perfect score
  var isPerfect: Bool {
    return score >= 100
  }
}

/// Single score data (used for daily, weekly, overall)
struct ScoreData: Codable {
  let score: Double
  let completedTasks: Int
  let totalTasks: Int

  enum CodingKeys: String, CodingKey {
    case score
    case completedTasks = "completed_tasks"
    case totalTasks = "total_tasks"
  }

  var scorePercentage: String {
    return "\(Int(score))%"
  }

  var hasTasks: Bool {
    return totalTasks > 0
  }
}

/// Combined score response with all three score types
struct ScoreResponse: Codable {
  let daily: ScoreData
  let weekly: ScoreData
  let overall: ScoreData
  let defaultTab: String
  let date: String

  enum CodingKeys: String, CodingKey {
    case daily, weekly, overall, date
    case defaultTab = "default_tab"
  }
}
