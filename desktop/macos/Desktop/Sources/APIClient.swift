import Foundation
import OmiWAL

actor APIClient {
  static let shared = APIClient()
  // Primary data backend URL — Python backend is the single source of truth for all data CRUD.
  // Beta release channel uses the dev service; stable uses production or explicit local env.
  var baseURL: String {
    DesktopBackendEnvironment.pythonBaseURL()
  }

  // Rust desktop backend URL — used only for: agent VM provisioning/status,
  // config/api-keys, Crisp, and local test subscription. All data CRUD,
  // chat AI, and title generation are on Python.
  // Set via OMI_DESKTOP_API_URL env var (in .env).
  var rustBackendURL: String {
    let resolved = DesktopBackendEnvironment.rustBackendURL()
    if !resolved.isEmpty { return resolved }

    NSLog("OMI API: OMI_DESKTOP_API_URL not set — Rust backend calls will fail")
    return ""
  }

  let session: URLSession
  private let decoder: JSONDecoder

  /// When set, `buildHeaders` uses this instead of calling AuthService (test-only).
  var testAuthHeader: String?

  // Short-lived caches to deduplicate simultaneous calls from multiple services
  private var goalsCacheTime: Date?
  private var goalsCache: [Goal]?
  // Keyed by the query parameters so a cached total for one filter set is never
  // returned for a different one (e.g. includeDiscarded / statuses).
  private var conversationsCountCache: [String: (count: Int, time: Date)] = [:]

  init() {
    let config = URLSessionConfiguration.default
    config.timeoutIntervalForRequest = 30
    self.session = URLSession(configuration: config)

    self.decoder = Self.makeDecoder()
  }

  /// Test-only initializer that accepts a custom URLSession for request interception.
  init(session: URLSession) {
    self.session = session
    self.decoder = Self.makeDecoder()
  }

  private static func makeDecoder() -> JSONDecoder {
    let decoder = JSONDecoder()
    // Note: Don't use .convertFromSnakeCase - it conflicts with explicit CodingKeys
    // Use custom date strategy to handle ISO8601 with fractional seconds
    decoder.dateDecodingStrategy = .custom { decoder in
      let container = try decoder.singleValueContainer()
      let dateString = try container.decode(String.self)

      // Try with fractional seconds first (API returns dates like "2026-01-25T22:51:07.159249Z")
      let isoWithFractional = ISO8601DateFormatter()
      isoWithFractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
      if let date = isoWithFractional.date(from: dateString) {
        return date
      }

      // Fallback to standard ISO8601 without fractional seconds
      let iso = ISO8601DateFormatter()
      if let date = iso.date(from: dateString) {
        return date
      }

      throw DecodingError.dataCorruptedError(
        in: container, debugDescription: "Invalid date format: \(dateString)")
    }
    return decoder
  }

  // MARK: - Request Building

  func buildHeaders(
    requireAuth: Bool = true,
    forceRefreshAuth: Bool = false,
    includeBYOK: Bool = true
  ) async throws -> [String: String] {
    var headers: [String: String] = [
      "Content-Type": "application/json",
      "X-App-Platform": "macos",
      "X-App-Version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown",
      "X-App-Build": Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "unknown",
      "X-Device-Id-Hash": ClientDeviceService.shared.deviceIdHash,
      "X-Request-Start-Time": String(Date().timeIntervalSince1970),
      "X-Desktop-Request-ID": UUID().uuidString,
    ]

    if requireAuth {
      if let testHeader = testAuthHeader {
        headers["Authorization"] = testHeader
      } else {
        let authService = await MainActor.run { AuthService.shared }
        let authHeader = try await authService.getAuthHeader(forceRefresh: forceRefreshAuth)
        headers["Authorization"] = authHeader
      }
    }

    // BYOK: attach user-provided keys so the backend uses them for LLM/STT
    // calls this request triggers. Sent per-request; never stored server-side.
    if includeBYOK, APIKeyService.isByokActive {
      let health = await MainActor.run { CredentialHealthManager.shared }
      let snapshot = APIKeyService.byokSnapshot
      for (provider, entry) in snapshot {
        let canAttach = await MainActor.run {
          health.canUseBYOK(provider: provider, fingerprint: entry.fingerprint)
        }
        if canAttach {
          headers[provider.headerName] = entry.key
        } else {
          log(
            "CredentialHealth: context=build_headers failure_class=byok_invalid_suppressed"
              + " provider=\(provider.rawValue)")
        }
      }
    }

    return headers
  }

  // MARK: - HTTP Methods

  func get<T: Decodable>(
    _ endpoint: String,
    requireAuth: Bool = true,
    customBaseURL: String? = nil,
    includeBYOK: Bool = true
  ) async throws -> T {
    let base = customBaseURL ?? baseURL
    let url = URL(string: base + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth, includeBYOK: includeBYOK)

    return try await performRequest(request)
  }

  func post<T: Decodable, B: Encodable>(
    _ endpoint: String,
    body: B,
    requireAuth: Bool = true,
    customBaseURL: String? = nil,
    includeBYOK: Bool = true
  ) async throws -> T {
    let base = customBaseURL ?? baseURL
    let url = URL(string: base + endpoint)!
    log("APIClient: POST \(url.absoluteString)")
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth, includeBYOK: includeBYOK)
    request.httpBody = try JSONEncoder().encode(body)

    return try await performRequest(request)
  }

  func post<T: Decodable>(
    _ endpoint: String,
    requireAuth: Bool = true,
    customBaseURL: String? = nil,
    includeBYOK: Bool = true
  ) async throws -> T {
    let base = customBaseURL ?? baseURL
    let url = URL(string: base + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth, includeBYOK: includeBYOK)

    return try await performRequest(request)
  }

  /// Phase 2 realtime hub: ask the backend to mint a short-lived ephemeral token
  /// for `provider` ("openai"|"gemini"). The backend gates on auth + paywall.
  /// Credential failures are typed so the hub can recover deterministically instead
  /// of treating every failure as a silent fallback.
  func mintRealtimeToken(provider: String) async throws -> String {
    struct Resp: Decodable { let token: String }
    let base = rustBackendURL
    guard !base.isEmpty else {
      throw CredentialHealthError.backendTransient(
        statusCode: nil,
        message: "Desktop backend URL is not configured.")
    }
    let normalized = base.hasSuffix("/") ? base : base + "/"
    guard let url = URL(string: normalized + "v2/realtime/session") else {
      throw CredentialHealthError.backendTransient(statusCode: nil, message: "Invalid desktop backend URL.")
    }

    let providerType = CredentialHealthManager.realtimeProvider(from: provider)
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true, includeBYOK: false)
    request.httpBody = try JSONEncoder().encode(["provider": provider])

    do {
      return try await performRealtimeMintRequest(request, provider: providerType, retriedAuth: false)
    } catch let error as RealtimeTokenMintError {
      log("APIClient: realtime token mint failed for \(provider): \(error.localizedDescription)")
      throw error
    } catch let error as CredentialHealthError {
      log("APIClient: realtime token mint failed for \(provider): \(error.localizedDescription)")
      throw error
    } catch {
      log("APIClient: realtime token mint failed for \(provider): \(error.localizedDescription)")
      throw CredentialHealthError.backendTransient(statusCode: nil, message: error.localizedDescription)
    }
  }

  private func performRealtimeMintRequest(
    _ request: URLRequest,
    provider: RealtimeHubProvider?,
    retriedAuth: Bool
  ) async throws -> String {
    struct Resp: Decodable { let token: String }
    let (data, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw CredentialHealthError.backendTransient(statusCode: nil, message: APIError.invalidResponse.localizedDescription)
    }

    if httpResponse.statusCode == 401, !retriedAuth {
      let authService = await MainActor.run { AuthService.shared }
      var retry = request
      do {
        retry.setValue(try await authService.getAuthHeader(forceRefresh: true), forHTTPHeaderField: "Authorization")
      } catch AuthError.notSignedIn {
        throw CredentialHealthError.requiresLogin(message: "Please sign in again to use voice responses.")
      } catch {
        throw CredentialHealthError.backendTransient(statusCode: nil, message: error.localizedDescription)
      }

      do {
        let token = try await performRealtimeMintRequest(retry, provider: provider, retriedAuth: true)
        log("CredentialHealth: context=realtime_mint_auth_retry failure_class=retry_succeeded")
        return token
      } catch let error as RealtimeTokenMintError {
        throw error
      } catch let error as CredentialHealthError {
        throw error
      } catch {
        throw CredentialHealthError.backendTransient(statusCode: nil, message: error.localizedDescription)
      }
    }

    guard (200...299).contains(httpResponse.statusCode) else {
      let payload = Self.extractErrorPayload(from: data)
      let healthError = CredentialHealthManager.classifyHTTPFailure(
        statusCode: httpResponse.statusCode,
        payload: payload,
        provider: provider)
      throw RealtimeTokenMintError(statusCode: httpResponse.statusCode, healthError: healthError, payload: payload)
    }

    let resp = try decoder.decode(Resp.self, from: data)
    guard !resp.token.isEmpty else {
      throw CredentialHealthError.backendTransient(statusCode: httpResponse.statusCode, message: "Realtime token was empty.")
    }
    return resp.token
  }

  /// Report a managed realtime turn's token usage so the backend can price it and record
  /// it into the llm_usage cost ledger. Fire-and-forget; failures are
  /// logged and dropped (the backend reconciler is the eventual safety net). Only called
  /// for managed (ephemeral) sessions — BYOK users pay the provider directly.
  func reportRealtimeUsage(
    provider: String,
    model: String,
    inputText: Int,
    inputAudio: Int,
    inputCached: Int,
    outputText: Int,
    outputAudio: Int
  ) async {
    let base = rustBackendURL
    guard !base.isEmpty else { return }
    let normalized = base.hasSuffix("/") ? base : base + "/"
    guard let url = URL(string: normalized + "v2/realtime/usage") else { return }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.timeoutInterval = 15
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    do {
      let headers = try await buildHeaders(requireAuth: true)
      for (k, v) in headers { request.setValue(v, forHTTPHeaderField: k) }
      let body: [String: Any] = [
        "provider": provider,
        "model": model,
        "input_text_tokens": inputText,
        "input_audio_tokens": inputAudio,
        "input_cached_tokens": inputCached,
        "output_text_tokens": outputText,
        "output_audio_tokens": outputAudio,
      ]
      request.httpBody = try JSONSerialization.data(withJSONObject: body)
      _ = try await session.data(for: request)
    } catch {
      log("APIClient: realtime usage report failed: \(error.localizedDescription)")
    }
  }

  func delete(
    _ endpoint: String,
    requireAuth: Bool = true,
    customBaseURL: String? = nil,
    includeBYOK: Bool = true
  ) async throws {
    let base = customBaseURL ?? baseURL
    let url = URL(string: base + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "DELETE"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth, includeBYOK: includeBYOK)

    let (_, httpResponse) = try await performAuthenticatedData(for: request)

    guard (200...299).contains(httpResponse.statusCode) else {
      throw APIError.httpError(statusCode: httpResponse.statusCode)
    }
  }

  // MARK: - Request Execution

  private func performAuthenticatedData(
    for request: URLRequest,
    retriedAuth: Bool = false
  ) async throws -> (Data, HTTPURLResponse) {
    let endpoint = request.url?.path ?? "unknown"
    let (data, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIError.invalidResponse
    }

    if httpResponse.statusCode == 401, !retriedAuth {
      let authService = await MainActor.run { AuthService.shared }
      var retryRequest = request
      retryRequest.setValue(
        try await authService.getAuthHeader(forceRefresh: true), forHTTPHeaderField: "Authorization")
      DesktopDiagnosticsManager.shared.recordApiAuthRetry(endpoint: endpoint, outcome: "retrying")
      do {
        let result = try await performAuthenticatedData(for: retryRequest, retriedAuth: true)
        DesktopDiagnosticsManager.shared.recordApiAuthRetry(endpoint: endpoint, outcome: "succeeded")
        return result
      } catch {
        DesktopDiagnosticsManager.shared.recordApiAuthRetry(endpoint: endpoint, outcome: "failed")
        throw error
      }
    }

    if httpResponse.statusCode == 401 {
      DesktopDiagnosticsManager.shared.recordApiAuthRetry(endpoint: endpoint, outcome: "unauthorized")
      throw APIError.unauthorized
    }

    return (data, httpResponse)
  }

  private func performRequest<T: Decodable>(_ request: URLRequest) async throws -> T {
    let (data, httpResponse) = try await performAuthenticatedData(for: request)

    guard (200...299).contains(httpResponse.statusCode) else {
      let detail = Self.extractErrorDetail(from: data)
      throw APIError.httpError(statusCode: httpResponse.statusCode, detail: detail)
    }

    do {
      return try decoder.decode(T.self, from: data)
    } catch let decodingError as DecodingError {
      // Log detailed decoding error for debugging
      switch decodingError {
      case .keyNotFound(let key, let context):
        logError(
          "Decoding error - key '\(key.stringValue)' not found: \(context.debugDescription)",
          error: decodingError)
      case .typeMismatch(let type, let context):
        logError(
          "Decoding error - type mismatch for \(type): \(context.debugDescription)",
          error: decodingError)
      case .valueNotFound(let type, let context):
        logError(
          "Decoding error - value not found for \(type): \(context.debugDescription)",
          error: decodingError)
      case .dataCorrupted(let context):
        logError(
          "Decoding error - data corrupted: \(context.debugDescription)", error: decodingError)
      @unknown default:
        logError("Decoding error", error: decodingError)
      }
      throw decodingError
    }
  }

  private static func extractErrorDetail(from data: Data) -> String? {
    if let payload = extractErrorPayload(from: data) {
      return payload.preferredMessage
    }
    guard
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let detail = json["detail"] as? String
    else { return nil }
    return detail
  }

  private static func extractErrorPayload(from data: Data) -> APIErrorPayload? {
    try? JSONDecoder().decode(APIErrorPayload.self, from: data)
  }
}

// MARK: - API Errors

enum APIError: LocalizedError {
  case invalidResponse
  case unauthorized
  case httpError(statusCode: Int, detail: String? = nil)
  case decodingError(Error)
  case unsupportedTierScopedBulkMutation(String)
  case syncRateLimited(retryAfterSeconds: Int?)
  case syncUploadRejected(reason: String)

  var detail: String? {
    switch self {
    case .httpError(_, let detail):
      return detail
    case .syncUploadRejected(let reason):
      return reason
    default:
      return nil
    }
  }

  var errorDescription: String? {
    switch self {
    case .invalidResponse:
      return "Invalid response from server"
    case .unauthorized:
      return "Unauthorized - please sign in again"
    case .httpError(let statusCode, let detail):
      if let detail { return detail }
      return "HTTP error: \(statusCode)"
    case .decodingError(let error):
      return "Failed to decode response: \(error.localizedDescription)"
    case .unsupportedTierScopedBulkMutation(let operation):
      return "Layer-scoped bulk memory \(operation) is not supported yet."
    case .syncRateLimited(let retryAfterSeconds):
      if let retryAfterSeconds {
        return "Sync rate limited (retry after \(retryAfterSeconds)s)"
      }
      return "Sync rate limited"
    case .syncUploadRejected(let reason):
      return reason
    }
  }
}

struct RealtimeTokenMintError: LocalizedError {
  let statusCode: Int
  let healthError: CredentialHealthError
  let payload: APIErrorPayload?

  var errorDescription: String? {
    var description = healthError.localizedDescription
    description += " [status: \(statusCode)"
    if let reason = payload?.reason {
      description += ", reason: \(reason)"
    }
    if let code = payload?.code {
      description += ", code: \(code)"
    }
    description += "]"
    return description
  }
}

// MARK: - MCP API

struct MCPKeyCreatedResponse: Codable {
  let id: String
  let name: String
  let key: String
}

extension APIClient {
  /// Creates a new MCP API key and returns the raw secret (shown only once by the server).
  /// Used to wire Omi memory into external MCP clients (Claude, ChatGPT, Claude Code, Codex).
  func createMCPKey(name: String = "Desktop") async throws -> String {
    struct Body: Encodable { let name: String }
    let response: MCPKeyCreatedResponse = try await post("v1/mcp/keys", body: Body(name: name))
    return response.key
  }
}

// MARK: - Conversation API

extension APIClient {

  static func conversationFilterQueryItems(
    statuses: [ConversationStatus] = [],
    includeDiscarded: Bool = false,
    startDate: Date? = nil,
    endDate: Date? = nil,
    folderId: String? = nil,
    starred: Bool? = nil
  ) -> [String] {
    var queryItems: [String] = [
      "include_discarded=\(includeDiscarded)"
    ]

    if !statuses.isEmpty {
      let statusStrings = statuses.map { $0.rawValue }.joined(separator: ",")
      queryItems.append("statuses=\(statusStrings)")
    }

    if let startDate = startDate {
      let formatter = ISO8601DateFormatter()
      queryItems.append("start_date=\(formatter.string(from: startDate))")
    }

    if let endDate = endDate {
      let formatter = ISO8601DateFormatter()
      queryItems.append("end_date=\(formatter.string(from: endDate))")
    }

    if let folderId = folderId {
      queryItems.append("folder_id=\(folderId)")
    }

    if let starred = starred {
      queryItems.append("starred=\(starred)")
    }

    return queryItems
  }

  /// Fetches conversations from the API with optional filtering
  func getConversations(
    limit: Int = 50,
    offset: Int = 0,
    statuses: [ConversationStatus] = [],
    includeDiscarded: Bool = false,
    startDate: Date? = nil,
    endDate: Date? = nil,
    folderId: String? = nil,
    starred: Bool? = nil
  ) async throws -> [ServerConversation] {
    var queryItems: [String] = [
      "limit=\(limit)",
      "offset=\(offset)",
    ]
    queryItems += Self.conversationFilterQueryItems(
      statuses: statuses,
      includeDiscarded: includeDiscarded,
      startDate: startDate,
      endDate: endDate,
      folderId: folderId,
      starred: starred
    )

    let endpoint = "v1/conversations?\(queryItems.joined(separator: "&"))"
    return try await get(endpoint)
  }

  /// Fetches a single conversation by ID
  func getConversation(id: String) async throws -> ServerConversation {
    return try await get("v1/conversations/\(id)")
  }

  /// Deletes a conversation by ID
  func deleteConversation(id: String) async throws {
    try await delete("v1/conversations/\(id)")
    invalidateConversationsCountCache()
  }

  /// Updates the starred status of a conversation
  func setConversationStarred(id: String, starred: Bool) async throws {
    let url = URL(string: baseURL + "v1/conversations/\(id)/starred?starred=\(starred)")!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)

    let (_, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse,
      (200...299).contains(httpResponse.statusCode)
    else {
      throw APIError.httpError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
    }
    invalidateConversationsCountCache()
  }

  /// Sets the visibility of a conversation for sharing
  /// - Parameters:
  ///   - id: The conversation ID
  ///   - visibility: The visibility level ("shared", "public", or "private")
  func setConversationVisibility(id: String, visibility: String = "shared") async throws {
    let url = URL(
      string: baseURL
        + "v1/conversations/\(id)/visibility?value=\(visibility)&visibility=\(visibility)")!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)

    let (_, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse,
      (200...299).contains(httpResponse.statusCode)
    else {
      throw APIError.httpError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
    }
  }

  /// Gets a shareable link for a conversation by setting it to shared visibility
  /// - Parameter id: The conversation ID
  /// - Returns: The shareable URL for the conversation
  func getConversationShareLink(id: String) async throws -> String {
    // Set visibility to shared
    try await setConversationVisibility(id: id, visibility: "shared")
    // Return the web URL for the shared conversation
    return "https://h.omi.me/conversations/\(id)"
  }

  /// Updates the title of a conversation
  func updateConversationTitle(id: String, title: String) async throws {
    var components = URLComponents(string: baseURL + "v1/conversations/\(id)/title")!
    components.queryItems = [URLQueryItem(name: "title", value: title)]
    let url = components.url!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)

    let (_, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse,
      (200...299).contains(httpResponse.statusCode)
    else {
      throw APIError.httpError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
    }
  }

  /// Searches conversations with a query
  func searchConversations(
    query: String,
    page: Int = 1,
    perPage: Int = 10,
    includeDiscarded: Bool = false
  ) async throws -> ConversationSearchResult {
    struct SearchRequest: Encodable {
      let query: String
      let page: Int
      let perPage: Int
      let includeDiscarded: Bool

      enum CodingKeys: String, CodingKey {
        case query, page
        case perPage = "per_page"
        case includeDiscarded = "include_discarded"
      }
    }

    let body = SearchRequest(
      query: query,
      page: page,
      perPage: perPage,
      includeDiscarded: includeDiscarded
    )

    return try await post("v1/conversations/search", body: body)
  }

  static func conversationsCountEndpoint(
    includeDiscarded: Bool = false,
    statuses: [ConversationStatus] = [.completed, .processing],
    startDate: Date? = nil,
    endDate: Date? = nil,
    folderId: String? = nil,
    starred: Bool? = nil
  ) -> String {
    let queryItems = Self.conversationFilterQueryItems(
      statuses: statuses,
      includeDiscarded: includeDiscarded,
      startDate: startDate,
      endDate: endDate,
      folderId: folderId,
      starred: starred
    )

    return "v1/conversations/count?\(queryItems.joined(separator: "&"))"
  }

  func invalidateConversationsCountCache() {
    conversationsCountCache.removeAll()
  }

  /// Gets the total count of conversations. Uses 5-second cache to deduplicate parallel calls.
  func getConversationsCount(
    includeDiscarded: Bool = false,
    statuses: [ConversationStatus] = [.completed, .processing],
    startDate: Date? = nil,
    endDate: Date? = nil,
    folderId: String? = nil,
    starred: Bool? = nil
  ) async throws -> Int {
    let endpoint = Self.conversationsCountEndpoint(
      includeDiscarded: includeDiscarded,
      statuses: statuses,
      startDate: startDate,
      endDate: endDate,
      folderId: folderId,
      starred: starred
    )

    if let cache = conversationsCountCache[endpoint], Date().timeIntervalSince(cache.time) < 5 {
      return cache.count
    }

    struct CountResponse: Decodable {
      let count: Int
    }

    let response: CountResponse = try await get(endpoint)
    conversationsCountCache[endpoint] = (count: response.count, time: Date())
    return response.count
  }

  /// True when this account has any conversations captured by an Omi wearable
  /// (paired on any platform — usually the mobile app).
  func hasOmiDeviceConversations() async throws -> Bool {
    struct CountResponse: Decodable {
      let count: Int
      // Backends without the sources filter ignore the param and return the
      // unfiltered total without this echo — decoding then fails, so we never
      // read a false positive from an old backend.
      let sources: [String]
    }

    let response: CountResponse = try await get(
      "v1/conversations/count?include_discarded=true&sources=friend,omi")
    return response.count > 0
  }

  /// Gets the count of AI chat messages from PostHog
  func getChatMessageCount() async throws -> Int {
    struct CountResponse: Decodable {
      let count: Int
    }

    let response: CountResponse = try await get("v1/users/stats/chat-messages")
    return response.count
  }

  /// Merges multiple conversations into a new conversation
  func mergeConversations(ids: [String], reprocess: Bool = true) async throws
    -> MergeConversationsResponse
  {
    struct MergeRequest: Encodable {
      let conversationIds: [String]
      let reprocess: Bool

      enum CodingKeys: String, CodingKey {
        case conversationIds = "conversation_ids"
        case reprocess
      }
    }

    let body = MergeRequest(conversationIds: ids, reprocess: reprocess)
    let response: MergeConversationsResponse = try await post("v1/conversations/merge", body: body)
    invalidateConversationsCountCache()
    return response
  }

  // MARK: - Folder API

  /// Gets all folders for the user
  func getFolders() async throws -> [Folder] {
    return try await get("v1/folders")
  }

  /// Creates a new folder
  func createFolder(name: String, description: String? = nil, color: String? = nil) async throws
    -> Folder
  {
    let body = CreateFolderRequest(name: name, description: description, color: color)
    return try await post("v1/folders", body: body)
  }

  /// Updates a folder
  func updateFolder(
    id: String, name: String? = nil, description: String? = nil, color: String? = nil,
    order: Int? = nil
  ) async throws -> Folder {
    let body = UpdateFolderRequest(name: name, description: description, color: color, order: order)
    return try await patch("v1/folders/\(id)", body: body)
  }

