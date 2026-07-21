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

  /// App display name based on update channel: "omi" for stable, "Omi Beta" for beta.
  /// Local hot-swap builds (self-beta.sh) stamp `OMISelfBuild=true` into Info.plist, so
  /// they show "Omi Beta (dev)" — a clear signal you're on a locally-rebuilt bundle, not a
  /// Codemagic-distributed one. A real Codemagic build never sets the key, and when it later
  /// replaces the hot-swap bundle via Sparkle the suffix disappears.
  static var appDisplayName: String {
    let channel = UserDefaults.standard.string(forKey: "update_channel") ?? "stable"
    let base = (channel == "beta" || channel == "staging") ? "Omi Beta" : "omi"
    let isSelfBuild = (Bundle.main.object(forInfoDictionaryKey: "OMISelfBuild") as? Bool) ?? false
    return isSelfBuild ? "\(base) (dev)" : base
  }
}

private let kUpdateChannelKey = "update_channel"

enum UpdateFailureReason: String {
  case appcastRetrieval = "appcast_retrieval"
  case download = "download"
  case signature = "signature"
  case readOnlyLocation = "read_only_location"
  case downloadsLocation = "downloads_location"
  case temporaryLocation = "temporary_location"
  case installerLaunch = "installer_launch"
  case network = "network"
  case noUpdate = "no_update"
  case unknown = "unknown"
}

struct UpdateFailureDiagnostics: Equatable {
  let reason: UpdateFailureReason
  let message: String
  let domain: String
  let code: Int
  let underlyingDomain: String?
  let underlyingCode: Int?
  let errorChainDomains: [String]
  let errorChainCodes: [Int]
  let nsurlErrorCode: Int?
  let failingURLHost: String?
  let failingURLPath: String?
  let updateChannel: String
  let launchLocationBucket: String
  let sourceAppVersion: String
  let sourceAppBuild: String
  let appcastURLHost: String?
  let appcastURLPath: String?

  var isRecoverableLaunchLocation: Bool {
    switch reason {
    case .readOnlyLocation, .downloadsLocation, .temporaryLocation:
      return true
    default:
      return false
    }
  }

  var userMessage: String {
    if isRecoverableLaunchLocation {
      return
        "Omi cannot update from its current location. Move it to Applications, reopen it, then check again."
    }

    switch reason {
    case .appcastRetrieval:
      return
        "Omi could not retrieve update information. You can try again or download the latest version manually."
    case .download:
      return
        "Omi found an update but could not download it. You can try again or download the latest version manually."
    case .signature:
      return "Omi could not verify the downloaded update. Download the latest version manually."
    case .network:
      return
        "Omi could not reach the update server. Check your connection or download the latest version manually."
    case .installerLaunch:
      return
        "Omi downloaded an update but could not start the installer. Try again or download the latest version manually."
    case .noUpdate:
      return "Omi is up to date."
    case .unknown:
      return
        "Omi could not complete the update check. You can try again or download the latest version manually."
    case .readOnlyLocation, .downloadsLocation, .temporaryLocation:
      return
        "Omi cannot update from its current location. Move it to Applications, reopen it, then check again."
    }
  }

  var analyticsProperties: [String: Any] {
    let telemetryMessage = message.isEmpty ? "\(domain) \(code)" : message
    var properties: [String: Any] = [
      // Emit the human-readable message under "error" so the daily report's
      // error_or_message column is populated (previously blank on Update Check Failed).
      "error": telemetryMessage,
      "phase": reason.rawValue,
      "update_failure_message": telemetryMessage,
      "update_failure_phase": reason.rawValue,
      "update_failure_reason": reason.rawValue,
      "update_failure_domain": domain,
      "update_failure_code": code,
      "update_channel": updateChannel,
      "launch_location_bucket": launchLocationBucket,
      "source_app_version": sourceAppVersion,
      "source_app_build": sourceAppBuild,
      "error_chain_domains": errorChainDomains,
      "error_chain_codes": errorChainCodes,
    ]

    if let underlyingDomain {
      properties["underlying_domain"] = underlyingDomain
    }
    if let underlyingCode {
      properties["underlying_code"] = underlyingCode
    }
    if let nsurlErrorCode {
      properties["nsurl_error_code"] = nsurlErrorCode
    }
    if let failingURLHost {
      properties["failing_url_host"] = failingURLHost
    }
    if let failingURLPath {
      properties["failing_url_path"] = failingURLPath
    }
    if let appcastURLHost {
      properties["appcast_url_host"] = appcastURLHost
    }
    if let appcastURLPath {
      properties["appcast_url_path"] = appcastURLPath
    }

    return properties
  }

