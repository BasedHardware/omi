import Foundation
import OmiWAL

// MARK: - App Models

/// App summary for list views (lightweight)
struct OmiApp: Codable, Identifiable, Sendable {
  let id: String
  let name: String
  let description: String
  let image: String
  let category: String
  let author: String
  let capabilities: [String]
  let approved: Bool
  let `private`: Bool
  let installs: Int
  var ratingAvg: Double?
  var ratingCount: Int
  let isPaid: Bool
  let price: Double?
  var enabled: Bool

  enum CodingKeys: String, CodingKey {
    case id, name, description, image, category, author, capabilities
    case approved
    case `private`
    case installs
    case ratingAvg = "rating_avg"
    case ratingCount = "rating_count"
    case isPaid = "is_paid"
    case price
    case enabled
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    name = try container.decodeIfPresent(String.self, forKey: .name) ?? ""
    description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
    image = try container.decodeIfPresent(String.self, forKey: .image) ?? ""
    category = try container.decodeIfPresent(String.self, forKey: .category) ?? "other"
    author = try container.decodeIfPresent(String.self, forKey: .author) ?? ""
    capabilities = try container.decodeIfPresent([String].self, forKey: .capabilities) ?? []
    approved = try container.decodeIfPresent(Bool.self, forKey: .approved) ?? false
    `private` = try container.decodeIfPresent(Bool.self, forKey: .private) ?? false
    installs = try container.decodeIfPresent(Int.self, forKey: .installs) ?? 0
    ratingAvg = try container.decodeIfPresent(Double.self, forKey: .ratingAvg)
    ratingCount = try container.decodeIfPresent(Int.self, forKey: .ratingCount) ?? 0
    isPaid = try container.decodeIfPresent(Bool.self, forKey: .isPaid) ?? false
    price = try container.decodeIfPresent(Double.self, forKey: .price)
    enabled = try container.decodeIfPresent(Bool.self, forKey: .enabled) ?? false
  }

  /// Check if app works with chat
  var worksWithChat: Bool {
    capabilities.contains("chat") || capabilities.contains("persona")
  }

  /// Check if app works with memories/conversations
  var worksWithMemories: Bool {
    capabilities.contains("memories")
  }

  /// Check if app has external integration
  var worksExternally: Bool {
    capabilities.contains("external_integration")
  }

  /// Formatted rating string
  var formattedRating: String? {
    guard let rating = ratingAvg, ratingCount > 0 else { return nil }
    return String(format: "%.1f", rating)
  }

  /// Formatted installs string (e.g., "1.2k", "43k")
  var formattedInstalls: String? {
    guard installs > 0 else { return nil }
    if installs >= 1000 {
      let thousands = Double(installs) / 1000.0
      if thousands >= 10 {
        return String(format: "%.0fk", thousands)
      } else {
        return String(format: "%.1fk", thousands)
      }
    }
    return "\(installs)"
  }
}
/// Full app details
struct OmiAppDetails: Codable, Identifiable {
  let id: String
  let name: String
  let description: String
  let image: String
  let category: String
  let author: String
  let email: String?
  let capabilities: [String]
  let uid: String?
  let approved: Bool
  let `private`: Bool
  let status: String
  let chatPrompt: String?
  let memoryPrompt: String?
  let personaPrompt: String?
  let installs: Int
  let ratingAvg: Double?
  let ratingCount: Int
  let isPaid: Bool
  let price: Double?
  let paymentPlan: String?
  let username: String?
  let twitter: String?
  let createdAt: Date?
  var enabled: Bool
  let externalIntegration: ExternalIntegration?

  enum CodingKeys: String, CodingKey {
    case id, name, description, image, category, author, email, capabilities
    case uid, approved
    case `private`
    case status
    case chatPrompt = "chat_prompt"
    case memoryPrompt = "memory_prompt"
    case personaPrompt = "persona_prompt"
    case installs
    case ratingAvg = "rating_avg"
    case ratingCount = "rating_count"
    case isPaid = "is_paid"
    case price
    case paymentPlan = "payment_plan"
    case username, twitter
    case createdAt = "created_at"
    case enabled
    case externalIntegration = "external_integration"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    name = try container.decodeIfPresent(String.self, forKey: .name) ?? ""
    description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
    image = try container.decodeIfPresent(String.self, forKey: .image) ?? ""
    category = try container.decodeIfPresent(String.self, forKey: .category) ?? "other"
    author = try container.decodeIfPresent(String.self, forKey: .author) ?? ""
    email = try container.decodeIfPresent(String.self, forKey: .email)
    capabilities = try container.decodeIfPresent([String].self, forKey: .capabilities) ?? []
    uid = try container.decodeIfPresent(String.self, forKey: .uid)
    approved = try container.decodeIfPresent(Bool.self, forKey: .approved) ?? false
    `private` = try container.decodeIfPresent(Bool.self, forKey: .private) ?? false
    status = try container.decodeIfPresent(String.self, forKey: .status) ?? "under-review"
    chatPrompt = try container.decodeIfPresent(String.self, forKey: .chatPrompt)
    memoryPrompt = try container.decodeIfPresent(String.self, forKey: .memoryPrompt)
    personaPrompt = try container.decodeIfPresent(String.self, forKey: .personaPrompt)
    installs = try container.decodeIfPresent(Int.self, forKey: .installs) ?? 0
    ratingAvg = try container.decodeIfPresent(Double.self, forKey: .ratingAvg)
    ratingCount = try container.decodeIfPresent(Int.self, forKey: .ratingCount) ?? 0
    isPaid = try container.decodeIfPresent(Bool.self, forKey: .isPaid) ?? false
    price = try container.decodeIfPresent(Double.self, forKey: .price)
    paymentPlan = try container.decodeIfPresent(String.self, forKey: .paymentPlan)
    username = try container.decodeIfPresent(String.self, forKey: .username)
    twitter = (try? container.decodeIfPresent(String.self, forKey: .twitter)) ?? nil
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt)
    enabled = try container.decodeIfPresent(Bool.self, forKey: .enabled) ?? false
    externalIntegration = try container.decodeIfPresent(
      ExternalIntegration.self, forKey: .externalIntegration)
  }
}

