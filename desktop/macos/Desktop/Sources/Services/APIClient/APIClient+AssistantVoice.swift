import Foundation

/// A selectable voice for floating-bar replies, decoded from the served catalog.
struct AssistantVoiceEntry: Decodable, Equatable, Sendable {
  let id: String
  let name: String
}

struct AssistantVoiceCatalogResponse: Decodable, Equatable, Sendable {
  let voices: [AssistantVoiceEntry]
  let defaultVoiceId: String

  enum CodingKeys: String, CodingKey {
    case voices
    case defaultVoiceId = "default_voice_id"
  }
}

struct AssistantVoicePreferenceResponse: Decodable, Equatable, Sendable {
  let voiceId: String

  enum CodingKeys: String, CodingKey {
    case voiceId = "voice_id"
  }
}

struct AssistantVoicePreferenceUpdate: Encodable, Sendable {
  let voiceId: String

  enum CodingKeys: String, CodingKey {
    case voiceId = "voice_id"
  }
}

extension APIClient {

  func getAssistantVoiceCatalog(
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AssistantVoiceCatalogResponse {
    try await get(
      "v1/tts/voices",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func getAssistantVoicePreference(
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AssistantVoicePreferenceResponse {
    try await get(
      "v1/users/voice",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func setAssistantVoicePreference(
    voiceId: String,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AssistantVoicePreferenceResponse {
    try await patch(
      "v1/users/voice",
      body: AssistantVoicePreferenceUpdate(voiceId: voiceId),
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }
}
