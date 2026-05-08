import Foundation

// MARK: - Thinking Budget Configuration

/// Controls how many tokens Gemini 2.5 spends on internal reasoning.
/// Budget 0 disables thinking (cheapest). Budget -1 = dynamic (model decides).
/// Flash range: 0–24576. Pro range: 128–32768.
struct ThinkingConfig: Encodable {
  let thinkingBudget: Int

  enum CodingKeys: String, CodingKey {
    case thinkingBudget = "thinking_budget"
  }

  /// Minimum thinking budget that disables or minimizes reasoning for a given model.
  /// Flash supports 0 (fully off). Pro requires at least 128.
  static func minimumBudget(for model: String) -> Int {
    model.contains("pro") ? 128 : 0
  }
}

// MARK: - Gemini API Request/Response Types

struct GeminiRequest: Encodable {
  let contents: [Content]
  let systemInstruction: SystemInstruction?
  let generationConfig: GenerationConfig?

  enum CodingKeys: String, CodingKey {
    case contents
    case systemInstruction = "system_instruction"
    case generationConfig = "generation_config"
  }

  struct Content: Encodable {
    let parts: [Part]
  }

  struct Part: Encodable {
    let text: String?
    let inlineData: InlineData?

    enum CodingKeys: String, CodingKey {
      case text
      case inlineData = "inline_data"
    }

    init(text: String) {
      self.text = text
      self.inlineData = nil
    }

    init(mimeType: String, data: String) {
      self.text = nil
      self.inlineData = InlineData(mimeType: mimeType, data: data)
    }
  }

  struct InlineData: Encodable {
    let mimeType: String
    let data: String

    enum CodingKeys: String, CodingKey {
      case mimeType = "mime_type"
      case data
    }
  }

  struct SystemInstruction: Encodable {
    let parts: [TextPart]

    struct TextPart: Encodable {
      let text: String
    }
  }

  struct GenerationConfig: Encodable {
    let responseMimeType: String?
    let responseSchema: ResponseSchema?
    let thinkingConfig: ThinkingConfig?

    enum CodingKeys: String, CodingKey {
      case responseMimeType = "response_mime_type"
      case responseSchema = "response_schema"
      case thinkingConfig = "thinking_config"
    }

    struct ResponseSchema: Encodable {
      let type: String
      let properties: [String: Property]
      let required: [String]

      struct Property: Encodable {
        let type: String
        let `enum`: [String]?
        let description: String?
        let items: Items?
        let nestedProperties: [String: Property]?
        let nestedRequired: [String]?

        enum CodingKeys: String, CodingKey {
          case type
          case `enum`
          case description
          case items
          case nestedProperties = "properties"
          case nestedRequired = "required"
        }

        init(type: String, enum: [String]? = nil, description: String? = nil, items: Items? = nil) {
          self.type = type
          self.enum = `enum`
          self.description = description
          self.items = items
          self.nestedProperties = nil
          self.nestedRequired = nil
        }

        /// Initialize an object property with nested properties
        init(
          type: String, description: String? = nil, properties: [String: Property],
          required: [String]
        ) {
          self.type = type
          self.enum = nil
          self.description = description
          self.items = nil
          self.nestedProperties = properties
          self.nestedRequired = required
        }

        struct Items: Encodable {
          let type: String
          let properties: [String: Property]?
          let required: [String]?
        }
      }
    }
  }
}

struct GeminiResponse: Decodable {
  let candidates: [Candidate]?
  let error: GeminiError?
  let promptFeedback: PromptFeedback?

  struct Candidate: Decodable {
    let content: Content?
    let finishReason: String?

    enum CodingKeys: String, CodingKey {
      case content
      case finishReason = "finish_reason"
    }

    struct Content: Decodable {
      let parts: [Part]?

      struct Part: Decodable {
        let text: String?
      }
    }
  }

  struct PromptFeedback: Decodable {
    let blockReason: String?

    enum CodingKeys: String, CodingKey {
      case blockReason = "block_reason"
    }
  }

  struct GeminiError: Decodable {
    let message: String
  }
}

// MARK: - GeminiClient

