import Foundation

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
        let responseMimeType: String
        let responseSchema: ResponseSchema?

        enum CodingKeys: String, CodingKey {
            case responseMimeType = "response_mime_type"
            case responseSchema = "response_schema"
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
                init(type: String, description: String? = nil, properties: [String: Property], required: [String]) {
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

    struct Candidate: Decodable {
        let content: Content?

        struct Content: Decodable {
            let parts: [Part]?

            struct Part: Decodable {
                let text: String?
            }
        }
    }

    struct GeminiError: Decodable {
        let message: String
    }
}

// MARK: - GeminiClient

/// Low-level client for communicating with the Gemini API
actor GeminiClient {
    private let apiKey: String
    private let model: String

    enum GeminiClientError: LocalizedError {
        case missingAPIKey
        case networkError(Error)
        case invalidResponse
        case apiError(String)

        var errorDescription: String? {
            switch self {
            case .missingAPIKey:
                return "GEMINI_API_KEY not set"
            case .networkError(let error):
                return "Network error: \(error.localizedDescription)"
            case .invalidResponse:
                return "Invalid response from Gemini API"
            case .apiError(let message):
                return "API error: \(message)"
            }
        }
    }

    init(apiKey: String? = nil, model: String = "gemini-3-flash-preview") throws {
        guard let key = apiKey ?? ProcessInfo.processInfo.environment["GEMINI_API_KEY"] else {
            throw GeminiClientError.missingAPIKey
        }
        self.apiKey = key
        self.model = model
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
        responseSchema: GeminiRequest.GenerationConfig.ResponseSchema
    ) async throws -> String {
        let maxRetries = 2
        var lastError: Error?

        for attempt in 0...maxRetries {
            do {
                let base64Data = imageData.base64EncodedString()

                let request = GeminiRequest(
                    contents: [
                        GeminiRequest.Content(parts: [
                            GeminiRequest.Part(text: prompt),
                            GeminiRequest.Part(mimeType: "image/jpeg", data: base64Data)
                        ])
                    ],
                    systemInstruction: GeminiRequest.SystemInstruction(
                        parts: [GeminiRequest.SystemInstruction.TextPart(text: systemPrompt)]
                    ),
                    generationConfig: GeminiRequest.GenerationConfig(
                        responseMimeType: "application/json",
                        responseSchema: responseSchema
                    )
                )

                let url = URL(string: "https://generativelanguage.googleapis.com/v1beta/models/\(model):generateContent?key=\(apiKey)")!
                var urlRequest = URLRequest(url: url)
                urlRequest.httpMethod = "POST"
                urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
                urlRequest.timeoutInterval = 300
                urlRequest.httpBody = try JSONEncoder().encode(request)

                let (data, _) = try await URLSession.shared.data(for: urlRequest)

                let response = try JSONDecoder().decode(GeminiResponse.self, from: data)

                if let error = response.error {
                    throw GeminiClientError.apiError(error.message)
                }

                guard let text = response.candidates?.first?.content?.parts?.first?.text else {
                    throw GeminiClientError.invalidResponse
                }

                return text
            } catch {
                lastError = error

                // Don't retry non-transient errors (e.g. safety filter / invalidResponse)
                guard attempt < maxRetries && isTransientError(error) else {
                    throw error
                }

                // Backoff: 1s after first failure, 2s after second
                let backoffSeconds = UInt64(attempt + 1)
                try? await Task.sleep(nanoseconds: backoffSeconds * 1_000_000_000)
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
        systemPrompt: String
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
                    generationConfig: nil
                )

                let url = URL(string: "https://generativelanguage.googleapis.com/v1beta/models/\(model):generateContent?key=\(apiKey)")!
                var urlRequest = URLRequest(url: url)
                urlRequest.httpMethod = "POST"
                urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
                urlRequest.timeoutInterval = 300
                urlRequest.httpBody = try JSONEncoder().encode(request)

                let (data, _) = try await URLSession.shared.data(for: urlRequest)

                let response = try JSONDecoder().decode(GeminiResponse.self, from: data)

                if let error = response.error {
                    throw GeminiClientError.apiError(error.message)
                }

                guard let text = response.candidates?.first?.content?.parts?.first?.text else {
                    throw GeminiClientError.invalidResponse
                }

                return text
            } catch {
                lastError = error
                guard attempt < maxRetries && isTransientError(error) else {
                    throw error
                }
                let backoffSeconds = UInt64(attempt + 1)
                try? await Task.sleep(nanoseconds: backoffSeconds * 1_000_000_000)
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
        responseSchema: GeminiRequest.GenerationConfig.ResponseSchema
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
                        responseSchema: responseSchema
                    )
                )

                let url = URL(string: "https://generativelanguage.googleapis.com/v1beta/models/\(model):generateContent?key=\(apiKey)")!
                var urlRequest = URLRequest(url: url)
                urlRequest.httpMethod = "POST"
                urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
                urlRequest.timeoutInterval = 300
                urlRequest.httpBody = try JSONEncoder().encode(request)

                let (data, _) = try await URLSession.shared.data(for: urlRequest)

                let response = try JSONDecoder().decode(GeminiResponse.self, from: data)

                if let error = response.error {
                    throw GeminiClientError.apiError(error.message)
                }

                guard let text = response.candidates?.first?.content?.parts?.first?.text else {
                    throw GeminiClientError.invalidResponse
                }

                return text
            } catch {
                lastError = error
                guard attempt < maxRetries && isTransientError(error) else {
                    throw error
                }
                let backoffSeconds = UInt64(attempt + 1)
                try? await Task.sleep(nanoseconds: backoffSeconds * 1_000_000_000)
            }
        }

        throw lastError!
    }

    /// Send a multi-turn chat request with streaming response
    /// - Parameters:
    ///   - messages: Array of chat messages (role: user/model, text)
    ///   - systemPrompt: System instructions for the model
    ///   - onChunk: Callback for each text chunk received
    /// - Returns: The complete text response
    func sendChatStreamRequest(
        messages: [ChatMessage],
        systemPrompt: String,
        onChunk: @escaping (String) -> Void
    ) async throws -> String {
        // Build contents from chat messages
        let contents = messages.map { message in
            GeminiChatRequest.Content(
                role: message.role,
                parts: [GeminiChatRequest.Part(text: message.text)]
            )
        }

        let request = GeminiChatRequest(
            contents: contents,
            systemInstruction: GeminiChatRequest.SystemInstruction(
                parts: [GeminiChatRequest.SystemInstruction.TextPart(text: systemPrompt)]
            ),
            generationConfig: GeminiChatRequest.GenerationConfig(
                temperature: 0.7,
                maxOutputTokens: 8192
            )
        )

        // Use streamGenerateContent endpoint for streaming
        let url = URL(string: "https://generativelanguage.googleapis.com/v1beta/models/\(model):streamGenerateContent?alt=sse&key=\(apiKey)")!
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.timeoutInterval = 300
        urlRequest.httpBody = try JSONEncoder().encode(request)

        var fullText = ""

        // Use URLSession bytes for streaming
        let (bytes, response) = try await URLSession.shared.bytes(for: urlRequest)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw GeminiClientError.invalidResponse
        }

        if httpResponse.statusCode != 200 {
            throw GeminiClientError.apiError("HTTP \(httpResponse.statusCode)")
        }

        // Parse SSE stream
        for try await line in bytes.lines {
            // SSE format: "data: {json}"
            if line.hasPrefix("data: ") {
                let jsonString = String(line.dropFirst(6))
                if let data = jsonString.data(using: .utf8) {
                    if let chunk = try? JSONDecoder().decode(GeminiStreamChunk.self, from: data) {
                        if let text = chunk.candidates?.first?.content?.parts?.first?.text {
                            fullText += text
                            onChunk(text)
                        }
                    }
                }
            }
        }

        return fullText
    }

    /// Chat message for multi-turn conversation
    struct ChatMessage {
        let role: String  // "user" or "model"
        let text: String
    }
}

