import Foundation

// MARK: - Beeper Desktop API client
//
// Durable local harness for the Beeper Desktop API (INV-INT-1): everything
// speaks the documented REST/WS contract on localhost — never the Beeper UI.
// Contract source: @beeper/desktop-api 5.0.0 TypeScript definitions +
// https://developers.beeper.com/desktop-api.

enum BeeperClientError: Error, Equatable {
  case notConfigured
  case invalidURL
  case httpError(statusCode: Int, code: String?)
  case invalidResponse
}

// MARK: - Wire models (subset of the SDK schema that the clone needs)

struct BeeperUser: Codable, Equatable {
  let id: String
  var fullName: String?
  var username: String?
  var isSelf: Bool?
}

struct BeeperAccount: Codable, Equatable, Identifiable {
  let accountID: String
  var network: String?
  var user: BeeperUser?

  var id: String { accountID }

  /// Human label for UI chips ("WhatsApp", "Telegram", "iMessage", …).
  var displayNetwork: String {
    if let network, !network.isEmpty { return network }
    return accountID
  }
}

struct BeeperParticipants: Codable, Equatable {
  var hasMore: Bool?
  var items: [BeeperUser]?
}

struct BeeperChat: Codable, Equatable, Identifiable {
  let id: String
  let accountID: String
  var network: String?
  var title: String?
  var type: String?  // "single" | "group"
  var unreadCount: Int?
  var participants: BeeperParticipants?
  var isMuted: Bool?
  var isArchived: Bool?
  var isReadOnly: Bool?
  var lastActivity: String?

  var isSingle: Bool { (type ?? "single") == "single" }
}

struct BeeperMessage: Codable, Equatable, Identifiable {
  let id: String
  var accountID: String?
  var chatID: String?
  var senderID: String?
  var senderName: String?
  var sortKey: String?
  var timestamp: String?
  var text: String?
  var type: String?  // TEXT | NOTICE | IMAGE | ...
  var isSender: Bool?
  var isUnread: Bool?
  var isDeleted: Bool?

  var isTextLike: Bool { (type ?? "TEXT") == "TEXT" }
}

struct BeeperCursorPage<Item: Codable & Equatable>: Codable, Equatable {
  var items: [Item]
  var hasMore: Bool?
  var oldestCursor: String?
  var newestCursor: String?
}

struct BeeperSendResponse: Codable, Equatable {
  let chatID: String
  let pendingMessageID: String
}

struct BeeperInfo: Codable, Equatable {
  // /v1/info is public server metadata. Keep everything optional so a Beeper
  // upgrade never breaks the probe; we only read `server.base_url` to
  // self-correct the port.
  struct Server: Codable, Equatable {
    var baseURL: String?
    var port: Int?

    enum CodingKeys: String, CodingKey {
      case baseURL = "base_url"
      case port
    }
  }

  var server: Server?
}

// MARK: - Live event stream wire models (ws://…/v1/ws, experimental)

struct BeeperLiveEvent: Codable, Equatable {
  let type: String  // message.upserted | message.deleted | chat.upserted | chat.deleted | ready | ...
  var seq: Int?
  var ts: Double?
  var chatID: String?
  var ids: [String]?
  var entries: [BeeperMessage]?
}

// MARK: - Client

/// Thin async client over the local Beeper Desktop REST API.
///
/// All calls are local (localhost) and authenticated with the user's Beeper
/// access token. The transport is injectable so tests run against a stub
/// `URLProtocol` with recorded fixtures instead of a live Beeper install.
struct BeeperDesktopClient {
  var baseURL: URL
  var accessToken: String
  var session: URLSession

  /// Beeper Desktop's local API port. Current builds bind 23374; older builds
  /// used 23373. `discoverBaseURL` probes both and then adopts whatever the
  /// running app reports in `/v1/info`, so a version/port change never breaks
  /// the connector.
  static let defaultBaseURL = URL(string: "http://127.0.0.1:23374")!
  static let candidatePorts = [23374, 23373]

  init(
    accessToken: String,
    baseURL: URL = BeeperDesktopClient.defaultBaseURL,
    session: URLSession = BeeperDesktopClient.makeDefaultSession()
  ) {
    self.accessToken = accessToken
    self.baseURL = baseURL
    self.session = session
  }

  static func makeDefaultSession() -> URLSession {
    let config = URLSessionConfiguration.ephemeral
    config.timeoutIntervalForRequest = 15
    return URLSession(configuration: config)
  }

  /// Locate the running Beeper Desktop API without needing a token: `/v1/info`
  /// is public and reports the authoritative `server.base_url`. Probes each
  /// candidate port and returns the URL the app itself advertises (falling
  /// back to the reachable candidate). Returns nil when Beeper isn't running.
  static func discoverBaseURL(
    session: URLSession = BeeperDesktopClient.makeDefaultSession()
  ) async -> URL? {
    for port in candidatePorts {
      guard let candidate = URL(string: "http://127.0.0.1:\(port)") else { continue }
      guard let info = try? await BeeperDesktopClient(accessToken: "probe", baseURL: candidate, session: session)
        .probeInfo()
      else { continue }
      if let advertised = info.server?.baseURL, let url = URL(string: advertised) {
        return url
      }
      return candidate
    }
    return nil
  }

  // MARK: Endpoints

  /// Functional probe: proves the API is reachable AND the token is accepted.
  func probeInfo() async throws -> BeeperInfo {
    try await request("GET", "/v1/info")
  }

  func listAccounts() async throws -> [BeeperAccount] {
    try await request("GET", "/v1/accounts")
  }

