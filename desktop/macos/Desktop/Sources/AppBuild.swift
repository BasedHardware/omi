// v0.12.149 release path advancement marker
import Foundation

enum AppBuild {
  /// v0.12.149 release candidate source touch.
  static let productionBundleIdentifier = "com.omi.computer-macos"
  /// The separately-installable beta app ("Omi Beta.app"). A distinct bundle id gives it
  /// its own UserDefaults domain, TCC grants, Keychain ACL, and single-instance lock, so
  /// it runs side-by-side with stable. Must stay in sync with
  /// `DesktopStorageIdentity.betaProductionBundleIdentifier` (asserted by a unit test).
  static let betaProductionBundleIdentifier = "com.omi.computer-macos.beta"
  static let productionFamilyBundleIdentifiers: Set<String> = [
    productionBundleIdentifier, betaProductionBundleIdentifier,
  ]
  static let desktopDevBundleIdentifier = "com.omi.desktop-dev"
  static let externalPreviewBundleIdentifierPrefix = "com.omi.preview."
  static let externalPreviewMarkerInfoKey = "OMIExternalPreview"
  static let externalPreviewBackendInfoKey = "OMIExternalPreviewBackend"

  enum ExternalPreviewBackend: String, Equatable {
    case production
    case development

    init?(infoValue: Any?) {
      guard let rawValue = infoValue as? String else { return nil }
      self.init(rawValue: rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }
  }

  /// Preview bundle identity, the explicit Info.plist marker, and the selected backend are
  /// all evaluated together. The reserved identity is the safety boundary: an artifact with
  /// a preview identity is always restricted, even if a packaging error omits its marker.
  struct Configuration: Equatable {
    let bundleIdentifier: String
    let isExternalPreview: Bool
    let hasExternalPreviewMarker: Bool
    let externalPreviewBackend: ExternalPreviewBackend?

    var isNonProduction: Bool {
      bundleIdentifier.hasPrefix("com.omi.")
        && !AppBuild.productionFamilyBundleIdentifiers.contains(bundleIdentifier)
    }

    var allowsLocalAutomation: Bool {
      isNonProduction && !isExternalPreview
    }

    var isNamedDevelopmentBundle: Bool {
      isNonProduction && !isExternalPreview && bundleIdentifier != AppBuild.desktopDevBundleIdentifier
    }

    var allowsSparkleUpdates: Bool {
      !isExternalPreview && !isNamedDevelopmentBundle
    }

    var hasValidExternalPreviewConfiguration: Bool {
      !isExternalPreview || (hasExternalPreviewMarker && externalPreviewBackend != nil)
    }
  }

  static func configuration(
    bundleIdentifier: String,
    infoDictionary: [String: Any]
  ) -> Configuration {
    let isExternalPreview = isExternalPreviewBundleIdentifier(bundleIdentifier)
    let hasExternalPreviewMarker = infoDictionary[externalPreviewMarkerInfoKey] as? Bool == true
    let externalPreviewBackend = ExternalPreviewBackend(
      infoValue: infoDictionary[externalPreviewBackendInfoKey])

    return Configuration(
      bundleIdentifier: bundleIdentifier,
      isExternalPreview: isExternalPreview,
      hasExternalPreviewMarker: hasExternalPreviewMarker,
      externalPreviewBackend: externalPreviewBackend
    )
  }

  static func isExternalPreviewBundleIdentifier(_ bundleIdentifier: String) -> Bool {
    let suffix = bundleIdentifier.dropFirst(externalPreviewBundleIdentifierPrefix.count)
    return bundleIdentifier.hasPrefix(externalPreviewBundleIdentifierPrefix) && !suffix.isEmpty
  }

  private static var buildConfiguration: Configuration {
    configuration(
      bundleIdentifier: bundleIdentifier,
      infoDictionary: Bundle.main.infoDictionary ?? [:]
    )
  }

  static var bundleIdentifier: String {
    Bundle.main.bundleIdentifier ?? productionBundleIdentifier
  }

  static var isNonProduction: Bool {
    buildConfiguration.isNonProduction
  }

  /// True for every shipped production-family artifact (stable *and* the beta app).
  /// Use `isBetaProductionBundle` when behavior differs between the two.
  static var isProductionBundle: Bool {
    productionFamilyBundleIdentifiers.contains(bundleIdentifier)
  }

  static func firebaseAPIKey(bundleIdentifier: String, environmentKey: String?, bundledKey: String?) -> String {
    // Shipped Beta shares production Firebase identity even while serving through dev.
    if productionFamilyBundleIdentifiers.contains(bundleIdentifier) {
      return bundledKey?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }
    return environmentKey?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
  }

  /// The separately-installable "Omi Beta" app. Its update channel is pinned to beta
  /// and it keeps its own isolated on-disk state, so it can run beside stable.
  static var isBetaProductionBundle: Bool {
    bundleIdentifier == betaProductionBundleIdentifier
  }

