import Foundation

enum DesktopBackendEnvironment {
  static let productionPythonAPIURL = "https://api.omi.me/"
  static let productionRustBackendURL = "https://desktop-backend-hhibjajaja-uc.a.run.app/"
  static let developmentPythonAPIURL = "https://api.omiapi.com/"
  static let developmentRustBackendURL = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/"

  static var shouldUseDevelopmentBackends: Bool {
    shouldUseDevelopmentBackends(
      bundleIdentifier: AppBuild.bundleIdentifier,
      updateChannel: AppBuild.currentUpdateChannel,
      externalPreviewBackend: AppBuild.externalPreviewBackend
    )
  }

  static func shouldUseDevelopmentBackends(
    bundleIdentifier: String,
    updateChannel: String,
    externalPreviewBackend: AppBuild.ExternalPreviewBackend? = nil
  ) -> Bool {
    // External previews opt into their backend through signed bundle metadata. They must
    // never inherit local-development routing or an environment force override. Missing or
    // malformed preview metadata therefore fails closed to the production backend.
    if AppBuild.isExternalPreviewBundleIdentifier(bundleIdentifier) {
      return externalPreviewBackend == .development
    }

    // Named/dev bundles route to the dev backend by default. Explicit launch
    // URLs still win below so local harnesses and intentionally-targeted tests
    // remain possible.
    if bundleIdentifier != AppBuild.productionBundleIdentifier {
      return true
    }

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

  static func pythonBaseURL(
    useDevelopmentBackends: Bool,
    environmentValue: String?
  ) -> String {
    // A production-family app must not allow a launch environment or bundled
    // config to switch its customer data plane. Development identities retain
    // their explicit override seam for local and signed-preview testing.
    if !useDevelopmentBackends {
      return productionPythonAPIURL
    }
    if let url = normalizedURL(environmentValue) {
      return url
    }

    return developmentPythonAPIURL
  }

  static func authBaseURL(
    useDevelopmentBackends: Bool = shouldUseDevelopmentBackends,
    environmentValue: String? = currentEnvironmentValue("OMI_AUTH_API_URL")
  ) -> String {
    if !useDevelopmentBackends {
      return productionPythonAPIURL
    }
    if let url = normalizedURL(environmentValue) {
      return url
    }

    // Desktop Apple Sign-In uses the shared Services ID. The registered web
    // callback is on api.omi.me, so beta must not inherit the dev data backend
    // host for OAuth unless a local/dev auth URL is explicitly supplied.
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
    if !useDevelopmentBackends {
      return productionRustBackendURL
    }
    if let url = normalizedURL(environmentValue) {
      return url
    }

    if let url = normalizedURL(launchEnvironmentValue) {
      return url
    }

    return developmentRustBackendURL
  }

  static func applyReleaseChannelDefaults() {
    if shouldUseDevelopmentBackends {
      if normalizedURL(currentEnvironmentValue("OMI_PYTHON_API_URL")) == nil {
        setenv("OMI_PYTHON_API_URL", developmentPythonAPIURL, 1)
      }
      if normalizedURL(currentEnvironmentValue("OMI_DESKTOP_API_URL")) == nil {
        setenv("OMI_DESKTOP_API_URL", developmentRustBackendURL, 1)
      }
    }
    log("BackendEnvironment: release-channel defaults applied only for missing backend URLs")
  }

  private static func normalizedURL(_ raw: String?) -> String? {
    guard let raw else { return nil }
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    return trimmed.hasSuffix("/") ? trimmed : trimmed + "/"
  }

  private static func currentEnvironmentValue(_ key: String) -> String? {
    guard let value = getenv(key), let string = String(validatingCString: value) else {
      return nil
    }
    return string
  }
}
