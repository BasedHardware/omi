import AppKit
import CryptoKit
import Foundation
import Network

/// Connects Omi to the user's Notion workspace over Notion's hosted MCP server
/// (mcp.notion.com). One OAuth grant powers both directions: writing the
/// "Omi Memories" page today, and reading workspace content into Omi later
/// (the token also covers notion-search / notion-fetch).
///
/// Auth is standard MCP OAuth: dynamic client registration + PKCE + loopback
/// redirect. No pre-registered client and no Notion app review is needed —
/// the /register endpoint is open (verified live 2026-07-21).
final class NotionMCPConnector: @unchecked Sendable {
  static let shared = NotionMCPConnector()

  private static let base = URL(string: "https://mcp.notion.com")!
  private static let keychainService = "com.omi.desktop.notion-mcp"
  private static let keychainAccount = "oauth"
  private static let pageIDKey = "memoryExportNotionPageID"
  private static let pageURLKey = "memoryExportNotionPageURL"
  private static let userAgent = "omi-desktop/1.0"
  private static let memoriesPageTitle = "Omi Memories"

  struct StoredAuth: Codable {
    var accessToken: String
    var refreshToken: String?
    var expiresAt: Date
    var clientID: String
  }

  enum ConnectError: LocalizedError {
    case timedOut
    case badResponse(String)
    case notConnected

    var errorDescription: String? {
      switch self {
      case .timedOut: return "Notion authorization timed out. Try again."
      case .badResponse(let detail): return "Notion setup failed: \(detail)"
      case .notConnected: return "Connect Notion first."
      }
    }
  }

  var isConnected: Bool { loadAuth() != nil }

  var memoriesPageURL: URL? {
    UserDefaults.standard.string(forKey: Self.pageURLKey).flatMap(URL.init(string:))
  }

  func disconnect() {
    DesktopKeychainStore.delete(service: Self.keychainService, account: Self.keychainAccount)
    UserDefaults.standard.removeObject(forKey: Self.pageIDKey)
    UserDefaults.standard.removeObject(forKey: Self.pageURLKey)
  }

  // MARK: - OAuth connect

