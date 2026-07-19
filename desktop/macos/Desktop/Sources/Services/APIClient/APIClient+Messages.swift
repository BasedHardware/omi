import Foundation
import OmiWAL

// MARK: - Insight Models
/// Empty body for POST requests with no body
struct EmptyBody: Encodable {}

// MARK: - Chat Messages API (Persistence)

extension APIClient {

  /// Clear chat message history
  func deleteMessages(
    appId: String? = nil,
    expectedOwnerId: String? = nil
  ) async throws -> MessageDeleteResponse {
    var endpoint = "v2/desktop/messages"
    if let appId = appId {
      endpoint += "?app_id=\(appId)"
    }

    guard let url = URL(string: baseURL + endpoint) else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "DELETE"
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: true,
      expectedAuthOwnerId: expectedOwnerId
    )

    return try await performRequest(
      request,
      authPolicy: expectedOwnerId.map { .ownerBound($0) } ?? .default
    )
  }

  /// Rate a message (thumbs up/down)
  /// - Parameters:
  ///   - messageId: The message ID to rate
  ///   - rating: 1 for thumbs up, -1 for thumbs down, nil to clear rating
  func rateMessage(messageId: String, rating: Int?) async throws {
    struct RateRequest: Encodable {
      let rating: Int?
      let app_version: String?
    }
    let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
    let body = RateRequest(rating: rating, app_version: version)
    let _: MessageStatusResponse = try await patch(
      "v2/desktop/messages/\(messageId)/rating", body: body)
  }

  /// Share chat messages and get a shareable URL
  func shareChatMessages(messageIds: [String]) async throws -> ShareChatResponse {
    struct ShareRequest: Encodable {
      let message_ids: [String]
    }
    let body = ShareRequest(message_ids: messageIds)
    return try await post("v2/messages/share", body: body)
  }

  /// Upload one or more files to be attached to a chat message.
  /// Mirrors the Flutter app's `uploadFilesServer` (lib/backend/http/api/messages.dart) —
  /// same `/v2/files` multipart endpoint, same response shape.
  func uploadChatFiles(
    _ uploads: [(data: Data, fileName: String, mimeType: String)],
    appId: String? = nil
  ) async throws -> [ChatFileResponse] {
    var endpoint = "v2/files"
    if let appId = appId, !appId.isEmpty, appId != "no_selected" {
      endpoint += "?app_id=\(appId)"
    }
    guard let url = URL(string: baseURL + endpoint) else {
      throw APIError.invalidResponse
    }

    let boundary = "Boundary-\(UUID().uuidString)"
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)
    request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

    var body = Data()
    let lineBreak = "\r\n"
    for upload in uploads {
      body.append(Data("--\(boundary)\(lineBreak)".utf8))
      body.append(
        Data(
          "Content-Disposition: form-data; name=\"files\"; filename=\"\(upload.fileName)\"\(lineBreak)"
            .utf8))
      body.append(Data("Content-Type: \(upload.mimeType)\(lineBreak)\(lineBreak)".utf8))
      body.append(upload.data)
      body.append(Data(lineBreak.utf8))
    }
    body.append(Data("--\(boundary)--\(lineBreak)".utf8))
    request.httpBody = body

    return try await performRequest(request)
  }

  // MARK: - Sync local files (WAL upload)

  /// Upload-only POST to `/v2/sync-local-files`. Mirrors Flutter `uploadLocalFilesV2`.
  func uploadLocalFilesV2(
    fileURLs: [URL],
    conversationId: String? = nil
  ) async throws -> UploadLocalFilesResult {
    guard var components = URLComponents(string: baseURL + "v2/sync-local-files") else {
      throw APIError.invalidResponse
    }
    if let conversationId, !conversationId.isEmpty {
      components.queryItems = [URLQueryItem(name: "conversation_id", value: conversationId)]
    }
    guard let url = components.url else {
      throw APIError.syncUploadRejected(reason: "Invalid sync-local-files URL")
    }
    let request = try await buildSyncLocalFilesMultipartRequest(url: url, fileURLs: fileURLs)
    return try await performSyncLocalFilesUpload(request)
  }

  /// Single GET of a sync job's status — no polling loop.
  func fetchSyncJobStatus(jobId: String) async -> SyncJobFetch {
    let endpoint = "v2/sync-local-files/\(jobId)"
    guard let url = URL(string: baseURL + endpoint) else {
      return SyncJobFetch(outcome: .transient)
    }
    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.allHTTPHeaderFields = try? await buildHeaders(requireAuth: true)

    guard let (data, response) = try? await session.data(for: request),
      let http = response as? HTTPURLResponse
    else {
      return SyncJobFetch(outcome: .transient)
    }

    if http.statusCode == 404 {
      return SyncJobFetch(outcome: .notFound)
    }
    // 403 means the caller is not permitted to access this sync job. Unlike a
    // transient transport failure, re-polling will not resolve it — the upload
    // path already refreshed auth on 401, so a 403 here is a durable permission
    // failure. Surface it as `.forbidden` so the reconciler reverts the WAL to
    // `.miss` for re-upload (the backend dedupes by conversation/timestamp)
    // instead of polling forever.
    if http.statusCode == 403 {
      return SyncJobFetch(outcome: .forbidden)
    }
    guard http.statusCode == 200 else {
      return SyncJobFetch(outcome: .transient)
    }

    do {
      let status = try decoder.decode(SyncJobStatusResponse.self, from: data)
      return SyncJobFetch(outcome: .ok, status: status)
    } catch {
      return SyncJobFetch(outcome: .transient)
    }
  }

  private func buildSyncLocalFilesMultipartRequest(url: URL, fileURLs: [URL]) async throws -> URLRequest {
    let boundary = "Boundary-\(UUID().uuidString)"
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    var headers = try await buildHeaders(requireAuth: true)
    headers.removeValue(forKey: "Content-Type")
    request.allHTTPHeaderFields = headers
    request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

    var body = Data()
    let lineBreak = "\r\n"
    for fileURL in fileURLs {
      // Legacy desktop WAL files on disk may still use byte-length `_fsN` tokens;
      // normalize at upload time so the backend Opus decoder gets sample-frame size.
      let fileName = WALSyncUploadFileName.normalizedForUpload(fileURL.lastPathComponent)
      let fileData = try Data(contentsOf: fileURL)
      body.append(Data("--\(boundary)\(lineBreak)".utf8))
      body.append(
        Data(
          "Content-Disposition: form-data; name=\"files\"; filename=\"\(fileName)\"\(lineBreak)"
            .utf8))
      body.append(Data("Content-Type: application/octet-stream\(lineBreak)\(lineBreak)".utf8))
      body.append(fileData)
      body.append(Data(lineBreak.utf8))
    }
    body.append(Data("--\(boundary)--\(lineBreak)".utf8))
    request.httpBody = body
    return request
  }

  private func performSyncLocalFilesUpload(_ request: URLRequest, retriedAuth: Bool = false) async throws
    -> UploadLocalFilesResult
  {
    let (data, http) = try await performAuthenticatedData(for: request, retriedAuth: retriedAuth)

    if http.statusCode == 200 {
      let completed = try decoder.decode(SyncLocalFilesResultResponse.self, from: data)
      // A legacy synchronous path can return 200 even when one or more
      // segments failed. Treat it as a retryable upload failure so WALService
      // preserves the local recording instead of acknowledging it as synced.
      if completed.failedSegments > 0 {
        throw APIError.syncUploadRejected(reason: "Transcription incomplete; retrying retained audio")
      }
      return .done(completed)
    }
    if http.statusCode == 202 {
      let start = try decoder.decode(SyncJobStartResponse.self, from: data)
      guard !start.jobId.isEmpty else {
        throw APIError.syncUploadRejected(reason: "Upload accepted but no job id returned")
      }
      return .queued(jobId: start.jobId)
    }
    if http.statusCode == 429 {
      let retryAfter = Self.parseRetryAfterSeconds(from: http)
      throw APIError.syncRateLimited(retryAfterSeconds: retryAfter)
    }
    if http.statusCode == 400 {
      throw APIError.syncUploadRejected(reason: "Audio file could not be processed by server")
    }
    if http.statusCode == 413 {
      throw APIError.syncUploadRejected(reason: "Audio file is too large to upload")
    }
    if http.statusCode >= 500 {
      throw APIError.syncUploadRejected(reason: "Server is temporarily unavailable")
    }
    throw APIError.syncUploadRejected(reason: "Upload failed unexpectedly")
  }

  private static func parseRetryAfterSeconds(from response: HTTPURLResponse) -> Int? {
    guard let raw = response.value(forHTTPHeaderField: "Retry-After") else { return nil }
    return Int(raw.trimmingCharacters(in: .whitespacesAndNewlines))
  }

}
/// Response shape for `POST /v2/files` — mirrors backend `FileChat` model.
struct ChatFileResponse: Codable {
  let id: String
  let name: String?
  let mimeType: String?
  let thumbnail: String?
  let thumbName: String?
  let openaiFileId: String?

