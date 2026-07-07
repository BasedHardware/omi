import Foundation

/// A single decoded message read from the local Messages database.
struct IMessageRecord: Sendable {
  let rowid: Int64
  let guid: String
  let text: String  // decoded body text; may be empty for attachment-only messages
  let isFromMe: Bool
  let date: Date
  let handle: String?  // sender phone/email; nil when isFromMe
  let chatGUID: String
  let chatIdentifier: String?
  let chatDisplayName: String?
  let hasAttachment: Bool  // true when the message carries an attachment (photo, video, etc.)
}

// MARK: - API payloads (snake_case matches backend models/imessage.py)

/// Shared ISO8601 formatting for iMessage payloads. Timestamps are emitted as
/// ISO8601 strings because APIClient's shared JSONEncoder encodes `Date` as a
/// reference-date double, which the backend would misread.
///
/// Uses `Date.ISO8601FormatStyle` — a `Sendable` value type — rather than a
/// shared `ISO8601DateFormatter` (a non-Sendable reference type with no internal
/// locking), so concurrent `encode(to:)` calls from sync/reply tasks can't race
/// on it. Output is identical: internet date-time with fractional seconds in UTC.
enum IMessagePayloadFormat {
  static let iso = Date.ISO8601FormatStyle(includingFractionalSeconds: true)

  static func string(from date: Date) -> String { iso.format(date) }
}

// Precision note: `timestamp` is millisecond-resolution, while chat.db dates are
// nanosecond. Two messages in the same millisecond can therefore tie on the wire.
// This is intentionally accepted, not a bug: the client emits the thread in true
// chronological (ROWID) order, and the backend's `_order_thread` uses a STABLE sort
// keyed on timestamp — so equal-timestamp messages keep the client's correct relative
// order. If a strict monotonic key is ever needed, add rowid/guid as a secondary sort.

/// `timestamp` is stored as a `Date` so callers can't accidentally pass a
/// localized or non-ISO string; a custom `encode(to:)` emits the stable ISO8601
/// string regardless of the shared encoder's date strategy.
struct IMessageMessagePayload: Encodable {
  let guid: String
  let text: String
  let isFromMe: Bool
  let timestamp: Date
  let handle: String?

  enum CodingKeys: String, CodingKey {
    case guid, text, timestamp, handle
    case isFromMe = "is_from_me"
  }

  func encode(to encoder: Encoder) throws {
    var c = encoder.container(keyedBy: CodingKeys.self)
    try c.encode(guid, forKey: .guid)
    try c.encode(text, forKey: .text)
    try c.encode(isFromMe, forKey: .isFromMe)
    try c.encode(IMessagePayloadFormat.string(from: timestamp), forKey: .timestamp)
    try c.encodeIfPresent(handle, forKey: .handle)
  }
}

struct IMessageThreadPayload: Encodable {
  let chatGUID: String
  let chatIdentifier: String?
  let displayName: String?
  let isGroup: Bool
  let messages: [IMessageMessagePayload]

  enum CodingKeys: String, CodingKey {
    case messages
    case chatGUID = "chat_guid"
    case chatIdentifier = "chat_identifier"
    case displayName = "display_name"
    case isGroup = "is_group"
  }
}

struct IMessageIngestRequestPayload: Encodable {
  let threads: [IMessageThreadPayload]
  let language: String
  let lastRowid: Int64?

  enum CodingKeys: String, CodingKey {
    case threads, language
    case lastRowid = "last_rowid"
  }
}

struct IMessageIngestResponsePayload: Decodable {
  let success: Bool
  let conversationsCreated: Int
  let peopleUpserted: Int
  let messagesIngested: Int
  let skippedDuplicates: Int
  /// True only when every window persisted durably. When false, the sync coordinator
  /// must NOT advance its ROWID cursor past this batch (the failed messages must be
  /// resent). Defaults true so an older backend that omits the field keeps working.
  let allPersisted: Bool

  enum CodingKeys: String, CodingKey {
    case success
    case conversationsCreated = "conversations_created"
    case peopleUpserted = "people_upserted"
    case messagesIngested = "messages_ingested"
    case skippedDuplicates = "skipped_duplicates"
    case allPersisted = "all_persisted"
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    success = try c.decodeIfPresent(Bool.self, forKey: .success) ?? true
    conversationsCreated = try c.decodeIfPresent(Int.self, forKey: .conversationsCreated) ?? 0
    peopleUpserted = try c.decodeIfPresent(Int.self, forKey: .peopleUpserted) ?? 0
    messagesIngested = try c.decodeIfPresent(Int.self, forKey: .messagesIngested) ?? 0
    skippedDuplicates = try c.decodeIfPresent(Int.self, forKey: .skippedDuplicates) ?? 0
    allPersisted = try c.decodeIfPresent(Bool.self, forKey: .allPersisted) ?? true
  }
}

