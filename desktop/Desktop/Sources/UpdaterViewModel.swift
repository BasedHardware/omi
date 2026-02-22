import Foundation
import SwiftUI
import Sparkle

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
        let isUpToDate = nsError.domain == SUSparkleErrorDomain
            && nsError.code == 1001 /* SUNoUpdateError */
        if isUpToDate {
            logSync("Sparkle: Already up to date")
        } else {
            logSync("Sparkle: Update check failed - \(message)")
            Task { @MainActor in
                AnalyticsManager.shared.updateCheckFailed(error: message)
            }
        }
    }

    /// Tells Sparkle which non-default channels this client wants to see.
    /// Channels are additive: the default (stable) channel is always included.
    func allowedChannels(for updater: SPUUpdater) -> Set<String> {
        let raw = UserDefaults.standard.string(forKey: kUpdateChannelKey) ?? "stable"
        switch raw {
        case "staging":
            return Set(["staging", "beta"])
        case "beta":
            return Set(["beta"])
        default:
            return Set() // empty = default (stable) channel only
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
}

/// View model for managing Sparkle auto-updates
/// Provides SwiftUI bindings for the updater UI
@MainActor
final class UpdaterViewModel: ObservableObject {
    static let shared = UpdaterViewModel()

    private let updaterController: SPUStandardUpdaterController
    private let updaterDelegate = UpdaterDelegate()
    private var isInitialized = false

    /// Whether automatic update checks are enabled
    @Published var automaticallyChecksForUpdates: Bool {
        didSet {
            updaterController.updater.automaticallyChecksForUpdates = automaticallyChecksForUpdates
            if isInitialized {
                AnalyticsManager.shared.settingToggled(setting: "automatic_update_checks", enabled: automaticallyChecksForUpdates)
            }
        }
    }

    /// Whether updates are automatically downloaded and installed
    @Published var automaticallyDownloadsUpdates: Bool {
        didSet {
            updaterController.updater.automaticallyDownloadsUpdates = automaticallyDownloadsUpdates
            if isInitialized {
                AnalyticsManager.shared.settingToggled(setting: "auto_install_updates", enabled: automaticallyDownloadsUpdates)
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
            UserDefaults.standard.set(updateChannel.rawValue, forKey: kUpdateChannelKey)
            activeChannelLabel = updateChannel == .stable ? "" : updateChannel.displayName
            if isInitialized {
                AnalyticsManager.shared.settingToggled(setting: "update_channel", enabled: updateChannel != .stable)
            }
        }
    }

    /// Whether a new update is available (set by delegate callbacks)
    @Published var updateAvailable: Bool = false

    /// Version string of the available update
    @Published var availableVersion: String = ""

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
        let storedChannel = UserDefaults.standard.string(forKey: kUpdateChannelKey) ?? "stable"
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

    /// Get the current app version string
    var currentVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "Unknown"
    }

    /// Get the current build number
    var buildNumber: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "Unknown"
    }

    /// The active channel label, including the hidden "staging" option
    @Published var activeChannelLabel: String = {
        let raw = UserDefaults.standard.string(forKey: kUpdateChannelKey) ?? "stable"
        switch raw {
        case "staging": return "Staging"
        case "beta": return "Beta"
        default: return ""
        }
    }()
}
