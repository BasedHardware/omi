import AppKit
import CryptoKit
import Foundation
import Network

enum GoogleOAuthError: LocalizedError {
  case noClientId
  case browserLaunchFailed
  case stateMismatch
  case noCode
  case redirectMissing
  case timedOut
  case exchangeFailed(String)
  case invalidGrant
  case revocationFailed(String)
  case network(String)
  case reconnectRequired

  var errorDescription: String? {
    switch self {
    case .noClientId:
      return "Add a Google OAuth client ID before connecting."
    case .browserLaunchFailed:
      return "Could not open the browser for Google sign-in."
    case .stateMismatch:
      return "Google's redirect did not match this sign-in attempt."
    case .noCode:
      return "Google did not return an authorization code."
    case .redirectMissing:
      return "The sign-in window never returned to Omi."
    case .timedOut:
      return "Google sign-in timed out. Try again."
    case .exchangeFailed(let detail):
      return "Google rejected the sign-in: \(detail)"
    case .invalidGrant:
      return "Google ended this connection. Reconnect to continue."
    case .revocationFailed(let detail):
      return "Google did not confirm sign-out: \(detail)"
    case .network(let detail):
      return "Network error: \(detail)"
    case .reconnectRequired:
      return "This connection needs to be reconnected."
    }
  }
}

struct PkcePair: Equatable {
  let verifier: String
  let challenge: String

  static func generate() -> PkcePair {
    var bytes = [UInt8](repeating: 0, count: 48)
    _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
    let verifier = Data(bytes).base64URLUnpadded
    return PkcePair(verifier: verifier, challenge: challenge(from: verifier))
  }

  static func challenge(from verifier: String) -> String {
    Data(SHA256.hash(data: Data(verifier.utf8))).base64URLUnpadded
  }
}

extension Data {
  var base64URLUnpadded: String {
    base64EncodedString()
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
  }
}

/// One-shot HTTP server on 127.0.0.1:0 that captures the OAuth redirect and
/// answers it so the browser stops loading. Torn down after the first request.
final class LoopbackRedirectServer: @unchecked Sendable {
  private let listener: NWListener
  private let queue = DispatchQueue(label: "com.omi.oauth.loopback")
  private var pending: CheckedContinuation<URL, Error>?
  private var settled = false

  init() throws {
    let parameters = NWParameters.tcp
    parameters.allowLocalEndpointReuse = true
    parameters.requiredLocalEndpoint = NWEndpoint.hostPort(
      host: "127.0.0.1", port: 0)
    listener = try NWListener(using: parameters)
  }

  var uri: URL {
    // swiftlint:disable:next force_unwrapping — fixed localhost literal cannot fail
    URL(string: "http://127.0.0.1:\(listener.port?.rawValue ?? 0)/oauth/callback")!
  }

  func start() {
    listener.newConnectionHandler = { [weak self] connection in
      self?.handle(connection)
    }
    listener.start(queue: queue)
  }

  func stop() {
    queue.async { [weak self] in
      self?.settle(with: .failure(GoogleOAuthError.redirectMissing))
      self?.listener.cancel()
    }
  }

  func waitForRedirect() async throws -> URL {
    try await withCheckedThrowingContinuation { continuation in
      queue.async { [weak self] in
        guard let self, !self.settled else {
          continuation.resume(throwing: GoogleOAuthError.redirectMissing)
          return
        }
        self.pending = continuation
      }
    }
  }

  private func settle(with result: Result<URL, Error>) {
    guard !settled else { return }
    settled = true
    listener.cancel()
    let waiter = pending
    pending = nil
    waiter?.resume(with: result)
  }

  private func handle(_ connection: NWConnection) {
    connection.start(queue: queue)
    var buffer = Data()
    func receiveLoop(
      data: Data?,
      context: NWConnection.ContentContext?,
      isComplete: Bool,
      error: NWError?
    ) {
      if let data {
        buffer.append(data)
      }
      if error != nil || isComplete || buffer.range(of: Data("\r\n\r\n".utf8)) != nil {
        respond(connection: connection, buffer: &buffer)
        return
      }
      connection.receive(
        minimumIncompleteLength: 1, maximumLength: 8192, completion: receiveLoop)
    }
    connection.receive(
      minimumIncompleteLength: 1, maximumLength: 8192, completion: receiveLoop)
  }

