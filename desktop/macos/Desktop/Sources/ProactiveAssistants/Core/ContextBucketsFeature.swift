import Foundation

enum ContextBucketsFeature {
  static let flagName = "context_buckets"
  /// Remote stop for the beta channel. Inverted on purpose: absent, unresolved, and false
  /// all mean "run the pipeline", so only an explicit true switches it off.
  static let killSwitchFlagName = "context_buckets_kill"
  private static let localQAOverrideName = "OMI_FORCE_CONTEXT_BUCKETS"

  /// PostHog feature flags fail closed while unavailable or uninitialized, so the
  /// production default is exactly today's behavior.
  ///
  /// Non-production bundles do not consult PostHog at all. They used to require
  /// `OMI_FORCE_CONTEXT_BUCKETS=1` in the launch environment, but that is read from
  /// `ProcessInfo` at runtime, so any relaunch that does not go through `run.sh` —
  /// opening the bundle from Finder, or macOS restoring it after a permission grant —
  /// silently dropped it. Capture kept running with the bucket pipeline disabled, which
  /// is indistinguishable from the feature simply never firing. Dev bundles exist to
  /// exercise this pipeline, so they default to on and the variable now only turns it off.
  @MainActor static var isEnabled: Bool {
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localQAOverrideName] != "0"
    }
    // The bucket pipeline is a beta-channel surface; stable stays on the fallback
    // assistants. That split is enforced here, on bundle identity, rather than through
    // a PostHog release condition on `update_channel`. The channel reaches PostHog as a
    // super property via `register(...)`, so it rides events but only lands on the person
    // record when `identify` runs — measured across 14 days of macOS clients, 215 of ~260
    // beta installs had a null person-side channel and 11 reported `stable`, so
    // person-property targeting resolved for roughly a sixth of the channel. Bundle
    // identity is exact and available before any network call.
    //
    // Enablement does not consult `context_buckets` either, because that flag inherits the
    // same problem from the other side: its audience can only be described with a static
    // cohort or the unreliable person property, so a *newly installed* beta client matches
    // neither and would silently get nothing. PostHog rejects behavioral cohorts in flag
    // targeting, so there is no server-side expression of "is running the beta build" that
    // stays correct as users arrive. Bundle identity already answers that question exactly.
    //
    // What remains useful remotely is the ability to stop the pipeline, so beta reads only
    // the kill switch, and reads it fail-open: an unreachable or uninitialized PostHog must
    // not switch the dogfood channel off by accident. Stable is gated out above, so this
    // default cannot reach it.
    guard AppBuild.isBetaProductionBundle else { return false }
    return !PostHogManager.shared.isFeatureEnabled(killSwitchFlagName)
  }
}