  static func classify(
    error: NSError,
    updateChannel: String,
    bundlePath: String = Bundle.main.bundlePath,
    sourceAppVersion: String = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
      ?? "unknown",
    sourceAppBuild: String = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown",
    appcastURL: URL? = Bundle.main.object(forInfoDictionaryKey: "SUFeedURL")
      .flatMap({ ($0 as? String).flatMap(URL.init(string:)) })
  ) -> UpdateFailureDiagnostics {
    let underlying = error.userInfo[NSUnderlyingErrorKey] as? NSError
    let chain = errorChain(from: error)
    let nsurlError = chain.first { $0.domain == NSURLErrorDomain }
    let failingURL = failingURL(in: chain)
    let message = error.localizedDescription
    let bucket = launchLocationBucket(for: bundlePath)

    return UpdateFailureDiagnostics(
      reason: reason(
        for: error,
        errorChain: chain,
        message: message.lowercased(),
        bucket: bucket
      ),
      message: message,
      domain: error.domain,
      code: error.code,
      underlyingDomain: underlying?.domain,
      underlyingCode: underlying?.code,
      errorChainDomains: chain.map(\.domain),
      errorChainCodes: chain.map(\.code),
      nsurlErrorCode: nsurlError?.code,
      failingURLHost: failingURL?.host,
      failingURLPath: failingURL?.path,
      updateChannel: updateChannel,
      launchLocationBucket: bucket,
      sourceAppVersion: sourceAppVersion,
      sourceAppBuild: sourceAppBuild,
      appcastURLHost: appcastURL?.host,
      appcastURLPath: appcastURL?.path
    )
  }

  static func launchLocationBucket(for bundlePath: String) -> String {
    let path = bundlePath.lowercased()

    if path.hasPrefix("/volumes/") {
      return "dmg_mounted"
    }
    if path.contains("/downloads/") {
      return "downloads_folder"
    }
    if path.hasPrefix("/private/var/folders/") || path.hasPrefix("/tmp/")
      || path.hasPrefix("/private/tmp/")
    {
      return "temporary_location"
    }
    if path.hasPrefix("/applications/") {
      return "applications_system"
    }
    if path.contains("/applications/") {
      return "applications_user"
    }

    return "other"
  }

  private static func reason(
    for error: NSError,
    errorChain: [NSError],
    message: String,
    bucket: String
  ) -> UpdateFailureReason {
    if error.domain == SUSparkleErrorDomain && error.code == 1001 {
      return .noUpdate
    }
    if message.contains("read-only") {
      return .readOnlyLocation
    }
    if message.contains("location it was downloaded to") || bucket == "downloads_folder" {
      return .downloadsLocation
    }
    if message.contains("temporary location") || bucket == "temporary_location"
      || bucket == "dmg_mounted"
    {
      return .temporaryLocation
    }
    if error.domain == SUSparkleErrorDomain && error.code == 4005 {
      return .installerLaunch
    }
    if errorChain.contains(where: { $0.domain == NSURLErrorDomain }) {
      return .network
    }
    if message.contains("retrieving update information") || message.contains("appcast") {
      return .appcastRetrieval
    }
    if message.contains("downloading the update") || message.contains("download") {
      return .download
    }
    if message.contains("signature") || message.contains("verify") || message.contains("ed25519") {
      return .signature
    }

    return .unknown
  }

  private static func errorChain(from error: NSError) -> [NSError] {
    var chain: [NSError] = []
    var current: NSError? = error
    var seen = Set<ObjectIdentifier>()

    while let error = current {
      let identifier = ObjectIdentifier(error)
      guard !seen.contains(identifier) else { break }
      seen.insert(identifier)
      chain.append(error)
      current = error.userInfo[NSUnderlyingErrorKey] as? NSError
    }

    return chain
  }

  private static func failingURL(in errorChain: [NSError]) -> URL? {
    for error in errorChain {
      if let url = error.userInfo[NSURLErrorFailingURLErrorKey] as? URL {
        return url
      }
      if let urlString = error.userInfo[NSURLErrorFailingURLStringErrorKey] as? String,
        let url = URL(string: urlString)
      {
        return url
      }
    }
    return nil
  }
}

