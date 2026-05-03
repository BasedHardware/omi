import Foundation

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
  private var conversationsCountCacheTime: Date?
  private var conversationsCountCache: Int?

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

  func buildHeaders(requireAuth: Bool = true) async throws -> [String: String] {
    var headers: [String: String] = [
      "Content-Type": "application/json",
      "X-App-Platform": "macos",
      "X-Request-Start-Time": String(Date().timeIntervalSince1970),
    ]

    if requireAuth {
      if let testHeader = testAuthHeader {
        headers["Authorization"] = testHeader
      } else {
        let authService = await MainActor.run { AuthService.shared }
        let authHeader = try await authService.getAuthHeader()
        headers["Authorization"] = authHeader
      }
    }

    // BYOK: attach user-provided keys so the backend uses them for LLM/STT
    // calls this request triggers. Sent per-request; never stored server-side.
    for (provider, entry) in APIKeyService.byokSnapshot {
      headers[provider.headerName] = entry.key
    }

    return headers
  }

  // MARK: - HTTP Methods

  func get<T: Decodable>(
    _ endpoint: String,
    requireAuth: Bool = true,
    customBaseURL: String? = nil
  ) async throws -> T {
    let base = customBaseURL ?? baseURL
    let url = URL(string: base + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth)

    return try await performRequest(request)
  }

  func post<T: Decodable, B: Encodable>(
    _ endpoint: String,
    body: B,
    requireAuth: Bool = true,
    customBaseURL: String? = nil
  ) async throws -> T {
    let base = customBaseURL ?? baseURL
    let url = URL(string: base + endpoint)!
    log("APIClient: POST \(url.absoluteString)")
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth)
    request.httpBody = try JSONEncoder().encode(body)

    return try await performRequest(request)
  }

  func post<T: Decodable>(
    _ endpoint: String,
    requireAuth: Bool = true,
    customBaseURL: String? = nil
  ) async throws -> T {
    let base = customBaseURL ?? baseURL
    let url = URL(string: base + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth)

    return try await performRequest(request)
  }

  func delete(
    _ endpoint: String,
    requireAuth: Bool = true,
    customBaseURL: String? = nil
  ) async throws {
    let base = customBaseURL ?? baseURL
    let url = URL(string: base + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "DELETE"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth)

    let (_, response) = try await session.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIError.invalidResponse
    }

    if httpResponse.statusCode == 401 {
      throw APIError.unauthorized
    }

    guard (200...299).contains(httpResponse.statusCode) else {
      throw APIError.httpError(statusCode: httpResponse.statusCode)
    }
  }

  // MARK: - Request Execution

  private func performRequest<T: Decodable>(_ request: URLRequest) async throws -> T {
    let (data, response) = try await session.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIError.invalidResponse
    }

    // Handle 401 - token might be expired
    if httpResponse.statusCode == 401 {
      // Try to refresh token and retry once
      let authService = await MainActor.run { AuthService.shared }
      _ = try await authService.getIdToken(forceRefresh: true)

      var retryRequest = request
      retryRequest.setValue(
        try await authService.getAuthHeader(), forHTTPHeaderField: "Authorization")

      let (retryData, retryResponse) = try await session.data(for: retryRequest)

      guard let retryHttpResponse = retryResponse as? HTTPURLResponse else {
        throw APIError.invalidResponse
      }

      if retryHttpResponse.statusCode == 401 {
        throw APIError.unauthorized
      }

      guard (200...299).contains(retryHttpResponse.statusCode) else {
        throw APIError.httpError(statusCode: retryHttpResponse.statusCode)
      }

      return try decoder.decode(T.self, from: retryData)
    }

    guard (200...299).contains(httpResponse.statusCode) else {
      throw APIError.httpError(statusCode: httpResponse.statusCode)
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
}

// MARK: - API Errors

enum APIError: LocalizedError {
  case invalidResponse
  case unauthorized
  case httpError(statusCode: Int)
  case decodingError(Error)

  var errorDescription: String? {
    switch self {
    case .invalidResponse:
      return "Invalid response from server"
    case .unauthorized:
      return "Unauthorized - please sign in again"
    case .httpError(let statusCode):
      return "HTTP error: \(statusCode)"
    case .decodingError(let error):
      return "Failed to decode response: \(error.localizedDescription)"
    }
  }
}

// MARK: - Conversation API

extension APIClient {

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
      "include_discarded=\(includeDiscarded)",
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
    struct TitleUpdate: Encodable {
      let title: String
    }