struct IMessageStatusPayload: Decodable {
  let connected: Bool
  let enabled: Bool
  let lastRowid: Int64?
  let conversationsIngested: Int

  enum CodingKeys: String, CodingKey {
    case connected, enabled
    case lastRowid = "last_rowid"
    case conversationsIngested = "conversations_ingested"
  }
}

// MARK: - Contact sync

/// One contact from the local macOS address book, POSTed so the backend can
/// create/update People keyed by phone/email. Handles are sent raw (phone
/// strings and emails as-is); the backend canonicalizes them.
struct IMessageContactSyncPayload: Encodable, Sendable {
  let name: String
  let handles: [String]
}

struct IMessageContactsSyncRequestPayload: Encodable {
  let contacts: [IMessageContactSyncPayload]
}

struct IMessageContactsSyncResponsePayload: Decodable {
  let success: Bool
  let peopleUpserted: Int

  enum CodingKeys: String, CodingKey {
    case success
    case peopleUpserted = "people_upserted"
  }
}

// MARK: - Reply drafting

struct IMessageDraftMessagePayload: Encodable, Sendable {
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
      try c.encode(IMessagePayloadFormat.string(from: timestamp), forKey: .timestamp)
    }
  }
}

struct IMessageDraftRequestPayload: Encodable {
  let person: String
  let thread: [IMessageDraftMessagePayload]
  let intent: String?
  var isGroup: Bool = false

  enum CodingKeys: String, CodingKey {
    case person, thread, intent
    case isGroup = "is_group"
  }
}

struct IMessageDraftResponsePayload: Decodable {
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

/// A thread whose latest message is inbound (awaiting a reply), shown in the Replies inbox.
struct IMessageInboxThread: Identifiable, Sendable {
  var id: String { chatGUID }
  let chatGUID: String
  let displayName: String
  let lastMessage: String
  let lastDate: Date
  let personRef: String  // handle or name used to resolve the person server-side
  let context: [IMessageDraftMessagePayload]
}

// MARK: - Full chat view (native iMessage-style Messages tab)

/// One message bubble in a chat.
struct IMessageChatBubble: Identifiable, Sendable {
  let id: String  // message guid
  let text: String
  let isFromMe: Bool
  let date: Date
  let senderName: String?  // shown above bubble in group chats
  var senderImage: Data? = nil  // group sender's contact photo
  var attachmentPath: String? = nil  // resolved file path if this message is an attachment
  var attachmentMime: String? = nil  // e.g. "image/jpeg", "video/quicktime"
  /// True when `text` is a synthesized attachment placeholder ("📷 Photo", etc.) rather
  /// than real message text, so the UI can suppress it without string-matching (which
  /// would also drop a genuine user caption that happens to equal a placeholder).
  var isPlaceholderText: Bool = false
}

/// A full conversation with its recent message history.
struct IMessageChat: Identifiable, Sendable {
  var id: String { chatGUID }
  let chatGUID: String
  let displayName: String
  let isGroup: Bool
  let personRef: String
  let bubbles: [IMessageChatBubble]  // ascending by date
  var avatarImageData: Data? = nil  // 1:1 contact photo

  var lastDate: Date { bubbles.last?.date ?? .distantPast }
  var lastPreview: String { bubbles.last?.text ?? "" }
  var awaitingReply: Bool { !(bubbles.last?.isFromMe ?? true) }

  /// Recent thread as draft-reply context (last N messages). In group chats each
  /// incoming bubble carries its sender so the backend can attribute messages and
  /// judge whether the user is actually being addressed. The last few inline photos
  /// are downscaled + base64-encoded so the backend can actually see them.
  func draftContext(limit: Int = 20) -> [IMessageDraftMessagePayload] {
    let recent = Array(bubbles.suffix(limit))
    // Encode at most the last 2 images to bound the request size.
    let imageIDs = Set(
      recent
        .filter { ($0.attachmentMime?.hasPrefix("image/") ?? false) && $0.attachmentPath != nil }
        .suffix(2).map { $0.id })
    return recent.map { b in
      let img = imageIDs.contains(b.id) ? b.attachmentPath.flatMap { MessagingMedia.base64JPEG(path: $0) } : nil
      return IMessageDraftMessagePayload(
        text: b.text, isFromMe: b.isFromMe,
        sender: isGroup ? b.senderName : nil, imageB64: img, timestamp: b.date)
    }
  }
}
