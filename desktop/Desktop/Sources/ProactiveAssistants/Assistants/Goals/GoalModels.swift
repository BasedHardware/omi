import Foundation

/// AI-generated goal suggestion
struct GoalSuggestion: Codable {
    let suggestedTitle: String
    let suggestedDescription: String?
    let suggestedType: String
    let suggestedTarget: Double
    let suggestedMin: Double
    let suggestedMax: Double
    let reasoning: String
    let linkedTaskIds: [String]?

    enum CodingKeys: String, CodingKey {
        case suggestedTitle = "suggested_title"
        case suggestedDescription = "suggested_description"
        case suggestedType = "suggested_type"
        case suggestedTarget = "suggested_target"
        case suggestedMin = "suggested_min"
        case suggestedMax = "suggested_max"
        case reasoning
        case linkedTaskIds = "linked_task_ids"
    }

    /// Convert suggested type string to GoalType enum
    var goalType: GoalType {
        switch suggestedType.lowercased() {
        case "boolean":
            return .boolean
        case "scale":
            return .scale
        case "numeric":
            return .numeric
        default:
            return .numeric
        }
    }
}

/// Result of AI progress extraction from text
struct ProgressExtraction: Codable {
    let found: Bool
    let value: Double?
    let reasoning: String?
}