    let url = URL(string: baseURL + "v1/conversations/\(id)")!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)
    request.httpBody = try JSONEncoder().encode(TitleUpdate(title: title))

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

  /// Gets the total count of conversations. Uses 5-second cache to deduplicate parallel calls.
  func getConversationsCount(
    includeDiscarded: Bool = false,
    statuses: [ConversationStatus] = [.completed, .processing]
  ) async throws -> Int {
    if let cache = conversationsCountCache, let time = conversationsCountCacheTime,
      Date().timeIntervalSince(time) < 5
    {
      return cache
    }

    var queryItems: [String] = [
      "include_discarded=\(includeDiscarded)"
    ]

    if !statuses.isEmpty {
      let statusStrings = statuses.map { $0.rawValue }.joined(separator: ",")
      queryItems.append("statuses=\(statusStrings)")
    }

    let endpoint = "v1/conversations/count?\(queryItems.joined(separator: "&"))"

    struct CountResponse: Decodable {
      let count: Int
    }

    let response: CountResponse = try await get(endpoint)
    conversationsCountCache = response.count
    conversationsCountCacheTime = Date()
    return response.count
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
    return try await post("v1/conversations/merge", body: body)
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

struct ServerConversation: Codable, Identifiable, Equatable {
  static func == (lhs: ServerConversation, rhs: ServerConversation) -> Bool {
    lhs.id == rhs.id && lhs.createdAt == rhs.createdAt && lhs.startedAt == rhs.startedAt
      && lhs.finishedAt == rhs.finishedAt && lhs.structured == rhs.structured
      && lhs.status == rhs.status && lhs.discarded == rhs.discarded && lhs.deleted == rhs.deleted
      && lhs.starred == rhs.starred && lhs.folderId == rhs.folderId && lhs.source == rhs.source
  }

  let id: String
  let createdAt: Date
  let startedAt: Date?
  let finishedAt: Date?

  var structured: Structured
  var transcriptSegments: [TranscriptSegment]
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
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)

    id = try container.decode(String.self, forKey: .id)
    createdAt = try container.decode(Date.self, forKey: .createdAt)
    startedAt = try container.decodeIfPresent(Date.self, forKey: .startedAt)
    finishedAt = try container.decodeIfPresent(Date.self, forKey: .finishedAt)
    structured = try container.decode(Structured.self, forKey: .structured)
    transcriptSegments =
      try container.decodeIfPresent([TranscriptSegment].self, forKey: .transcriptSegments) ?? []
    geolocation = try container.decodeIfPresent(Geolocation.self, forKey: .geolocation)
    photos = try container.decodeIfPresent([ConversationPhoto].self, forKey: .photos) ?? []
    appsResults = try container.decodeIfPresent([AppResponse].self, forKey: .appsResults) ?? []
    source = try container.decodeIfPresent(ConversationSource.self, forKey: .source)
    language = try container.decodeIfPresent(String.self, forKey: .language)
    status = try container.decodeIfPresent(ConversationStatus.self, forKey: .status) ?? .completed
    discarded = try container.decodeIfPresent(Bool.self, forKey: .discarded) ?? false
    deleted = try container.decodeIfPresent(Bool.self, forKey: .deleted) ?? false
    isLocked = try container.decodeIfPresent(Bool.self, forKey: .isLocked) ?? false
    starred = try container.decodeIfPresent(Bool.self, forKey: .starred) ?? false
    folderId = try container.decodeIfPresent(String.self, forKey: .folderId)
    inputDeviceName = try container.decodeIfPresent(String.self, forKey: .inputDeviceName)
  }

  /// Memberwise initializer for creating from local storage
  init(
    id: String,
    createdAt: Date,
    startedAt: Date?,
    finishedAt: Date?,
    structured: Structured,
    transcriptSegments: [TranscriptSegment],
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
    inputDeviceName: String?
  ) {
    self.id = id
    self.createdAt = createdAt
    self.startedAt = startedAt
    self.finishedAt = finishedAt
    self.structured = structured
    self.transcriptSegments = transcriptSegments
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
}

struct Structured: Codable, Equatable {
  var title: String
  let overview: String
  let emoji: String
  let category: String
  let actionItems: [ActionItem]
  let events: [Event]

  enum CodingKeys: String, CodingKey {
    case title, overview, emoji, category
    case actionItems = "action_items"
    case events
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)

