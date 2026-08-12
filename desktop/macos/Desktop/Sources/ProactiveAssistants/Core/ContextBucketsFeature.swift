import Foundation

enum ContextBucketsFeature {
  static let flagName = "context_buckets"

  /// PostHog feature flags fail closed while unavailable or uninitialized, so the
  /// default is exactly today's behavior.
  @MainActor static var isEnabled: Bool {
    PostHogManager.shared.isFeatureEnabled(flagName)
  }
}