/// Low-level client for communicating with the Gemini API via backend proxy.
/// All requests route through the Rust backend (/v1/proxy/gemini/*) which adds
/// the Gemini API key server-side. Auth uses Firebase Bearer token.
actor GeminiClient {
  private let model: String

  /// Backend proxy base URL (from OMI_DESKTOP_API_URL env var)
  private static var proxyBaseURL: String {
    if let cString = getenv("OMI_DESKTOP_API_URL"), let url = String(validatingUTF8: cString), !url.isEmpty {
      return url.hasSuffix("/") ? url : url + "/"
    }
    return "https://api.omi.me/"
  }

  enum GeminiClientError: LocalizedError {
    case missingAPIKey
    case networkError(Error)
    case invalidResponse
    case apiError(String)

    /// The raw API message for internal logging (not shown to user).
    var internalMessage: String? {
      if case .apiError(let msg) = self { return msg }
      return nil
    }

    var errorDescription: String? {
      switch self {
      case .missingAPIKey:
        return "AI features are not configured. Please update the app."
      case .networkError:
        return "Could not reach AI service. Check your internet connection and try again."
      case .invalidResponse:
        return "AI service returned an unexpected response. Please try again."
      case .apiError(let message):
        return Self.userFacingMessage(for: message)
      }
    }

    /// Convert raw API error messages into user-friendly descriptions.
    /// Never expose API keys, auth details, or internal service info to users.
    private static func userFacingMessage(for rawMessage: String) -> String {
      let lower = rawMessage.lowercased()

      if lower.contains("leaked") || lower.contains("api key") || lower.contains("api_key")
        || lower.contains("unauthorized") || lower.contains("permission denied")
        || lower.contains("invalid key") || lower.contains("forbidden")
      {
        return "AI service authentication error. Please update the app to the latest version."
      }
      if lower.contains("quota") || lower.contains("rate limit")
        || lower.contains("resource exhausted")
        || lower.contains("429")
      {
        return "AI service is busy. Please try again in a moment."
      }
      if lower.contains("overloaded") || lower.contains("service unavailable")
        || lower.contains("503")
        || lower.contains("internal error") || lower.contains("500")
      {
        return "AI service is temporarily unavailable. Please try again later."
      }
      if lower.contains("blocked") || lower.contains("safety") {
        return "Content was filtered by the AI safety system."
      }
      // Fallback: generic message that doesn't leak internals
      return "AI service error. Please try again."
    }
  }

  init(apiKey: String? = nil, model: String = ModelQoS.Gemini.proactive) throws {
    // BREAKING CHANGE (issue #5861): apiKey parameter is ignored.
    // All Gemini requests now route through the backend proxy which supplies
    // the key server-side. Defaults to production when OMI_DESKTOP_API_URL is absent
    // so installed test bundles launched from Finder still have AI features.
    guard !Self.proxyBaseURL.isEmpty else {
      throw GeminiClientError.missingAPIKey
    }
    self.model = model
  }

  /// Get Firebase auth header for proxy requests
  private func authHeader() async throws -> String {
    let authService = await MainActor.run { AuthService.shared }
    return try await authService.getAuthHeader()
  }

  /// Build proxy URL for a Gemini model action
  private func proxyURL(action: String) -> URL {
    URL(string: "\(Self.proxyBaseURL)v1/proxy/gemini/models/\(model):\(action)")!
  }


  /// Log the raw API error message for debugging and throw a sanitized error.
  /// The `errorDescription` on GeminiClientError is user-friendly; this log preserves the raw detail.
  private func throwAPIError(_ rawMessage: String) throws -> Never {
    log("GeminiClient: API error (raw): \(rawMessage)")
    throw GeminiClientError.apiError(rawMessage)
  }

  /// Throw a descriptive error based on why the Gemini response has no usable content.
  /// Prefers block reasons from promptFeedback or finishReason over the generic invalidResponse.
  private func throwBlockedOrInvalidResponse(
    blockReason: String?,
    finishReason: String?
  ) throws -> Never {
    if let reason = blockReason {
      throw GeminiClientError.apiError("blocked: \(reason)")
    }
    if let reason = finishReason, reason != "STOP" {
      throw GeminiClientError.apiError("blocked: \(reason)")
    }
    throw GeminiClientError.invalidResponse
  }

  /// Check HTTP status code before attempting JSON decode.
  /// Throws GeminiClientError.apiError for non-2xx responses so the error flows
  /// through isTransientError() and userFacingMessage() instead of crashing JSONDecoder.
  private func checkHTTPStatus(_ response: URLResponse, data: Data) throws {
    guard let httpResponse = response as? HTTPURLResponse else { return }
    let status = httpResponse.statusCode
    guard (200..<300).contains(status) else {
      let body = String(data: data.prefix(512), encoding: .utf8) ?? ""
      throw GeminiClientError.apiError("HTTP \(status): \(body)")
    }
  }

  /// Check if an error is transient and worth retrying
  private func isTransientError(_ error: Error) -> Bool {
    if let geminiError = error as? GeminiClientError {
      switch geminiError {
      case .apiError(let message):
        let lower = message.lowercased()
        return lower.contains("service unavailable")
          || lower.contains("overloaded")
          || lower.contains("resource exhausted")
          || lower.contains("high demand")
          || lower.contains("503")
          || lower.contains("429")
          || lower.contains("internal error")
      case .networkError:
        return true
      case .invalidResponse, .missingAPIKey:
        return false
      }
    }
    // URLSession network errors are transient
    return (error as NSError).domain == NSURLErrorDomain
  }

  /// Sleep with exponential backoff (2s, 8s) and log the retry attempt.
  private func retryBackoff(attempt: Int, error: Error) async {
    let delaySec = [2, 8][min(attempt, 1)]
    log("GeminiClient: transient error, retrying in \(delaySec)s (attempt \(attempt + 2)/3): \(error.localizedDescription)")
    try? await Task.sleep(nanoseconds: UInt64(delaySec) * 1_000_000_000)
  }

  /// Send a request to the Gemini API with an image
  /// Retries up to 2 times for transient errors (3 total attempts).
  /// - Parameters:
  ///   - prompt: Text prompt to send
  ///   - imageData: JPEG image data to analyze
  ///   - systemPrompt: System instructions for the model
  ///   - responseSchema: JSON schema for structured output
  /// - Returns: The text response from the model
  func sendRequest(
    prompt: String,
    imageData: Data,
    systemPrompt: String,
    responseSchema: GeminiRequest.GenerationConfig.ResponseSchema,
    thinkingBudget: Int = 0
  ) async throws -> String {
    let maxRetries = 2
    var lastError: Error?

    for attempt in 0...maxRetries {
      do {
        // Wrap base64 encoding + JSON serialization in autoreleasepool.
        // These create bridged Obj-C objects (NSString, NSData) that accumulate
        // in Swift concurrency's cooperative thread pool without being drained.
        let requestBody: Data = try autoreleasepool {
          let base64Data = imageData.base64EncodedString()

          let request = GeminiRequest(
            contents: [
              GeminiRequest.Content(parts: [
                GeminiRequest.Part(text: prompt),
                GeminiRequest.Part(mimeType: "image/webp", data: base64Data),
              ])
            ],
            systemInstruction: GeminiRequest.SystemInstruction(
              parts: [GeminiRequest.SystemInstruction.TextPart(text: systemPrompt)]
            ),
            generationConfig: GeminiRequest.GenerationConfig(
              responseMimeType: "application/json",
              responseSchema: responseSchema,
              thinkingConfig: ThinkingConfig(thinkingBudget: max(thinkingBudget, ThinkingConfig.minimumBudget(for: model)))
            )
          )

          return try JSONEncoder().encode(request)
        }

        let url = proxyURL(action: "generateContent")
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.setValue(try await authHeader(), forHTTPHeaderField: "Authorization")
        urlRequest.timeoutInterval = 300
        urlRequest.httpBody = requestBody

        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        try checkHTTPStatus(urlResponse, data: data)

        let response = try JSONDecoder().decode(GeminiResponse.self, from: data)

        if let error = response.error {
          try throwAPIError(error.message)
        }

        guard let text = response.candidates?.first?.content?.parts?.first?.text else {
          try throwBlockedOrInvalidResponse(
            blockReason: response.promptFeedback?.blockReason,
            finishReason: response.candidates?.first?.finishReason
          )
        }

        return text
      } catch {
        lastError = error

        // Don't retry non-transient errors (e.g. safety filter / invalidResponse)
        guard attempt < maxRetries && isTransientError(error) else {
          throw error
        }

        // Backoff: 1s after first failure, 2s after second
        await retryBackoff(attempt: attempt, error: error)
      }
    }

    throw lastError!
  }

  /// Send a text-only request to the Gemini API
  /// Retries up to 2 times for transient errors (3 total attempts).
  /// - Parameters:
  ///   - prompt: Text prompt to send
  ///   - systemPrompt: System instructions for the model
  /// - Returns: The text response from the model
  func sendTextRequest(
    prompt: String,
    systemPrompt: String,
    maxRetries: Int = 2,
    timeout: TimeInterval = 300,
    thinkingBudget: Int = 0
  ) async throws -> String {
    var lastError: Error?

    for attempt in 0...maxRetries {
      do {
        let request = GeminiRequest(
          contents: [
            GeminiRequest.Content(parts: [
              GeminiRequest.Part(text: prompt)
            ])
          ],
          systemInstruction: GeminiRequest.SystemInstruction(
            parts: [GeminiRequest.SystemInstruction.TextPart(text: systemPrompt)]
          ),
          generationConfig: GeminiRequest.GenerationConfig(
            responseMimeType: nil,
            responseSchema: nil,
            thinkingConfig: ThinkingConfig(thinkingBudget: max(thinkingBudget, ThinkingConfig.minimumBudget(for: model)))
          )
        )

        let url = proxyURL(action: "generateContent")
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.setValue(try await authHeader(), forHTTPHeaderField: "Authorization")
        urlRequest.timeoutInterval = timeout
        urlRequest.httpBody = try JSONEncoder().encode(request)

        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        try checkHTTPStatus(urlResponse, data: data)

        let response = try JSONDecoder().decode(GeminiResponse.self, from: data)

        if let error = response.error {
          try throwAPIError(error.message)
        }

        guard let text = response.candidates?.first?.content?.parts?.first?.text else {
          try throwBlockedOrInvalidResponse(
            blockReason: response.promptFeedback?.blockReason,
            finishReason: response.candidates?.first?.finishReason
          )
        }

        return text
      } catch {
        lastError = error
        guard attempt < maxRetries && isTransientError(error) else {
          throw error
        }
        await retryBackoff(attempt: attempt, error: error)
      }
    }

    throw lastError!
  }

  /// Send a text-only request with structured JSON output
  /// Retries up to 2 times for transient errors (3 total attempts).
  /// - Parameters:
  ///   - prompt: Text prompt to send
  ///   - systemPrompt: System instructions for the model
  ///   - responseSchema: JSON schema for structured output
  /// - Returns: The text response from the model (JSON)
  func sendRequest(
    prompt: String,
    systemPrompt: String,
    responseSchema: GeminiRequest.GenerationConfig.ResponseSchema,
    thinkingBudget: Int = 0
  ) async throws -> String {
    let maxRetries = 2
    var lastError: Error?

    for attempt in 0...maxRetries {
      do {
        let request = GeminiRequest(
          contents: [
            GeminiRequest.Content(parts: [
              GeminiRequest.Part(text: prompt)
            ])
          ],
          systemInstruction: GeminiRequest.SystemInstruction(
            parts: [GeminiRequest.SystemInstruction.TextPart(text: systemPrompt)]
          ),
          generationConfig: GeminiRequest.GenerationConfig(
            responseMimeType: "application/json",
            responseSchema: responseSchema,
            thinkingConfig: ThinkingConfig(thinkingBudget: max(thinkingBudget, ThinkingConfig.minimumBudget(for: model)))
          )
        )

        let url = proxyURL(action: "generateContent")
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.setValue(try await authHeader(), forHTTPHeaderField: "Authorization")
        urlRequest.timeoutInterval = 300
        urlRequest.httpBody = try JSONEncoder().encode(request)

        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        try checkHTTPStatus(urlResponse, data: data)

        let response = try JSONDecoder().decode(GeminiResponse.self, from: data)

        if let error = response.error {
          try throwAPIError(error.message)
        }

        guard let text = response.candidates?.first?.content?.parts?.first?.text else {
          try throwBlockedOrInvalidResponse(
            blockReason: response.promptFeedback?.blockReason,
            finishReason: response.candidates?.first?.finishReason
          )
        }

        return text
      } catch {
        lastError = error
        guard attempt < maxRetries && isTransientError(error) else {
          throw error
        }
        await retryBackoff(attempt: attempt, error: error)
      }
    }

    throw lastError!
  }

}


