import Foundation

protocol LocalInferenceHTTPClient: Sendable {
  func send(_ request: URLRequest) async throws -> (Data, URLResponse)
}

/// Refuses every HTTP redirect.
///
/// `requireLoopback` validates the *configured* base URL. `URLSession` with no
/// delegate follows up to 20 redirects on its own, and a 307/308 preserves the
/// method and body — so a process answering on the configured loopback port
/// could reply `307 Location: https://<anywhere>` and the POST, prompt and
/// transcript included, would be re-sent there under the user's network
/// identity. `requireLoopback` never sees that URL, because the redirect is
/// resolved below the adapter.
///
/// A local OpenAI-compatible server has no legitimate reason to redirect, so
/// the policy is refusal rather than re-validation: there is no correct
/// redirect for this adapter to follow, and refusing is the only rule with no
/// second URL to get wrong.
final class LocalInferenceRedirectPolicy: NSObject, URLSessionTaskDelegate, Sendable {
  func urlSession(
    _ session: URLSession,
    task: URLSessionTask,
    willPerformHTTPRedirection response: HTTPURLResponse,
    newRequest request: URLRequest,
    completionHandler: @escaping (URLRequest?) -> Void
  ) {
    completionHandler(nil)
  }
}

struct URLSessionLocalInferenceHTTPClient: LocalInferenceHTTPClient {
  private static let redirectPolicy = LocalInferenceRedirectPolicy()

  /// Never `URLSession.shared`: the shared session carries no delegate, so it
  /// follows redirects, and it cannot be given this policy without changing
  /// behaviour for every other caller in the app. One session for the process,
  /// because a session created per request would retain its delegate until
  /// invalidated and leak.
  static let fencedSession = URLSession(
    configuration: .ephemeral,
    delegate: redirectPolicy,
    delegateQueue: nil
  )

  var session: URLSession

  init(session: URLSession? = nil) {
    self.session = session ?? Self.fencedSession
  }

  func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
    try await session.data(for: request)
  }
}

enum LocalInferenceLoopback {
  /// Fail closed: the local-server adapter may only speak to a loopback host.
  /// A misconfigured paid or remote endpoint is an error, never a silent
  /// route onto a cloud provider.
  static let allowedSchemes: Set<String> = ["http", "https"]

  static func isAllowed(_ url: URL) -> Bool {
    // A non-HTTP scheme is not a local model server. `file:` in particular
    // would make the "base URL" a path read, and a custom scheme can be
    // claimed by any installed app.
    guard let scheme = url.scheme?.lowercased(), allowedSchemes.contains(scheme) else {
      return false
    }
    guard let host = url.host?.trimmingCharacters(in: .whitespacesAndNewlines), !host.isEmpty else {
      return false
    }
    let normalized = host.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
    if normalized == "localhost" || normalized == "::1" { return true }
    return isLoopbackIPv4(normalized)
  }

  static func requireLoopback(_ url: URL) throws {
    guard isAllowed(url) else {
      throw LocalInferenceError.nonLoopbackBaseURL(url.absoluteString)
    }
  }

  private static func isLoopbackIPv4(_ host: String) -> Bool {
    let parts = host.split(separator: ".", omittingEmptySubsequences: false)
    guard parts.count == 4, parts.first == "127" else { return false }
    return parts.allSatisfy { part in
      guard let value = Int(part) else { return false }
      return (0...255).contains(value)
    }
  }
}

struct LocalServerInferenceConfiguration: Sendable, Equatable {
  var baseURL: URL
  var model: String
  var contextWindowTokens: Int
  var timeout: TimeInterval

  static func fromKillSwitchSources(
    environment: [String: String] = ProcessInfo.processInfo.environment,
    defaults: UserDefaults = .standard
  ) -> LocalServerInferenceConfiguration {
    LocalServerInferenceConfiguration(
      baseURL: LocalInferenceKillSwitches.localServerURL(environment: environment, defaults: defaults),
      model: LocalInferenceKillSwitches.localServerModel(environment: environment, defaults: defaults),
      contextWindowTokens: 8192,
      timeout: 60
    )
  }
}

