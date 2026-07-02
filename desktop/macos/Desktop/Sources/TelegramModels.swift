import Foundation

// MARK: - Helper (subprocess) event decoding
//
// The on-device MTProto helper (telegram-helper/omi_telegram_helper.py) speaks
// newline-delimited JSON. These types decode the events it emits on stdout.

/// One message inside a helper `new_message` thread snapshot.
struct TelegramHelperMessage: Decodable, Sendable {
  let messageID: String
  let text: String
  let isFromMe: Bool
  let timestamp: Date
  let handle: String?  // "tg:<user_id>" of the sender; nil when isFromMe
  var imagePath: String? = nil  // absolute path to a downloaded inline photo, if any

  enum CodingKeys: String, CodingKey {
    case text, timestamp, handle
    case messageID = "message_id"
    case isFromMe = "is_from_me"
    case imagePath = "image_path"
  }
}

/// A normalized thread snapshot the helper emits for each new inbound message.
struct TelegramHelperThread: Decodable, Sendable {
  let chatID: String
  let displayName: String?
  let isGroup: Bool
  let latestMessageID: String
  let awaitingReply: Bool
  let messages: [TelegramHelperMessage]

  enum CodingKeys: String, CodingKey {
    case messages
    case chatID = "chat_id"
    case displayName = "display_name"
    case isGroup = "is_group"
    case latestMessageID = "latest_message_id"
    case awaitingReply = "awaiting_reply"
  }
}

/// The `me` block the helper returns after bootstrap/connect.
struct TelegramHelperMe: Decodable, Sendable {
  let id: Int64
  let username: String?
}

/// A decoded helper event. Only the fields relevant per event are populated.
struct TelegramHelperEvent: Decodable, Sendable {
  let event: String
  let me: TelegramHelperMe?
  let thread: TelegramHelperThread?
  let reason: String?
  let message: String?
  let fatal: Bool?
  let chatID: String?
  let messageID: String?

  enum CodingKeys: String, CodingKey {
    case event, me, thread, reason, message, fatal
    case chatID = "chat_id"
    case messageID = "message_id"
  }
}

// MARK: - Backend API payloads (snake_case matches backend models/telegram.py)

/// Shared ISO8601 formatting. Uses a `Sendable` value-type format style so
/// concurrent `encode(to:)` calls can't race (mirrors IMessagePayloadFormat).
enum TelegramPayloadFormat {
  static let iso = Date.ISO8601FormatStyle(includingFractionalSeconds: true)
  static func string(from date: Date) -> String { iso.format(date) }
}

struct TelegramMessagePayload: Encodable, Sendable {
  let messageID: String
  let text: String
  let isFromMe: Bool
  let timestamp: Date
  let handle: String?

  enum CodingKeys: String, CodingKey {
    case text, timestamp, handle
    case messageID = "message_id"
    case isFromMe = "is_from_me"
  }

  func encode(to encoder: Encoder) throws {
    var c = encoder.container(keyedBy: CodingKeys.self)
    try c.encode(messageID, forKey: .messageID)
    try c.encode(text, forKey: .text)
    try c.encode(isFromMe, forKey: .isFromMe)
    try c.encode(TelegramPayloadFormat.string(from: timestamp), forKey: .timestamp)
    try c.encodeIfPresent(handle, forKey: .handle)
  }
}

struct TelegramThreadPayload: Encodable, Sendable {
  let chatID: String
  let displayName: String?
  let isGroup: Bool
  let messages: [TelegramMessagePayload]

  enum CodingKeys: String, CodingKey {
    case messages
    case chatID = "chat_id"
    case displayName = "display_name"
    case isGroup = "is_group"
  }
}

struct TelegramIngestRequestPayload: Encodable {
  let threads: [TelegramThreadPayload]
  let language: String
}

struct TelegramIngestResponsePayload: Decodable {
  let success: Bool
  let conversationsCreated: Int
  let peopleUpserted: Int
  let messagesIngested: Int
  let skippedDuplicates: Int

  enum CodingKeys: String, CodingKey {
    case success
    case conversationsCreated = "conversations_created"
    case peopleUpserted = "people_upserted"
    case messagesIngested = "messages_ingested"
    case skippedDuplicates = "skipped_duplicates"
  }
}

struct TelegramStatusPayload: Decodable {
  let connected: Bool
  let enabled: Bool
  let conversationsIngested: Int

  enum CodingKeys: String, CodingKey {
    case connected, enabled
    case conversationsIngested = "conversations_ingested"
  }
}

