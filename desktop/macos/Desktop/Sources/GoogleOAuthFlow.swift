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
  case randomGenerationFailed
  case keychainWriteFailed
  case accountUnverified
  case missingScopes([String])

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
    case .randomGenerationFailed:
      return "Could not generate secure random bytes for Google sign-in."
    case .keychainWriteFailed:
      return "Google sign-in succeeded but the connection could not be saved securely."
    case .accountUnverified:
      return "Google did not return a verified account email."
    case .missingScopes(let scopes):
      return "Google did not grant the required permissions: \(scopes.joined(separator: ", "))."
    }
  }
}

struct PkcePair: Equatable {
  let verifier: String
  let challenge: String

  static func generate() throws -> PkcePair {
    var bytes = [UInt8](repeating: 0, count: 48)
    guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
      throw GoogleOAuthError.randomGenerationFailed
    }
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
/// answers it so the browser stops loading. Torn down after the redirect
/// callback arrives. The listener reports `.ready` before `start()` returns,
/// so the redirect URI never embeds an unbound port 0.
final class LoopbackRedirectServer: @unchecked Sendable {
  private let listener: NWListener
  private let queue = DispatchQueue(label: "com.omi.oauth.loopback")
  private var pending: CheckedContinuation<URL, Error>?
  private var retainedResult: Result<URL, Error>?
  private var settled = false
  private var readyWaiter: CheckedContinuation<Void, Error>?
  private var boundPort: UInt16 = 0

  init() throws {
    let parameters = NWParameters.tcp
    parameters.allowLocalEndpointReuse = true
    parameters.requiredLocalEndpoint = NWEndpoint.hostPort(
      host: "127.0.0.1", port: 0)
    listener = try NWListener(using: parameters)
  }

  /// Bind the listener and wait for the OS to report `.ready`, then return the
  /// resolved redirect URI. NWListener binds port 0 asynchronously on its own
  /// queue, so reading `listener.port` immediately after `start()` can yield
  /// nil and produce a redirect URI of `http://127.0.0.1:0/oauth/callback`.
  func start() async throws -> URL {
    try await withCheckedThrowingContinuation { continuation in
      queue.async { [weak self] in
        guard let self else { return }
        self.readyWaiter = continuation
        self.listener.newConnectionHandler = { [weak self] connection in
          self?.handle(connection)
        }
        self.listener.stateUpdateHandler = { [weak self] state in
          guard let self else { return }
          switch state {
          case .ready:
            guard let port = self.listener.port?.rawValue, port != 0 else {
              self.readyWaiter?.resume(
                throwing: GoogleOAuthError.network("Google sign-in listener did not bind a port."))
              self.readyWaiter = nil
              self.listener.cancel()
              return
            }
            self.boundPort = port
            self.readyWaiter?.resume()
            self.readyWaiter = nil
          case .failed(let error):
            self.readyWaiter?.resume(throwing: error)
            self.readyWaiter = nil
          default:
            break
          }
        }
        self.listener.start(queue: self.queue)
      }
    }
    return uri
  }

  var uri: URL {
    // swiftlint:disable:next force_unwrapping — fixed localhost literal cannot fail
    URL(string: "http://127.0.0.1:\(boundPort)/oauth/callback")!
  }

  func stop() {
    queue.async { [weak self] in
      self?.settle(with: .failure(GoogleOAuthError.redirectMissing))
      self?.listener.cancel()
    }
  }

  func waitForRedirect() async throws -> URL {
    try await withTaskCancellationHandler {
      try await withCheckedThrowingContinuation { continuation in
        queue.async { [weak self] in
          guard let self else {
            continuation.resume(throwing: GoogleOAuthError.redirectMissing)
            return
          }
          if let retainedResult {
            // A redirect may arrive before this waiter installs; keep it and
            // hand it to whoever asks next instead of discarding it.
            continuation.resume(with: retainedResult)
            self.retainedResult = nil
            return
          }
          self.pending = continuation
        }
      }
    } onCancel: {
      queue.async { [weak self] in
        self?.settle(with: .failure(GoogleOAuthError.redirectMissing))
      }
    }
  }

  private func settle(with result: Result<URL, Error>) {
    guard !settled else { return }
    settled = true
    listener.cancel()
    if let waiter = pending {
      pending = nil
      waiter.resume(with: result)
    } else {
      // No waiter yet — the redirect is a legitimate result, not an error.
      retainedResult = result
    }
  }

