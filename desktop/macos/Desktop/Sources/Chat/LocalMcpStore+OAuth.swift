import AppKit
import CryptoKit
import Foundation
import Network
import Security

/// Fully local OAuth for remote MCP servers: metadata discovery, dynamic client
/// registration, PKCE, a loopback redirect listener, code exchange, and refresh.
/// Tokens live inside the server's entry in ~/.omi/mcp.json under "auth" —
/// the same trust model as other local MCP clients.
extension LocalMcpStore {

  enum RemoteAddResult {
    case added
    case oauthCompleted
  }

  /// Add a remote server. Uses the API key when given; otherwise runs the OAuth
  /// flow when the server advertises one; otherwise stores a plain URL.
  static func addRemoteServer(name: String, url: String, apiKey: String?) async throws -> RemoteAddResult {
    let slug = LocalSkillsStore.slugify(name)
    guard !slug.isEmpty else {
      throw storeError("Server name must contain letters or numbers")
    }
    guard let serverURL = URL(string: url), let scheme = serverURL.scheme,
      ["http", "https"].contains(scheme), serverURL.host != nil
    else {
      throw storeError("Enter the server's http(s) URL")
    }

    if let apiKey, !apiKey.isEmpty {
      try upsertServer(slug, entry: ["url": url, "token": apiKey])
      return .added
    }

    guard let meta = await discoverOAuthMetadata(serverURL: serverURL) else {
      try upsertServer(slug, entry: ["url": url])
      return .added
    }

    let auth = try await runOAuthFlow(meta: meta)
    try upsertServer(slug, entry: ["url": url, "auth": auth])
    return .oauthCompleted
  }

  /// Authorize a server that is already configured.
  ///
  /// `addRemoteServer` only runs the flow while adding, so a server that arrived any other way —
  /// installed from the marketplace, hand-written into mcp.json, or one whose refresh token has
  /// since been revoked — could report "Needs sign-in" with nothing anywhere to act on it.
  static func signIn(name: String) async throws {
    guard var entry = readAllServers()[name] as? [String: Any] else {
      throw storeError("That server is no longer configured")
    }
    guard let url = entry["url"] as? String, let serverURL = URL(string: url) else {
      throw storeError("Only remote servers sign in; a local command runs as you")
    }
    guard let meta = await discoverOAuthMetadata(serverURL: serverURL) else {
      throw storeError("This server does not advertise OAuth. If it needs an API key, set one here instead.")
    }
    entry["auth"] = try await runOAuthFlow(meta: meta)
    // A key and a token are alternative credentials; leaving a stale key behind would keep being
    // sent as the Authorization header and mask the token we just obtained.
    entry.removeValue(forKey: "token")
    try upsertServer(name, entry: entry)
  }

  /// Replace the API key on a configured server, for a key that was mistyped or has been rotated.
  static func setAPIKey(name: String, apiKey: String) throws {
    guard var entry = readAllServers()[name] as? [String: Any] else {
      throw storeError("That server is no longer configured")
    }
    guard entry["url"] is String else {
      throw storeError("Only remote servers take an API key")
    }
    let trimmed = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty {
      entry.removeValue(forKey: "token")
    } else {
      entry["token"] = trimmed
      entry.removeValue(forKey: "auth")
    }
    try upsertServer(name, entry: entry)
  }

