import Foundation

/// Summarizer seam used by conversation-end attach. Production is
/// `ConversationChunkSummarizer`; tests inject a counter or fixture.
protocol ConversationSummarizing: Sendable {
  func summarize(
    sessionId: Int64,
    segments: [TranscriptHash.Segment],
    startedAt: Date
  ) async throws -> StoredClientProjection

  func peekStored(sessionId: Int64) async throws -> StoredClientProjection?
}

extension ConversationChunkSummarizer: ConversationSummarizing {
  func peekStored(sessionId: Int64) async throws -> StoredClientProjection? {
    try await store.load(sessionId: sessionId)
  }
}

/// When S11 attaches the S10 stored `client_processing` blob.
///
/// Identified basic (`planGated`) is the only plan that attaches. Paid,
/// unknown, and BYOK fail open so the server still decides. Thermal
/// `.serious+` defers generation but will send a hash-matching stored
/// blob so a retry does not drop a finished local summary.
enum LocalProjectionFinalization {
  enum Decision: Equatable, Sendable {
    case skip
    case generate
    case storedOnly
  }

  static func decision(
    flagEnabled: Bool,
    entitlement: SubscriptionEntitlementDecision,
    thermalState: ProcessInfo.ThermalState
  ) -> Decision {
    guard flagEnabled, entitlement == .planGated else { return .skip }
    switch thermalState {
    case .serious, .critical:
      return .storedOnly
    case .nominal, .fair:
      return .generate
    @unknown default:
      return .generate
    }
  }

  static func projection(
    decision: Decision,
    sessionId: Int64,
    segments: [TranscriptHash.Segment],
    startedAt: Date,
    summarizer: (any ConversationSummarizing)?
  ) async -> Data? {
    guard decision != .skip, let summarizer else { return nil }
    do {
      switch decision {
      case .skip:
        return nil
      case .storedOnly:
        guard let stored = try await summarizer.peekStored(sessionId: sessionId) else {
          return nil
        }
        let digest = TranscriptHash.sha256(segments: segments)
        guard stored.transcriptSha256 == digest else { return nil }
        return stored.json
      case .generate:
        let stored = try await summarizer.summarize(
          sessionId: sessionId,
          segments: segments,
          startedAt: startedAt
        )
        return stored.json
      }
    } catch {
      return nil
    }
  }
}

extension APIClient.UploadSegment {
  var hashSegment: TranscriptHash.Segment {
    TranscriptHash.Segment(
      speaker: speaker,
      speakerId: speaker_id,
      isUser: is_user,
      personId: person_id,
      text: text
    )
  }
}
