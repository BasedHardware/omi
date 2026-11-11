import Foundation
import os

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

/// Qwen3.5 defaults to thinking on; temperature zero also looped inside strings
/// in 3/19 measured calls. The model-card non-thinking settings had 0/51 loops
/// (2026-09-20). Send them explicitly so server launch flags do not pick behavior.
struct LocalServerInferenceSampling: Sendable, Equatable {
  var temperature: Double = 0.7
  var topP: Double = 0.8
  var topK: Int = 20
  var minP: Double = 0
  var presencePenalty: Double = 1.5
  var disableThinking: Bool = true
}

struct LocalServerInferenceConfiguration: Sendable, Equatable {
  var baseURL: URL
  var model: String
  var contextWindowTokens: Int
  var timeout: TimeInterval
  /// Sent as `max_tokens`. A full draft at the schema's caps measured 1,500–1,800
  /// tokens on a 40-minute meeting; this leaves headroom and still ends a
  /// runaway in about a minute instead of at the end of the window.
  var maxCompletionTokens: Int = 4096
  var sampling: LocalServerInferenceSampling = .init()

  static func fromKillSwitchSources(
    environment: [String: String] = ProcessInfo.processInfo.environment,
    defaults: UserDefaults = .standard
  ) -> LocalServerInferenceConfiguration {
    LocalServerInferenceConfiguration(
      baseURL: LocalInferenceKillSwitches.localServerURL(environment: environment, defaults: defaults),
      model: LocalInferenceKillSwitches.localServerModel(environment: environment, defaults: defaults),
      contextWindowTokens: LocalInferenceKillSwitches.localServerContextTokens(
        environment: environment, defaults: defaults),
      timeout: LocalInferenceKillSwitches.localServerTimeoutSeconds(
        environment: environment, defaults: defaults)
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

    // Elapsed time is logged on every exit, including the throwing ones. A
    // request that died at exactly `timeout` seconds is a transport fault; one
    // that returned quickly with nothing useful is a model result. Both reach
    // the caller as the deterministic minimum, so the log is the only place the
    // two can be told apart.
    let started = ContinuousClock.now
    let promptBytes = request.httpBody?.count ?? 0
    func elapsedMs() -> Int { max(0, Int(started.duration(to: .now) / .milliseconds(1))) }

    let data: Data
    let response: URLResponse
    do {
      (data, response) = try await httpClient.send(request)
    } catch {
      let nsError = error as NSError
      Self.emit(
        "LOCAL_SERVER_CALL outcome=transport_error elapsed_ms=\(elapsedMs()) timeout_s=\(Int(configuration.timeout)) request_bytes=\(promptBytes) domain=\(nsError.domain) code=\(nsError.code)"
      )
      throw error
    }
    let status = (response as? HTTPURLResponse)?.statusCode ?? -1
    guard (200...299).contains(status) else {
      // The body of a llama-server 4xx/5xx is the actual error. Without it a
      // context overflow, a grammar compile failure and an OOM are all "400".
      let detail = String(decoding: data.prefix(600), as: UTF8.self)
        .replacingOccurrences(of: "\n", with: " ")
      Self.emit(
        "LOCAL_SERVER_CALL outcome=http_\(status) elapsed_ms=\(elapsedMs()) request_bytes=\(promptBytes) detail=\(detail)"
      )
      throw LocalInferenceError.httpStatus(status)
    }
    let usage = try? JSONDecoder().decode(OpenAIUsageEnvelope.self, from: data)
    Self.emit(
      "LOCAL_SERVER_CALL outcome=ok elapsed_ms=\(elapsedMs()) request_bytes=\(promptBytes) prompt_tokens=\(usage?.usage?.promptTokens ?? -1) completion_tokens=\(usage?.usage?.completionTokens ?? -1) finish=\(usage?.choices?.first?.finishReason ?? "unknown")"
    )
    let completion: OpenAIChatCompletionResponse
    do {
      completion = try JSONDecoder().decode(OpenAIChatCompletionResponse.self, from: data)
    } catch {
      throw LocalInferenceError.invalidResponse("undecodable_content")
    }
    let content = try unwrapContent(completion)
    let payload = try jsonObjectData(from: content)
    do {
      return try JSONDecoder().decode(T.self, from: payload)
    } catch {
      throw LocalInferenceError.invalidResponse("undecodable_content")
    }
  }

  private static let callLog = Logger(subsystem: "com.omi.desktop", category: "local-inference")

  /// `Logger` for the app, and stdout when an evaluation asks for it, because
  /// `swift test` does not surface the unified log.
  private static func emit(_ line: String) {
    callLog.info("\(line, privacy: .public)")
    if ProcessInfo.processInfo.environment["OMI_LOCAL_INFERENCE_TRACE"] == "1" {
      print(line)
    }
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

  /// Builds the request with the schema spliced in **verbatim**.
  ///
  /// The schema used to be parsed with `JSONSerialization` and re-serialized as
  /// part of the body. That round-trip goes through an unordered dictionary, so
  /// `title, overview, …, sections, …, action_items` reached the server as
  /// `category, events, emoji, sections, title, action_items, overview`.
  /// llama.cpp compiles `json_schema` to a grammar that emits properties in the
  /// order the schema lists them, so property order *is* generation order: the
  /// model was made to write `sections` before it had written a title or an
  /// overview. Measured 2026-09-20 on Qwen3.5-4B at 32K: with nothing planned, it
  /// poured a whole 40-minute meeting into one section body, fell into a
  /// repetition loop inside that string, and generated 23,626 tokens to the end
  /// of the window — 407 s, then the deterministic minimum. The authored order
  /// completes the same prompt in 25 s.
  ///
  /// `maxItems` cannot stop that loop, because it is inside a string. Only a
  /// token cap can, so one is sent: `max_tokens` bounds the cost of a runaway; it
  /// does not rescue the result, which still fails closed.
  private func encodeChatRequest(prompt: String, schema: LocalInferenceJSONSchema) throws -> Data {
    // Still parsed, but only to reject a schema that is not JSON before it is
    // spliced into a body by text.
    _ = try JSONSerialization.jsonObject(with: schema.json)
    let placeholder = "omi-schema-\(UUID().uuidString)"
    var body: [String: Any] = [
      "model": configuration.model,
      "max_tokens": configuration.maxCompletionTokens,
      "temperature": configuration.sampling.temperature,
      "top_p": configuration.sampling.topP,
      "top_k": configuration.sampling.topK,
      "min_p": configuration.sampling.minP,
      "presence_penalty": configuration.sampling.presencePenalty,
      "messages": [
        ["role": "user", "content": prompt]
      ],
      "response_format": [
        "type": "json_schema",
        "json_schema": [
          "name": schema.name,
          "strict": true,
          "schema": placeholder,
        ],
      ],
    ]
    if configuration.sampling.disableThinking {
      body["chat_template_kwargs"] = ["enable_thinking": false]
    }
    let encoded = try JSONSerialization.data(withJSONObject: body)
    guard
      let text = String(data: encoded, encoding: .utf8),
      let schemaText = String(data: schema.json, encoding: .utf8),
      let range = text.range(of: "\"\(placeholder)\"")
    else {
      throw LocalInferenceError.invalidResponse("unencodable_request")
    }
    // A fresh UUID cannot occur in the prompt, and a quoted occurrence inside a
    // JSON string would be escaped (`\"`), so this matches the value only.
    return Data(text.replacingCharacters(in: range, with: schemaText).utf8)
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

/// Token accounting, decoded leniently and only for the log line.
private struct OpenAIUsageEnvelope: Decodable {
  struct Usage: Decodable {
    var promptTokens: Int?
    var completionTokens: Int?
    enum CodingKeys: String, CodingKey {
      case promptTokens = "prompt_tokens"
      case completionTokens = "completion_tokens"
    }
  }
  struct Choice: Decodable {
    var finishReason: String?
    enum CodingKeys: String, CodingKey { case finishReason = "finish_reason" }
  }
  var usage: Usage?
  var choices: [Choice]?
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
