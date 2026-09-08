import Foundation

/// Typed wire contracts for the existing sync-audio endpoints. They live next
/// to the archive rather than extending the generated surface because the
/// current OpenAPI describes these payloads as `OmiAnyCodable`.
struct CaptureAudioPrecacheResponse: Decodable, Equatable {
  let status: String
  let message: String?
  let audioFileCount: Int?

  enum CodingKeys: String, CodingKey {
    case status, message
    case audioFileCount = "audio_file_count"
  }
}

struct CaptureAudioURLFile: Decodable, Equatable, Identifiable {
  let id: String
  let status: String
  let signedURL: URL?
  let contentType: String?
  let duration: TimeInterval

  enum CodingKeys: String, CodingKey {
    case id, status
    case signedURL = "signed_url"
    case contentType = "content_type"
    case duration
  }
}

struct CaptureAudioURLSpan: Decodable, Equatable {
  let fileID: String
  let wallOffset: TimeInterval
  let artifactOffset: TimeInterval
  let length: TimeInterval

  enum CodingKeys: String, CodingKey {
    case fileID = "file_id"
    case wallOffset = "wall_offset"
    case artifactOffset = "artifact_offset"
    case length = "len"
  }
}

struct CaptureAudioURLArtifact: Decodable, Equatable {
  let status: String
  let signedURL: URL?
  let contentType: String?
  let duration: TimeInterval?
  let capturedDuration: TimeInterval?
  let spans: [CaptureAudioURLSpan]

  enum CodingKeys: String, CodingKey {
    case status
    case signedURL = "signed_url"
    case contentType = "content_type"
    case duration
    case capturedDuration = "captured_duration"
    case spans
  }
}

struct CaptureAudioURLsResponse: Decodable, Equatable {
  let audioFiles: [CaptureAudioURLFile]
  let conversationAudio: CaptureAudioURLArtifact?
  let pollAfterMs: Int?

  enum CodingKeys: String, CodingKey {
    case audioFiles = "audio_files"
    case conversationAudio = "conversation_audio"
    case pollAfterMs = "poll_after_ms"
  }
}

extension APIClient {
  /// Requests backend-side preparation only. Signed URLs are intentionally
  /// never logged or persisted by this client.
  func precacheCaptureAudio(conversationID: String) async throws -> CaptureAudioPrecacheResponse {
    try await post("v1/sync/audio/\(conversationID)/precache")
  }

  func captureAudioURLs(conversationID: String) async throws -> CaptureAudioURLsResponse {
    try await get("v1/sync/audio/\(conversationID)/urls")
  }
}
