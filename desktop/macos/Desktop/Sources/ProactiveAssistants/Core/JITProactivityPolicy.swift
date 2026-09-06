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

/// Whether the current owner's proactivity is routed through the JIT lanes.
///
/// Set by `JITProactivityCoordinator` from the backend rollout verdict on every
/// context visit. Legacy per-frame producers that the JIT lanes replace (the
/// focus-nudge assistant) read it so the two never run side by side for one
/// owner. It is derived state, never authority: the backend flag and kill
/// switch remain the only enrolment path.
@MainActor
enum JITProactivityLaneState {
  private static var activeOwnerID: String?

  /// True only for the owner the backend last admitted. A different or absent
  /// owner reads false, so sign-out and account transitions need no reset.
  static func isActive(ownerID: String?) -> Bool {
    guard let ownerID, !ownerID.isEmpty else { return false }
    return activeOwnerID == ownerID
  }

  static func update(ownerID: String, active: Bool) {
    if active {
      activeOwnerID = ownerID
    } else if activeOwnerID == ownerID {
      activeOwnerID = nil
    }
  }
}

enum JITAmbientNanoTriage: Equatable, Sendable {
  case approved
  case rejected
  case unknown
}

struct JITProactivityFlags: Equatable, Sendable {
  let rollout: JITProactivityRolloutState
  let killSwitch: JITProactivityRolloutState
  /// The backend's own admission verdict from `/v1/jit/rollout-decision`.
  /// Servers that predate the field leave it absent; the rollout +
  /// kill-switch pair remains the fallback derivation.
  let effective: JITProactivityRolloutState
  /// Whether the decision response carried `kill_switch` at all. An absent
  /// field is wire compatibility, not an unknown-off veto; a present
  /// `unknown` still fails closed.
  let killSwitchPresent: Bool
  /// Optional server capability for the qualification-only full-turn budget.
  /// Older servers omit it; omission keeps the released JIT route unchanged.
  let budgetContractVersion: String?

  init(
    rollout: JITProactivityRolloutState,
    killSwitch: JITProactivityRolloutState,
    effective: JITProactivityRolloutState = .unknown,
    killSwitchPresent: Bool = true,
    budgetContractVersion: String? = nil
  ) {
    self.rollout = rollout
    self.killSwitch = killSwitch
    self.effective = effective
    self.killSwitchPresent = killSwitchPresent
    self.budgetContractVersion = budgetContractVersion
  }

  /// The server-computed `effective` verdict owns admission: the client must
  /// not re-derive a stricter verdict from the raw flags. The complete,
  /// known-good rollout + kill-switch pair remains the fallback for servers
  /// that predate `effective`, and unknown still fails closed.
  var permitsNewLane: Bool {
    if effective == .enabled { return true }
    if effective == .disabled { return false }
    guard rollout == .enabled else { return false }
    return killSwitch == .disabled || !killSwitchPresent
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
      if flags.killSwitch == .enabled {
        reason = "kill_switch"
      } else if flags.rollout == .unknown || (flags.killSwitch == .unknown && flags.killSwitchPresent) {
        // Only a `kill_switch` the server actually sent can report as
        // unknown; an absent field is compatibility, not an unknown state.
        reason = "rollout_unknown"
      } else {
        reason = "rollout_disabled"
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
