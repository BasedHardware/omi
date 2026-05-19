import Foundation
import Vision

// MARK: - Settings cache

/// Short-TTL cache for local daemon hybrid settings (avoids hitting /v1/settings on every capture frame).
actor HybridDaemonSettingsCache {
  static let shared = HybridDaemonSettingsCache()

  private var cached: [LocalDaemonSetting]?
  private var fetchedAt: Date?
  private let ttlSeconds: TimeInterval = 45

  func settings() async throws -> [LocalDaemonSetting] {
    guard DesktopBackendEnvironment.selectedBackendTarget.mode == .localDaemon else {
      return []
    }
    if let cached, let fetchedAt, Date().timeIntervalSince(fetchedAt) < ttlSeconds {
      return cached
    }
    let fresh = try await APIClient.shared.getSelectedBackendSettings()
    cached = fresh
    fetchedAt = Date()
    return fresh
  }
}

// MARK: - Hybrid LLM (OpenAI-compatible chat completions)

/// Direct OpenAI-compatible `/v1/chat/completions` for hybrid (local daemon) mode.
enum HybridLLMClient {

  struct ProviderConfig: Equatable {
    let baseURL: String
    let model: String
    let apiKey: String
  }

  enum ClientError: LocalizedError {
    case notConfigured
    case invalidSettings
    case invalidResponse
    case httpFailure(status: Int, body: String)

    var errorDescription: String? {
      switch self {
      case .notConfigured:
        return "Hybrid AI is not configured. Set ai_provider or chat_provider in Settings, or add a BYOK OpenAI key."
      case .invalidSettings:
        return "Hybrid provider settings are invalid."
      case .invalidResponse:
        return "Hybrid AI provider returned an unexpected response."
      case .httpFailure(let status, _):
        return "Hybrid AI request failed (HTTP \(status))."
      }
    }
  }

  // MARK: Provider loading

  /// Vision / multimodal routing — optional separate provider (see ``HybridVisionProvider``).
  static func loadVisionProviderConfig(from settings: [LocalDaemonSetting]) -> ProviderConfig? {
    guard HybridVisionProvider.isConfigured(settings: settings) else {
      return nil
    }
    return loadOpenAICompatibleProvider(forKeys: ["vision_provider"], settings: settings)
  }

  /// Primary chat routing for assistants: prefers chat_provider, then legacy ai_provider / provider.
  static func resolveEffectiveChatConfig(settings: [LocalDaemonSetting]) -> ProviderConfig? {
    if let c = loadOpenAICompatibleProvider(forKeys: ["chat_provider"], settings: settings) {
      return c
    }
    return loadOpenAICompatibleProvider(forKeys: ["ai_provider", "provider"], settings: settings)
      ?? byokOpenAIConfig()
  }

  /// BYOK OpenAI → vendor endpoint (desktop hybrid escape hatch when daemon JSON is unset).
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

  private static func loadOpenAICompatibleProvider(
    forKeys keys: [String],
    settings: [LocalDaemonSetting]
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
    let model = (json["model"] as? String) ?? "gpt-4o-mini"
    let apiKey =
      (json["api_key"] as? String) ?? (json["key"] as? String) ?? ""
    return ProviderConfig(baseURL: baseURL, model: model, apiKey: apiKey)
  }

  // MARK: HTTP helpers

  private static func completionsURL(config: ProviderConfig) throws -> URL {
    let trimmed = config.baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
    let base = trimmed.hasSuffix("/") ? String(trimmed.dropLast()) : trimmed
    guard let url = URL(string: "\(base)/chat/completions") else {
      throw ClientError.invalidSettings
    }
    return url
  }