/// OpenAI-compatible localhost client. Does not start or bundle a runtime.
struct LocalServerInferenceAdapter: LocalInferenceService {
  var engineID: LocalInferenceEngineID { .localServer }
  var capabilities: LocalInferenceCapabilities {
    LocalInferenceCapabilities(
      structuredOutput: true,
      toolLoop: false,
      contextWindowTokens: configuration.contextWindowTokens
    )
  }

  var configuration: LocalServerInferenceConfiguration
  var httpClient: any LocalInferenceHTTPClient

  init(
    configuration: LocalServerInferenceConfiguration,
    httpClient: any LocalInferenceHTTPClient = URLSessionLocalInferenceHTTPClient()
  ) {
    self.configuration = configuration
    self.httpClient = httpClient
  }

  func generateStructured<T: Decodable>(prompt: String, schema: LocalInferenceJSONSchema) async throws -> T {
    try LocalInferenceLoopback.requireLoopback(configuration.baseURL)
    var request = URLRequest(
      url: chatCompletionsURL(baseURL: configuration.baseURL),
      timeoutInterval: configuration.timeout
    )
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = try encodeChatRequest(prompt: prompt, schema: schema)

    let (data, response) = try await httpClient.send(request)
    let status = (response as? HTTPURLResponse)?.statusCode ?? -1
    guard (200...299).contains(status) else {
      throw LocalInferenceError.httpStatus(status)
    }
    let completion = try JSONDecoder().decode(OpenAIChatCompletionResponse.self, from: data)
    let content = try unwrapContent(completion)
    let payload = try jsonObjectData(from: content)
    return try JSONDecoder().decode(T.self, from: payload)
  }

  func runToolLoop(prompt _: String, tools _: [LocalInferenceToolSpec], budget _: ToolLoopBudget) async throws
    -> ToolLoopResult
  {
    throw LocalInferenceError.capabilityUnavailable("tool_loop")
  }

  private func chatCompletionsURL(baseURL: URL) -> URL {
    var path = baseURL.absoluteString
    if path.hasSuffix("/") { path.removeLast() }
    if path.hasSuffix("/chat/completions") {
      return URL(string: path) ?? baseURL
    }
    return URL(string: path + "/chat/completions") ?? baseURL.appendingPathComponent("chat/completions")
  }

  private func encodeChatRequest(prompt: String, schema: LocalInferenceJSONSchema) throws -> Data {
    let schemaObject = try JSONSerialization.jsonObject(with: schema.json)
    let body: [String: Any] = [
      "model": configuration.model,
      "messages": [
        ["role": "user", "content": prompt]
      ],
      "response_format": [
        "type": "json_schema",
        "json_schema": [
          "name": schema.name,
          "strict": true,
          "schema": schemaObject,
        ],
      ],
    ]
    return try JSONSerialization.data(withJSONObject: body)
  }

  private func unwrapContent(_ completion: OpenAIChatCompletionResponse) throws -> String {
    guard let content = completion.choices.first?.message.content?.trimmingCharacters(in: .whitespacesAndNewlines),
      !content.isEmpty
    else {
      throw LocalInferenceError.invalidResponse("empty_content")
    }
    return content
  }

  private func jsonObjectData(from content: String) throws -> Data {
    var json = content
    if json.hasPrefix("```") {
      json = json.replacingOccurrences(of: "^```(?:json)?\\s*", with: "", options: .regularExpression)
      json = json.replacingOccurrences(of: "\\s*```$", with: "", options: .regularExpression)
    }
    guard let data = json.data(using: .utf8) else {
      throw LocalInferenceError.invalidResponse("undecodable_content")
    }
    return data
  }
}

private struct OpenAIChatCompletionResponse: Decodable {
  struct Choice: Decodable {
    struct Message: Decodable {
      var content: String?
    }
    var message: Message
  }
  var choices: [Choice]
}