// MARK: - Tool Calling Support

/// Wrapper for dynamic JSON values in function arguments
struct AnyCodable: Decodable {
  let value: Any

  init(_ value: Any) {
    self.value = value
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.singleValueContainer()

    if let string = try? container.decode(String.self) {
      value = string
    } else if let int = try? container.decode(Int.self) {
      value = int
    } else if let double = try? container.decode(Double.self) {
      value = double
    } else if let bool = try? container.decode(Bool.self) {
      value = bool
    } else if let array = try? container.decode([AnyCodable].self) {
      value = array.map { $0.value }
    } else if let dict = try? container.decode([String: AnyCodable].self) {
      value = dict.mapValues { $0.value }
    } else {
      value = NSNull()
    }
  }

  var stringValue: String? { value as? String }
  var intValue: Int? { value as? Int }
  var doubleValue: Double? { value as? Double }
  var boolValue: Bool? { value as? Bool }
}

/// Tool definition for Gemini function calling
struct GeminiTool: Encodable {
  let functionDeclarations: [FunctionDeclaration]

  enum CodingKeys: String, CodingKey {
    case functionDeclarations = "function_declarations"
  }

  struct FunctionDeclaration: Encodable {
    let name: String
    let description: String
    let parameters: Parameters

    struct Parameters: Encodable {
      let type: String
      let properties: [String: Property]
      let required: [String]

