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

/// Response of POST /v1/users/ai-profile/synthesize.
struct AIUserProfileSynthesisResponse: Codable, Equatable, Sendable {
  let profileText: String
  let dataSourcesUsed: [String]
  let itemCount: Int

  enum CodingKeys: String, CodingKey {
    case profileText = "profile_text"
    case dataSourcesUsed = "data_sources_used"
    case itemCount = "item_count"
  }
}

struct AIUserProfileResponse: Codable {
  let profileText: String
  let generatedAt: Date
  let dataSourcesUsed: Int

  enum CodingKeys: String, CodingKey {
    case profileText = "profile_text"
    case generatedAt = "generated_at"
    case dataSourcesUsed = "data_sources_used"
  }
}

extension APIClient {

  /// Sync AI-generated user profile to backend
  func syncAIUserProfile(profileText: String, generatedAt: Date, dataSourcesUsed: Int) async throws {
    struct SyncRequest: Encodable {
      let profile_text: String
      let generated_at: String
      let data_sources_used: Int
    }

    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

    let body = SyncRequest(
      profile_text: profileText,
      generated_at: formatter.string(from: generatedAt),
      data_sources_used: dataSourcesUsed
    )

    let _: AIUserProfileResponse = try await patch("v1/users/ai-profile", body: body)
  }

  /// Return-only two-stage AI user profile synthesis through managed memories.
  /// The prompts, the model and the consolidation live in the backend; callers send
  /// their formatted source lines plus past profiles (oldest first) and persist the
  /// returned text through `syncAIUserProfile`.
  func synthesizeAIUserProfile(
    memories: [String],
    tasks: [String],
    goals: [String],
    conversations: [String],
    messages: [String],
    pastProfilesOldestFirst: [String],
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AIUserProfileSynthesisResponse {
    // The request carries one account's memories, messages and past profiles. Without a
    // pinned owner an auth retry after a mid-flight account switch would replay them under
    // the new account's token.
    guard
      let pinnedAuthorization =
        authorizationSnapshot
        ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: expectedOwnerId)
    else {
      throw AuthError.userChangedDuringRequest
    }
    struct SynthesizeRequest: Encodable {
      let memories: [String]
      let tasks: [String]
      let goals: [String]
      let conversations: [String]
      let messages: [String]
      let past_profiles: [String]
    }

    return try await post(
      "v1/users/ai-profile/synthesize",
      body: SynthesizeRequest(
        memories: memories,
        tasks: tasks,
        goals: goals,
        conversations: conversations,
        messages: messages,
        past_profiles: Array(pastProfilesOldestFirst.prefix(5))
      ),
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: pinnedAuthorization,
      requestTimeout: Self.managedSynthesisTimeout)
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