  private static func postJSON(url: URL, body: [String: Any], apiKey: String, timeout: TimeInterval) async throws
    -> [String: Any]
  {
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    if !apiKey.isEmpty {
      request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
    }
    request.timeoutInterval = timeout
    request.httpBody = try JSONSerialization.data(withJSONObject: body)

    let (data, response) = try await URLSession.shared.data(for: request)
    guard let http = response as? HTTPURLResponse else {
      throw ClientError.invalidResponse
    }
    guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      throw ClientError.invalidResponse
    }
    guard (200..<300).contains(http.statusCode) else {
      let body = String(data: data.prefix(512), encoding: .utf8) ?? ""
      throw ClientError.httpFailure(status: http.statusCode, body: body)
    }
    return json
  }

  // MARK: Chat (no tools)

  static func chatCompletionText(
    config: ProviderConfig,
    systemPrompt: String,
    userText: String,
    jsonMode: Bool,
    timeout: TimeInterval = 300
  ) async throws -> String {
    let content: [[String: Any]] = [
      ["type": "text", "text": userText]
    ]
    let messages: [[String: Any]] = [
      ["role": "system", "content": systemPrompt],
      ["role": "user", "content": content],
    ]
    return try await chatCompletionRaw(
      config: config, messages: messages, jsonMode: jsonMode, tools: nil, toolChoice: nil, timeout: timeout)
  }

  static func chatCompletionMultimodalJPEG(
    config: ProviderConfig,
    systemPrompt: String,
    userText: String,
    jpegData: Data,
    jsonMode: Bool,
    timeout: TimeInterval = 300
  ) async throws -> String {
    let b64 = jpegData.base64EncodedString()
    let dataUrl = "data:image/jpeg;base64,\(b64)"
    let content: [[String: Any]] = [
      ["type": "text", "text": userText],
      ["type": "image_url", "image_url": ["url": dataUrl]],
    ]
    let messages: [[String: Any]] = [
      ["role": "system", "content": systemPrompt],
      ["role": "user", "content": content],
    ]
    return try await chatCompletionRaw(
      config: config, messages: messages, jsonMode: jsonMode, tools: nil, toolChoice: nil, timeout: timeout)
  }

  private static func chatCompletionRaw(
    config: ProviderConfig,
    messages: [[String: Any]],
    jsonMode: Bool,
    tools: [[String: Any]]?,
    toolChoice: Any?,
    timeout: TimeInterval
  ) async throws -> String {
    var body: [String: Any] = [
      "model": config.model,
      "messages": messages,
      "temperature": 0.4,
    ]
    if jsonMode {
      body["response_format"] = ["type": "json_object"]
    }
    if let tools {
      body["tools"] = tools
    }
    if let toolChoice {
      body["tool_choice"] = toolChoice
    }

    let json = try await postJSON(url: try completionsURL(config: config), body: body, apiKey: config.apiKey, timeout: timeout)
    return try extractAssistantText(from: json)
  }

  private static func extractAssistantText(from json: [String: Any]) throws -> String {
    guard let choices = json["choices"] as? [[String: Any]],
      let first = choices.first,
      let message = first["message"] as? [String: Any]
    else {
      throw ClientError.invalidResponse
    }
    if let toolCalls = message["tool_calls"] as? [[String: Any]], !toolCalls.isEmpty {
      throw ClientError.invalidResponse
    }
    if let str = message["content"] as? String {
      return str
    }
    if let parts = message["content"] as? [[String: Any]] {
      // Some providers use array-of-parts content
      let texts = parts.compactMap { $0["text"] as? String }
      return texts.joined(separator: "\n")
    }
    throw ClientError.invalidResponse
  }

  // MARK: Tool loop (GeminiImageToolRequest → OpenAI chat)

  /// One round of a tool-calling dialog (caller appends turns between rounds).
  static func performGeminiCompatibleToolRound(
    config: ProviderConfig,
    systemPrompt: String,
    contents: [GeminiImageToolRequest.Content],
    tools: [GeminiTool],
    forceToolCall: Bool,
    allowVisionInlineJPEG: Bool,
    timeout: TimeInterval = 300
  ) async throws -> ToolChatResult {
    let messages = try openAIMessages(from: contents, allowVisionInlineJPEG: allowVisionInlineJPEG)
    let openAITools = openAITools(from: tools)

    var toolChoice: Any = "auto"
    if forceToolCall {
      toolChoice = "required"
    }

    var body: [String: Any] = [
      "model": config.model,
      "messages": [["role": "system", "content": systemPrompt]] + messages,
      "tools": openAITools,
      "tool_choice": toolChoice,
      "temperature": 0.4,
    ]

    let json = try await postJSON(url: try completionsURL(config: config), body: body, apiKey: config.apiKey, timeout: timeout)
    return try parseToolChatResult(from: json)
  }

  private static func parseToolChatResult(from json: [String: Any]) throws -> ToolChatResult {
    guard let choices = json["choices"] as? [[String: Any]],
      let first = choices.first,
      let message = first["message"] as? [String: Any]
    else {
      throw ClientError.invalidResponse
    }

    var toolCalls: [ToolCall] = []
    if let rawCalls = message["tool_calls"] as? [[String: Any]] {
      for tc in rawCalls {
        guard let fn = tc["function"] as? [String: Any],
          let name = fn["name"] as? String
        else {
          continue
        }
        let argsStr = fn["arguments"] as? String ?? "{}"
        let argsAny =
          (try? JSONSerialization.jsonObject(with: Data(argsStr.utf8))) as? [String: Any] ?? [:]
        toolCalls.append(
          ToolCall(name: name, arguments: argsAny, thoughtSignature: nil))
      }
    }

    var textResponse = ""
    if let content = message["content"] as? String {
      textResponse = content
    } else if let parts = message["content"] as? [[String: Any]] {
      textResponse = parts.compactMap { $0["text"] as? String }.joined(separator: "\n")
    }

    return ToolChatResult(
      text: textResponse,
      toolCalls: toolCalls,
      requiresToolExecution: !toolCalls.isEmpty
    )
  }

  // MARK: OpenAI message building

  private static func openAIMessages(
    from contents: [GeminiImageToolRequest.Content],
    allowVisionInlineJPEG: Bool
  ) throws -> [[String: Any]] {
    var out: [[String: Any]] = []
    /// Pair assistant `tool_calls[].id` with subsequent tool result rows (Gemini omits ids).
    var pendingToolCallIds: [String] = []

    for content in contents {
      let role = content.role
      if role == "user" {
        var userParts: [[String: Any]] = []
        var toolResults: [[String: Any]] = []

        for part in content.parts {
          if let fr = part.functionResponse {
            let toolCallId =
              pendingToolCallIds.isEmpty ? "call_hybrid_fallback_\(fr.name)" : pendingToolCallIds.removeFirst()
            toolResults.append([
              "role": "tool",
              "tool_call_id": toolCallId,
              "content": fr.response.result,
            ])
            continue
          }
          if let t = part.text, !t.isEmpty {
            userParts.append(["type": "text", "text": t])
          }
          if let img = part.inlineData, allowVisionInlineJPEG {
            let mime = img.mimeType
            let dataUrl = "data:\(mime);base64,\(img.data)"
            userParts.append(["type": "image_url", "image_url": ["url": dataUrl]])
          }
        }

        if !userParts.isEmpty {
          out.append(["role": "user", "content": userParts])
        }
        for tr in toolResults {
          out.append(tr)
        }
      } else if role == "model" {
        var textAccum = ""
        var oaToolCalls: [[String: Any]] = []

        for part in content.parts {
          if let t = part.text, !t.isEmpty {
            textAccum += t
          }
          if let fc = part.functionCall {
            let id = "call_" + UUID().uuidString.replacingOccurrences(of: "-", with: "")
            pendingToolCallIds.append(id)
            let argData = try JSONSerialization.data(withJSONObject: fc.args, options: [])
            let argStr = String(data: argData, encoding: .utf8) ?? "{}"
            oaToolCalls.append([
              "id": id,
              "type": "function",
              "function": ["name": fc.name, "arguments": argStr],
            ])
          }
        }

        var msg: [String: Any] = ["role": "assistant"]
        if !textAccum.isEmpty {
          msg["content"] = textAccum
        } else if oaToolCalls.isEmpty {
          msg["content"] = ""
        }
        if !oaToolCalls.isEmpty {
          msg["tool_calls"] = oaToolCalls
        }
        out.append(msg)
      } else {
        // Unknown role — skip
      }
    }
    return out
  }

  private static func openAITools(from tools: [GeminiTool]) -> [[String: Any]] {
    tools.flatMap(\.functionDeclarations).compactMap { fd in
      guard let schema = jsonSchema(from: fd.parameters) else { return nil }
      return [
        "type": "function",
        "function": [
          "name": fd.name,
          "description": fd.description,
          "parameters": schema,
        ],
      ]
    }
  }

  private static func jsonSchema(from params: GeminiTool.FunctionDeclaration.Parameters) -> [String: Any]? {
    var properties: [String: Any] = [:]
    for (name, prop) in params.properties {
      if let nested = propJSONSchema(prop) {
        properties[name] = nested
      }
    }
    var schema: [String: Any] = [
      "type": params.type,
      "properties": properties,
      "required": params.required,
    ]
    return schema
  }

  private static func propJSONSchema(_ prop: GeminiTool.FunctionDeclaration.Parameters.Property) -> [String: Any]? {
    if let nested = prop.nestedProperties, let req = prop.nestedRequired {
      var childProps: [String: Any] = [:]
      for (k, v) in nested {
        if let sch = propJSONSchema(v) {
          childProps[k] = sch
        }
      }
      var obj: [String: Any] = [
        "type": "object",
        "properties": childProps,
        "required": req,
      ]
      if let d = prop.description, !d.isEmpty {
        obj["description"] = d
      }
      return obj
    }

    var out: [String: Any] = [
      "type": prop.type
    ]
    if let d = prop.description, !d.isEmpty {
      out["description"] = d
    }
    if let `enum` = prop.`enum` {
      out["enum"] = `enum`
    }
    if let items = prop.items {
      out["items"] = ["type": items.type]
    }
    return out
  }

  // MARK: OCR (on-device) for hybrid without vision_provider

  enum ScreenOCR {
    static func recognizeTextFromJPEG(_ jpegData: Data) async throws -> String {
      try await Task.detached(priority: .userInitiated) {
        try await Self.recognizeTextFromJPEGSync(jpegData)
      }.value
    }

    private static func recognizeTextFromJPEGSync(_ jpegData: Data) async throws -> String {
      try await withCheckedThrowingContinuation { continuation in
        let request = VNRecognizeTextRequest { request, error in
          if let error {
            continuation.resume(throwing: error)
            return
          }
          let observations = (request.results as? [VNRecognizedTextObservation]) ?? []
          let text = observations.compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
          continuation.resume(returning: text)
        }
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true

        let handler = VNImageRequestHandler(data: jpegData, options: [:])
        do {
          try handler.perform([request])
        } catch {
          continuation.resume(throwing: error)
        }
      }
    }
  }
}