// MARK: - Gemini Chat Request (multi-turn with roles)

struct GeminiChatRequest: Encodable {
    let contents: [Content]
    let systemInstruction: SystemInstruction?
    let generationConfig: GenerationConfig?

    enum CodingKeys: String, CodingKey {
        case contents
        case systemInstruction = "system_instruction"
        case generationConfig = "generation_config"
    }

    struct Content: Encodable {
        let role: String  // "user" or "model"
        let parts: [Part]
    }

    struct Part: Encodable {
        let text: String
    }

    struct SystemInstruction: Encodable {
        let parts: [TextPart]

        struct TextPart: Encodable {
            let text: String
        }
    }

    struct GenerationConfig: Encodable {
        let temperature: Double?
        let maxOutputTokens: Int?

        enum CodingKeys: String, CodingKey {
            case temperature
            case maxOutputTokens = "max_output_tokens"
        }
    }
}

// MARK: - Gemini Stream Chunk Response

struct GeminiStreamChunk: Decodable {
    let candidates: [Candidate]?

    struct Candidate: Decodable {
        let content: Content?

        struct Content: Decodable {
            let parts: [Part]?

            struct Part: Decodable {
                let text: String?
                let functionCall: FunctionCall?

                enum CodingKeys: String, CodingKey {
                    case text
                    case functionCall = "functionCall"
                }
            }
        }
    }