struct UpdateAnalyticsContext {
  let sourceAppVersion: String
  let sourceAppBuild: String
  let updateChannel: String
  let appcastURLHost: String?
  let appcastURLPath: String?

  var properties: [String: Any] {
    var properties: [String: Any] = [
      "source_app_version": sourceAppVersion,
      "source_app_build": sourceAppBuild,
      "update_channel": updateChannel,
    ]
    if let appcastURLHost {
      properties["appcast_url_host"] = appcastURLHost
    }
    if let appcastURLPath {
      properties["appcast_url_path"] = appcastURLPath
    }
    return properties
  }

  static func current(updateChannel: String) -> UpdateAnalyticsContext {
    let appcastURL = Bundle.main.object(forInfoDictionaryKey: "SUFeedURL")
      .flatMap { ($0 as? String).flatMap(URL.init(string:)) }

    return UpdateAnalyticsContext(
      sourceAppVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString")
        as? String ?? "unknown",
      sourceAppBuild: Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        ?? "unknown",
      updateChannel: updateChannel,
      appcastURLHost: appcastURL?.host,
      appcastURLPath: appcastURL?.path
    )
  }
}

struct UpdateItemAnalytics {
  let targetVersion: String
  let targetBuild: String
  let itemChannel: String

  var properties: [String: Any] {
    [
      "target_version": targetVersion,
      "target_build": targetBuild,
      "item_channel": itemChannel,
    ]
  }

  static func from(item: SUAppcastItem) -> UpdateItemAnalytics {
    UpdateItemAnalytics(
      targetVersion: item.displayVersionString,
      targetBuild: item.versionString,
      itemChannel: (item.channel?.isEmpty == false) ? item.channel! : "stable"
    )
  }
}

/// Delegate to track Sparkle update events for analytics
final class UpdaterDelegate: NSObject, SPUUpdaterDelegate {

  /// Back-reference to the view model (set after init)
  weak var viewModel: UpdaterViewModel?
  private var deferredInstall: DeferredUpdateInstall?

  // NOTE: All delegate methods use logSync() to write synchronously to disk.
  // Sparkle may terminate the app immediately after willInstallUpdate / didAbortWithError,
  // so async logging (Task + logQueue.async) would be lost.

