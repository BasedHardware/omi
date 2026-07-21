import Foundation

/// Beta-only enhanced diagnostics are enabled by default and can be disabled in
/// Advanced Settings. Stable and development bundles never use this path.
enum BetaEnhancedDiagnosticsConfiguration {
  static let defaultsKey = "betaEnhancedDiagnosticsEnabled"

  static var isEnabled: Bool {
    isEnabled(
      bundleIdentifier: AppBuild.bundleIdentifier,
      updateChannel: AppBuild.currentUpdateChannel,
      defaults: .standard)
  }

  static func isEnabled(bundleIdentifier: String, updateChannel: String, defaults: UserDefaults) -> Bool {
    guard bundleIdentifier == AppBuild.productionBundleIdentifier, updateChannel == "beta" else { return false }
    guard defaults.object(forKey: defaultsKey) != nil else { return true }
    return defaults.bool(forKey: defaultsKey)
  }
}