  /// Deletes a folder
  func deleteFolder(id: String, moveToFolderId: String? = nil) async throws {
    var endpoint = "v1/folders/\(id)"
    if let moveToId = moveToFolderId {
      endpoint += "?move_to_folder_id=\(moveToId)"
    }
    try await delete(endpoint)
    invalidateConversationsCountCache()
  }

  /// Moves a conversation to a folder
  func moveConversationToFolder(conversationId: String, folderId: String?) async throws {
    let body = MoveToFolderRequest(folderId: folderId)
    let url = URL(string: baseURL + "v1/conversations/\(conversationId)/folder")!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)
    request.httpBody = try JSONEncoder().encode(body)

    let (_, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse,
      (200...299).contains(httpResponse.statusCode)
    else {
      throw APIError.httpError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
    }
    invalidateConversationsCountCache()
  }

}

// MARK: - Conversation Models (matching Flutter app)

enum ConversationStatus: String, Codable {
  case inProgress = "in_progress"
  case processing = "processing"
  case merging = "merging"
  case completed = "completed"
  case failed = "failed"
}

enum ConversationSource: String, Codable {
  case friend
  case omi
  case workflow
  case openglass
  case screenpipe
  case sdcard
  case fieldy
  case bee
  case xor
  case frame
  case friendCom = "friend_com"
  case appleWatch = "apple_watch"
  case phone
  case desktop
  case limitless
  case plaud
  case unknown

  init(from decoder: Decoder) throws {
    let container = try decoder.singleValueContainer()
    let rawValue = try container.decode(String.self)
    self = ConversationSource(rawValue: rawValue) ?? .unknown
  }
}

enum TranscriptPresenceState: Equatable {
  case omittedFromResponse
  case lockedOrRedacted
  case includedEmpty
  case includedNonEmpty
}

struct ServerConversation: Codable, Identifiable, Equatable {
  static func == (lhs: ServerConversation, rhs: ServerConversation) -> Bool {
    lhs.id == rhs.id && lhs.createdAt == rhs.createdAt && lhs.startedAt == rhs.startedAt
      && lhs.finishedAt == rhs.finishedAt && lhs.structured == rhs.structured
      && lhs.status == rhs.status && lhs.discarded == rhs.discarded && lhs.deleted == rhs.deleted
      && lhs.isLocked == rhs.isLocked && lhs.starred == rhs.starred && lhs.folderId == rhs.folderId
      && lhs.source == rhs.source
      && lhs.transcriptSegmentsIncluded == rhs.transcriptSegmentsIncluded
  }

  let id: String
  let createdAt: Date
  let startedAt: Date?
  let finishedAt: Date?

  var structured: Structured
  var transcriptSegments: [TranscriptSegment]
  var transcriptSegmentsIncluded: Bool
  let geolocation: Geolocation?
  let photos: [ConversationPhoto]

  let appsResults: [AppResponse]
  let source: ConversationSource?
  let language: String?

  let status: ConversationStatus
  let discarded: Bool
  let deleted: Bool
  let isLocked: Bool
  var starred: Bool
  let folderId: String?
  let inputDeviceName: String?
  // Lazy processing: true while only the raw transcript is stored (no LLM summary yet);
  // cleared once enriched on first open (get_conversation_by_id).
  let deferred: Bool

  enum CodingKeys: String, CodingKey {
    case id
    case createdAt = "created_at"
    case startedAt = "started_at"
    case finishedAt = "finished_at"
    case structured
    case transcriptSegments = "transcript_segments"
    case geolocation
    case photos
    case appsResults = "apps_results"
    case source
    case language
    case status
    case discarded
    case deleted
    case isLocked = "is_locked"
    case starred
    case folderId = "folder_id"
    case inputDeviceName = "input_device_name"
    case deferred
  }

  init(from decoder: Decoder) throws {
    // Schema authority: OmiAPI.Conversation (generated from app-client OpenAPI).
    // The domain model adapts wire string-dates into Date via the APIClient
    // decoder's ISO8601 strategy, preserves tolerant defaults, and tracks
    // whether transcript_segments was present in the response.
    let wire = try OmiAPI.Conversation(from: decoder)
    let container = try decoder.container(keyedBy: CodingKeys.self)

    id = wire.id
    createdAt = try Self.parseDate(wire.createdAt, decoder: decoder)
    startedAt = try Self.parseOptionalDate(wire.startedAt, decoder: decoder)
    finishedAt = try Self.parseOptionalDate(wire.finishedAt, decoder: decoder)
    structured = Structured(wire.structured ?? OmiAPI.Structured(actionItems: nil, category: nil, emoji: nil, events: nil, overview: nil, title: nil))
    // container.contains distinguishes `"transcript_segments": null` (present,
    // empty) from the key being absent (omitted). wire.transcriptSegments is
    // nil for both, so we must check the container directly.
    transcriptSegmentsIncluded = container.contains(.transcriptSegments)
    transcriptSegments = (wire.transcriptSegments ?? []).map(TranscriptSegment.init)
    geolocation = wire.geolocation
    photos = (wire.photos ?? []).map(ConversationPhoto.init)
    appsResults = (wire.appsResults ?? []).map(AppResponse.init)
    source = wire.source.map { ConversationSource(rawValue: $0.rawValue) ?? .unknown }
    language = wire.language
    status = wire.status.map { ConversationStatus(rawValue: $0.rawValue) ?? .completed } ?? .completed
    discarded = wire.discarded ?? false
    deleted = false  // backend REST Conversation schema does not expose deleted
    isLocked = wire.isLocked ?? false
    starred = wire.starred ?? false
    folderId = wire.folderId
    inputDeviceName = wire.clientDeviceId
    deferred = wire.deferred ?? false
  }

  // Date helpers shared with Event/Structured adapters.
  private static let fractionalFormatter: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
  }()
  private static let standardFormatter = ISO8601DateFormatter()

  private static func parseDate(_ s: String, decoder: Decoder) throws -> Date {
    if let d = fractionalFormatter.date(from: s) ?? standardFormatter.date(from: s) { return d }
    throw DecodingError.dataCorrupted(.init(
      codingPath: decoder.codingPath,
      debugDescription: "Conversation.created_at is not a valid ISO8601 date: \(s)"
    ))
  }

  private static func parseOptionalDate(_ s: String?, decoder: Decoder) throws -> Date? {
    guard let s else { return nil }
    return try parseDate(s, decoder: decoder)
  }

  /// Memberwise initializer for creating from local storage
  init(
    id: String,
    createdAt: Date,
    startedAt: Date?,
    finishedAt: Date?,
    structured: Structured,
    transcriptSegments: [TranscriptSegment],
    transcriptSegmentsIncluded: Bool,
    geolocation: Geolocation?,
    photos: [ConversationPhoto],
    appsResults: [AppResponse],
    source: ConversationSource?,
    language: String?,
    status: ConversationStatus,
    discarded: Bool,
    deleted: Bool,
    isLocked: Bool,
    starred: Bool,
    folderId: String?,
    inputDeviceName: String?,
    deferred: Bool = false
  ) {
    self.id = id
    self.createdAt = createdAt
    self.startedAt = startedAt
    self.finishedAt = finishedAt
    self.structured = structured
    self.transcriptSegments = transcriptSegments
    self.transcriptSegmentsIncluded = transcriptSegmentsIncluded
    self.geolocation = geolocation
    self.photos = photos
    self.appsResults = appsResults
    self.source = source
    self.language = language
    self.status = status
    self.discarded = discarded
    self.deleted = deleted
    self.isLocked = isLocked
    self.starred = starred
    self.folderId = folderId
    self.inputDeviceName = inputDeviceName
    self.deferred = deferred
  }

  /// Returns the title from structured data, or a fallback
  var title: String {
    structured.title.isEmpty ? "Untitled Conversation" : structured.title
  }

  /// Returns the overview/summary from structured data
  var overview: String {
    structured.overview
  }

  /// Returns duration in seconds based on start/finish times or transcript
  var durationInSeconds: Int {
    if let start = startedAt, let end = finishedAt {
      return Int(end.timeIntervalSince(start))
    }
    // Fallback to transcript duration
    guard let lastSegment = transcriptSegments.last else { return 0 }
    return Int(lastSegment.end)
  }

  /// Formatted duration string (e.g., "5m 30s")
  var formattedDuration: String {
    let duration = durationInSeconds
    let minutes = duration / 60
    let seconds = duration % 60
    if minutes > 0 {
      return "\(minutes)m \(seconds)s"
    }
    return "\(seconds)s"
  }

  /// Full transcript as a single string
  var transcript: String {
    transcriptSegments.map { segment in
      let speaker = segment.isUser ? "You" : "Speaker \(segment.speakerId)"
      return "\(speaker): \(segment.text)"
    }.joined(separator: "\n\n")
  }

  var transcriptPresenceState: TranscriptPresenceState {
    if isLocked {
      return .lockedOrRedacted
    }
    if !transcriptSegmentsIncluded {
      return .omittedFromResponse
    }
    if transcriptSegments.isEmpty {
      return .includedEmpty
    }
    return .includedNonEmpty
  }

  var shouldFetchDetailForTranscript: Bool {
    transcriptPresenceState == .omittedFromResponse
  }
}

struct Structured: Codable, Equatable {
  var title: String
  let overview: String
  let emoji: String
  let category: String
  let actionItems: [ActionItem]
  let events: [Event]

  init(from decoder: Decoder) throws {
    // Schema authority: OmiAPI.Structured (generated from app-client OpenAPI).
    // The domain model adds tolerant defaults the wire DTO does not guarantee.
    let wire = try OmiAPI.Structured(from: decoder)
    title = wire.title ?? ""
    overview = wire.overview ?? ""
    emoji = wire.emoji ?? ""
    // CategoryEnum is the backend's strict union; fall back to "other" when the
    // backend returns a value outside it (decoded as ._unknown).
    if let cat = wire.category, cat != ._unknown {
      category = cat.rawValue
    } else {
      category = "other"
    }
    actionItems = (wire.actionItems ?? []).map(ActionItem.init)
    events = (wire.events ?? []).map(Event.init)
  }

  init(_ wire: OmiAPI.Structured) {
    title = wire.title ?? ""
    overview = wire.overview ?? ""
    emoji = wire.emoji ?? ""
    if let cat = wire.category, cat != ._unknown {
      category = cat.rawValue
    } else {
      category = "other"
    }
    actionItems = (wire.actionItems ?? []).map(ActionItem.init)
    events = (wire.events ?? []).map(Event.init)
  }

  func encode(to encoder: Encoder) throws {
    let actionItemsWire = actionItems.map {
      OmiAPI.ActionItem(completed: $0.completed, completedAt: nil, conversationId: nil, createdAt: nil, description_: $0.description, dueAt: nil, updatedAt: nil)
    }
    let eventsWire = events.map {
      OmiAPI.Event(
        created: $0.created,
        description_: $0.description,
        duration: $0.duration,
        start: Event.encodeDateForWire($0.startsAt),
        title: $0.title
      )
    }
    let wire = OmiAPI.Structured(
      actionItems: actionItemsWire,
      category: OmiAPI.CategoryEnum(rawValue: category),
      emoji: emoji,
      events: eventsWire,
      overview: overview,
      title: title
    )
    try wire.encode(to: encoder)
  }

  /// Memberwise initializer for creating from local storage
  init(
    title: String,
    overview: String,
    emoji: String,
    category: String,
    actionItems: [ActionItem],
    events: [Event]
  ) {
    self.title = title
    self.overview = overview
    self.emoji = emoji
    self.category = category
    self.actionItems = actionItems
    self.events = events
  }
}

struct ActionItem: Codable, Identifiable, Equatable {
  var id: String { description }
  let description: String
  let completed: Bool
  let deleted: Bool

  init(description: String, completed: Bool, deleted: Bool) {
    self.description = description
    self.completed = completed
    self.deleted = deleted
  }

  /// Adapter from the generated wire DTO (OmiAPI.ActionItem). `deleted` is a
  /// desktop-only field the backend REST schema does not expose; it defaults
  /// to false on decode.
  init(_ wire: OmiAPI.ActionItem) {
    self.description = wire.description_
    self.completed = wire.completed ?? false
    self.deleted = false
  }

  init(from decoder: Decoder) throws {
    let wire = try OmiAPI.ActionItem(from: decoder)
    self.description = wire.description_
    self.completed = wire.completed ?? false
    self.deleted = false
  }

  func encode(to encoder: Encoder) throws {
    let wire = OmiAPI.ActionItem(
      completed: completed,
      completedAt: nil,
      conversationId: nil,
      createdAt: nil,
      description_: description,
      dueAt: nil,
      updatedAt: nil
    )
    try wire.encode(to: encoder)
  }
}

struct Event: Codable, Identifiable, Equatable {
  var id: String { title + startsAt.description }
  let title: String
  let startsAt: Date
  let duration: Int
  let description: String
  let created: Bool

  /// Adapter from the generated wire DTO (OmiAPI.Event). The backend `Event`
  /// model exposes `start` (not `starts_at`); this adapter maps the field and
  /// parses the ISO8601 string into a Date using the APIClient decoder's
  /// strategy via JSONDecoder reuse.
  init(_ wire: OmiAPI.Event) {
    self.title = wire.title
    self.startsAt = Self.parseDate(wire.start) ?? Date()
    self.duration = wire.duration ?? 0
    self.description = wire.description_ ?? ""
    self.created = wire.created ?? false
  }

  init(from decoder: Decoder) throws {
    // Decode via the generated wire shape, then adapt. `start` is the backend
    // field name (generated); cached rows may still use legacy `starts_at`.
    if let wire = try? OmiAPI.Event(from: decoder) {
      self.title = wire.title
      self.startsAt = Self.parseDate(wire.start) ?? Date()
      self.duration = wire.duration ?? 0
      self.description = wire.description_ ?? ""
      self.created = wire.created ?? false
      return
    }

    enum LegacyKeys: String, CodingKey {
      case title, start, startsAt = "starts_at", duration, description, created
    }
    let container = try decoder.container(keyedBy: LegacyKeys.self)
    self.title = try container.decode(String.self, forKey: .title)
    let startString = try container.decodeIfPresent(String.self, forKey: .start)
      ?? container.decodeIfPresent(String.self, forKey: .startsAt)
    self.startsAt = startString.flatMap(Self.parseDate) ?? Date()
    self.duration = try container.decodeIfPresent(Int.self, forKey: .duration) ?? 0
    self.description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
    self.created = try container.decodeIfPresent(Bool.self, forKey: .created) ?? false
  }

  func encode(to encoder: Encoder) throws {
    let startString = Self.encodeDate(startsAt)
    let wire = OmiAPI.Event(
      created: created,
      description_: description,
      duration: duration,
      start: startString,
      title: title
    )
    try wire.encode(to: encoder)
  }

  // Date helpers — reuse the APIClient decoder's ISO8601-with-fractional strategy.
  private static let fractionalFormatter: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
  }()
  private static let standardFormatter = ISO8601DateFormatter()

  private static func parseDate(_ s: String) -> Date? {
    fractionalFormatter.date(from: s) ?? standardFormatter.date(from: s)
  }

  private static func decodeDate(_ s: String, using decoder: Decoder) throws -> Date {
    if let date = parseDate(s) { return date }
    let context = DecodingError.Context(
      codingPath: decoder.codingPath,
      debugDescription: "Event.start is not a valid ISO8601 date: \(s)"
    )
    throw DecodingError.dataCorrupted(context)
  }

  private static func encodeDate(_ date: Date) -> String {
    fractionalFormatter.string(from: date)
  }

  fileprivate static func encodeDateForWire(_ date: Date) -> String {
    encodeDate(date)
  }
}

/// Schema authority: OmiAPI.Translation (generated from app-client OpenAPI).
/// Field-for-field identical to the wire DTO, so this is a thin alias.
typealias TranscriptTranslation = OmiAPI.Translation

struct TranscriptSegment: Codable, Identifiable {
  let id: String
  let backendId: String?
  let text: String
  let speaker: String?
  let isUser: Bool
  let personId: String?
  let start: Double
  let end: Double
  let translations: [TranscriptTranslation]

  var speakerId: Int {
    guard let speaker = speaker else { return 0 }
    let parts = speaker.split(separator: "_")
    if parts.count > 1, let id = Int(parts[1]) {
      return id
    }
    return 0
  }

  enum CodingKeys: String, CodingKey {
    case id, text, speaker
    case isUser = "is_user"
    case personId = "person_id"
    case start, end, translations
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    let decodedId = try container.decodeIfPresent(String.self, forKey: .id)
    id = decodedId ?? UUID().uuidString
    backendId = decodedId
    text = try container.decodeIfPresent(String.self, forKey: .text) ?? ""
    speaker = try container.decodeIfPresent(String.self, forKey: .speaker)
    isUser = try container.decodeIfPresent(Bool.self, forKey: .isUser) ?? false
    personId = try container.decodeIfPresent(String.self, forKey: .personId)
    start = try container.decodeIfPresent(Double.self, forKey: .start) ?? 0
    end = try container.decodeIfPresent(Double.self, forKey: .end) ?? 0
    translations =
      try container.decodeIfPresent([TranscriptTranslation].self, forKey: .translations) ?? []
  }

  /// Adapter from the generated wire DTO (OmiAPI.TranscriptSegment). The
  /// generated wire exposes `speaker_id` directly; the domain derives it from
  /// `speaker` to preserve legacy behavior.
  init(_ wire: OmiAPI.TranscriptSegment) {
    let decodedId = wire.id
    self.id = decodedId ?? UUID().uuidString
    self.backendId = decodedId
    self.text = wire.text
    self.speaker = wire.speaker
    self.isUser = wire.isUser
    self.personId = wire.personId
    self.start = wire.start
    self.end = wire.end
    self.translations = []  // wire translations map omitted; legacy field
  }

  /// Memberwise initializer for creating from local storage
  init(
    id: String,
    backendId: String? = nil,
    text: String,
    speaker: String?,
    isUser: Bool,
    personId: String?,
    start: Double,
    end: Double,
    translations: [TranscriptTranslation] = []
  ) {
    self.id = id
    self.backendId = backendId
    self.text = text
    self.speaker = speaker
    self.isUser = isUser
    self.personId = personId
    self.start = start
    self.end = end
    self.translations = translations
  }

  /// Formatted timestamp string (e.g., "00:01:30 - 00:01:45")
  var timestampString: String {
    let startTime = formatTime(start)
    let endTime = formatTime(end)
    return "\(startTime) - \(endTime)"
  }

  private func formatTime(_ seconds: Double) -> String {
    let totalSeconds = Int(seconds)
    let hours = totalSeconds / 3600
    let minutes = (totalSeconds % 3600) / 60
    let secs = totalSeconds % 60
    return String(format: "%02d:%02d:%02d", hours, minutes, secs)
  }
}

/// Schema authority: OmiAPI.Geolocation (generated from app-client OpenAPI).
/// Field-for-field identical to the wire DTO; the prior adapter only passed
/// the four exposed fields through with no transformation (no Date parsing,
/// no defaults, no computed properties), so this is a thin alias.
typealias Geolocation = OmiAPI.Geolocation

struct ConversationPhoto: Codable, Identifiable {
  let id: String
  let base64: String
  let description: String?
  let createdAt: Date
  let discarded: Bool

  enum CodingKeys: String, CodingKey {
    case id, base64, description
    case createdAt = "created_at"
    case discarded
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
    base64 = try container.decodeIfPresent(String.self, forKey: .base64) ?? ""
    description = try container.decodeIfPresent(String.self, forKey: .description)
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
    discarded = try container.decodeIfPresent(Bool.self, forKey: .discarded) ?? false
  }

  /// Adapter from the generated wire DTO (OmiAPI.ConversationPhoto). The wire
  /// exposes `created_at` as a string; this adapter parses it via the shared
  /// ISO8601 strategy.
  init(_ wire: OmiAPI.ConversationPhoto) {
    self.id = wire.id ?? UUID().uuidString
    self.base64 = wire.base64
    self.description = wire.description_
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let std = ISO8601DateFormatter()
    if let s = wire.createdAt, let d = f.date(from: s) ?? std.date(from: s) {
      self.createdAt = d
    } else {
      self.createdAt = Date()
    }
    self.discarded = wire.discarded ?? false
  }
}

struct AppResponse: Codable, Identifiable {
  var id: String { appId ?? UUID().uuidString }
  let appId: String?
  let content: String

  enum CodingKeys: String, CodingKey {
    case appId = "app_id"
    case content
  }

  /// Adapter from the generated wire DTO (OmiAPI.AppResult).
  init(_ wire: OmiAPI.AppResult) {
    self.appId = wire.appId
    self.content = wire.content
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    appId = try container.decodeIfPresent(String.self, forKey: .appId)
    content = try container.decodeIfPresent(String.self, forKey: .content) ?? ""
  }
}

struct ConversationSearchResult: Codable {
  let items: [ServerConversation]
  let currentPage: Int
  let totalPages: Int

  enum CodingKeys: String, CodingKey {
    case items
    case currentPage = "current_page"
    case totalPages = "total_pages"
  }
}

// MARK: - Merge Response

/// Response from merge conversations API
struct MergeConversationsResponse: Decodable {
  let status: String
  let message: String
  let warning: String?
  let conversationIds: [String]
  let newConversationId: String?

  enum CodingKeys: String, CodingKey {
    case status, message, warning
    case conversationIds = "conversation_ids"
    case newConversationId = "new_conversation_id"
  }
}

// MARK: - Folder Models

struct Folder: Codable, Identifiable {
  let id: String
  var name: String
  var description: String?
  var color: String
  let createdAt: Date
  let updatedAt: Date
  var order: Int
  let isDefault: Bool
  let isSystem: Bool
  let categoryMapping: String?
  let conversationCount: Int

  enum CodingKeys: String, CodingKey {
    case id, name, description, color, order
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case isDefault = "is_default"
    case isSystem = "is_system"
    case categoryMapping = "category_mapping"
    case conversationCount = "conversation_count"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    name = try container.decode(String.self, forKey: .name)
    description = try container.decodeIfPresent(String.self, forKey: .description)
    color = try container.decodeIfPresent(String.self, forKey: .color) ?? "#6B7280"
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
    updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt) ?? Date()
    order = try container.decodeIfPresent(Int.self, forKey: .order) ?? 0
    isDefault = try container.decodeIfPresent(Bool.self, forKey: .isDefault) ?? false
    isSystem = try container.decodeIfPresent(Bool.self, forKey: .isSystem) ?? false
    categoryMapping = try container.decodeIfPresent(String.self, forKey: .categoryMapping)
    conversationCount = try container.decodeIfPresent(Int.self, forKey: .conversationCount) ?? 0
  }
}

struct CreateFolderRequest: Encodable {
  let name: String
  let description: String?
  let color: String?
}

struct UpdateFolderRequest: Encodable {
  let name: String?
  let description: String?
  let color: String?
  let order: Int?
}

struct MoveToFolderRequest: Encodable {
  let folderId: String?

  enum CodingKeys: String, CodingKey {
    case folderId = "folder_id"
  }
}
// MARK: - Memory Models

enum MemoryCategory: String, Codable, CaseIterable {
  case system
  case interesting
  case manual
  case workflow

  var displayName: String {
    switch self {
    case .system: return "About You"
    case .interesting: return "Insights"
    case .manual: return "Manual"
    case .workflow: return "Workflow"
    }
  }

  var icon: String {
    switch self {
    case .system: return "person"
    case .interesting: return "lightbulb"
    case .manual: return "square.and.pencil"
    case .workflow: return "arrow.triangle.branch"
    }
  }

  /// Adapter from the generated wire enum (OmiAPI.MemoryCategory). The backend
  /// exposes a wider enum than the desktop renders; unknown values collapse to
  /// `.system` so the row still decodes.
  init(_ wire: OmiAPI.MemoryCategory) {
    self = MemoryCategory(rawValue: wire.rawValue) ?? .system
  }
}

enum MemoryLayer: String, Codable, CaseIterable, Identifiable {
  case shortTerm = "short_term"
  case longTerm = "long_term"
  case archive

  init(from decoder: Decoder) throws {
    let container = try decoder.singleValueContainer()
    let rawValue = try container.decode(String.self)
    guard let layer = MemoryLayer(rawValue: rawValue) else {
      throw DecodingError.dataCorruptedError(
        in: container,
        debugDescription: "Unknown ServerMemory layer '\(rawValue)'"
      )
    }
    self = layer
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.singleValueContainer()
    try container.encode(rawValue)
  }

