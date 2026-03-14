import Foundation
import Sparkle
import SwiftUI

/// Update channel for staged releases
enum UpdateChannel: String, CaseIterable {
  case stable = "stable"
  case beta = "beta"

  var displayName: String {
    switch self {
    case .stable: return "Stable"
    case .beta: return "Beta"
    }
  }

  var description: String {
    switch self {
    case .stable: return "Recommended for most users"
    case .beta: return "Early access to new features"
    }
  }

  /// App display name based on update channel: "omi" for stable, "Omi Beta" for beta
  static var appDisplayName: String {
    let channel = UserDefaults.standard.string(forKey: "update_channel") ?? "stable"
    return (channel == "beta" || channel == "staging") ? "Omi Beta" : "omi"
  }
}

private let kUpdateChannelKey = "update_channel"

/// Delegate to track Sparkle update events for analytics
final class UpdaterDelegate: NSObject, SPUUpdaterDelegate {

  /// Back-reference to the view model (set after init)
  weak var viewModel: UpdaterViewModel?

  // NOTE: All delegate methods use logSync() to write synchronously to disk.
  // Sparkle may terminate the app immediately after willInstallUpdate / didAbortWithError,
  // so async logging (Task + logQueue.async) would be lost.

  /// Called when Sparkle is about to check for updates (permission gate)
  func updater(_ updater: SPUUpdater, mayPerform check: SPUUpdateCheck) throws {
    logSync("Sparkle: Starting update check")
    Task { @MainActor in
      AnalyticsManager.shared.updateCheckStarted()
    }
  }

  /// Called when Sparkle finishes loading the appcast
  func updater(_ updater: SPUUpdater, didFinishLoading appcast: SUAppcast) {
    logSync("Sparkle: Appcast loaded (\(appcast.items.count) items)")

    // Capture latest stable build metadata for downgrade detection
    var bestStableBuild: Int?
    var bestStableVersion: String?
    for item in appcast.items {
      let isStable = item.channel == nil || item.channel?.isEmpty == true
      guard isStable, let build = Int(item.versionString) else { continue }
      if bestStableBuild == nil || build > bestStableBuild! {
        bestStableBuild = build
        bestStableVersion = item.displayVersionString
      }
    }
    // Always update (including nil) so stale data doesn't produce false downgrade alerts
    Task { @MainActor in
      self.viewModel?.latestStableBuildNumber = bestStableBuild
      self.viewModel?.latestStableVersionString = bestStableVersion
    }
  }

  /// Called when Sparkle finds a valid update
  func updater(_ updater: SPUUpdater, didFindValidUpdate item: SUAppcastItem) {
    let version = item.displayVersionString
    logSync("Sparkle: Found update v\(version)")
    Task { @MainActor in
      AnalyticsManager.shared.updateAvailable(version: version)
      self.viewModel?.updateAvailable = true
      self.viewModel?.availableVersion = version
    }
  }

  /// Called when no update is available
  func updaterDidNotFindUpdate(_ updater: SPUUpdater) {
    logSync("Sparkle: No update available")
    Task { @MainActor in
      AnalyticsManager.shared.updateNotFound()
      self.viewModel?.updateAvailable = false
    }
  }

