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

struct ChatFirstMaterializationRejection: Codable, Equatable, Sendable {
  let intentID: String
  let code: String
  let message: String?

  enum CodingKeys: String, CodingKey {
    case intentID = "intent_id"
    case code, message
  }
}

struct ChatFirstMaterializationDeferral: Codable, Equatable, Sendable {
  let intentID: String
  let code: String

  enum CodingKeys: String, CodingKey {
    case intentID = "intent_id"
    case code
  }
}

enum ChatFirstMaterializationWire {
  static func rejectionMessage(_ message: String) -> String {
    String(message.prefix(300))
  }

  static func encodedRequest(
    ownerID: String,
    controlGeneration: Int,
    windowForeground: Bool,
    receipts: ChatFirstPromptReceiptBatch
  ) throws -> Data {
    try JSONEncoder().encode(
      request(
        ownerID: ownerID,
        controlGeneration: controlGeneration,
        windowForeground: windowForeground,
        receipts: receipts))
  }

  fileprivate static func request(
    ownerID: String,
    controlGeneration: Int,
    windowForeground: Bool,
    receipts: ChatFirstPromptReceiptBatch
  ) -> ChatFirstMaterializePromptsRequest {
    ChatFirstMaterializePromptsRequest(
      controlGeneration: controlGeneration,
      ownerFence: ownerID,
      windowForeground: windowForeground,
      receipts: receipts.materializationReceipts.map {
        ChatFirstMaterializePromptsRequest.Receipt(intentID: $0.intentID, receiptID: $0.receiptID)
      },
      coldStartSequenceTerminalReceipts: receipts.coldStartSequenceTerminalReceipts.map {
        ChatFirstMaterializePromptsRequest.ColdStartSequenceTerminalReceipt(
          sequenceID: $0.sequenceID,
          receiptID: $0.receiptID,
          terminalState: $0.terminalState)
      },
      rejections: receipts.materializationRejections.isEmpty
        ? nil
        : receipts.materializationRejections.map {
          ChatFirstMaterializePromptsRequest.Rejection(
            intentID: $0.intentID,
            code: $0.code,
            message: $0.message.map(rejectionMessage))
        },
      deferrals: receipts.materializationDeferrals.isEmpty
        ? nil
        : receipts.materializationDeferrals.map {
          ChatFirstMaterializePromptsRequest.Deferral(intentID: $0.intentID, code: $0.code)
        })
  }
}

/// A terminal receipt is derived only from the local main-Chat journal after
/// the fixed sparse script completes or the user explicitly abandons it. It
/// is carried beside materialization receipts through the existing server
/// fetch/ack boundary, never persisted as a client rollout preference.
struct ChatFirstColdStartSequenceTerminalReceipt: Codable, Equatable, Sendable {
  enum TerminalState: String, Codable, Sendable {
    case completed
    case abandoned
  }

  let sequenceID: String
  let receiptID: String
  let terminalState: TerminalState

  enum CodingKeys: String, CodingKey {
    case sequenceID = "sequence_id"
    case receiptID = "receipt_id"
    case terminalState = "terminal_state"
  }
}

struct ChatFirstPromptReceiptBatch: Equatable, Sendable {
  let materializationReceipts: [ChatFirstMaterializationReceipt]
  let coldStartSequenceTerminalReceipts: [ChatFirstColdStartSequenceTerminalReceipt]
  let materializationRejections: [ChatFirstMaterializationRejection]
  let materializationDeferrals: [ChatFirstMaterializationDeferral]

  init(
    materializationReceipts: [ChatFirstMaterializationReceipt],
    coldStartSequenceTerminalReceipts: [ChatFirstColdStartSequenceTerminalReceipt],
    materializationRejections: [ChatFirstMaterializationRejection] = [],
    materializationDeferrals: [ChatFirstMaterializationDeferral] = []
  ) {
    self.materializationReceipts = materializationReceipts
    self.coldStartSequenceTerminalReceipts = coldStartSequenceTerminalReceipts
    self.materializationRejections = materializationRejections
    self.materializationDeferrals = materializationDeferrals
  }

  static let empty = Self(materializationReceipts: [], coldStartSequenceTerminalReceipts: [])

  var isEmpty: Bool {
    materializationReceipts.isEmpty && coldStartSequenceTerminalReceipts.isEmpty
      && materializationRejections.isEmpty
      && materializationDeferrals.isEmpty
  }
}

/// The provider vends this only while the root-sampled capability remains
/// admitted for the exact main-Chat owner. It is not a persisted rollout flag.
struct ChatFirstMaterializationContext: Equatable, Sendable {
  let ownerID: String
  let controlGeneration: Int
}

/// Intent blocks are immutable decoded JSON. They are immediately encoded at
/// the runtime boundary rather than shared as mutable Foundation collections.
struct ChatFirstPromptIntent: Codable, @unchecked Sendable {
  enum Source: String, Codable, Sendable {
    case dailyOpener = "daily_opener"
    case captureArrival = "capture_arrival"
    case deferralReraise = "deferral_reraise"
    case agentJudgment = "agent_judgment"
    case coldStartRich = "cold_start_rich"
    case coldStartSparse = "cold_start_sparse"
  }