  var id: String { rawValue }

  var displayName: String {
    switch self {
    case .shortTerm: return "Short-term"
    case .longTerm: return "Long-term"
    case .archive: return "Archive"
    }
  }

  var icon: String {
    switch self {
    case .shortTerm: return "clock"
    case .longTerm: return "brain.head.profile"
    case .archive: return "archivebox"
    }
  }

  var isDefaultAccessible: Bool {
    self == .shortTerm || self == .longTerm
  }

  var layerInfoText: String {
    switch self {
    case .shortTerm:
      return
        "Recent observations from your activity. May decay or promote to Long-term when corroborated."
    case .longTerm:
      return
        "Durable facts Omi keeps long-term - stable details about you, your preferences, and your life."
    case .archive:
      return "Aged-out long-term memories. Hidden by default; search Archive to find them."
    }
  }
}

/// Reversible alias during WS-G client rename.
typealias MemoryTier = MemoryLayer

struct MemoryLayerScope: Equatable {
  let tiers: [MemoryLayer]
  let requiresArchiveAcknowledgement: Bool

  static let defaultAccess = MemoryLayerScope(
    tiers: [.shortTerm, .longTerm],
    requiresArchiveAcknowledgement: false
  )
  static let archiveOnly = MemoryLayerScope(
    tiers: [.archive],
    requiresArchiveAcknowledgement: true
  )
  static let allIncludingArchive = MemoryLayerScope(
    tiers: [.shortTerm, .longTerm, .archive],
    requiresArchiveAcknowledgement: true
  )

  var includesArchive: Bool { tiers.contains(.archive) }
  var sqlTierRawValues: [String] { tiers.map { $0.rawValue } }
}

/// Reversible alias during WS-G client rename.
typealias MemoryTierScope = MemoryLayerScope

private enum ServerMemoryAliasDecodeError {
  static func conflict(
    _ firstField: String,
    _ firstValue: String,
    _ secondField: String,
    _ secondValue: String,
    codingPath: [CodingKey]
  ) -> DecodingError {
    DecodingError.dataCorrupted(
      DecodingError.Context(
        codingPath: codingPath,
        debugDescription: "Conflicting ServerMemory aliases: \(firstField)=\(firstValue) differs from \(secondField)=\(secondValue)"
      )
    )
  }
}

struct ServerMemory: Decodable, Identifiable {
  let id: String
  let content: String
  let category: MemoryCategory
  let createdAt: Date
  let updatedAt: Date
  let capturedAt: Date?
  let expiresAt: Date?
  let tier: MemoryLayer
  let tierIsExplicit: Bool
  let conversationId: String?
  let reviewed: Bool
  let userReview: Bool?
  var visibility: String
  let manuallyAdded: Bool
  let scoring: String?
  let source: String?
  // New fields for parity with Advice
  let confidence: Double?
  let sourceApp: String?
  let contextSummary: String?
  let isRead: Bool
  let isDismissed: Bool
  // Tags for filtering (e.g., ["tips", "productivity"])
  let tags: [String]
  // Reasoning behind the memory/tip (from advice system)
  let reasoning: String?
  // Description of user's activity when memory was generated
  let currentActivity: String?
  // Input device name (microphone) for desktop transcriptions
  let inputDeviceName: String?
  // Window title when memory was extracted
  let windowTitle: String?
  // Capture-device provenance (optional; absent on legacy memories)
  let primaryCaptureDevice: String?
  let captureDeviceIds: [String]
  // Short headline for notification preview (advice/tips only)
  let headline: String?

  enum CodingKeys: String, CodingKey {
    case id, content, category, reviewed, visibility, scoring, source, confidence, tags, reasoning,
      headline, tier, layer
    case memoryId = "memory_id"
    case memoryTier = "memory_tier"
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case capturedAt = "captured_at"
    case expiresAt = "expires_at"
    case conversationId = "conversation_id"
    case userReview = "user_review"
    case manuallyAdded = "manually_added"
    case sourceApp = "source_app"
    case contextSummary = "context_summary"
    case isRead = "is_read"
    case isDismissed = "is_dismissed"
    case currentActivity = "current_activity"
    case inputDeviceName = "input_device_name"
    case windowTitle = "window_title"
    case primaryCaptureDevice = "primary_capture_device"
    case captureDeviceIds = "capture_device_ids"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    // Schema authority: OmiAPI.MemoryDB (generated from app-client OpenAPI).
    // The wire DTO validates backend-owned fields against the generated
    // contract, but its required fields (uid, id, createdAt, updatedAt) are
    // stricter than the legacy decoder which used decodeIfPresent for
    // tolerance. We try the wire DTO and fall back to the container for any
    // field it rejects, preserving the old tolerant behavior.
    let wire = try? OmiAPI.MemoryDB(from: decoder)

    // id / memory_id alias resolution: wire.id is the backend authority
    // (required String); memory_id is an optional legacy alias. Preserve the
    // silent-mismatch behavior from the legacy decoder.
    let idValue = try wire?.id ?? container.decodeIfPresent(String.self, forKey: .id)
    let memoryIdValue = try wire?.memoryId ?? container.decodeIfPresent(String.self, forKey: .memoryId)
    switch (idValue, memoryIdValue) {
    case let (.some(id), .some(memoryId)) where id != memoryId:
      self.id = id
    case let (.some(id), _):
      self.id = id
    case let (_, .some(memoryId)):
      self.id = memoryId
    case (.none, .none):
      throw DecodingError.keyNotFound(
        CodingKeys.id,
        DecodingError.Context(
          codingPath: container.codingPath,
          debugDescription: "ServerMemory requires either id or memory_id"
        )
      )
    }

    content = try wire?.content ?? container.decode(String.self, forKey: .content)
    category = wire?.category.map(MemoryCategory.init) ?? .system
    capturedAt = try container.decodeIfPresent(Date.self, forKey: .capturedAt)
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let std = ISO8601DateFormatter()
    let createdAtString = wire?.createdAt
    createdAt = (createdAtString.flatMap { f.date(from: $0) ?? std.date(from: $0) }) ?? capturedAt ?? Date()
    let updatedAtString = wire?.updatedAt
    updatedAt = (updatedAtString.flatMap { f.date(from: $0) ?? std.date(from: $0) }) ?? createdAt
    expiresAt = try container.decodeIfPresent(Date.self, forKey: .expiresAt)

    // layer / tier / memory_tier alias resolution. Prefer wire DTO fields
    // (schema-validated); fall back to container decoding when the wire DTO
    // could not be constructed (missing required fields like uid).
    let layerValue = try wire?.layer.flatMap(MemoryLayer.init(rawValue:))
      ?? container.decodeIfPresent(MemoryLayer.self, forKey: .layer)
    let tierValue = try container.decodeIfPresent(MemoryLayer.self, forKey: .tier)
    let memoryTierValue = try wire?.memoryTier.flatMap { MemoryLayer(rawValue: $0.rawValue) }
      ?? container.decodeIfPresent(MemoryLayer.self, forKey: .memoryTier)
    tierIsExplicit = layerValue != nil || tierValue != nil || memoryTierValue != nil

    let presentTierAliases: [(String, MemoryLayer)] = [
      layerValue.map { ("layer", $0) },
      tierValue.map { ("tier", $0) },
      memoryTierValue.map { ("memory_tier", $0) },
    ].compactMap { $0 }
    if presentTierAliases.count >= 2 {
      let first = presentTierAliases[0]
      for other in presentTierAliases.dropFirst() where other.1 != first.1 {
        throw ServerMemoryAliasDecodeError.conflict(
          first.0, first.1.rawValue, other.0, other.1.rawValue, codingPath: container.codingPath)
      }
    }

    switch (layerValue, tierValue, memoryTierValue) {
    case let (.some(layer), _, _):
      self.tier = layer
    case let (_, .some(tier), _):
      self.tier = tier
    case let (_, _, .some(memoryTier)):
      self.tier = memoryTier
    case (.none, .none, .none):
      self.tier = .longTerm
    }

    conversationId = wire?.conversationId
    reviewed = wire?.reviewed ?? false
    userReview = wire?.userReview
    visibility = wire?.visibility ?? "private"
    manuallyAdded = wire?.manuallyAdded ?? false
    scoring = wire?.scoring
    source = try container.decodeIfPresent(String.self, forKey: .source)
    confidence = wire?.captureConfidence
    sourceApp = wire?.appId
    contextSummary = try container.decodeIfPresent(String.self, forKey: .contextSummary)
    isRead = try container.decodeIfPresent(Bool.self, forKey: .isRead) ?? false
    isDismissed = try container.decodeIfPresent(Bool.self, forKey: .isDismissed) ?? false
    tags = wire?.tags ?? []
    reasoning = try container.decodeIfPresent(String.self, forKey: .reasoning)
    currentActivity = try container.decodeIfPresent(String.self, forKey: .currentActivity)
    inputDeviceName = try container.decodeIfPresent(String.self, forKey: .inputDeviceName)
    windowTitle = try container.decodeIfPresent(String.self, forKey: .windowTitle)
    primaryCaptureDevice = wire?.primaryCaptureDevice
    captureDeviceIds = wire?.captureDeviceIds ?? []
    headline = wire?.headline
  }

  var isPublic: Bool {
    visibility == "public"
  }

  /// Confidence as percentage string
  var confidenceString: String? {
    guard let confidence = confidence else { return nil }
    return "\(Int(confidence * 100))%"
  }

  /// Human-readable source name
  var sourceName: String? {
    guard let source = source else { return nil }
    switch source {
    case "screenshot": return "Screenshot"
    case "omi": return "OMI"
    case "desktop": return "Desktop"
    case "phone": return "Phone"
    case "frame": return "Frame"
    case "friend", "friend_com": return "Friend"
    case "apple_watch": return "Apple Watch"
    case "bee": return "Bee"
    case "plaud": return "Plaud"
    case "limitless": return "Limitless"
    case "screenpipe": return "Screenpipe"
    case "workflow": return "Integration"
    case "openglass": return "OpenGlass"
    default: return source.capitalized
    }
  }

  /// SF Symbol for source device
  var sourceIcon: String {
    guard let source = source else { return "questionmark.circle" }
    switch source {
    case "screenshot": return "camera.viewfinder"
    case "omi": return "wave.3.right.circle"
    case "desktop": return "desktopcomputer"
    case "phone": return "iphone"
    case "frame": return "eyeglasses"
    case "friend", "friend_com": return "person.wave.2"
    case "apple_watch": return "applewatch"
    case "bee": return "ant"
    case "plaud": return "mic"
    case "limitless": return "infinity"
    case "screenpipe": return "rectangle.on.rectangle"
    case "workflow": return "arrow.triangle.branch"
    case "openglass": return "eyeglasses"
    default: return "circle"
    }
  }

  /// Whether this memory is a tip (from advice system)
  var isTip: Bool {
    tags.contains("tips")
  }

  /// Get the tip subcategory (productivity, health, etc.) if this is a tip
  var tipCategory: String? {
    guard isTip else { return nil }
    let subcategories = ["productivity", "health", "communication", "learning", "other"]
    return tags.first { subcategories.contains($0) }
  }

  /// Icon for tip subcategory
  var tipCategoryIcon: String {
    switch tipCategory {
    case "productivity": return "chart.line.uptrend.xyaxis"
    case "health": return "heart.fill"
    case "communication": return "bubble.left.and.bubble.right.fill"
    case "learning": return "book.fill"
    case "other": return "lightbulb.fill"
    default: return "lightbulb.fill"
    }
  }
}

// MARK: - Force Process Conversation API

extension APIClient {

  /// Response from Python POST /v1/conversations (force-process)
  struct ForceProcessConversationResponse: Decodable {
    let conversation: ServerConversation
  }

  /// Force-process the current in-progress conversation on the Python backend.
  /// Endpoint: POST /v1/conversations (Python backend)
  /// This is the same endpoint the mobile app uses when stopping phone mic recording.
  /// The Python backend finds the in-progress conversation via Redis and processes it.
  /// Returns the processed conversation on success, nil on 404 (already processed).
  /// Throws on other errors.
  func forceProcessConversation() async throws -> ServerConversation? {
    struct EmptyBody: Encodable {}

    do {
      let response: ForceProcessConversationResponse = try await post(
        "v1/conversations",
        body: EmptyBody(),
        customBaseURL: nil
      )
      return response.conversation
    } catch APIError.httpError(statusCode: let statusCode, detail: _) where statusCode == 404 {
      // 404 = no in-progress conversation found — WS close handler already processed it
      return nil
    }
  }

  /// Finalize a specific backend conversation id. This avoids the global Redis-backed
  /// force-process endpoint, which can act on a newer in-progress recording after rotation.
  func finalizeConversation(id conversationId: String) async throws -> ServerConversation {
    struct EmptyBody: Encodable {}

    let response: ForceProcessConversationResponse = try await post(
      "v1/conversations/\(conversationId)/finalize",
      body: EmptyBody(),
      customBaseURL: nil
    )
    return response.conversation
  }
}

// MARK: - Create Conversation From Segments (on-device transcription upload)

extension APIClient {
  /// One transcript segment for the from-segments upload (matches backend DevTranscriptSegment).
  struct UploadSegment: Encodable {
    let text: String
    let speaker: String
    let speaker_id: Int?
    let is_user: Bool
    let person_id: String?
    let start: Double
    let end: Double
  }

  struct CreateConversationFromSegmentsRequest: Encodable {
    let transcript_segments: [UploadSegment]
    let source: String
    let started_at: String?  // ISO8601
    let finished_at: String?  // ISO8601
    let language: String
    let client_conversation_id: String?
  }

  struct CreateConversationFromSegmentsResponse: Decodable {
    let id: String
    let status: String
    let discarded: Bool

    enum CodingKeys: String, CodingKey {
      case id
      case status
      case discarded
    }

    init(from decoder: Decoder) throws {
      let container = try decoder.container(keyedBy: CodingKeys.self)
      id = try container.decode(String.self, forKey: .id)
      status = try container.decodeIfPresent(String.self, forKey: .status) ?? ConversationStatus.processing.rawValue
      discarded = try container.decodeIfPresent(Bool.self, forKey: .discarded) ?? false
    }
  }

  /// Upload an already-transcribed (on-device Parakeet) conversation to the backend so it is
  /// persisted, processed (memories/summaries), and synced to every device — the same pipeline a
  /// cloud-transcribed conversation goes through, without the live `/v4/listen` websocket.
  /// Endpoint: POST /v1/conversations/from-segments (Firebase-authed).
  func createConversationFromSegments(_ request: CreateConversationFromSegmentsRequest)
    async throws -> CreateConversationFromSegmentsResponse
  {
    let response: CreateConversationFromSegmentsResponse = try await post(
      "v1/conversations/from-segments", body: request, customBaseURL: nil)
    invalidateConversationsCountCache()
    return response
  }
}

// MARK: - Memories API

extension APIClient {
  private static let canonicalLifecycleExposedHeader = "X-Omi-Memory-Canonical-Lifecycle-Exposed"
  private static let deviceScopeSupportedHeader = "X-Omi-Memory-Device-Scope-Supported"

  struct MemoryListPage {
    let memories: [ServerMemory]
    let canonicalLifecycleExposed: Bool
    let deviceScopeSupported: Bool?
  }

  /// Fetches memories from the API with optional filtering
  func getMemories(
    limit: Int = 100,
    offset: Int = 0,
    category: String? = nil,
    tags: [String]? = nil,
    includeDismissed: Bool = false,
    deviceScope: String? = nil
  ) async throws -> [ServerMemory] {
    var endpoint = "v3/memories?limit=\(limit)&offset=\(offset)"
    if let category = category {
      endpoint += "&category=\(category)"
    }
    if let tags = tags, !tags.isEmpty {
      endpoint += "&tags=\(tags.joined(separator: ","))"
    }
    if includeDismissed {
      endpoint += "&include_dismissed=true"
    }
    if let deviceScope = deviceScope {
      endpoint += "&device_scope=\(deviceScope)"
    }
    return try await get(endpoint)
  }

  /// Fetches memories plus server-authoritative capability headers.
  func getMemoriesPage(
    limit: Int = 100,
    offset: Int = 0,
    category: String? = nil,
    tags: [String]? = nil,
    includeDismissed: Bool = false,
    deviceScope: String? = nil
  ) async throws -> MemoryListPage {
    var endpoint = "v3/memories?limit=\(limit)&offset=\(offset)"
    if let category = category {
      endpoint += "&category=\(category)"
    }
    if let tags = tags, !tags.isEmpty {
      endpoint += "&tags=\(tags.joined(separator: ","))"
    }
    if includeDismissed {
      endpoint += "&include_dismissed=true"
    }
    if let deviceScope = deviceScope {
      endpoint += "&device_scope=\(deviceScope)"
    }

    let url = URL(string: baseURL + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)
    return try await performMemoryListRequest(request, retriedAuth: false)
  }

  private func performMemoryListRequest(_ request: URLRequest, retriedAuth: Bool) async throws -> MemoryListPage {
    let (data, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIError.invalidResponse
    }

    if httpResponse.statusCode == 401, !retriedAuth {
      let authService = await MainActor.run { AuthService.shared }
      var retry = request
      retry.setValue(try await authService.getAuthHeader(forceRefresh: true), forHTTPHeaderField: "Authorization")
      return try await performMemoryListRequest(retry, retriedAuth: true)
    }
    if httpResponse.statusCode == 401 {
      throw APIError.unauthorized
    }

    guard (200...299).contains(httpResponse.statusCode) else {
      let detail = Self.extractErrorDetail(from: data)
      throw APIError.httpError(statusCode: httpResponse.statusCode, detail: detail)
    }

    let memories = try decoder.decode([ServerMemory].self, from: data)
    let lifecycleHeader = httpResponse.value(forHTTPHeaderField: Self.canonicalLifecycleExposedHeader)
    let canonicalLifecycleExposed = lifecycleHeader == "true"
    let deviceScopeHeader = httpResponse.value(forHTTPHeaderField: Self.deviceScopeSupportedHeader)
    let deviceScopeSupported = deviceScopeHeader.map { $0.caseInsensitiveCompare("true") == .orderedSame }
    return MemoryListPage(
      memories: memories,
      canonicalLifecycleExposed: canonicalLifecycleExposed,
      deviceScopeSupported: deviceScopeSupported
    )
  }

  /// Creates a new memory (manual or extracted)
  func createMemory(
    content: String,
    visibility: String = "private",
    category: MemoryCategory? = nil,
    confidence: Double? = nil,
    sourceApp: String? = nil,
    contextSummary: String? = nil,
    tags: [String] = [],
    reasoning: String? = nil,
    currentActivity: String? = nil,
    source: String? = nil,
    windowTitle: String? = nil,
    headline: String? = nil
  ) async throws -> CreateMemoryResponse {
    struct CreateRequest: Encodable {
      let content: String
      let visibility: String
      let category: String?
      let confidence: Double?
      let sourceApp: String?
      let contextSummary: String?
      let tags: [String]
      let reasoning: String?
      let currentActivity: String?
      let source: String?
      let windowTitle: String?
      let headline: String?

      enum CodingKeys: String, CodingKey {
        case content, visibility, category, confidence, tags, reasoning, source, headline
        case sourceApp = "source_app"
        case contextSummary = "context_summary"
        case currentActivity = "current_activity"
        case windowTitle = "window_title"
      }
    }
    let body = CreateRequest(
      content: content,
      visibility: visibility,
      category: category?.rawValue,
      confidence: confidence,
      sourceApp: sourceApp,
      contextSummary: contextSummary,
      tags: tags,
      reasoning: reasoning,
      currentActivity: currentActivity,
      source: source,
      windowTitle: windowTitle,
      headline: headline
    )
    return try await post("v3/memories", body: body)
  }

  /// Max memories per POST /v3/memories/batch call. Must match the
  /// `MEMORIES_BATCH_MAX` constant in backend/routers/memories.py.
  static let memoriesBatchMaxSize = 100
  static let memoryImportBatchMaxSize = 100

  /// Creates many product memories in a single HTTP call.
  ///
  /// Caller is responsible for chunking input into groups of at most
  /// `memoriesBatchMaxSize`. Returns the created count from the server.
  func createMemoriesBatch(_ memories: [MemoryBatchItem]) async throws -> BatchMemoriesResponse {
    precondition(
      memories.count <= Self.memoriesBatchMaxSize,
      "createMemoriesBatch received \(memories.count) memories, max is \(Self.memoriesBatchMaxSize)"
    )
    struct BatchRequest: Encodable {
      let memories: [MemoryBatchItem]
    }
    let body = BatchRequest(memories: memories)
    return try await post("v3/memories/batch", body: body)
  }

  func createMemoryImportBatch(_ batch: ImportEvidenceBatch) async throws -> ImportEvidenceBatchResponse {
    precondition(
      batch.items.count <= Self.memoryImportBatchMaxSize,
      "createMemoryImportBatch received \(batch.items.count) artifacts, max is \(Self.memoryImportBatchMaxSize)"
    )
    return try await post("v3/memory-imports/batch", body: batch, includeBYOK: false)
  }

  /// Deletes a memory by ID
  func deleteMemory(id: String) async throws {
    try await delete("v3/memories/\(id)")
  }

  /// Edits a memory's content
  func editMemory(id: String, content: String) async throws {
    struct EditRequest: Encodable {
      let value: String
    }
    let body = EditRequest(value: content)
    let _: MemoryStatusResponse = try await patch("v3/memories/\(id)", body: body)
  }

  /// Updates a memory's visibility
  func updateMemoryVisibility(id: String, visibility: String) async throws {
    struct VisibilityRequest: Encodable {
      let value: String
    }
    let body = VisibilityRequest(value: visibility)
    let _: MemoryStatusResponse = try await patch("v3/memories/\(id)/visibility", body: body)
  }

  /// Updates memory read/dismissed status
  func updateMemoryReadStatus(id: String, isRead: Bool? = nil, isDismissed: Bool? = nil)
    async throws -> ServerMemory
  {
    struct UpdateReadRequest: Encodable {
      let isRead: Bool?
      let isDismissed: Bool?

      enum CodingKeys: String, CodingKey {
        case isRead = "is_read"
        case isDismissed = "is_dismissed"
      }
    }
    let body = UpdateReadRequest(isRead: isRead, isDismissed: isDismissed)
    return try await patch("v3/memories/\(id)/read", body: body)
  }

  /// Marks all memories as read
  func markAllMemoriesRead() async throws {
    let _: MemoryStatusResponse = try await post("v3/memories/mark-all-read", body: EmptyBody())
  }

  /// Layer/archive scoped bulk read-state mutations remain disabled until backend semantics exist.
  func markAllMemoriesRead(scope: MemoryLayerScope) async throws {
    throw APIError.unsupportedTierScopedBulkMutation("read-state updates")
  }

  /// Updates visibility of all memories
  func updateAllMemoriesVisibility(visibility: String) async throws {
    struct VisibilityRequest: Encodable {
      let value: String
    }
    let body = VisibilityRequest(value: visibility)
    let _: MemoryStatusResponse = try await patch("v3/memories/visibility", body: body)
  }

  /// Updates visibility of all default-scope memories.
  /// Layer/archive scoped bulk mutations remain disabled until backend semantics exist.
  func updateAllMemoriesVisibility(scope: MemoryLayerScope, visibility: String) async throws {
    if scope == .defaultAccess {
      try await updateAllMemoriesVisibility(visibility: visibility)
      return
    }
    throw APIError.unsupportedTierScopedBulkMutation("visibility updates")
  }

  /// Deletes all memories
  func deleteAllMemories() async throws {
    try await delete("v3/memories")
  }

  /// Deletes all default-scope memories.
  /// Layer/archive scoped bulk mutations remain disabled until backend semantics exist.
  func deleteAllMemories(scope: MemoryLayerScope) async throws {
    if scope == .defaultAccess {
      try await deleteAllMemories()
      return
    }
    throw APIError.unsupportedTierScopedBulkMutation("deletion")
  }

  // MARK: - PATCH helper

  func patch<T: Decodable, B: Encodable>(
    _ endpoint: String,
    body: B,
    requireAuth: Bool = true,
    customBaseURL: String? = nil
  ) async throws -> T {
    let base = customBaseURL ?? baseURL
    let url = URL(string: base + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth)
    request.httpBody = try JSONEncoder().encode(body)

    return try await performPatchRequest(request)
  }

