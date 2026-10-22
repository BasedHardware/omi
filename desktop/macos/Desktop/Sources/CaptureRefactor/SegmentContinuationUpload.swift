import Foundation

extension APIClient {
  /// The client flag is independent of the server cohort. A disabled server
  /// rejects continuation explicitly; callers keep the durable local recording.
  func createConversationFromSegmentChunks(
    _ request: CreateConversationFromSegmentsRequest,
    authorization supplied: RuntimeOwnerAuthorizationSnapshot?
  )
    async throws -> CreateConversationFromSegmentsResponse
  {
    guard let authorization = supplied, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
      throw AuthError.userChangedDuringRequest
    }
    let chunks = SegmentContinuationUpload.chunks(request.transcript_segments)
    guard chunks.count <= 128 else { throw APIError.invalidResponse }
    var result: CreateConversationFromSegmentsResponse?
    for (index, chunk) in chunks.enumerated() {
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { throw AuthError.userChangedDuringRequest }
      let payload = SegmentContinuationUpload.Payload(
        request: request, segments: chunk,
        index: index, count: chunks.count)
      let response: CreateConversationFromSegmentsResponse = try await post(
        "v1/conversations/from-segments", body: payload, customBaseURL: nil, authorizationSnapshot: authorization,
        requestTimeout: 180)
      result = response
      if response.status == "deleted" { return response }
    }
    guard let result else { throw APIError.invalidResponse }
    invalidateConversationsCountCache()
    return result
  }
}

enum SegmentContinuationUpload {
  static func finishedAt(startedAt: Date, finishedAt: Date?, segmentEnds: [Double]) -> Date? {
    if let finishedAt { return finishedAt }
    guard let end = segmentEnds.filter({ $0.isFinite && $0 > 0 }).max() else { return nil }
    return startedAt.addingTimeInterval(end)
  }

  static func chunks<T>(_ segments: [T]) -> [[T]] {
    stride(from: 0, to: segments.count, by: 500).map { Array(segments[$0..<min($0 + 500, segments.count)]) }
  }

  struct Payload: Encodable {
    let request: APIClient.CreateConversationFromSegmentsRequest
    let segments: [APIClient.UploadSegment]
    let index: Int
    let count: Int
    enum CodingKeys: String, CodingKey {
      case segments = "transcript_segments", session = "client_session_id"
      case index = "chunk_index", count = "chunk_count", source, language
      case started = "started_at", finished = "finished_at", role = "conversation_role"
      case reason = "conversation_finalization_reason", projection = "client_processing"
      case evidence = "capture_evidence"
    }
    func encode(to encoder: Encoder) throws {
      var container = encoder.container(keyedBy: CodingKeys.self)
      try container.encode(segments, forKey: .segments)
      try container.encode(request.client_conversation_id, forKey: .session)
      try container.encode(index, forKey: .index)
      try container.encode(count, forKey: .count)
      try container.encode(request.source, forKey: .source)
      try container.encode(request.language, forKey: .language)
      try container.encodeIfPresent(request.started_at, forKey: .started)
      try container.encodeIfPresent(request.finished_at, forKey: .finished)
      try container.encode(request.conversation_role, forKey: .role)
      try container.encodeIfPresent(request.conversation_finalization_reason, forKey: .reason)
      try container.encodeIfPresent(request.captureEvidence, forKey: .evidence)
      if index == count - 1, let data = request.client_processing {
        try container.encode(ClientProcessingContract.decode(data), forKey: .projection)
      }
    }
  }
}
