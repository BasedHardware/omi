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
  var avatarPath: String? = nil  // absolute path to the chat's downloaded profile photo

  enum CodingKeys: String, CodingKey {
    case messages
    case chatID = "chat_id"
    case displayName = "display_name"
    case isGroup = "is_group"
    case latestMessageID = "latest_message_id"
    case awaitingReply = "awaiting_reply"
    case avatarPath = "avatar_path"
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
  // True only when the backend durably persisted every window. Telegram events are
  // the sole source of these payloads, so on a partial persist the client retries
  // the ingest rather than dropping the un-stored messages.
  let allPersisted: Bool

  enum CodingKeys: String, CodingKey {
    case success
    case conversationsCreated = "conversations_created"
    case peopleUpserted = "people_upserted"
    case messagesIngested = "messages_ingested"
    case skippedDuplicates = "skipped_duplicates"
    case allPersisted = "all_persisted"
  }

  // Tolerant decode: allPersisted defaults to true when absent so an older backend
  // (no field) is treated as fully persisted rather than retried forever.
  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    success = (try? c.decode(Bool.self, forKey: .success)) ?? true
    conversationsCreated = (try? c.decode(Int.self, forKey: .conversationsCreated)) ?? 0
    peopleUpserted = (try? c.decode(Int.self, forKey: .peopleUpserted)) ?? 0
    messagesIngested = (try? c.decode(Int.self, forKey: .messagesIngested)) ?? 0
    skippedDuplicates = (try? c.decode(Int.self, forKey: .skippedDuplicates)) ?? 0
    allPersisted = (try? c.decodeIfPresent(Bool.self, forKey: .allPersisted)) ?? true
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
  var sender: String? = nil  // group-chat sender name/handle; lets the backend attribute messages
  var imageB64: String? = nil  // downscaled JPEG of an inline photo, for the backend's vision step
  var timestamp: Date? = nil

  enum CodingKeys: String, CodingKey {
    case text, timestamp, sender
    case isFromMe = "is_from_me"
    case imageB64 = "image_b64"
  }

  func encode(to encoder: Encoder) throws {
    var c = encoder.container(keyedBy: CodingKeys.self)
    try c.encode(text, forKey: .text)
    try c.encode(isFromMe, forKey: .isFromMe)
    try c.encodeIfPresent(sender, forKey: .sender)
    try c.encodeIfPresent(imageB64, forKey: .imageB64)
    if let timestamp {
      try c.encode(TelegramPayloadFormat.string(from: timestamp), forKey: .timestamp)
    }
  }
}

struct TelegramDraftRequestPayload: Encodable {
  let person: String
  let thread: [TelegramDraftMessagePayload]
  let intent: String?
  var isGroup: Bool = false

  enum CodingKeys: String, CodingKey {
    case person, thread, intent
    case isGroup = "is_group"
  }
}

struct TelegramDraftResponsePayload: Decodable {
  let draft: String
  /// True when the person matched more than one contact: `draft` is a
  /// disambiguation ask, not a sendable reply. Defaults false for older backends.
  var ambiguous: Bool = false
  /// True when the drafter judged the latest group message wasn't directed at the
  /// user: `draft` is empty and no draft should be shown. Defaults false.
  var abstain: Bool = false
  /// True when the message needs the user rather than an auto-sent reply (asks
  /// something we can't answer truthfully, needs the user's decision, or requests
  /// sensitive info). `draft` is a best-guess SUGGESTION — never auto-send it;
  /// surface it for review and notify the user. Defaults false for older backends.
  var needsInput: Bool = false
  /// Short, user-facing reason for the escalation (e.g. "They want to lock in a time").
  var needsInputReason: String?
  /// Set when the reply accepted a proposed time: a tentative calendar hold was created
  /// that the user can confirm or discard. Nil when the reply didn't commit to a time.
  var hold: DraftHold?

  enum CodingKeys: String, CodingKey {
    case draft, ambiguous, abstain, hold
    case needsInput = "needs_input"
    case needsInputReason = "needs_input_reason"
  }

  // Swift's synthesized Decodable ignores property defaults and would throw
  // `keyNotFound` when an older backend omits `ambiguous`/`abstain`. Decode them
  // as optional-with-fallback so responses without the fields still parse.
  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    draft = try c.decode(String.self, forKey: .draft)
    ambiguous = try c.decodeIfPresent(Bool.self, forKey: .ambiguous) ?? false
    abstain = try c.decodeIfPresent(Bool.self, forKey: .abstain) ?? false
    needsInput = try c.decodeIfPresent(Bool.self, forKey: .needsInput) ?? false
    needsInputReason = try c.decodeIfPresent(String.self, forKey: .needsInputReason)
    hold = try? c.decodeIfPresent(DraftHold.self, forKey: .hold)
  }
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
  var avatarImageData: Data? = nil  // chat/user profile photo

  var lastDate: Date { bubbles.last?.date ?? .distantPast }
  var lastPreview: String {
    guard let last = bubbles.last else { return "" }
    if !last.text.isEmpty { return last.text }
    return last.imagePath != nil ? "📷 Photo" : ""
  }
  var awaitingReply: Bool { !(bubbles.last?.isFromMe ?? true) }

  /// Recent thread as draft-reply context (last N messages). In group chats each
  /// incoming bubble carries its sender so the backend can attribute messages and
  /// judge whether the user is actually being addressed. The last few inline photos
  /// are downscaled + base64-encoded so the backend can actually see them.
  func draftContext(limit: Int = 20) -> [TelegramDraftMessagePayload] {
    let recent = Array(bubbles.suffix(limit))
    let imageIDs = Set(recent.filter { $0.imagePath != nil }.suffix(2).map { $0.id })
    return recent.map { b in
      let img = imageIDs.contains(b.id) ? b.imagePath.flatMap { MessagingMedia.base64JPEG(path: $0) } : nil
      return TelegramDraftMessagePayload(
        text: b.text, isFromMe: b.isFromMe,
        sender: isGroup ? b.senderName : nil, imageB64: img, timestamp: b.date)
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
    let avatar: Data? = {
      guard let p = t.avatarPath, !p.isEmpty, FileManager.default.fileExists(atPath: p) else {
        return nil
      }
      return try? Data(contentsOf: URL(fileURLWithPath: p))
    }()
    self.init(
      chatID: t.chatID,
      displayName: t.displayName ?? (partner ?? "Telegram chat"),
      isGroup: t.isGroup,
      personRef: partner ?? (t.displayName ?? t.chatID),
      bubbles: bubbles,
      avatarImageData: avatar)
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
