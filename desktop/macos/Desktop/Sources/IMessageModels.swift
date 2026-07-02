import Foundation

/// A single decoded message read from the local Messages database.
struct IMessageRecord: Sendable {
  let rowid: Int64
  let guid: String
  let text: String
  let isFromMe: Bool
  let date: Date
  let handle: String?  // sender phone/email; nil when isFromMe
  let chatGUID: String
  let chatIdentifier: String?
  let chatDisplayName: String?
}

// MARK: - API payloads (snake_case matches backend models/imessage.py)

/// Timestamps are sent as ISO8601 strings because APIClient's shared JSONEncoder
/// encodes `Date` as a reference-date double, which the backend would misread.
struct IMessageMessagePayload: Encodable {
  let guid: String
  let text: String
  let isFromMe: Bool
  let timestamp: String
  let handle: String?

  enum CodingKeys: String, CodingKey {
    case guid, text, timestamp, handle
    case isFromMe = "is_from_me"
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

  enum CodingKeys: String, CodingKey {
    case success
    case conversationsCreated = "conversations_created"
    case peopleUpserted = "people_upserted"
    case messagesIngested = "messages_ingested"
    case skippedDuplicates = "skipped_duplicates"
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

// MARK: - Reply drafting

struct IMessageDraftMessagePayload: Codable, Sendable {
  let text: String
  let isFromMe: Bool

  enum CodingKeys: String, CodingKey {
    case text
    case isFromMe = "is_from_me"
  }
}

struct IMessageDraftRequestPayload: Encodable {
  let person: String
  let thread: [IMessageDraftMessagePayload]
  let intent: String?
}

struct IMessageDraftResponsePayload: Decodable {
  let draft: String
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

  /// Recent thread as draft-reply context (last N messages).
  func draftContext(limit: Int = 20) -> [IMessageDraftMessagePayload] {
    bubbles.suffix(limit).map {
      IMessageDraftMessagePayload(text: $0.text, isFromMe: $0.isFromMe)
    }
  }
}