  /// Refresh OAuth tokens that are expired or expire within 5 minutes.
  /// Call at agent-runtime start and periodically while the app runs.
  static func refreshExpiredTokens() async {
    for (name, raw) in readAllServers() {
      guard var entry = raw as? [String: Any],
        var auth = entry["auth"] as? [String: Any],
        let refreshToken = auth["refresh_token"] as? String,
        let tokenEndpoint = auth["token_endpoint"] as? String,
        let clientId = auth["client_id"] as? String
      else { continue }
      let expiresAt = auth["expires_at"] as? Double ?? 0
      guard expiresAt > 0, expiresAt < Date().timeIntervalSince1970 + 300 else { continue }
      do {
        var form = [
          "grant_type": "refresh_token",
          "refresh_token": refreshToken,
          "client_id": clientId,
        ]
        if let secret = auth["client_secret"] as? String { form["client_secret"] = secret }
        let tokens = try await postForm(endpoint: tokenEndpoint, form: form)
        auth["access_token"] = tokens["access_token"]
        if let newRefresh = tokens["refresh_token"] as? String { auth["refresh_token"] = newRefresh }
        if let expiresIn = tokens["expires_in"] as? Double {
          auth["expires_at"] = Date().timeIntervalSince1970 + expiresIn
        }
        entry["auth"] = auth
        try upsertServer(name, entry: entry)
      } catch {
        log("LocalMcpOAuth: token refresh failed for \(name): \(error)")
      }
    }
  }

  // MARK: - Flow pieces

  private struct OAuthMeta {
    let authorizationEndpoint: String
    let tokenEndpoint: String
    let registrationEndpoint: String?
    let scopes: [String]?
    /// The canonical resource identifier this token is for (RFC 8707). An authorization server
    /// fronting several resources issues an audience-scoped token, so omitting it gets a token the
    /// MCP server then rejects.
    let resource: String
  }

  /// Where a server's authorization server actually lives.
  ///
  /// Probing only the resource's own `/.well-known/oauth-authorization-server` assumes the resource
  /// *is* its own authorization server. The current spec does not: a server answers 401 with
  /// `resource_metadata` (RFC 9728), and that document names the authorization servers — which are
  /// routinely on a different host. Hosted providers work exactly this way, so resource-only
  /// discovery failed every one of them.
  private static func discoverOAuthMetadata(serverURL: URL) async -> OAuthMeta? {
    let discovered = await protectedResource(for: serverURL)
    let resource = discovered.resource ?? origin(of: serverURL)?.absoluteString ?? serverURL.absoluteString
    for issuer in discovered.issuers {
      if let meta = await authorizationServerMetadata(issuer: issuer, resource: resource) {
        return meta
      }
    }
    return nil
  }

  /// Issuers to try, best-documented first, ending with the resource itself for older servers that
  /// publish their own authorization metadata and no protected-resource document.
  private static func protectedResource(for serverURL: URL) async -> (issuers: [URL], resource: String?) {
    var issuers: [URL] = []
    var resource: String?
    if let origin = origin(of: serverURL),
      let metadata = await getJSON(origin.appendingPathComponent(".well-known/oauth-protected-resource"))
    {
      issuers += ((metadata["authorization_servers"] as? [String]) ?? []).compactMap(URL.init(string:))
      resource = metadata["resource"] as? String
    }
    if let origin = origin(of: serverURL), !issuers.contains(origin) { issuers.append(origin) }
    return (issuers, resource)
  }

  /// An issuer's OAuth metadata. Both well-known paths are tried: `oauth-authorization-server` is
  /// the OAuth one, `openid-configuration` is what some providers publish instead.
  private static func authorizationServerMetadata(issuer: URL, resource: String) async -> OAuthMeta? {
    for suffix in ["oauth-authorization-server", "openid-configuration"] {
      // RFC 8414 inserts the well-known segment before an issuer's path rather than after it.
      let candidates = [
        issuerWellKnown(issuer: issuer, suffix: suffix),
        issuer.appendingPathComponent(".well-known/\(suffix)"),
      ]
      for url in candidates.compactMap({ $0 }) {
        guard let json = await getJSON(url),
          let authorize = json["authorization_endpoint"] as? String,
          let token = json["token_endpoint"] as? String
        else { continue }
        return OAuthMeta(
          authorizationEndpoint: authorize,
          tokenEndpoint: token,
          registrationEndpoint: json["registration_endpoint"] as? String,
          scopes: json["scopes_supported"] as? [String],
          resource: resource)
      }
    }
    return nil
  }

  static func issuerWellKnown(issuer: URL, suffix: String) -> URL? {
    guard var components = URLComponents(url: issuer, resolvingAgainstBaseURL: false) else {
      return nil
    }
    let path = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    components.path = path.isEmpty ? "/.well-known/\(suffix)" : "/.well-known/\(suffix)/\(path)"
    return components.url
  }