  private func handle(_ connection: NWConnection) {
    connection.start(queue: queue)
    let box = ConnectionBox(connection)
    // The completion handler must be @Sendable; the loop is stored on the box
    // so the closure does not recursively capture itself.
    box.receiveLoop = { [weak self, weak box] data, _, isComplete, error in
      guard let self, let box else { return }
      box.buffer.append(data ?? Data())
      if error != nil || isComplete || box.buffer.range(of: Data("\r\n\r\n".utf8)) != nil {
        self.respond(connection: box.connection, buffer: box.buffer)
        return
      }
      box.connection.receive(
        minimumIncompleteLength: 1, maximumLength: 8192, completion: box.receiveLoop)
    }
    connection.receive(
      minimumIncompleteLength: 1, maximumLength: 8192, completion: box.receiveLoop)
  }

  private func respond(connection: NWConnection, buffer: Data) {
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
    // Only the OAuth callback URL may settle the waiter. A non-callback
    // request (e.g. a favicon or a health ping) is answered and ignored so it
    // cannot finish the wait with a stateMismatch that drops the real redirect.
    guard let url else {
      settle(with: .failure(GoogleOAuthError.redirectMissing))
      return
    }
    guard url.path == "/oauth/callback" else { return }
    settle(with: .success(url))
  }

