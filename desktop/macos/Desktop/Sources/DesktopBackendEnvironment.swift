import Foundation

enum DesktopBackendEnvironment {
  static let productionPythonAPIURL = "https://api.omi.me/"
  static let betaPythonAPIURL = "https://api-beta.omi.me/"
  static let developmentPythonAPIURL = "https://api.omiapi.com/"
  static let developmentRustBackendURL = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/"

  static var shouldUseBetaRingBackends: Bool {
    shouldUseBetaRingBackends(
      bundleIdentifier: AppBuild.bundleIdentifier,
      updateChannel: AppBuild.currentUpdateChannel,
      forceOverride: currentEnvironmentValue("OMI_FORCE_DEV_BACKENDS"),
      externalPreviewBackend: AppBuild.externalPreviewBackend
    )
  }

  static func shouldUseBetaRingBackends(
    bundleIdentifier: String,
    updateChannel: String,
    forceOverride: String? = nil,
    externalPreviewBackend: AppBuild.ExternalPreviewBackend? = nil
  ) -> Bool {
    guard !AppBuild.isExternalPreviewBundleIdentifier(bundleIdentifier) else { return false }
    guard !isAffirmative(forceOverride) else { return false }
    return bundleIdentifier == AppBuild.productionBundleIdentifier && normalizedChannel(updateChannel) == "beta"
  }

  static var shouldUseDevelopmentBackends: Bool {
    shouldUseDevelopmentBackends(
      bundleIdentifier: AppBuild.bundleIdentifier,
      updateChannel: AppBuild.currentUpdateChannel,
      forceOverride: currentEnvironmentValue("OMI_FORCE_DEV_BACKENDS"),
      externalPreviewBackend: AppBuild.externalPreviewBackend
    )
  }

  static func shouldUseDevelopmentBackends(
    bundleIdentifier: String,
    updateChannel: String,
    forceOverride: String? = nil,
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

    // Production beta now has a dedicated stateless release ring. It selects
    // beta URLs below rather than inheriting the development backend.
    if isAffirmative(forceOverride) {
      return true
    }

    return false
  }

  static func pythonBaseURL(
    environmentValue: String? = currentEnvironmentValue("OMI_PYTHON_API_URL")
  ) -> String {
    pythonBaseURL(
      useDevelopmentBackends: shouldUseDevelopmentBackends,
      useBetaRingBackends: shouldUseBetaRingBackends,
      environmentValue: environmentValue
    )
  }

  static func pythonBaseURL(
    useDevelopmentBackends: Bool,
    useBetaRingBackends: Bool = false,
    environmentValue: String?
  ) -> String {
    if let url = normalizedURL(environmentValue) {
      return url
    }

    if useBetaRingBackends {
      return betaPythonAPIURL
    }
    if useDevelopmentBackends {
      return developmentPythonAPIURL
    }

    return productionPythonAPIURL
  }

  static func authBaseURL(
    environmentValue: String? = currentEnvironmentValue("OMI_AUTH_API_URL")
  ) -> String {
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
      useBetaRingBackends: shouldUseBetaRingBackends,
      environmentValue: environmentValue,
      launchEnvironmentValue: launchEnvironmentValue
    )
  }

  static func rustBackendURL(
    useDevelopmentBackends: Bool,
    useBetaRingBackends: Bool = false,
    environmentValue: String?,
    launchEnvironmentValue: String?
  ) -> String {
    if let url = normalizedURL(environmentValue) {
      return url
    }

    if let url = normalizedURL(launchEnvironmentValue) {
      return url
    }

    // The Rust desktop backend has its own, currently roll-forward-only
    // release path. v1's stateless beta ring is the Python/GKE path; leave
    // this unset so the signed production bundle's explicit Rust endpoint
    // remains authoritative rather than inventing an unprovisioned beta host.
    if useDevelopmentBackends {
      return developmentRustBackendURL
    }

    return ""
  }

  static func applyReleaseChannelDefaults() {
    if shouldUseBetaRingBackends, normalizedURL(currentEnvironmentValue("OMI_PYTHON_API_URL")) == nil {
      setenv("OMI_PYTHON_API_URL", betaPythonAPIURL, 1)
    }
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
    guard let value = getenv(key), let string = String(validatingCString: value) else {
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