  private func respond(connection: NWConnection, buffer: inout Data) {
    defer { connection.cancel() }
    let head = String(
      decoding: buffer.prefix(4096), as: UTF8.self)
    let url = Self.redirectURL(fromRequestHead: head)
    let body =
      "<!doctype html><html><body style=\"font-family:system-ui;padding:2rem\">"
      + "You can close this window and return to Omi.</body></html>"
    let response =
      "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
      + "Content-Length: \(body.utf8.count)\r\nConnection: close\r\n\r\n\(body)"
    connection.send(
      content: Data(response.utf8), completion: .contentProcessed { _ in })
    if let url {
      settle(with: .success(url))
    }
  }

  static func redirectURL(fromRequestHead head: String) -> URL? {
    guard let firstLine = head.split(separator: "\r\n").first else {
      return nil
    }
    let parts = firstLine.split(separator: " ")
    guard parts.count >= 2, parts[0] == "GET", let path = parts[1].split(separator: "?").first
    else {
      return nil
    }
    let query =
      parts[1].contains("?")
      ? String(parts[1].split(separator: "?", maxSplits: 1)[1]) : ""
    var components = URLComponents()
    components.scheme = "http"
    components.host = "127.0.0.1"
    components.path = String(path)
    components.query = query
    return components.url
  }
}

/// PKCE authorization-code exchange, refresh, revocation, and account naming.
/// Everything provider specific lives in [GoogleOAuth]; the session is injected
/// so tests can stub the network.
final class GoogleOAuthTokenClient {
  let session: URLSession

  init(session: URLSession = .shared) {
    self.session = session
  }

  func exchangeCode(
    code: String,
    verifier: String,
    redirectUri: String,
    clientId: String
  ) async throws -> GoogleOAuthConnection {
    var form = [
      "grant_type": "authorization_code",
      "code": code,
      "redirect_uri": redirectUri,
      "client_id": clientId,
      "code_verifier": verifier,
    ]
    if let secret = GoogleOAuth.clientSecret {
      form["client_secret"] = secret
    }
    let json = try await postForm(GoogleOAuth.tokenEndpoint, form)
    let accessToken = json["access_token"] as? String
    guard let accessToken, !accessToken.isEmpty else {
      throw GoogleOAuthError.exchangeFailed(Self.detail(json))
    }
    let expiresIn = (json["expires_in"] as? NSNumber)?.doubleValue ?? 3600
    let refreshToken = json["refresh_token"] as? String
    let scopes =
      (json["scope"] as? String)?
      .split(separator: " ").map(String.init) ?? GoogleOAuth.scopes
    let account = await fetchAccount(accessToken: accessToken)
    return GoogleOAuthConnection(
      accessToken: accessToken,
      expiresAt: Date().addingTimeInterval(expiresIn),
      grantedScopes: scopes,
      refreshToken: (refreshToken?.isEmpty ?? true) ? nil : refreshToken,
      account: account
    )
  }

  func refresh(
    _ connection: GoogleOAuthConnection,
    clientId: String
  ) async throws -> GoogleOAuthConnection {
    guard let refreshToken = connection.refreshToken else {
      throw GoogleOAuthError.invalidGrant
    }
    var form = [
      "grant_type": "refresh_token",
      "refresh_token": refreshToken,
      "client_id": clientId,
    ]
    if let secret = GoogleOAuth.clientSecret {
      form["client_secret"] = secret
    }
    let json = try await postForm(GoogleOAuth.tokenEndpoint, form)
    let accessToken = json["access_token"] as? String
    guard let accessToken, !accessToken.isEmpty else {
      throw GoogleOAuthError.invalidGrant
    }
    let expiresIn = (json["expires_in"] as? NSNumber)?.doubleValue ?? 3600
    let rotated = json["refresh_token"] as? String
    return GoogleOAuthConnection(
      accessToken: accessToken,
      expiresAt: Date().addingTimeInterval(expiresIn),
      grantedScopes: connection.grantedScopes,
      refreshToken: (rotated?.isEmpty ?? true) ? refreshToken : rotated,
      account: connection.account
    )
  }

