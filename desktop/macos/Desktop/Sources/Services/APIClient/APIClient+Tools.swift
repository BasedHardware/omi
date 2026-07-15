import Foundation
import OmiWAL

extension APIClient {
  // MARK: - Platform Tools (backend RAG)

  struct ToolResponse: Decodable {
    let toolName: String
    let resultText: String
    let isError: Bool

    enum CodingKeys: String, CodingKey {
      case toolName = "tool_name"
      case resultText = "result_text"
      case isError = "is_error"
    }
  }

  struct SearchRequest: Encodable {
    let query: String
    let startDate: String?
    let endDate: String?
    let limit: Int
    let includeTranscript: Bool?

    enum CodingKeys: String, CodingKey {
      case query
      case startDate = "start_date"
      case endDate = "end_date"
      case limit
      case includeTranscript = "include_transcript"
    }
  }

  struct MemorySearchRequest: Encodable {
    let query: String
    let limit: Int
  }

  struct CreateActionItemRequest: Encodable {
    let description: String
    let dueAt: String?
    let conversationId: String?

    enum CodingKeys: String, CodingKey {
      case description
      case dueAt = "due_at"
      case conversationId = "conversation_id"
    }
  }

  struct UpdateActionItemRequest: Encodable {
    let completed: Bool?
    let description: String?
    let dueAt: String?

    enum CodingKeys: String, CodingKey {
      case completed
      case description
      case dueAt = "due_at"
    }
  }

  struct CreateCalendarEventRequest: Encodable {
    let title: String
    let startTime: String
    let endTime: String
    let description: String?
    let location: String?
    let attendees: String?

    enum CodingKeys: String, CodingKey {
      case title
      case startTime = "start_time"
      case endTime = "end_time"
      case description
      case location
      case attendees
    }
  }

  /// Percent-encode a date string for use in query parameters.
  /// `.urlQueryAllowed` does not encode `+`, but servers decode `+` as space in query strings.
  /// This encodes `+` as `%2B` so timezone offsets like `+07:00` survive round-trip.
  private func encodeQueryDate(_ date: String) -> String {
    var allowed = CharacterSet.urlQueryAllowed
    allowed.remove(charactersIn: "+")
    return date.addingPercentEncoding(withAllowedCharacters: allowed) ?? date
  }