    title = try container.decodeIfPresent(String.self, forKey: .title) ?? ""
    overview = try container.decodeIfPresent(String.self, forKey: .overview) ?? ""
    emoji = try container.decodeIfPresent(String.self, forKey: .emoji) ?? ""
    category = try container.decodeIfPresent(String.self, forKey: .category) ?? "other"
    actionItems = try container.decodeIfPresent([ActionItem].self, forKey: .actionItems) ?? []
    events = try container.decodeIfPresent([Event].self, forKey: .events) ?? []
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

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
    completed = try container.decodeIfPresent(Bool.self, forKey: .completed) ?? false
    deleted = try container.decodeIfPresent(Bool.self, forKey: .deleted) ?? false
  }
}

struct Event: Codable, Identifiable, Equatable {
  var id: String { title + startsAt.description }
  let title: String
  let startsAt: Date
  let duration: Int
  let description: String
  let created: Bool

  enum CodingKeys: String, CodingKey {
    case title
    case startsAt = "starts_at"
    case duration
    case description
    case created
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    title = try container.decodeIfPresent(String.self, forKey: .title) ?? ""
    startsAt = try container.decodeIfPresent(Date.self, forKey: .startsAt) ?? Date()
    duration = try container.decodeIfPresent(Int.self, forKey: .duration) ?? 0
    description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
    created = try container.decodeIfPresent(Bool.self, forKey: .created) ?? false
  }
}

/// Translation from backend
struct TranscriptTranslation: Codable {
  let lang: String
  let text: String
}

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

struct Geolocation: Codable {
  let latitude: Double?
  let longitude: Double?
  let address: String?
  let locationType: String?

  enum CodingKeys: String, CodingKey {
    case latitude, longitude, address
    case locationType = "location_type"
  }
}

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
}

struct AppResponse: Codable, Identifiable {
  var id: String { appId ?? UUID().uuidString }
  let appId: String?
  let content: String

  enum CodingKeys: String, CodingKey {
    case appId = "app_id"
    case content
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

  var displayName: String {
    switch self {
    case .system: return "System"
    case .interesting: return "Interesting"
    case .manual: return "Manual"
    }
  }

  var icon: String {
    switch self {
    case .system: return "gearshape"
    case .interesting: return "sparkles"
    case .manual: return "square.and.pencil"
    }
  }
}

struct ServerMemory: Codable, Identifiable {
  let id: String
  let content: String
  let category: MemoryCategory
  let createdAt: Date
  let updatedAt: Date
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
  // Short headline for notification preview (advice/tips only)
  let headline: String?

  enum CodingKeys: String, CodingKey {
    case id, content, category, reviewed, visibility, scoring, source, confidence, tags, reasoning,
      headline
    case createdAt = "created_at"
    case updatedAt = "updated_at"
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
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    content = try container.decode(String.self, forKey: .content)
    category = try container.decodeIfPresent(MemoryCategory.self, forKey: .category) ?? .system
    createdAt = try container.decode(Date.self, forKey: .createdAt)
    updatedAt = try container.decode(Date.self, forKey: .updatedAt)
    conversationId = try container.decodeIfPresent(String.self, forKey: .conversationId)
    reviewed = try container.decodeIfPresent(Bool.self, forKey: .reviewed) ?? false
    userReview = try container.decodeIfPresent(Bool.self, forKey: .userReview)
    visibility = try container.decodeIfPresent(String.self, forKey: .visibility) ?? "private"
    manuallyAdded = try container.decodeIfPresent(Bool.self, forKey: .manuallyAdded) ?? false
    scoring = try container.decodeIfPresent(String.self, forKey: .scoring)
    source = try container.decodeIfPresent(String.self, forKey: .source)
    confidence = try container.decodeIfPresent(Double.self, forKey: .confidence)
    sourceApp = try container.decodeIfPresent(String.self, forKey: .sourceApp)
    contextSummary = try container.decodeIfPresent(String.self, forKey: .contextSummary)
    isRead = try container.decodeIfPresent(Bool.self, forKey: .isRead) ?? false
    isDismissed = try container.decodeIfPresent(Bool.self, forKey: .isDismissed) ?? false
    tags = try container.decodeIfPresent([String].self, forKey: .tags) ?? []
    reasoning = try container.decodeIfPresent(String.self, forKey: .reasoning)
    currentActivity = try container.decodeIfPresent(String.self, forKey: .currentActivity)
    inputDeviceName = try container.decodeIfPresent(String.self, forKey: .inputDeviceName)
    windowTitle = try container.decodeIfPresent(String.self, forKey: .windowTitle)
    headline = try container.decodeIfPresent(String.self, forKey: .headline)
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
    } catch APIError.httpError(let statusCode) where statusCode == 404 {
      // 404 = no in-progress conversation found — WS close handler already processed it
      return nil
    }
  }
}

