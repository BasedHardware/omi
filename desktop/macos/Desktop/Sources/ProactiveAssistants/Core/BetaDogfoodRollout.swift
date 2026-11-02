import Foundation

/// Shared bundle-scoped rollout policy used by unrelated beta dogfood features.
enum BetaDogfoodRollout {
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
    if isBetaProductionBundle {
      return !isKillSwitchEnabled
    }
    return isFlagEnabled
  }

  @MainActor static func isEnabled(flagName: String, killSwitchFlagName: String, localOverrideName: String) -> Bool {
    let isNonProduction = AppBuild.isNonProduction
    let isBeta = AppBuild.isBetaProductionBundle
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