  private func performPatchRequest<T: Decodable>(_ request: URLRequest) async throws -> T {
    // Delegate to performRequest so PATCH gets the same 401 refresh-and-retry as
    // GET/POST. PATCH previously threw `.unauthorized` on the first 401, which
    // surfaced as a user-visible failure (e.g. the onboarding language step)
    // whenever the ID token was momentarily stale right after sign-in.
    return try await performRequest(request)
  }
}

struct CreateMemoryResponse: Codable {
  let id: String
  let message: String?
}

/// One item in a POST /v3/memories/batch payload. Mirrors the `Memory` model
/// in `backend/models/memories.py`. The server honors `category`, so batch
/// imports default to `.system` ("About You") rather than landing in "Manual".
struct MemoryBatchItem: Encodable {
  let content: String
  let visibility: String
  let category: String
  let tags: [String]
  let headline: String?
  let source: String?
  let windowTitle: String?

  init(
    content: String,
    visibility: String = "private",
    category: MemoryCategory = .system,
    tags: [String] = [],
    headline: String? = nil,
    source: String? = nil,
    windowTitle: String? = nil
  ) {
    self.content = content
    self.visibility = visibility
    self.category = category.rawValue
    self.tags = tags
    self.headline = headline
    self.source = source
    self.windowTitle = windowTitle
  }

  enum CodingKeys: String, CodingKey {
    case content, visibility, category, tags, headline, source
    case windowTitle = "window_title"
  }
}

/// Response from POST /v3/memories/batch. The server returns the full
/// created memories list; we only care about `createdCount` for onboarding
/// telemetry, but keep `memories` available for future callers.
struct BatchMemoriesResponse: Decodable {
  let memories: [BatchMemory]
  let createdCount: Int

  enum CodingKeys: String, CodingKey {
    case memories
    case createdCount = "created_count"
  }

  struct BatchMemory: Decodable {
    let id: String
    let content: String
  }
}

struct ImportEvidenceBatch: Encodable {
  let sourceType: String
  let importRunId: String?
  let sourceAccountHash: String?
  let importerVersion: String
  let extractorVersion: String?
  let items: [ImportEvidenceBatchItem]

  init(
    sourceType: String,
    importRunId: String? = nil,
    sourceAccountHash: String? = nil,
    importerVersion: String = "desktop-import-v1",
    extractorVersion: String? = nil,
    items: [ImportEvidenceBatchItem]
  ) {
    self.sourceType = sourceType
    self.importRunId = importRunId
    self.sourceAccountHash = sourceAccountHash
    self.importerVersion = importerVersion
    self.extractorVersion = extractorVersion
    self.items = items
  }

  enum CodingKeys: String, CodingKey {
    case sourceType = "source_type"
    case importRunId = "import_run_id"
    case sourceAccountHash = "source_account_hash"
    case importerVersion = "importer_version"
    case extractorVersion = "extractor_version"
    case items
  }
}

struct ImportEvidenceBatchItem: Encodable, Hashable {
  let externalId: String?
  let occurredAt: Date?
  let title: String?
  let snippet: String?
  let content: String?
  let contentHash: String?
  let metadata: [String: String]
  let clientDeviceId: String?

  init(
    externalId: String? = nil,
    occurredAt: Date? = nil,
    title: String? = nil,
    snippet: String? = nil,
    content: String? = nil,
    contentHash: String? = nil,
    metadata: [String: String] = [:],
    clientDeviceId: String? = nil
  ) {
    self.externalId = externalId
    self.occurredAt = occurredAt
    self.title = title
    self.snippet = snippet
    self.content = content
    self.contentHash = contentHash
    self.metadata = metadata
    self.clientDeviceId = clientDeviceId
  }

  enum CodingKeys: String, CodingKey {
    case externalId = "external_id"
    case occurredAt = "occurred_at"
    case title
    case snippet
    case content
    case contentHash = "content_hash"
    case metadata
    case clientDeviceId = "client_device_id"
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.container(keyedBy: CodingKeys.self)
    try container.encodeIfPresent(externalId, forKey: .externalId)
    if let occurredAt {
      let formatter = ISO8601DateFormatter()
      formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
      try container.encode(formatter.string(from: occurredAt), forKey: .occurredAt)
    }
    try container.encodeIfPresent(title, forKey: .title)
    try container.encodeIfPresent(snippet, forKey: .snippet)
    try container.encodeIfPresent(content, forKey: .content)
    try container.encodeIfPresent(contentHash, forKey: .contentHash)
    try container.encode(metadata, forKey: .metadata)
    try container.encodeIfPresent(clientDeviceId, forKey: .clientDeviceId)
  }
}

struct ImportEvidenceBatchResponse: Decodable {
  let runId: String
  let artifactsReceived: Int
  let artifactsCreated: Int
  let artifactsDeduped: Int
  let candidatesCreated: Int
  let status: String

  enum CodingKeys: String, CodingKey {
    case runId = "run_id"
    case artifactsReceived = "artifacts_received"
    case artifactsCreated = "artifacts_created"
    case artifactsDeduped = "artifacts_deduped"
    case candidatesCreated = "candidates_created"
    case status
  }
}

struct MemoryStatusResponse: Codable {
  let status: String
}

// MARK: - Action Items API

/// Response wrapper for paginated action items list
/// Accepts both "action_items" (/v1/action-items) and "items" (/v1/staged-tasks) keys.
struct ActionItemsListResponse: Decodable {
  let items: [TaskActionItem]
  let hasMore: Bool

  enum CodingKeys: String, CodingKey {
    case actionItems = "action_items"
    case items
    case hasMore = "has_more"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    if let actionItems = try container.decodeIfPresent([TaskActionItem].self, forKey: .actionItems)
    {
      self.items = actionItems
    } else {
      self.items = try container.decode([TaskActionItem].self, forKey: .items)
    }
    self.hasMore = try container.decode(Bool.self, forKey: .hasMore)
  }
}

extension APIClient {

  /// Fetches action items from the API with optional filtering and sorting
  func getActionItems(
    limit: Int = 100,
    offset: Int = 0,
    completed: Bool? = nil,
    startDate: Date? = nil,
    endDate: Date? = nil,
    dueStartDate: Date? = nil,
    dueEndDate: Date? = nil,
    sortBy: String? = nil,
    deleted: Bool? = nil
  ) async throws -> ActionItemsListResponse {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

    var queryItems: [String] = [
      "limit=\(limit)",
      "offset=\(offset)",
    ]

    if let completed = completed {
      queryItems.append("completed=\(completed)")
    }

    if let startDate = startDate {
      queryItems.append("start_date=\(formatter.string(from: startDate))")
    }

    if let endDate = endDate {
      queryItems.append("end_date=\(formatter.string(from: endDate))")
    }

    if let dueStartDate = dueStartDate {
      queryItems.append("due_start_date=\(formatter.string(from: dueStartDate))")
    }

    if let dueEndDate = dueEndDate {
      queryItems.append("due_end_date=\(formatter.string(from: dueEndDate))")
    }

    if let sortBy = sortBy {
      queryItems.append("sort_by=\(sortBy)")
    }

    if let deleted = deleted {
      queryItems.append("deleted=\(deleted)")
    }

    let endpoint = "v1/action-items?\(queryItems.joined(separator: "&"))"
    return try await get(endpoint)
  }

  /// Fetches one action item by backend ID.
  func getActionItem(id: String) async throws -> TaskActionItem {
    try await get("v1/action-items/\(id)")
  }

  /// Updates an action item
  func updateActionItem(
    id: String,
    completed: Bool? = nil,
    description: String? = nil,
    dueAt: Date? = nil,
    clearDueAt: Bool = false,
    priority: String? = nil,
    metadata: [String: Any]? = nil,
    goalId: String? = nil,
    relevanceScore: Int? = nil,
    recurrenceRule: String? = nil
  ) async throws -> TaskActionItem {
    struct UpdateRequest: Encodable {
      let completed: Bool?
      let description: String?
      let dueAt: String?
      let includeDueAt: Bool
      let clearDueAt: Bool
      let priority: String?
      let metadata: String?
      let goalId: String?
      let relevanceScore: Int?
      let recurrenceRule: String?

      enum CodingKeys: String, CodingKey {
        case completed, description, priority, metadata
        case dueAt = "due_at"
        case clearDueAt = "clear_due_at"
        case goalId = "goal_id"
        case relevanceScore = "relevance_score"
        case recurrenceRule = "recurrence_rule"
      }

      func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encodeIfPresent(completed, forKey: .completed)
        try container.encodeIfPresent(description, forKey: .description)
        if includeDueAt {
          if let dueAt {
            try container.encode(dueAt, forKey: .dueAt)
          } else {
            try container.encodeNil(forKey: .dueAt)
          }
        }
        if clearDueAt {
          try container.encode(true, forKey: .clearDueAt)
        }
        try container.encodeIfPresent(priority, forKey: .priority)
        try container.encodeIfPresent(metadata, forKey: .metadata)
        try container.encodeIfPresent(goalId, forKey: .goalId)
        try container.encodeIfPresent(relevanceScore, forKey: .relevanceScore)
        try container.encodeIfPresent(recurrenceRule, forKey: .recurrenceRule)
      }
    }

    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

    var metadataString: String? = nil
    if let metadata = metadata {
      if let data = try? JSONSerialization.data(withJSONObject: metadata),
        let str = String(data: data, encoding: .utf8)
      {
        metadataString = str
      }
    }

    let request = UpdateRequest(
      completed: completed,
      description: description,
      dueAt: dueAt.map { formatter.string(from: $0) },
      includeDueAt: clearDueAt || dueAt != nil,
      clearDueAt: clearDueAt,
      priority: priority,
      metadata: metadataString,
      goalId: goalId,
      relevanceScore: relevanceScore,
      recurrenceRule: recurrenceRule
    )

    return try await patch("v1/action-items/\(id)", body: request)
  }

  /// Deletes an action item
  func deleteActionItem(id: String) async throws {
    try await delete("v1/action-items/\(id)")
  }

  /// Creates a new action item
  func createActionItem(
    description: String,
    dueAt: Date? = nil,
    source: String? = nil,
    priority: String? = nil,
    category: String? = nil,
    metadata: [String: Any]? = nil,
    relevanceScore: Int? = nil,
    recurrenceRule: String? = nil,
    recurrenceParentId: String? = nil
  ) async throws -> TaskActionItem {
    struct CreateRequest: Encodable {
      let description: String
      let dueAt: String?
      let source: String?
      let priority: String?
      let category: String?
      let metadata: String?
      let relevanceScore: Int?
      let recurrenceRule: String?
      let recurrenceParentId: String?

      enum CodingKeys: String, CodingKey {
        case description
        case dueAt = "due_at"
        case source, priority, category, metadata
        case relevanceScore = "relevance_score"
        case recurrenceRule = "recurrence_rule"
        case recurrenceParentId = "recurrence_parent_id"
      }
    }

    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

    var metadataString: String? = nil
    if let metadata = metadata {
      if let data = try? JSONSerialization.data(withJSONObject: metadata),
        let str = String(data: data, encoding: .utf8)
      {
        metadataString = str
      }
    }

    let request = CreateRequest(
      description: description,
      dueAt: dueAt.map { formatter.string(from: $0) },
      source: source,
      priority: priority,
      category: category,
      metadata: metadataString,
      relevanceScore: relevanceScore,
      recurrenceRule: recurrenceRule,
      recurrenceParentId: recurrenceParentId
    )

    return try await post("v1/action-items", body: request)
  }

  /// Batch update relevance scores for multiple action items
  func batchUpdateScores(_ scores: [(id: String, score: Int)]) async throws {
    struct ScoreUpdate: Encodable {
      let id: String
      let relevance_score: Int
    }
    struct BatchRequest: Encodable {
      let scores: [ScoreUpdate]
    }
    struct StatusResponse: Decodable {
      let status: String
    }
    let request = BatchRequest(
      scores: scores.map { ScoreUpdate(id: $0.id, relevance_score: $0.score) })
    let _: StatusResponse = try await patch("v1/action-items/batch-scores", body: request)
  }

  /// Batch update sort orders and indent levels for multiple action items
  func batchUpdateSortOrders(_ updates: [(id: String, sortOrder: Int, indentLevel: Int)])
    async throws
  {
    struct SortUpdate: Encodable {
      let id: String
      let sort_order: Int
      let indent_level: Int
    }
    struct BatchRequest: Encodable {
      let items: [SortUpdate]
    }
    struct StatusResponse: Decodable {
      let status: String
    }
    let request = BatchRequest(
      items: updates.map {
        SortUpdate(id: $0.id, sort_order: $0.sortOrder, indent_level: $0.indentLevel)
      })
    let _: StatusResponse = try await patch("v1/action-items/batch", body: request)
  }

  // MARK: - Task Sharing

  /// Shares tasks and returns a shareable URL
  func shareTasks(taskIds: [String]) async throws -> ShareTasksResponse {
    struct ShareRequest: Encodable {
      let taskIds: [String]
      enum CodingKeys: String, CodingKey {
        case taskIds = "task_ids"
      }
    }
    return try await post("v1/action-items/share", body: ShareRequest(taskIds: taskIds))
  }

}

/// Response types for task sharing
struct ShareTasksResponse: Codable {
  let url: String
  let token: String
}
// MARK: - Staged Tasks API

extension APIClient {

  /// Creates a new staged task
  func createStagedTask(
    description: String,
    dueAt: Date? = nil,
    source: String? = nil,
    priority: String? = nil,
    category: String? = nil,
    metadata: [String: Any]? = nil,
    relevanceScore: Int? = nil
  ) async throws -> TaskActionItem {
    struct CreateRequest: Encodable {
      let description: String
      let dueAt: String?
      let source: String?
      let priority: String?
      let category: String?
      let metadata: String?
      let relevanceScore: Int?

      enum CodingKeys: String, CodingKey {
        case description
        case dueAt = "due_at"
        case source, priority, category, metadata
        case relevanceScore = "relevance_score"
      }
    }

    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

    var metadataString: String? = nil
    if let metadata = metadata {
      if let data = try? JSONSerialization.data(withJSONObject: metadata),
        let str = String(data: data, encoding: .utf8)
      {
        metadataString = str
      }
    }

    let request = CreateRequest(
      description: description,
      dueAt: dueAt.map { formatter.string(from: $0) },
      source: source,
      priority: priority,
      category: category,
      metadata: metadataString,
      relevanceScore: relevanceScore
    )

    return try await post("v1/staged-tasks", body: request)
  }

  /// Fetches staged tasks ordered by relevance score
  func getStagedTasks(limit: Int = 100, offset: Int = 0) async throws -> ActionItemsListResponse {
    let params = "limit=\(limit)&offset=\(offset)"
    return try await get("v1/staged-tasks?\(params)")
  }

  /// Hard-deletes a staged task
  func deleteStagedTask(id: String) async throws {
    try await delete("v1/staged-tasks/\(id)")
  }

  /// Batch update relevance scores for staged tasks
  func batchUpdateStagedScores(_ scores: [(id: String, score: Int)]) async throws {
    struct ScoreUpdate: Encodable {
      let id: String
      let relevance_score: Int
    }
    struct BatchRequest: Encodable {
      let scores: [ScoreUpdate]
    }
    struct StatusResponse: Decodable {
      let status: String
    }
    let request = BatchRequest(
      scores: scores.map { ScoreUpdate(id: $0.id, relevance_score: $0.score) })
    let _: StatusResponse = try await patch("v1/staged-tasks/batch-scores", body: request)
  }

  /// Promotes the top-ranked staged task to action_items
  func promoteTopStagedTask() async throws -> PromoteResponse {
    return try await post("v1/staged-tasks/promote")
  }

  /// One-time migration of existing AI tasks to staged_tasks
  func migrateStagedTasks() async throws {
    struct StatusResponse: Decodable { let status: String }
    let _: StatusResponse = try await post("v1/staged-tasks/migrate")
  }

  /// Migrate conversation-extracted action items (no source field) to staged_tasks
  func migrateConversationItemsToStaged() async throws {
    struct MigrateResponse: Decodable {
      let status: String
      let migrated: Int
      let deleted: Int
    }
    let _: MigrateResponse = try await post("v1/staged-tasks/migrate-conversation-items")
  }
}

/// Response for staged task promotion
struct PromoteResponse: Codable {
  let promoted: Bool
  let reason: String?
  let promotedTask: TaskActionItem?

  enum CodingKeys: String, CodingKey {
    case promoted, reason
    case promotedTask = "promoted_task"
  }
}

// MARK: - Goals API

extension APIClient {

  /// Fetches all active goals (up to 4). Uses 5-second cache to deduplicate parallel calls.
  func getGoals() async throws -> [Goal] {
    if let cache = goalsCache, let time = goalsCacheTime, Date().timeIntervalSince(time) < 5 {
      return cache
    }
    let goals: [Goal] = try await get("v1/goals/all")
    goalsCache = goals
    goalsCacheTime = Date()
    return goals
  }

  /// Creates a new goal
  func createGoal(
    title: String,
    description: String? = nil,
    goalType: GoalType = .boolean,
    targetValue: Double = 1.0,
    currentValue: Double = 0.0,
    minValue: Double = 0.0,
    maxValue: Double = 100.0,
    unit: String? = nil,
    source: String? = nil
  ) async throws -> Goal {
    struct CreateGoalRequest: Encodable {
      let title: String
      let description: String?
      let goalType: String
      let targetValue: Double
      let currentValue: Double
      let minValue: Double
      let maxValue: Double
      let unit: String?
      let source: String?

      enum CodingKeys: String, CodingKey {
        case title, description, unit, source
        case goalType = "goal_type"
        case targetValue = "target_value"
        case currentValue = "current_value"
        case minValue = "min_value"
        case maxValue = "max_value"
      }
    }

    let request = CreateGoalRequest(
      title: title,
      description: description,
      goalType: goalType.rawValue,
      targetValue: targetValue,
      currentValue: currentValue,
      minValue: minValue,
      maxValue: maxValue,
      unit: unit,
      source: source
    )

    let goal: Goal = try await post("v1/goals", body: request)
    goalsCache = nil
    return goal
  }

  /// Updates a goal's progress
  func updateGoalProgress(goalId: String, currentValue: Double) async throws -> Goal {
    let url = URL(string: baseURL + "v1/goals/\(goalId)/progress?current_value=\(currentValue)")!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)

    let (data, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse,
      (200...299).contains(httpResponse.statusCode)
    else {
      throw APIError.httpError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
    }

    let goal = try decoder.decode(Goal.self, from: data)
    goalsCache = nil
    return goal
  }

  /// Updates editable goal fields.
  func updateGoal(goalId: String, title: String, currentValue: Double, targetValue: Double)
    async throws -> Goal
  {
    struct UpdateGoalRequest: Encodable {
      let title: String
      let currentValue: Double
      let targetValue: Double

      enum CodingKeys: String, CodingKey {
        case title
        case currentValue = "current_value"
        case targetValue = "target_value"
      }
    }

    let request = UpdateGoalRequest(
      title: title,
      currentValue: currentValue,
      targetValue: targetValue
    )

    let goal: Goal = try await patch("v1/goals/\(goalId)", body: request)
    goalsCache = nil
    return goal
  }

  /// Gets completed goals for history
  func getCompletedGoals() async throws -> [Goal] {
    let goals: [Goal] = try await get("v1/goals/completed")
    return goals
  }

  /// Completes a goal (marks as inactive with completed_at)
  func completeGoal(id: String) async throws -> Goal {
    struct CompleteGoalRequest: Encodable {
      let is_active: Bool
      let completed_at: String
    }

    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let body = CompleteGoalRequest(
      is_active: false,
      completed_at: formatter.string(from: Date())
    )

    let url = URL(string: baseURL + "v1/goals/\(id)")!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)
    request.httpBody = try JSONEncoder().encode(body)

    let (data, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse,
      (200...299).contains(httpResponse.statusCode)
    else {
      throw APIError.httpError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
    }

    let goal = try decoder.decode(Goal.self, from: data)
    goalsCache = nil
    return goal
  }

  /// Deletes a goal
  func deleteGoal(id: String) async throws {
    try await delete("v1/goals/\(id)")
    goalsCache = nil
  }

  /// Get all scores (daily, weekly, overall) with default tab selection
  func getScores(date: Date? = nil) async throws -> ScoreResponse {
    var endpoint = "v1/scores"
    if let date = date {
      let formatter = DateFormatter()
      formatter.dateFormat = "yyyy-MM-dd"
      endpoint += "?date=\(formatter.string(from: date))"
    }
    return try await get(endpoint)
  }
}

// MARK: - Action Item Model (Standalone)

/// Standalone action item stored in Firestore subcollection
/// Different from ActionItem which is embedded in conversation structured data
struct TaskActionItem: Codable, Identifiable, Equatable {
  let id: String
  let description: String
  let completed: Bool
  let createdAt: Date
  let updatedAt: Date?
  let dueAt: Date?
  let completedAt: Date?
  let conversationId: String?
  /// Source of the task: "screenshot", "transcription:omi", "transcription:desktop", "manual"
  let source: String?
  /// Priority: "high", "medium", "low"
  let priority: String?
  /// JSON metadata string containing extra info like source_app, confidence
  let metadata: String?
  /// Classification category: personal, work, feature, bug, code, research, communication, finance, health, other
  let category: String?
  /// Soft-delete: true if this task has been deleted by AI dedup
  let deleted: Bool?
  /// Who deleted: "user", "ai_dedup"
  let deletedBy: String?
  /// When the task was soft-deleted
  let deletedAt: Date?
  /// AI reason for deletion (dedup explanation)
  let deletedReason: String?
  /// ID of the task that was kept instead of this one
  let keptTaskId: String?
  /// ID of the goal this task is linked to
  let goalId: String?
  /// Whether this task was promoted from staged_tasks
  let fromStaged: Bool?
  /// Recurrence rule: "daily", "weekdays", "weekly", "biweekly", "monthly"
  let recurrenceRule: String?
  /// ID of original parent task in recurrence chain
  let recurrenceParentId: String?

  // Ordering (synced to backend)
  var sortOrder: Int?  // Sort position within category
  var indentLevel: Int?  // 0-3 indent depth

  // Prioritization (stored locally, not synced to backend)
  var relevanceScore: Int?  // 0-100 relevance score from TaskPrioritizationService

  // Desktop extraction context (stored locally, not synced to backend)
  var contextSummary: String?  // Summary of screen context at extraction time
  var currentActivity: String?  // What user was doing when task was detected
  var agentEditedFiles: [String]?  // Files the agent previously edited

  // Agent execution tracking (stored locally, not synced to backend)
  var agentStatus: String?  // nil, "pending", "processing", "completed", "failed"
  var agentPrompt: String?  // The prompt sent to Claude
  var agentPlan: String?  // Claude's response/plan
  var agentSessionId: String?  // tmux session name for the Claude session
  var agentStartedAt: Date?  // When agent was launched
  var agentCompletedAt: Date?  // When agent finished

  // Chat session for task-scoped AI chat (stored locally, not synced to backend)
  var chatSessionId: String?

  /// Whether this task has an active recurrence rule
  var isRecurring: Bool {
    guard let rule = recurrenceRule, !rule.isEmpty else { return false }
    return true
  }

  /// Custom Equatable: compares only display-relevant fields.
  /// Skips `metadata` (JSON key ordering is non-deterministic after SQLite round-trip),
  /// `updatedAt` (set to Date() when nil on sync), and fields lost through SQLite.
  static func == (lhs: TaskActionItem, rhs: TaskActionItem) -> Bool {
    lhs.id == rhs.id && lhs.description == rhs.description && lhs.completed == rhs.completed
      && lhs.createdAt == rhs.createdAt && lhs.dueAt == rhs.dueAt && lhs.source == rhs.source
      && lhs.priority == rhs.priority && lhs.category == rhs.category && lhs.deleted == rhs.deleted
      && lhs.deletedBy == rhs.deletedBy && lhs.goalId == rhs.goalId
      && lhs.recurrenceRule == rhs.recurrenceRule
  }

  enum CodingKeys: String, CodingKey {
    case id, description, completed, source, priority, metadata, category, deleted
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case dueAt = "due_at"
    case completedAt = "completed_at"
    case conversationId = "conversation_id"
    case deletedBy = "deleted_by"
    case deletedAt = "deleted_at"
    case deletedReason = "deleted_reason"
    case keptTaskId = "kept_task_id"
    case goalId = "goal_id"
    case fromStaged = "from_staged"
    case recurrenceRule = "recurrence_rule"
    case recurrenceParentId = "recurrence_parent_id"
    case sortOrder = "sort_order"
    case indentLevel = "indent_level"
    case relevanceScore = "relevance_score"
  }