  /// Full browser OAuth: register a client for a fresh loopback port, open the
  /// consent page, await the redirect, exchange the code, store tokens.
  func connect() async throws {
    let listener = try OAuthCallbackListener()
    defer { listener.cancel() }
    let redirectURI = "http://localhost:\(listener.port)/callback"

    let registration = try await postJSON(
      url: Self.base.appendingPathComponent("register"),
      body: [
        "client_name": "Omi Memory",
        "redirect_uris": [redirectURI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
      ])
    guard let clientID = registration["client_id"] as? String else {
      throw ConnectError.badResponse("client registration rejected")
    }

    let verifier = Self.randomURLSafe(64)
    let challenge = Self.codeChallenge(for: verifier)
    let state = Self.randomURLSafe(24)

    guard
      var components = URLComponents(
        url: Self.base.appendingPathComponent("authorize"), resolvingAgainstBaseURL: false)
    else {
      throw ConnectError.badResponse("could not build the authorize URL")
    }
    components.queryItems = [
      URLQueryItem(name: "client_id", value: clientID),
      URLQueryItem(name: "response_type", value: "code"),
      URLQueryItem(name: "redirect_uri", value: redirectURI),
      URLQueryItem(name: "code_challenge", value: challenge),
      URLQueryItem(name: "code_challenge_method", value: "S256"),
      URLQueryItem(name: "state", value: state),
    ]
    guard let authorizeURL = components.url else {
      throw ConnectError.badResponse("could not build the authorize URL")
    }
    _ = await MainActor.run { NSWorkspace.shared.open(authorizeURL) }

    let params = try await listener.waitForCallback(timeout: 240)
    guard params["state"] == state, let code = params["code"] else {
      throw ConnectError.badResponse("authorization was denied or the redirect was invalid")
    }

    let token = try await postForm(
      url: Self.base.appendingPathComponent("token"),
      fields: [
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirectURI,
        "client_id": clientID,
        "code_verifier": verifier,
      ])
    try storeAuth(from: token, clientID: clientID)
  }

  // MARK: - Token lifecycle

  static func needsRefresh(expiresAt: Date, now: Date = Date()) -> Bool {
    now >= expiresAt.addingTimeInterval(-300)
  }

  private func validAccessToken() async throws -> String {
    guard let auth = loadAuth() else { throw ConnectError.notConnected }
    guard Self.needsRefresh(expiresAt: auth.expiresAt) else { return auth.accessToken }
    guard let refreshToken = auth.refreshToken else { throw ConnectError.notConnected }
    let token = try await postForm(
      url: Self.base.appendingPathComponent("token"),
      fields: [
        "grant_type": "refresh_token",
        "refresh_token": refreshToken,
        "client_id": auth.clientID,
      ])
    try storeAuth(from: token, clientID: auth.clientID, fallbackRefreshToken: refreshToken)
    guard let refreshed = loadAuth() else { throw ConnectError.notConnected }
    return refreshed.accessToken
  }

  private func storeAuth(
    from token: [String: Any], clientID: String, fallbackRefreshToken: String? = nil
  ) throws {
    guard let access = token["access_token"] as? String else {
      throw ConnectError.badResponse("token exchange failed")
    }
    let expiresIn = (token["expires_in"] as? Double) ?? 3600
    let auth = StoredAuth(
      accessToken: access,
      refreshToken: (token["refresh_token"] as? String) ?? fallbackRefreshToken,
      expiresAt: Date().addingTimeInterval(expiresIn),
      clientID: clientID)
    let data = try JSONEncoder().encode(auth)
    _ = DesktopKeychainStore.setString(
      String(decoding: data, as: UTF8.self),
      service: Self.keychainService, account: Self.keychainAccount)
  }

  private func loadAuth() -> StoredAuth? {
    guard
      let raw = DesktopKeychainStore.string(
        service: Self.keychainService, account: Self.keychainAccount),
      let auth = try? JSONDecoder().decode(StoredAuth.self, from: Data(raw.utf8))
    else { return nil }
    return auth
  }

  // MARK: - Memories page sync

  /// Writes the markdown pack to the "Omi Memories" page: replaces content when
  /// the page exists, creates it (and remembers its id) on first sync or if the
  /// user deleted it.
  func syncMemories(markdown: String) async throws -> URL? {
    let token = try await validAccessToken()
    let session = try await initializeSession(token: token)

    if let pageID = UserDefaults.standard.string(forKey: Self.pageIDKey) {
      let update = try await toolsCall(
        name: "notion-update-page",
        arguments: ["page_id": pageID, "command": "replace_content", "new_str": markdown],
        token: token, session: session)
      if !Self.toolCallFailed(update) {
        return memoriesPageURL
      }
      // Page was likely deleted by the user; fall through and recreate.
    }

    let create = try await toolsCall(
      name: "notion-create-pages",
      arguments: [
        "pages": [["properties": ["title": Self.memoriesPageTitle], "content": markdown]]
      ],
      token: token, session: session)
    guard let record = Self.pageRecord(fromToolResult: create) else {
      throw ConnectError.badResponse("Notion did not return the created page")
    }
    UserDefaults.standard.set(record.id, forKey: Self.pageIDKey)
    UserDefaults.standard.set(record.url, forKey: Self.pageURLKey)
    return URL(string: record.url)
  }

  // MARK: - MCP plumbing

  private func initializeSession(token: String) async throws -> String? {
    let (body, session) = try await mcpRequest(
      payload: [
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": [
          "protocolVersion": "2025-03-26", "capabilities": [:],
          "clientInfo": ["name": "omi-desktop", "version": "1.0"],
        ],
      ], token: token, session: nil)
    if body?["result"] == nil {
      throw ConnectError.badResponse("MCP initialize failed")
    }
    _ = try? await mcpRequest(
      payload: ["jsonrpc": "2.0", "method": "notifications/initialized", "params": [:]],
      token: token, session: session)
    return session
  }

