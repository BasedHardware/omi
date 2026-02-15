import Foundation
import SwiftUI
import Sparkle

/// Delegate to track Sparkle update events for analytics
final class UpdaterDelegate: NSObject, SPUUpdaterDelegate {

    /// Back-reference to the view model (set after init)
    weak var viewModel: UpdaterViewModel?

    /// Called when Sparkle is about to check for updates (permission gate)
    func updater(_ updater: SPUUpdater, mayPerform check: SPUUpdateCheck) throws {
        Task { @MainActor in
            log("Sparkle: Starting update check")
            AnalyticsManager.shared.updateCheckStarted()
        }
    }

    /// Called when Sparkle finishes loading the appcast
    func updater(_ updater: SPUUpdater, didFinishLoading appcast: SUAppcast) {
        Task { @MainActor in
            log("Sparkle: Appcast loaded (\(appcast.items.count) items)")
        }
    }

    /// Called when Sparkle finds a valid update
    func updater(_ updater: SPUUpdater, didFindValidUpdate item: SUAppcastItem) {
        let version = item.displayVersionString
        Task { @MainActor in
            log("Sparkle: Found update v\(version)")
            AnalyticsManager.shared.updateAvailable(version: version)
            self.viewModel?.updateAvailable = true
            self.viewModel?.availableVersion = version
        }
    }

    /// Called when no update is available
    func updaterDidNotFindUpdate(_ updater: SPUUpdater) {
        Task { @MainActor in
            log("Sparkle: No update available")
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
        Task { @MainActor in
            if isUpToDate {
                log("Sparkle: Already up to date")
            } else {
                log("Sparkle: Update check failed - \(message)")
                AnalyticsManager.shared.updateCheckFailed(error: message)
            }
        }
    }

    /// Called when an update will be installed
    func updater(_ updater: SPUUpdater, willInstallUpdate item: SUAppcastItem) {
        let version = item.displayVersionString
        Task { @MainActor in
            log("Sparkle: Installing update v\(version)")
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

    /// Whether automatic update checks are enabled
    @Published var automaticallyChecksForUpdates: Bool {
        didSet {
            updaterController.updater.automaticallyChecksForUpdates = automaticallyChecksForUpdates
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

        // Initialize published property from updater state (must be before using `self`)
        automaticallyChecksForUpdates = updaterController.updater.automaticallyChecksForUpdates

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
}
