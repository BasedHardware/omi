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