  /// Memberwise initializer for creating instances programmatically
  init(
    id: String,
    description: String,
    completed: Bool,
    createdAt: Date,
    updatedAt: Date? = nil,
    dueAt: Date? = nil,
    completedAt: Date? = nil,
    conversationId: String? = nil,
    source: String? = nil,
    priority: String? = nil,
    metadata: String? = nil,
    category: String? = nil,
    deleted: Bool? = nil,
    deletedBy: String? = nil,
    deletedAt: Date? = nil,
    deletedReason: String? = nil,
    keptTaskId: String? = nil,
    goalId: String? = nil,
    fromStaged: Bool? = nil,
    recurrenceRule: String? = nil,
    recurrenceParentId: String? = nil,
    sortOrder: Int? = nil,
    indentLevel: Int? = nil,
    relevanceScore: Int? = nil,
    contextSummary: String? = nil,
    currentActivity: String? = nil,
    agentEditedFiles: [String]? = nil,
    agentStatus: String? = nil,
    agentPrompt: String? = nil,
    agentPlan: String? = nil,
    agentSessionId: String? = nil,
    agentStartedAt: Date? = nil,
    agentCompletedAt: Date? = nil,
    chatSessionId: String? = nil
  ) {
    self.id = id
    self.description = description
    self.completed = completed
    self.createdAt = createdAt
    self.updatedAt = updatedAt
    self.dueAt = dueAt
    self.completedAt = completedAt
    self.conversationId = conversationId
    self.source = source
    self.priority = priority
    self.metadata = metadata
    self.category = category
    self.deleted = deleted
    self.deletedBy = deletedBy
    self.deletedAt = deletedAt
    self.deletedReason = deletedReason
    self.keptTaskId = keptTaskId
    self.goalId = goalId
    self.fromStaged = fromStaged
    self.recurrenceRule = recurrenceRule
    self.recurrenceParentId = recurrenceParentId
    self.sortOrder = sortOrder
    self.indentLevel = indentLevel
    self.relevanceScore = relevanceScore
    self.contextSummary = contextSummary
    self.currentActivity = currentActivity
    self.agentEditedFiles = agentEditedFiles
    self.agentStatus = agentStatus
    self.agentPrompt = agentPrompt
    self.agentPlan = agentPlan
    self.agentSessionId = agentSessionId
    self.agentStartedAt = agentStartedAt
    self.agentCompletedAt = agentCompletedAt
    self.chatSessionId = chatSessionId
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
    completed = try container.decodeIfPresent(Bool.self, forKey: .completed) ?? false
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
    updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt)
    dueAt = try container.decodeIfPresent(Date.self, forKey: .dueAt)
    completedAt = try container.decodeIfPresent(Date.self, forKey: .completedAt)
    conversationId = try container.decodeIfPresent(String.self, forKey: .conversationId)
    source = try container.decodeIfPresent(String.self, forKey: .source)
    priority = try container.decodeIfPresent(String.self, forKey: .priority)
    metadata = try container.decodeIfPresent(String.self, forKey: .metadata)
    category = try container.decodeIfPresent(String.self, forKey: .category)
    deleted = try container.decodeIfPresent(Bool.self, forKey: .deleted)
    deletedBy = try container.decodeIfPresent(String.self, forKey: .deletedBy)
    deletedAt = try container.decodeIfPresent(Date.self, forKey: .deletedAt)
    deletedReason = try container.decodeIfPresent(String.self, forKey: .deletedReason)
    keptTaskId = try container.decodeIfPresent(String.self, forKey: .keptTaskId)
    goalId = try container.decodeIfPresent(String.self, forKey: .goalId)
    fromStaged = try container.decodeIfPresent(Bool.self, forKey: .fromStaged)
    recurrenceRule = try container.decodeIfPresent(String.self, forKey: .recurrenceRule)
    recurrenceParentId = try container.decodeIfPresent(String.self, forKey: .recurrenceParentId)
    sortOrder = try container.decodeIfPresent(Int.self, forKey: .sortOrder)
    indentLevel = try container.decodeIfPresent(Int.self, forKey: .indentLevel)
    relevanceScore = try container.decodeIfPresent(Int.self, forKey: .relevanceScore)

    // Local-only fields, not decoded from API
    contextSummary = nil
    currentActivity = nil
    agentEditedFiles = nil
    agentStatus = nil
    agentPrompt = nil
    agentPlan = nil
    agentSessionId = nil
    agentStartedAt = nil
    agentCompletedAt = nil
  }

  /// Categories that trigger Claude agent execution
  static let agentCategories: Set<String> = ["feature", "bug", "code"]

  /// Get tags array from metadata or fall back to single category
  var tags: [String] {
    // First try to get tags from metadata JSON
    if let metadata = metadata,
      let data = metadata.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let metaTags = json["tags"] as? [String], !metaTags.isEmpty
    {
      return metaTags
    }
    // Fall back to single category for backward compat
    if let category = category {
      return [category]
    }
    return []
  }

  /// Check if this task should trigger an agent (any task can trigger)
  var shouldTriggerAgent: Bool {
    return true
  }

  /// Parsed source classification from metadata
  var sourceClassification: TaskSourceClassification? {
    guard let metadata = metadata,
      let data = metadata.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let cat = json["source_category"] as? String,
      let sub = json["source_subcategory"] as? String
    else { return nil }
    return TaskSourceClassification.from(category: cat, subcategory: sub)
  }

  /// Parse metadata JSON to extract source app name
  var sourceApp: String? {
    guard let metadata = metadata,
      let data = metadata.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }
    return json["source_app"] as? String
  }

  /// Parse metadata JSON to extract window title
  var windowTitle: String? {
    guard let metadata = metadata,
      let data = metadata.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }
    return json["window_title"] as? String
  }

  /// Parse metadata JSON to extract confidence score
  var confidence: Double? {
    guard let metadata = metadata,
      let data = metadata.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }
    return json["confidence"] as? Double
  }

  /// Parse full metadata JSON dictionary
  var parsedMetadata: [String: Any]? {
    guard let metadata = metadata,
      let data = metadata.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }
    return json
  }

  /// Whether this task has detail metadata worth showing (beyond tags/category already visible as badges)
  var hasDetailMetadata: Bool {
    guard let json = parsedMetadata else { return false }
    let displayedKeys: Set<String> = ["tags", "category", "source_category", "source_subcategory"]
    return json.keys.contains(where: { !displayedKeys.contains($0) })
  }

  /// Display-friendly source label
  var sourceLabel: String {
    guard let source = source else { return "Task" }
    switch source {
    case "screenshot": return "Screen"
    case "transcription:omi": return "omi"
    case "transcription:desktop": return "Desktop"
    case "transcription:phone": return "Phone"
    case "manual": return "Manual"
    default: return "Task"
    }
  }

  /// Display label: app name for screenshot tasks, generic label otherwise
  var sourceAppLabel: String {
    if source == "screenshot", let app = sourceApp {
      return app
    }
    return sourceLabel
  }

  /// System icon name for source
  var sourceIcon: String {
    guard let source = source else { return "list.bullet" }
    switch source {
    case "screenshot": return "camera.fill"
    case "transcription:omi": return "waveform"
    case "transcription:desktop": return "desktopcomputer"
    case "transcription:phone": return "iphone"
    case "manual": return "square.and.pencil"
    default: return "list.bullet"
    }
  }

  /// Display-friendly category label
  var categoryLabel: String {
    guard let category = category else { return "" }
    return category.capitalized
  }

  /// System icon name for category
  var categoryIcon: String {
    guard let category = category else { return "folder.fill" }
    switch category {
    case "feature": return "sparkles"
    case "bug": return "ladybug.fill"
    case "code": return "chevron.left.forwardslash.chevron.right"
    case "work": return "briefcase.fill"
    case "personal": return "person.fill"
    case "research": return "magnifyingglass"
    case "communication": return "bubble.left.fill"
    case "finance": return "dollarsign.circle.fill"
    case "health": return "heart.fill"
    default: return "folder.fill"
    }
  }

  /// Color for category badge
  var categoryColor: String {
    guard let category = category else { return "gray" }
    switch category {
    case "feature": return "purple"
    case "bug": return "red"
    case "code": return "blue"
    case "work": return "orange"
    case "personal": return "green"
    case "research": return "cyan"
    case "communication": return "indigo"
    case "finance": return "yellow"
    case "health": return "pink"
    default: return "gray"
    }
  }

  /// All meaningful task data formatted for chat context.
  /// Add new fields here when they're added to the struct so chat always gets everything.
  var chatContext: String {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .short

    var lines: [String] = []

    // Core
    lines.append("Task: \(description)")
    if let category = category { lines.append("Category: \(category)") }
    if !tags.isEmpty { lines.append("Tags: \(tags.joined(separator: ", "))") }
    if let priority = priority { lines.append("Priority: \(priority)") }
    lines.append("Status: \(completed ? "completed" : "active")")
    lines.append("Created: \(formatter.string(from: createdAt))")
    if let dueAt = dueAt { lines.append("Due: \(formatter.string(from: dueAt))") }
    if let completedAt = completedAt {
      lines.append("Completed: \(formatter.string(from: completedAt))")
    }

    // Source & origin
    if let source = source { lines.append("Source: \(sourceLabel) (\(source))") }
    if let app = sourceApp { lines.append("Source app: \(app)") }
    if let title = windowTitle { lines.append("Window title: \(title)") }
    if let conf = confidence {
      lines.append("Extraction confidence: \(String(format: "%.0f%%", conf * 100))")
    }

    // Screen context at extraction time
    if let ctx = contextSummary, !ctx.isEmpty { lines.append("Context when detected: \(ctx)") }
    if let act = currentActivity, !act.isEmpty { lines.append("User activity: \(act)") }

    // Relationships
    if let convId = conversationId { lines.append("Conversation ID: \(convId)") }
    if let goalId = goalId { lines.append("Linked goal: \(goalId)") }

    // Agent work
    if let status = agentStatus { lines.append("Agent status: \(status)") }
    if let prompt = agentPrompt, !prompt.isEmpty {
      lines.append("Agent prompt: \(String(prompt.prefix(1000)))")
    }
    if let plan = agentPlan, !plan.isEmpty {
      lines.append("Agent plan:\n\(String(plan.prefix(2000)))")
    }
    if let files = agentEditedFiles, !files.isEmpty {
      lines.append("Files edited by agent: \(files.joined(separator: ", "))")
    }

    // Raw metadata (catches anything not explicitly listed above)
    if let meta = parsedMetadata {
      let coveredKeys: Set<String> = [
        "tags", "source_app", "window_title", "confidence",
        "source_category", "source_subcategory",
      ]
      let extra = meta.filter { !coveredKeys.contains($0.key) }
      if !extra.isEmpty {
        let pairs = extra.map { "\($0.key): \($0.value)" }.sorted()
        lines.append("Additional metadata: \(pairs.joined(separator: ", "))")
      }
    }

    return lines.joined(separator: "\n")
  }
}

// MARK: - Goal Models

/// Type of goal measurement
enum GoalType: String, Codable, CaseIterable {
  case boolean = "boolean"
  case scale = "scale"
  case numeric = "numeric"

  var displayName: String {
    switch self {
    case .boolean: return "Done/Not Done"
    case .scale: return "Scale"
    case .numeric: return "Numeric"
    }
  }
}

/// User goal
struct Goal: Codable, Identifiable {
  let id: String
  let title: String
  let description: String?
  let goalType: GoalType
  let targetValue: Double
  var currentValue: Double
  let minValue: Double
  let maxValue: Double
  let unit: String?
  let isActive: Bool
  let createdAt: Date
  let updatedAt: Date
  let completedAt: Date?
  let source: String?

  enum CodingKeys: String, CodingKey {
    case id, title, description, unit, source
    case goalType = "goal_type"
    case targetValue = "target_value"
    case currentValue = "current_value"
    case minValue = "min_value"
    case maxValue = "max_value"
    case isActive = "is_active"
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case completedAt = "completed_at"
  }

  init(from decoder: Decoder) throws {
    // Schema authority: OmiAPI.GoalResponse (generated from app-client OpenAPI).
    // The domain model layers on client-only fields (description, completedAt,
    // source) the backend REST schema does not expose, read via the same
    // container with tolerant fallbacks.
    let container = try decoder.container(keyedBy: CodingKeys.self)
    // Wire DTO required fields (created_at, title, etc.) are stricter than the
    // legacy decoder; use try? and fall back to the container for tolerance.
    let wire = try? OmiAPI.GoalResponse(from: decoder)

    id = try wire?.id ?? container.decodeIfPresent(String.self, forKey: .id) ?? ""
    title = try wire?.title ?? container.decodeIfPresent(String.self, forKey: .title) ?? ""
    description = try container.decodeIfPresent(String.self, forKey: .description)
    goalType = GoalType(rawValue: try wire?.goalType ?? container.decodeIfPresent(String.self, forKey: .goalType) ?? "") ?? .boolean
    targetValue = try wire?.targetValue ?? container.decodeIfPresent(Double.self, forKey: .targetValue) ?? 0
    currentValue = try wire?.currentValue ?? container.decodeIfPresent(Double.self, forKey: .currentValue) ?? 0
    minValue = try wire?.minValue ?? container.decodeIfPresent(Double.self, forKey: .minValue) ?? 0
    maxValue = try wire?.maxValue ?? container.decodeIfPresent(Double.self, forKey: .maxValue) ?? 0
    unit = try wire?.unit ?? container.decodeIfPresent(String.self, forKey: .unit)
    isActive = try wire?.isActive ?? container.decodeIfPresent(Bool.self, forKey: .isActive) ?? true
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let std = ISO8601DateFormatter()
    let createdAtString = wire?.createdAt
    createdAt = (createdAtString.flatMap { f.date(from: $0) ?? std.date(from: $0) }) ?? Date()
    let updatedAtString = wire?.updatedAt
    updatedAt = (updatedAtString.flatMap { f.date(from: $0) ?? std.date(from: $0) }) ?? createdAt
    completedAt = try container.decodeIfPresent(Date.self, forKey: .completedAt)
    source = try container.decodeIfPresent(String.self, forKey: .source)
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.container(keyedBy: CodingKeys.self)
    try container.encode(id, forKey: .id)
    try container.encode(title, forKey: .title)
    try container.encodeIfPresent(description, forKey: .description)
    try container.encode(goalType, forKey: .goalType)
    try container.encode(targetValue, forKey: .targetValue)
    try container.encode(currentValue, forKey: .currentValue)
    try container.encode(minValue, forKey: .minValue)
    try container.encode(maxValue, forKey: .maxValue)
    try container.encodeIfPresent(unit, forKey: .unit)
    try container.encode(isActive, forKey: .isActive)
    try container.encode(createdAt, forKey: .createdAt)
    try container.encode(updatedAt, forKey: .updatedAt)
    try container.encodeIfPresent(completedAt, forKey: .completedAt)
    try container.encodeIfPresent(source, forKey: .source)
  }

  /// Progress as a percentage (0-100), based on targetValue
  var progress: Double {
    guard targetValue != minValue else { return 0 }
    let pct = ((currentValue - minValue) / (targetValue - minValue)) * 100.0
    return min(max(pct, 0), 100)
  }

  /// Whether the goal is completed
  var isCompleted: Bool {
    currentValue >= targetValue
  }

  /// Formatted progress text
  var progressText: String {
    switch goalType {
    case .boolean:
      return isCompleted ? "Done" : "Not Done"
    case .scale, .numeric:
      if let unit = unit {
        return "\(Int(currentValue))/\(Int(targetValue)) \(unit)"
      }
      return "\(Int(currentValue))/\(Int(targetValue))"
    }
  }
}

/// Daily score calculation result
struct DailyScore: Codable {
  let score: Double
  let completedTasks: Int
  let totalTasks: Int
  let date: String

  enum CodingKeys: String, CodingKey {
    case score, date
    case completedTasks = "completed_tasks"
    case totalTasks = "total_tasks"
  }

  /// Score formatted as percentage
  var scorePercentage: String {
    return "\(Int(score))%"
  }

  /// Whether this is a perfect score
  var isPerfect: Bool {
    return score >= 100
  }
}

/// Single score data (used for daily, weekly, overall)
struct ScoreData: Codable {
  let score: Double
  let completedTasks: Int
  let totalTasks: Int

  enum CodingKeys: String, CodingKey {
    case score
    case completedTasks = "completed_tasks"
    case totalTasks = "total_tasks"
  }

  var scorePercentage: String {
    return "\(Int(score))%"
  }

  var hasTasks: Bool {
    return totalTasks > 0
  }
}

/// Combined score response with all three score types
struct ScoreResponse: Codable {
  let daily: ScoreData
  let weekly: ScoreData
  let overall: ScoreData
  let defaultTab: String
  let date: String

  enum CodingKeys: String, CodingKey {
    case daily, weekly, overall, date
    case defaultTab = "default_tab"
  }
}

// MARK: - App Models

/// App summary for list views (lightweight)
struct OmiApp: Codable, Identifiable, Sendable {
  let id: String
  let name: String
  let description: String
  let image: String
  let category: String
  let author: String
  let capabilities: [String]
  let approved: Bool
  let `private`: Bool
  let installs: Int
  var ratingAvg: Double?
  var ratingCount: Int
  let isPaid: Bool
  let price: Double?
  var enabled: Bool

  enum CodingKeys: String, CodingKey {
    case id, name, description, image, category, author, capabilities
    case approved
    case `private`
    case installs
    case ratingAvg = "rating_avg"
    case ratingCount = "rating_count"
    case isPaid = "is_paid"
    case price
    case enabled
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    name = try container.decodeIfPresent(String.self, forKey: .name) ?? ""
    description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
    image = try container.decodeIfPresent(String.self, forKey: .image) ?? ""
    category = try container.decodeIfPresent(String.self, forKey: .category) ?? "other"
    author = try container.decodeIfPresent(String.self, forKey: .author) ?? ""
    capabilities = try container.decodeIfPresent([String].self, forKey: .capabilities) ?? []
    approved = try container.decodeIfPresent(Bool.self, forKey: .approved) ?? false
    `private` = try container.decodeIfPresent(Bool.self, forKey: .private) ?? false
    installs = try container.decodeIfPresent(Int.self, forKey: .installs) ?? 0
    ratingAvg = try container.decodeIfPresent(Double.self, forKey: .ratingAvg)
    ratingCount = try container.decodeIfPresent(Int.self, forKey: .ratingCount) ?? 0
    isPaid = try container.decodeIfPresent(Bool.self, forKey: .isPaid) ?? false
    price = try container.decodeIfPresent(Double.self, forKey: .price)
    enabled = try container.decodeIfPresent(Bool.self, forKey: .enabled) ?? false
  }

  /// Check if app works with chat
  var worksWithChat: Bool {
    capabilities.contains("chat") || capabilities.contains("persona")
  }

  /// Check if app works with memories/conversations
  var worksWithMemories: Bool {
    capabilities.contains("memories")
  }

  /// Check if app has external integration
  var worksExternally: Bool {
    capabilities.contains("external_integration")
  }

  /// Formatted rating string
  var formattedRating: String? {
    guard let rating = ratingAvg, ratingCount > 0 else { return nil }
    return String(format: "%.1f", rating)
  }

  /// Formatted installs string (e.g., "1.2k", "43k")
  var formattedInstalls: String? {
    guard installs > 0 else { return nil }
    if installs >= 1000 {
      let thousands = Double(installs) / 1000.0
      if thousands >= 10 {
        return String(format: "%.0fk", thousands)
      } else {
        return String(format: "%.1fk", thousands)
      }
    }
    return "\(installs)"
  }
}

/// Full app details
struct OmiAppDetails: Codable, Identifiable {
  let id: String
  let name: String
  let description: String
  let image: String
  let category: String
  let author: String
  let email: String?
  let capabilities: [String]
  let uid: String?
  let approved: Bool
  let `private`: Bool
  let status: String
  let chatPrompt: String?
  let memoryPrompt: String?
  let personaPrompt: String?
  let installs: Int
  let ratingAvg: Double?
  let ratingCount: Int
  let isPaid: Bool
  let price: Double?
  let paymentPlan: String?
  let username: String?
  let twitter: String?
  let createdAt: Date?
  var enabled: Bool
  let externalIntegration: ExternalIntegration?

  enum CodingKeys: String, CodingKey {
    case id, name, description, image, category, author, email, capabilities
    case uid, approved
    case `private`
    case status
    case chatPrompt = "chat_prompt"
    case memoryPrompt = "memory_prompt"
    case personaPrompt = "persona_prompt"
    case installs
    case ratingAvg = "rating_avg"
    case ratingCount = "rating_count"
    case isPaid = "is_paid"
    case price
    case paymentPlan = "payment_plan"
    case username, twitter
    case createdAt = "created_at"
    case enabled
    case externalIntegration = "external_integration"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    name = try container.decodeIfPresent(String.self, forKey: .name) ?? ""
    description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
    image = try container.decodeIfPresent(String.self, forKey: .image) ?? ""
    category = try container.decodeIfPresent(String.self, forKey: .category) ?? "other"
    author = try container.decodeIfPresent(String.self, forKey: .author) ?? ""
    email = try container.decodeIfPresent(String.self, forKey: .email)
    capabilities = try container.decodeIfPresent([String].self, forKey: .capabilities) ?? []
    uid = try container.decodeIfPresent(String.self, forKey: .uid)
    approved = try container.decodeIfPresent(Bool.self, forKey: .approved) ?? false
    `private` = try container.decodeIfPresent(Bool.self, forKey: .private) ?? false
    status = try container.decodeIfPresent(String.self, forKey: .status) ?? "under-review"
    chatPrompt = try container.decodeIfPresent(String.self, forKey: .chatPrompt)
    memoryPrompt = try container.decodeIfPresent(String.self, forKey: .memoryPrompt)
    personaPrompt = try container.decodeIfPresent(String.self, forKey: .personaPrompt)
    installs = try container.decodeIfPresent(Int.self, forKey: .installs) ?? 0
    ratingAvg = try container.decodeIfPresent(Double.self, forKey: .ratingAvg)
    ratingCount = try container.decodeIfPresent(Int.self, forKey: .ratingCount) ?? 0
    isPaid = try container.decodeIfPresent(Bool.self, forKey: .isPaid) ?? false
    price = try container.decodeIfPresent(Double.self, forKey: .price)
    paymentPlan = try container.decodeIfPresent(String.self, forKey: .paymentPlan)
    username = try container.decodeIfPresent(String.self, forKey: .username)
    twitter = (try? container.decodeIfPresent(String.self, forKey: .twitter)) ?? nil
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt)
    enabled = try container.decodeIfPresent(Bool.self, forKey: .enabled) ?? false
    externalIntegration = try container.decodeIfPresent(
      ExternalIntegration.self, forKey: .externalIntegration)
  }
}

/// App category
struct OmiAppCategory: Codable, Identifiable, Sendable {
  let id: String
  let title: String
}

/// App capability definition
struct OmiAppCapability: Codable, Identifiable, Sendable {
  let id: String
  let title: String
  let description: String?

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    title = try container.decodeIfPresent(String.self, forKey: .title) ?? ""
    description = try container.decodeIfPresent(String.self, forKey: .description)
  }

  enum CodingKeys: String, CodingKey {
    case id, title, description
  }
}

/// Auth step for external integration setup
struct AuthStep: Codable, Sendable {
  let name: String
  let url: String
}

/// External integration setup details
struct ExternalIntegration: Codable, Sendable {
  let authSteps: [AuthStep]
  let setupCompletedUrl: String?
  let setupInstructionsFilePath: String?
  let appHomeUrl: String?
  let isInstructionsUrl: Bool?

  enum CodingKeys: String, CodingKey {
    case authSteps = "auth_steps"
    case setupCompletedUrl = "setup_completed_url"
    case setupInstructionsFilePath = "setup_instructions_file_path"
    case appHomeUrl = "app_home_url"
    case isInstructionsUrl = "is_instructions_url"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    authSteps = try container.decodeIfPresent([AuthStep].self, forKey: .authSteps) ?? []
    setupCompletedUrl = try container.decodeIfPresent(String.self, forKey: .setupCompletedUrl)
    setupInstructionsFilePath = try container.decodeIfPresent(
      String.self, forKey: .setupInstructionsFilePath)
    appHomeUrl = try container.decodeIfPresent(String.self, forKey: .appHomeUrl)
    isInstructionsUrl = try container.decodeIfPresent(Bool.self, forKey: .isInstructionsUrl)
  }
}