  func revoke(_ connection: GoogleOAuthConnection) async throws {
    let token = connection.refreshToken ?? connection.accessToken
    let body = "token=\(Self.formEncode(token))"
    var request = URLRequest(url: GoogleOAuth.revocationEndpoint)
    request.httpMethod = "POST"
    request.httpBody = Data(body.utf8)
    request.setValue(
      "application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
    do {
      let (_, response) = try await session.data(for: request)
      let status = (response as? HTTPURLResponse)?.statusCode ?? 0
      if status >= 200 && status < 300 || status == 400 { return }
      throw GoogleOAuthError.revocationFailed("HTTP \(status)")
    } catch let error as GoogleOAuthError {
      throw error
    } catch {
      throw GoogleOAuthError.network(error.localizedDescription)
    }
  }

  func fetchAccount(accessToken: String) async -> String? {
    var request = URLRequest(url: GoogleOAuth.userInfoEndpoint)
    request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    do {
      let (data, response) = try await session.data(for: request)
      guard (response as? HTTPURLResponse)?.statusCode == 200 else { return nil }
      let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
      let email = json?["email"] as? String
      return (email?.isEmpty ?? true) ? nil : email
    } catch {
      return nil
    }
  }

  private func postForm(
    _ url: URL, _ form: [String: String]
  ) async throws -> [String: Any] {
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue(
      "application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
    request.httpBody = Data(
      form.map { "\(Self.formEncode($0.key))=\(Self.formEncode($0.value))" }
        .joined(separator: "&").utf8)
    do {
      let (data, response) = try await session.data(for: request)
      let status = (response as? HTTPURLResponse)?.statusCode ?? 0
      let json =
        (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
      if status == 400 || status == 401 {
        if let error = json["error"] as? String, error == "invalid_grant" {
          throw GoogleOAuthError.invalidGrant
        }
        throw GoogleOAuthError.exchangeFailed(Self.detail(json))
      }
      guard status >= 200 && status < 300 else {
        throw GoogleOAuthError.exchangeFailed("HTTP \(status)")
      }
      return json
    } catch let error as GoogleOAuthError {
      throw error
    } catch {
      throw GoogleOAuthError.network(error.localizedDescription)
    }
  }

  static func detail(_ json: [String: Any]) -> String {
    let error = json["error"] as? String ?? ""
    let description = json["error_description"] as? String ?? ""
    return [error, description].filter { !$0.isEmpty }.joined(separator: ": ")
  }

  static func formEncode(_ value: String) -> String {
    var allowed = CharacterSet.alphanumerics
    allowed.insert(charactersIn: "-._~_")
    return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value
  }
}

/// Drives connect, refresh, and disconnect for the Google connector, keeping
/// one grant per account. Nothing here knows about cookies.
final class GoogleOAuthConnectionManager: @unchecked Sendable {
  static let shared = GoogleOAuthConnectionManager(store: GoogleOAuthStore.shared)

  private let store: GoogleOAuthStoring
  private let tokenClient: GoogleOAuthTokenClient
  private let lock = NSLock()

  init(
    store: GoogleOAuthStoring,
    tokenClient: GoogleOAuthTokenClient = GoogleOAuthTokenClient()
  ) {
    self.store = store
    self.tokenClient = tokenClient
  }

  func connections() -> [GoogleOAuthConnection] {
    lock.lock()
    defer { lock.unlock() }
    return store.readAll()
  }

  func primaryConnection() -> GoogleOAuthConnection? {
    connections().first { !$0.needsReconnect }
  }

  func connection(account: String?) -> GoogleOAuthConnection? {
    connections().first {
      $0.account == account || (account == nil && !$0.needsReconnect)
    }
  }

  func hasGrants() -> Bool {
    !connections().isEmpty
  }

  func connect() async throws -> GoogleOAuthConnection {
    guard let clientId = GoogleOAuth.clientId, !clientId.isEmpty else {
      throw GoogleOAuthError.noClientId
    }
    let pair = PkcePair.generate()
    let state = Self.randomState()
    let server = try LoopbackRedirectServer()
    server.start()
    let redirectUri = server.uri
    let authURL = Self.authorizationURL(
      clientId: clientId, redirectUri: redirectUri, challenge: pair.challenge,
      state: state)
    guard NSWorkspace.shared.open(authURL) else {
      server.stop()
      throw GoogleOAuthError.browserLaunchFailed
    }
    let redirect: URL
    do {
      redirect = try await withTimeout {
        try await server.waitForRedirect()
      }
    } catch {
      server.stop()
      throw error
    }
    server.stop()
    guard let code = Self.code(from: redirect, expectedState: state) else {
      throw GoogleOAuthError.stateMismatch
    }
    let connection = try await tokenClient.exchangeCode(
      code: code,
      verifier: pair.verifier,
      redirectUri: redirectUri.absoluteString,
      clientId: clientId
    )
    upsert(connection)
    return connection
  }

  func accessToken(account: String? = nil) async throws -> String {
    guard var stored = connection(account: account) else {
      throw GoogleOAuthError.reconnectRequired
    }
    if !stored.isExpired { return stored.accessToken }
    guard let clientId = GoogleOAuth.clientId else {
      throw GoogleOAuthError.reconnectRequired
    }
    do {
      let refreshed = try await tokenClient.refresh(stored, clientId: clientId)
      upsert(refreshed)
      return refreshed.accessToken
    } catch GoogleOAuthError.invalidGrant {
      stored.needsReconnect = true
      upsert(stored)
      throw GoogleOAuthError.reconnectRequired
    }
  }

  func disconnect(account: String? = nil) async throws {
    guard let stored = connection(account: account) else { return }
    var failure: Error?
    do {
      try await tokenClient.revoke(stored)
    } catch {
      failure = error
    }
    remove(account: stored.account)
    if let failure { throw failure }
  }

  func upsert(_ connection: GoogleOAuthConnection) {
    lock.lock()
    defer { lock.unlock() }
    var all = store.readAll()
    all.removeAll { $0.account == connection.account }
    all.insert(connection, at: 0)
    store.write(all)
  }

  func remove(account: String?) {
    lock.lock()
    defer { lock.unlock() }
    let all = store.readAll().filter { $0.account != account }
    store.write(all)
  }

  static func authorizationURL(
    clientId: String,
    redirectUri: URL,
    challenge: String,
    state: String
  ) -> URL {
    var components = URLComponents(
      // swiftlint:disable:next force_unwrapping — fixed endpoint constant cannot fail
      url: GoogleOAuth.authorizationEndpoint, resolvingAgainstBaseURL: false)!
    components.queryItems = [
      URLQueryItem(name: "response_type", value: "code"),
      URLQueryItem(name: "client_id", value: clientId),
      URLQueryItem(name: "redirect_uri", value: redirectUri.absoluteString),
      URLQueryItem(name: "scope", value: GoogleOAuth.scopes.joined(separator: " ")),
      URLQueryItem(name: "state", value: state),
      URLQueryItem(name: "code_challenge", value: challenge),
      URLQueryItem(name: "code_challenge_method", value: "S256"),
      URLQueryItem(name: "access_type", value: "offline"),
      URLQueryItem(name: "prompt", value: "consent"),
    ]
    // swiftlint:disable:next force_unwrapping — fixed components cannot fail
    return components.url!
  }

  static func code(from redirect: URL, expectedState: String) -> String? {
    guard
      let components = URLComponents(
        url: redirect, resolvingAgainstBaseURL: false)
    else {
      return nil
    }
    let query = components.queryItems ?? []
    if let error = query.first(where: { $0.name == "error" })?.value {
      log("GoogleOAuth: consent rejected by Google (\(error))")
      return nil
    }
    guard query.first(where: { $0.name == "state" })?.value == expectedState,
      let code = query.first(where: { $0.name == "code" })?.value,
      !code.isEmpty
    else {
      return nil
    }
    return code
  }

  static func randomState() -> String {
    var bytes = [UInt8](repeating: 0, count: 32)
    _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
    return Data(bytes).base64URLUnpadded
  }

  private func withTimeout<T: Sendable>(
    _ operation: @escaping @Sendable () async throws -> T,
    seconds: Double = 300
  ) async throws -> T {
    try await withThrowingTaskGroup(of: T.self) { group in
      group.addTask { try await operation() }
      group.addTask {
        try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
        throw GoogleOAuthError.timedOut
      }
      // swiftlint:disable:next force_unwrapping — the group always has one winner
      let value = try await group.next()!
      group.cancelAll()
      return value
    }
  }
}