  static func origin(of url: URL) -> URL? {
    guard let scheme = url.scheme, let host = url.host else { return nil }
    let port = url.port.map { ":\($0)" } ?? ""
    return URL(string: "\(scheme)://\(host)\(port)")
  }

  private static func getJSON(_ url: URL) async -> [String: Any]? {
    var request = URLRequest(url: url)
    request.timeoutInterval = 10
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    guard let (data, response) = try? await URLSession.shared.data(for: request),
      (response as? HTTPURLResponse)?.statusCode == 200
    else { return nil }
    return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
  }

  private static func runOAuthFlow(meta: OAuthMeta) async throws -> [String: Any] {
    guard let registration = meta.registrationEndpoint else {
      throw storeError("This server requires OAuth but does not support automatic client registration")
    }

    let listener = try await LoopbackCallbackListener.start()
    let redirectURI = "http://127.0.0.1:\(listener.port)/callback"
    defer { listener.stop() }

    // Dynamic client registration (public client, PKCE only)
    let registered = try await postJSON(
      endpoint: registration,
      body: [
        "client_name": "Omi",
        "redirect_uris": [redirectURI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
      ])
    guard let clientId = registered["client_id"] as? String else {
      throw storeError("The server's OAuth registration did not return a client id")
    }
    let clientSecret = registered["client_secret"] as? String

    // PKCE + authorization request
    // RFC 7636 §4.1's recommended construction: 32 random octets, base64url-encoded.
    let verifier = try randomURLSafeToken(byteCount: 32)
    let challenge = Data(SHA256.hash(data: Data(verifier.utf8))).base64URLEncoded()
    let state = try randomURLSafeToken(byteCount: 16)
    guard var components = URLComponents(string: meta.authorizationEndpoint) else {
      throw storeError("The server advertised an invalid authorization endpoint")
    }
    var query = [
      URLQueryItem(name: "response_type", value: "code"),
      URLQueryItem(name: "client_id", value: clientId),
      URLQueryItem(name: "redirect_uri", value: redirectURI),
      URLQueryItem(name: "state", value: state),
      URLQueryItem(name: "code_challenge", value: challenge),
      URLQueryItem(name: "code_challenge_method", value: "S256"),
      URLQueryItem(name: "resource", value: meta.resource),
    ]
    if let scopes = meta.scopes, !scopes.isEmpty {
      query.append(URLQueryItem(name: "scope", value: scopes.joined(separator: " ")))
    }
    components.queryItems = (components.queryItems ?? []) + query
    guard let authURL = components.url else { throw storeError("Invalid authorization URL") }
    _ = await MainActor.run { NSWorkspace.shared.open(authURL) }

    let callback = try await listener.waitForCode(timeoutSeconds: 240)
    guard callback.state == state else { throw storeError("OAuth state mismatch; try again") }

    var form = [
      "grant_type": "authorization_code",
      "code": callback.code,
      "redirect_uri": redirectURI,
      "client_id": clientId,
      "code_verifier": verifier,
      "resource": meta.resource,
    ]
    if let clientSecret { form["client_secret"] = clientSecret }
    let tokens = try await postForm(endpoint: meta.tokenEndpoint, form: form)
    guard let accessToken = tokens["access_token"] as? String else {
      throw storeError("The server did not return an access token")
    }

    var auth: [String: Any] = [
      "access_token": accessToken,
      "token_endpoint": meta.tokenEndpoint,
      "client_id": clientId,
    ]
    if let refresh = tokens["refresh_token"] as? String { auth["refresh_token"] = refresh }
    if let expiresIn = tokens["expires_in"] as? Double {
      auth["expires_at"] = Date().timeIntervalSince1970 + expiresIn
    }
    if let clientSecret { auth["client_secret"] = clientSecret }
    return auth
  }

  // MARK: - HTTP helpers

  private static func postJSON(endpoint: String, body: [String: Any]) async throws -> [String: Any] {
    guard let url = URL(string: endpoint) else { throw storeError("Invalid endpoint: \(endpoint)") }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = try JSONSerialization.data(withJSONObject: body)
    let (data, response) = try await URLSession.shared.data(for: request)
    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
    guard (200..<300).contains(status),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { throw storeError("Request to \(url.host ?? endpoint) failed (HTTP \(status))") }
    return json
  }

  private static func postForm(endpoint: String, form: [String: String]) async throws -> [String: Any] {
    guard let url = URL(string: endpoint) else { throw storeError("Invalid endpoint: \(endpoint)") }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
    request.httpBody = form.map { key, value in
      let encoded = value.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? value
      return "\(key)=\(encoded)"
    }.joined(separator: "&").data(using: .utf8)
    let (data, response) = try await URLSession.shared.data(for: request)
    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
    guard (200..<300).contains(status),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { throw storeError("Token request failed (HTTP \(status))") }
    return json
  }

  /// A PKCE verifier or an OAuth `state`, from the system CSPRNG.
  ///
  /// `Int.random` draws from a generator that carries no cryptographic guarantee, and these two
  /// values are exactly what an attacker must not predict: the verifier is the proof that the
  /// party redeeming the code is the one that started the flow, and `state` is the CSRF binding.
  /// A failure to draw randomness throws rather than falling back to a weaker source — an OAuth
  /// flow the user can retry is strictly better than one built on guessable secrets.
  ///
  /// Base64url of raw bytes rather than picking characters out of an alphabet: index-by-modulo
  /// over 66 characters is biased for any byte-sized draw, and this is the construction RFC 7636
  /// recommends anyway.
  static func randomURLSafeToken(byteCount: Int) throws -> String {
    var bytes = [UInt8](repeating: 0, count: byteCount)
    guard SecRandomCopyBytes(kSecRandomDefault, byteCount, &bytes) == errSecSuccess else {
      throw storeError("Could not generate secure random data for the sign-in request")
    }
    return Data(bytes).base64URLEncoded()
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

/// One-shot loopback HTTP listener for the OAuth redirect (RFC 8252 native-app flow).
/// One-shot loopback HTTP listener for the OAuth redirect.
///
/// A plain BSD socket rather than `NWListener`: every `NWListener` configuration — `.tcp` on
/// `.any`, bare `NWParameters.tcp`, and an explicit loopback `requiredLocalEndpoint` — fails with
/// EINVAL here, which surfaced as sign-in being impossible. A socket bound to 127.0.0.1:0 is also
/// the tighter grant: the redirect only ever arrives from this machine.
final class LoopbackCallbackListener: @unchecked Sendable {
  struct Callback {
    let code: String
    let state: String
  }

  let port: UInt16
  private let descriptor: Int32
  private let lock = NSLock()
  private var continuation: CheckedContinuation<Callback, Error>?
  private var stopped = false

  init() throws {
    // Bound through a local before any member is assigned: the closures below would otherwise
    // capture a partially initialized self.
    let fd = socket(AF_INET, SOCK_STREAM, 0)
    guard fd >= 0 else {
      throw LocalMcpStore.storeError("Could not open a local socket for the OAuth redirect")
    }
    var reuse: Int32 = 1
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse, socklen_t(MemoryLayout<Int32>.size))

    var address = sockaddr_in()
    address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
    address.sin_family = sa_family_t(AF_INET)
    address.sin_port = 0  // the kernel picks a free ephemeral port
    address.sin_addr.s_addr = inet_addr("127.0.0.1")

    let bound = withUnsafePointer(to: &address) {
      $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
        bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
      }
    }
    guard bound == 0, listen(fd, 1) == 0 else {
      close(fd)
      throw LocalMcpStore.storeError("Could not open a local port for the OAuth redirect")
    }

    var assigned = sockaddr_in()
    var length = socklen_t(MemoryLayout<sockaddr_in>.size)
    withUnsafeMutablePointer(to: &assigned) {
      _ = $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(fd, $0, &length) }
    }
    let assignedPort = UInt16(bigEndian: assigned.sin_port)
    guard assignedPort != 0 else {
      close(fd)
      throw LocalMcpStore.storeError("Could not open a local port for the OAuth redirect")
    }

    descriptor = fd
    port = assignedPort
  }