/// App review
struct OmiAppReview: Codable, Identifiable {
  var id: String { uid }
  let uid: String
  let score: Int
  let review: String
  let response: String?
  let ratedAt: Date
  let editedAt: Date?

  enum CodingKeys: String, CodingKey {
    case uid, score, review, response
    case ratedAt = "rated_at"
    case editedAt = "edited_at"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    uid = try container.decode(String.self, forKey: .uid)
    score = try container.decodeIfPresent(Int.self, forKey: .score) ?? 0
    review = try container.decodeIfPresent(String.self, forKey: .review) ?? ""
    response = try container.decodeIfPresent(String.self, forKey: .response)
    ratedAt = try container.decodeIfPresent(Date.self, forKey: .ratedAt) ?? Date()
    editedAt = try container.decodeIfPresent(Date.self, forKey: .editedAt)
  }
}

// MARK: - V2 Apps Response Types

/// Capability info in v2/apps response
struct OmiCapabilityInfo: Codable, Sendable {
  let id: String
  let title: String
}

/// Pagination metadata in v2/apps response
struct OmiPaginationMeta: Codable, Sendable {
  let total: Int
  let count: Int
  let offset: Int
  let limit: Int
}

/// A single group in the v2/apps response
struct OmiAppGroup: Codable, Sendable {
  let capability: OmiCapabilityInfo
  let data: [OmiApp]
  let pagination: OmiPaginationMeta
}

/// Metadata in v2/apps response
struct OmiAppsV2Meta: Codable, Sendable {
  let capabilities: [OmiCapabilityInfo]
  let groupCount: Int
  let limit: Int
  let offset: Int
}

/// Full v2/apps grouped response
struct OmiAppsV2Response: Codable, Sendable {
  let groups: [OmiAppGroup]
  let meta: OmiAppsV2Meta
}

// MARK: - Apps API

extension APIClient {

  /// Fetches apps from the API
  func getApps(
    capability: String? = nil,
    category: String? = nil,
    limit: Int = 50,
    offset: Int = 0
  ) async throws -> [OmiApp] {
    var queryItems: [String] = [
      "limit=\(limit)",
      "offset=\(offset)",
    ]

    if let capability = capability {
      queryItems.append("capability=\(capability)")
    }

    if let category = category {
      queryItems.append("category=\(category)")
    }

    let endpoint = "v1/apps?\(queryItems.joined(separator: "&"))"
    return try await get(endpoint)
  }

  /// Fetches apps grouped by capability (v2 API - matches Flutter/Python backend)
  /// Returns groups: Featured, Integrations, Chat Assistants, Summary Apps, Realtime Notifications
  /// Fetches all apps with real rating data from v1/apps
  func getAppsWithRatings(limit: Int = 200) async throws -> [OmiApp] {
    return try await get("v1/apps?limit=\(limit)")
  }

  func getAppsV2(offset: Int = 0, limit: Int = 50) async throws -> OmiAppsV2Response {
    let endpoint = "v2/apps?offset=\(offset)&limit=\(limit)"
    return try await get(endpoint)
  }

  /// Searches apps with filters
  func searchApps(
    query: String? = nil,
    category: String? = nil,
    capability: String? = nil,
    minRating: Int? = nil,
    installedOnly: Bool = false,
    limit: Int = 50,
    offset: Int = 0
  ) async throws -> [OmiApp] {
    struct SearchResponse: Decodable {
      let data: [OmiApp]
    }

    var queryItems: [URLQueryItem] = [
      URLQueryItem(name: "limit", value: "\(limit)"),
      URLQueryItem(name: "offset", value: "\(offset)"),
    ]

    if let query = query, !query.isEmpty {
      queryItems.append(URLQueryItem(name: "q", value: query))
    }

    if let category = category {
      queryItems.append(URLQueryItem(name: "category", value: category))
    }

    if let capability = capability {
      queryItems.append(URLQueryItem(name: "capability", value: capability))
    }

    if let minRating = minRating {
      queryItems.append(URLQueryItem(name: "rating", value: "\(minRating)"))
    }

    if installedOnly {
      queryItems.append(URLQueryItem(name: "installed_apps", value: "true"))
    }

    var components = URLComponents()
    components.queryItems = queryItems
    let endpoint = "v2/apps/search?\(components.percentEncodedQuery ?? "")"
    let response: SearchResponse = try await get(endpoint)
    return response.data
  }

  /// Fetches app details by ID
  func getAppDetails(appId: String) async throws -> OmiAppDetails {
    return try await get("v1/apps/\(appId)")
  }

  /// Fetches app reviews
  func getAppReviews(appId: String) async throws -> [OmiAppReview] {
    return try await get("v1/apps/\(appId)/reviews")
  }

  /// Fetches user's enabled apps
  func getEnabledApps() async throws -> [OmiApp] {
    return try await get("v1/apps/enabled")
  }

  /// Enables an app for the current user
  func enableApp(appId: String) async throws {
    struct ToggleResponse: Decodable {
      let status: String?
      let detail: String?
    }
    let _: ToggleResponse = try await post("v1/apps/enable?app_id=\(appId)")
  }

  /// Disables an app for the current user
  func disableApp(appId: String) async throws {
    struct ToggleResponse: Decodable {
      let status: String?
      let detail: String?
    }
    let _: ToggleResponse = try await post("v1/apps/disable?app_id=\(appId)")
  }

  /// Checks if an external integration app's setup is complete
  func isAppSetupCompleted(url: String, uid: String) async -> Bool {
    // An empty/unknown completion URL means setup cannot be verified, so report
    // not-completed (consistent with the invalid-URL and network-failure paths
    // below). Returning true here would wrongly mark an unconfigured app as set up.
    guard !url.isEmpty else { return false }
    guard let fullUrl = URL(string: "\(url)?uid=\(uid)") else { return false }
    var request = URLRequest(url: fullUrl)
    request.httpMethod = "GET"
    do {
      let (data, _) = try await session.data(for: request)
      if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
        return json["is_setup_completed"] as? Bool ?? false
      }
    } catch {}
    return false
  }

  /// Submits a review for an app
  func submitAppReview(appId: String, score: Int, review: String) async throws -> OmiAppReview {
    struct ReviewRequest: Encodable {
      let app_id: String
      let score: Int
      let review: String
    }
    let body = ReviewRequest(app_id: appId, score: score, review: review)
    return try await post("v1/apps/review", body: body)
  }

  /// Fetches all app categories
  func getAppCategories() async throws -> [OmiAppCategory] {
    return try await get("v1/app-categories")
  }

  /// Fetches all app capabilities
  func getAppCapabilities() async throws -> [OmiAppCapability] {
    return try await get("v1/app-capabilities")
  }

  // MARK: - Conversation Reprocessing

  /// Reprocess a conversation with a specific app
  func reprocessConversation(conversationId: String, appId: String) async throws {
    struct ReprocessRequest: Encodable {
      let app_id: String
    }
    struct ReprocessResponse: Decodable {
      let success: Bool
      let message: String
    }
    let body = ReprocessRequest(app_id: appId)
    let _: ReprocessResponse = try await post(
      "v1/conversations/\(conversationId)/reprocess", body: body)
  }
}

// MARK: - Persona API

extension APIClient {

  /// Fetches user's persona (if exists)
  func getPersona() async throws -> Persona? {
    return try await get("v1/personas")
  }

  /// Creates a new persona
  func createPersona(name: String, username: String? = nil) async throws -> Persona {
    struct CreateRequest: Encodable {
      let name: String
      let username: String?
    }
    let body = CreateRequest(name: name, username: username)
    return try await post("v1/personas", body: body)
  }

  /// Updates an existing persona
  func updatePersona(
    name: String? = nil,
    description: String? = nil,
    personaPrompt: String? = nil,
    image: String? = nil
  ) async throws -> Persona {
    struct UpdateRequest: Encodable {
      let name: String?
      let description: String?
      let personaPrompt: String?
      let image: String?

      enum CodingKeys: String, CodingKey {
        case name, description, image
        case personaPrompt = "persona_prompt"
      }
    }
    let body = UpdateRequest(
      name: name, description: description, personaPrompt: personaPrompt, image: image)
    return try await patch("v1/personas", body: body)
  }

  /// Deletes user's persona
  func deletePersona() async throws {
    try await delete("v1/personas")
  }

  /// Regenerates persona prompt from current public memories
  func regeneratePersonaPrompt() async throws -> GeneratePromptResponse {
    struct EmptyRequest: Encodable {}
    return try await post("v1/personas/generate-prompt", body: EmptyRequest())
  }

  /// Checks if a username is available
  func checkPersonaUsername(_ username: String) async throws -> UsernameAvailableResponse {
    return try await get("v1/personas/check-username?username=\(username)")
  }
}

// MARK: - Persona Models

/// AI Persona model
struct Persona: Codable, Identifiable {
  let id: String
  let uid: String
  let name: String
  let username: String?
  let description: String
  let image: String
  let category: String
  let capabilities: [String]
  let personaPrompt: String?
  let approved: Bool
  let status: String
  let isPrivate: Bool
  let author: String
  let email: String?
  let createdAt: Date
  let updatedAt: Date
  let publicMemoriesCount: Int?

  enum CodingKeys: String, CodingKey {
    case id, uid, name, username, description, image, category, capabilities
    case personaPrompt = "persona_prompt"
    case approved, status
    case isPrivate = "private"
    case author, email
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case publicMemoriesCount = "public_memories_count"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    uid = try container.decode(String.self, forKey: .uid)
    name = try container.decode(String.self, forKey: .name)
    username = try container.decodeIfPresent(String.self, forKey: .username)
    description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
    image = try container.decodeIfPresent(String.self, forKey: .image) ?? ""
    category = try container.decodeIfPresent(String.self, forKey: .category) ?? ""
    capabilities = try container.decodeIfPresent([String].self, forKey: .capabilities) ?? []
    personaPrompt = try container.decodeIfPresent(String.self, forKey: .personaPrompt)
    approved = try container.decodeIfPresent(Bool.self, forKey: .approved) ?? false
    status = try container.decodeIfPresent(String.self, forKey: .status) ?? "under-review"
    isPrivate = try container.decodeIfPresent(Bool.self, forKey: .isPrivate) ?? false
    author = try container.decodeIfPresent(String.self, forKey: .author) ?? ""
    email = try container.decodeIfPresent(String.self, forKey: .email)
    createdAt = try container.decode(Date.self, forKey: .createdAt)
    updatedAt = try container.decode(Date.self, forKey: .updatedAt)
    publicMemoriesCount = try container.decodeIfPresent(Int.self, forKey: .publicMemoriesCount)
  }

  /// Whether the persona has a generated prompt
  var hasPrompt: Bool {
    personaPrompt != nil && !personaPrompt!.isEmpty
  }

  /// Status display text
  var statusText: String {
    switch status {
    case "approved": return "Active"
    case "under-review": return "Pending Review"
    case "rejected": return "Rejected"
    default: return status.capitalized
    }
  }

  /// Status color
  var statusColor: String {
    switch status {
    case "approved": return "green"
    case "under-review": return "orange"
    case "rejected": return "red"
    default: return "gray"
    }
  }
}

/// Response for prompt generation
struct GeneratePromptResponse: Codable {
  let personaPrompt: String
  let description: String
  let memoriesUsed: Int

  enum CodingKeys: String, CodingKey {
    case personaPrompt = "persona_prompt"
    case description
    case memoriesUsed = "memories_used"
  }
}

/// Response for username availability check
struct UsernameAvailableResponse: Codable {
  let available: Bool
  let username: String
}

// MARK: - User Settings API

extension APIClient {

  /// Fetches daily summary settings
  func getDailySummarySettings() async throws -> DailySummarySettings {
    return try await get("v1/users/daily-summary-settings")
  }

  /// Updates daily summary settings
  func updateDailySummarySettings(enabled: Bool? = nil, hour: Int? = nil) async throws
    -> DailySummarySettings
  {
    struct UpdateRequest: Encodable {
      let enabled: Bool?
      let hour: Int?
    }
    let body = UpdateRequest(enabled: enabled, hour: hour)
    return try await patch("v1/users/daily-summary-settings", body: body)
  }

  /// Fetches transcription preferences
  func getTranscriptionPreferences() async throws -> TranscriptionPreferences {
    return try await get("v1/users/transcription-preferences")
  }

  /// Updates transcription preferences
  func updateTranscriptionPreferences(singleLanguageMode: Bool? = nil, vocabulary: [String]? = nil)
    async throws -> TranscriptionPreferences
  {
    struct UpdateRequest: Encodable {
      let singleLanguageMode: Bool?
      let vocabulary: [String]?

      enum CodingKeys: String, CodingKey {
        case singleLanguageMode = "single_language_mode"
        case vocabulary
      }
    }
    let body = UpdateRequest(singleLanguageMode: singleLanguageMode, vocabulary: vocabulary)
    return try await patch("v1/users/transcription-preferences", body: body)
  }

  /// Fetches user language preference
  func getUserLanguage() async throws -> UserLanguageResponse {
    return try await get("v1/users/language")
  }

  /// Updates user language preference. The PATCH endpoint's response shape differs
  /// from GET's (`{status, single_language_mode}`, not `{language}`) — decoding into
  /// UserLanguageResponse here always threw ("data couldn't be read because it is
  /// missing") even though the backend had already saved the language, silently
  /// (pre-await-fix) or now visibly blocking the caller on a save that succeeded.
  @discardableResult
  func updateUserLanguage(_ language: String) async throws -> SetUserLanguageResponse {
    struct UpdateRequest: Encodable {
      let language: String
    }
    let body = UpdateRequest(language: language)
    return try await patch("v1/users/language", body: body)
  }

  /// Fetches recording permission status
  func getRecordingPermission() async throws -> RecordingPermissionResponse {
    return try await get("v1/users/store-recording-permission")
  }

  /// Sets recording permission
  func setRecordingPermission(enabled: Bool) async throws {
    let url = URL(string: baseURL + "v1/users/store-recording-permission?value=\(enabled)")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)

    let (_, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse,
      (200...299).contains(httpResponse.statusCode)
    else {
      throw APIError.httpError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
    }
  }

  /// Fetches private cloud sync setting
  func getPrivateCloudSync() async throws -> PrivateCloudSyncResponse {
    return try await get("v1/users/private-cloud-sync")
  }

  /// Sets private cloud sync
  func setPrivateCloudSync(enabled: Bool) async throws {
    let url = URL(string: baseURL + "v1/users/private-cloud-sync?value=\(enabled)")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)

    let (_, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse,
      (200...299).contains(httpResponse.statusCode)
    else {
      throw APIError.httpError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
    }
  }

  /// Fetches notification settings
  func getNotificationSettings() async throws -> NotificationSettingsResponse {
    return try await get("v1/users/notification-settings")
  }

  /// Updates notification settings
  func updateNotificationSettings(enabled: Bool? = nil, frequency: Int? = nil) async throws
    -> NotificationSettingsResponse
  {
    struct UpdateRequest: Encodable {
      let enabled: Bool?
      let frequency: Int?
    }
    let body = UpdateRequest(enabled: enabled, frequency: frequency)
    return try await patch("v1/users/notification-settings", body: body)
  }

  /// Fetches user profile
  func getUserProfile() async throws -> UserProfileResponse {
    return try await get("v1/users/profile")
  }

  /// Updates user profile (onboarding data)
  func updateUserProfile(
    name: String? = nil, motivation: String? = nil, useCase: String? = nil, job: String? = nil,
    company: String? = nil
  ) async throws {
    struct UpdateRequest: Encodable {
      let name: String?
      let motivation: String?
      let use_case: String?
      let job: String?
      let company: String?
    }
    let body = UpdateRequest(
      name: name, motivation: motivation, use_case: useCase, job: job, company: company)
    let _: UserProfileResponse = try await patch("v1/users/profile", body: body)
  }

  /// Deletes the authenticated user's account and all server data.
  func deleteAccount() async throws {
    try await delete("v1/users/delete-account")
  }

  // MARK: - Assistant Settings API

  /// Fetches assistant settings from the backend
  func getAssistantSettings() async throws -> AssistantSettingsResponse {
    return try await get("v1/users/assistant-settings")
  }

  /// Updates assistant settings on the backend (partial update — only non-nil fields are changed)
  func updateAssistantSettings(_ settings: AssistantSettingsResponse) async throws
    -> AssistantSettingsResponse
  {
    return try await patch("v1/users/assistant-settings", body: settings)
  }

  /// Fetches server-controlled desktop update/banner policy.
  func getDesktopUpdatePolicy(currentBuild: Int?) async throws -> DesktopUpdatePolicyResponse {
    var endpoint = "v2/desktop/update-policy?platform=macos"
    if let currentBuild {
      endpoint += "&current_build=\(currentBuild)"
    }
    return try await get(endpoint, requireAuth: false, includeBYOK: false)
  }

  // MARK: - Knowledge Graph API

  /// Get the full knowledge graph (nodes and edges)
  func getKnowledgeGraph() async throws -> KnowledgeGraphResponse {
    return try await get("v1/knowledge-graph")
  }

  /// Rebuild the knowledge graph from memories
  func rebuildKnowledgeGraph(limit: Int = 500) async throws -> RebuildGraphResponse {
    return try await post("v1/knowledge-graph/rebuild?limit=\(limit)", body: EmptyBody())
  }

  /// Delete the knowledge graph
  func deleteKnowledgeGraph() async throws {
    return try await delete("v1/knowledge-graph")
  }
}

// MARK: - Knowledge Graph Models

/// Node type in the knowledge graph
enum KnowledgeGraphNodeType: String, Codable {
  case person
  case place
  case organization
  case thing
  case concept
}

/// A node in the knowledge graph representing an entity
struct KnowledgeGraphNode: Codable, Identifiable {
  let id: String
  let label: String
  let nodeType: KnowledgeGraphNodeType
  let aliases: [String]
  let memoryIds: [String]
  let createdAt: Date
  let updatedAt: Date

  enum CodingKeys: String, CodingKey {
    case id, label, aliases
    case nodeType = "node_type"
    case memoryIds = "memory_ids"
    case createdAt = "created_at"
    case updatedAt = "updated_at"
  }

  init(
    id: String, label: String, nodeType: KnowledgeGraphNodeType, aliases: [String] = [],
    memoryIds: [String] = [], createdAt: Date = Date(), updatedAt: Date = Date()
  ) {
    self.id = id
    self.label = label
    self.nodeType = nodeType
    self.aliases = aliases
    self.memoryIds = memoryIds
    self.createdAt = createdAt
    self.updatedAt = updatedAt
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    label = try container.decode(String.self, forKey: .label)
    if let rawType = try container.decodeIfPresent(String.self, forKey: .nodeType) {
      nodeType = KnowledgeGraphNodeType(rawValue: rawType) ?? .concept
    } else {
      nodeType = .concept
    }
    aliases = try container.decodeIfPresent([String].self, forKey: .aliases) ?? []
    memoryIds = try container.decodeIfPresent([String].self, forKey: .memoryIds) ?? []
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
    updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt) ?? Date()
  }
}

/// An edge in the knowledge graph representing a relationship
struct KnowledgeGraphEdge: Codable, Identifiable {
  let id: String
  let sourceId: String
  let targetId: String
  let label: String
  let memoryIds: [String]
  let createdAt: Date

  enum CodingKeys: String, CodingKey {
    case id, label
    case sourceId = "source_id"
    case targetId = "target_id"
    case memoryIds = "memory_ids"
    case createdAt = "created_at"
  }

  init(
    id: String, sourceId: String, targetId: String, label: String, memoryIds: [String] = [],
    createdAt: Date = Date()
  ) {
    self.id = id
    self.sourceId = sourceId
    self.targetId = targetId
    self.label = label
    self.memoryIds = memoryIds
    self.createdAt = createdAt
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    sourceId = try container.decode(String.self, forKey: .sourceId)
    targetId = try container.decode(String.self, forKey: .targetId)
    label = try container.decode(String.self, forKey: .label)
    memoryIds = try container.decodeIfPresent([String].self, forKey: .memoryIds) ?? []
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
  }
}

/// Response containing the full knowledge graph
struct KnowledgeGraphResponse: Codable {
  let nodes: [KnowledgeGraphNode]
  let edges: [KnowledgeGraphEdge]

  init(nodes: [KnowledgeGraphNode], edges: [KnowledgeGraphEdge]) {
    self.nodes = nodes
    self.edges = edges
  }
}

/// Response for rebuild operation
struct RebuildGraphResponse: Codable {
  let status: String
  let nodesCount: Int?
  let edgesCount: Int?

  enum CodingKeys: String, CodingKey {
    case status
    case nodesCount = "nodes_count"
    case edgesCount = "edges_count"
  }
}

// MARK: - User Settings Models

/// Daily summary notification settings
struct DailySummarySettings: Codable {
  let enabled: Bool
  let hour: Int
}

/// Transcription preferences
struct TranscriptionPreferences: Codable {
  let singleLanguageMode: Bool
  let vocabulary: [String]

  enum CodingKeys: String, CodingKey {
    case singleLanguageMode = "single_language_mode"
    case vocabulary
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    singleLanguageMode =
      try container.decodeIfPresent(Bool.self, forKey: .singleLanguageMode) ?? false
    vocabulary = try container.decodeIfPresent([String].self, forKey: .vocabulary) ?? []
  }
}

/// User language response (GET /v1/users/language)
struct UserLanguageResponse: Codable {
  let language: String
}

/// Response shape for PATCH /v1/users/language — deliberately distinct from
/// UserLanguageResponse; the backend's set_user_language handler returns
/// {status, single_language_mode}, never {language}.
struct SetUserLanguageResponse: Codable {
  let status: String
  let single_language_mode: Bool
}

/// Recording permission response
struct RecordingPermissionResponse: Codable {
  let enabled: Bool

  enum CodingKeys: String, CodingKey {
    case enabled = "store_recording_permission"
  }
}

/// Private cloud sync response
struct PrivateCloudSyncResponse: Codable {
  let enabled: Bool

  enum CodingKeys: String, CodingKey {
    case enabled = "private_cloud_sync_enabled"
  }
}

/// Notification settings response
struct NotificationSettingsResponse: Codable {
  let enabled: Bool
  let frequency: Int

  /// Frequency level description
  var frequencyDescription: String {
    switch frequency {
    case 0: return "Off"
    case 1: return "Minimal"
    case 2: return "Low"
    case 3: return "Balanced"
    case 4: return "High"
    case 5: return "Maximum"
    default: return "Unknown"
    }
  }
}

enum SubscriptionPlanType: String, Codable {
  case basic      // display "Free"
  case unlimited  // legacy — display "Unlimited (legacy)"
  case architect  // display "Architect" ($400/mo, cost_usd quota)
  case pro        // backward compat: old Firestore docs may still say "pro"
  case `operator` // new — display "Operator"
}

enum SubscriptionStatusType: String, Codable {
  case active
  case inactive
}

struct SubscriptionLimitsResponse: Codable {
  let transcriptionSeconds: Int?
  let wordsTranscribed: Int?
  let insightsGained: Int?
  let memoriesCreated: Int?

  enum CodingKeys: String, CodingKey {
    case transcriptionSeconds = "transcription_seconds"
    case wordsTranscribed = "words_transcribed"
    case insightsGained = "insights_gained"
    case memoriesCreated = "memories_created"
  }
}

struct UserSubscriptionInfo: Codable {
  let plan: SubscriptionPlanType
  let status: SubscriptionStatusType
  let currentPeriodEnd: Int?
  let stripeSubscriptionId: String?
  let currentPriceId: String?
  let features: [String]
  let cancelAtPeriodEnd: Bool
  let limits: SubscriptionLimitsResponse
  let deprecated: Bool?
  let deprecationMessage: String?

  enum CodingKeys: String, CodingKey {
    case plan, status, features, limits, deprecated
    case currentPeriodEnd = "current_period_end"
    case stripeSubscriptionId = "stripe_subscription_id"
    case currentPriceId = "current_price_id"
    case cancelAtPeriodEnd = "cancel_at_period_end"
    case deprecationMessage = "deprecation_message"
  }
}