  /// Called when the update driver aborts with an error
  /// Note: Sparkle also calls this with "You're up to date!" when no update is found,
  /// which is not an actual error — updaterDidNotFindUpdate handles that case.
  func updater(_ updater: SPUUpdater, didAbortWithError error: Error) {
    let message = error.localizedDescription
    let nsError = error as NSError
    let isUpToDate =
      nsError.domain == SUSparkleErrorDomain
      && nsError.code == 1001 /* SUNoUpdateError */
    if isUpToDate {
      logSync("Sparkle: Already up to date")
    } else {
      logSync(
        "Sparkle: Update check failed - \(message) [domain=\(nsError.domain) code=\(nsError.code)]")
      if let underlying = nsError.userInfo[NSUnderlyingErrorKey] as? NSError {
        logSync(
          "Sparkle: Underlying error - \(underlying.localizedDescription) [domain=\(underlying.domain) code=\(underlying.code)]"
        )
      }
      for (key, value) in nsError.userInfo where key != NSUnderlyingErrorKey {
        logSync("Sparkle: Error info [\(key)] = \(value)")
      }
      // Build diagnostic properties for analytics
      let errorDomain = nsError.domain
      let errorCode = nsError.code
      var underlyingMessage: String? = nil
      var underlyingDomain: String? = nil
      var underlyingCode: Int? = nil

      if let underlying = nsError.userInfo[NSUnderlyingErrorKey] as? NSError {
        underlyingMessage = underlying.localizedDescription
        underlyingDomain = underlying.domain
        underlyingCode = underlying.code
      }

      Task { @MainActor in
        AnalyticsManager.shared.updateCheckFailed(
          error: message,
          errorDomain: errorDomain,
          errorCode: errorCode,
          underlyingError: underlyingMessage,
          underlyingDomain: underlyingDomain,
          underlyingCode: underlyingCode
        )
      }

      // SUInstallationError (4005): Sparkle's installer failed to launch.
      // On macOS 26, AuthorizationCreate/SMJobSubmit can fail due to stricter
      // code signature validation or on-demand-only launchd mode.
      // Fallback: open the download page so the user can install manually.
      let isInstallationError = nsError.domain == SUSparkleErrorDomain && nsError.code == 4005
      if isInstallationError {
        logSync("Sparkle: Installation failed, opening download page as fallback")
        if let url = URL(string: "https://macos.omi.me") {
          NSWorkspace.shared.open(url)
        }
      }
    }
  }

  /// Tells Sparkle which non-default channels this client wants to see.
  /// Channels are additive: the default (stable) channel is always included.
  func allowedChannels(for updater: SPUUpdater) -> Set<String> {
    let raw = UserDefaults.standard.string(forKey: kUpdateChannelKey) ?? "stable"
    if raw == "beta" || raw == "staging" {
      return Set(["beta"])
    }
    return Set()  // empty = default (stable) channel only
  }

  /// Called after Sparkle has launched the installer and submitted launchd jobs.
  /// On macOS 26+, launchd may be in "on-demand-only mode" which prevents RunAtLoad
  /// services from starting. We force-start them via launchctl kickstart as a backup
  /// to Sparkle 2.9.0's built-in probe (PR #2852).
  func updater(_ updater: SPUUpdater, didExtractUpdate item: SUAppcastItem) {
    logSync("Sparkle: Installer launched for v\(item.displayVersionString), kickstarting services")
    kickstartSparkleServices()
  }

  /// Force-start Sparkle's launchd services to work around macOS 26 on-demand-only mode.
  /// Services submitted via SMJobSubmit with RunAtLoad=YES may not start immediately.
  /// Using `launchctl kickstart` forces launchd to spawn them right away.
  private func kickstartSparkleServices() {
    guard let bundleID = Bundle.main.bundleIdentifier else { return }

    let updaterLabel = "\(bundleID)-sparkle-updater"
    let progressLabel = "\(bundleID)-sparkle-progress"
    let uid = getuid()

    // Try multiple times to handle timing variance
    for delay in [0.5, 2.0, 5.0] {
      DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + delay) {
        for label in [progressLabel, updaterLabel] {
          let process = Process()
          process.executableURL = URL(fileURLWithPath: "/bin/launchctl")
          process.arguments = ["kickstart", "-p", "gui/\(uid)/\(label)"]
          process.standardOutput = FileHandle.nullDevice
          process.standardError = FileHandle.nullDevice

          do {
            try process.run()
            process.waitUntilExit()
            if process.terminationStatus == 0 {
              logSync("Sparkle kickstart: started \(label) (delay=\(delay)s)")
            }
          } catch {
            // Best effort — service may not exist yet or already running
          }
        }
      }
    }
  }

  /// Called when an update will be installed (app may terminate immediately after)
  func updater(_ updater: SPUUpdater, willInstallUpdate item: SUAppcastItem) {
    let version = item.displayVersionString
    logSync("Sparkle: Installing update v\(version)")
    Task { @MainActor in
      AnalyticsManager.shared.updateInstalled(version: version)
      self.viewModel?.updateAvailable = false
    }
  }

  /// Called when Sparkle has downloaded an update and scheduled it for silent install on quit.
  /// On release builds we immediately invoke the installation block so the app updates and relaunches
  /// without waiting for the user to manually quit.
  func updater(
    _ updater: SPUUpdater,
    willInstallUpdateOnQuit item: SUAppcastItem,
    immediateInstallationBlock installationBlock: @escaping () -> Void
  ) -> Bool {
    let version = item.displayVersionString
    logSync("Sparkle: Update v\(version) scheduled for install on quit")

    guard !AnalyticsManager.isDevBuild else {
      logSync("Sparkle: Leaving update scheduled for quit because this is a development build")
      return false
    }

    logSync("Sparkle: Triggering immediate installation for v\(version)")
    installationBlock()
    return true
  }
}