    struct FunctionCall: Decodable {
        let name: String
        let args: [String: AnyCodable]?
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

/// Chat request with tools
struct GeminiToolChatRequest: Encodable {
    let contents: [Content]
    let systemInstruction: SystemInstruction?
    let generationConfig: GenerationConfig?
    let tools: [GeminiTool]?

    enum CodingKeys: String, CodingKey {
        case contents
        case systemInstruction = "system_instruction"
        case generationConfig = "generation_config"
        case tools
    }

    struct Content: Encodable {
        let role: String
        let parts: [Part]
    }

    struct Part: Encodable {
        let text: String?
        let functionCall: FunctionCallPart?
        let functionResponse: FunctionResponsePart?
        let thoughtSignature: String?

        enum CodingKeys: String, CodingKey {
            case text
            case functionCall = "functionCall"
            case functionResponse = "functionResponse"
            case thoughtSignature = "thought_signature"
        }

        init(text: String) {
            self.text = text
            self.functionCall = nil
            self.functionResponse = nil
            self.thoughtSignature = nil
        }

        init(functionResponse: FunctionResponsePart) {
            self.text = nil
            self.functionCall = nil
            self.functionResponse = functionResponse
            self.thoughtSignature = nil
        }

        init(functionCall: FunctionCallPart, thoughtSignature: String? = nil) {
            self.text = nil
            self.functionCall = functionCall
            self.functionResponse = nil
            self.thoughtSignature = thoughtSignature
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

    struct GenerationConfig: Encodable {
        let temperature: Double?
        let maxOutputTokens: Int?

        enum CodingKeys: String, CodingKey {
            case temperature
            case maxOutputTokens = "max_output_tokens"
        }
    }
}

/// Result of a tool-enabled chat (may include tool calls)
struct ToolChatResult {
    let text: String
    let toolCalls: [ToolCall]
    let requiresToolExecution: Bool
    /// Accumulated conversation contents for multi-turn tool loops
    var contents: [GeminiToolChatRequest.Content]?
}

/// A function call from the model
struct ToolCall {
    let name: String
    let arguments: [String: Any]
    let thoughtSignature: String?
}

// MARK: - GeminiClient Tool Extensions

extension GeminiClient {

    /// Available chat tools
    static let chatTools: [GeminiTool] = [
        GeminiTool(functionDeclarations: [
            // Execute SQL on local omi.db
            GeminiTool.FunctionDeclaration(
                name: "execute_sql",
                description: "Execute a SQL query on the local omi.db database. Supports SELECT, INSERT, UPDATE, DELETE. Use this for any structured data lookup — app usage, screenshots, tasks, conversations, time-based queries, aggregations, etc. The system prompt contains the full database schema.",
                parameters: GeminiTool.FunctionDeclaration.Parameters(
                    type: "object",
                    properties: [
                        "query": .init(type: "string", description: "SQL query to execute. SELECT queries auto-limit to 200 rows. UPDATE/DELETE require WHERE clause. DROP/ALTER/CREATE are blocked.")
                    ],
                    required: ["query"]
                )
            ),
            // Semantic vector search
            GeminiTool.FunctionDeclaration(
                name: "semantic_search",
                description: "Search screen history using semantic similarity (vector embeddings). Use this for fuzzy conceptual queries where exact keywords won't work — e.g. 'reading about machine learning', 'working on design mockups', 'chatting with friends'. Returns screenshots ranked by semantic similarity.",
                parameters: GeminiTool.FunctionDeclaration.Parameters(
                    type: "object",
                    properties: [
                        "query": .init(type: "string", description: "Natural language description of what to search for."),
                        "days": .init(type: "integer", description: "Search the last N days (default: 7). Use 1 for today only."),
                        "app_filter": .init(type: "string", description: "Optional: filter by app name (e.g., 'Google Chrome', 'Cursor', 'Slack')")
                    ],
                    required: ["query"]
                )
            )
        ])
    ]