struct SubscriptionPriceOption: Codable, Identifiable {
  let id: String
  let title: String
  let description: String?
  let priceString: String

  enum CodingKeys: String, CodingKey {
    case id, title, description
    case priceString = "price_string"
  }
}

struct SubscriptionPlanOption: Codable, Identifiable {
  let id: String
  let title: String
  let subtitle: String?
  let description: String?
  let eyebrow: String?
  let features: [String]
  let prices: [SubscriptionPriceOption]

  init(id: String, title: String, subtitle: String? = nil, description: String? = nil, eyebrow: String? = nil, features: [String] = [], prices: [SubscriptionPriceOption] = []) {
    self.id = id
    self.title = title
    self.subtitle = subtitle
    self.description = description
    self.eyebrow = eyebrow
    self.features = features
    self.prices = prices
  }
}

struct UserSubscriptionResponse: Codable {
  let subscription: UserSubscriptionInfo
  let transcriptionSecondsUsed: Int
  let transcriptionSecondsLimit: Int
  let wordsTranscribedUsed: Int
  let wordsTranscribedLimit: Int
  let insightsGainedUsed: Int
  let insightsGainedLimit: Int
  let memoriesCreatedUsed: Int
  let memoriesCreatedLimit: Int
  let availablePlans: [SubscriptionPlanOption]
  let showSubscriptionUI: Bool
  // Set for Neo subscribers whose current billing period started before the
  // policy change in #7496 — they retain desktop access until this unix-seconds
  // timestamp (their `current_period_end`). Null for everyone else.
  let desktopGrandfatherUntil: Int?

  enum CodingKeys: String, CodingKey {
    case subscription
    case transcriptionSecondsUsed = "transcription_seconds_used"
    case transcriptionSecondsLimit = "transcription_seconds_limit"
    case wordsTranscribedUsed = "words_transcribed_used"
    case wordsTranscribedLimit = "words_transcribed_limit"
    case insightsGainedUsed = "insights_gained_used"
    case insightsGainedLimit = "insights_gained_limit"
    case memoriesCreatedUsed = "memories_created_used"
    case memoriesCreatedLimit = "memories_created_limit"
    case availablePlans = "available_plans"
    case showSubscriptionUI = "show_subscription_ui"
    case desktopGrandfatherUntil = "desktop_grandfather_until"
  }

  // Defensive decode: only `subscription` is required. The usage counters and
  // plan catalog default when absent so a backend that's behind on schema
  // (notably the dev backend the beta channel routes to, which can lag prod or
  // omit newer fields like `memories_created_used`) doesn't blank the entire
  // Plan & Usage page with "Failed to load plan information."
  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    subscription = try c.decode(UserSubscriptionInfo.self, forKey: .subscription)
    transcriptionSecondsUsed = try c.decodeIfPresent(Int.self, forKey: .transcriptionSecondsUsed) ?? 0
    transcriptionSecondsLimit = try c.decodeIfPresent(Int.self, forKey: .transcriptionSecondsLimit) ?? 0
    wordsTranscribedUsed = try c.decodeIfPresent(Int.self, forKey: .wordsTranscribedUsed) ?? 0
    wordsTranscribedLimit = try c.decodeIfPresent(Int.self, forKey: .wordsTranscribedLimit) ?? 0
    insightsGainedUsed = try c.decodeIfPresent(Int.self, forKey: .insightsGainedUsed) ?? 0
    insightsGainedLimit = try c.decodeIfPresent(Int.self, forKey: .insightsGainedLimit) ?? 0
    memoriesCreatedUsed = try c.decodeIfPresent(Int.self, forKey: .memoriesCreatedUsed) ?? 0
    memoriesCreatedLimit = try c.decodeIfPresent(Int.self, forKey: .memoriesCreatedLimit) ?? 0
    availablePlans = try c.decodeIfPresent([SubscriptionPlanOption].self, forKey: .availablePlans) ?? []
    showSubscriptionUI = try c.decodeIfPresent(Bool.self, forKey: .showSubscriptionUI) ?? true
    desktopGrandfatherUntil = try c.decodeIfPresent(Int.self, forKey: .desktopGrandfatherUntil)
  }
}

struct CheckoutSessionResponse: Codable {
  let url: String?
  let sessionId: String?
  let status: String?
  let message: String?

  enum CodingKeys: String, CodingKey {
    case url, status, message
    case sessionId = "session_id"
  }
}

struct UpgradeSubscriptionResponse: Codable {
  let status: String
  let message: String
  let daysRemaining: Int?
  let scheduleId: String?

  enum CodingKeys: String, CodingKey {
    case status, message
    case daysRemaining = "days_remaining"
    case scheduleId = "schedule_id"
  }
}

struct AvailablePlanPriceOption: Codable, Identifiable {
  let id: String
  let title: String
  let priceString: String
  let description: String?
  let interval: String
  let unitAmount: Int
  let isActive: Bool

  enum CodingKeys: String, CodingKey {
    case id, title, description, interval
    case priceString = "price_string"
    case unitAmount = "unit_amount"
    case isActive = "is_active"
  }
}

struct AvailablePlansResponse: Codable {
  let plans: [AvailablePlanPriceOption]
}

struct OverageInfoResponse: Codable {
  let plan: String
  let planType: String
  let isOveragePlan: Bool
  let includedQuestions: Int?
  let usedQuestions: Int
  let excessQuestions: Int
  let realCostUsd: Double
  let overageUsd: Double
  let markupMultiplier: Double
  let markupPercent: Double
  let resetAt: Int?
  let explainerTitle: String
  let explainerBody: String
  let byokAvailable: Bool

  enum CodingKeys: String, CodingKey {
    case plan
    case planType = "plan_type"
    case isOveragePlan = "is_overage_plan"
    case includedQuestions = "included_questions"
    case usedQuestions = "used_questions"
    case excessQuestions = "excess_questions"
    case realCostUsd = "real_cost_usd"
    case overageUsd = "overage_usd"
    case markupMultiplier = "markup_multiplier"
    case markupPercent = "markup_percent"
    case resetAt = "reset_at"
    case explainerTitle = "explainer_title"
    case explainerBody = "explainer_body"
    case byokAvailable = "byok_available"
  }
}

struct CustomerPortalResponse: Codable {
  let url: String
}

/// Trial metadata from `/v1/users/me/trial` (Python backend) — timing info for countdown UI
struct TrialMetadataResponse: Codable {
  let trialStartedAt: Int?
  let trialEndsAt: Int?
  let trialRemainingSeconds: Int
  let trialExpired: Bool
  let trialDurationSeconds: Int
  let trialFeatures: [String]
  let planAfterTrial: String

  enum CodingKeys: String, CodingKey {
    case trialStartedAt = "trial_started_at"
    case trialEndsAt = "trial_ends_at"
    case trialRemainingSeconds = "trial_remaining_seconds"
    case trialExpired = "trial_expired"
    case trialDurationSeconds = "trial_duration_seconds"
    case trialFeatures = "trial_features"
    case planAfterTrial = "plan_after_trial"
  }
}

/// User profile response
struct UserProfileResponse: Codable {
  let uid: String
  let email: String?
  let name: String?
  let timeZone: String?
  let createdAt: String?
  let motivation: String?
  let useCase: String?
  let job: String?
  let company: String?

  enum CodingKeys: String, CodingKey {
    case uid, email, name, motivation, job, company
    case timeZone = "time_zone"
    case createdAt = "created_at"
    case useCase = "use_case"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    uid = try container.decode(String.self, forKey: .uid)
    email = try container.decodeIfPresent(String.self, forKey: .email)
    name = try container.decodeIfPresent(String.self, forKey: .name)
    timeZone = try container.decodeIfPresent(String.self, forKey: .timeZone)
    createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
    motivation = try container.decodeIfPresent(String.self, forKey: .motivation)
    useCase = try container.decodeIfPresent(String.self, forKey: .useCase)
    job = try container.decodeIfPresent(String.self, forKey: .job)
    company = try container.decodeIfPresent(String.self, forKey: .company)
  }
}

// MARK: - Desktop Update Policy Models

struct DesktopUpdatePolicyResponse: Codable, Equatable {
  enum Severity: String, Codable {
    case none
    case banner
    case required
  }

  let id: String
  let active: Bool
  let severity: Severity
  let maximumBuildNumber: Int?
  let latestBuildNumber: Int?
  let title: String?
  let message: String?
  let ctaText: String
  let downloadURL: String
  let canDismiss: Bool

  enum CodingKeys: String, CodingKey {
    case id, active, severity, title, message
    case maximumBuildNumber = "maximum_build_number"
    case latestBuildNumber = "latest_build_number"
    case ctaText = "cta_text"
    case downloadURL = "download_url"
    case canDismiss = "can_dismiss"
  }

  var isRequired: Bool {
    active && severity == .required
  }
}

// MARK: - Assistant Settings Models

struct SharedAssistantSettingsResponse: Codable {
  var cooldownInterval: Int?
  var glowOverlayEnabled: Bool?
  var analysisDelay: Int?
  var screenAnalysisEnabled: Bool?

  enum CodingKeys: String, CodingKey {
    case cooldownInterval = "cooldown_interval"
    case glowOverlayEnabled = "glow_overlay_enabled"
    case analysisDelay = "analysis_delay"
    case screenAnalysisEnabled = "screen_analysis_enabled"
  }
}

struct FocusSettingsResponse: Codable {
  var enabled: Bool?
  var analysisPrompt: String?
  var cooldownInterval: Int?
  var notificationsEnabled: Bool?
  var excludedApps: [String]?

  enum CodingKeys: String, CodingKey {
    case enabled
    case analysisPrompt = "analysis_prompt"
    case cooldownInterval = "cooldown_interval"
    case notificationsEnabled = "notifications_enabled"
    case excludedApps = "excluded_apps"
  }
}

struct TaskSettingsResponse: Codable {
  var enabled: Bool?
  var analysisPrompt: String?
  var extractionInterval: Double?
  var minConfidence: Double?
  var notificationsEnabled: Bool?
  var allowedApps: [String]?
  var browserKeywords: [String]?

  enum CodingKeys: String, CodingKey {
    case enabled
    case analysisPrompt = "analysis_prompt"
    case extractionInterval = "extraction_interval"
    case minConfidence = "min_confidence"
    case notificationsEnabled = "notifications_enabled"
    case allowedApps = "allowed_apps"
    case browserKeywords = "browser_keywords"
  }
}

struct InsightSettingsResponse: Codable {
  var enabled: Bool?
  var analysisPrompt: String?
  var extractionInterval: Double?
  var minConfidence: Double?
  var notificationsEnabled: Bool?
  var excludedApps: [String]?

  enum CodingKeys: String, CodingKey {
    case enabled
    case analysisPrompt = "analysis_prompt"
    case extractionInterval = "extraction_interval"
    case minConfidence = "min_confidence"
    case notificationsEnabled = "notifications_enabled"
    case excludedApps = "excluded_apps"
  }
}

struct MemorySettingsResponse: Codable {
  var enabled: Bool?
  var analysisPrompt: String?
  var extractionInterval: Double?
  var minConfidence: Double?
  var notificationsEnabled: Bool?
  var excludedApps: [String]?

  enum CodingKeys: String, CodingKey {
    case enabled
    case analysisPrompt = "analysis_prompt"
    case extractionInterval = "extraction_interval"
    case minConfidence = "min_confidence"
    case notificationsEnabled = "notifications_enabled"
    case excludedApps = "excluded_apps"
  }
}

struct FloatingBarSettingsResponse: Codable {
  var voiceAnswersEnabled: Bool?
  var elevenlabsVoiceId: String?

  enum CodingKeys: String, CodingKey {
    case voiceAnswersEnabled = "voice_answers_enabled"
    case elevenlabsVoiceId = "elevenlabs_voice_id"
  }
}

enum AssistantSettingsJSONValue: Codable, Equatable {
  case null
  case bool(Bool)
  case int(Int)
  case double(Double)
  case string(String)
  case array([AssistantSettingsJSONValue])
  case object([String: AssistantSettingsJSONValue])

  init(from decoder: Decoder) throws {
    let container = try decoder.singleValueContainer()
    if container.decodeNil() {
      self = .null
    } else if let value = try? container.decode(Bool.self) {
      self = .bool(value)
    } else if let value = try? container.decode(Int.self) {
      self = .int(value)
    } else if let value = try? container.decode(Double.self) {
      self = .double(value)
    } else if let value = try? container.decode(String.self) {
      self = .string(value)
    } else if let value = try? container.decode([AssistantSettingsJSONValue].self) {
      self = .array(value)
    } else if let value = try? container.decode([String: AssistantSettingsJSONValue].self) {
      self = .object(value)
    } else {
      throw DecodingError.dataCorruptedError(
        in: container, debugDescription: "Unsupported assistant settings JSON value")
    }
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.singleValueContainer()
    switch self {
    case .null:
      try container.encodeNil()
    case .bool(let value):
      try container.encode(value)
    case .int(let value):
      try container.encode(value)
    case .double(let value):
      try container.encode(value)
    case .string(let value):
      try container.encode(value)
    case .array(let value):
      try container.encode(value)
    case .object(let value):
      try container.encode(value)
    }
  }
}

struct AssistantSettingsResponse: Codable {
  var shared: SharedAssistantSettingsResponse?
  var focus: FocusSettingsResponse?
  var task: TaskSettingsResponse?
  var insight: InsightSettingsResponse?
  var memory: MemorySettingsResponse?
  var floatingBar: FloatingBarSettingsResponse?
  var updateChannel: String?
  var unknownSections: [String: AssistantSettingsJSONValue]

  enum CodingKeys: String, CodingKey, CaseIterable {
    case shared, focus, task
    case insight = "advice"
    case memory
    case floatingBar = "floating_bar"
    case updateChannel = "update_channel"
  }

  init(
    shared: SharedAssistantSettingsResponse? = nil,
    focus: FocusSettingsResponse? = nil,
    task: TaskSettingsResponse? = nil,
    insight: InsightSettingsResponse? = nil,
    memory: MemorySettingsResponse? = nil,
    floatingBar: FloatingBarSettingsResponse? = nil,
    updateChannel: String? = nil,
    unknownSections: [String: AssistantSettingsJSONValue] = [:]
  ) {
    self.shared = shared
    self.focus = focus
    self.task = task
    self.insight = insight
    self.memory = memory
    self.floatingBar = floatingBar
    self.updateChannel = updateChannel
    self.unknownSections = unknownSections
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    shared = Self.decodeLossy(SharedAssistantSettingsResponse.self, from: container, forKey: .shared)
    focus = Self.decodeLossy(FocusSettingsResponse.self, from: container, forKey: .focus)
    task = Self.decodeLossy(TaskSettingsResponse.self, from: container, forKey: .task)
    insight = Self.decodeLossy(InsightSettingsResponse.self, from: container, forKey: .insight)
    memory = Self.decodeLossy(MemorySettingsResponse.self, from: container, forKey: .memory)
    floatingBar = Self.decodeLossy(
      FloatingBarSettingsResponse.self, from: container, forKey: .floatingBar)
    updateChannel = Self.decodeLossy(String.self, from: container, forKey: .updateChannel)

    let rawContainer = try decoder.container(keyedBy: AssistantSettingsDynamicCodingKey.self)
    let knownKeys = Set(CodingKeys.allCases.map(\.rawValue))
    unknownSections = rawContainer.allKeys.reduce(into: [:]) { result, key in
      guard !knownKeys.contains(key.stringValue),
        let value = try? rawContainer.decode(AssistantSettingsJSONValue.self, forKey: key)
      else { return }
      result[key.stringValue] = value
    }
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.container(keyedBy: CodingKeys.self)
    try container.encodeIfPresent(shared, forKey: .shared)
    try container.encodeIfPresent(focus, forKey: .focus)
    try container.encodeIfPresent(task, forKey: .task)
    try container.encodeIfPresent(insight, forKey: .insight)
    try container.encodeIfPresent(memory, forKey: .memory)
    try container.encodeIfPresent(floatingBar, forKey: .floatingBar)
    try container.encodeIfPresent(updateChannel, forKey: .updateChannel)

    var rawContainer = encoder.container(keyedBy: AssistantSettingsDynamicCodingKey.self)
    let knownKeys = Set(CodingKeys.allCases.map(\.rawValue))
    for (key, value) in unknownSections where !knownKeys.contains(key) {
      try rawContainer.encode(value, forKey: AssistantSettingsDynamicCodingKey(stringValue: key))
    }
  }

  private static func decodeLossy<T: Decodable>(
    _ type: T.Type,
    from container: KeyedDecodingContainer<CodingKeys>,
    forKey key: CodingKeys
  ) -> T? {
    do {
      return try container.decodeIfPresent(type, forKey: key)
    } catch {
      return nil
    }
  }
}

struct AssistantSettingsDynamicCodingKey: CodingKey {
  let stringValue: String
  let intValue: Int?

  init(stringValue: String) {
    self.stringValue = stringValue
    intValue = nil
  }

  init(intValue: Int) {
    stringValue = String(intValue)
    self.intValue = intValue
  }
}

// MARK: - Focus Sessions API

extension APIClient {

}

// MARK: - Insight API

extension APIClient {

}

// MARK: - Insight Models
/// Empty body for POST requests with no body
struct EmptyBody: Encodable {}

// MARK: - Chat Messages API (Persistence)

extension APIClient {

  /// Save a chat message to the backend
  func saveMessage(
    text: String,
    sender: String,
    appId: String? = nil,
    sessionId: String? = nil,
    metadata: String? = nil,
    clientMessageId: String? = nil,
    messageSource: String = "desktop_chat"
  ) async throws -> SaveMessageResponse {
    struct SaveRequest: Encodable {
      let text: String
      let sender: String
      let app_id: String?
      let session_id: String?
      let metadata: String?
      let client_message_id: String?
      let message_source: String
    }
    let body = SaveRequest(
      text: text,
      sender: sender,
      app_id: appId,
      session_id: sessionId,
      metadata: metadata,
      client_message_id: clientMessageId,
      message_source: messageSource
    )
    return try await post("v2/desktop/messages", body: body)
  }

  /// Fetch chat message history
  func getMessages(
    appId: String? = nil,
    limit: Int = 100,
    offset: Int = 0
  ) async throws -> [ChatMessageDB] {
    var queryItems: [String] = [
      "limit=\(limit)",
      "offset=\(offset)",
    ]

    if let appId = appId {
      queryItems.append("app_id=\(appId)")
    }

    let endpoint = "v2/desktop/messages?\(queryItems.joined(separator: "&"))"
    return try await get(endpoint)
  }

  /// Clear chat message history
  func deleteMessages(appId: String? = nil) async throws -> MessageDeleteResponse {
    var endpoint = "v2/desktop/messages"
    if let appId = appId {
      endpoint += "?app_id=\(appId)"
    }

    let url = URL(string: baseURL + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "DELETE"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)

    let (data, httpResponse) = try await performAuthenticatedData(for: request)

    guard (200...299).contains(httpResponse.statusCode) else {
      throw APIError.httpError(statusCode: httpResponse.statusCode)
    }

    return try decoder.decode(MessageDeleteResponse.self, from: data)
  }

  /// Fetch messages for a specific session
  func getMessages(
    sessionId: String,
    limit: Int = 100,
    offset: Int = 0
  ) async throws -> [ChatMessageDB] {
    let queryItems: [String] = [
      "session_id=\(sessionId)",
      "limit=\(limit)",
      "offset=\(offset)",
    ]

    let endpoint = "v2/desktop/messages?\(queryItems.joined(separator: "&"))"
    return try await get(endpoint)
  }

  /// Rate a message (thumbs up/down)
  /// - Parameters:
  ///   - messageId: The message ID to rate
  ///   - rating: 1 for thumbs up, -1 for thumbs down, nil to clear rating
  func rateMessage(messageId: String, rating: Int?) async throws {
    struct RateRequest: Encodable {
      let rating: Int?
      let app_version: String?
    }
    let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
    let body = RateRequest(rating: rating, app_version: version)
    let _: MessageStatusResponse = try await patch(
      "v2/desktop/messages/\(messageId)/rating", body: body)
  }

  /// Share chat messages and get a shareable URL
  func shareChatMessages(messageIds: [String]) async throws -> ShareChatResponse {
    struct ShareRequest: Encodable {
      let message_ids: [String]
    }
    let body = ShareRequest(message_ids: messageIds)
    return try await post("v2/messages/share", body: body)
  }

  /// Upload one or more files to be attached to a chat message.
  /// Mirrors the Flutter app's `uploadFilesServer` (lib/backend/http/api/messages.dart) —
  /// same `/v2/files` multipart endpoint, same response shape.
  func uploadChatFiles(
    _ uploads: [(data: Data, fileName: String, mimeType: String)],
    appId: String? = nil
  ) async throws -> [ChatFileResponse] {
    var endpoint = "v2/files"
    if let appId = appId, !appId.isEmpty, appId != "no_selected" {
      endpoint += "?app_id=\(appId)"
    }
    let url = URL(string: baseURL + endpoint)!

    let boundary = "Boundary-\(UUID().uuidString)"
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)
    request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

    var body = Data()
    let lineBreak = "\r\n"
    for upload in uploads {
      body.append("--\(boundary)\(lineBreak)".data(using: .utf8)!)
      body.append(
        "Content-Disposition: form-data; name=\"files\"; filename=\"\(upload.fileName)\"\(lineBreak)"
          .data(using: .utf8)!)
      body.append("Content-Type: \(upload.mimeType)\(lineBreak)\(lineBreak)".data(using: .utf8)!)
      body.append(upload.data)
      body.append(lineBreak.data(using: .utf8)!)
    }
    body.append("--\(boundary)--\(lineBreak)".data(using: .utf8)!)
    request.httpBody = body

    let (data, httpResponse) = try await performAuthenticatedData(for: request)
    guard (200...299).contains(httpResponse.statusCode) else {
      throw APIError.httpError(statusCode: httpResponse.statusCode)
    }
    return try decoder.decode([ChatFileResponse].self, from: data)
  }

  // MARK: - Sync local files (WAL upload)

  /// Upload-only POST to `/v2/sync-local-files`. Mirrors Flutter `uploadLocalFilesV2`.
  func uploadLocalFilesV2(
    fileURLs: [URL],
    conversationId: String? = nil
  ) async throws -> UploadLocalFilesResult {
    var components = URLComponents(string: baseURL + "v2/sync-local-files")!
    if let conversationId, !conversationId.isEmpty {
      components.queryItems = [URLQueryItem(name: "conversation_id", value: conversationId)]
    }
    guard let url = components.url else {
      throw APIError.syncUploadRejected(reason: "Invalid sync-local-files URL")
    }
    let request = try await buildSyncLocalFilesMultipartRequest(url: url, fileURLs: fileURLs)
    return try await performSyncLocalFilesUpload(request)
  }

  /// Single GET of a sync job's status — no polling loop.
  func fetchSyncJobStatus(jobId: String) async -> SyncJobFetch {
    let endpoint = "v2/sync-local-files/\(jobId)"
    let url = URL(string: baseURL + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.allHTTPHeaderFields = try? await buildHeaders(requireAuth: true)

    guard let (data, response) = try? await session.data(for: request),
          let http = response as? HTTPURLResponse else {
      return SyncJobFetch(outcome: .transient)
    }

    if http.statusCode == 404 {
      return SyncJobFetch(outcome: .notFound)
    }
    // 403 means the caller is not permitted to access this sync job. Unlike a
    // transient transport failure, re-polling will not resolve it — the upload
    // path already refreshed auth on 401, so a 403 here is a durable permission
    // failure. Surface it as `.forbidden` so the reconciler reverts the WAL to
    // `.miss` for re-upload (the backend dedupes by conversation/timestamp)
    // instead of polling forever.
    if http.statusCode == 403 {
      return SyncJobFetch(outcome: .forbidden)
    }
    guard http.statusCode == 200 else {
      return SyncJobFetch(outcome: .transient)
    }

    do {
      let status = try decoder.decode(SyncJobStatusResponse.self, from: data)
      return SyncJobFetch(outcome: .ok, status: status)
    } catch {
      return SyncJobFetch(outcome: .transient)
    }
  }

  private func buildSyncLocalFilesMultipartRequest(url: URL, fileURLs: [URL]) async throws -> URLRequest {
    let boundary = "Boundary-\(UUID().uuidString)"
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    var headers = try await buildHeaders(requireAuth: true)
    headers.removeValue(forKey: "Content-Type")
    request.allHTTPHeaderFields = headers
    request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

    var body = Data()
    let lineBreak = "\r\n"
    for fileURL in fileURLs {
      // Legacy desktop WAL files on disk may still use byte-length `_fsN` tokens;
      // normalize at upload time so the backend Opus decoder gets sample-frame size.
      let fileName = WALSyncUploadFileName.normalizedForUpload(fileURL.lastPathComponent)
      let fileData = try Data(contentsOf: fileURL)
      body.append("--\(boundary)\(lineBreak)".data(using: .utf8)!)
      body.append(
        "Content-Disposition: form-data; name=\"files\"; filename=\"\(fileName)\"\(lineBreak)"
          .data(using: .utf8)!)
      body.append("Content-Type: application/octet-stream\(lineBreak)\(lineBreak)".data(using: .utf8)!)
      body.append(fileData)
      body.append(lineBreak.data(using: .utf8)!)
    }
    body.append("--\(boundary)--\(lineBreak)".data(using: .utf8)!)
    request.httpBody = body
    return request
  }

  private func performSyncLocalFilesUpload(_ request: URLRequest, retriedAuth: Bool = false) async throws -> UploadLocalFilesResult {
    let (data, http) = try await performAuthenticatedData(for: request, retriedAuth: retriedAuth)

    if http.statusCode == 200 {
      let completed = try decoder.decode(SyncLocalFilesResultResponse.self, from: data)
      return .done(completed)
    }
    if http.statusCode == 202 {
      let start = try decoder.decode(SyncJobStartResponse.self, from: data)
      guard !start.jobId.isEmpty else {
        throw APIError.syncUploadRejected(reason: "Upload accepted but no job id returned")
      }
      return .queued(jobId: start.jobId)
    }
    if http.statusCode == 429 {
      let retryAfter = Self.parseRetryAfterSeconds(from: http)
      throw APIError.syncRateLimited(retryAfterSeconds: retryAfter)
    }
    if http.statusCode == 400 {
      throw APIError.syncUploadRejected(reason: "Audio file could not be processed by server")
    }
    if http.statusCode == 413 {
      throw APIError.syncUploadRejected(reason: "Audio file is too large to upload")
    }
    if http.statusCode >= 500 {
      throw APIError.syncUploadRejected(reason: "Server is temporarily unavailable")
    }
    throw APIError.syncUploadRejected(reason: "Upload failed unexpectedly")
  }

  private static func parseRetryAfterSeconds(from response: HTTPURLResponse) -> Int? {
    guard let raw = response.value(forHTTPHeaderField: "Retry-After") else { return nil }
    return Int(raw.trimmingCharacters(in: .whitespacesAndNewlines))
  }

}

