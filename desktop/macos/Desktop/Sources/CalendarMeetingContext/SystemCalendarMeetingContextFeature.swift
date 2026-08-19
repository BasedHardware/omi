import Foundation

/// Rollout gating for features whose consumer is scoped by *deployment* rather than by user.
///
/// The backend half of this feature is scoped by deployment: the `CONVERSATION_*` rollout flags
/// are `true` only in the dev runtime environment, and the beta app bundle is the only
/// production-family identity that talks to it (`DesktopBackendEnvironment`
/// `shouldForceDevelopmentServingEndpoints`). The client half is scoped by PostHog, which targets
/// *users* and knows nothing about which backend a bundle points at.
///
/// Enabling beta by default is what makes the two halves line up. Without it, turning the feature
/// on for beta would mean a PostHog cohort that also matches stable users — whose backend has the
/// consuming flags off, so they would pay for calendar permission prompts and uploads that nothing
/// reads. The PostHog flag stays the lever for stable; beta keeps a kill switch so a bad build can
/// be disarmed without shipping a new one.
enum BetaDogfoodRollout {
  /// The decision, with every input passed in so it can be exercised without a bundle,
  /// a process environment, or a PostHog client.
  static func isEnabled(
    isNonProduction: Bool,
    isBetaProductionBundle: Bool,
    localOverrideValue: String?,
    isFlagEnabled: Bool,
    isKillSwitchEnabled: Bool
  ) -> Bool {
    if isNonProduction {
      return localOverrideValue == "1"
    }
    // Beta is the production-account dogfood channel and is pinned to the dev backend, which
    // is where the consuming rollout flags are enabled.
    if isBetaProductionBundle {
      return !isKillSwitchEnabled
    }
    return isFlagEnabled
  }

  @MainActor static func isEnabled(flagName: String, killSwitchFlagName: String, localOverrideName: String) -> Bool {
    let isNonProduction = AppBuild.isNonProduction
    let isBeta = AppBuild.isBetaProductionBundle
    // Evaluate only the flag the decision actually consumes, so a stable client never
    // reports exposure to the beta kill switch and vice versa.
    return isEnabled(
      isNonProduction: isNonProduction,
      isBetaProductionBundle: isBeta,
      localOverrideValue: ProcessInfo.processInfo.environment[localOverrideName],
      isFlagEnabled: !isNonProduction && !isBeta && PostHogManager.shared.isFeatureEnabled(flagName),
      isKillSwitchEnabled: !isNonProduction && isBeta
        && PostHogManager.shared.isFeatureEnabled(killSwitchFlagName)
    )
  }
}

enum SystemCalendarMeetingContextFeature {
  static let flagName = "system_calendar_meeting_context"
  static let killSwitchFlagName = "system_calendar_meeting_context_kill"
  private static let localOverrideName = "OMI_FORCE_SYSTEM_CALENDAR_MEETING_CONTEXT"

  /// Named/dev bundles require an explicit environment override; beta is on unless killed;
  /// stable requires an explicit true PostHog flag evaluation.
  @MainActor static var isEnabled: Bool {
    BetaDogfoodRollout.isEnabled(
      flagName: flagName,
      killSwitchFlagName: killSwitchFlagName,
      localOverrideName: localOverrideName
    )
  }
}

enum OnDeviceMeetingIdentityFeature {
  static let flagName = "on_device_meeting_identity"
  static let killSwitchFlagName = "on_device_meeting_identity_kill"
  private static let localOverrideName = "OMI_FORCE_ON_DEVICE_MEETING_IDENTITY"

  /// Independent dark launch: screen-derived identity does not require Calendar permission.
  @MainActor static var isEnabled: Bool {
    BetaDogfoodRollout.isEnabled(
      flagName: flagName,
      killSwitchFlagName: killSwitchFlagName,
      localOverrideName: localOverrideName
    )
  }
}
