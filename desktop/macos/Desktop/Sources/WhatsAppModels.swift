import Foundation

/// A single text message read from the local WhatsApp database (`ChatStorage.sqlite`).
///
/// WhatsApp stores `ZTEXT` as plain text (unlike iMessage's `attributedBody`), so
/// there's no decoder step. Handles are phone numbers (`<digits>@s.whatsapp.net`)
/// or opaque `<id>@lid` JIDs — see `WhatsAppReaderService` for the canonicalization
/// rules that produce `handle`.
struct WhatsAppRecord: Sendable {
  let rowid: Int64  // ZWAMESSAGE.Z_PK — the client-side sync cursor
  let messageId: String  // ZSTANZAID
  let text: String  // ZTEXT (plain)
  let isFromMe: Bool
  let date: Date
  let handle: String?  // sender phone/opaque JID; nil when isFromMe
  let chatID: String  // full ZCONTACTJID of the session (e.g. `<digits>@s.whatsapp.net`, `<id>@g.us`)
  let chatDisplayName: String?  // ZPARTNERNAME (contact name for 1:1, subject for groups)
  let isGroup: Bool
  let senderName: String?  // group member display name, shown above the bubble in groups
  var imagePath: String? = nil  // absolute path to an image attachment (ZMESSAGETYPE=1), if any
}

// MARK: - API payloads (snake_case matches backend models/whatsapp.py)

/// Shared ISO8601 formatting for WhatsApp payloads. Timestamps are emitted as
/// ISO8601 strings because APIClient's shared JSONEncoder encodes `Date` as a
/// reference-date double, which the backend would misread.
///
/// Uses `Date.ISO8601FormatStyle` — a `Sendable` value type — rather than a
/// shared `ISO8601DateFormatter` (a non-Sendable reference type with no internal
/// locking), so concurrent `encode(to:)` calls from sync/reply tasks can't race
/// on it.
enum WhatsAppPayloadFormat {
  static let iso = Date.ISO8601FormatStyle(includingFractionalSeconds: true)

  static func string(from date: Date) -> String { iso.format(date) }
}

/// `timestamp` is stored as a `Date` so callers can't accidentally pass a
/// localized or non-ISO string; a custom `encode(to:)` emits the stable ISO8601
/// string regardless of the shared encoder's date strategy.
struct WhatsAppMessagePayload: Encodable {
  let messageId: String
  let text: String
  let isFromMe: Bool
  let timestamp: Date
  let handle: String?

  enum CodingKeys: String, CodingKey {
    case text, timestamp, handle
    case messageId = "message_id"
    case isFromMe = "is_from_me"
  }

  func encode(to encoder: Encoder) throws {
    var c = encoder.container(keyedBy: CodingKeys.self)
    try c.encode(messageId, forKey: .messageId)
    try c.encode(text, forKey: .text)
    try c.encode(isFromMe, forKey: .isFromMe)
    try c.encode(WhatsAppPayloadFormat.string(from: timestamp), forKey: .timestamp)
    try c.encodeIfPresent(handle, forKey: .handle)
  }
}

struct WhatsAppThreadPayload: Encodable {
  let chatID: String
  let displayName: String?
  let isGroup: Bool
  let messages: [WhatsAppMessagePayload]

  enum CodingKeys: String, CodingKey {
    case messages
    case chatID = "chat_id"
    case displayName = "display_name"
    case isGroup = "is_group"
  }
}

/// Ingest request. Unlike iMessage, the Z_PK cursor stays entirely client-side in
/// UserDefaults, so there is no `last_rowid` field on the wire.
struct WhatsAppIngestRequestPayload: Encodable {
  let threads: [WhatsAppThreadPayload]
  let language: String
}

struct WhatsAppIngestResponsePayload: Decodable {
  let success: Bool
  let conversationsCreated: Int
  let peopleUpserted: Int
  let messagesIngested: Int
  let skippedDuplicates: Int
  // True only when the backend durably persisted every window. The coordinator
  // advances its Z_PK cursor only when this is true, so a partial persist failure
  // re-sends the batch next sync instead of skipping (and losing) those messages.
  let allPersisted: Bool

  enum CodingKeys: String, CodingKey {
    case success
    case conversationsCreated = "conversations_created"
    case peopleUpserted = "people_upserted"
    case messagesIngested = "messages_ingested"
    case skippedDuplicates = "skipped_duplicates"
    case allPersisted = "all_persisted"
  }

  // Tolerant decode so a partial/older backend response can't fail the whole sync.
  // allPersisted defaults to true when absent so an older backend (no field) never
  // wedges the cursor.
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

struct WhatsAppStatusPayload: Decodable {
  let connected: Bool
  let enabled: Bool
  let conversationsIngested: Int

  enum CodingKeys: String, CodingKey {
    case connected, enabled
    case conversationsIngested = "conversations_ingested"
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    connected = (try? c.decode(Bool.self, forKey: .connected)) ?? false
    enabled = (try? c.decode(Bool.self, forKey: .enabled)) ?? false
    conversationsIngested = (try? c.decode(Int.self, forKey: .conversationsIngested)) ?? 0
  }
}

// MARK: - Settings

/// Server-side connector settings. Round-trips through GET/PUT `/v1/whatsapp/settings`.
struct WhatsAppSettingsPayload: Codable {
  var enabled: Bool
  var optedOutHandles: [String]
  var backfillDays: Int

