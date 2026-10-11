import Foundation

/// The backend-owned JIT proactivity switch is represented as a tri-state on
/// the client.  Unknown never activates the new lane; the released context
/// bucket pipeline remains the compatibility path in that case.
enum JITProactivityRolloutState: Equatable, Sendable {
  case enabled
  case disabled
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