  func toolGetConversations(
    startDate: String? = nil,
    endDate: String? = nil,
    limit: Int = 20,
    offset: Int = 0,
    includeTranscript: Bool = true,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ToolResponse {
    var params =
      "v1/tools/conversations?limit=\(limit)&offset=\(offset)&include_transcript=\(includeTranscript)"
    if let sd = startDate { params += "&start_date=\(encodeQueryDate(sd))" }
    if let ed = endDate { params += "&end_date=\(encodeQueryDate(ed))" }
    return try await get(
      params,
      customBaseURL: nil,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func toolSearchConversations(
    query: String,
    startDate: String? = nil,
    endDate: String? = nil,
    limit: Int = 5,
    includeTranscript: Bool = true,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ToolResponse {
    let body = SearchRequest(
      query: query, startDate: startDate, endDate: endDate, limit: limit,
      includeTranscript: includeTranscript)
    return try await post(
      "v1/tools/conversations/search",
      body: body,
      customBaseURL: nil,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func toolGetMemories(
    limit: Int = 50,
    offset: Int = 0,
    startDate: String? = nil,
    endDate: String? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ToolResponse {
    var params = "v1/tools/memories?limit=\(limit)&offset=\(offset)"
    if let sd = startDate { params += "&start_date=\(encodeQueryDate(sd))" }
    if let ed = endDate { params += "&end_date=\(encodeQueryDate(ed))" }
    return try await get(
      params,
      customBaseURL: nil,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func toolSearchMemories(
    query: String,
    limit: Int = 5,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ToolResponse {
    let body = MemorySearchRequest(query: query, limit: limit)
    return try await post(
      "v1/tools/memories/search",
      body: body,
      customBaseURL: nil,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func toolGetActionItems(
    limit: Int = 50,
    offset: Int = 0,
    completed: Bool? = nil,
    startDate: String? = nil,
    endDate: String? = nil,
    dueStartDate: String? = nil,
    dueEndDate: String? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ToolResponse {
    var params = "v1/tools/action-items?limit=\(limit)&offset=\(offset)"
    if let c = completed { params += "&completed=\(c)" }
    if let sd = startDate { params += "&start_date=\(encodeQueryDate(sd))" }
    if let ed = endDate { params += "&end_date=\(encodeQueryDate(ed))" }
    if let dsd = dueStartDate { params += "&due_start_date=\(encodeQueryDate(dsd))" }
    if let ded = dueEndDate { params += "&due_end_date=\(encodeQueryDate(ded))" }
    return try await get(
      params,
      customBaseURL: nil,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func toolCreateActionItem(
    description: String,
    dueAt: String? = nil,
    conversationId: String? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ToolResponse {
    let body = CreateActionItemRequest(
      description: description, dueAt: dueAt, conversationId: conversationId)
    return try await post(
      "v1/tools/action-items",
      body: body,
      customBaseURL: nil,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func toolUpdateActionItem(
    id: String,
    completed: Bool? = nil,
    description: String? = nil,
    dueAt: String? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ToolResponse {
    let body = UpdateActionItemRequest(completed: completed, description: description, dueAt: dueAt)
    return try await patch(
      "v1/tools/action-items/\(id)",
      body: body,
      customBaseURL: nil,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func toolCreateCalendarEvent(
    title: String,
    startTime: String,
    endTime: String,
    description: String? = nil,
    location: String? = nil,
    attendees: String? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ToolResponse {
    let body = CreateCalendarEventRequest(
      title: title,
      startTime: startTime,
      endTime: endTime,
      description: description,
      location: location,
      attendees: attendees
    )
    return try await post(
      "v1/tools/calendar-events",
      body: body,
      customBaseURL: nil,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  // MARK: - X (Twitter) Connector

  /// Ask the Python backend for the X OAuth authorize URL. The desktop passes
  /// its own deep link so the backend can redirect back to this exact build.
  func xOAuthURL(successRedirectURL: String) async throws -> XOAuthURLResponse {
    let encoded = successRedirectURL.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
    return try await get("v1/x/oauth-url?success_redirect_url=\(encoded)")
  }

  func xConnectionStatus() async throws -> XConnectionStatus {
    try await get("v1/x/connection-status")
  }

  @discardableResult
  func xSync() async throws -> XSyncResult {
    try await post("v1/x/sync")
  }

  func xDisconnect() async throws {
    let _: XSimpleOK = try await post("v1/x/disconnect")
  }
}

struct XOAuthURLResponse: Decodable {
  let success: Bool
  let authUrl: String?
  let error: String?
  enum CodingKeys: String, CodingKey {
    case success
    case authUrl = "auth_url"
    case error
  }
}

struct XConnectionStatus: Decodable {
  let success: Bool
  let connected: Bool
  let handle: String?
  let postCount: Int?
  let memoryCount: Int?
  let syncing: Bool?
  let lastSyncedAt: String?
  let lastSyncSource: String?
  enum CodingKeys: String, CodingKey {
    case success
    case connected
    case handle
    case postCount = "post_count"
    case memoryCount = "memory_count"
    case syncing
    case lastSyncedAt = "last_synced_at"
    case lastSyncSource = "last_sync_source"
  }
}

struct XSyncResult: Decodable {
  let success: Bool
  let source: String?
  let newPosts: Int?
  let memoriesCreated: Int?
  let error: String?
  enum CodingKeys: String, CodingKey {
    case success
    case source
    case newPosts = "new_posts"
    case memoriesCreated = "memories_created"
    case error
  }
}

struct XSimpleOK: Decodable {
  let success: Bool
}
