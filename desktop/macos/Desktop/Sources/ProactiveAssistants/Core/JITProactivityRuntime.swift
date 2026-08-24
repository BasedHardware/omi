import Foundation

/// Runtime admission for the additive JIT lane.
///
/// The rollout endpoint owns enrollment, but the current trigger projection
/// intentionally lacks an authoritative durable action/receipt contract. An
/// enabled rollout therefore still preserves the released context-bucket path:
/// ambient must not outrank an unseen planned trigger, and a trigger ID alone
/// cannot safely purchase a full agent turn.
actor JITProactivityRuntime {
  static let shared = JITProactivityRuntime()

  typealias FlagResolver = @Sendable (RuntimeOwnerAuthorizationSnapshot) async -> JITProactivityFlags
  private let flags: FlagResolver

  init(
    flags: @escaping FlagResolver = { snapshot in
      await ProactiveLaneClient.shared.jitProactivityFlags(authorizationSnapshot: snapshot)
    }
  ) {
    self.flags = flags
  }

  func admission(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async -> JITProactivityDecision {
    let resolved = await flags(authorizationSnapshot)
    guard resolved.permitsNewLane else {
      return JITProactivityPolicy.decide(flags: resolved, planned: [], ambient: [])
    }
    return .legacyContextBucketFallback(reason: "authoritative_trigger_action_unavailable")
  }
}
