import Foundation

enum AppBuild {
  static let productionBundleIdentifier = "com.omi.computer-macos"
  private static let updateChannelDefaultsKey = "update_channel"
  private static let betaOverwriteMigrationKey = "didMigrateBetaOverwrite_v1"
  private static let desktopAppcastURL = URL(
    string: "https://api.omi.me/v2/desktop/appcast.xml?platform=macos")!

  static var bundleIdentifier: String {
    Bundle.main.bundleIdentifier ?? productionBundleIdentifier
  }

  static var isNonProduction: Bool {
    bundleIdentifier.hasPrefix("com.omi.") && bundleIdentifier != productionBundleIdentifier
  }

  static var isProductionBundle: Bool {
    bundleIdentifier == productionBundleIdentifier
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
  @discardableResult
  static func syncUpdateChannelOnFirstLaunch() -> String? {
    guard UserDefaults.standard.string(forKey: updateChannelDefaultsKey) == nil else { return nil }
    let resolved = resolveFreshInstallUpdateChannelSynchronously()
    UserDefaults.standard.set(resolved, forKey: updateChannelDefaultsKey)
    return resolved
  }

  /// One-time migration for users whose beta channel was overwritten to stable
  /// by the syncUpdateChannelWithInstalledApp() bug (commit 8c60fafe8, March 27 2026).
  /// Re-checks the appcast: if the current build is ahead of latest stable, restore beta.
  static func migrateBetaChannelOverwrite() {
    guard !UserDefaults.standard.bool(forKey: betaOverwriteMigrationKey) else { return }
    UserDefaults.standard.set(true, forKey: betaOverwriteMigrationKey)

    guard currentUpdateChannel == "stable" else { return }

    let resolved = resolveFreshInstallUpdateChannelSynchronously()
    if resolved == "beta" {
      UserDefaults.standard.set("beta", forKey: updateChannelDefaultsKey)
    }
  }

  static func prepareUpdateChannelForBackendRouting() {
    guard isProductionBundle else { return }

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

  private static func resolveFreshInstallUpdateChannelSynchronously(timeout: TimeInterval = 3) -> String {
    let fallback = inferredUpdateChannel

    if fallback == "beta" {
      return "beta"
    }

    guard let currentBuild = currentBuildNumber else {
      return fallback
    }

    let configuration = URLSessionConfiguration.ephemeral
    configuration.timeoutIntervalForRequest = timeout
    configuration.timeoutIntervalForResource = timeout

    let session = URLSession(configuration: configuration)
    let semaphore = DispatchSemaphore(value: 0)
    var appcastXML: String?

    let task = session.dataTask(with: desktopAppcastURL) { data, _, _ in
      defer { semaphore.signal() }
      guard let data, let xml = String(data: data, encoding: .utf8) else { return }
      appcastXML = xml
    }
    task.resume()

    let finishedInTime = semaphore.wait(timeout: .now() + timeout + 0.5) == .success
    session.finishTasksAndInvalidate()

    guard finishedInTime, let appcastXML else {
      return fallback
    }

    return resolveFreshInstallUpdateChannel(
      currentBuild: currentBuild,
      fallback: fallback,
      appcastXML: appcastXML
    )
  }
}