    /// Send a chat request with tool support (non-streaming)
    func sendToolChatRequest(
        messages: [ChatMessage],
        systemPrompt: String,
        tools: [GeminiTool]? = nil
    ) async throws -> ToolChatResult {
        // Build contents from chat messages
        let contents = messages.map { message in
            GeminiToolChatRequest.Content(
                role: message.role,
                parts: [GeminiToolChatRequest.Part(text: message.text)]
            )
        }

        let request = GeminiToolChatRequest(
            contents: contents,
            systemInstruction: GeminiToolChatRequest.SystemInstruction(
                parts: [GeminiToolChatRequest.SystemInstruction.TextPart(text: systemPrompt)]
            ),
            generationConfig: GeminiToolChatRequest.GenerationConfig(
                temperature: 0.7,
                maxOutputTokens: 8192
            ),
            tools: tools ?? Self.chatTools
        )

        let url = URL(string: "https://generativelanguage.googleapis.com/v1beta/models/\(model):generateContent?key=\(apiKey)")!
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.timeoutInterval = 300
        urlRequest.httpBody = try JSONEncoder().encode(request)

        let (data, _) = try await URLSession.shared.data(for: urlRequest)

        // Parse response
        let response = try JSONDecoder().decode(GeminiToolResponse.self, from: data)

        if let error = response.error {
            throw GeminiClientError.apiError(error.message)
        }

        guard let candidate = response.candidates?.first,
              let parts = candidate.content?.parts else {
            throw GeminiClientError.invalidResponse
        }

        // Check for function calls
        var toolCalls: [ToolCall] = []
        var textResponse = ""

        for part in parts {
            if let functionCall = part.functionCall {
                let args = functionCall.args?.mapValues { $0.value } ?? [:]
                toolCalls.append(ToolCall(name: functionCall.name, arguments: args, thoughtSignature: part.thoughtSignature))
            }
            if let text = part.text {
                textResponse += text
            }
        }

        return ToolChatResult(
            text: textResponse,
            toolCalls: toolCalls,
            requiresToolExecution: !toolCalls.isEmpty,
            contents: contents
        )
    }

    /// Continue a conversation after executing tools
    /// Returns ToolChatResult so the caller can check if more tool calls are needed (multi-turn loop)
    func continueWithToolResults(
        previousContents: [GeminiToolChatRequest.Content],
        toolCalls: [ToolCall],
        toolResults: [String: String],
        systemPrompt: String,
        tools: [GeminiTool]? = nil
    ) async throws -> ToolChatResult {
        var contents = previousContents

        // Add the model's function call as a model turn
        var functionCallParts: [GeminiToolChatRequest.Part] = []
        for call in toolCalls {
            functionCallParts.append(GeminiToolChatRequest.Part(
                functionCall: GeminiToolChatRequest.FunctionCallPart(
                    name: call.name,
                    args: call.arguments.mapValues { "\($0)" }
                ),
                thoughtSignature: call.thoughtSignature
            ))
        }
        contents.append(GeminiToolChatRequest.Content(role: "model", parts: functionCallParts))

        // Add function responses
        for call in toolCalls {
            let result = toolResults[call.name] ?? "No result"
            contents.append(GeminiToolChatRequest.Content(
                role: "function",
                parts: [GeminiToolChatRequest.Part(
                    functionResponse: GeminiToolChatRequest.FunctionResponsePart(
                        name: call.name,
                        response: .init(result: result)
                    )
                )]
            ))
        }

        let request = GeminiToolChatRequest(
            contents: contents,
            systemInstruction: GeminiToolChatRequest.SystemInstruction(
                parts: [GeminiToolChatRequest.SystemInstruction.TextPart(text: systemPrompt)]
            ),
            generationConfig: GeminiToolChatRequest.GenerationConfig(
                temperature: 0.7,
                maxOutputTokens: 8192
            ),
            tools: tools
        )

        let url = URL(string: "https://generativelanguage.googleapis.com/v1beta/models/\(model):generateContent?key=\(apiKey)")!
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.timeoutInterval = 300
        urlRequest.httpBody = try JSONEncoder().encode(request)

        let (data, _) = try await URLSession.shared.data(for: urlRequest)

        let response = try JSONDecoder().decode(GeminiToolResponse.self, from: data)

        if let error = response.error {
            throw GeminiClientError.apiError(error.message)
        }

        guard let candidate = response.candidates?.first,
              let parts = candidate.content?.parts else {
            throw GeminiClientError.invalidResponse
        }

        // Check for more function calls or text
        var newToolCalls: [ToolCall] = []
        var textResponse = ""

        for part in parts {
            if let functionCall = part.functionCall {
                let args = functionCall.args?.mapValues { $0.value } ?? [:]
                newToolCalls.append(ToolCall(name: functionCall.name, arguments: args, thoughtSignature: part.thoughtSignature))
            }
            if let text = part.text {
                textResponse += text
            }
        }

        return ToolChatResult(
            text: textResponse,
            toolCalls: newToolCalls,
            requiresToolExecution: !newToolCalls.isEmpty,
            contents: contents
        )
    }
}

// MARK: - Image + Tool Calling Request

/// Request type combining image analysis with tool calling
struct GeminiImageToolRequest: Encodable {
    let contents: [Content]
    let systemInstruction: SystemInstruction?
    let tools: [GeminiTool]?
    let toolConfig: ToolConfig?

