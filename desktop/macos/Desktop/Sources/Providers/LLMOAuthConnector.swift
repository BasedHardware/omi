import AppKit
import CryptoKit
import Foundation
import Network
import Security

enum LLMOAuthProvider: String, CaseIterable {
  case chatgpt
  case grok

  var connectionStorageKey: String {
    switch self {
    case .chatgpt: return DefaultsKey.chatGPTLLMOAuthConnected.rawValue
    case .grok: return DefaultsKey.grokLLMOAuthConnected.rawValue
    }
  }

  var redirectURI: String {
    switch self {
    case .chatgpt: return "http://localhost:1455/auth/callback"
    case .grok: return "http://127.0.0.1:56121/callback"
    }
  }

  fileprivate var authorizationEndpoint: String {
    switch self {
    case .chatgpt: return "https://auth.openai.com/oauth/authorize"
    case .grok: return "https://auth.x.ai/oauth2/authorize"
    }
  }

  fileprivate var clientID: String {
    switch self {
    case .chatgpt: return "app_EMoamEEZ73f0CkXaXp7hrann"
    case .grok: return "b1a00492-073a-47ea-816f-4c329264a828"
    }
  }

  fileprivate var scope: String {
    switch self {
    case .chatgpt: return "openid profile email offline_access"
    case .grok: return "openid profile email offline_access grok-cli:access api:access"
    }
  }

  fileprivate func authorizationItems(verifier: String, state: String, challenge: String) -> [URLQueryItem] {
    var items = [
      URLQueryItem(name: "client_id", value: clientID),
      URLQueryItem(name: "response_type", value: "code"),
      URLQueryItem(name: "redirect_uri", value: redirectURI),
      URLQueryItem(name: "scope", value: scope),
      URLQueryItem(name: "code_challenge", value: challenge),
      URLQueryItem(name: "code_challenge_method", value: "S256"),
      URLQueryItem(name: "state", value: state),
    ]
    if self == .chatgpt {
      items += [
        URLQueryItem(name: "id_token_add_organizations", value: "true"),
        URLQueryItem(name: "codex_cli_simplified_flow", value: "true"),
        URLQueryItem(name: "originator", value: "omi"),
      ]
    }
    return items
  }
}

final class LLMOAuthConnector: @unchecked Sendable {
  enum Error: LocalizedError {
    case invalidAuthorizationURL
    case callbackUnavailable
    case timedOut
    case invalidCallback

    var errorDescription: String? {
      switch self {
      case .invalidAuthorizationURL: return "Could not start provider sign-in."
      case .callbackUnavailable: return "Another app is using the provider sign-in callback."
      case .timedOut: return "Provider sign-in timed out. Try again."
      case .invalidCallback: return "Provider sign-in did not complete."
      }
    }
  }

  static let shared = LLMOAuthConnector()

  func connect(_ provider: LLMOAuthProvider) async throws {
    let listener = try CallbackListener(provider: provider)
    defer { listener.cancel() }
    let verifier = Self.randomURLSafe(length: 64)
    let state = Self.randomURLSafe(length: 24)
    let challenge = Self.codeChallenge(for: verifier)
    var components = URLComponents(string: provider.authorizationEndpoint)!
    components.queryItems = provider.authorizationItems(verifier: verifier, state: state, challenge: challenge)
    guard let url = components.url else { throw Error.invalidAuthorizationURL }
    _ = await MainActor.run { NSWorkspace.shared.open(url) }
    let values = try await listener.waitForCallback(timeout: 240)
    guard values["state"] == state, let code = values["code"] else { throw Error.invalidCallback }
    try await APIClient.shared.completeLLMOAuth(
      provider: provider,
      code: code,
      codeVerifier: verifier,
      redirectURI: provider.redirectURI
    )
    UserDefaults.standard.set(true, forKey: provider.connectionStorageKey)
  }

  static func randomURLSafe(length: Int) -> String {
    var bytes = [UInt8](repeating: 0, count: length)
    _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
    return Data(bytes)
      .base64EncodedString()
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
  }

  static func codeChallenge(for verifier: String) -> String {
    Data(SHA256.hash(data: Data(verifier.utf8)))
      .base64EncodedString()
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
  }

  private final class CallbackListener: @unchecked Sendable {
    private let listener: NWListener
    private let lock = NSLock()
    private var continuation: CheckedContinuation<[String: String], Swift.Error>?

    init(provider: LLMOAuthProvider) throws {
      let port = provider == .chatgpt ? UInt16(1455) : UInt16(56121)
      guard let endpointPort = NWEndpoint.Port(rawValue: port) else { throw Error.callbackUnavailable }
      do {
        listener = try NWListener(using: .tcp, on: endpointPort)
      } catch {
        throw Error.callbackUnavailable
      }
      listener.newConnectionHandler = { [weak self] connection in
        self?.handle(connection)
      }
      listener.start(queue: DispatchQueue(label: "llm-oauth-callback"))
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
          self?.finish(.failure(Error.timedOut))
        }
      }
    }

    private func handle(_ connection: NWConnection) {
      connection.start(queue: DispatchQueue(label: "llm-oauth-callback-connection"))
      connection.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, _, _ in
        guard let self, let data, let request = String(data: data, encoding: .utf8) else {
          connection.cancel()
          return
        }
        let values = Self.queryItems(request)
        let html = "<html><body><h2>Omi is connected. You can close this tab.</h2></body></html>"
        let response =
          "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: \(html.utf8.count)\r\nConnection: close\r\n\r\n\(html)"
        connection.send(content: Data(response.utf8), completion: .contentProcessed { _ in connection.cancel() })
        if !values.isEmpty {
          self.finish(.success(values))
        }
      }
    }

    private func finish(_ result: Result<[String: String], Swift.Error>) {
      lock.lock()
      let continuation = self.continuation
      self.continuation = nil
      lock.unlock()
      switch result {
      case .success(let values): continuation?.resume(returning: values)
      case .failure(let error): continuation?.resume(throwing: error)
      }
    }

    private static func queryItems(_ request: String) -> [String: String] {
      guard let line = request.split(separator: "\r\n").first,
        line.hasPrefix("GET "),
        let path = line.split(separator: " ").dropFirst().first,
        let components = URLComponents(string: String(path))
      else { return [:] }
      return (components.queryItems ?? []).reduce(into: [String: String]()) { result, item in
        if let value = item.value { result[item.name] = value }
      }
    }
  }
}