  /// Called when Sparkle is about to check for updates (permission gate)
  func updater(_ updater: SPUUpdater, mayPerform check: SPUUpdateCheck) throws {
    logSync("Sparkle: Starting update check")
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
      self.viewModel?.lastUpdateFailure = nil
    }
  }

  /// Called when Sparkle finds a valid update
  func updater(_ updater: SPUUpdater, didFindValidUpdate item: SUAppcastItem) {
    let version = item.displayVersionString
    let context = UpdateAnalyticsContext.current(
      updateChannel: UserDefaults.standard.string(forKey: kUpdateChannelKey) ?? "stable"
    )
    let itemAnalytics = UpdateItemAnalytics.from(item: item)
    logSync("Sparkle: Found update v\(version)")
    Task { @MainActor in
      AnalyticsManager.shared.updateAvailable(
        version: version,
        context: context,
        item: itemAnalytics
      )
      self.viewModel?.updateAvailable = true
      self.viewModel?.availableVersion = version
      self.viewModel?.lastUpdateFailure = nil
    }
  }

  /// Called when no update is available
  func updaterDidNotFindUpdate(_ updater: SPUUpdater) {
    logSync("Sparkle: No update available")
    Task { @MainActor in
      self.viewModel?.updateAvailable = false
      self.viewModel?.lastUpdateFailure = nil
    }
  }

  /// Called when the update driver aborts with an error
  /// Note: Sparkle also calls this with "You're up to date!" when no update is found,
  /// which is not an actual error — updaterDidNotFindUpdate handles that case.
  func updater(_ updater: SPUUpdater, didAbortWithError error: Error) {
    let message = error.localizedDescription
    let nsError = error as NSError
    let diagnostics = UpdateFailureDiagnostics.classify(
      error: nsError,
      updateChannel: UserDefaults.standard.string(forKey: kUpdateChannelKey) ?? "stable"
    )
    if diagnostics.reason == .noUpdate {
      logSync("Sparkle: Already up to date")
      Task { @MainActor in
        self.viewModel?.lastUpdateFailure = nil
      }
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

      // SUInstallationError (4005): Sparkle's installer failed to launch.
      // Don't open the browser — Sparkle will retry on next check cycle.
      let isInstallationError = nsError.domain == SUSparkleErrorDomain && nsError.code == 4005
      if isInstallationError {
        logSync("Sparkle: Installation failed (error 4005), will retry on next check")
      }

      Task { @MainActor in
        AnalyticsManager.shared.updateCheckFailed(diagnostics: diagnostics)
        self.viewModel?.lastUpdateFailure = diagnostics
      }
    }
  }

  /// Tells Sparkle which non-default channels this client wants to see.
  /// Channels are additive: the default (stable) channel is always included.
  /// Reads `AppBuild.currentUpdateChannel` so the Omi Beta identity stays pinned
  /// to the beta channel no matter what the defaults key says.
  func allowedChannels(for updater: SPUUpdater) -> Set<String> {
    if AppBuild.currentUpdateChannel == "beta" {
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
    let context = UpdateAnalyticsContext.current(
      updateChannel: UserDefaults.standard.string(forKey: kUpdateChannelKey) ?? "stable"
    )
    let itemAnalytics = UpdateItemAnalytics.from(item: item)
    logSync("Sparkle: Installing update v\(version)")
    let restoreMainWindow = AppDelegate.shouldRestoreMainWindowAfterUpdateRelaunch()
    let attempt = UpdateRelaunchWindowPolicy.markPendingRelaunch(
      restoreMainWindow: restoreMainWindow,
      sourceVersion: context.sourceAppVersion,
      sourceBuild: context.sourceAppBuild,
      targetVersion: itemAnalytics.targetVersion,
      targetBuild: itemAnalytics.targetBuild,
      channel: context.updateChannel
    )
    logSync(
      "Sparkle: Next launch will \(restoreMainWindow ? "restore" : "suppress") the main window after update"
    )
    Task { @MainActor in
      AnalyticsManager.shared.updateInstallStarted(attempt: attempt)
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

    if let lastSpeech = VADGateService.lastSpeechAt {
      let secondsSinceSpeech = Date().timeIntervalSince(lastSpeech)
      if secondsSinceSpeech < UpdaterDelegate.activeCallSilenceWindow {
        logSync(
          "Sparkle: Deferring update v\(version) — speech detected \(Int(secondsSinceSpeech))s ago (active recording)"
        )
        deferredInstall = DeferredUpdateInstall(
          version: version,
          silenceWindow: UpdaterDelegate.activeCallSilenceWindow,
          lastSpeechProvider: { VADGateService.lastSpeechAt },
          install: installationBlock
        )
        deferredInstall?.start()
        return true
      }
    }

    logSync("Sparkle: Triggering immediate installation for v\(version)")
    installationBlock()
    return true
  }

  /// Minimum seconds of VAD silence required before an auto-install is allowed.
  /// Matches the typical pause threshold at which a real conversation has wound down.
  fileprivate static let activeCallSilenceWindow: TimeInterval = 120
}

final class DeferredUpdateInstall {
  private static let minimumRetryDelay: TimeInterval = 5

  private let version: String
  private let silenceWindow: TimeInterval
  private let lastSpeechProvider: () -> Date?
  private let install: () -> Void
  private var pendingWorkItem: DispatchWorkItem?
  private var didInstall = false

  init(
    version: String,
    silenceWindow: TimeInterval,
    lastSpeechProvider: @escaping () -> Date?,
    install: @escaping () -> Void
  ) {
    self.version = version
    self.silenceWindow = silenceWindow
    self.lastSpeechProvider = lastSpeechProvider
    self.install = install
  }

  deinit {
    pendingWorkItem?.cancel()
  }

  func start(now: Date = Date()) {
    pendingWorkItem?.cancel()
    scheduleNextCheck(now: now)
  }

  private func scheduleNextCheck(now: Date) {
    guard !didInstall else { return }

    if let delay = Self.nextDelay(
      now: now,
      lastSpeechAt: lastSpeechProvider(),
      silenceWindow: silenceWindow,
      minimumRetryDelay: Self.minimumRetryDelay
    ) {
      logSync(
        "Sparkle: Deferred install for v\(version) will retry after \(Int(ceil(delay)))s of remaining silence"
      )
      let workItem = DispatchWorkItem { [weak self] in
        self?.scheduleNextCheck(now: Date())
      }
      pendingWorkItem = workItem
      DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: workItem)
      return
    }

    didInstall = true
    pendingWorkItem = nil
    logSync("Sparkle: Silence window satisfied, installing deferred update v\(version)")
    install()
  }

  static func nextDelay(
    now: Date,
    lastSpeechAt: Date?,
    silenceWindow: TimeInterval,
    minimumRetryDelay: TimeInterval = minimumRetryDelay
  ) -> TimeInterval? {
    guard let lastSpeechAt else { return nil }

    let secondsSinceSpeech = now.timeIntervalSince(lastSpeechAt)
    guard secondsSinceSpeech < silenceWindow else { return nil }

    return max(minimumRetryDelay, silenceWindow - secondsSinceSpeech)
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
    AppBuild.allowsSparkleUpdates && !AnalyticsManager.isDevBuild
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

  /// Last non-successful Sparkle update failure, if one needs user recovery.
  @Published var lastUpdateFailure: UpdateFailureDiagnostics?

  /// Latest stable build number from the appcast (for downgrade detection)
  @Published var latestStableBuildNumber: Int?

  /// Latest stable version string from the appcast (e.g. "0.11.48+11048")
  @Published var latestStableVersionString: String?

  /// The date of the last update check
  var lastUpdateCheckDate: Date? {
    updaterController.updater.lastUpdateCheckDate
  }

  private init() {
    if AppBuild.allowsSparkleUpdates {
      // Restore beta for users whose preference was overwritten by the March 27 bug
      AppBuild.migrateBetaChannelOverwrite()

      if UserDefaults.standard.string(forKey: kUpdateChannelKey) == nil {
        AppBuild.syncUpdateChannelOnFirstLaunch()
      }
    }

    // Preview builds must not use the shared update feed. Do not start Sparkle for those
    // artifacts; its manual and background entry points are guarded below as well.
    updaterController = SPUStandardUpdaterController(
      startingUpdater: AppBuild.allowsSparkleUpdates,
      updaterDelegate: updaterDelegate,
      userDriverDelegate: nil
    )

    // Initialize published properties from updater state (must be before using `self`)
    automaticallyChecksForUpdates = updaterController.updater.automaticallyChecksForUpdates
    automaticallyDownloadsUpdates = updaterController.updater.automaticallyDownloadsUpdates

    // Initialize update channel from UserDefaults
    // Normalize legacy "staging" → "beta" and "better" → "beta"
    var storedChannel = UserDefaults.standard.string(forKey: kUpdateChannelKey) ?? "stable"
    if storedChannel == "staging" || storedChannel == "better" { storedChannel = "beta" }
    updateChannel = UpdateChannel(rawValue: storedChannel) ?? .stable

    // Wire up delegate back-reference
    updaterDelegate.viewModel = self

    // Poll faster on the beta channel so testers pick up new builds within ~2 min of
    // publish; stable stays at the conservative 10-min cadence (unchanged for prod users).
    // (Release builds already auto-download + silent-install on quit, so a faster poll is
    // the only lever left for delivery latency after a build publishes.)
    updaterController.updater.updateCheckInterval = (updateChannel == .beta) ? 120 : 600

    if AppBuild.allowsSparkleUpdates {
      // Observe updater state changes only when Sparkle is active. In particular, do not let
      // its initial KVO value re-enable the update UI for a published preview app.
      updaterController.updater.publisher(for: \.canCheckForUpdates)
        .receive(on: DispatchQueue.main)
        .assign(to: &$canCheckForUpdates)

      updaterController.updater.publisher(for: \.sessionInProgress)
        .receive(on: DispatchQueue.main)
        .assign(to: &$updateSessionInProgress)
    }

    applyManagedUpdatePolicy()
    if !AppBuild.allowsSparkleUpdates {
      canCheckForUpdates = false
    }
    isInitialized = true
  }

  /// Quick check if Sparkle is mid-update (safe to call from anywhere)
  nonisolated static var isUpdateInProgress: Bool {
    _isUpdateInProgress
  }

  /// Manually check for updates
  func checkForUpdates() {
    guard AppBuild.allowsSparkleUpdates else { return }
    updaterController.checkForUpdates(nil)
  }

  /// Background update check (no UI). Used after channel changes.
  func checkForUpdatesInBackground() {
    guard AppBuild.allowsSparkleUpdates else { return }
    updaterController.updater.checkForUpdatesInBackground()
  }

  /// Force the runtime update policy:
  /// - release builds: always auto-check + auto-install
  /// - dev builds: keep both disabled to avoid replacing the local app
  func applyManagedUpdatePolicy() {
    let shouldAutoUpdate = AppBuild.allowsSparkleUpdates && !AnalyticsManager.isDevBuild
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
    guard AppBuild.allowsSparkleUpdates else { return }
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
