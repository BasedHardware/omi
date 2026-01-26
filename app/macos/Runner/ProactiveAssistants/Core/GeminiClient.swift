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

                init(type: String, enum: [String]? = nil, description: String? = nil, items: Items? = nil) {
                    self.type = type
                    self.enum = `enum`
                    self.description = description
                    self.items = items
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

    init(apiKey: String? = nil, model: String = "gemini-2.0-flash") throws {
        guard let key = apiKey ?? ProcessInfo.processInfo.environment["GEMINI_API_KEY"] else {
            throw GeminiClientError.missingAPIKey
        }
        self.apiKey = key
        self.model = model
    }

    /// Send a request to the Gemini API with an image
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
    }

    /// Send a text-only request to the Gemini API
    /// - Parameters:
    ///   - prompt: Text prompt to send
    ///   - systemPrompt: System instructions for the model
    /// - Returns: The text response from the model
    func sendTextRequest(
        prompt: String,
        systemPrompt: String
    ) async throws -> String {
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
    }
}
