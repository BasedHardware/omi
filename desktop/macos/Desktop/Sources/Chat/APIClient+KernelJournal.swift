import Foundation

// The kernel journal owns chat durability. These transport calls are its
// bounded backend projection/reconciliation boundary, kept out of APIClient's
// already oversized core transport file.
extension APIClient {
  func saveMessage(
    text: String,
    sender: String,
    appId: String? = nil,
    sessionId: String? = nil,
    contentBlocksJSON: String? = nil,
    metadata: String? = nil,
    clientMessageId: String? = nil,
    messageSource: String = "desktop_chat",
    journalRevision: Int? = nil,
    expectedOwnerId: String? = nil
  ) async throws -> SaveMessageResponse {
    struct SaveRequest: Encodable {
      let text: String
      let sender: String
      let app_id: String?
      let session_id: String?
      let content_blocks: [OmiAnyCodable]?
      let metadata: String?
      let client_message_id: String?
      let message_source: String
      let journal_revision: Int?
    }
    let contentBlocks = contentBlocksJSON.flatMap { json -> [OmiAnyCodable]? in
      guard let data = json.data(using: .utf8) else { return nil }
      return try? JSONDecoder().decode([OmiAnyCodable].self, from: data)
    }
    let body = SaveRequest(
      text: text,
      sender: sender,
      app_id: appId,
      session_id: sessionId,
      content_blocks: contentBlocks,
      metadata: metadata,
      client_message_id: clientMessageId,
      message_source: messageSource,
      journal_revision: journalRevision)
    return try await post(
      "v2/desktop/messages",
      body: body,
      includeBYOK: false,
      expectedOwnerId: expectedOwnerId)
  }

  func getMessages(
    appId: String? = nil,
    limit: Int = 100,
    offset: Int = 0,
    expectedOwnerId: String? = nil
  ) async throws -> [ChatMessageDB] {
    var queryItems = ["limit=\(limit)", "offset=\(offset)"]
    if let appId { queryItems.append("app_id=\(appId)") }
    return try await get(
      "v2/desktop/messages?\(queryItems.joined(separator: "&"))",
      includeBYOK: false,
      expectedOwnerId: expectedOwnerId)
  }

  func getMessages(
    sessionId: String,
    limit: Int = 100,
    offset: Int = 0,
    expectedOwnerId: String? = nil
  ) async throws -> [ChatMessageDB] {
    let queryItems = [
      "session_id=\(sessionId)",
      "limit=\(limit)",
      "offset=\(offset)",
    ]
    return try await get(
      "v2/desktop/messages?\(queryItems.joined(separator: "&"))",
      includeBYOK: false,
      expectedOwnerId: expectedOwnerId)
  }

  /// Stable keyset page used only by the canonical kernel reconciler. The
  /// offset-based message APIs above remain unchanged for rollback clients.
  func getMessagesReconcilePage(
    appId: String? = nil,
    sessionId: String? = nil,
    limit: Int = 100,
    cursor: String? = nil,
    expectedOwnerId: String
  ) async throws -> DesktopMessageReconcilePage {
    var components = URLComponents()
    components.path = "v2/desktop/messages/reconcile"
    var queryItems = [URLQueryItem(name: "limit", value: String(limit))]
    if let appId { queryItems.append(URLQueryItem(name: "app_id", value: appId)) }
    if let sessionId { queryItems.append(URLQueryItem(name: "session_id", value: sessionId)) }
    if let cursor { queryItems.append(URLQueryItem(name: "cursor", value: cursor)) }
    components.queryItems = queryItems
    guard let endpoint = components.string else { throw APIError.invalidResponse }
    return try await get(
      endpoint,
      includeBYOK: false,
      expectedOwnerId: expectedOwnerId)
  }
}

struct SaveMessageResponse: Codable {
  let id: String
  let createdAt: Date
  let sessionId: String?
  let created: Bool?
  let updated: Bool?
  let journalRevision: Int?

  enum CodingKeys: String, CodingKey {
    case id
    case createdAt = "created_at"
    case sessionId = "session_id"
    case created
    case updated
    case journalRevision = "journal_revision"
  }
}

struct ChatMessageDB: Decodable, Identifiable {
  let id: String
  let text: String
  let createdAt: Date
  let sender: String
  let appId: String?
  let sessionId: String?
  let rating: Int?
  let reported: Bool
  let metadata: String?
  let contentBlocksJSON: String?
  let clientMessageId: String?

  enum CodingKeys: String, CodingKey {
    case id, text, sender, rating, reported, metadata
    case contentBlocks = "content_blocks"
    case clientMessageId = "client_message_id"
    case createdAt = "created_at"
    case appId = "app_id"
    case sessionId = "session_id"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    text = try container.decodeIfPresent(String.self, forKey: .text) ?? ""
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
    sender = try container.decodeIfPresent(String.self, forKey: .sender) ?? "human"
    appId = try container.decodeIfPresent(String.self, forKey: .appId)
    sessionId = try container.decodeIfPresent(String.self, forKey: .sessionId)
    rating = try container.decodeIfPresent(Int.self, forKey: .rating)
    reported = try container.decodeIfPresent(Bool.self, forKey: .reported) ?? false
    metadata = try container.decodeIfPresent(String.self, forKey: .metadata)
    if let blocks = try container.decodeIfPresent([OmiAnyCodable].self, forKey: .contentBlocks) {
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.sortedKeys]
      contentBlocksJSON = try String(decoding: encoder.encode(blocks), as: UTF8.self)
    } else {
      contentBlocksJSON = nil
    }
    clientMessageId = try container.decodeIfPresent(String.self, forKey: .clientMessageId)
  }
}

struct DesktopMessageReconcilePage: Decodable {
  let messages: [ChatMessageDB]
  let nextCursor: String?
  let hasMore: Bool

  enum CodingKeys: String, CodingKey {
    case messages
    case nextCursor = "next_cursor"
    case hasMore = "has_more"
  }
}

struct MessageDeleteResponse: Codable {
  let status: String
  let deletedCount: Int?

  enum CodingKeys: String, CodingKey {
    case status
    case deletedCount = "deleted_count"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    status = try container.decodeIfPresent(String.self, forKey: .status) ?? "ok"
    deletedCount = try container.decodeIfPresent(Int.self, forKey: .deletedCount)
  }
}