  func searchChats(limit: Int = 60, type: String? = nil) async throws -> BeeperCursorPage<BeeperChat> {
    var query = [URLQueryItem(name: "limit", value: String(limit))]
    if let type { query.append(URLQueryItem(name: "type", value: type)) }
    return try await request("GET", "/v1/chats/search", query: query)
  }

  /// Messages sorted by timestamp; `direction=before` + cursor walks history.
  func listMessages(
    chatID: String,
    cursor: String? = nil,
    direction: String? = nil
  ) async throws -> BeeperCursorPage<BeeperMessage> {
    var query: [URLQueryItem] = []
    if let cursor { query.append(URLQueryItem(name: "cursor", value: cursor)) }
    if let direction { query.append(URLQueryItem(name: "direction", value: direction)) }
    return try await request(
      "GET", "/v1/chats/\(encodePath(chatID))/messages", query: query)
  }

  func sendMessage(chatID: String, text: String, replyToMessageID: String? = nil) async throws -> BeeperSendResponse {
    var body: [String: Any] = ["text": text]
    if let replyToMessageID { body["replyToMessageID"] = replyToMessageID }
    return try await request(
      "POST", "/v1/chats/\(encodePath(chatID))/messages", jsonBody: body)
  }

  /// Draft mode: place the proposed reply into the chat's compose box.
  /// PATCH /v1/chats/{chatID} accepts a draft object; null clears it first so
  /// a stale prior draft can never block the update.
  func setDraft(chatID: String, text: String) async throws {
    let path = "/v1/chats/\(encodePath(chatID))"
    let clear: [String: Any?] = ["draft": nil]
    _ = try await requestRaw("PATCH", path, jsonBody: clear as [String: Any])
    _ = try await requestRaw("PATCH", path, jsonBody: ["draft": ["text": text]])
  }

  /// Benchmark replay source: filtered message history across chats.
  func searchMessages(
    chatIDs: [String]? = nil,
    sender: String? = nil,
    chatType: String? = nil,
    dateAfter: String? = nil,
    limit: Int = 100,
    cursor: String? = nil
  ) async throws -> BeeperCursorPage<BeeperMessage> {
    var query = [URLQueryItem(name: "limit", value: String(limit))]
    if let chatIDs { for id in chatIDs { query.append(URLQueryItem(name: "chatIDs", value: id)) } }
    if let sender { query.append(URLQueryItem(name: "sender", value: sender)) }
    if let chatType { query.append(URLQueryItem(name: "chatType", value: chatType)) }
    if let dateAfter { query.append(URLQueryItem(name: "dateAfter", value: dateAfter)) }
    if let cursor { query.append(URLQueryItem(name: "cursor", value: cursor)) }
    return try await request("GET", "/v1/messages/search", query: query)
  }

  // MARK: WebSocket

  func makeWebSocketTask() throws -> URLSessionWebSocketTask {
    guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
      throw BeeperClientError.invalidURL
    }
    components.scheme = components.scheme == "https" ? "wss" : "ws"
    components.path = "/v1/ws"
    guard let url = components.url else { throw BeeperClientError.invalidURL }
    var request = URLRequest(url: url)
    request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
    return session.webSocketTask(with: request)
  }

  /// `subscriptions.set` fully replaces subscriptions; `["*"]` = all chats.
  static func subscriptionsSetPayload(chatIDs: [String], requestID: String) throws -> String {
    let payload: [String: Any] = [
      "type": "subscriptions.set",
      "requestID": requestID,
      "chatIDs": chatIDs,
    ]
    let data = try JSONSerialization.data(withJSONObject: payload)
    return String(decoding: data, as: UTF8.self)
  }

  static func decodeLiveEvent(_ text: String) -> BeeperLiveEvent? {
    guard let data = text.data(using: .utf8) else { return nil }
    return try? JSONDecoder().decode(BeeperLiveEvent.self, from: data)
  }

  // MARK: Transport

  private func encodePath(_ component: String) -> String {
    component.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/")))
      ?? component
  }

  private func request<T: Decodable>(
    _ method: String,
    _ path: String,
    query: [URLQueryItem] = [],
    jsonBody: [String: Any]? = nil
  ) async throws -> T {
    let data = try await requestRaw(method, path, query: query, jsonBody: jsonBody)
    do {
      return try JSONDecoder().decode(T.self, from: data)
    } catch {
      throw BeeperClientError.invalidResponse
    }
  }

  @discardableResult
  private func requestRaw(
    _ method: String,
    _ path: String,
    query: [URLQueryItem] = [],
    jsonBody: [String: Any]? = nil
  ) async throws -> Data {
    guard !accessToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      throw BeeperClientError.notConfigured
    }
    guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
      throw BeeperClientError.invalidURL
    }
    components.path = path
    if !query.isEmpty { components.queryItems = query }
    guard let url = components.url else { throw BeeperClientError.invalidURL }

    var request = URLRequest(url: url)
    request.httpMethod = method
    request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    if let jsonBody {
      request.setValue("application/json", forHTTPHeaderField: "Content-Type")
      request.httpBody = try JSONSerialization.data(withJSONObject: jsonBody, options: [])
    }

    let (data, response) = try await session.data(for: request)
    guard let http = response as? HTTPURLResponse else {
      throw BeeperClientError.invalidResponse
    }
    guard (200..<300).contains(http.statusCode) else {
      let code = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])
        .flatMap { ($0?["error"] as? [String: Any])?["code"] as? String ?? $0?["code"] as? String }
      throw BeeperClientError.httpError(statusCode: http.statusCode, code: code)
    }
    return data
  }
}