// MARK: - Memories API

extension APIClient {

  /// Fetches memories from the API with optional filtering
  func getMemories(
    limit: Int = 100,
    offset: Int = 0,
    category: String? = nil,
    tags: [String]? = nil,
    includeDismissed: Bool = false
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
    return try await get(endpoint)
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

  /// Creates many memories in a single HTTP call. Used by the onboarding
  /// local-file import flow to avoid fanning out N requests and tripping
  /// Cloud Armor's per-Authorization 120/min throttle.
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

  /// Updates visibility of all memories
  func updateAllMemoriesVisibility(visibility: String) async throws {
    struct VisibilityRequest: Encodable {
      let value: String
    }
    let body = VisibilityRequest(value: visibility)
    let _: MemoryStatusResponse = try await patch("v3/memories/visibility", body: body)
  }

  /// Deletes all memories
  func deleteAllMemories() async throws {
    try await delete("v3/memories")
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
    let (data, response) = try await session.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIError.invalidResponse
    }

    if httpResponse.statusCode == 401 {
      throw APIError.unauthorized
    }

    guard (200...299).contains(httpResponse.statusCode) else {
      throw APIError.httpError(statusCode: httpResponse.statusCode)
    }

    return try decoder.decode(T.self, from: data)
  }
}

struct CreateMemoryResponse: Codable {
  let id: String
  let message: String?
}

/// One item in a POST /v3/memories/batch payload. Mirrors the `Memory` model
/// in `backend/models/memories.py` (the server hardcodes category=manual on
/// batch creation, so we intentionally don't send it).
struct MemoryBatchItem: Encodable {
  let content: String
  let visibility: String
  let tags: [String]
  let headline: String?

  init(content: String, visibility: String = "private", tags: [String] = [], headline: String? = nil)
  {
    self.content = content
    self.visibility = visibility
    self.tags = tags
    self.headline = headline
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
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    title = try container.decodeIfPresent(String.self, forKey: .title) ?? ""
    description = try container.decodeIfPresent(String.self, forKey: .description)
    goalType = try container.decodeIfPresent(GoalType.self, forKey: .goalType) ?? .boolean
    targetValue = try container.decodeIfPresent(Double.self, forKey: .targetValue) ?? 1.0
    currentValue = try container.decodeIfPresent(Double.self, forKey: .currentValue) ?? 0.0
    minValue = try container.decodeIfPresent(Double.self, forKey: .minValue) ?? 0.0
    maxValue = try container.decodeIfPresent(Double.self, forKey: .maxValue) ?? 100.0
    unit = try container.decodeIfPresent(String.self, forKey: .unit)
    isActive = try container.decodeIfPresent(Bool.self, forKey: .isActive) ?? true
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
    updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt) ?? Date()
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
    return ((currentValue - minValue) / (targetValue - minValue)) * 100.0
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
    twitter = try container.decodeIfPresent(String.self, forKey: .twitter)
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

    var queryItems: [String] = [
      "limit=\(limit)",
      "offset=\(offset)",
    ]

    if let query = query, !query.isEmpty {
      queryItems.append(
        "query=\(query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query)")
    }

    if let category = category {
      queryItems.append("category=\(category)")
    }

    if let capability = capability {
      queryItems.append("capability=\(capability)")
    }

    if let minRating = minRating {
      queryItems.append("rating=\(minRating)")
    }

    if installedOnly {
      queryItems.append("installed_apps=true")
    }

    let endpoint = "v2/apps/search?\(queryItems.joined(separator: "&"))"
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
    guard !url.isEmpty else { return true }
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

