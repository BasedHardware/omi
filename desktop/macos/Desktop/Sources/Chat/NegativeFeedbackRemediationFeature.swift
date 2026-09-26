import Foundation

/// Behavioural half of the thumbs-down remediation (memory subject admission,
/// per-task Focus ledger, web-search honesty). Tier 1 instrumentation ships on
/// without this flag so the next window can measure Tiers 2–3.
///
/// Beta dogfoods it by default (kill-switchable); stable stays dark until
/// `negative_feedback_remediation` is true; non-production bundles require
/// `OMI_FORCE_NEGATIVE_FEEDBACK_REMEDIATION=1`.
enum NegativeFeedbackRemediationFeature {
  static let flagName = "negative_feedback_remediation"
  static let killSwitchFlagName = "negative_feedback_remediation_kill"
  static let localOverrideName = "OMI_FORCE_NEGATIVE_FEEDBACK_REMEDIATION"

  private static let overrideLock = NSLock()
  nonisolated(unsafe) private static var cachedTestOverride: Bool?

  nonisolated static var testOverride: Bool? {
    get { overrideLock.withLock { cachedTestOverride } }
    set { overrideLock.withLock { cachedTestOverride = newValue } }
  }

  @MainActor static var isEnabled: Bool {
    if let testOverride { return testOverride }
    return BetaDogfoodRollout.isEnabled(
      flagName: flagName,
      killSwitchFlagName: killSwitchFlagName,
      localOverrideName: localOverrideName
    )
  }
}