  static var isExternalPreview: Bool {
    buildConfiguration.isExternalPreview
  }

  /// Legacy "Omi Computer.app" cleanup force-terminates running
  /// `com.omi.computer-macos` processes and deletes the old bundle — strictly
  /// stable-lineage housekeeping. Only the stable identity may run it: Omi Beta
  /// or a dev bundle doing so would kill the user's running stable app.
  static var mayRunLegacyStableAppCleanup: Bool {
    mayRunLegacyStableAppCleanup(bundleIdentifier: bundleIdentifier)
  }

  static func mayRunLegacyStableAppCleanup(bundleIdentifier: String) -> Bool {
    bundleIdentifier == productionBundleIdentifier
  }

  /// Only local development bundles expose the loopback automation/debug bridge. Published
  /// preview apps share the non-production namespace but must never expose that bridge.
  static var allowsLocalAutomation: Bool {
    buildConfiguration.allowsLocalAutomation
  }

  /// Preview artifacts and local named developer bundles never consume the shared Sparkle feed.
  /// The updater additionally checks this at every call site.
  static var allowsSparkleUpdates: Bool {
    buildConfiguration.allowsSparkleUpdates
  }

  static var hasValidExternalPreviewConfiguration: Bool {
    buildConfiguration.hasValidExternalPreviewConfiguration
  }

  /// Nil is intentional for a malformed preview configuration. Backend routing then fails
  /// closed to production rather than inheriting the local-development default.
  static var externalPreviewBackend: ExternalPreviewBackend? {
    guard buildConfiguration.isExternalPreview, buildConfiguration.hasExternalPreviewMarker else {
      return nil
    }
    return buildConfiguration.externalPreviewBackend
  }

  static var isNamedDevelopmentBundle: Bool {
    buildConfiguration.isNamedDevelopmentBundle
  }

  static var usesLazyDevPermissions: Bool {
    isNamedDevelopmentBundle && UserDefaults.standard.bool(forKey: "devLazyPermissionsEnabled")
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

  /// GitHub repo that hosts desktop releases (source of truth for the changelog).
  private static let releasesBaseURL = "https://github.com/BasedHardware/omi/releases"

  /// Release tag for the running build, e.g. "v0.11.475+11475-macos".
  /// Matches the tag Codemagic publishes (`v{shortVersion}+{build}-{platform}`).
  static var releaseTag: String? {
    guard
      let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String,
      !version.isEmpty,
      let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String,
      !build.isEmpty
    else {
      return nil
    }
    return "v\(version)+\(build)-macos"
  }

  /// "What's New" target: the GitHub release page for the running build.
  /// Real shipped builds (beta + stable both use the production bundle id) carry a
  /// version that maps to a published tag, so deep-link to this version's notes (the
  /// `+` in the tag must be `%2B` in the URL path). Dev/named test bundles carry a
  /// placeholder version with no matching tag, so fall back to the releases list.
  static var changelogURLString: String {
    guard isProductionBundle, let tag = releaseTag else { return releasesBaseURL }
    return "\(releasesBaseURL)/tag/\(tag.replacingOccurrences(of: "+", with: "%2B"))"
  }

  /// Sparkle channel is identity-bound. Omi Beta is permanently a beta-channel
  /// client. Stable.app never consumes the beta Sparkle channel: leftover
  /// `update_channel` defaults and server-synced settings must not opt it into
  /// newer stable-identity zips against production APIs.
  static var currentUpdateChannel: String {
    updateChannel(isBetaIdentity: isBetaProductionBundle)
  }

  static func updateChannel(isBetaIdentity: Bool) -> String {
    isBetaIdentity ? "beta" : "stable"
  }

  static var manualDownloadURL: URL {
    manualDownloadURL(channel: currentUpdateChannel, isBetaIdentity: isBetaProductionBundle)
  }

  /// Fail-closed Omi Beta DMG. Stable Settings uses this instead of flipping Sparkle.
  static var omiBetaInstallURL: URL {
    manualDownloadURL(channel: "beta", isBetaIdentity: true)
  }

  static func manualDownloadURL(channel: String, isBetaIdentity: Bool) -> URL {
    var components = URLComponents()
    components.scheme = "https"
    components.host = "api.omi.me"
    components.path = "/v2/desktop/download/latest"
    var queryItems = [URLQueryItem(name: "channel", value: channel)]
    if isBetaIdentity {
      // The Omi Beta app must re-download its own identity, never the stable app.
      queryItems.append(URLQueryItem(name: "identity", value: "beta"))
    }
    components.queryItems = queryItems
    // Fixed scheme/host/path always produce a URL; the fallback is unreachable.
    return components.url ?? URL(fileURLWithPath: "/")
  }
}