  let intentID: String
  let continuityKey: String
  let accountGeneration: Int
  let source: Source
  let blocks: [OmiAnyCodable]

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

struct ChatFirstMaterializePromptsResponse: Decodable, @unchecked Sendable {
  let intents: [ChatFirstPromptIntent]
}

/// The coordinator consumes this narrow driver rather than owning an API
/// client, journal, or cache. It keeps the production flow testable while the
/// ChatProvider remains the sole Swift projection of the kernel transcript.
@MainActor
protocol ChatFirstPromptMaterializationDriving: AnyObject {
  func materializationContext() -> ChatFirstMaterializationContext?
  func pendingReceipts() async throws -> ChatFirstPromptReceiptBatch
  func fetchPrompts(
    ownerID: String,
    controlGeneration: Int,
    windowForeground: Bool,
    receipts: ChatFirstPromptReceiptBatch
  ) async throws -> ChatFirstMaterializePromptsResponse
  func acknowledge(_ receipts: ChatFirstPromptReceiptBatch) async throws
  func materialize(_ intents: [ChatFirstPromptIntent]) async throws
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

  struct ColdStartSequenceTerminalReceipt: Encodable {
    let sequenceID: String
    let receiptID: String
    let terminalState: ChatFirstColdStartSequenceTerminalReceipt.TerminalState

    enum CodingKeys: String, CodingKey {
      case sequenceID = "sequence_id"
      case receiptID = "receipt_id"
      case terminalState = "terminal_state"
    }
  }

  struct Rejection: Encodable {
    let intentID: String
    let code: String
    let message: String?

    enum CodingKeys: String, CodingKey {
      case intentID = "intent_id"
      case code, message
    }
  }

  struct Deferral: Encodable {
    let intentID: String
    let code: String
    enum CodingKeys: String, CodingKey {
      case intentID = "intent_id"
      case code
    }
  }

  let sourceSurface: String = "main_chat"
  let controlGeneration: Int
  let ownerFence: String
  let windowForeground: Bool
  let initialPageLoaded: Bool = true
  let receipts: [Receipt]
  let coldStartSequenceTerminalReceipts: [ColdStartSequenceTerminalReceipt]
  let rejections: [Rejection]?
  let deferrals: [Deferral]?

  enum CodingKeys: String, CodingKey {
    case sourceSurface = "source_surface"
    case controlGeneration = "control_generation"
    case ownerFence = "owner_fence"
    case windowForeground = "window_foreground"
    case initialPageLoaded = "initial_page_loaded"
    case receipts
    case coldStartSequenceTerminalReceipts = "cold_start_sequence_terminal_receipts"
    case rejections
    case deferrals
  }
}

extension APIClient {
  func materializeChatFirstPrompts(
    ownerID: String,
    controlGeneration: Int,
    windowForeground: Bool,
    receipts: ChatFirstPromptReceiptBatch
  ) async throws -> ChatFirstMaterializePromptsResponse {
    guard !ownerID.isEmpty,
      controlGeneration >= 0,
      receipts.materializationReceipts.count <= 16,
      receipts.coldStartSequenceTerminalReceipts.count <= 16,
      receipts.materializationRejections.count <= 16, receipts.materializationDeferrals.count <= 16
    else {
      throw APIError.invalidResponse
    }
    let body = ChatFirstMaterializationWire.request(
      ownerID: ownerID,
      controlGeneration: controlGeneration,
      windowForeground: windowForeground,
      receipts: receipts
    )
    do {
      return try await post(
        "v2/chat/materialize-prompts",
        body: body,
        includeBYOK: false,
        expectedOwnerId: ownerID
      )
    } catch {
      // Desktop Beta/Stable artifacts can outlive the independently deployed
      // Python backend. A missing v2 route is the one safe compatibility case:
      // the released v1 contract returns the legacy block union and therefore
      // intentionally omits meeting-link blocks, while preserving questions,
      // tasks, goals, and captures. Do not hide auth, generation, or transient
      // failures behind a second request.
      guard ChatFirstMaterializationEndpointPolicy.shouldFallbackToV1(for: error) else {
        throw error
      }
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "chat_first_materialization",
        from: "v2",
        to: "v1",
        reason: "v2_route_missing",
        outcome: .degraded)
      log("Chat-first v2 materialization unavailable; retrying released v1 contract")
      return try await post(
        "v1/chat/materialize-prompts",
        body: body,
        includeBYOK: false,
        expectedOwnerId: ownerID
      )
    }
  }
}

enum ChatFirstMaterializationEndpointPolicy {
  static func shouldFallbackToV1(for error: Error) -> Bool {
    guard let apiError = error as? APIError else { return false }
    if case .httpError(let statusCode, _) = apiError {
      return statusCode == 404
    }
    return false
  }
}
