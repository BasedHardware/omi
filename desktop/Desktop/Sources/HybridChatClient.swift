import Foundation

/// Direct OpenAI-compatible chat completions for hybrid local daemon mode (no pi-mono proxy).
enum HybridChatClient {

  struct ProviderConfig: Equatable {
    let baseURL: String
    let model: String
    let apiKey: String
    let providerAccountID: String?
    let providerKind: String?
    let slotSource: String?
    let resolutionReason: String?

    init(
      baseURL: String,
      model: String,
      apiKey: String,
      providerAccountID: String? = nil,
      providerKind: String? = nil,
      slotSource: String? = nil,
      resolutionReason: String? = nil
    ) {
      self.baseURL = baseURL
      self.model = model
      self.apiKey = apiKey
      self.providerAccountID = providerAccountID
      self.providerKind = providerKind
      self.slotSource = slotSource
      self.resolutionReason = resolutionReason
    }
  }

  struct CompletionResult: Equatable {
    let text: String
    let model: String
    let providerAccountID: String?
    let providerKind: String?
    let slotSource: String?
    let resolutionReason: String?
    let inputTokens: Int
    let outputTokens: Int
  }

  enum ClientError: LocalizedError {
    case notConfigured(String)
    case invalidSettings
    case invalidResponse
    case providerError(String)

    var errorDescription: String? {
      switch self {
      case .notConfigured(let reason):
        if reason.isEmpty {
          return "Chat model slot is not configured. Configure the chat slot in local provider policy."
        }
        return "Chat model slot is not configured: \(reason)"
      case .invalidSettings:
        return "Chat provider policy settings are invalid."
      case .invalidResponse:
        return "Chat provider returned an unexpected response."
      case .providerError(let message):
        return message
      }
    }
  }

  static func isEnabled() -> Bool {
    if CodexAuthService.isActive {
      return true
    }
    guard DesktopBackendEnvironment.selectedBackendTarget.mode == .localDaemon else {
      return false
    }
    guard DesktopBackendEnvironment.isCapability(.directChat, availableIn: .localDaemon) else {
      return false
    }
    return true
  }

  static func resolveEffectiveChatConfig(
    from response: HybridProviderPolicy.SlotResolutionResponse
  ) -> ProviderConfig? {
    HybridProviderPolicy.chatProviderConfig(from: response)
  }

  /// Resolves the daemon chat slot and completes one chat turn (non-streaming).
  static func completeFromDaemonSettings(
    systemPrompt: String,
    conversationMessages: [(role: String, text: String)],
    userMessage: String
  ) async throws -> CompletionResult {
    if CodexAuthService.isActive {
      await CodexProxyService.shared.ensureRunning()
    }
    let resolution = try await APIClient.shared.resolveSelectedBackendProviderSlot(
      HybridProviderPolicy.chatSlot)
    return try await complete(
      systemPrompt: systemPrompt,
      conversationMessages: conversationMessages,
      userMessage: userMessage,
      slotResolution: resolution
    )
  }

  static func complete(
    systemPrompt: String,
    conversationMessages: [(role: String, text: String)],
    userMessage: String,
    slotResolution: HybridProviderPolicy.SlotResolutionResponse,
    session: URLSession = .shared
  ) async throws -> CompletionResult {
    guard let config = resolveEffectiveChatConfig(from: slotResolution) else {
      throw ClientError.notConfigured(slotResolution.resolution.reason)
    }
    return try await completeOpenAICompatible(
      config: config,
      systemPrompt: systemPrompt,
      conversationMessages: conversationMessages,
      userMessage: userMessage,
      session: session
    )
  }

  private struct ChatCompletionMessage: Encodable {
    let role: String
    let content: String
  }

  private struct ChatCompletionRequest: Encodable {
    let model: String
    let messages: [ChatCompletionMessage]
    let temperature: Double
  }

  private static func completeOpenAICompatible(
    config: ProviderConfig,
    systemPrompt: String,
    conversationMessages: [(role: String, text: String)],
    userMessage: String,
    session: URLSession
  ) async throws -> CompletionResult {
    let base = config.baseURL.hasSuffix("/") ? String(config.baseURL.dropLast()) : config.baseURL
    guard let url = URL(string: "\(base)/chat/completions") else {
      throw ClientError.invalidSettings
    }

    var apiMessages: [ChatCompletionMessage] = [
      ChatCompletionMessage(role: "system", content: systemPrompt)
    ]
    for turn in conversationMessages {
      apiMessages.append(ChatCompletionMessage(role: turn.role, content: turn.text))
    }
    apiMessages.append(ChatCompletionMessage(role: "user", content: userMessage))

    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    if !config.apiKey.isEmpty {
      request.setValue("Bearer \(config.apiKey)", forHTTPHeaderField: "Authorization")
    }
    request.timeoutInterval = 120
    let payload = ChatCompletionRequest(
      model: config.model,
      messages: apiMessages,
      temperature: 0.2
    )
    request.httpBody = try JSONEncoder().encode(payload)

    let (data, response) = try await session.data(for: request)
    guard let http = response as? HTTPURLResponse else {
      throw ClientError.invalidResponse
    }
    guard (200..<300).contains(http.statusCode) else {
      throw ClientError.providerError(parseProviderErrorBody(data: data, statusCode: http.statusCode))
    }
    guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      let choices = json["choices"] as? [[String: Any]],
      let first = choices.first,
      let msg = first["message"] as? [String: Any]
    else {
      throw ClientError.invalidResponse
    }

    let content: String
    if let str = msg["content"] as? String {
      content = str
    } else if let parts = msg["content"] as? [[String: Any]] {
      let texts = parts.compactMap { $0["text"] as? String }
      content = texts.joined(separator: "\n")
    } else {
      throw ClientError.invalidResponse
    }

    let returnedModel = (json["model"] as? String) ?? config.model
    var inputTokens = 0
    var outputTokens = 0
    if let usage = json["usage"] as? [String: Any] {
      inputTokens = usage["prompt_tokens"] as? Int ?? usage["input_tokens"] as? Int ?? 0
      outputTokens =
        usage["completion_tokens"] as? Int ?? usage["output_tokens"] as? Int ?? 0
    }

    return CompletionResult(
      text: content.trimmingCharacters(in: .whitespacesAndNewlines),
      model: returnedModel,
      providerAccountID: config.providerAccountID,
      providerKind: config.providerKind,
      slotSource: config.slotSource,
      resolutionReason: config.resolutionReason,
      inputTokens: inputTokens,
      outputTokens: outputTokens
    )
  }

  private static func parseProviderErrorBody(data: Data, statusCode: Int) -> String {
    if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
      if let error = json["error"] as? [String: Any],
        let message = error["message"] as? String,
        !message.isEmpty
      {
        return message
      }
      if let detail = json["detail"] as? String, !detail.isEmpty {
        return detail
      }
    }
    let snippet =
      String(data: data.prefix(400), encoding: .utf8)?
      .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if snippet.isEmpty {
      return "Chat provider request failed (HTTP \(statusCode))."
    }
    return "Chat provider request failed (HTTP \(statusCode)): \(snippet)"
  }
}
