import Foundation

/// Typed wire contract for T04's fetch/ack endpoint. The server owns due
/// timing and content; desktop only reports presence and commits receipts to
/// its one local journal.
struct ChatFirstMaterializationReceipt: Codable, Equatable, Sendable {
  let intentID: String
  let receiptID: String

  enum CodingKeys: String, CodingKey {
    case intentID = "intent_id"
    case receiptID = "receipt_id"
  }
}

/// The provider vends this only while the root-sampled capability remains
/// admitted for the exact main-Chat owner. It is not a persisted rollout flag.
struct ChatFirstMaterializationContext: Equatable, Sendable {
  let ownerID: String
  let controlGeneration: Int
}

struct ChatFirstPromptIntent: Decodable {
  enum Source: String, Decodable, Sendable {
    case dailyOpener = "daily_opener"
    case captureArrival = "capture_arrival"
    case deferralReraise = "deferral_reraise"
    case agentJudgment = "agent_judgment"
  }

  let intentID: String
  let continuityKey: String
  let accountGeneration: Int
  let source: Source
  let blocks: [OmiAPI.OmiAnyCodable]

  enum CodingKeys: String, CodingKey {
    case intentID = "intent_id"
    case continuityKey = "continuity_key"
    case accountGeneration = "account_generation"
    case source, blocks
  }

  /// The kernel performs the bounded schema conversion and only it assigns
  /// persisted block IDs. Refuse an incomplete server response before it can
  /// become a journal mutation.
  var kernelBlocks: [[String: Any]]? {
    let values = blocks.compactMap { $0.value as? [String: Any] }
    return values.count == blocks.count && !values.isEmpty ? values : nil
  }
}

struct ChatFirstMaterializePromptsResponse: Decodable {
  let intents: [ChatFirstPromptIntent]
}

private struct ChatFirstMaterializePromptsRequest: Encodable {
  struct Receipt: Encodable {
    let intentID: String
    let receiptID: String

    enum CodingKeys: String, CodingKey {
      case intentID = "intent_id"
      case receiptID = "receipt_id"
    }
  }

  let sourceSurface: String = "main_chat"
  let controlGeneration: Int
  let ownerFence: String
  let windowForeground: Bool
  let receipts: [Receipt]

  enum CodingKeys: String, CodingKey {
    case sourceSurface = "source_surface"
    case controlGeneration = "control_generation"
    case ownerFence = "owner_fence"
    case windowForeground = "window_foreground"
    case receipts
  }
}

extension APIClient {
  func materializeChatFirstPrompts(
    ownerID: String,
    controlGeneration: Int,
    windowForeground: Bool,
    receipts: [ChatFirstMaterializationReceipt]
  ) async throws -> ChatFirstMaterializePromptsResponse {
    guard !ownerID.isEmpty, controlGeneration >= 0, receipts.count <= 16 else {
      throw APIError.invalidResponse
    }
    let body = ChatFirstMaterializePromptsRequest(
      controlGeneration: controlGeneration,
      ownerFence: ownerID,
      windowForeground: windowForeground,
      receipts: receipts.map {
        ChatFirstMaterializePromptsRequest.Receipt(intentID: $0.intentID, receiptID: $0.receiptID)
      }
    )
    return try await post(
      "v1/chat/materialize-prompts",
      body: body,
      includeBYOK: false,
      expectedOwnerId: ownerID
    )
  }
}
