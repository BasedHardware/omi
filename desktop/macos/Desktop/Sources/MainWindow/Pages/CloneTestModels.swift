import Foundation

// Clone test API models. These mirror backend/models/clone.py. The APIClient
// decoder does NOT use convertFromSnakeCase, so every model declares explicit
// snake_case CodingKeys. Kept Foundation-only so the request/response contract
// can be validated without the SwiftUI layer.

struct CloneAskRequestPayload: Encodable {
    let question: String
    let usePersona: Bool
    enum CodingKeys: String, CodingKey {
        case question
        case usePersona = "use_persona"
    }
}

struct CloneAskResponse: Decodable {
    let answer: String
    let grounded: Bool
    let memoriesUsed: Int
    let personaUsed: Bool
    enum CodingKeys: String, CodingKey {
        case answer
        case grounded
        case memoriesUsed = "memories_used"
        case personaUsed = "persona_used"
    }
}

struct CloneBenchmarkSamplePayload: Encodable {
    let incomingMessage: String
    let actualReply: String
    let contactName: String?
    let network: String?
    enum CodingKeys: String, CodingKey {
        case incomingMessage = "incoming_message"
        case actualReply = "actual_reply"
        case contactName = "contact_name"
        case network
    }
}

struct CloneBenchmarkRequestPayload: Encodable {
    let samples: [CloneBenchmarkSamplePayload]
    let usePersona: Bool
    enum CodingKeys: String, CodingKey {
        case samples
        case usePersona = "use_persona"
    }
}

struct CloneBenchmarkItem: Decodable {
    let incomingMessage: String
    let actualReply: String
    let generatedReply: String
    let match: Bool
    let score: Double
    let reason: String
    enum CodingKeys: String, CodingKey {
        case incomingMessage = "incoming_message"
        case actualReply = "actual_reply"
        case generatedReply = "generated_reply"
        case match
        case score
        case reason
    }
}

struct CloneBenchmarkResult: Decodable {
    let total: Int
    let matched: Int
    let matchRate: Double
    let averageScore: Double
    let items: [CloneBenchmarkItem]
    enum CodingKeys: String, CodingKey {
        case total
        case matched
        case matchRate = "match_rate"
        case averageScore = "average_score"
        case items
    }
}