  private func toolsCall(
    name: String, arguments: [String: Any], token: String, session: String?
  ) async throws -> [String: Any] {
    let (body, _) = try await mcpRequest(
      payload: [
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": ["name": name, "arguments": arguments],
      ], token: token, session: session)
    guard let body else { throw ConnectError.badResponse("empty MCP response") }
    if let error = body["error"] as? [String: Any] {
      throw ConnectError.badResponse((error["message"] as? String) ?? "MCP error")
    }
    return body
  }

  private func mcpRequest(
    payload: [String: Any], token: String, session: String?
  ) async throws -> ([String: Any]?, String?) {
    var request = URLRequest(url: Self.base.appendingPathComponent("mcp"))
    request.httpMethod = "POST"
    request.httpBody = try JSONSerialization.data(withJSONObject: payload)
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("application/json, text/event-stream", forHTTPHeaderField: "Accept")
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.setValue(Self.userAgent, forHTTPHeaderField: "User-Agent")
    if let session {
      request.setValue(session, forHTTPHeaderField: "Mcp-Session-Id")
    }
    let (data, response) = try await URLSession.shared.data(for: request)
    let http = response as? HTTPURLResponse
    let newSession = http?.value(forHTTPHeaderField: "Mcp-Session-Id") ?? session
    let text = String(decoding: data, as: UTF8.self)
    let jsonText: String
    if (http?.value(forHTTPHeaderField: "Content-Type") ?? "").contains("text/event-stream") {
      guard let last = Self.lastSSEDataLine(text) else { return (nil, newSession) }
      jsonText = last
    } else {
      jsonText = text
    }
    guard !jsonText.isEmpty,
      let object = try? JSONSerialization.jsonObject(with: Data(jsonText.utf8)) as? [String: Any]
    else { return (nil, newSession) }
    return (object, newSession)
  }

  // MARK: - Pure helpers (unit-tested)

  /// The MCP endpoint frames JSON-RPC responses as SSE; the response is the
  /// last `data:` line of the stream.
  static func lastSSEDataLine(_ body: String) -> String? {
    var last: String?
    for line in body.split(separator: "\n", omittingEmptySubsequences: true)
    where line.hasPrefix("data:") {
      last = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
    }
    return (last?.isEmpty == false) ? last : nil
  }

  /// notion-create-pages returns its payload as JSON text inside content[0].text.
  static func pageRecord(fromToolResult body: [String: Any]) -> (id: String, url: String)? {
    guard
      let result = body["result"] as? [String: Any],
      let content = result["content"] as? [[String: Any]],
      let text = content.first?["text"] as? String,
      let parsed = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any],
      let page = (parsed["pages"] as? [[String: Any]])?.first,
      let id = page["id"] as? String,
      let url = page["url"] as? String
    else { return nil }
    return (id, url)
  }

  static func toolCallFailed(_ body: [String: Any]) -> Bool {
    guard let result = body["result"] as? [String: Any] else { return true }
    return (result["isError"] as? Bool) == true
  }

  // MARK: - HTTP + crypto helpers

  private func postJSON(url: URL, body: [String: Any]) async throws -> [String: Any] {
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.httpBody = try JSONSerialization.data(withJSONObject: body)
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue(Self.userAgent, forHTTPHeaderField: "User-Agent")
    let (data, _) = try await URLSession.shared.data(for: request)
    guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      throw ConnectError.badResponse("unexpected response from Notion")
    }
    return object
  }

  private func postForm(url: URL, fields: [String: String]) async throws -> [String: Any] {
    var components = URLComponents()
    components.queryItems = fields.map { URLQueryItem(name: $0.key, value: $0.value) }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.httpBody = (components.percentEncodedQuery ?? "").data(using: .utf8)
    request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
    request.setValue(Self.userAgent, forHTTPHeaderField: "User-Agent")
    let (data, _) = try await URLSession.shared.data(for: request)
    guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      throw ConnectError.badResponse("token endpoint returned an unexpected response")
    }
    return object
  }

  private static func randomURLSafe(_ bytes: Int) -> String {
    var buffer = [UInt8](repeating: 0, count: bytes)
    _ = SecRandomCopyBytes(kSecRandomDefault, bytes, &buffer)
    return Data(buffer).base64URLEncoded()
  }

  private static func codeChallenge(for verifier: String) -> String {
    Data(SHA256.hash(data: Data(verifier.utf8))).base64URLEncoded()
  }
}

