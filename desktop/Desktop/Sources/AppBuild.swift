import Foundation

enum AppBuild {
  static let productionBundleIdentifier = "com.omi.computer-macos"
  private static let updateChannelDefaultsKey = "update_channel"
  private static let productionDesktopBackendURL = "https://desktop-backend-hhibjajaja-uc.a.run.app/"
  private static let developmentDesktopBackendURL = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/"

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

  static var prefersDevelopmentDesktopBackend: Bool {
    isNonProduction || currentUpdateChannel == "beta"
  }

  static var managedDesktopBackendBaseURL: String {
    prefersDevelopmentDesktopBackend ? developmentDesktopBackendURL : productionDesktopBackendURL
  }

  static func resolvedAPIBaseURL(configuredURL: String?) -> String {
    let preferredManagedURL = managedDesktopBackendBaseURL

    guard let configuredURL, !configuredURL.isEmpty else {
      return preferredManagedURL
    }

    let normalizedURL = configuredURL.hasSuffix("/") ? configuredURL : configuredURL + "/"

    if isKnownManagedDesktopBackendURL(normalizedURL) {
      return preferredManagedURL
    }

    return normalizedURL
  }

  private static func isKnownManagedDesktopBackendURL(_ url: String) -> Bool {
    url == productionDesktopBackendURL || url == developmentDesktopBackendURL
  }
}