/// App category
struct OmiAppCategory: Codable, Identifiable, Sendable {
  let id: String
  let title: String
}

/// App capability definition
struct OmiAppCapability: Codable, Identifiable, Sendable {
  let id: String
  let title: String
  let description: String?

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    title = try container.decodeIfPresent(String.self, forKey: .title) ?? ""
    description = try container.decodeIfPresent(String.self, forKey: .description)
  }

  enum CodingKeys: String, CodingKey {
    case id, title, description
  }
}

/// Auth step for external integration setup
struct AuthStep: Codable, Sendable {
  let name: String
  let url: String
}

/// External integration setup details
struct ExternalIntegration: Codable, Sendable {
  let authSteps: [AuthStep]
  let setupCompletedUrl: String?
  let setupInstructionsFilePath: String?
  let appHomeUrl: String?
  let isInstructionsUrl: Bool?

  enum CodingKeys: String, CodingKey {
    case authSteps = "auth_steps"
    case setupCompletedUrl = "setup_completed_url"
    case setupInstructionsFilePath = "setup_instructions_file_path"
    case appHomeUrl = "app_home_url"
    case isInstructionsUrl = "is_instructions_url"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    authSteps = try container.decodeIfPresent([AuthStep].self, forKey: .authSteps) ?? []
    setupCompletedUrl = try container.decodeIfPresent(String.self, forKey: .setupCompletedUrl)
    setupInstructionsFilePath = try container.decodeIfPresent(
      String.self, forKey: .setupInstructionsFilePath)
    appHomeUrl = try container.decodeIfPresent(String.self, forKey: .appHomeUrl)
    isInstructionsUrl = try container.decodeIfPresent(Bool.self, forKey: .isInstructionsUrl)
  }
}

/// App review
struct OmiAppReview: Codable, Identifiable {
  var id: String { uid }
  let uid: String
  let score: Int
  let review: String
  let response: String?
  let ratedAt: Date
  let editedAt: Date?

  enum CodingKeys: String, CodingKey {
    case uid, score, review, response
    case ratedAt = "rated_at"
    case editedAt = "edited_at"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    uid = try container.decode(String.self, forKey: .uid)
    score = try container.decodeIfPresent(Int.self, forKey: .score) ?? 0
    review = try container.decodeIfPresent(String.self, forKey: .review) ?? ""
    response = try container.decodeIfPresent(String.self, forKey: .response)
    ratedAt = try container.decodeIfPresent(Date.self, forKey: .ratedAt) ?? Date()
    editedAt = try container.decodeIfPresent(Date.self, forKey: .editedAt)
  }
}

// MARK: - V2 Apps Response Types

/// Capability info in v2/apps response
struct OmiCapabilityInfo: Codable, Sendable {
  let id: String
  let title: String
}

/// Pagination metadata in v2/apps response
struct OmiPaginationMeta: Codable, Sendable {
  let total: Int
  let count: Int
  let offset: Int
  let limit: Int
}

/// A single group in the v2/apps response
struct OmiAppGroup: Codable, Sendable {
  let capability: OmiCapabilityInfo
  let data: [OmiApp]
  let pagination: OmiPaginationMeta
}

/// Metadata in v2/apps response
struct OmiAppsV2Meta: Codable, Sendable {
  let capabilities: [OmiCapabilityInfo]
  let groupCount: Int
  let limit: Int
  let offset: Int
}

/// Full v2/apps grouped response
struct OmiAppsV2Response: Codable, Sendable {
  let groups: [OmiAppGroup]
  let meta: OmiAppsV2Meta
}

// MARK: - Apps API

extension APIClient {

  /// Fetches apps from the API
  func getApps(
    capability: String? = nil,
    category: String? = nil,
    limit: Int = 50,
    offset: Int = 0
  ) async throws -> [OmiApp] {
    var queryItems: [String] = [
      "limit=\(limit)",
      "offset=\(offset)",
    ]

    if let capability = capability {
      queryItems.append("capability=\(capability)")
    }

    if let category = category {
      queryItems.append("category=\(category)")
    }

    let endpoint = "v1/apps?\(queryItems.joined(separator: "&"))"
    return try await get(endpoint)
  }