    enum CodingKeys: String, CodingKey {
        case contents
        case systemInstruction = "system_instruction"
        case tools
        case toolConfig = "tool_config"
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

    /// Send image + text + tools, returns the model's function call
    /// Retries up to 2 times for transient errors.
    func sendImageToolRequest(
        prompt: String,
        imageData: Data,
        systemPrompt: String,
        tools: [GeminiTool],
        forceToolCall: Bool = true
    ) async throws -> ToolChatResult {
        let maxRetries = 2
        var lastError: Error?

        for attempt in 0...maxRetries {
            do {
                let base64Data = imageData.base64EncodedString()

                let toolConfig = forceToolCall ? GeminiImageToolRequest.ToolConfig(
                    functionCallingConfig: .init(mode: "ANY")
                ) : nil

                let request = GeminiImageToolRequest(
                    contents: [
                        GeminiImageToolRequest.Content(
                            role: "user",
                            parts: [
                                GeminiImageToolRequest.Part(text: prompt),
                                GeminiImageToolRequest.Part(mimeType: "image/jpeg", data: base64Data)
                            ]
                        )
                    ],
                    systemInstruction: GeminiImageToolRequest.SystemInstruction(
                        parts: [.init(text: systemPrompt)]
                    ),
                    tools: tools,
                    toolConfig: toolConfig
                )

                let url = URL(string: "https://generativelanguage.googleapis.com/v1beta/models/\(model):generateContent?key=\(apiKey)")!
                var urlRequest = URLRequest(url: url)
                urlRequest.httpMethod = "POST"
                urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
                urlRequest.timeoutInterval = 300
                urlRequest.httpBody = try JSONEncoder().encode(request)

                let (data, _) = try await URLSession.shared.data(for: urlRequest)

                let response = try JSONDecoder().decode(GeminiToolResponse.self, from: data)

                if let error = response.error {
                    throw GeminiClientError.apiError(error.message)
                }

                guard let candidate = response.candidates?.first,
                      let parts = candidate.content?.parts else {
                    throw GeminiClientError.invalidResponse
                }

                var toolCalls: [ToolCall] = []
                var textResponse = ""

                for part in parts {
                    if let functionCall = part.functionCall {
                        let args = functionCall.args?.mapValues { $0.value } ?? [:]
                        toolCalls.append(ToolCall(name: functionCall.name, arguments: args, thoughtSignature: part.thoughtSignature))
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
                let backoffSeconds = UInt64(attempt + 1)
                try? await Task.sleep(nanoseconds: backoffSeconds * 1_000_000_000)
            }
        }

        throw lastError!
    }

    /// Send image + tool loop request: takes pre-built contents array for multi-turn tool calling.
    /// Retries up to 2 times for transient errors.
    func sendImageToolLoop(
        contents: [GeminiImageToolRequest.Content],
        systemPrompt: String,
        tools: [GeminiTool],
        forceToolCall: Bool = false
    ) async throws -> ToolChatResult {
        let maxRetries = 2
        var lastError: Error?

        for attempt in 0...maxRetries {
            do {
                let toolConfig = forceToolCall ? GeminiImageToolRequest.ToolConfig(
                    functionCallingConfig: .init(mode: "ANY")
                ) : nil

                let request = GeminiImageToolRequest(
                    contents: contents,
                    systemInstruction: GeminiImageToolRequest.SystemInstruction(
                        parts: [.init(text: systemPrompt)]
                    ),
                    tools: tools,
                    toolConfig: toolConfig
                )

                let url = URL(string: "https://generativelanguage.googleapis.com/v1beta/models/\(model):generateContent?key=\(apiKey)")!
                var urlRequest = URLRequest(url: url)
                urlRequest.httpMethod = "POST"
                urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
                urlRequest.timeoutInterval = 300
                urlRequest.httpBody = try JSONEncoder().encode(request)

                let (data, _) = try await URLSession.shared.data(for: urlRequest)

                let response = try JSONDecoder().decode(GeminiToolResponse.self, from: data)

                if let error = response.error {
                    throw GeminiClientError.apiError(error.message)
                }

                guard let candidate = response.candidates?.first,
                      let parts = candidate.content?.parts else {
                    throw GeminiClientError.invalidResponse
                }

                var toolCalls: [ToolCall] = []
                var textResponse = ""

                for part in parts {
                    if let functionCall = part.functionCall {
                        let args = functionCall.args?.mapValues { $0.value } ?? [:]
                        toolCalls.append(ToolCall(name: functionCall.name, arguments: args, thoughtSignature: part.thoughtSignature))
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
                let backoffSeconds = UInt64(attempt + 1)
                try? await Task.sleep(nanoseconds: backoffSeconds * 1_000_000_000)
            }
        }

        throw lastError!
    }

    /// Continue conversation after tool execution: sends full history + tool result, returns text
    /// No tools on continuation — model returns plain JSON guided by system prompt.
    func continueImageToolRequest(
        originalPrompt: String,
        originalImageData: Data,
        toolCall: ToolCall,
        toolResult: String,
        systemPrompt: String
    ) async throws -> String {
        let maxRetries = 2
        var lastError: Error?

        for attempt in 0...maxRetries {
            do {
                let base64Data = originalImageData.base64EncodedString()

                // Build the full conversation:
                // 1. User message with image + text
                // 2. Model's function call
                // 3. Function response with results
                let contents: [GeminiImageToolRequest.Content] = [
                    // User turn: image + prompt
                    GeminiImageToolRequest.Content(
                        role: "user",
                        parts: [
                            GeminiImageToolRequest.Part(text: originalPrompt),
                            GeminiImageToolRequest.Part(mimeType: "image/jpeg", data: base64Data)
                        ]
                    ),
                    // Model turn: function call
                    GeminiImageToolRequest.Content(
                        role: "model",
                        parts: [
                            GeminiImageToolRequest.Part(
                                functionCall: .init(
                                    name: toolCall.name,
                                    args: toolCall.arguments.compactMapValues { "\($0)" }
                                ),
                                thoughtSignature: toolCall.thoughtSignature
                            )
                        ]
                    ),
                    // User turn: function response
                    GeminiImageToolRequest.Content(
                        role: "user",
                        parts: [
                            GeminiImageToolRequest.Part(functionResponse: .init(
                                name: toolCall.name,
                                response: .init(result: toolResult)
                            ))
                        ]
                    )
                ]

                let request = GeminiImageToolRequest(
                    contents: contents,
                    systemInstruction: GeminiImageToolRequest.SystemInstruction(
                        parts: [.init(text: systemPrompt)]
                    ),
                    tools: nil,   // No tools on continuation
                    toolConfig: nil
                )

                let url = URL(string: "https://generativelanguage.googleapis.com/v1beta/models/\(model):generateContent?key=\(apiKey)")!
                var urlRequest = URLRequest(url: url)
                urlRequest.httpMethod = "POST"
                urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
                urlRequest.timeoutInterval = 300
                urlRequest.httpBody = try JSONEncoder().encode(request)

                let (data, _) = try await URLSession.shared.data(for: urlRequest)

                let response = try JSONDecoder().decode(GeminiToolResponse.self, from: data)

                if let error = response.error {
                    throw GeminiClientError.apiError(error.message)
                }

                guard let text = response.candidates?.first?.content?.parts?.first?.text else {
                    throw GeminiClientError.invalidResponse
                }

                return text
            } catch {
                lastError = error
                guard attempt < maxRetries && isTransientError(error) else {
                    throw error
                }
                let backoffSeconds = UInt64(attempt + 1)
                try? await Task.sleep(nanoseconds: backoffSeconds * 1_000_000_000)
            }
        }

        throw lastError!
    }
}

/// Response type for tool-enabled requests
struct GeminiToolResponse: Decodable {
    let candidates: [Candidate]?
    let error: GeminiError?

    struct Candidate: Decodable {
        let content: Content?

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

    struct FunctionCall: Decodable {
        let name: String
        let args: [String: AnyCodable]?
    }

    struct GeminiError: Decodable {
        let message: String
    }
}