extension Data {
  fileprivate func base64URLEncoded() -> String {
    base64EncodedString()
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
  }
}

/// One-shot loopback HTTP listener for the OAuth redirect. Binds a random high
/// port on 127.0.0.1, serves a single GET, hands back its query parameters.
private final class OAuthCallbackListener: @unchecked Sendable {
  let port: UInt16
  private let listener: NWListener
  private let lock = NSLock()
  private var continuation: CheckedContinuation<[String: String], Error>?

  init() throws {
    var created: (NWListener, UInt16)?
    for _ in 0..<4 {
      let candidate = UInt16.random(in: 45_000...59_000)
      if let endpointPort = NWEndpoint.Port(rawValue: candidate),
        let attempt = try? NWListener(using: .tcp, on: endpointPort)
      {
        created = (attempt, candidate)
        break
      }
    }
    guard let (listener, port) = created else {
      throw NotionMCPConnector.ConnectError.badResponse("no free local port for the OAuth redirect")
    }
    self.listener = listener
    self.port = port
    listener.newConnectionHandler = { [weak self] connection in
      self?.handle(connection)
    }
    listener.start(queue: DispatchQueue(label: "notion-oauth-callback"))
  }

  func cancel() {
    listener.cancel()
  }

  func waitForCallback(timeout: TimeInterval) async throws -> [String: String] {
    try await withCheckedThrowingContinuation { continuation in
      lock.lock()
      self.continuation = continuation
      lock.unlock()
      DispatchQueue.global().asyncAfter(deadline: .now() + timeout) { [weak self] in
        self?.finish(with: .failure(NotionMCPConnector.ConnectError.timedOut))
      }
    }
  }

  private func finish(with result: Result<[String: String], Error>) {
    lock.lock()
    let continuation = self.continuation
    self.continuation = nil
    lock.unlock()
    switch result {
    case .success(let params): continuation?.resume(returning: params)
    case .failure(let error): continuation?.resume(throwing: error)
    }
  }

  private func handle(_ connection: NWConnection) {
    connection.start(queue: DispatchQueue(label: "notion-oauth-conn"))
    connection.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, _, _ in
      guard let self, let data, let request = String(data: data, encoding: .utf8) else {
        connection.cancel()
        return
      }
      let params = Self.queryParams(fromRequestLine: request)
      let html = "<html><body><h2>Omi is connected to Notion. Close this tab.</h2></body></html>"
      let response =
        "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: \(html.utf8.count)\r\nConnection: close\r\n\r\n\(html)"
      connection.send(
        content: Data(response.utf8),
        completion: .contentProcessed { _ in connection.cancel() })
      if !params.isEmpty {
        self.finish(with: .success(params))
      }
    }
  }

  static func queryParams(fromRequestLine request: String) -> [String: String] {
    guard let firstLine = request.split(separator: "\r\n").first,
      firstLine.hasPrefix("GET "),
      let path = firstLine.split(separator: " ").dropFirst().first,
      let components = URLComponents(string: String(path))
    else { return [:] }
    var params: [String: String] = [:]
    for item in components.queryItems ?? [] {
      params[item.name] = item.value
    }
    return params
  }
}
