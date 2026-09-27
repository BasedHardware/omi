import Foundation

/// Voice-first reply loop on proactive floating-bar cards.
///
/// Off is today's behavior exactly: the 6s timeout, no reply hint, no grace
/// window, no hover instrumentation, and the director prompt/clamp stay
/// byte-identical to the pre-Interject build. Beta dogfoods it by default
/// (kill-switchable); stable stays dark until `desktop_interject` is true;
/// non-production bundles require `OMI_FORCE_INTERJECT=1`.
///
/// EXP-002: an enrolled arm owns this decision for the experiment's
/// population — `memory_v1` turns Interject on, enrolled `control` turns it
/// off (the assistant-chrome comparator). Un-enrolled users keep the dogfood
/// decision untouched. The fleet kill switch (`desktop_interject_kill`)
/// still disarms every arm; ops authority is never overridden.
enum InterjectFeature {
  static let flagName = "desktop_interject"
  static let killSwitchFlagName = "desktop_interject_kill"
  static let localOverrideName = "OMI_FORCE_INTERJECT"

  /// Tests pin this; production leaves it nil. Access only while holding overrideLock.
  private static let overrideLock = NSLock()
  nonisolated(unsafe) private static var cachedTestOverride: Bool?

  nonisolated static var testOverride: Bool? {
    get { overrideLock.withLock { cachedTestOverride } }
    set { overrideLock.withLock { cachedTestOverride = newValue } }
  }

  /// The arm-driven decision, with every input passed in so it can be
  /// exercised without a bundle, a PostHog client, or an enrolled owner.
  /// An arm (enrolled or forced-local dogfood) owns the decision for its
  /// population: `memory_v1` on, `control` off. Un-armed users keep the
  /// dogfood decision untouched. The fleet kill switch disarms every arm.
  @MainActor
  static func isEnabled(
    experimentVariant: String?,
    killSwitchEnabled: Bool,
    unenrolledDecision: Bool
  ) -> Bool {
    guard let experimentVariant else {
      return unenrolledDecision
    }
    if killSwitchEnabled {
      return false
    }
    return experimentVariant == DesktopExperiment.memoryV1Variant
  }

  @MainActor static var isEnabled: Bool {
    if let testOverride { return testOverride }
    let experimentVariant = DesktopExperimentCoordinator.shared.assignment?.variant
    let killSwitchEnabled =
      !AppBuild.isNonProduction && AppBuild.isBetaProductionBundle
      && PostHogManager.shared.isFeatureEnabled(killSwitchFlagName)
    return isEnabled(
      experimentVariant: experimentVariant,
      killSwitchEnabled: killSwitchEnabled,
      unenrolledDecision: BetaDogfoodRollout.isEnabled(
        flagName: flagName,
        killSwitchFlagName: killSwitchFlagName,
        localOverrideName: localOverrideName
      )
    )
  }
}
