import Foundation
import OmiWAL

extension APIClient {
  // MARK: - Platform Tools (backend RAG)

  struct ToolResponse: Decodable {
    let toolName: String
    let resultText: String
    let isError: Bool
    let sources: [ToolSource]?

    enum CodingKeys: String, CodingKey {
      case toolName = "tool_name"
      case resultText = "result_text"
      case isError = "is_error"
      case sources
    }
  }

  struct ToolSource: Decodable, Sendable {
    let kind: String
    let sourceID: String
    let title: String
    let preview: String
    let createdAt: String?
    let momentTimestampMs: Int?
    let appName: String?
    let url: String?

    enum CodingKeys: String, CodingKey {
      case kind, title, preview, url
      case sourceID = "source_id"
      case createdAt = "created_at"
      case momentTimestampMs = "moment_timestamp_ms"
      case appName = "app_name"
    }

    init(
      kind: String,
      sourceID: String,
      title: String,
      preview: String,
      createdAt: String?,
      momentTimestampMs: Int?,
      appName: String?,
      url: String?
    ) {
      self.kind = kind
      self.sourceID = sourceID
      self.title = title
      self.preview = preview
      self.createdAt = createdAt
      self.momentTimestampMs = momentTimestampMs
      self.appName = appName
      self.url = url
    }

    init(from decoder: Decoder) throws {
      let container = try decoder.container(keyedBy: CodingKeys.self)
      kind = try container.decodeIfPresent(String.self, forKey: .kind) ?? ""
      sourceID = try container.decodeIfPresent(String.self, forKey: .sourceID) ?? ""
      title = try container.decodeIfPresent(String.self, forKey: .title) ?? ""
      preview = try container.decodeIfPresent(String.self, forKey: .preview) ?? ""
      createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
      momentTimestampMs = try container.decodeIfPresent(Int.self, forKey: .momentTimestampMs)
      appName = try container.decodeIfPresent(String.self, forKey: .appName)
      url = try container.decodeIfPresent(String.self, forKey: .url)
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

  struct SearchChunksRequest: Encodable {
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

  /// Semantic search over raw transcript chunks — the verbatim layer behind
  /// `toolSearchConversations`, whose summary matching drops exact dates, names,
  /// and numbers. Typed sources reuse kind "conversation" with the PARENT
  /// conversation id, so chunk citations share the summary results' ref
  /// namespace. Older backends return the same envelope with no sources.
  func toolSearchConversationChunks(
    query: String,
    limit: Int = 5,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ToolResponse {
    let body = SearchChunksRequest(query: query, limit: limit)
    return try await post(
      "v1/tools/conversations/search-chunks",
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

  // MARK: - JIT Knowledge Ledger Tools (generic passthrough)

  /// Response envelope for `POST /v1/agent/execute-tool` (backend/routers/agent_tools.py).
  /// This is a distinct, narrower contract than `ToolResponse` above: no `sources`, and
  /// failures come back as a populated `error` string rather than an HTTP error.
  struct AgentExecuteToolResponse: Decodable {
    let result: String?
    let error: String?
  }

  /// Generic dispatch for the seven JIT-gated knowledge-ledger tools (search_knowledge,
  /// read_playbook, search_historical_facts, get_entity_timeline_tool, save_playbook,
  /// create_standing_trigger, close_fact). They share one backend route keyed by
  /// `tool_name`, so there is no per-tool typed wrapper the way the `/v1/tools/*` routes
  /// above have. The backend independently re-checks the JIT rollout for `toolName` on
  /// every call; a 404 there means the tool is unavailable for this user regardless of
  /// what the desktop manifest advertised.
  func executeAgentTool(
    toolName: String,
    params: [String: Any],
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AgentExecuteToolResponse {
    let body = OmiAnyCodable(["tool_name": toolName, "params": params] as [String: Any])
    return try await post(
      "v1/agent/execute-tool",
      body: body,
      customBaseURL: nil,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

}