  /// Kept async for call-site symmetry with the previous listener, and so a future implementation
  /// can bind off the calling thread without changing callers.
  static func start() async throws -> LoopbackCallbackListener {
    try LoopbackCallbackListener()
  }

  func waitForCode(timeoutSeconds: Int) async throws -> Callback {
    DispatchQueue.global(qos: .userInitiated).async { [weak self] in self?.acceptOnce() }
    let timeoutTask = Task { [weak self] in
      try? await Task.sleep(nanoseconds: UInt64(timeoutSeconds) * 1_000_000_000)
      guard !Task.isCancelled else { return }
      self?.finish(.failure(LocalMcpStore.storeError("Timed out waiting for the browser to return")))
    }
    defer { timeoutTask.cancel() }
    return try await withCheckedThrowingContinuation { continuation in
      lock.lock()
      if stopped {
        lock.unlock()
        continuation.resume(throwing: CancellationError())
        return
      }
      self.continuation = continuation
      lock.unlock()
    }
  }

  func stop() {
    lock.lock()
    let alreadyStopped = stopped
    stopped = true
    lock.unlock()
    guard !alreadyStopped else { return }
    close(descriptor)
  }

  private func acceptOnce() {
    var remote = sockaddr()
    var length = socklen_t(MemoryLayout<sockaddr>.size)
    let connection = accept(descriptor, &remote, &length)
    guard connection >= 0 else {
      // A closed descriptor is `stop()` doing its job, not a failure to report.
      lock.lock()
      let wasStopped = stopped
      lock.unlock()
      if !wasStopped {
        finish(.failure(LocalMcpStore.storeError("The OAuth redirect connection failed")))
      }
      return
    }
    defer { close(connection) }

    var request = Data()
    var buffer = [UInt8](repeating: 0, count: 2048)
    // The request line is all we need, and it arrives in the first segment.
    while request.count < 8192 {
      let read = recv(connection, &buffer, buffer.count, 0)
      guard read > 0 else { break }
      request.append(contentsOf: buffer[0..<read])
      if request.range(of: Data("\r\n\r\n".utf8)) != nil { break }
      if request.range(of: Data("\n".utf8)) != nil, request.count > 16 { break }
    }

    let body =
      "You can close this window and return to Omi."
    let response = """
      HTTP/1.1 200 OK\r
      Content-Type: text/plain; charset=utf-8\r
      Content-Length: \(body.utf8.count)\r
      Connection: close\r
      \r
      \(body)
      """
    _ = response.withCString { send(connection, $0, strlen($0), 0) }

    guard let text = String(data: request, encoding: .utf8),
      let target = text.split(separator: " ").dropFirst().first,
      let components = URLComponents(string: "http://127.0.0.1\(target)")
    else {
      finish(.failure(LocalMcpStore.storeError("The OAuth redirect was malformed")))
      return
    }
    let items = components.queryItems ?? []
    if let error = items.first(where: { $0.name == "error" })?.value {
      finish(.failure(LocalMcpStore.storeError("The server refused authorization: \(error)")))
      return
    }
    guard let code = items.first(where: { $0.name == "code" })?.value,
      let state = items.first(where: { $0.name == "state" })?.value
    else {
      finish(.failure(LocalMcpStore.storeError("The OAuth redirect carried no authorization code")))
      return
    }
    finish(.success(Callback(code: code, state: state)))
  }

  private func finish(_ result: Result<Callback, Error>) {
    lock.lock()
    let continuation = self.continuation
    self.continuation = nil
    lock.unlock()
    switch result {
    case .success(let value): continuation?.resume(returning: value)
    case .failure(let error): continuation?.resume(throwing: error)
    }
  }
}
