import Foundation

/// Low-level HTTP transport for the desktop Python/Rust backends.
/// Owns URLSession, JSON decoding, auth/BYOK header assembly, and standard verb helpers.
struct OmiHTTPTransport {
  let session: URLSession
  let decoder: JSONDecoder
  let encoder: JSONEncoder

  // Cached formatters — avoid allocating per-field on large payloads.
  private static let isoFractional: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
  }()
  private static let isoStandard = ISO8601DateFormatter()

  /// When set, `buildHeaders` uses this instead of calling AuthService (test-only).
  var testAuthHeader: String?

  init() {
    let config = URLSessionConfiguration.default
    config.timeoutIntervalForRequest = 30
    self.session = URLSession(configuration: config)
    self.decoder = Self.makeDecoder()
    self.encoder = Self.makeEncoder()
  }

  /// Test-only initializer that accepts a custom URLSession for request interception.
  init(session: URLSession) {
    self.session = session
    self.decoder = Self.makeDecoder()
    self.encoder = Self.makeEncoder()
  }

  static func makeDecoder() -> JSONDecoder {
    let decoder = JSONDecoder()
    // Note: Don't use .convertFromSnakeCase - it conflicts with explicit CodingKeys
    // Use custom date strategy to handle ISO8601 with fractional seconds
    decoder.dateDecodingStrategy = .custom { decoder in
      let container = try decoder.singleValueContainer()
      let dateString = try container.decode(String.self)

      // Try with fractional seconds first (API returns dates like "2026-01-25T22:51:07.159249Z")
      if let date = isoFractional.date(from: dateString) {
        return date
      }

      // Fallback to standard ISO8601 without fractional seconds
      if let date = isoStandard.date(from: dateString) {
        return date
      }

      throw DecodingError.dataCorruptedError(
        in: container, debugDescription: "Invalid date format: \(dateString)")
    }
    return decoder
  }

  static func makeEncoder() -> JSONEncoder {
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .custom { date, encoder in
      var container = encoder.singleValueContainer()
      let formatted = isoFractional.string(from: date)
      try container.encode(formatted)
    }
    return encoder
  }

  // MARK: - Request Building

  func buildHeaders(
    requireAuth: Bool = true,
    forceRefreshAuth: Bool = false,
    includeBYOK: Bool = false
  ) async throws -> [String: String] {
    var headers: [String: String] = [
      "Content-Type": "application/json",
      "X-App-Platform": "macos",
      "X-App-Version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown",
      "X-App-Build": Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "unknown",
      "X-Device-Id-Hash": ClientDeviceService.shared.deviceIdHash,
      "X-Request-Start-Time": String(Date().timeIntervalSince1970),
      "X-Desktop-Request-ID": UUID().uuidString,
    ]

    if requireAuth {
      if let testHeader = testAuthHeader {
        headers["Authorization"] = testHeader
      } else {
        let authService = await MainActor.run { AuthService.shared }
        let authHeader = try await authService.getAuthHeader(forceRefresh: forceRefreshAuth)
        headers["Authorization"] = authHeader
      }
    }

    // BYOK: attach user-provided keys so the backend uses them for LLM/STT
    // calls this request triggers. Sent per-request; never stored server-side.
    if includeBYOK, APIKeyService.isByokActive {
      let health = await MainActor.run { CredentialHealthManager.shared }
      let snapshot = APIKeyService.byokSnapshot
      for (provider, entry) in snapshot {
        let canAttach = await MainActor.run {
          health.canUseBYOK(provider: provider, fingerprint: entry.fingerprint)
        }
        if canAttach {
          headers[provider.headerName] = entry.key
        } else {
          log(
            "CredentialHealth: context=build_headers failure_class=byok_invalid_suppressed"
              + " provider=\(provider.rawValue)")
        }
      }
    }

    return headers
  }

  // MARK: - HTTP Methods

  func get<T: Decodable>(
    _ endpoint: String,
    baseURL: String,
    requireAuth: Bool = true,
    includeBYOK: Bool = false
  ) async throws -> T {
    guard let url = URL(string: baseURL + endpoint) else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth, includeBYOK: includeBYOK)

    return try await performRequest(request)
  }

  func post<T: Decodable, B: Encodable>(
    _ endpoint: String,
    baseURL: String,
    body: B,
    requireAuth: Bool = true,
    includeBYOK: Bool = false
  ) async throws -> T {
    guard let url = URL(string: baseURL + endpoint) else {
      throw APIError.invalidResponse
    }
    log("APIClient: POST \(url.absoluteString)")
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth, includeBYOK: includeBYOK)
    request.httpBody = try encoder.encode(body)

    return try await performRequest(request)
  }

  func post<T: Decodable>(
    _ endpoint: String,
    baseURL: String,
    requireAuth: Bool = true,
    includeBYOK: Bool = false
  ) async throws -> T {
    guard let url = URL(string: baseURL + endpoint) else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth, includeBYOK: includeBYOK)

    return try await performRequest(request)
  }

  func delete(
    _ endpoint: String,
    baseURL: String,
    requireAuth: Bool = true,
    includeBYOK: Bool = false
  ) async throws {
    guard let url = URL(string: baseURL + endpoint) else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "DELETE"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: requireAuth, includeBYOK: includeBYOK)

    let (_, response) = try await session.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIError.invalidResponse
    }

    if httpResponse.statusCode == 401 {
      throw APIError.unauthorized
    }

    guard (200...299).contains(httpResponse.statusCode) else {
      throw APIError.httpError(statusCode: httpResponse.statusCode)
    }
  }

  // MARK: - Request Execution

  func performRequest<T: Decodable>(_ request: URLRequest) async throws -> T {
    let (data, response) = try await session.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIError.invalidResponse
    }

    // Handle 401 - token might be expired
    if httpResponse.statusCode == 401 {
      // Try to refresh token and retry once
      let authService = await MainActor.run { AuthService.shared }

      var retryRequest = request
      retryRequest.setValue(
        try await authService.getAuthHeader(forceRefresh: true), forHTTPHeaderField: "Authorization")

      let (retryData, retryResponse) = try await session.data(for: retryRequest)

      guard let retryHttpResponse = retryResponse as? HTTPURLResponse else {
        throw APIError.invalidResponse
      }

      if retryHttpResponse.statusCode == 401 {
        throw APIError.unauthorized
      }

      guard (200...299).contains(retryHttpResponse.statusCode) else {
        let detail = Self.extractErrorDetail(from: retryData)
        throw APIError.httpError(statusCode: retryHttpResponse.statusCode, detail: detail)
      }

      return try decoder.decode(T.self, from: retryData)
    }

    guard (200...299).contains(httpResponse.statusCode) else {
      let detail = Self.extractErrorDetail(from: data)
      throw APIError.httpError(statusCode: httpResponse.statusCode, detail: detail)
    }

    do {
      return try decoder.decode(T.self, from: data)
    } catch let decodingError as DecodingError {
      // Log detailed decoding error for debugging
      switch decodingError {
      case .keyNotFound(let key, let context):
        logError(
          "Decoding error - key '\(key.stringValue)' not found: \(context.debugDescription)",
          error: decodingError)
      case .typeMismatch(let type, let context):
        logError(
          "Decoding error - type mismatch for \(type): \(context.debugDescription)",
          error: decodingError)
      case .valueNotFound(let type, let context):
        logError(
          "Decoding error - value not found for \(type): \(context.debugDescription)",
          error: decodingError)
      case .dataCorrupted(let context):
        logError(
          "Decoding error - data corrupted: \(context.debugDescription)", error: decodingError)
      @unknown default:
        logError("Decoding error", error: decodingError)
      }
      throw decodingError
    }
  }

  static func extractErrorDetail(from data: Data) -> String? {
    if let payload = extractErrorPayload(from: data) {
      return payload.preferredMessage
    }
    guard
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let detail = json["detail"] as? String
    else { return nil }
    return detail
  }

  static func extractErrorPayload(from data: Data) -> APIErrorPayload? {
    try? JSONDecoder().decode(APIErrorPayload.self, from: data)
  }
}

