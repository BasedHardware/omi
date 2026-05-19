import Foundation

/// Direct embedding client for hybrid mode (no Omi Gemini proxy).
enum HybridEmbeddingClient {
  static let legacyGeminiModelId = "gemini-embedding-001"
  static let legacyGeminiDimension = 3072

  struct ProviderConfig: Equatable {
    let baseURL: String
    let model: String
    let apiKey: String
  }

  struct EmbeddingResult: Equatable {
    let vector: [Float]
    let model: String
    let dimension: Int
  }

  enum ClientError: LocalizedError {
    case notConfigured
    case invalidSettings
    case invalidResponse
    case dimensionMismatch(expected: Int, got: Int)

    var errorDescription: String? {
      switch self {
      case .notConfigured:
        return "Hybrid embeddings are not configured. Set embedding_provider in Settings and enable OMI_HYBRID_DIRECT_EMBEDDINGS_ENABLED."
      case .invalidSettings:
        return "embedding_provider settings are invalid."
      case .invalidResponse:
        return "Embedding provider returned an unexpected response."
      case .dimensionMismatch(let expected, let got):
        return "Embedding dimension mismatch (expected \(expected), got \(got))."
      }
    }
  }

  static func isEnabled() -> Bool {
    guard DesktopBackendEnvironment.selectedBackendTarget.mode == .localDaemon else {
      return false
    }
    return DesktopBackendEnvironment.isCapability(.directEmbeddings, availableIn: .localDaemon)
  }

  static func loadProviderConfig(from settings: [LocalDaemonSetting]) -> ProviderConfig? {
    guard let raw = settings.first(where: { $0.key == "embedding_provider" })?.valueJson,
      let data = raw.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }
    let kind = (json["kind"] as? String) ?? ""
    guard kind == "openai_compatible" || kind == "openai" else {
      return nil
    }
    guard let baseURL = json["base_url"] as? String, !baseURL.isEmpty else {
      return nil
    }
    let model = (json["model"] as? String) ?? "text-embedding-3-small"
    let apiKey =
      (json["api_key"] as? String) ?? (json["key"] as? String) ?? ""
    return ProviderConfig(baseURL: baseURL, model: model, apiKey: apiKey)
  }

  static func embed(text: String, settings: [LocalDaemonSetting]) async throws -> EmbeddingResult {
    guard let config = loadProviderConfig(from: settings) else {
      throw ClientError.notConfigured
    }
    return try await embedOpenAICompatible(text: text, config: config)
  }

  static func embedFromDaemonSettings(text: String) async throws -> EmbeddingResult {
    let settings = try await APIClient.shared.getSelectedBackendSettings()
    return try await embed(text: text, settings: settings)
  }

  private static func embedOpenAICompatible(text: String, config: ProviderConfig) async throws
    -> EmbeddingResult
  {
    let base = config.baseURL.hasSuffix("/") ? String(config.baseURL.dropLast()) : config.baseURL
    guard let url = URL(string: "\(base)/embeddings") else {
      throw ClientError.invalidSettings
    }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    if !config.apiKey.isEmpty {
      request.setValue("Bearer \(config.apiKey)", forHTTPHeaderField: "Authorization")
    }
    request.timeoutInterval = 60
    request.httpBody = try JSONSerialization.data(withJSONObject: [
      "model": config.model,
      "input": text,
    ])

    let (data, response) = try await URLSession.shared.data(for: request)
    guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
      throw ClientError.invalidResponse
    }
    guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      let items = json["data"] as? [[String: Any]],
      let first = items.first,
      let embedding = first["embedding"] as? [Double]
    else {
      throw ClientError.invalidResponse
    }
    let floats = embedding.map { Float($0) }
    let normalized = normalize(floats)
    return EmbeddingResult(
      vector: normalized,
      model: config.model,
      dimension: normalized.count
    )
  }

  private static func normalize(_ vector: [Float]) -> [Float] {
    var sum: Float = 0
    for value in vector {
      sum += value * value
    }
    let magnitude = sqrt(sum)
    guard magnitude > 0 else { return vector }
    return vector.map { $0 / magnitude }
  }

  static func isCompatibleEmbedding(
    storedModel: String?,
    storedDim: Int?,
    activeModel: String,
    activeDim: Int
  ) -> Bool {
    guard let storedModel, let storedDim else {
      // Legacy rows without metadata: only match legacy Gemini size when using cloud defaults.
      return activeModel == legacyGeminiModelId && activeDim == legacyGeminiDimension
    }
    return storedModel == activeModel && storedDim == activeDim
  }
}
