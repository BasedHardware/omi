import Foundation
import OmiWAL

// MARK: - Chat Sessions API

extension APIClient {

  /// Delete a chat session and its messages
  func deleteChatSession(
    sessionId: String,
    expectedOwnerId: String? = nil
  ) async throws {
    try await delete(
      "v2/chat-sessions/\(sessionId)",
      authPolicy: expectedOwnerId.map { .ownerBound($0) } ?? .default,
      expectedAuthOwnerId: expectedOwnerId
    )
  }
}

// MARK: - AI User Profile API

/// Wire shape of `GET`/`PATCH /v1/users/ai-profile` and `POST /v1/users/ai-profile/refresh`.
///
/// Local DTO: the generated OpenAPI client types these routes as `OmiAnyCodable`. Every
/// field is optional and dates decode leniently, so one malformed timestamp never hides
/// the profile text from the prompts that read it.
struct AIUserProfileResponse: Decodable, Equatable, Sendable {
  let profileText: String?
  let generatedAt: Date?
  let dataSourcesUsed: Int?
  /// `backend` | `user_edit` | `exploration` | `client` (a legacy PATCH without a source).
  let source: String?
  /// When the backend last generated the profile; drives its daily cadence.
  let refreshedAt: Date?

  enum CodingKeys: String, CodingKey {
    case profileText = "profile_text"
    case generatedAt = "generated_at"
    case dataSourcesUsed = "data_sources_used"
    case source
    case refreshedAt = "refreshed_at"
  }

  init(
    profileText: String?, generatedAt: Date? = nil, dataSourcesUsed: Int? = nil, source: String? = nil,
    refreshedAt: Date? = nil
  ) {
    self.profileText = profileText
    self.generatedAt = generatedAt
    self.dataSourcesUsed = dataSourcesUsed
    self.source = source
    self.refreshedAt = refreshedAt
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    profileText = try? container.decodeIfPresent(String.self, forKey: .profileText)
    generatedAt = Self.date(container, .generatedAt)
    dataSourcesUsed = try? container.decodeIfPresent(Int.self, forKey: .dataSourcesUsed)
    source = try? container.decodeIfPresent(String.self, forKey: .source)
    refreshedAt = Self.date(container, .refreshedAt)
  }

  /// Python `isoformat()` may omit the zone or the fractional seconds; accept all of them.
  private static func date(_ container: KeyedDecodingContainer<CodingKeys>, _ key: CodingKeys) -> Date? {
    guard let raw = try? container.decodeIfPresent(String.self, forKey: key), !raw.isEmpty else { return nil }
    for options: ISO8601DateFormatter.Options in [
      [.withInternetDateTime, .withFractionalSeconds], [.withInternetDateTime],
    ] {
      let formatter = ISO8601DateFormatter()
      formatter.formatOptions = options
      if let date = formatter.date(from: raw) ?? formatter.date(from: raw + "Z") { return date }
    }
    return nil
  }
}

/// Who wrote the text sent with `PATCH /v1/users/ai-profile`.
enum AIUserProfileEditSource: String, Encodable, Sendable {
  case userEdit = "user_edit"
  case exploration
}

extension APIClient {

  /// The backend-owned profile, or nil when none exists yet. A read also lets the backend
  /// schedule its own refresh when the profile is stale; it never waits on generation.
  func getAIUserProfile() async throws -> AIUserProfileResponse? {
    try await get("v1/users/ai-profile", authorizationSnapshot: try Self.aiProfileOwnerSnapshot())
  }

  /// Synchronous backend regeneration (Settings "Generate Now" / "Regenerate"); ~10-40 s.
  func refreshAIUserProfile() async throws -> AIUserProfileResponse {
    try await post(
      "v1/users/ai-profile/refresh",
      body: EmptyBody(),
      authorizationSnapshot: try Self.aiProfileOwnerSnapshot(),
      requestTimeout: Self.managedSynthesisTimeout)
  }

  func updateAIUserProfile(profileText: String, source: AIUserProfileEditSource) async throws
    -> AIUserProfileResponse
  {
    struct UpdateRequest: Encodable {
      let profileText: String
      let source: AIUserProfileEditSource

      enum CodingKeys: String, CodingKey {
        case profileText = "profile_text"
        case source
      }
    }
    return try await patch(
      "v1/users/ai-profile",
      body: UpdateRequest(profileText: profileText, source: source),
      authorizationSnapshot: try Self.aiProfileOwnerSnapshot())
  }

  /// Upload a profile the retired local history held but never mirrored. Sent the way released
  /// builds mirrored it (no `source`, so the backend records `client`, with its `generated_at`),
  /// and pinned to the owner whose database the row was read from.
  func restoreLocalProfile(
    profileText: String, generatedAt: Date, authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> AIUserProfileResponse {
    struct RestoreRequest: Encodable {
      let profileText: String
      let generatedAt: String

      enum CodingKeys: String, CodingKey {
        case profileText = "profile_text"
        case generatedAt = "generated_at"
      }
    }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return try await patch(
      "v1/users/ai-profile",
      body: RestoreRequest(profileText: profileText, generatedAt: formatter.string(from: generatedAt)),
      authorizationSnapshot: authorizationSnapshot)
  }

  func deleteAIUserProfile() async throws {
    try await delete("v1/users/ai-profile", authorizationSnapshot: try Self.aiProfileOwnerSnapshot())
  }

  /// The profile is one account's text. Pin every call to the owner that started it so an
  /// auth retry after a mid-flight account switch never reads or writes the next account.
  private static func aiProfileOwnerSnapshot() throws -> RuntimeOwnerAuthorizationSnapshot {
    guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
      throw AuthError.userChangedDuringRequest
    }
    return snapshot
  }

  // MARK: - Agent VM

  struct AgentProvisionResponse: Decodable {
    let status: String
    let vmName: String
    let ip: String?
    let authToken: String
    let agentStatus: String
  }

  /// Provision a cloud agent VM for the current user (fire-and-forget)
  func provisionAgentVM() async throws -> AgentProvisionResponse {
    return try await post("v2/agent/provision", customBaseURL: rustBackendURL)
  }

  struct AgentStatusResponse: Decodable {
    let vmName: String
    let zone: String
    let ip: String?
    let status: String
    let authToken: String
    let createdAt: String
    let lastQueryAt: String?
  }

  /// Get current agent VM status
  func getAgentStatus() async throws -> AgentStatusResponse? {
    return try await get("v2/agent/status", customBaseURL: rustBackendURL)
  }
}
