import Foundation
import OmiWAL

// MARK: - Persona API

extension APIClient {

  /// Fetches user's persona (if exists)
  func getPersona() async throws -> Persona? {
    return try await get("v1/personas")
  }

  /// Creates a new persona
  func createPersona(name: String, username: String? = nil) async throws -> Persona {
    struct CreateRequest: Encodable {
      let name: String
      let username: String?
    }
    let body = CreateRequest(name: name, username: username)
    return try await post("v1/personas", body: body)
  }

  /// Updates an existing persona
  func updatePersona(
    name: String? = nil,
    description: String? = nil,
    personaPrompt: String? = nil,
    image: String? = nil
  ) async throws -> Persona {
    struct UpdateRequest: Encodable {
      let name: String?
      let description: String?
      let personaPrompt: String?
      let image: String?

      enum CodingKeys: String, CodingKey {
        case name, description, image
        case personaPrompt = "persona_prompt"
      }
    }
    let body = UpdateRequest(
      name: name, description: description, personaPrompt: personaPrompt, image: image)
    return try await patch("v1/personas", body: body)
  }

  /// Deletes user's persona
  func deletePersona() async throws {
    try await delete("v1/personas")
  }

  /// Regenerates persona prompt from current public memories
  func regeneratePersonaPrompt() async throws -> GeneratePromptResponse {
    struct EmptyRequest: Encodable {}
    return try await post("v1/personas/generate-prompt", body: EmptyRequest())
  }

  /// Checks if a username is available
  func checkPersonaUsername(_ username: String) async throws -> UsernameAvailableResponse {
    return try await get("v1/personas/check-username?username=\(username)")
  }
}
// MARK: - Persona Models

/// AI Persona model
struct Persona: Codable, Identifiable {
  let id: String
  let uid: String
  let name: String
  let username: String?
  let description: String
  let image: String
  let category: String
  let capabilities: [String]
  let personaPrompt: String?
  let approved: Bool
  let status: String
  let isPrivate: Bool
  let author: String
  let email: String?
  let createdAt: Date
  let updatedAt: Date
  let publicMemoriesCount: Int?

  enum CodingKeys: String, CodingKey {
    case id, uid, name, username, description, image, category, capabilities
    case personaPrompt = "persona_prompt"
    case approved, status
    case isPrivate = "private"
    case author, email
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case publicMemoriesCount = "public_memories_count"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    uid = try container.decode(String.self, forKey: .uid)
    name = try container.decode(String.self, forKey: .name)
    username = try container.decodeIfPresent(String.self, forKey: .username)
    description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
    image = try container.decodeIfPresent(String.self, forKey: .image) ?? ""
    category = try container.decodeIfPresent(String.self, forKey: .category) ?? ""
    capabilities = try container.decodeIfPresent([String].self, forKey: .capabilities) ?? []
    personaPrompt = try container.decodeIfPresent(String.self, forKey: .personaPrompt)
    approved = try container.decodeIfPresent(Bool.self, forKey: .approved) ?? false
    status = try container.decodeIfPresent(String.self, forKey: .status) ?? "under-review"
    isPrivate = try container.decodeIfPresent(Bool.self, forKey: .isPrivate) ?? false
    author = try container.decodeIfPresent(String.self, forKey: .author) ?? ""
    email = try container.decodeIfPresent(String.self, forKey: .email)
    createdAt = try container.decode(Date.self, forKey: .createdAt)
    updatedAt = try container.decode(Date.self, forKey: .updatedAt)
    publicMemoriesCount = try container.decodeIfPresent(Int.self, forKey: .publicMemoriesCount)
  }

  /// Whether the persona has a generated prompt
  var hasPrompt: Bool {
    personaPrompt != nil && !personaPrompt!.isEmpty
  }

  /// Status display text
  var statusText: String {
    switch status {
    case "approved": return "Active"
    case "under-review": return "Pending Review"
    case "rejected": return "Rejected"
    default: return status.capitalized
    }
  }

  /// Status color
  var statusColor: String {
    switch status {
    case "approved": return "green"
    case "under-review": return "orange"
    case "rejected": return "red"
    default: return "gray"
    }
  }
}

/// Response for prompt generation
struct GeneratePromptResponse: Codable {
  let personaPrompt: String
  let description: String
  let memoriesUsed: Int

  enum CodingKeys: String, CodingKey {
    case personaPrompt = "persona_prompt"
    case description
    case memoriesUsed = "memories_used"
  }
}

/// Response for username availability check
struct UsernameAvailableResponse: Codable {
  let available: Bool
  let username: String
}
