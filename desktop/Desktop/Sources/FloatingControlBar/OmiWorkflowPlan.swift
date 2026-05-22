import Foundation

enum OmiActionType: String, Codable {
    case click
    case type
    case shortcut
    case scroll
    case openApp = "open_app"
}

struct OmiWorkflowStep: Codable {
    let action: OmiActionType
    let target: String?
    let value: String?
    let scrollDirection: String?
    let scrollAmount: Int?
    let stepDescription: String

    enum CodingKeys: String, CodingKey {
        case action
        case target
        case value
        case scrollDirection = "scroll_direction"
        case scrollAmount = "scroll_amount"
        case stepDescription = "step_description"
    }
}

struct OmiWorkflowPlan: Codable {
    let description: String
    let steps: [OmiWorkflowStep]
}