/// View model for managing Sparkle auto-updates
/// Provides SwiftUI bindings for the updater UI
@MainActor
final class UpdaterViewModel: ObservableObject {
  static let shared = UpdaterViewModel()

  private let updaterController: SPUStandardUpdaterController
  private let updaterDelegate = UpdaterDelegate()
  private var isInitialized = false

  var usesManagedUpdatePolicy: Bool {
    !AnalyticsManager.isDevBuild
  }

  /// Whether automatic update checks are enabled
  @Published var automaticallyChecksForUpdates: Bool {
    didSet {
      updaterController.updater.automaticallyChecksForUpdates = automaticallyChecksForUpdates
      if isInitialized {
        AnalyticsManager.shared.settingToggled(
          setting: "automatic_update_checks", enabled: automaticallyChecksForUpdates)
      }
    }
  }

  /// Whether updates are automatically downloaded and installed
  @Published var automaticallyDownloadsUpdates: Bool {
    didSet {
      updaterController.updater.automaticallyDownloadsUpdates = automaticallyDownloadsUpdates
      if isInitialized {
        AnalyticsManager.shared.settingToggled(
          setting: "auto_install_updates", enabled: automaticallyDownloadsUpdates)
      }
    }
  }

  /// Whether the updater can check for updates (e.g., not already checking)
  @Published private(set) var canCheckForUpdates: Bool = true

  /// Whether Sparkle has an active update session (downloading, installing, etc.)
  @Published private(set) var updateSessionInProgress: Bool = false {
    didSet { UpdaterViewModel._isUpdateInProgress = updateSessionInProgress }
  }

  /// Nonisolated snapshot for cross-actor reads
  private nonisolated(unsafe) static var _isUpdateInProgress: Bool = false

  /// Selected update channel (persisted to UserDefaults)
  @Published var updateChannel: UpdateChannel {
    didSet {
      guard oldValue != updateChannel else { return }

      // Must happen before check; Sparkle delegate reads from UserDefaults
      UserDefaults.standard.set(updateChannel.rawValue, forKey: kUpdateChannelKey)
      activeChannelLabel = updateChannel == .stable ? "" : updateChannel.displayName

      if isInitialized {
        AnalyticsManager.shared.settingToggled(
          setting: "update_channel", enabled: updateChannel != .stable)
        checkForUpdatesInBackground()
      }
    }
  }

  /// Whether a new update is available (set by delegate callbacks)
  @Published var updateAvailable: Bool = false

  /// Version string of the available update
  @Published var availableVersion: String = ""

  /// Latest stable build number from the appcast (for downgrade detection)
  @Published var latestStableBuildNumber: Int?

  /// Latest stable version string from the appcast (e.g. "0.11.48+11048")
  @Published var latestStableVersionString: String?

