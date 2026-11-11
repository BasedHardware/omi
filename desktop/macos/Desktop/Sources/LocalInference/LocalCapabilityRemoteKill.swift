/// Existing free-tier emergency stop, read from Omi's flag store only. Unknown is
/// not killed. No flag fetch, exposure event, content, or per-frame telemetry.
enum LocalCapabilityRemoteKill {
  static let killSwitchFlag = "free-tier-kill-switch-v1"

  static var isDisabled: Bool {
    resolve(OmiFlagStore.shared.value(killSwitchFlag))
  }

  static func resolve(_ value: Any?) -> Bool {
    // Multivariate strings and absent/error values are not a definitive kill.
    (value as? Bool) == true
  }
}