  /// Boxed connection + buffer so the `@Sendable` receive completion can
  /// capture mutable state without strict-concurrency errors. `receiveLoop`
  /// is stored here (not captured) so the loop closure can recurse legally.
  private final class ConnectionBox: @unchecked Sendable {
    let connection: NWConnection
    var buffer = Data()
    var receiveLoop: @Sendable (Data?, NWConnection.ContentContext?, Bool, NWError?) -> Void = {
      _, _, _, _ in
    }
    init(_ connection: NWConnection) {
      self.connection = connection
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
final class GoogleOAuthTokenClient: @unchecked Sendable {
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
      .split(separator: " ").map(String.init) ?? []
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
      guard json?["email_verified"] as? Bool == true else { return nil }
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

actor GoogleOAuthRefreshGate {
  private var tasks: [String: Task<GoogleOAuthConnection, Error>] = [:]

  func run(
    key: String,
    operation: @escaping @Sendable () async throws -> GoogleOAuthConnection
  ) async throws -> GoogleOAuthConnection {
    if let task = tasks[key] {
      return try await task.value
    }
    let task = Task { try await operation() }
    tasks[key] = task
    defer { tasks[key] = nil }
    return try await task.value
  }
}

/// Drives connect, refresh, and disconnect for the Google connector, keeping
/// one grant per account. Nothing here knows about cookies.
final class GoogleOAuthConnectionManager: @unchecked Sendable {
  static let shared = GoogleOAuthConnectionManager(store: GoogleOAuthStore.shared)

  private let store: GoogleOAuthStoring
  private let tokenClient: GoogleOAuthTokenClient
  private let lock = NSLock()
  private let refreshGate = GoogleOAuthRefreshGate()

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

  func activeConnections() -> [GoogleOAuthConnection] {
    connections().filter { !$0.needsReconnect }
  }

  func connection(account: String?) -> GoogleOAuthConnection? {
    if let account {
      return connections().first { $0.account == account && !$0.needsReconnect }
    }
    return connections().first { !$0.needsReconnect }
  }

  func hasGrants() -> Bool {
    !connections().isEmpty
  }

  func connect() async throws -> GoogleOAuthConnection {
    guard let clientId = GoogleOAuth.clientId, !clientId.isEmpty else {
      throw GoogleOAuthError.noClientId
    }
    let pair = try PkcePair.generate()
    let state = try Self.randomState()
    let server = try LoopbackRedirectServer()
    let redirectUri = try await server.start()
    let authURL = Self.authorizationURL(
      clientId: clientId, redirectUri: redirectUri, challenge: pair.challenge,
      state: state)
    guard NSWorkspace.shared.open(authURL) else {
      server.stop()
      throw GoogleOAuthError.browserLaunchFailed
    }
    let redirect: URL
    do {
      redirect = try await withTimeout(
        {
          try await server.waitForRedirect()
        },
        onTimeout: {
          server.stop()
        })
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
    // A grant without a verified account key cannot be deduplicated or
    // surfaced in the account list; reject it instead of silently
    // overwriting a prior nil-account grant.
    guard let account = connection.account, !account.isEmpty else {
      throw GoogleOAuthError.accountUnverified
    }
    let missingScopes = Self.missingRequiredScopes(connection.grantedScopes)
    guard missingScopes.isEmpty else {
      throw GoogleOAuthError.missingScopes(missingScopes.sorted())
    }
    // Probe both required APIs before persisting so a disabled API or a
    // missing resource scope fails the connect, not the next import.
    let token = connection.accessToken
    _ = try await GoogleOAuthGmailReader.readRecentEmails(token: token, maxResults: 1)
    _ = try await GoogleOAuthCalendarReader.readEvents(
      token: token, daysBack: 1, daysForward: 1, maxResults: 1)
    guard upsert(connection) else {
      throw GoogleOAuthError.keychainWriteFailed
    }
    return connection
  }

  func accessToken(account: String? = nil) async throws -> String {
    guard let stored = connection(account: account) else {
      throw GoogleOAuthError.reconnectRequired
    }
    if !stored.isExpired { return stored.accessToken }
    guard let clientId = GoogleOAuth.clientId else {
      throw GoogleOAuthError.reconnectRequired
    }
    do {
      let refreshed = try await refreshGate.run(
        key: stored.account ?? "legacy",
        operation: { [tokenClient] in
          try await tokenClient.refresh(stored, clientId: clientId)
        })
      return try lock.withLock {
        let current = store.readAll().first { Self.sameAccount($0, stored) }
        guard let current else {
          throw GoogleOAuthError.reconnectRequired
        }
        guard Self.sameSnapshot(current, stored) else {
          guard !current.needsReconnect else {
            throw GoogleOAuthError.reconnectRequired
          }
          return current.accessToken
        }
        var all = store.readAll()
        all.removeAll { Self.sameAccount($0, stored) }
        all.insert(refreshed, at: 0)
        guard store.write(all) else {
          throw GoogleOAuthError.keychainWriteFailed
        }
        return refreshed.accessToken
      }
    } catch GoogleOAuthError.invalidGrant {
      _ = markNeedsReconnect(account: stored.account, expected: stored)
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
    guard remove(account: stored.account, expected: stored) else {
      throw GoogleOAuthError.keychainWriteFailed
    }
    if let failure { throw failure }
  }

  /// Returns false when the keychain write fails, so callers can surface the
  /// failure instead of reporting a connection that was never persisted.
  func upsert(_ connection: GoogleOAuthConnection) -> Bool {
    guard let account = connection.account, !account.isEmpty else { return false }
    lock.lock()
    defer { lock.unlock() }
    var all = store.readAll()
    all.removeAll { $0.account == account }
    all.insert(connection, at: 0)
    return store.write(all)
  }

  @discardableResult
  func markNeedsReconnect(account: String?, expected: GoogleOAuthConnection? = nil) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    var all = store.readAll()
    guard
      let index = all.firstIndex(where: { connection in
        guard Self.sameAccount(connection, account: account) else { return false }
        guard let expected else { return true }
        return Self.sameSnapshot(connection, expected)
      })
    else {
      return false
    }
    all[index].needsReconnect = true
    return store.write(all)
  }

  func remove(account: String?, expected: GoogleOAuthConnection? = nil) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    var all = store.readAll()
    guard let index = all.firstIndex(where: { Self.sameAccount($0, account: account) }) else {
      return true
    }
    if let expected, !Self.sameSnapshot(all[index], expected) {
      return true
    }
    all.remove(at: index)
    return store.write(all)
  }

  private static func sameAccount(_ lhs: GoogleOAuthConnection, _ rhs: GoogleOAuthConnection) -> Bool {
    sameAccount(lhs, account: rhs.account)
  }

  private static func sameAccount(_ connection: GoogleOAuthConnection, account: String?) -> Bool {
    connection.account == account
  }

  private static func sameSnapshot(_ lhs: GoogleOAuthConnection, _ rhs: GoogleOAuthConnection) -> Bool {
    lhs.accessToken == rhs.accessToken
      && lhs.expiresAt == rhs.expiresAt
      && lhs.grantedScopes == rhs.grantedScopes
      && lhs.refreshToken == rhs.refreshToken
      && lhs.account == rhs.account
      && lhs.needsReconnect == rhs.needsReconnect
  }

  static func missingRequiredScopes(_ scopes: [String]) -> [String] {
    let granted = Set(scopes)
    return Set([
      "https://www.googleapis.com/auth/gmail.readonly",
      "https://www.googleapis.com/auth/calendar.readonly",
    ]).subtracting(granted).sorted()
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

  static func randomState() throws -> String {
    var bytes = [UInt8](repeating: 0, count: 32)
    guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
      throw GoogleOAuthError.randomGenerationFailed
    }
    return Data(bytes).base64URLUnpadded
  }

  private func withTimeout<T: Sendable>(
    _ operation: @escaping @Sendable () async throws -> T,
    onTimeout: @escaping @Sendable () -> Void,
    seconds: Double = 300
  ) async throws -> T {
    try await withThrowingTaskGroup(of: T.self) { group in
      group.addTask { try await operation() }
      group.addTask {
        try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
        throw GoogleOAuthError.timedOut
      }
      // swiftlint:disable:next force_unwrapping — the group always has one winner
      do {
        guard let value = try await group.next() else {
          throw GoogleOAuthError.timedOut
        }
        group.cancelAll()
        return value
      } catch {
        onTimeout()
        group.cancelAll()
        throw error
      }
    }
  }
}
