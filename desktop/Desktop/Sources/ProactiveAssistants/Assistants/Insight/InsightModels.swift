import Foundation

// MARK: - Insight Category

enum InsightCategory: String, Codable {
    case productivity
    case health // legacy, kept for backward compatibility with stored records
    case communication
    case learning
    case other
}

// MARK: - Extracted Insight

struct ExtractedInsight: Codable {
    let insight: String
    let headline: String?
    let reasoning: String?
    let category: InsightCategory
    let sourceApp: String
    let confidence: Double

    enum CodingKeys: String, CodingKey {
        case insight = "advice"
        case headline
        case reasoning
        case category
        case sourceApp = "source_app"
        case confidence
    }

    /// Convert to dictionary for Flutter
    func toDictionary() -> [String: Any] {
        var dict: [String: Any] = [
            "advice": insight,
            "category": category.rawValue,
            "sourceApp": sourceApp,
            "confidence": confidence
        ]
        if let headline = headline {
            dict["headline"] = headline
        }
        if let reasoning = reasoning {
            dict["reasoning"] = reasoning
        }
        return dict
    }
}

// MARK: - Insight Extraction Result

struct InsightExtractionResult: Codable, AssistantResult {
    let hasInsight: Bool
    let insight: ExtractedInsight?
    let contextSummary: String
    let currentActivity: String

    enum CodingKeys: String, CodingKey {
        case hasInsight = "has_advice"
        case insight = "advice"
        case contextSummary = "context_summary"
        case currentActivity = "current_activity"
    }

    /// Convert to dictionary for Flutter
    func toDictionary() -> [String: Any] {
        var dict: [String: Any] = [
            "hasInsight": hasInsight,
            "contextSummary": contextSummary,
            "currentActivity": currentActivity
        ]
        if let insight = insight {
            dict["advice"] = insight.toDictionary()
        }
        return dict
    }
}
