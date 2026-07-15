import Foundation
import OmiWAL

// MARK: - Chat Sessions API

extension APIClient {

  /// Create a new chat session
  func createChatSession(
    title: String? = nil,
    appId: String? = nil
  ) async throws -> ChatSession {
    struct CreateRequest: Encodable {
      let title: String?
      let app_id: String?
    }
    let body = CreateRequest(title: title, app_id: appId)
    return try await post("v2/chat-sessions", body: body)
  }

  /// Fetch chat sessions
  func getChatSessions(
    appId: String? = nil,
    limit: Int = 50,
    offset: Int = 0,
    starred: Bool? = nil
  ) async throws -> [ChatSession] {
    var queryItems: [String] = [
      "limit=\(limit)",
      "offset=\(offset)",
    ]

    if let appId = appId {
      queryItems.append("app_id=\(appId)")
    }
    if let starred = starred {
      queryItems.append("starred=\(starred)")
    }

    let endpoint = "v2/chat-sessions?\(queryItems.joined(separator: "&"))"
    return try await get(endpoint)
  }

  /// Update a chat session (title, starred)
  func updateChatSession(
    sessionId: String,
    title: String? = nil,
    starred: Bool? = nil
  ) async throws -> ChatSession {
    struct UpdateRequest: Encodable {
      let title: String?
      let starred: Bool?
    }
    let body = UpdateRequest(title: title, starred: starred)
    return try await patch("v2/chat-sessions/\(sessionId)", body: body)
  }

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

  /// Generate an initial greeting message for a new chat session
  func getInitialMessage(
    sessionId: String,
    appId: String? = nil,
    expectedOwnerId: String? = nil
  ) async throws
    -> InitialMessageResponse
  {
    struct InitialMessageRequest: Encodable {
      let sessionId: String
      let appId: String?

      enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case appId = "app_id"
      }
    }

    let body = InitialMessageRequest(sessionId: sessionId, appId: appId)
    guard let expectedOwnerId else {
      return try await post("v2/chat/initial-message", body: body)
    }
    guard let url = URL(string: baseURL + "v2/chat/initial-message") else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: true,
      expectedAuthOwnerId: expectedOwnerId
    )
    request.httpBody = try transport.encoder.encode(body)
    return try await performRequest(request, authPolicy: .ownerBound(expectedOwnerId))
  }

  /// Generate a title for a chat session based on its messages
  func generateSessionTitle(sessionId: String, messages: [(text: String, sender: String)])
    async throws -> GenerateTitleResponse
  {
    struct TitleMessageInput: Encodable {
      let text: String
      let sender: String
    }

    struct GenerateTitleRequest: Encodable {
      let sessionId: String
      let messages: [TitleMessageInput]

      enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case messages
      }
    }

    let body = GenerateTitleRequest(
      sessionId: sessionId,
      messages: messages.map { TitleMessageInput(text: $0.text, sender: $0.sender) }
    )
    return try await post("v2/chat/generate-title", body: body)
  }
}
/// Response from generating session title
struct GenerateTitleResponse: Codable {
  let title: String
}

/// Response from generating initial message
struct InitialMessageResponse: Codable {
  let message: String
  let messageId: String

  enum CodingKeys: String, CodingKey {
    case message
    case messageId = "message_id"
  }
}

// MARK: - AI User Profile API

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
  func syncAIUserProfile(profileText: String, generatedAt: Date, dataSourcesUsed: Int) async throws
  {
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