      struct Property: Encodable {
        let type: String
        let description: String
        let `enum`: [String]?
        let items: Items?

        init(type: String, description: String, enumValues: [String]? = nil, items: Items? = nil) {
          self.type = type
          self.description = description
          self.enum = enumValues
          self.items = items
        }

        struct Items: Encodable {
          let type: String
        }
      }
    }
  }
}


/// Result of a tool-enabled chat (may include tool calls)
struct ToolChatResult {
  let text: String
  let toolCalls: [ToolCall]
  let requiresToolExecution: Bool
}

/// A function call from the model
struct ToolCall {
  let name: String
  let arguments: [String: Any]
  let thoughtSignature: String?
}

// MARK: - Image + Tool Calling Request

/// Request type combining image analysis with tool calling
struct GeminiImageToolRequest: Encodable {
  let contents: [Content]
  let systemInstruction: SystemInstruction?
  let generationConfig: GenerationConfig?
  let tools: [GeminiTool]?
  let toolConfig: ToolConfig?

  enum CodingKeys: String, CodingKey {
    case contents
    case systemInstruction = "system_instruction"
    case generationConfig = "generation_config"
    case tools
    case toolConfig = "tool_config"
  }

  struct GenerationConfig: Encodable {
    let thinkingConfig: ThinkingConfig?

