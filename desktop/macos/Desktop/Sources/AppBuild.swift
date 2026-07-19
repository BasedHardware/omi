import Foundation

enum AppBuild {
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
  private static let updateChannelDefaultsKey = "update_channel"
  private static let betaOverwriteMigrationKey = "didMigrateBetaOverwrite_v1"
  private static let desktopAppcastURL = URL(
    string: "https://api.omi.me/v2/desktop/appcast.xml?platform=macos")!

  /// How long the launch-time channel probe may hold the main thread. It runs before the
  /// first frame, so it has to stay clear of the 3s watchdog that reports "App Hanging".
  private static let channelProbeMainThreadBudget: TimeInterval = 1.5
  private static let channelProbeRequestTimeout: TimeInterval = 3

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

  /// The separately-installable "Omi Beta" app. Its update channel is pinned to beta
  /// and it keeps its own isolated on-disk state, so it can run beside stable.
  static var isBetaProductionBundle: Bool {
    bundleIdentifier == betaProductionBundleIdentifier
  }

  static var isExternalPreview: Bool {
    buildConfiguration.isExternalPreview
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

  static var currentUpdateChannel: String {
    // The Omi Beta app is permanently a beta-channel client; a stray defaults value
    // (imported settings, sync) must never flip it to stable-identity updates.
    if isBetaProductionBundle { return "beta" }
    let raw = UserDefaults.standard.string(forKey: updateChannelDefaultsKey) ?? "stable"
    return raw == "staging" ? "beta" : raw
  }

  static var manualDownloadURL: URL {
    URL(string: "https://api.omi.me/v2/desktop/download/latest?channel=\(currentUpdateChannel)")!
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
  @discardableResult
  static func syncUpdateChannelOnFirstLaunch() -> String? {
    guard UserDefaults.standard.string(forKey: updateChannelDefaultsKey) == nil else { return nil }
    let resolved = probeFreshInstallUpdateChannel()
    UserDefaults.standard.set(resolved, forKey: updateChannelDefaultsKey)
    return resolved
  }

  /// One-time migration for users whose beta channel was overwritten to stable
  /// by the syncUpdateChannelWithInstalledApp() bug (commit 8c60fafe8, March 27 2026).
  /// Re-checks the appcast: if the current build is ahead of latest stable, restore beta.
  static func migrateBetaChannelOverwrite() {
    migrateBetaChannelOverwrite(probeAppcast: probeFreshInstallUpdateChannel)
  }

  static func migrateBetaChannelOverwrite(probeAppcast: () -> String) {
    guard !UserDefaults.standard.bool(forKey: betaOverwriteMigrationKey) else { return }
    UserDefaults.standard.set(true, forKey: betaOverwriteMigrationKey)

    // A fresh install has no stored channel, so there is nothing to restore — and
    // syncUpdateChannelOnFirstLaunch() probes the same appcast moments later. Probing
    // here as well made every new install pay for two serial launch-blocking round
    // trips to answer one question.
    guard UserDefaults.standard.string(forKey: updateChannelDefaultsKey) != nil else { return }
    guard currentUpdateChannel == "stable" else { return }

    if probeAppcast() == "beta" {
      UserDefaults.standard.set("beta", forKey: updateChannelDefaultsKey)
    }
  }

  static func prepareUpdateChannelForBackendRouting() {
    guard isProductionBundle else { return }
    // Beta identity: channel is pinned, so the launch-blocking appcast probes and the
    // stable-overwrite migration have nothing to decide.
    guard !isBetaProductionBundle else { return }

    migrateBetaChannelOverwrite()
    if UserDefaults.standard.string(forKey: updateChannelDefaultsKey) == nil {
      syncUpdateChannelOnFirstLaunch()
    }
  }

  static func resolveFreshInstallUpdateChannel(
    currentBuild: Int,
    fallback: String,
    appcastXML: String
  ) -> String {
    if fallback == "beta" {
      return "beta"
    }

    guard let latestStableBuild = latestStableBuildNumber(in: appcastXML) else {
      return fallback
    }

    return currentBuild > latestStableBuild ? "beta" : "stable"
  }

  static func latestStableBuildNumber(in appcastXML: String) -> Int? {
    let itemPattern = #"<item>(.*?)</item>"#
    let versionPattern = #"<sparkle:version>(\d+)</sparkle:version>"#

    guard
      let itemRegex = try? NSRegularExpression(
        pattern: itemPattern,
        options: [.dotMatchesLineSeparators]
      ),
      let versionRegex = try? NSRegularExpression(pattern: versionPattern)
    else {
      return nil
    }

    let xmlRange = NSRange(appcastXML.startIndex..<appcastXML.endIndex, in: appcastXML)
    var latestStableBuild: Int?

    for match in itemRegex.matches(in: appcastXML, options: [], range: xmlRange) {
      guard
        let itemRange = Range(match.range(at: 1), in: appcastXML)
      else {
        continue
      }

      let itemXML = String(appcastXML[itemRange])
      if itemXML.contains("<sparkle:channel>beta</sparkle:channel>")
        || itemXML.contains("<sparkle:channel>staging</sparkle:channel>")
      {
        continue
      }

      let itemNSRange = NSRange(itemXML.startIndex..<itemXML.endIndex, in: itemXML)
      guard
        let versionMatch = versionRegex.firstMatch(in: itemXML, options: [], range: itemNSRange),
        let versionRange = Range(versionMatch.range(at: 1), in: itemXML),
        let build = Int(itemXML[versionRange])
      else {
        continue
      }

      latestStableBuild = max(latestStableBuild ?? build, build)
    }

    return latestStableBuild
  }

  private static var currentBuildNumber: Int? {
    guard
      let raw = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
    else {
      return nil
    }

    return Int(raw)
  }

  private static func probeFreshInstallUpdateChannel() -> String {
    probeFreshInstallUpdateChannel(
      fallback: inferredUpdateChannel,
      currentBuild: currentBuildNumber,
      mainThreadBudget: channelProbeMainThreadBudget,
      fetchAppcast: fetchDesktopAppcast,
      persistLateCorrection: { storeLateChannelCorrection($0) }
    )
  }

  /// Resolve the channel for an install with no stored preference.
  ///
  /// This runs on the main thread during launch (`AppState.init` needs the channel before
  /// it loads backend URLs), so it waits at most `mainThreadBudget` for the appcast. Past
  /// that it returns the bundle-inferred channel and lets the request finish in the
  /// background: a late answer that disagrees is written through `persistLateCorrection`,
  /// so the next launch starts on the right channel.
  ///
  /// It used to block for up to 3.5s inline, and pinned the timed-out guess permanently.
  static func probeFreshInstallUpdateChannel(
    fallback: String,
    currentBuild: Int?,
    mainThreadBudget: TimeInterval,
    fetchAppcast: @escaping (@escaping @Sendable (String?) -> Void) -> Void,
    persistLateCorrection: @escaping @Sendable (String) -> Void
  ) -> String {
    if fallback == "beta" {
      return "beta"
    }

    guard let currentBuild else {
      return fallback
    }

    let appcast = AppcastProbeResult()
    let semaphore = DispatchSemaphore(value: 0)

    fetchAppcast { xml in
      appcast.set(xml)
      semaphore.signal()
    }

    if semaphore.wait(timeout: .now() + mainThreadBudget) == .success {
      guard let appcastXML = appcast.value else { return fallback }
      return resolveFreshInstallUpdateChannel(
        currentBuild: currentBuild,
        fallback: fallback,
        appcastXML: appcastXML
      )
    }

    DispatchQueue.global(qos: .utility).async {
      guard
        semaphore.wait(timeout: .now() + channelProbeRequestTimeout + 0.5) == .success,
        let appcastXML = appcast.value
      else { return }

      let resolved = resolveFreshInstallUpdateChannel(
        currentBuild: currentBuild,
        fallback: fallback,
        appcastXML: appcastXML
      )
      guard resolved != fallback else { return }
      persistLateCorrection(resolved)
    }

    return fallback
  }

  private static func fetchDesktopAppcast(completion: @escaping @Sendable (String?) -> Void) {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.timeoutIntervalForRequest = channelProbeRequestTimeout
    configuration.timeoutIntervalForResource = channelProbeRequestTimeout

    let session = URLSession(configuration: configuration)
    session.dataTask(with: desktopAppcastURL) { data, _, _ in
      defer { session.finishTasksAndInvalidate() }
      guard let data, let xml = String(data: data, encoding: .utf8) else {
        completion(nil)
        return
      }
      completion(xml)
    }.resume()
  }

  private static func storeLateChannelCorrection(_ resolved: String) {
    DispatchQueue.main.async {
      // Only upgrade the guess this probe stored — never clobber a channel the user
      // picked in Settings while the appcast was still in flight.
      guard currentUpdateChannel == "stable" else { return }
      UserDefaults.standard.set(resolved, forKey: updateChannelDefaultsKey)
      log("AppBuild: appcast answered after the launch budget; update channel set to \(resolved)")
    }
  }
}

private final class AppcastProbeResult: @unchecked Sendable {
  private let lock = NSLock()
  private var xml: String?

  func set(_ value: String?) {
    lock.lock()
    defer { lock.unlock() }
    xml = value
  }

  var value: String? {
    lock.lock()
    defer { lock.unlock() }
    return xml
  }
}
