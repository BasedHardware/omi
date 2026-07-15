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
  var transport: OmiHTTPTransport

  /// When set, `buildHeaders` uses this instead of calling AuthService (test-only).
  var testAuthHeader: String? {
    get { transport.testAuthHeader }
    set { transport.testAuthHeader = newValue }
  }

  // Short-lived caches to deduplicate simultaneous calls from multiple services
  private var goalsCacheTime: Date?
  private var goalsCache: [Goal]?
  // Keyed by the query parameters so a cached total for one filter set is never
  // returned for a different one (e.g. includeDiscarded / statuses).
  private var conversationsCountCache: [String: (count: Int, time: Date)] = [:]

  init() {
    let transport = OmiHTTPTransport()
    self.transport = transport
    self.session = transport.session
  }

  /// Test-only initializer that accepts a custom URLSession for request interception.
  init(session: URLSession) {
    let transport = OmiHTTPTransport(session: session)
    self.transport = transport
    self.session = session
  }

  var decoder: JSONDecoder { transport.decoder }

  // MARK: - Request Building

  func buildHeaders(
    requireAuth: Bool = true,
    forceRefreshAuth: Bool = false,
    includeBYOK: Bool = true,
    expectedAuthOwnerId: String? = nil
  ) async throws -> [String: String] {
    try await transport.buildHeaders(
      requireAuth: requireAuth,
      forceRefreshAuth: forceRefreshAuth,
      includeBYOK: includeBYOK,
      expectedAuthOwnerId: expectedAuthOwnerId
    )
  }

  // MARK: - HTTP Methods

  func get<T: Decodable>(
    _ endpoint: String,
    requireAuth: Bool = true,
    customBaseURL: String? = nil,
    includeBYOK: Bool = true,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> T {
    let authPolicy = try resolvedRequestAuthPolicy(
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
    let authOwnerId = authPolicy.expectedAuthOwnerId
    try validateExpectedOwner(authPolicy)
    let base = customBaseURL ?? baseURL
    guard let url = URL(string: base + endpoint) else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: requireAuth,
      includeBYOK: includeBYOK,
      expectedAuthOwnerId: authOwnerId)
    try validateExpectedOwner(authPolicy)

    return try await performRequest(
      request,
      authPolicy: authPolicy)
  }

  func post<T: Decodable, B: Encodable>(
    _ endpoint: String,
    body: B,
    requireAuth: Bool = true,
    customBaseURL: String? = nil,
    includeBYOK: Bool = true,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> T {
    let authPolicy = try resolvedRequestAuthPolicy(
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
    let authOwnerId = authPolicy.expectedAuthOwnerId
    try validateExpectedOwner(authPolicy)
    let base = customBaseURL ?? baseURL
    guard let url = URL(string: base + endpoint) else {
      throw APIError.invalidResponse
    }
    log("APIClient: POST \(url.absoluteString)")
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: requireAuth,
      includeBYOK: includeBYOK,
      expectedAuthOwnerId: authOwnerId)
    try validateExpectedOwner(authPolicy)
    request.httpBody = try transport.encoder.encode(body)

    return try await performRequest(
      request,
      authPolicy: authPolicy)
  }

  func post<T: Decodable>(
    _ endpoint: String,
    requireAuth: Bool = true,
    customBaseURL: String? = nil,
    includeBYOK: Bool = true,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> T {
    let authPolicy = try resolvedRequestAuthPolicy(
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
    let authOwnerId = authPolicy.expectedAuthOwnerId
    try validateExpectedOwner(authPolicy)
    let base = customBaseURL ?? baseURL
    guard let url = URL(string: base + endpoint) else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: requireAuth,
      includeBYOK: includeBYOK,
      expectedAuthOwnerId: authOwnerId)
    try validateExpectedOwner(authPolicy)

    return try await performRequest(
      request,
      authPolicy: authPolicy)
  }

  /// Phase 2 realtime hub: ask the backend to mint a short-lived ephemeral token
  /// for `provider` ("openai"|"gemini"). The backend gates on auth + paywall.
  /// Credential failures are typed so the hub can recover deterministically instead
  /// of treating every failure as a silent fallback.
  func mintRealtimeToken(
    provider: String,
    expectedOwnerID: String,
    customBaseURL: String? = nil
  ) async throws -> String {
    struct Resp: Decodable { let token: String }
    let base = customBaseURL ?? rustBackendURL
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
    let authPolicy = RequestAuthPolicy.ownerBound(expectedOwnerID)
    try validateExpectedOwner(authPolicy)
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: true,
      includeBYOK: false,
      expectedAuthOwnerId: expectedOwnerID)
    request.httpBody = try JSONEncoder().encode(["provider": provider])

    do {
      return try await performRealtimeMintRequest(
        request,
        provider: providerType,
        authPolicy: authPolicy,
        retriedAuth: false)
    } catch let error as RealtimeTokenMintError {
      log("APIClient: realtime token mint failed for \(provider): \(error.localizedDescription)")
      throw error
    } catch let error as CredentialHealthError {
      log("APIClient: realtime token mint failed for \(provider): \(error.localizedDescription)")
      throw error
    } catch let error as AuthError {
      log("APIClient: realtime token mint rejected after owner change for \(provider)")
      throw error
    } catch {
      log("APIClient: realtime token mint failed for \(provider): \(error.localizedDescription)")
      throw CredentialHealthError.backendTransient(statusCode: nil, message: error.localizedDescription)
    }
  }

  private func performRealtimeMintRequest(
    _ request: URLRequest,
    provider: RealtimeHubProvider?,
    authPolicy: RequestAuthPolicy,
    retriedAuth: Bool
  ) async throws -> String {
    struct Resp: Decodable { let token: String }
    try validateExpectedOwner(authPolicy)
    let (data, response) = try await session.data(for: request)
    try validateExpectedOwner(authPolicy)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw CredentialHealthError.backendTransient(statusCode: nil, message: APIError.invalidResponse.localizedDescription)
    }

    if httpResponse.statusCode == 401, !retriedAuth {
      guard let retry = try await authorizedRetryRequest(
        from: request,
        retriedAuth: false,
        authPolicy: authPolicy
      ) else {
        throw CredentialHealthError.requiresLogin(message: "Please sign in again to use voice responses.")
      }
      do {
        let token = try await performRealtimeMintRequest(
          retry,
          provider: provider,
          authPolicy: authPolicy,
          retriedAuth: true)
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

    if httpResponse.statusCode == 401 {
      await invalidateSessionAfterUnauthorized(
        endpoint: endpointLabel(for: request),
        signOutOn401: authPolicy.signOutOn401)
      throw CredentialHealthError.requiresLogin(message: "Please sign in again to use voice responses.")
    }

    guard (200...299).contains(httpResponse.statusCode) else {
      let payload = OmiHTTPTransport.extractErrorPayload(from: data)
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
    outputAudio: Int,
    contextPlanID: String = "",
    stableCacheIdentity: String = "",
    dynamicContextIdentity: String = "",
    contextCacheReplaced: Bool = false
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
        // Opaque hashes/plan identifiers only; no rendered context or user text.
        "context_plan_id": contextPlanID,
        "stable_cache_identity": stableCacheIdentity,
        "dynamic_context_identity": dynamicContextIdentity,
        "context_cache_replaced": contextCacheReplaced,
      ]
      request.httpBody = try JSONSerialization.data(withJSONObject: body)
      _ = try await session.data(for: request)
    } catch {
      log("APIClient: realtime usage report failed: \(error.localizedDescription)")
    }
  }

  func performVoidRequest(
    _ request: URLRequest,
    authPolicy: RequestAuthPolicy = .default,
    retriedAuth: Bool = false
  ) async throws {
    let (_, httpResponse) = try await performAuthenticatedData(
      for: request,
      authPolicy: authPolicy,
      retriedAuth: retriedAuth
    )

    guard (200...299).contains(httpResponse.statusCode) else {
      throw APIError.httpError(statusCode: httpResponse.statusCode)
    }
  }

  func delete(
    _ endpoint: String,
    requireAuth: Bool = true,
    customBaseURL: String? = nil,
    includeBYOK: Bool = true,
    authPolicy: RequestAuthPolicy = .default,
    expectedAuthOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws {
    let effectiveAuthPolicy = try resolvedRequestAuthPolicy(
      expectedOwnerId: expectedAuthOwnerId,
      authorizationSnapshot: authorizationSnapshot,
      fallback: authPolicy)
    let authOwnerId = effectiveAuthPolicy.expectedAuthOwnerId
    try validateExpectedOwner(effectiveAuthPolicy)
    let base = customBaseURL ?? baseURL
    let url = URL(string: base + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "DELETE"
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: requireAuth,
      includeBYOK: includeBYOK,
      expectedAuthOwnerId: authOwnerId
    )
    try validateExpectedOwner(effectiveAuthPolicy)

    try await performVoidRequest(request, authPolicy: effectiveAuthPolicy)
  }

  // MARK: - Request Execution

  func invalidateSessionAfterUnauthorized(endpoint: String, signOutOn401: Bool) async {
    guard signOutOn401 else { return }
    await AuthSessionCoordinator.shared.handleHTTPUnauthorized(
      endpoint: endpoint,
      signOutOn401: true,
      auth: AuthService.shared
    )
  }

  func endpointLabel(for request: URLRequest) -> String {
    request.url?.path ?? request.url?.absoluteString ?? "unknown"
  }

  /// Refresh auth and build a retry request. Returns nil when already retried (caller should throw).
  private func authorizedRetryRequest(
    from request: URLRequest,
    retriedAuth: Bool,
    authPolicy: RequestAuthPolicy
  ) async throws -> URLRequest? {
    if retriedAuth {
      await invalidateSessionAfterUnauthorized(
        endpoint: endpointLabel(for: request),
        signOutOn401: authPolicy.signOutOn401
      )
      return nil
    }
    let authService = await MainActor.run { AuthService.shared }
    do {
      var retry = request
      let authHeader: String
      if let expectedOwnerId = authPolicy.expectedAuthOwnerId {
        authHeader = try await authService.getAuthHeader(
          forceRefresh: true,
          expectedUserId: expectedOwnerId
        )
      } else {
        authHeader = try await authService.getAuthHeader(forceRefresh: true)
      }
      try validateExpectedOwner(authPolicy)
      retry.setValue(authHeader, forHTTPHeaderField: "Authorization")
      return retry
    } catch AuthError.notSignedIn {
      await invalidateSessionAfterUnauthorized(
        endpoint: endpointLabel(for: request),
        signOutOn401: authPolicy.signOutOn401
      )
      return nil
    }
  }

  func performAuthenticatedData(
    for request: URLRequest,
    authPolicy: RequestAuthPolicy = .default,
    retriedAuth: Bool = false
  ) async throws -> (Data, HTTPURLResponse) {
    try validateExpectedOwner(authPolicy)
    let endpoint = endpointLabel(for: request)
    let (data, response) = try await session.data(for: request)
    try validateExpectedOwner(authPolicy)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIError.invalidResponse
    }

    if httpResponse.statusCode == 401 {
      if retriedAuth, authPolicy.returnsPersistent401Response {
        return (data, httpResponse)
      }
      if !retriedAuth, authPolicy.recordsAuthRetryTelemetry {
        DesktopDiagnosticsManager.shared.recordApiAuthRetry(endpoint: endpoint, outcome: "retrying")
      }
      guard let retryRequest = try await authorizedRetryRequest(
        from: request,
        retriedAuth: retriedAuth,
        authPolicy: authPolicy
      ) else {
        if authPolicy.recordsAuthRetryTelemetry {
          DesktopDiagnosticsManager.shared.recordApiAuthRetry(endpoint: endpoint, outcome: "unauthorized")
        }
        throw APIError.unauthorized
      }
      do {
        let result = try await performAuthenticatedData(
          for: retryRequest,
          authPolicy: authPolicy,
          retriedAuth: true
        )
        let (_, retryResponse) = result
        let outcome = (200...299).contains(retryResponse.statusCode) ? "succeeded" : "failed"
        if authPolicy.recordsAuthRetryTelemetry {
          DesktopDiagnosticsManager.shared.recordApiAuthRetry(endpoint: endpoint, outcome: outcome)
        }
        return result
      } catch {
        if case APIError.unauthorized = error {
          throw error
        }
        if authPolicy.recordsAuthRetryTelemetry {
          DesktopDiagnosticsManager.shared.recordApiAuthRetry(endpoint: endpoint, outcome: "failed")
        }
        throw error
      }
    }

    return (data, httpResponse)
  }

  /// An owner-bound request may finish after the app has signed out or switched
  /// accounts. The authorization header still belongs to the original owner,
  /// so never let that response flow into the new owner's local state.
  nonisolated func validateExpectedOwner(_ authPolicy: RequestAuthPolicy) throws {
    if let authorizationSnapshot = authPolicy.authorizationSnapshot {
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
        throw AuthError.userChangedDuringRequest
      }
      return
    }
    guard let expectedOwnerId = authPolicy.expectedAuthOwnerId else { return }
    guard AuthorizedToolExecution.isOwnerCurrent(expectedOwnerId) else {
      throw AuthError.userChangedDuringRequest
    }
  }

  func performRequest<T: Decodable>(
    _ request: URLRequest,
    authPolicy: RequestAuthPolicy = .default,
    retriedAuth: Bool = false
  ) async throws -> T {
    let (data, httpResponse) = try await performAuthenticatedData(
      for: request,
      authPolicy: authPolicy,
      retriedAuth: retriedAuth
    )

    guard (200...299).contains(httpResponse.statusCode) else {
      let detail = OmiHTTPTransport.extractErrorDetail(from: data)
      throw APIError.httpError(statusCode: httpResponse.statusCode, detail: detail)
    }

    do {
      let decoded = try decoder.decode(T.self, from: data)
      try validateExpectedOwner(authPolicy)
      return decoded
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
    try await delete("v1/conversations/\(id)?cascade=true")
    invalidateConversationsCountCache()
  }

  /// Updates the starred status of a conversation
  func setConversationStarred(id: String, starred: Bool) async throws -> ServerConversation {
    let url = URL(string: baseURL + "v1/conversations/\(id)/starred?starred=\(starred)")!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)

    let response: ConversationMutationResponse = try await performRequest(request)
    invalidateConversationsCountCache()
    return response.conversation
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

    try await performVoidRequest(request)
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
  func updateConversationTitle(id: String, title: String) async throws -> ServerConversation {
    var components = URLComponents(string: baseURL + "v1/conversations/\(id)/title")!
    components.queryItems = [URLQueryItem(name: "title", value: title)]
    let url = components.url!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)

    let response: ConversationMutationResponse = try await performRequest(request)
    return response.conversation
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
  func moveConversationToFolder(conversationId: String, folderId: String?) async throws -> ServerConversation {
    let body = MoveToFolderRequest(folderId: folderId)
    let url = URL(string: baseURL + "v1/conversations/\(conversationId)/folder")!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)
    request.httpBody = try JSONEncoder().encode(body)

    let response: ConversationMutationResponse = try await performRequest(request)
    invalidateConversationsCountCache()
    return response.conversation
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

    let goal: Goal = try await performRequest(request)
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

    let goal: Goal = try await performRequest(request)
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
extension APIClient {
  // MARK: - PATCH helper

  func patch<T: Decodable, B: Encodable>(
    _ endpoint: String,
    body: B,
    requireAuth: Bool = true,
    customBaseURL: String? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> T {
    let authPolicy = try resolvedRequestAuthPolicy(
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
    let authOwnerId = authPolicy.expectedAuthOwnerId
    try validateExpectedOwner(authPolicy)
    let base = customBaseURL ?? baseURL
    let url = URL(string: base + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: requireAuth,
      expectedAuthOwnerId: authOwnerId)
    try validateExpectedOwner(authPolicy)
    request.httpBody = try JSONEncoder().encode(body)

    return try await performPatchRequest(
      request,
      authPolicy: authPolicy)
  }

  private func performPatchRequest<T: Decodable>(
    _ request: URLRequest,
    authPolicy: RequestAuthPolicy = .default
  ) async throws -> T {
    // Delegate to performRequest so PATCH gets the same 401 refresh-and-retry as
    // GET/POST. PATCH previously threw `.unauthorized` on the first 401, which
    // surfaced as a user-visible failure (e.g. the onboarding language step)
    // whenever the ID token was momentarily stale right after sign-in.
    return try await performRequest(request, authPolicy: authPolicy)
  }
}
