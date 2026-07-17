import Foundation
import OmiWAL

// MARK: - People Models

struct Person: Codable, Identifiable {
  let id: String
  let name: String
  let createdAt: Date?
  let updatedAt: Date?
  let speechSamples: [String]
  let speechSampleTranscripts: [String]?
  let speechSamplesVersion: Int

  enum CodingKeys: String, CodingKey {
    case id, name
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case speechSamples = "speech_samples"
    case speechSampleTranscripts = "speech_sample_transcripts"
    case speechSamplesVersion = "speech_samples_version"
  }

  init(
    id: String,
    name: String,
    createdAt: Date? = nil,
    updatedAt: Date? = nil,
    speechSamples: [String] = [],
    speechSampleTranscripts: [String]? = nil,
    speechSamplesVersion: Int = 3
  ) {
    self.id = id
    self.name = name
    self.createdAt = createdAt
    self.updatedAt = updatedAt
    self.speechSamples = speechSamples
    self.speechSampleTranscripts = speechSampleTranscripts
    self.speechSamplesVersion = speechSamplesVersion
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    name = try container.decode(String.self, forKey: .name)
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt)
    updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt)
    speechSamples = try container.decodeIfPresent([String].self, forKey: .speechSamples) ?? []
    speechSampleTranscripts = try container.decodeIfPresent(
      [String].self, forKey: .speechSampleTranscripts)
    speechSamplesVersion = try container.decodeIfPresent(Int.self, forKey: .speechSamplesVersion) ?? 3
  }
}

// MARK: - People API

extension APIClient {

  func getUserSubscription() async throws -> UserSubscriptionResponse {
    return try await get("v1/users/me/subscription")
  }

  func getTrialMetadata() async throws -> TrialMetadataResponse {
    return try await get("v1/users/me/trial")
  }

  func getAvailablePlans() async throws -> AvailablePlansResponse {
    return try await get("v1/payments/available-plans")
  }

  func getOverageInfo() async throws -> OverageInfoResponse {
    return try await get("v1/payments/overage-info")
  }

  func createCheckoutSession(priceId: String, promotionCode: String? = nil) async throws
    -> CheckoutSessionResponse
  {
    struct Request: Encodable {
      let priceId: String
      let promotionCode: String?

      enum CodingKeys: String, CodingKey {
        case priceId = "price_id"
        case promotionCode = "promotion_code"
      }
    }

    return try await post(
      "v1/payments/checkout-session",
      body: Request(priceId: priceId, promotionCode: promotionCode))
  }

  func upgradeSubscription(priceId: String, promotionCode: String? = nil) async throws
    -> UpgradeSubscriptionResponse
  {
    struct Request: Encodable {
      let priceId: String
      let promotionCode: String?

      enum CodingKeys: String, CodingKey {
        case priceId = "price_id"
        case promotionCode = "promotion_code"
      }
    }

    return try await post(
      "v1/payments/upgrade-subscription",
      body: Request(priceId: priceId, promotionCode: promotionCode))
  }

  func createCustomerPortalSession() async throws -> CustomerPortalResponse {
    return try await post("v1/payments/customer-portal")
  }

  /// Activate the Bring-Your-Own-Keys free plan on the backend.
  /// Sends SHA-256 fingerprints (never the keys themselves) so the backend
  /// can tell when the user rotates keys and re-validate.
  func activateBYOK(fingerprints: [String: String]) async throws {
    struct Request: Encodable {
      let fingerprints: [String: String]
    }
    struct Empty: Decodable {}
    let _: Empty = try await post(
      "v1/users/me/byok-active", body: Request(fingerprints: fingerprints), includeBYOK: false
    )
  }

  /// Deactivate BYOK (user cleared keys) so they return to the paid plan gate.
  func deactivateBYOK() async throws {
    try await delete("v1/users/me/byok-active", includeBYOK: false)
  }

  /// Fetches all people for the current user
  func getPeople() async throws -> [Person] {
    return try await get("v1/users/people")
  }

  /// Creates a new person
  func createPerson(name: String) async throws -> Person {
    struct CreatePersonRequest: Encodable {
      let name: String
    }
    return try await post("v1/users/people", body: CreatePersonRequest(name: name))
  }

  /// Bulk assigns segments to a person or user
  func assignSegmentsBulk(
    conversationId: String,
    segmentIds: [String],
    isUser: Bool,
    personId: String?
  ) async throws {
    struct AssignBulkRequest: Encodable {
      let assignType: String
      let value: String?
      let segmentIds: [String]

      enum CodingKeys: String, CodingKey {
        case assignType = "assign_type"
        case value
        case segmentIds = "segment_ids"
      }
    }

    let body = AssignBulkRequest(
      assignType: isUser ? "is_user" : "person_id",
      value: isUser ? "true" : personId,
      segmentIds: segmentIds
    )

    guard let url = URL(string: baseURL + "v1/conversations/\(conversationId)/segments/assign-bulk") else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)
    request.httpBody = try JSONEncoder().encode(body)

