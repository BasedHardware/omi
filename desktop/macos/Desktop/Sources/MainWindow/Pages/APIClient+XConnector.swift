import Foundation

/// Backend transport owned by the X connector import feature.
extension APIClient {
  /// Ask the Python backend for the X OAuth authorize URL. The desktop passes
  /// its own deep link so the backend can redirect back to this exact build.
  func xOAuthURL(successRedirectURL: String) async throws -> XOAuthURLResponse {
    let encoded = successRedirectURL.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
    return try await get("v1/x/oauth-url?success_redirect_url=\(encoded)")
  }

  func xConnectionStatus() async throws -> XConnectionStatus {
    try await get("v1/x/connection-status")
  }

  @discardableResult
  func xSync() async throws -> XSyncResult {
    try await post("v1/x/sync")
  }

  func xDisconnect() async throws {
    let _: XDisconnectResponse = try await post("v1/x/disconnect")
  }
}

struct XOAuthURLResponse: Decodable {
  let success: Bool
  let authUrl: String?
  let error: String?

  enum CodingKeys: String, CodingKey {
    case success
    case authUrl = "auth_url"
    case error
  }
}

struct XConnectionStatus: Decodable {
  let success: Bool
  let connected: Bool
  let handle: String?
  let postCount: Int?
  let memoryCount: Int?
  let syncing: Bool?
  let lastSyncedAt: String?
  let lastSyncSource: String?

  enum CodingKeys: String, CodingKey {
    case success
    case connected
    case handle
    case postCount = "post_count"
    case memoryCount = "memory_count"
    case syncing
    case lastSyncedAt = "last_synced_at"
    case lastSyncSource = "last_sync_source"
  }
}

struct XSyncResult: Decodable {
  let success: Bool
  let source: String?
  let newPosts: Int?
  let memoriesCreated: Int?
  let error: String?

  enum CodingKeys: String, CodingKey {
    case success
    case source
    case newPosts = "new_posts"
    case memoriesCreated = "memories_created"
    case error
  }
}

private struct XDisconnectResponse: Decodable {
  let success: Bool
}