  enum CodingKeys: String, CodingKey {
    case enabled
    case optedOutHandles = "opted_out_handles"
    case backfillDays = "backfill_days"
  }

  init(enabled: Bool, optedOutHandles: [String] = [], backfillDays: Int = 90) {
    self.enabled = enabled
    self.optedOutHandles = optedOutHandles
    self.backfillDays = backfillDays
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    enabled = (try? c.decode(Bool.self, forKey: .enabled)) ?? true
    optedOutHandles = (try? c.decode([String].self, forKey: .optedOutHandles)) ?? []
    backfillDays = (try? c.decode(Int.self, forKey: .backfillDays)) ?? 90
  }
}

/// Minimal success envelope for endpoints that return no useful body (disconnect).
struct WhatsAppSimpleOK: Decodable {
  let success: Bool

  init(from decoder: Decoder) throws {
    let c = try? decoder.container(keyedBy: CodingKeys.self)
    success = (try? c?.decode(Bool.self, forKey: .success)) ?? true
  }

  enum CodingKeys: String, CodingKey { case success }
}

// MARK: - Contact sync

struct WhatsAppContactsSyncResponsePayload: Decodable {
  let success: Bool
  let peopleUpserted: Int

  enum CodingKeys: String, CodingKey {
    case success
    case peopleUpserted = "people_upserted"
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    success = (try? c.decode(Bool.self, forKey: .success)) ?? true
    peopleUpserted = (try? c.decode(Int.self, forKey: .peopleUpserted)) ?? 0
  }
}

// MARK: - Reply drafting

struct WhatsAppDraftMessagePayload: Encodable, Sendable {
  let text: String
  let isFromMe: Bool
  var sender: String? = nil  // group-chat sender name/handle; lets the backend attribute messages
  var imageB64: String? = nil  // downscaled JPEG of an inline photo, for the backend's vision step
  var timestamp: Date? = nil  // send time; lets the backend order the thread deterministically

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
      try c.encode(WhatsAppPayloadFormat.string(from: timestamp), forKey: .timestamp)
    }
  }
}

struct WhatsAppDraftRequestPayload: Encodable {
  let person: String
  let thread: [WhatsAppDraftMessagePayload]
  let intent: String?
  var isGroup: Bool = false

  enum CodingKeys: String, CodingKey {
    case person, thread, intent
    case isGroup = "is_group"
  }
}

struct WhatsAppDraftResponsePayload: Decodable {
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

  // Decode each field with a fallback so responses that omit `ambiguous`/`abstain`
  // still parse (Swift's synthesized Decodable would throw keyNotFound instead of
  // using the property default). Previously `abstain` was left out of CodingKeys
  // entirely, so a backend abstain signal was silently ignored.
  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    draft = (try? c.decode(String.self, forKey: .draft)) ?? ""
    ambiguous = (try? c.decode(Bool.self, forKey: .ambiguous)) ?? false
    abstain = (try? c.decode(Bool.self, forKey: .abstain)) ?? false
    needsInput = (try? c.decode(Bool.self, forKey: .needsInput)) ?? false
    needsInputReason = try? c.decode(String.self, forKey: .needsInputReason)
    hold = try? c.decodeIfPresent(DraftHold.self, forKey: .hold)
  }
}

/// A thread whose latest message is inbound (awaiting a reply), shown in the inbox.
struct WhatsAppInboxThread: Identifiable, Sendable {
  var id: String { chatID }
  let chatID: String
  let displayName: String
  let lastMessage: String
  let lastDate: Date
  let personRef: String  // handle or name used to resolve the person server-side
  let context: [WhatsAppDraftMessagePayload]
}

// MARK: - Full chat view (native WhatsApp-style tab)

/// One message bubble in a chat.
struct WhatsAppChatBubble: Identifiable, Sendable {
  let id: String  // message id
  let text: String
  let isFromMe: Bool
  let date: Date
  let senderName: String?  // shown above bubble in group chats
  var senderImage: Data? = nil  // group sender's contact photo
  var imagePath: String? = nil  // absolute path to an inline image attachment, if any
}

/// A full conversation with its recent message history.
struct WhatsAppChat: Identifiable, Sendable {
  var id: String { chatID }
  let chatID: String
  let displayName: String
  let isGroup: Bool
  let personRef: String
  let bubbles: [WhatsAppChatBubble]  // ascending by date
  var avatarImageData: Data? = nil  // 1:1 contact photo
  var dialablePhone: String? = nil  // digits for the whatsapp:// send deep link (1:1 only)

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
  func draftContext(limit: Int = 20) -> [WhatsAppDraftMessagePayload] {
    let recent = Array(bubbles.suffix(limit))
    let imageIDs = Set(recent.filter { $0.imagePath != nil }.suffix(2).map { $0.id })
    return recent.map { b in
      let img = imageIDs.contains(b.id) ? b.imagePath.flatMap { MessagingMedia.base64JPEG(path: $0) } : nil
      return WhatsAppDraftMessagePayload(
        text: b.text, isFromMe: b.isFromMe,
        sender: isGroup ? b.senderName : nil, imageB64: img, timestamp: b.date)
    }
  }
}
