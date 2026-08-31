import Foundation

/// Voice-first reply loop on proactive floating-bar cards.
///
/// Off is today's behavior exactly: the 6s timeout, no reply hint, no grace
/// window, no hover instrumentation, and the director prompt/clamp stay
/// byte-identical to the pre-Interject build. Beta dogfoods it by default
/// (kill-switchable); stable stays dark until `desktop_interject` is true;
/// non-production bundles require `OMI_FORCE_INTERJECT=1`.
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

  @MainActor static var isEnabled: Bool {
    if let testOverride { return testOverride }
    return BetaDogfoodRollout.isEnabled(
      flagName: flagName,
      killSwitchFlagName: killSwitchFlagName,
      localOverrideName: localOverrideName
    )
  }
}