    try await performVoidRequest(request)
  }

  // MARK: - LLM Usage

  func recordLlmUsage(
    inputTokens: Int,
    outputTokens: Int,
    cacheReadTokens: Int,
    cacheWriteTokens: Int,
    totalTokens: Int,
    costUsd: Double,
    account: String = "omi"
  ) async {
    struct Req: Encodable {
      let input_tokens: Int
      let output_tokens: Int
      let cache_read_tokens: Int
      let cache_write_tokens: Int
      let total_tokens: Int
      let cost_usd: Double
      let account: String
    }
    struct Res: Decodable { let status: String }
    do {
      let _: Res = try await post(
        "v1/users/me/llm-usage",
        body: Req(
          input_tokens: inputTokens,
          output_tokens: outputTokens,
          cache_read_tokens: cacheReadTokens,
          cache_write_tokens: cacheWriteTokens,
          total_tokens: totalTokens,
          cost_usd: costUsd,
          account: account
        ))
    } catch {
      log("APIClient: LLM usage record failed: \(error.localizedDescription)")
    }
  }

  func fetchTotalOmiAICost() async -> Double? {
    struct Res: Decodable { let total_cost_usd: Double }
    do {
      log("APIClient: Fetching total Omi AI cost from backend")
      let res: Res = try await get("v1/users/me/llm-usage/total")
      log(
        "APIClient: Total Omi AI cost from backend: $\(String(format: "%.4f", res.total_cost_usd))")
      return res.total_cost_usd
    } catch {
      log("APIClient: LLM total cost fetch failed: \(error.localizedDescription)")
      return nil
    }
  }

  // MARK: - Chat Usage Quota

  /// Current-month chat usage + the plan's cap. Backed by Python backend
  /// endpoint `/v1/users/me/usage-quota` which reads `users/{uid}/llm_usage/*`.
  struct ChatUsageQuota: Decodable {
    let plan: String  // display name: "Free" | "Plus" | "Pro"
    let planType: String  // internal id: "basic" | "unlimited" | "architect"
    let unit: String  // "questions" | "cost_usd"
    let used: Double
    let limit: Double?  // nil means unlimited
    let percent: Double
    let allowed: Bool
    let resetAt: Int?  // unix seconds — start of next UTC month

    enum CodingKeys: String, CodingKey {
      case plan
      case planType = "plan_type"
      case unit
      case used
      case limit
      case percent
      case allowed
      case resetAt = "reset_at"
    }
  }

  func fetchChatUsageQuota(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async -> ChatUsageQuota? {
    do {
      let res: ChatUsageQuota = try await get(
        "v1/users/me/usage-quota",
        authorizationSnapshot: authorizationSnapshot)
      log(
        "APIClient: Quota plan=\(res.plan) unit=\(res.unit) used=\(res.used) limit=\(res.limit ?? -1) allowed=\(res.allowed)"
      )
      return res
    } catch {
      log("APIClient: Chat quota fetch failed: \(error.localizedDescription)")
      return nil
    }
  }

  // MARK: - API Keys

  struct ApiKeysResponse: Decodable {
    let deepgramApiKey: String?
    let geminiApiKey: String?
    let firebaseApiKey: String?
    let googleCalendarApiKey: String?

    enum CodingKeys: String, CodingKey {
      case deepgramApiKey = "deepgram_api_key"
      case geminiApiKey = "gemini_api_key"
      case firebaseApiKey = "firebase_api_key"
      case googleCalendarApiKey = "google_calendar_api_key"
    }
  }

  func fetchApiKeys() async throws -> ApiKeysResponse {
    return try await get("v1/config/api-keys", customBaseURL: rustBackendURL)
  }

  struct TtsSynthesizeRequest: Encodable {
    let text: String
    let voiceId: String
    let instructions: String?

    enum CodingKeys: String, CodingKey {
      case text
      case voiceId = "voice_id"
      case instructions
    }
  }

  func synthesizeSpeech(request body: TtsSynthesizeRequest) async throws -> Data {
    let base = rustBackendURL
    guard !base.isEmpty, let url = URL(string: base + "v1/tts/synthesize") else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.timeoutInterval = 60
    request.allHTTPHeaderFields = try await buildHeaders()
    request.httpBody = try JSONEncoder().encode(body)

    // This desktop-backend route can surface upstream OpenAI/BYOK credential
    // failures as HTTP 401. Refresh the Firebase header once in case it is stale,
    // but never let a voice-only provider failure invalidate the Omi session.
    // Only remap to providerAuth when the body is OpenAI-shaped — a bare/Firebase
    // 401 after refresh is a real login failure and must require re-auth.
    let (data, httpResponse) = try await performAuthenticatedData(
      for: request,
      authPolicy: .providerCredentialBoundary
    )

    if httpResponse.statusCode == 401 {
      let detail = (try? JSONDecoder().decode(APIErrorPayload.self, from: data))?.preferredMessage
      if detail?.hasPrefix("OpenAI TTS request failed:") == true {
        let mode: CredentialAuthMode = APIKeyService.isByokActive ? .byok : .managed
        throw CredentialHealthError.providerAuth(
          provider: .openai,
          mode: mode,
          message: mode == .byok
            ? "Your OpenAI key was rejected. Update it in Settings."
            : "OpenAI authentication failed. Voice responses are using fallback."
        )
      }
      await invalidateSessionAfterUnauthorized(
        endpoint: endpointLabel(for: request),
        signOutOn401: true
      )
      throw APIError.unauthorized
    }

    if httpResponse.statusCode == 429 {
      let detail = (try? JSONDecoder().decode(APIErrorPayload.self, from: data))?.preferredMessage
      if detail?.hasPrefix("OpenAI TTS request failed:") == true {
        throw CredentialHealthError.providerQuota(
          provider: .openai,
          message: "OpenAI voice quota was exceeded. Voice responses are using fallback."
        )
      }
      throw APIError.httpError(statusCode: httpResponse.statusCode, detail: detail)
    }
    guard (200...299).contains(httpResponse.statusCode) else {
      throw APIError.httpError(statusCode: httpResponse.statusCode)
    }

    return data
  }

}