// MARK: - Reply drafting

struct TelegramDraftMessagePayload: Encodable, Sendable {
  let text: String
  let isFromMe: Bool
  var timestamp: Date? = nil

  enum CodingKeys: String, CodingKey {
    case text, timestamp
    case isFromMe = "is_from_me"
  }

  func encode(to encoder: Encoder) throws {
    var c = encoder.container(keyedBy: CodingKeys.self)
    try c.encode(text, forKey: .text)
    try c.encode(isFromMe, forKey: .isFromMe)
    if let timestamp {
      try c.encode(TelegramPayloadFormat.string(from: timestamp), forKey: .timestamp)
    }
  }
}

struct TelegramDraftRequestPayload: Encodable {
  let person: String
  let thread: [TelegramDraftMessagePayload]
  let intent: String?
}

struct TelegramDraftResponsePayload: Decodable {
  let draft: String
  /// True when the person matched more than one contact: `draft` is a
  /// disambiguation ask, not a sendable reply. Defaults false for older backends.
  var ambiguous: Bool = false
}

// MARK: - Display models (inbox UI)

/// One message bubble in a Telegram chat.
struct TelegramChatBubble: Identifiable, Sendable {
  let id: String  // message id
  let text: String
  let isFromMe: Bool
  let date: Date
  let senderName: String?  // shown above bubble in group chats
  var imagePath: String? = nil  // absolute path to an inline photo attachment, if any
}

/// A Telegram conversation with its recent message history.
struct TelegramChat: Identifiable, Sendable {
  var id: String { chatID }
  let chatID: String
  let displayName: String
  let isGroup: Bool
  let personRef: String  // "tg:<user_id>" of the 1:1 partner (or a group label)
  let bubbles: [TelegramChatBubble]  // ascending by date

  var lastDate: Date { bubbles.last?.date ?? .distantPast }
  var lastPreview: String {
    guard let last = bubbles.last else { return "" }
    if !last.text.isEmpty { return last.text }
    return last.imagePath != nil ? "📷 Photo" : ""
  }
  var awaitingReply: Bool { !(bubbles.last?.isFromMe ?? true) }

  /// Recent thread as draft-reply context (last N messages).
  func draftContext(limit: Int = 20) -> [TelegramDraftMessagePayload] {
    bubbles.suffix(limit).map {
      TelegramDraftMessagePayload(text: $0.text, isFromMe: $0.isFromMe, timestamp: $0.date)
    }
  }

  /// The full thread as an ingest payload (all recent bubbles).
  func ingestPayload() -> TelegramThreadPayload {
    let msgs = bubbles.map {
      TelegramMessagePayload(
        messageID: $0.id, text: $0.text, isFromMe: $0.isFromMe, timestamp: $0.date,
        handle: $0.isFromMe ? nil : (isGroup ? nil : personRef))
    }
    return TelegramThreadPayload(
      chatID: chatID, displayName: displayName, isGroup: isGroup, messages: msgs)
  }
}

extension TelegramChat {
  /// Build a display chat from a helper thread snapshot. Sender handles are carried
  /// on each bubble via the payload; the 1:1 partner handle becomes `personRef`.
  init(helperThread t: TelegramHelperThread) {
    let bubbles = t.messages.map {
      TelegramChatBubble(
        id: $0.messageID, text: $0.text, isFromMe: $0.isFromMe, date: $0.timestamp,
        senderName: nil, imagePath: $0.imagePath)
    }
    // The person to resolve server-side: the first non-me sender's tg handle.
    let partner = t.messages.first(where: { !$0.isFromMe && $0.handle != nil })?.handle
    self.init(
      chatID: t.chatID,
      displayName: t.displayName ?? (partner ?? "Telegram chat"),
      isGroup: t.isGroup,
      personRef: partner ?? (t.displayName ?? t.chatID),
      bubbles: bubbles)
  }

  /// Ingest payload that preserves per-message sender handles from a helper thread.
  static func ingestPayload(from t: TelegramHelperThread) -> TelegramThreadPayload {
    let msgs = t.messages.map {
      TelegramMessagePayload(
        messageID: $0.messageID, text: $0.text, isFromMe: $0.isFromMe, timestamp: $0.timestamp,
        handle: $0.isFromMe ? nil : $0.handle)
    }
    return TelegramThreadPayload(
      chatID: t.chatID, displayName: t.displayName, isGroup: t.isGroup, messages: msgs)
  }
}