  /// The date of the last update check
  var lastUpdateCheckDate: Date? {
    updaterController.updater.lastUpdateCheckDate
  }

  private init() {
    // Initialize the updater controller with our delegate
    updaterController = SPUStandardUpdaterController(
      startingUpdater: true,
      updaterDelegate: updaterDelegate,
      userDriverDelegate: nil
    )

    // Initialize published properties from updater state (must be before using `self`)
    automaticallyChecksForUpdates = updaterController.updater.automaticallyChecksForUpdates
    automaticallyDownloadsUpdates = updaterController.updater.automaticallyDownloadsUpdates

    // Initialize update channel from UserDefaults
    // Normalize legacy "staging" → "beta" for users upgrading from older builds
    var storedChannel = UserDefaults.standard.string(forKey: kUpdateChannelKey) ?? "stable"
    if storedChannel == "staging" { storedChannel = "beta" }
    updateChannel = UpdateChannel(rawValue: storedChannel) ?? .stable

    // Wire up delegate back-reference
    updaterDelegate.viewModel = self

    // Check for updates every 10 minutes
    updaterController.updater.updateCheckInterval = 600

    // Observe updater state changes
    updaterController.updater.publisher(for: \.canCheckForUpdates)
      .receive(on: DispatchQueue.main)
      .assign(to: &$canCheckForUpdates)

    updaterController.updater.publisher(for: \.sessionInProgress)
      .receive(on: DispatchQueue.main)
      .assign(to: &$updateSessionInProgress)

    applyManagedUpdatePolicy()
    isInitialized = true
  }

  /// Quick check if Sparkle is mid-update (safe to call from anywhere)
  nonisolated static var isUpdateInProgress: Bool {
    _isUpdateInProgress
  }

  /// Manually check for updates
  func checkForUpdates() {
    updaterController.checkForUpdates(nil)
  }

  /// Background update check (no UI). Used after channel changes.
  func checkForUpdatesInBackground() {
    updaterController.updater.checkForUpdatesInBackground()
  }

  /// Force the runtime update policy:
  /// - release builds: always auto-check + auto-install
  /// - dev builds: keep both disabled to avoid replacing the local app
  func applyManagedUpdatePolicy() {
    let shouldAutoUpdate = !AnalyticsManager.isDevBuild
    automaticallyChecksForUpdates = shouldAutoUpdate
    automaticallyDownloadsUpdates = shouldAutoUpdate
    updaterController.updater.automaticallyChecksForUpdates = shouldAutoUpdate
    updaterController.updater.automaticallyDownloadsUpdates = shouldAutoUpdate
    logSync(
      "Sparkle: Managed policy applied - isDevBuild=\(AnalyticsManager.isDevBuild) autoChecks=\(updaterController.updater.automaticallyChecksForUpdates) autoDownloads=\(updaterController.updater.automaticallyDownloadsUpdates)"
    )
  }

  /// Trigger one immediate silent update check right after launch.
  /// Sparkle recommends calling this only immediately after starting the updater.
  func checkForUpdatesImmediatelyAfterLaunchIfNeeded() {
    guard usesManagedUpdatePolicy else { return }
    guard automaticallyChecksForUpdates else { return }
    guard canCheckForUpdates else { return }
    checkForUpdatesInBackground()
  }

  /// Get the current app version string
  var currentVersion: String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "Unknown"
  }

  /// Get the current build number
  var buildNumber: String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "Unknown"
  }

  /// The active channel label
  @Published var activeChannelLabel: String = {
    let raw = UserDefaults.standard.string(forKey: kUpdateChannelKey) ?? "stable"
    return (raw == "beta" || raw == "staging") ? "Beta" : ""
  }()

  /// Returns true if switching to stable would be a downgrade (current build > latest stable build)
  var isDowngradeToStable: Bool {
    guard let currentBuild = Int(buildNumber),
      let stableBuild = latestStableBuildNumber
    else {
      return false
    }
    return currentBuild > stableBuild
  }
}