// MARK: - API Errors

enum APIError: LocalizedError {
  case invalidResponse
  case unauthorized
  case httpError(statusCode: Int, detail: String? = nil)
  case decodingError(Error)
  case unsupportedTierScopedBulkMutation(String)
  case syncRateLimited(retryAfterSeconds: Int?)
  case syncUploadRejected(reason: String)

  var detail: String? {
    switch self {
    case .httpError(_, let detail):
      return detail
    case .syncUploadRejected(let reason):
      return reason
    default:
      return nil
    }
  }

  var errorDescription: String? {
    switch self {
    case .invalidResponse:
      return "Invalid response from server"
    case .unauthorized:
      return "Unauthorized - please sign in again"
    case .httpError(let statusCode, let detail):
      if let detail { return detail }
      return "HTTP error: \(statusCode)"
    case .decodingError(let error):
      return "Failed to decode response: \(error.localizedDescription)"
    case .unsupportedTierScopedBulkMutation(let operation):
      return "Layer-scoped bulk memory \(operation) is not supported yet."
    case .syncRateLimited(let retryAfterSeconds):
      if let retryAfterSeconds {
        return "Sync rate limited (retry after \(retryAfterSeconds)s)"
      }
      return "Sync rate limited"
    case .syncUploadRejected(let reason):
      return reason
    }
  }
}
