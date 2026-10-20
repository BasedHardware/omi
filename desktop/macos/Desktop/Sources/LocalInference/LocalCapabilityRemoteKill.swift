import PostHog

/// Existing free-tier emergency stop, read from the SDK cache only. Unknown is
/// not killed. No flag fetch, exposure event, content, or per-frame telemetry.
enum LocalCapabilityRemoteKill {
  static let key = "free-tier-kill-switch-v1"

  static var isDisabled: Bool {
    resolve(PostHogSDK.shared.getFeatureFlag(key, sendFeatureFlagEvent: false))
  }

  static func resolve(_ value: Any?) -> Bool {
    // Multivariate strings and absent/error values are not a definitive kill.
    (value as? Bool) == true
  }
}
