import Foundation

// MARK: - Advice Category

enum AdviceCategory: String, Codable {
    case productivity
    case health // legacy, kept for backward compatibility with stored records
    case communication
    case learning
    case other
}

// MARK: - Extracted Advice

struct ExtractedAdvice: Codable {
    let advice: String
    let headline: String?
    let reasoning: String?
    let category: AdviceCategory
    let sourceApp: String
    let confidence: Double

    enum CodingKeys: String, CodingKey {
        case advice
        case headline
        case reasoning
        case category
        case sourceApp = "source_app"
        case confidence
    }

    /// Convert to dictionary for Flutter
    func toDictionary() -> [String: Any] {
        var dict: [String: Any] = [
            "advice": advice,
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

// MARK: - Advice Extraction Result

struct AdviceExtractionResult: Codable, AssistantResult {
    let hasAdvice: Bool
    let advice: ExtractedAdvice?
    let contextSummary: String
    let currentActivity: String

    enum CodingKeys: String, CodingKey {
        case hasAdvice = "has_advice"
        case advice
        case contextSummary = "context_summary"
        case currentActivity = "current_activity"
    }

    /// Convert to dictionary for Flutter
    func toDictionary() -> [String: Any] {
        var dict: [String: Any] = [
            "hasAdvice": hasAdvice,
            "contextSummary": contextSummary,
            "currentActivity": currentActivity
        ]
        if let advice = advice {
            dict["advice"] = advice.toDictionary()
        }
        return dict
    }
}
