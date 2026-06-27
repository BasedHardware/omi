import Foundation

enum DesktopBackendEnvironment {
  static let productionPythonAPIURL = "https://api.omi.me/"
  static let developmentPythonAPIURL = "https://api.omiapi.com/"
  static let developmentRustBackendURL = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/"

  static var shouldUseDevelopmentBackends: Bool {
    shouldUseDevelopmentBackends(
      bundleIdentifier: AppBuild.bundleIdentifier,
      updateChannel: AppBuild.currentUpdateChannel,
      forceOverride: currentEnvironmentValue("OMI_FORCE_DEV_BACKENDS")
    )
  }

  static func shouldUseDevelopmentBackends(
    bundleIdentifier: String,
    updateChannel: String,
    forceOverride: String? = nil
  ) -> Bool {
    // Beta channel of the production bundle routes to the dev backend
    // (api.omiapi.com + dev Cloud Run desktop-backend). The dev backend is
    // configured to use prod Firebase (project_id=based-hardware, prod service
    // account, prod FIREBASE_API_KEY), so custom tokens it mints resolve to the
    // same UID a user has on prod — and reads/writes hit prod Firestore. Same
    // pattern as mobile TestFlight → staging.
    //
    // PR #7014 (April 2026) was reverted because at that time the dev backend
    // was wired to the based-hardware-dev Firebase project, so beta users
    // ended up signed in as fresh empty UIDs. The infra has since been moved
    // onto prod Firebase. Verify before any future revert: dev backend
    // /v1/auth/token must mint custom tokens whose UID matches prod.
    if isAffirmative(forceOverride) {
      return true
    }

    return bundleIdentifier == AppBuild.productionBundleIdentifier
      && normalizedChannel(updateChannel) == "beta"
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

  private static func isAffirmative(_ value: String?) -> Bool {
    guard let value else { return false }
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return normalized == "1" || normalized == "true" || normalized == "yes"
  }
}
