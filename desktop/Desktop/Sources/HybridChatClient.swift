import Foundation

/// Direct OpenAI-compatible chat completions for hybrid local daemon mode (no pi-mono proxy).
enum HybridChatClient {

  struct ProviderConfig: Equatable {
    let baseURL: String
    let model: String
    let apiKey: String
  }

  struct CompletionResult: Equatable {
    let text: String
    let model: String
    let inputTokens: Int
    let outputTokens: Int
  }

  enum ClientError: LocalizedError {
    case notConfigured
    case invalidSettings
    case invalidResponse

    var errorDescription: String? {
      switch self {
      case .notConfigured:
        return
          "Hybrid direct chat is not configured. Set chat_provider or ai_provider in Settings → Plan and Usage (or run a local LLM at the default Ollama URL)."
      case .invalidSettings:
        return "chat_provider settings are invalid."
      case .invalidResponse:
        return "Chat provider returned an unexpected response."
      }
    }
  }

  static func isEnabled() -> Bool {
    guard DesktopBackendEnvironment.selectedBackendTarget.mode == .localDaemon else {
      return false
    }
    guard DesktopBackendEnvironment.isCapability(.directChat, availableIn: .localDaemon) else {
      return false
    }
    return true
  }

  /// Resolves chat_provider → ai_provider / provider (matches HybridLLMClient).
  static func resolveEffectiveChatConfig(from settings: [LocalDaemonSetting]) -> ProviderConfig? {
    if let chat = loadProviderConfig(from: settings, key: "chat_provider") {
      return chat
    }
    if let ai = loadProviderConfig(from: settings, keys: ["ai_provider", "provider"]) {
      return ai
    }
    return byokOpenAIConfig()
  }

  static func loadProviderConfig(from settings: [LocalDaemonSetting]) -> ProviderConfig? {
    loadProviderConfig(from: settings, key: "chat_provider")
  }

  private static func loadProviderConfig(
    from settings: [LocalDaemonSetting],
    key: String
  ) -> ProviderConfig? {
    loadProviderConfig(from: settings, keys: [key])
  }

  private static func loadProviderConfig(
    from settings: [LocalDaemonSetting],
    keys: [String]
  ) -> ProviderConfig? {
    guard let raw = settings.first(where: { keys.contains($0.key) })?.valueJson,
      let data = raw.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }
    return parseOpenAICompatible(json: json)
  }

  private static func parseOpenAICompatible(json: [String: Any]) -> ProviderConfig? {
    let kind = (json["kind"] as? String)?.lowercased() ?? ""
    guard kind == "openai_compatible" || kind == "openai" else {
      return nil
    }
    guard let baseURL = json["base_url"] as? String, !baseURL.isEmpty else {
      return nil
    }
    let model = (json["model"] as? String) ?? HybridProviderReadiness.defaultModel()
    let apiKey =
      (json["api_key"] as? String) ?? (json["key"] as? String) ?? ""
    return ProviderConfig(baseURL: baseURL, model: model, apiKey: apiKey)
  }

  private static func byokOpenAIConfig() -> ProviderConfig? {
    guard let key = APIKeyService.byokKey(.openai), !key.isEmpty else {
      return nil
    }
    let model =
      ProcessInfo.processInfo.environment["OMI_HYBRID_BYOK_OPENAI_MODEL"].flatMap {
        $0.trimmingCharacters(in: .whitespacesAndNewlines)
      }.flatMap { $0.isEmpty ? nil : $0 } ?? "gpt-4o-mini"
    return ProviderConfig(baseURL: "https://api.openai.com/v1", model: model, apiKey: key)
  }

  /// Loads daemon hybrid settings and completes one chat turn (non-streaming).
  static func completeFromDaemonSettings(
    systemPrompt: String,
    conversationMessages: [(role: String, text: String)],
    userMessage: String
  ) async throws -> CompletionResult {
    let settings = try await APIClient.shared.getSelectedBackendSettings()
    return try await complete(
      systemPrompt: systemPrompt,
      conversationMessages: conversationMessages,
      userMessage: userMessage,
      settings: settings
    )
  }

  static func complete(
    systemPrompt: String,
    conversationMessages: [(role: String, text: String)],
    userMessage: String,
    settings: [LocalDaemonSetting]
  ) async throws -> CompletionResult {
    guard let config = resolveEffectiveChatConfig(from: settings) else {
      throw ClientError.notConfigured
    }
    return try await completeOpenAICompatible(
      config: config,
      systemPrompt: systemPrompt,
      conversationMessages: conversationMessages,
      userMessage: userMessage
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
    userMessage: String
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

    let (data, response) = try await URLSession.shared.data(for: request)
    guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
      throw ClientError.invalidResponse
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
      inputTokens: inputTokens,
      outputTokens: outputTokens
    )
  }
}