  enum CodingKeys: String, CodingKey {
    case id
    case name
    case thumbnail
    case mimeType = "mime_type"
    case thumbName = "thumb_name"
    case openaiFileId = "openai_file_id"
  }
}

/// Response from rating a message
struct MessageStatusResponse: Codable {
  let status: String
}

// MARK: - Sync local files (WAL upload)

/// Outcome of POST `/v2/sync-local-files` — exactly one of `jobId` (202) or `completed` (200).
enum UploadLocalFilesResult: Equatable {
  case queued(jobId: String)
  case done(SyncLocalFilesResultResponse)

  var jobId: String? {
    if case .queued(let jobId) = self { return jobId }
    return nil
  }
}

struct SyncLocalFilesResultResponse: Codable, Equatable {
  let newMemories: [String]
  let updatedMemories: [String]
  let failedSegments: Int
  let totalSegments: Int
  let errors: [String]

  enum CodingKeys: String, CodingKey {
    case newMemories = "new_memories"
    case updatedMemories = "updated_memories"
    case failedSegments = "failed_segments"
    case totalSegments = "total_segments"
    case errors
  }
}

struct SyncJobStartResponse: Codable, Equatable {
  let jobId: String
  let status: String
  let totalFiles: Int
  let totalSegments: Int
  let pollAfterMs: Int

