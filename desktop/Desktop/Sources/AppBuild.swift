import Foundation

enum AppBuild {
  static let productionBundleIdentifier = "com.omi.computer-macos"
  private static let updateChannelDefaultsKey = "update_channel"

  static var bundleIdentifier: String {
    Bundle.main.bundleIdentifier ?? productionBundleIdentifier
  }

  static var isNonProduction: Bool {
    bundleIdentifier.hasPrefix("com.omi.") && bundleIdentifier != productionBundleIdentifier
  }

  static var displayName: String {
    if let displayName = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String,
      !displayName.isEmpty
    {
      return displayName
    }

    if let bundleName = Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String,
      !bundleName.isEmpty
    {
      return bundleName
    }

    return "omi"
  }

  static var currentUpdateChannel: String {
    let raw = UserDefaults.standard.string(forKey: updateChannelDefaultsKey) ?? "stable"
    return raw == "staging" ? "beta" : raw
  }

  static var inferredUpdateChannel: String {
    let bundlePath = Bundle.main.bundleURL.path.lowercased()
    let display = displayName.lowercased()
    let bundle = bundleIdentifier.lowercased()

    // Check for "better" channel first (installed from /better link)
    if bundle.contains("better")
      || display.contains("better")
      || bundlePath.contains("/better")
      || bundlePath.contains("omi better")
    {
      return "better"
    }

    if bundle.contains("beta")
      || display.contains("beta")
      || bundlePath.contains("/beta")
      || bundlePath.contains("omi beta")
    {
      return "beta"
    }

    return "stable"
  }

  static func syncUpdateChannelWithInstalledApp() {
    let inferred = inferredUpdateChannel
    if currentUpdateChannel != inferred {
      UserDefaults.standard.set(inferred, forKey: updateChannelDefaultsKey)
    }
  }
}
