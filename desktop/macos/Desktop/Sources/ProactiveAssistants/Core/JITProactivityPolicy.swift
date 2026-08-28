import Foundation

/// The backend-owned JIT proactivity switch is represented as a tri-state on
/// the client.  Unknown never activates the new lane; the released context
/// bucket pipeline remains the compatibility path in that case.
enum JITProactivityRolloutState: Equatable, Sendable {
  case enabled
  case disabled
  case unknown
}

enum JITProactivityLane: String, Equatable, Sendable {
  case planned
  case ambient
}

enum JITAmbientNanoTriage: Equatable, Sendable {
  case approved
  case rejected
  case unknown
}

struct JITProactivityFlags: Equatable, Sendable {
  let rollout: JITProactivityRolloutState
  let killSwitch: JITProactivityRolloutState

  /// Only a complete, known-good pair activates the additive lane.
  var permitsNewLane: Bool {
    rollout == .enabled && killSwitch == .disabled
  }
}

struct JITPlannedTriggerCandidate: Equatable, Sendable {
  let id: String
  let continuityKey: String
  let matched: Bool
  let standingIntent: Bool
  let wakeupsRemaining: Int

  var isDeliverable: Bool {
    !id.isEmpty && !continuityKey.isEmpty && matched && standingIntent && wakeupsRemaining > 0
  }
}

struct JITAmbientContextCandidate: Equatable, Sendable {
  let id: String
  let continuityKey: String
  let materialChange: Bool
  let locallyNovel: Bool
  let locallyRelevant: Bool
  let nanoTriage: JITAmbientNanoTriage
  let fullAgentTurnsRemaining: Int

  var isDeliverable: Bool {
    !id.isEmpty
      && !continuityKey.isEmpty
      && materialChange
      && locallyNovel
      && locallyRelevant
      && nanoTriage == .approved
      && fullAgentTurnsRemaining > 0
  }
}

enum JITProactivityDecision: Equatable, Sendable {
  /// The new lane is off or cannot be authorized. Existing context buckets
  /// continue unchanged; this is not a new notification.
  case legacyContextBucketFallback(reason: String)
  case deliver(lane: JITProactivityLane, id: String, continuityKey: String)
  case suppressed(reason: String)
}

enum JITProactivityPolicy {
  /// Select at most one delivery for a context transition.
  ///
  /// Planned, agent-authored standing triggers always outrank the ambient
  /// lane.  Ambient candidates are deliberately cheap and require every local
  /// guard plus one bounded nano triage; if the triage is unknown, no provider
  /// call is purchased.  ``deliveredContinuityKeys`` joins both lanes so an
  /// ambient candidate cannot race a planned delivery into a duplicate turn.
  static func decide(
    flags: JITProactivityFlags,
    planned: [JITPlannedTriggerCandidate],
    ambient: [JITAmbientContextCandidate],
    deliveredContinuityKeys: Set<String> = []
  ) -> JITProactivityDecision {
    guard flags.permitsNewLane else {
      let reason: String
      switch (flags.rollout, flags.killSwitch) {
      case (_, .enabled): reason = "kill_switch"
      case (.unknown, _), (_, .unknown): reason = "rollout_unknown"
      default: reason = "rollout_disabled"
      }
      return .legacyContextBucketFallback(reason: reason)
    }

    // Sorting is part of the policy: an API/SQLite iteration order must not
    // decide which standing trigger gets the one available full turn.
    let plannedCandidate =
      planned
      .filter { $0.isDeliverable && !deliveredContinuityKeys.contains($0.continuityKey) }
      .sorted { lhs, rhs in
        if lhs.continuityKey != rhs.continuityKey { return lhs.continuityKey < rhs.continuityKey }
        return lhs.id < rhs.id
      }
      .first
    if let plannedCandidate {
      return .deliver(
        lane: .planned,
        id: plannedCandidate.id,
        continuityKey: plannedCandidate.continuityKey
      )
    }

    let ambientCandidate =
      ambient
      .filter { $0.isDeliverable && !deliveredContinuityKeys.contains($0.continuityKey) }
      .sorted { lhs, rhs in
        if lhs.continuityKey != rhs.continuityKey { return lhs.continuityKey < rhs.continuityKey }
        return lhs.id < rhs.id
      }
      .first
    if let ambientCandidate {
      return .deliver(
        lane: .ambient,
        id: ambientCandidate.id,
        continuityKey: ambientCandidate.continuityKey
      )
    }

    return .suppressed(reason: "no_eligible_candidate")
  }
}
