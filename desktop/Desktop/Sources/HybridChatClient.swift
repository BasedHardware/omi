import Foundation

/// Direct OpenAI-compatible chat completions for desktop provider routes.
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
          return
            "Chat model slot is not configured. Configure the chat slot in local provider policy."
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

  enum Route: Equatable {
    case directCodex(ProviderConfig)
    case directDaemonChatSlot
    case agentBridge(reason: String)

    var usesDirectProvider: Bool {
      switch self {
      case .directCodex, .directDaemonChatSlot:
      return true
      case .agentBridge:
        return false
    }
    }

    var supportsInlineImages: Bool {
      switch self {
      case .directCodex:
        return true
      case .directDaemonChatSlot:
      return false
      case .agentBridge:
        return true
      }
    }

    var displayName: String {
      switch self {
      case .directCodex:
        return "ChatGPT plan"
      case .directDaemonChatSlot:
        return "Local provider policy"
      case .agentBridge:
        return "Agent bridge"
      }
    }
  }

  static func currentRoute() -> Route {
    if CodexAuthService.isActive {
      if let config = codexChatConfig() {
        return .directCodex(config)
      }
      return .agentBridge(
        reason: "ChatGPT plan is connected, but no Codex auth snapshot is available.")
    }
    guard DesktopBackendEnvironment.selectedBackendTarget.mode == .localDaemon else {
      return .agentBridge(reason: "Cloud backend mode uses the agent bridge.")
    }
    guard DesktopBackendEnvironment.isCapability(.directChat, availableIn: .localDaemon) else {
      return .agentBridge(
        reason: DesktopBackendEnvironment.unavailableReason(for: .directChat, in: .localDaemon)
          ?? "Direct local chat is unavailable."
      )
    }
    return .directDaemonChatSlot
  }

  static func resolveEffectiveChatConfig(
    from response: HybridProviderPolicy.SlotResolutionResponse
  ) -> ProviderConfig? {
    HybridProviderPolicy.chatProviderConfig(from: response)
  }

  /// Completes one non-streaming turn through the active direct provider route.
  static func completeWithActiveDirectProvider(
    systemPrompt: String,
    conversationMessages: [(role: String, text: String)],
    userMessage: String,
    imageData: Data? = nil,
    session: URLSession = .shared,
    ensureCodexProxy: Bool = true
  ) async throws -> CompletionResult {
    switch currentRoute() {
    case .directCodex(let config):
      if ensureCodexProxy {
      await CodexProxyService.shared.ensureRunning()
    }
      return try await completeOpenAICompatible(
        config: config,
        systemPrompt: systemPrompt,
        conversationMessages: conversationMessages,
        userMessage: userMessage,
        imageData: imageData,
        session: session
      )
    case .directDaemonChatSlot:
    let resolution = try await APIClient.shared.resolveSelectedBackendProviderSlot(
      HybridProviderPolicy.chatSlot)
    return try await complete(
      systemPrompt: systemPrompt,
      conversationMessages: conversationMessages,
      userMessage: userMessage,
        slotResolution: resolution,
        imageData: imageData,
        session: session
    )
    case .agentBridge(let reason):
      throw ClientError.notConfigured(reason)
    }
  }

  static func complete(
    systemPrompt: String,
    conversationMessages: [(role: String, text: String)],
    userMessage: String,
    slotResolution: HybridProviderPolicy.SlotResolutionResponse,
    imageData: Data? = nil,
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
      imageData: imageData,
      session: session
    )
  }

  private static func codexChatConfig() -> ProviderConfig? {
    guard let config = HybridLLMClient.codexProviderConfig() else { return nil }
    return ProviderConfig(
      baseURL: config.baseURL,
      model: config.model,
      apiKey: config.apiKey,
      providerAccountID: "chatgpt-plan",
      providerKind: "openai_compatible",
      slotSource: "chatgpt_plan",
      resolutionReason: "ChatGPT plan subscription integration"
    )
  }

  private enum ChatCompletionContent: Encodable {
    case text(String)
    case parts([ChatCompletionContentPart])

    func encode(to encoder: Encoder) throws {
      switch self {
      case .text(let value):
        var container = encoder.singleValueContainer()
        try container.encode(value)
      case .parts(let parts):
        var container = encoder.singleValueContainer()
        try container.encode(parts)
      }
    }
  }

  private struct ChatCompletionContentPart: Encodable {
    private struct ImageURL: Encodable {
      let url: String
    }

    private let type: String
    private let text: String?
    private let imageURL: ImageURL?

    enum CodingKeys: String, CodingKey {
      case type
      case text
      case imageURL = "image_url"
    }

    static func text(_ value: String) -> ChatCompletionContentPart {
      ChatCompletionContentPart(type: "text", text: value, imageURL: nil)
    }

    static func image(_ imageData: Data) -> ChatCompletionContentPart {
      ChatCompletionContentPart(
        type: "image_url",
        text: nil,
        imageURL: ImageURL(url: "data:image/png;base64,\(imageData.base64EncodedString())")
      )
    }

    func encode(to encoder: Encoder) throws {
      var container = encoder.container(keyedBy: CodingKeys.self)
      try container.encode(type, forKey: .type)
      if let text {
        try container.encode(text, forKey: .text)
      }
      if let imageURL {
        try container.encode(imageURL, forKey: .imageURL)
      }
    }
  }

  private struct ChatCompletionMessage: Encodable {
    let role: String
    let content: ChatCompletionContent
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
    imageData: Data?,
    session: URLSession
  ) async throws -> CompletionResult {
    let base = config.baseURL.hasSuffix("/") ? String(config.baseURL.dropLast()) : config.baseURL
    guard let url = URL(string: "\(base)/chat/completions") else {
      throw ClientError.invalidSettings
    }

    var apiMessages: [ChatCompletionMessage] = [
      ChatCompletionMessage(role: "system", content: .text(systemPrompt))
    ]
    for turn in conversationMessages {
      apiMessages.append(ChatCompletionMessage(role: turn.role, content: .text(turn.text)))
    }
    if let imageData {
      apiMessages.append(
        ChatCompletionMessage(
          role: "user",
          content: .parts([
            .text(userMessage),
            .image(imageData),
          ])
        )
      )
    } else {
      apiMessages.append(ChatCompletionMessage(role: "user", content: .text(userMessage)))
    }

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
      throw ClientError.providerError(
        parseProviderErrorBody(data: data, statusCode: http.statusCode))
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
