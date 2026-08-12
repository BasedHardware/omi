import Foundation

enum ContextBucketsFeature {
  static let flagName = "context_buckets"
  private static let localQAOverrideName = "OMI_FORCE_CONTEXT_BUCKETS"

  /// PostHog feature flags fail closed while unavailable or uninitialized, so the
  /// default is exactly today's behavior.
  @MainActor static var isEnabled: Bool {
    if AppBuild.isNonProduction,
      ProcessInfo.processInfo.environment[localQAOverrideName] == "1"
    {
      return true
    }
    return PostHogManager.shared.isFeatureEnabled(flagName)
  }
}