  /// Updates user language preference
  func updateUserLanguage(_ language: String) async throws -> UserLanguageResponse {
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

/// User language response
struct UserLanguageResponse: Codable {
  let language: String
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
  var elevenLabsVoiceID: String?

  enum CodingKeys: String, CodingKey {
    case voiceAnswersEnabled = "voice_answers_enabled"
    case elevenLabsVoiceID = "elevenlabs_voice_id"
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

  enum CodingKeys: String, CodingKey {
    case shared, focus, task
    case insight = "advice"
    case memory
    case floatingBar = "floating_bar"
    case updateChannel = "update_channel"
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
    metadata: String? = nil
  ) async throws -> SaveMessageResponse {
    struct SaveRequest: Encodable {
      let text: String
      let sender: String
      let app_id: String?
      let session_id: String?
      let metadata: String?
    }
    let body = SaveRequest(
      text: text, sender: sender, app_id: appId, session_id: sessionId, metadata: metadata)
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

    let (data, response) = try await session.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIError.invalidResponse
    }

    if httpResponse.statusCode == 401 {
      throw APIError.unauthorized
    }

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

}

/// Response from rating a message
struct MessageStatusResponse: Codable {
  let status: String
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

  enum CodingKeys: String, CodingKey {
    case id
    case createdAt = "created_at"
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

  enum CodingKeys: String, CodingKey {
    case id, text, sender, rating, reported
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
  let createdAt: Date
  let updatedAt: Date

  enum CodingKeys: String, CodingKey {
    case id, name
    case createdAt = "created_at"
    case updatedAt = "updated_at"
  }
}

// MARK: - People API

extension APIClient {

  func getUserSubscription() async throws -> UserSubscriptionResponse {
    return try await get("v1/users/me/subscription")
  }

  func getAvailablePlans() async throws -> AvailablePlansResponse {
    return try await get("v1/payments/available-plans")
  }

  func getOverageInfo() async throws -> OverageInfoResponse {
    return try await get("v1/payments/overage-info")
  }

  func createCheckoutSession(priceId: String) async throws -> CheckoutSessionResponse {
    struct Request: Encodable {
      let priceId: String

      enum CodingKeys: String, CodingKey {
        case priceId = "price_id"
      }
    }

    return try await post("v1/payments/checkout-session", body: Request(priceId: priceId))
  }

  func upgradeSubscription(priceId: String) async throws -> UpgradeSubscriptionResponse {
    struct Request: Encodable {
      let priceId: String

      enum CodingKeys: String, CodingKey {
        case priceId = "price_id"
      }
    }

    return try await post("v1/payments/upgrade-subscription", body: Request(priceId: priceId))
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
      "v1/users/me/byok-active", body: Request(fingerprints: fingerprints)
    )
  }

  /// Deactivate BYOK (user cleared keys) so they return to the paid plan gate.
  func deactivateBYOK() async throws {
    try await delete("v1/users/me/byok-active")
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

  // MARK: - TTS Proxy (issue #6622)

  struct TtsSynthesizeRequest: Encodable {
    let text: String
    let voiceId: String
    let modelId: String
    let outputFormat: String
    let voiceSettings: TtsVoiceSettings

    enum CodingKeys: String, CodingKey {
      case text
      case voiceId = "voice_id"
      case modelId = "model_id"
      case outputFormat = "output_format"
      case voiceSettings = "voice_settings"
    }
  }

  struct TtsVoiceSettings: Encodable {
    let stability: Double
    let similarityBoost: Double
    let style: Double
    let useSpeakerBoost: Bool

    enum CodingKeys: String, CodingKey {
      case stability
      case similarityBoost = "similarity_boost"
      case style
      case useSpeakerBoost = "use_speaker_boost"
    }
  }

  /// Synthesize speech via the backend TTS proxy (ElevenLabs key stays server-side).
  /// Returns raw audio data (audio/mpeg).
  func synthesizeSpeech(request: TtsSynthesizeRequest) async throws -> Data {
    let base = rustBackendURL
    let url = URL(string: base + "v1/tts/synthesize")!
    var urlRequest = URLRequest(url: url)
    urlRequest.httpMethod = "POST"
    urlRequest.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)
    urlRequest.httpBody = try JSONEncoder().encode(request)
    urlRequest.timeoutInterval = 60

    let (data, response) = try await session.data(for: urlRequest)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIError.invalidResponse
    }

    if httpResponse.statusCode == 401 {
      // Retry with refreshed token
      let authService = await MainActor.run { AuthService.shared }
      _ = try await authService.getIdToken(forceRefresh: true)

      var retryRequest = urlRequest
      retryRequest.setValue(
        try await authService.getAuthHeader(), forHTTPHeaderField: "Authorization")

      let (retryData, retryResponse) = try await session.data(for: retryRequest)
      guard let retryHttpResponse = retryResponse as? HTTPURLResponse else {
        throw APIError.invalidResponse
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
}