  /// Fetches apps grouped by capability (v2 API - matches Flutter/Python backend)
  /// Returns groups: Featured, Integrations, Chat Assistants, Summary Apps, Realtime Notifications
  /// Fetches all apps with real rating data from v1/apps
  func getAppsWithRatings(limit: Int = 200) async throws -> [OmiApp] {
    return try await get("v1/apps?limit=\(limit)")
  }

  func getAppsV2(offset: Int = 0, limit: Int = 50) async throws -> OmiAppsV2Response {
    let endpoint = "v2/apps?offset=\(offset)&limit=\(limit)"
    return try await get(endpoint)
  }

  /// Searches apps with filters
  func searchApps(
    query: String? = nil,
    category: String? = nil,
    capability: String? = nil,
    minRating: Int? = nil,
    installedOnly: Bool = false,
    limit: Int = 50,
    offset: Int = 0
  ) async throws -> [OmiApp] {
    struct SearchResponse: Decodable {
      let data: [OmiApp]
    }

    var queryItems: [URLQueryItem] = [
      URLQueryItem(name: "limit", value: "\(limit)"),
      URLQueryItem(name: "offset", value: "\(offset)"),
    ]

    if let query = query, !query.isEmpty {
      queryItems.append(URLQueryItem(name: "q", value: query))
    }

    if let category = category {
      queryItems.append(URLQueryItem(name: "category", value: category))
    }

    if let capability = capability {
      queryItems.append(URLQueryItem(name: "capability", value: capability))
    }

    if let minRating = minRating {
      queryItems.append(URLQueryItem(name: "rating", value: "\(minRating)"))
    }

    if installedOnly {
      queryItems.append(URLQueryItem(name: "installed_apps", value: "true"))
    }

    var components = URLComponents()
    components.queryItems = queryItems
    let endpoint = "v2/apps/search?\(components.percentEncodedQuery ?? "")"
    let response: SearchResponse = try await get(endpoint)
    return response.data
  }

  /// Fetches app details by ID
  func getAppDetails(appId: String) async throws -> OmiAppDetails {
    return try await get("v1/apps/\(appId)")
  }

  /// Fetches app reviews
  func getAppReviews(appId: String) async throws -> [OmiAppReview] {
    return try await get("v1/apps/\(appId)/reviews")
  }

  /// Fetches user's enabled apps
  func getEnabledApps() async throws -> [OmiApp] {
    return try await get("v1/apps/enabled")
  }

  /// Enables an app for the current user
  func enableApp(appId: String) async throws {
    struct ToggleResponse: Decodable {
      let status: String?
      let detail: String?
    }
    let _: ToggleResponse = try await post("v1/apps/enable?app_id=\(appId)")
  }

  /// Disables an app for the current user
  func disableApp(appId: String) async throws {
    struct ToggleResponse: Decodable {
      let status: String?
      let detail: String?
    }
    let _: ToggleResponse = try await post("v1/apps/disable?app_id=\(appId)")
  }

  /// Checks if an external integration app's setup is complete
  func isAppSetupCompleted(url: String, uid: String) async -> Bool {
    // An empty/unknown completion URL means setup cannot be verified, so report
    // not-completed (consistent with the invalid-URL and network-failure paths
    // below). Returning true here would wrongly mark an unconfigured app as set up.
    guard !url.isEmpty else { return false }
    guard let fullUrl = URL(string: "\(url)?uid=\(uid)") else { return false }
    var request = URLRequest(url: fullUrl)
    request.httpMethod = "GET"
    do {
      let (data, _) = try await session.data(for: request)
      if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
        return json["is_setup_completed"] as? Bool ?? false
      }
    } catch {}
    return false
  }

  /// Submits a review for an app
  func submitAppReview(appId: String, score: Int, review: String) async throws -> OmiAppReview {
    struct ReviewRequest: Encodable {
      let app_id: String
      let score: Int
      let review: String
    }
    let body = ReviewRequest(app_id: appId, score: score, review: review)
    return try await post("v1/apps/review", body: body)
  }

  /// Fetches all app categories
  func getAppCategories() async throws -> [OmiAppCategory] {
    return try await get("v1/app-categories")
  }

  /// Fetches all app capabilities
  func getAppCapabilities() async throws -> [OmiAppCapability] {
    return try await get("v1/app-capabilities")
  }

  // MARK: - Conversation Reprocessing

  /// Reprocess a conversation with a specific app
  func reprocessConversation(conversationId: String, appId: String) async throws {
    struct ReprocessRequest: Encodable {
      let app_id: String
    }
    struct ReprocessResponse: Decodable {
      let success: Bool
      let message: String
    }
    let body = ReprocessRequest(app_id: appId)
    let _: ReprocessResponse = try await post(
      "v1/conversations/\(conversationId)/reprocess", body: body)
  }
}