    enum CodingKeys: String, CodingKey {
      case thinkingConfig = "thinking_config"
    }
  }

  struct Content: Encodable {
    let role: String
    let parts: [Part]
  }

  struct Part: Encodable {
    let text: String?
    let inlineData: InlineData?
    let functionCall: FunctionCallPart?
    let functionResponse: FunctionResponsePart?
    let thoughtSignature: String?

    enum CodingKeys: String, CodingKey {
      case text
      case inlineData = "inline_data"
      case functionCall = "functionCall"
      case functionResponse = "functionResponse"
      case thoughtSignature = "thoughtSignature"
    }

    init(text: String) {
      self.text = text
      self.inlineData = nil
      self.functionCall = nil
      self.functionResponse = nil
      self.thoughtSignature = nil
    }

    init(mimeType: String, data: String) {
      self.text = nil
      self.inlineData = InlineData(mimeType: mimeType, data: data)
      self.functionCall = nil
      self.functionResponse = nil
      self.thoughtSignature = nil
    }

    init(functionCall: FunctionCallPart, thoughtSignature: String? = nil) {
      self.text = nil
      self.inlineData = nil
      self.functionCall = functionCall
      self.functionResponse = nil
      self.thoughtSignature = thoughtSignature
    }

    init(functionResponse: FunctionResponsePart) {
      self.text = nil
      self.inlineData = nil
      self.functionCall = nil
      self.functionResponse = functionResponse
      self.thoughtSignature = nil
    }
  }

  struct InlineData: Encodable {
    let mimeType: String
    let data: String

    enum CodingKeys: String, CodingKey {
      case mimeType = "mime_type"
      case data
    }
  }

  struct FunctionCallPart: Encodable {
    let name: String
    let args: [String: String]
  }

  struct FunctionResponsePart: Encodable {
    let name: String
    let response: ResponseContent

    struct ResponseContent: Encodable {
      let result: String
    }
  }

  struct SystemInstruction: Encodable {
    let parts: [TextPart]

    struct TextPart: Encodable {
      let text: String
    }
  }

  struct ToolConfig: Encodable {
    let functionCallingConfig: FunctionCallingConfig

    enum CodingKeys: String, CodingKey {
      case functionCallingConfig = "function_calling_config"
    }