/// Response shape for `POST /v2/files` — mirrors backend `FileChat` model.
struct ChatFileResponse: Codable {
  let id: String
  let name: String?
  let mimeType: String?
  let thumbnail: String?
  let thumbName: String?
  let openaiFileId: String?

  enum CodingKeys: String, CodingKey {
    case id
    case name
    case thumbnail
    case mimeType = "mime_type"
    case thumbName = "thumb_name"
    case openaiFileId = "openai_file_id"
  }
}

/// Response from rating a message
struct MessageStatusResponse: Codable {
  let status: String
}

// MARK: - Sync local files (WAL upload)

/// Outcome of POST `/v2/sync-local-files` — exactly one of `jobId` (202) or `completed` (200).
enum UploadLocalFilesResult: Equatable {
  case queued(jobId: String)
  case done(SyncLocalFilesResultResponse)

  var jobId: String? {
    if case .queued(let jobId) = self { return jobId }
    return nil
  }
}

struct SyncLocalFilesResultResponse: Codable, Equatable {
  let newMemories: [String]
  let updatedMemories: [String]
  let failedSegments: Int
  let totalSegments: Int
  let errors: [String]

  enum CodingKeys: String, CodingKey {
    case newMemories = "new_memories"
    case updatedMemories = "updated_memories"
    case failedSegments = "failed_segments"
    case totalSegments = "total_segments"
    case errors
  }
}

struct SyncJobStartResponse: Codable, Equatable {
  let jobId: String
  let status: String
  let totalFiles: Int
  let totalSegments: Int
  let pollAfterMs: Int

  enum CodingKeys: String, CodingKey {
    case jobId = "job_id"
    case status
    case totalFiles = "total_files"
    case totalSegments = "total_segments"
    case pollAfterMs = "poll_after_ms"
  }
}

struct SyncJobStatusResponse: Codable, Equatable {
  let jobId: String
  let status: String
  let totalSegments: Int
  let processedSegments: Int
  let successfulSegments: Int
  let failedSegments: Int
  let result: SyncLocalFilesResultResponse?
  let error: String?

  var isTerminal: Bool {
    status == "completed" || status == "partial_failure" || status == "failed"
  }

  enum CodingKeys: String, CodingKey {
    case jobId = "job_id"
    case status
    case totalSegments = "total_segments"
    case processedSegments = "processed_segments"
    case successfulSegments = "successful_segments"
    case failedSegments = "failed_segments"
    case result
    case error
  }
}

enum SyncJobFetchOutcome: Equatable {
  case ok
  case notFound
  case forbidden
  case transient
}

struct SyncJobFetch: Equatable {
  let outcome: SyncJobFetchOutcome
  let status: SyncJobStatusResponse?

  init(outcome: SyncJobFetchOutcome, status: SyncJobStatusResponse? = nil) {
    self.outcome = outcome
    self.status = status
  }
}

/// Response from sharing chat messages
struct ShareChatResponse: Codable {
  let url: String
  let token: String
}

// MARK: - Chat Sessions API

extension APIClient {

  /// Create a new chat session
  func createChatSession(
    title: String? = nil,
    appId: String? = nil
  ) async throws -> ChatSession {
    struct CreateRequest: Encodable {
      let title: String?
      let app_id: String?
    }
    let body = CreateRequest(title: title, app_id: appId)
    return try await post("v2/chat-sessions", body: body)
  }

  /// Fetch chat sessions
  func getChatSessions(
    appId: String? = nil,
    limit: Int = 50,
    offset: Int = 0,
    starred: Bool? = nil
  ) async throws -> [ChatSession] {
    var queryItems: [String] = [
      "limit=\(limit)",
      "offset=\(offset)",
    ]

    if let appId = appId {
      queryItems.append("app_id=\(appId)")
    }
    if let starred = starred {
      queryItems.append("starred=\(starred)")
    }

    let endpoint = "v2/chat-sessions?\(queryItems.joined(separator: "&"))"
    return try await get(endpoint)
  }

  /// Update a chat session (title, starred)
  func updateChatSession(
    sessionId: String,
    title: String? = nil,
    starred: Bool? = nil
  ) async throws -> ChatSession {
    struct UpdateRequest: Encodable {
      let title: String?
      let starred: Bool?
    }
    let body = UpdateRequest(title: title, starred: starred)
    return try await patch("v2/chat-sessions/\(sessionId)", body: body)
  }

  /// Delete a chat session and its messages
  func deleteChatSession(sessionId: String) async throws {
    try await delete("v2/chat-sessions/\(sessionId)")
  }

  /// Generate an initial greeting message for a new chat session
  func getInitialMessage(sessionId: String, appId: String? = nil) async throws
    -> InitialMessageResponse
  {
    struct InitialMessageRequest: Encodable {
      let sessionId: String
      let appId: String?

      enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case appId = "app_id"
      }
    }

    let body = InitialMessageRequest(sessionId: sessionId, appId: appId)
    return try await post("v2/chat/initial-message", body: body)
  }

  /// Generate a title for a chat session based on its messages
  func generateSessionTitle(sessionId: String, messages: [(text: String, sender: String)])
    async throws -> GenerateTitleResponse
  {
    struct TitleMessageInput: Encodable {
      let text: String
      let sender: String
    }

    struct GenerateTitleRequest: Encodable {
      let sessionId: String
      let messages: [TitleMessageInput]

      enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case messages
      }
    }

    let body = GenerateTitleRequest(
      sessionId: sessionId,
      messages: messages.map { TitleMessageInput(text: $0.text, sender: $0.sender) }
    )
    return try await post("v2/chat/generate-title", body: body)
  }
}

/// Response from generating session title
struct GenerateTitleResponse: Codable {
  let title: String
}

/// Response from generating initial message
struct InitialMessageResponse: Codable {
  let message: String
  let messageId: String

  enum CodingKeys: String, CodingKey {
    case message
    case messageId = "message_id"
  }
}

// MARK: - Chat Message Models

/// Response from saving a message
struct SaveMessageResponse: Codable {
  let id: String
  let createdAt: Date
  let sessionId: String?
  let created: Bool?

  enum CodingKeys: String, CodingKey {
    case id
    case createdAt = "created_at"
    case sessionId = "session_id"
    case created
  }
}

/// Persisted chat message from database
struct ChatMessageDB: Codable, Identifiable {
  let id: String
  let text: String
  let createdAt: Date
  let sender: String
  let appId: String?
  let sessionId: String?
  let rating: Int?
  let reported: Bool
  /// JSON string with extra info (attachments, etc.); see ChatMessage.decodeAttachments.
  let metadata: String?

  enum CodingKeys: String, CodingKey {
    case id, text, sender, rating, reported, metadata
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
  }
}

/// Response from deleting messages
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

// MARK: - AI User Profile API

struct AIUserProfileResponse: Codable {
  let profileText: String
  let generatedAt: Date
  let dataSourcesUsed: Int

  enum CodingKeys: String, CodingKey {
    case profileText = "profile_text"
    case generatedAt = "generated_at"
    case dataSourcesUsed = "data_sources_used"
  }
}

extension APIClient {

  /// Sync AI-generated user profile to backend
  func syncAIUserProfile(profileText: String, generatedAt: Date, dataSourcesUsed: Int) async throws
  {
    struct SyncRequest: Encodable {
      let profile_text: String
      let generated_at: String
      let data_sources_used: Int
    }

    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

    let body = SyncRequest(
      profile_text: profileText,
      generated_at: formatter.string(from: generatedAt),
      data_sources_used: dataSourcesUsed
    )

    let _: AIUserProfileResponse = try await patch("v1/users/ai-profile", body: body)
  }

  // MARK: - Agent VM

  struct AgentProvisionResponse: Decodable {
    let status: String
    let vmName: String
    let ip: String?
    let authToken: String
    let agentStatus: String
  }

  /// Provision a cloud agent VM for the current user (fire-and-forget)
  func provisionAgentVM() async throws -> AgentProvisionResponse {
    return try await post("v2/agent/provision", customBaseURL: rustBackendURL)
  }

  struct AgentStatusResponse: Decodable {
    let vmName: String
    let zone: String
    let ip: String?
    let status: String
    let authToken: String
    let createdAt: String
    let lastQueryAt: String?
  }

  /// Get current agent VM status
  func getAgentStatus() async throws -> AgentStatusResponse? {
    return try await get("v2/agent/status", customBaseURL: rustBackendURL)
  }
}

// MARK: - People Models

struct Person: Codable, Identifiable {
  let id: String
  let name: String
  let createdAt: Date?
  let updatedAt: Date?
  let speechSamples: [String]
  let speechSampleTranscripts: [String]?
  let speechSamplesVersion: Int

  enum CodingKeys: String, CodingKey {
    case id, name
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case speechSamples = "speech_samples"
    case speechSampleTranscripts = "speech_sample_transcripts"
    case speechSamplesVersion = "speech_samples_version"
  }

  init(
    id: String,
    name: String,
    createdAt: Date? = nil,
    updatedAt: Date? = nil,
    speechSamples: [String] = [],
    speechSampleTranscripts: [String]? = nil,
    speechSamplesVersion: Int = 3
  ) {
    self.id = id
    self.name = name
    self.createdAt = createdAt
    self.updatedAt = updatedAt
    self.speechSamples = speechSamples
    self.speechSampleTranscripts = speechSampleTranscripts
    self.speechSamplesVersion = speechSamplesVersion
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    name = try container.decode(String.self, forKey: .name)
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt)
    updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt)
    speechSamples = try container.decodeIfPresent([String].self, forKey: .speechSamples) ?? []
    speechSampleTranscripts = try container.decodeIfPresent(
      [String].self, forKey: .speechSampleTranscripts)
    speechSamplesVersion = try container.decodeIfPresent(Int.self, forKey: .speechSamplesVersion) ?? 3
  }
}

// MARK: - People API

extension APIClient {

  func getUserSubscription() async throws -> UserSubscriptionResponse {
    return try await get("v1/users/me/subscription")
  }

  func getTrialMetadata() async throws -> TrialMetadataResponse {
    return try await get("v1/users/me/trial")
  }

  func getAvailablePlans() async throws -> AvailablePlansResponse {
    return try await get("v1/payments/available-plans")
  }

  func getOverageInfo() async throws -> OverageInfoResponse {
    return try await get("v1/payments/overage-info")
  }

  func createCheckoutSession(priceId: String, promotionCode: String? = nil) async throws
    -> CheckoutSessionResponse
  {
    struct Request: Encodable {
      let priceId: String
      let promotionCode: String?

      enum CodingKeys: String, CodingKey {
        case priceId = "price_id"
        case promotionCode = "promotion_code"
      }
    }

    return try await post(
      "v1/payments/checkout-session",
      body: Request(priceId: priceId, promotionCode: promotionCode))
  }

  func upgradeSubscription(priceId: String, promotionCode: String? = nil) async throws
    -> UpgradeSubscriptionResponse
  {
    struct Request: Encodable {
      let priceId: String
      let promotionCode: String?

      enum CodingKeys: String, CodingKey {
        case priceId = "price_id"
        case promotionCode = "promotion_code"
      }
    }

    return try await post(
      "v1/payments/upgrade-subscription",
      body: Request(priceId: priceId, promotionCode: promotionCode))
  }

  func createCustomerPortalSession() async throws -> CustomerPortalResponse {
    return try await post("v1/payments/customer-portal")
  }

  /// Activate the Bring-Your-Own-Keys free plan on the backend.
  /// Sends SHA-256 fingerprints (never the keys themselves) so the backend
  /// can tell when the user rotates keys and re-validate.
  func activateBYOK(fingerprints: [String: String]) async throws {
    struct Request: Encodable {
      let fingerprints: [String: String]
    }
    struct Empty: Decodable {}
    let _: Empty = try await post(
      "v1/users/me/byok-active", body: Request(fingerprints: fingerprints), includeBYOK: false
    )
  }

  /// Deactivate BYOK (user cleared keys) so they return to the paid plan gate.
  func deactivateBYOK() async throws {
    try await delete("v1/users/me/byok-active", includeBYOK: false)
  }

  /// Fetches all people for the current user
  func getPeople() async throws -> [Person] {
    return try await get("v1/users/people")
  }

  /// Creates a new person
  func createPerson(name: String) async throws -> Person {
    struct CreatePersonRequest: Encodable {
      let name: String
    }
    return try await post("v1/users/people", body: CreatePersonRequest(name: name))
  }

  /// Bulk assigns segments to a person or user
  func assignSegmentsBulk(
    conversationId: String,
    segmentIds: [String],
    isUser: Bool,
    personId: String?
  ) async throws {
    struct AssignBulkRequest: Encodable {
      let assignType: String
      let value: String?
      let segmentIds: [String]

      enum CodingKeys: String, CodingKey {
        case assignType = "assign_type"
        case value
        case segmentIds = "segment_ids"
      }
    }

    let body = AssignBulkRequest(
      assignType: isUser ? "is_user" : "person_id",
      value: isUser ? "true" : personId,
      segmentIds: segmentIds
    )

    let url = URL(string: baseURL + "v1/conversations/\(conversationId)/segments/assign-bulk")!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)
    request.httpBody = try JSONEncoder().encode(body)

    let (_, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse,
      (200...299).contains(httpResponse.statusCode)
    else {
      throw APIError.httpError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
    }
  }

  // MARK: - LLM Usage

  func recordLlmUsage(
    inputTokens: Int,
    outputTokens: Int,
    cacheReadTokens: Int,
    cacheWriteTokens: Int,
    totalTokens: Int,
    costUsd: Double,
    account: String = "omi"
  ) async {
    struct Req: Encodable {
      let input_tokens: Int
      let output_tokens: Int
      let cache_read_tokens: Int
      let cache_write_tokens: Int
      let total_tokens: Int
      let cost_usd: Double
      let account: String
    }
    struct Res: Decodable { let status: String }
    do {
      let _: Res = try await post(
        "v1/users/me/llm-usage",
        body: Req(
          input_tokens: inputTokens,
          output_tokens: outputTokens,
          cache_read_tokens: cacheReadTokens,
          cache_write_tokens: cacheWriteTokens,
          total_tokens: totalTokens,
          cost_usd: costUsd,
          account: account
        ))
    } catch {
      log("APIClient: LLM usage record failed: \(error.localizedDescription)")
    }
  }

  func fetchTotalOmiAICost() async -> Double? {
    struct Res: Decodable { let total_cost_usd: Double }
    do {
      log("APIClient: Fetching total Omi AI cost from backend")
      let res: Res = try await get("v1/users/me/llm-usage/total")
      log(
        "APIClient: Total Omi AI cost from backend: $\(String(format: "%.4f", res.total_cost_usd))")
      return res.total_cost_usd
    } catch {
      log("APIClient: LLM total cost fetch failed: \(error.localizedDescription)")
      return nil
    }
  }

  // MARK: - Chat Usage Quota

  /// Current-month chat usage + the plan's cap. Backed by Python backend
  /// endpoint `/v1/users/me/usage-quota` which reads `users/{uid}/llm_usage/*`.
  struct ChatUsageQuota: Decodable {
    let plan: String       // display name: "Free" | "Plus" | "Pro"
    let planType: String   // internal id: "basic" | "unlimited" | "architect"
    let unit: String       // "questions" | "cost_usd"
    let used: Double
    let limit: Double?     // nil means unlimited
    let percent: Double
    let allowed: Bool
    let resetAt: Int?      // unix seconds — start of next UTC month

    enum CodingKeys: String, CodingKey {
      case plan
      case planType = "plan_type"
      case unit
      case used
      case limit
      case percent
      case allowed
      case resetAt = "reset_at"
    }
  }

  func fetchChatUsageQuota() async -> ChatUsageQuota? {
    do {
      let res: ChatUsageQuota = try await get("v1/users/me/usage-quota")
      log(
        "APIClient: Quota plan=\(res.plan) unit=\(res.unit) used=\(res.used) limit=\(res.limit ?? -1) allowed=\(res.allowed)"
      )
      return res
    } catch {
      log("APIClient: Chat quota fetch failed: \(error.localizedDescription)")
      return nil
    }
  }

  // MARK: - API Keys

  struct ApiKeysResponse: Decodable {
    let deepgramApiKey: String?
    let geminiApiKey: String?
    let firebaseApiKey: String?
    let googleCalendarApiKey: String?

    enum CodingKeys: String, CodingKey {
      case deepgramApiKey = "deepgram_api_key"
      case geminiApiKey = "gemini_api_key"
      case firebaseApiKey = "firebase_api_key"
      case googleCalendarApiKey = "google_calendar_api_key"
    }
  }

  func fetchApiKeys() async throws -> ApiKeysResponse {
    return try await get("v1/config/api-keys", customBaseURL: rustBackendURL)
  }

  struct TtsSynthesizeRequest: Encodable {
    let text: String
    let voiceId: String
    let instructions: String?

    enum CodingKeys: String, CodingKey {
      case text
      case voiceId = "voice_id"
      case instructions
    }
  }

  func synthesizeSpeech(request body: TtsSynthesizeRequest) async throws -> Data {
    let base = rustBackendURL
    guard !base.isEmpty, let url = URL(string: base + "v1/tts/synthesize") else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.timeoutInterval = 60
    request.allHTTPHeaderFields = try await buildHeaders()
    request.httpBody = try JSONEncoder().encode(body)

    let (data, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIError.invalidResponse
    }

    if httpResponse.statusCode == 401 {
      let authService = await MainActor.run { AuthService.shared }
      _ = try await authService.getIdToken(forceRefresh: true)

      var retryRequest = request
      retryRequest.setValue(
        try await authService.getAuthHeader(), forHTTPHeaderField: "Authorization")

      let (retryData, retryResponse) = try await session.data(for: retryRequest)
      guard let retryHttpResponse = retryResponse as? HTTPURLResponse else {
        throw APIError.invalidResponse
      }
      guard retryHttpResponse.statusCode != 401 else {
        throw APIError.unauthorized
      }
      guard (200...299).contains(retryHttpResponse.statusCode) else {
        throw APIError.httpError(statusCode: retryHttpResponse.statusCode)
      }
      return retryData
    }

    guard (200...299).contains(httpResponse.statusCode) else {
      throw APIError.httpError(statusCode: httpResponse.statusCode)
    }

    return data
  }

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
    includeTranscript: Bool = true
  ) async throws -> ToolResponse {
    var params =
      "v1/tools/conversations?limit=\(limit)&offset=\(offset)&include_transcript=\(includeTranscript)"
    if let sd = startDate { params += "&start_date=\(encodeQueryDate(sd))" }
    if let ed = endDate { params += "&end_date=\(encodeQueryDate(ed))" }
    return try await get(params, customBaseURL: nil)
  }

  func toolSearchConversations(
    query: String,
    startDate: String? = nil,
    endDate: String? = nil,
    limit: Int = 5,
    includeTranscript: Bool = true
  ) async throws -> ToolResponse {
    let body = SearchRequest(
      query: query, startDate: startDate, endDate: endDate, limit: limit,
      includeTranscript: includeTranscript)
    return try await post("v1/tools/conversations/search", body: body, customBaseURL: nil)
  }

  func toolGetMemories(
    limit: Int = 50,
    offset: Int = 0,
    startDate: String? = nil,
    endDate: String? = nil
  ) async throws -> ToolResponse {
    var params = "v1/tools/memories?limit=\(limit)&offset=\(offset)"
    if let sd = startDate { params += "&start_date=\(encodeQueryDate(sd))" }
    if let ed = endDate { params += "&end_date=\(encodeQueryDate(ed))" }
    return try await get(params, customBaseURL: nil)
  }

  func toolSearchMemories(query: String, limit: Int = 5) async throws -> ToolResponse {
    let body = MemorySearchRequest(query: query, limit: limit)
    return try await post("v1/tools/memories/search", body: body, customBaseURL: nil)
  }

  func toolGetActionItems(
    limit: Int = 50,
    offset: Int = 0,
    completed: Bool? = nil,
    startDate: String? = nil,
    endDate: String? = nil,
    dueStartDate: String? = nil,
    dueEndDate: String? = nil
  ) async throws -> ToolResponse {
    var params = "v1/tools/action-items?limit=\(limit)&offset=\(offset)"
    if let c = completed { params += "&completed=\(c)" }
    if let sd = startDate { params += "&start_date=\(encodeQueryDate(sd))" }
    if let ed = endDate { params += "&end_date=\(encodeQueryDate(ed))" }
    if let dsd = dueStartDate { params += "&due_start_date=\(encodeQueryDate(dsd))" }
    if let ded = dueEndDate { params += "&due_end_date=\(encodeQueryDate(ded))" }
    return try await get(params, customBaseURL: nil)
  }

  func toolCreateActionItem(
    description: String, dueAt: String? = nil, conversationId: String? = nil
  ) async throws -> ToolResponse {
    let body = CreateActionItemRequest(
      description: description, dueAt: dueAt, conversationId: conversationId)
    return try await post("v1/tools/action-items", body: body, customBaseURL: nil)
  }

  func toolUpdateActionItem(
    id: String, completed: Bool? = nil, description: String? = nil, dueAt: String? = nil
  ) async throws -> ToolResponse {
    let body = UpdateActionItemRequest(completed: completed, description: description, dueAt: dueAt)
    return try await patch("v1/tools/action-items/\(id)", body: body, customBaseURL: nil)
  }

  func toolCreateCalendarEvent(
    title: String,
    startTime: String,
    endTime: String,
    description: String? = nil,
    location: String? = nil,
    attendees: String? = nil
  ) async throws -> ToolResponse {
    let body = CreateCalendarEventRequest(
      title: title,
      startTime: startTime,
      endTime: endTime,
      description: description,
      location: location,
      attendees: attendees
    )
    return try await post("v1/tools/calendar-events", body: body, customBaseURL: nil)
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
