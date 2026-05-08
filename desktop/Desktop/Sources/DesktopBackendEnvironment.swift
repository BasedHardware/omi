import Foundation

enum DesktopBackendEnvironment {
  static let productionPythonAPIURL = "https://api.omi.me/"
  static let developmentPythonAPIURL = "https://api.omiapi.com/"
  static let developmentRustBackendURL = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/"

  static var shouldUseDevelopmentBackends: Bool {
    shouldUseDevelopmentBackends(
      bundleIdentifier: AppBuild.bundleIdentifier,
      updateChannel: AppBuild.currentUpdateChannel
    )
  }

  static func shouldUseDevelopmentBackends(
    bundleIdentifier: String,
    updateChannel: String
  ) -> Bool {
    // Beta-to-dev routing disabled: signed-in users were landing in fresh empty
    // Firebase accounts (e.g. caLCFj7… instead of viUv7Gtdo… for kodjima33),
    // because the dev backend's auth path mints custom tokens for new UIDs
    // instead of linking to the existing prod user. Keep beta on prod backends
    // until the auth flow is fixed.
    return false
  }

  static func pythonBaseURL(
    environmentValue: String? = currentEnvironmentValue("OMI_PYTHON_API_URL")
  ) -> String {
    pythonBaseURL(
      useDevelopmentBackends: shouldUseDevelopmentBackends,
      environmentValue: environmentValue
    )
  }

  static func pythonBaseURL(useDevelopmentBackends: Bool, environmentValue: String?) -> String {
    if useDevelopmentBackends {
      return developmentPythonAPIURL
    }

    if let url = normalizedURL(environmentValue) {
      return url
    }

    return productionPythonAPIURL
  }

  static func rustBackendURL(
    environmentValue: String? = currentEnvironmentValue("OMI_DESKTOP_API_URL"),
    launchEnvironmentValue: String? = ProcessInfo.processInfo.environment["OMI_DESKTOP_API_URL"]
  ) -> String {
    rustBackendURL(
      useDevelopmentBackends: shouldUseDevelopmentBackends,
      environmentValue: environmentValue,
      launchEnvironmentValue: launchEnvironmentValue
    )
  }

  static func rustBackendURL(
    useDevelopmentBackends: Bool,
    environmentValue: String?,
    launchEnvironmentValue: String?
  ) -> String {
    if useDevelopmentBackends {
      return developmentRustBackendURL
    }

    if let url = normalizedURL(environmentValue) {
      return url
    }

    if let url = normalizedURL(launchEnvironmentValue) {
      return url
    }

    return ""
  }

  static func applyReleaseChannelDefaults() {
    guard shouldUseDevelopmentBackends else { return }

    setenv("OMI_PYTHON_API_URL", developmentPythonAPIURL, 1)
    setenv("OMI_DESKTOP_API_URL", developmentRustBackendURL, 1)
    log("BackendEnvironment: beta channel using development backends with production data stores")
  }

  private static func normalizedChannel(_ channel: String) -> String {
    let normalized = channel.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return normalized == "staging" ? "beta" : normalized
  }

  private static func normalizedURL(_ raw: String?) -> String? {
    guard let raw else { return nil }
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    return trimmed.hasSuffix("/") ? trimmed : trimmed + "/"
  }

  private static func currentEnvironmentValue(_ key: String) -> String? {
    guard let value = getenv(key), let string = String(validatingUTF8: value) else {
      return nil
    }
    return string
  }
}
