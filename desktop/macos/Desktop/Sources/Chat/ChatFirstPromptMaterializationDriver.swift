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

  static let empty = Self(materializationReceipts: [], coldStartSequenceTerminalReceipts: [])

  var isEmpty: Bool {
    materializationReceipts.isEmpty && coldStartSequenceTerminalReceipts.isEmpty
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

struct ChatFirstMaterializePromptsResponse: Decodable {
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

/// One presence-triggered fetch/ack/materialize pass. The local receipt is
/// removed only after the server fetch accepted it; an acknowledgement failure
/// leaves the kernel receipt available for the next attempt.
@MainActor
enum ChatFirstPromptMaterializationRunner {
  static func run(
    driver: any ChatFirstPromptMaterializationDriving,
    context: ChatFirstMaterializationContext,
    windowForeground: Bool,
    isCurrent: @escaping @MainActor () -> Bool
  ) async throws {
    guard isCurrent() else { return }
    let pendingReceipts = try await driver.pendingReceipts()
    guard isCurrent() else { return }
    let response = try await driver.fetchPrompts(
      ownerID: context.ownerID,
      controlGeneration: context.controlGeneration,
      windowForeground: windowForeground,
      receipts: pendingReceipts
    )
    guard isCurrent() else { return }
    if !pendingReceipts.isEmpty {
      try await driver.acknowledge(pendingReceipts)
      guard isCurrent() else { return }
    }
    guard response.intents.allSatisfy({ $0.accountGeneration == context.controlGeneration }) else { return }
    try await driver.materialize(response.intents)
  }
}

@MainActor
final class APIChatFirstPromptMaterializationDriver: ChatFirstPromptMaterializationDriving {
  private weak var chatProvider: ChatProvider?

  init(chatProvider: ChatProvider) {
    self.chatProvider = chatProvider
  }

  func materializationContext() -> ChatFirstMaterializationContext? {
    chatProvider?.chatFirstMaterializationContext()
  }

  func pendingReceipts() async throws -> ChatFirstPromptReceiptBatch {
    guard let chatProvider else { return .empty }
    return try await chatProvider.pendingChatFirstMaterializationReceipts()
  }

  func fetchPrompts(
    ownerID: String,
    controlGeneration: Int,
    windowForeground: Bool,
    receipts: ChatFirstPromptReceiptBatch
  ) async throws -> ChatFirstMaterializePromptsResponse {
    try await APIClient.shared.materializeChatFirstPrompts(
      ownerID: ownerID,
      controlGeneration: controlGeneration,
      windowForeground: windowForeground,
      receipts: receipts
    )
  }

  func acknowledge(_ receipts: ChatFirstPromptReceiptBatch) async throws {
    guard let chatProvider else { return }
    _ = try await chatProvider.acknowledgeChatFirstMaterializationReceipts(receipts)
  }

  func materialize(_ intents: [ChatFirstPromptIntent]) async throws {
    guard let chatProvider else { return }
    _ = try await chatProvider.materializeChatFirstIntents(intents)
  }
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

  let sourceSurface: String = "main_chat"
  let controlGeneration: Int
  let ownerFence: String
  let windowForeground: Bool
  let initialPageLoaded: Bool = true
  let receipts: [Receipt]
  let coldStartSequenceTerminalReceipts: [ColdStartSequenceTerminalReceipt]

  enum CodingKeys: String, CodingKey {
    case sourceSurface = "source_surface"
    case controlGeneration = "control_generation"
    case ownerFence = "owner_fence"
    case windowForeground = "window_foreground"
    case initialPageLoaded = "initial_page_loaded"
    case receipts
    case coldStartSequenceTerminalReceipts = "cold_start_sequence_terminal_receipts"
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
      receipts.coldStartSequenceTerminalReceipts.count <= 16
    else {
      throw APIError.invalidResponse
    }
    let body = ChatFirstMaterializePromptsRequest(
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
          terminalState: $0.terminalState
        )
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