    struct FunctionCallingConfig: Encodable {
      let mode: String  // "ANY", "AUTO", "NONE"
    }
  }
}

// MARK: - GeminiClient Image + Tool Extensions

extension GeminiClient {

  /// Send image + tool loop request: takes pre-built contents array for multi-turn tool calling.
  /// Retries up to 2 times for transient errors.
  /// - Parameter thinkingBudget: Token budget for model reasoning. Tool-calling features that need
  ///   multi-step reasoning (e.g. InsightAssistant SQL generation, TaskAssistant screen analysis)
  ///   should pass a reasonable budget (e.g. 1024). Default 0 = minimal thinking.
  func sendImageToolLoop(
    contents: [GeminiImageToolRequest.Content],
    systemPrompt: String,
    tools: [GeminiTool],
    forceToolCall: Bool = false,
    thinkingBudget: Int = 0
  ) async throws -> ToolChatResult {
    let maxRetries = 2
    var lastError: Error?

    for attempt in 0...maxRetries {
      do {
        // Wrap JSON serialization in autoreleasepool (contents may include
        // large base64 image data that creates bridged Obj-C intermediaries).
        let requestBody: Data = try autoreleasepool {
          let toolConfig =
            forceToolCall
            ? GeminiImageToolRequest.ToolConfig(
              functionCallingConfig: .init(mode: "ANY")
            ) : nil

          let request = GeminiImageToolRequest(
            contents: contents,
            systemInstruction: GeminiImageToolRequest.SystemInstruction(
              parts: [.init(text: systemPrompt)]
            ),
            generationConfig: GeminiImageToolRequest.GenerationConfig(
              thinkingConfig: ThinkingConfig(thinkingBudget: max(thinkingBudget, ThinkingConfig.minimumBudget(for: model)))
            ),
            tools: tools,
            toolConfig: toolConfig
          )

          return try JSONEncoder().encode(request)
        }

        let url = proxyURL(action: "generateContent")
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.setValue(try await authHeader(), forHTTPHeaderField: "Authorization")
        urlRequest.timeoutInterval = 300
        urlRequest.httpBody = requestBody

        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        try checkHTTPStatus(urlResponse, data: data)

        let response = try JSONDecoder().decode(GeminiToolResponse.self, from: data)

        if let error = response.error {
          try throwAPIError(error.message)
        }

        guard let candidate = response.candidates?.first,
          let parts = candidate.content?.parts
        else {
          try throwBlockedOrInvalidResponse(
            blockReason: response.promptFeedback?.blockReason,
            finishReason: response.candidates?.first?.finishReason
          )
        }

        var toolCalls: [ToolCall] = []
        var textResponse = ""

        for part in parts {
          if let functionCall = part.functionCall {
            let args = functionCall.args?.mapValues { $0.value } ?? [:]
            toolCalls.append(
              ToolCall(
                name: functionCall.name, arguments: args, thoughtSignature: part.thoughtSignature))
          }
          if let text = part.text {
            textResponse += text
          }
        }

        return ToolChatResult(
          text: textResponse,
          toolCalls: toolCalls,
          requiresToolExecution: !toolCalls.isEmpty
        )
      } catch {
        lastError = error
        guard attempt < maxRetries && isTransientError(error) else {
          throw error
        }
        await retryBackoff(attempt: attempt, error: error)
      }
    }

    throw lastError!
  }

}

/// Response type for tool-enabled requests
struct GeminiToolResponse: Decodable {
  let candidates: [Candidate]?
  let error: GeminiError?
  let promptFeedback: PromptFeedback?

  struct Candidate: Decodable {
    let content: Content?
    let finishReason: String?

    enum CodingKeys: String, CodingKey {
      case content
      case finishReason = "finish_reason"
    }

    struct Content: Decodable {
      let parts: [Part]?

      struct Part: Decodable {
        let text: String?
        let functionCall: FunctionCall?
        let thoughtSignature: String?

        enum CodingKeys: String, CodingKey {
          case text
          case functionCall = "functionCall"
          case thoughtSignature = "thoughtSignature"
        }
      }
    }
  }

  struct PromptFeedback: Decodable {
    let blockReason: String?

    enum CodingKeys: String, CodingKey {
      case blockReason = "block_reason"
    }
  }

  struct FunctionCall: Decodable {
    let name: String
    let args: [String: AnyCodable]?
  }

  struct GeminiError: Decodable {
    let message: String
  }
}
