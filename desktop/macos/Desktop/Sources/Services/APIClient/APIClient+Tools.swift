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

  /// `GET /v1/tools/commitments`: the person's open commitments to other people, grouped by
  /// person. Missing collections decode as empty so an error envelope still decodes.
  struct CommitmentsToolResponse: Decodable, Sendable {
    let toolName: String
    let resultText: String
    let isError: Bool
    let sources: [ToolSource]?
    /// The start of the window the server actually checked (after its 90-day clamp).
    let since: String?
    let groups: [CommitmentGroup]
    let unattributed: [Commitment]
    let totals: CommitmentTotals
    let truncated: Bool

    enum CodingKeys: String, CodingKey {
      case toolName = "tool_name"
      case resultText = "result_text"
      case isError = "is_error"
      case sources, since, groups, unattributed, totals, truncated
    }

    init(from decoder: Decoder) throws {
      let container = try decoder.container(keyedBy: CodingKeys.self)
      toolName = try container.decodeIfPresent(String.self, forKey: .toolName) ?? "get_commitments"
      resultText = try container.decodeIfPresent(String.self, forKey: .resultText) ?? ""
      isError = try container.decodeIfPresent(Bool.self, forKey: .isError) ?? false
      sources = try container.decodeIfPresent([ToolSource].self, forKey: .sources)
      since = try container.decodeIfPresent(String.self, forKey: .since)
      groups = try container.decodeIfPresent([CommitmentGroup].self, forKey: .groups) ?? []
      unattributed = try container.decodeIfPresent([Commitment].self, forKey: .unattributed) ?? []
      totals = try container.decodeIfPresent(CommitmentTotals.self, forKey: .totals) ?? CommitmentTotals()
      truncated = try container.decodeIfPresent(Bool.self, forKey: .truncated) ?? false
    }
  }

  struct CommitmentGroup: Decodable, Sendable {
    let names: [String]
    let basis: String
    let likely: Bool?
    /// The person filter matched only part of this name, so the model checks with the user.
    let partialMatch: Bool?
    let openCount: Int
    let commitments: [Commitment]

    enum CodingKeys: String, CodingKey {
      case names, basis, likely, commitments
      case openCount = "open_count"
      case partialMatch = "partial_match"
    }
  }

  struct Commitment: Decodable, Sendable {
    struct Attribution: Decodable, Sendable {
      let names: [String]
      let basis: String
      /// True when the person was inferred rather than heard on their own line.
      let likely: Bool?
    }

    let taskID: String
    let description: String
    let dueAt: String?
    let dueCertainty: String?
    let createdAt: String?
    let conversationID: String
    let conversationTitle: String?
    let excerpt: String?
    let context: String?
    let attribution: Attribution
    let partialMatch: Bool?

    enum CodingKeys: String, CodingKey {
      case description, excerpt, context, attribution
      case taskID = "task_id"
      case dueAt = "due_at"
      case dueCertainty = "due_certainty"
      case createdAt = "created_at"
      case conversationID = "conversation_id"
      case conversationTitle = "conversation_title"
      case partialMatch = "partial_match"
    }
  }

  struct CommitmentTotals: Decodable, Sendable {
    var people = 0
    var commitments = 0
    var unattributed = 0
    var excludedUnknownOwner = 0
    var notChecked = 0

    enum CodingKeys: String, CodingKey {
      case people, commitments, unattributed
      case excludedUnknownOwner = "excluded_unknown_owner"
      case notChecked = "not_checked"
    }

    init() {}

    init(from decoder: Decoder) throws {
      let container = try decoder.container(keyedBy: CodingKeys.self)
      people = try container.decodeIfPresent(Int.self, forKey: .people) ?? 0
      commitments = try container.decodeIfPresent(Int.self, forKey: .commitments) ?? 0
      unattributed = try container.decodeIfPresent(Int.self, forKey: .unattributed) ?? 0
      excludedUnknownOwner = try container.decodeIfPresent(Int.self, forKey: .excludedUnknownOwner) ?? 0
      notChecked = try container.decodeIfPresent(Int.self, forKey: .notChecked) ?? 0
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

  /// Percent-encode a free-text query value (a name may hold `&`, `=`, `#` or `+`).
  private func encodeQueryValue(_ value: String) -> String {
    var allowed = CharacterSet.urlQueryAllowed
    allowed.remove(charactersIn: "+&=#?/")
    return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value
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

  /// Read-only. The owner is the authenticated account; there is no owner parameter.
  func toolGetCommitments(
    since: String? = nil,
    person: String? = nil,
    limitPeople: Int = 10,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> CommitmentsToolResponse {
    var params = "v1/tools/commitments?limit_people=\(limitPeople)"
    if let since { params += "&since=\(encodeQueryValue(since))" }
    if let person { params += "&person=\(encodeQueryValue(person))" }
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
