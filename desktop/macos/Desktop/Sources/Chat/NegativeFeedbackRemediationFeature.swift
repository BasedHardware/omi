import Foundation

/// Behavioural half of thumbs-down remediation, enabled for all users unless
/// the permanent PostHog stop lever is set.
enum NegativeFeedbackRemediationFeature {
  static let killSwitchFlagName = "negative_feedback_remediation_kill"

  @MainActor static var isEnabled: Bool {
    isEnabled(killSwitchEnabled: PostHogManager.shared.isFeatureEnabled(killSwitchFlagName))
  }

  static func isEnabled(killSwitchEnabled: Bool) -> Bool {
    !killSwitchEnabled
  }
}
