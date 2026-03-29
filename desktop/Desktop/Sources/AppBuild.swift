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

    if bundle.contains("beta")
      || display.contains("beta")
      || bundlePath.contains("/beta")
      || bundlePath.contains("omi beta")
    {
      return "beta"
    }

    return "stable"
  }

  /// Only set the channel on first launch when no preference exists yet.
  /// Never overwrite a user-chosen channel (e.g. beta selected in settings).
  static func syncUpdateChannelOnFirstLaunch() {
    guard UserDefaults.standard.string(forKey: updateChannelDefaultsKey) == nil else { return }
    let inferred = inferredUpdateChannel
    UserDefaults.standard.set(inferred, forKey: updateChannelDefaultsKey)
  }
}
