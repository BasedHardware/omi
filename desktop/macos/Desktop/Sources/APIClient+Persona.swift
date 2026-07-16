import Foundation

// MARK: - Persona API
// Extracted from APIClient.swift to keep the consolidated client under its
// line-count ratchet (test_desktop_rest_inventory.py::test_apiclient_swift_line_count_ratchet).

extension APIClient {

  /// Fetches user's persona (if exists)
  func getPersona() async throws -> Persona? {
    return try await get("v1/personas")
  }

  /// Auto-create a developer API key for the user's persona app.
  /// Calls POST /v1/apps/{app_id}/keys using the user's Firebase auth.
  /// Uses the default `baseURL` (api.omi.me in production).
  func createAppKey(appId: String) async throws -> String {
    struct KeyResponse: Decodable {
      let id: String
      let secret: String
      let label: String
    }
    let response: KeyResponse = try await post("v1/apps/\(appId)/keys")
    return response.secret
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

  /// Get or create the user's persona via POST /v1/user/persona.
  /// Uses the default `baseURL` (resolves via DesktopBackendEnvironment,
  /// which is api.omi.me in production). The backendURL override was
  /// removed to prevent auth header leakage to untrusted URLs.
  /// Identified by cubic + maintainer review.
  func getOrCreatePersona() async throws -> Persona {
    return try await post("v1/user/persona")
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
