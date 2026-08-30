import AppKit
import CryptoKit
import Foundation
import Network

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

    let listener = try LoopbackCallbackListener()
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
    let verifier = randomURLSafeString(length: 64)
    let challenge = Data(SHA256.hash(data: Data(verifier.utf8))).base64URLEncoded()
    let state = randomURLSafeString(length: 24)
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

  private static func randomURLSafeString(length: Int) -> String {
    let alphabet = Array("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
    return String((0..<length).map { _ in alphabet[Int.random(in: 0..<alphabet.count)] })
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
final class LoopbackCallbackListener: @unchecked Sendable {
  struct Callback {
    let code: String
    let state: String
  }

  private let listener: NWListener
  let port: UInt16
  private var continuation: CheckedContinuation<Callback, Error>?
  private let lock = NSLock()

  init() throws {
    listener = try NWListener(using: .tcp, on: .any)
    listener.start(queue: .global())
    // Wait briefly for the ephemeral port to materialize.
    var resolved: UInt16 = 0
    for _ in 0..<100 {
      if let p = listener.port?.rawValue, p != 0 {
        resolved = p
        break
      }
      usleep(20_000)
    }
    guard resolved != 0 else {
      listener.cancel()
      throw NSError(
        domain: "LoopbackCallbackListener", code: 1,
        userInfo: [NSLocalizedDescriptionKey: "Could not open a local port for the OAuth redirect"])
    }
    port = resolved
    listener.newConnectionHandler = { [weak self] connection in
      self?.handle(connection)
    }
  }

  func waitForCode(timeoutSeconds: Int) async throws -> Callback {
    try await withCheckedThrowingContinuation { continuation in
      lock.lock()
      self.continuation = continuation
      lock.unlock()
      DispatchQueue.global().asyncAfter(deadline: .now() + .seconds(timeoutSeconds)) { [weak self] in
        self?.finish(
          .failure(
            NSError(
              domain: "LoopbackCallbackListener", code: 2,
              userInfo: [NSLocalizedDescriptionKey: "Timed out waiting for the browser authorization"])))
      }
    }
  }

  func stop() {
    listener.cancel()
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

  private func handle(_ connection: NWConnection) {
    connection.start(queue: .global())
    connection.receive(minimumIncompleteLength: 1, maximumLength: 16384) { [weak self] data, _, _, _ in
      guard let self, let data, let request = String(data: data, encoding: .utf8),
        let firstLine = request.split(separator: "\r\n").first,
        let path = firstLine.split(separator: " ").dropFirst().first,
        let components = URLComponents(string: String(path))
      else {
        connection.cancel()
        return
      }
      let items = components.queryItems ?? []
      let code = items.first(where: { $0.name == "code" })?.value
      let state = items.first(where: { $0.name == "state" })?.value
      let body =
        code != nil
        ? "<html><body style='font-family:system-ui;background:#111;color:#fff;text-align:center;padding-top:20vh'><h2>Connected</h2><p>You can close this window and return to Omi.</p></body></html>"
        : "<html><body style='font-family:system-ui;background:#111;color:#fff;text-align:center;padding-top:20vh'><h2>Authorization failed</h2><p>Return to Omi and try again.</p></body></html>"
      let response =
        "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: \(body.utf8.count)\r\nConnection: close\r\n\r\n\(body)"
      connection.send(
        content: Data(response.utf8),
        completion: .contentProcessed { _ in
          connection.cancel()
        })
      if let code, let state {
        self.finish(.success(Callback(code: code, state: state)))
      } else if components.path == "/callback" {
        self.finish(
          .failure(
            NSError(
              domain: "LoopbackCallbackListener", code: 3,
              userInfo: [NSLocalizedDescriptionKey: "The authorization was denied or returned no code"])))
      }
    }
  }
}
