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
/// Attach only when funded processing is known unavailable. Unknown funding
/// and BYOK leave the decision to the server. Thermal
/// `.serious+` defers generation but will send a hash-matching stored
/// blob so a retry does not drop a finished local summary.
enum LocalProjectionFinalization {
  enum Decision: Equatable, Sendable {
    case skip
    case generate
    case storedOnly
  }

  /// Server allowance is authoritative when present. Current main's basic-only
  /// managed-compute gate is the fallback only without an allowance snapshot.
  /// TODO(#21488 follow-up): consume a dedicated funded-processing capability
  /// after #21488 and the backend fold; that PR projects funding via this field.
  static func fundingUnavailable(
    subscription: UserSubscriptionResponse?, isByokActive: Bool
  ) -> Bool {
    guard !isByokActive, let subscription else { return false }
    if SubscriptionEntitlement.hasByokFeature(subscription.subscription.features) { return false }
    if let allowance = subscription.transcriptionAllowance {
      switch allowance.mode {
      case "managed": return false
      case "on_device":
        guard allowance.remainingSeconds == 0 else { return false }
        switch allowance.reason {
        case "usage_budget_exhausted": return true  // Ladder shared funded budget (#21488).
        case "plan_allowance_exhausted", "subscription_inactive":
          // On current main this field measures STT separately from processing.
          // A paid user's STT cap is not proof that summary funding is exhausted.
          return subscription.subscription.plan == .basic
        default: return false  // Includes usage_invalid and allowance_unavailable.
        }
      default: return false
      }
    }
    return subscription.subscription.plan == .basic
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