  enum CodingKeys: String, CodingKey {
    case jobId = "job_id"
    case status
    case totalFiles = "total_files"
    case totalSegments = "total_segments"
    case pollAfterMs = "poll_after_ms"
  }
}

struct SyncJobStatusResponse: Codable, Equatable {
  let jobId: String
  let status: String
  let totalSegments: Int
  let processedSegments: Int
  let successfulSegments: Int
  let failedSegments: Int
  let result: SyncLocalFilesResultResponse?
  let error: String?

  var isTerminal: Bool {
    status == "completed" || status == "partial_failure" || status == "failed"
  }

  enum CodingKeys: String, CodingKey {
    case jobId = "job_id"
    case status
    case totalSegments = "total_segments"
    case processedSegments = "processed_segments"
    case successfulSegments = "successful_segments"
    case failedSegments = "failed_segments"
    case result
    case error
  }
}

enum SyncJobFetchOutcome: Equatable {
  case ok
  case notFound
  case forbidden
  case transient
}

struct SyncJobFetch: Equatable {
  let outcome: SyncJobFetchOutcome
  let status: SyncJobStatusResponse?

  init(outcome: SyncJobFetchOutcome, status: SyncJobStatusResponse? = nil) {
    self.outcome = outcome
    self.status = status
  }
}

/// Response from sharing chat messages
struct ShareChatResponse: Codable {
  let url: String
  let token: String
}
