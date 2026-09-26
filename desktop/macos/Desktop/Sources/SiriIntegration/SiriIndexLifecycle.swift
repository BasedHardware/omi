import Foundation

@MainActor
final class SiriIndexLifecycle {
  static let shared = SiriIndexLifecycle()
  private var ownerObserver: NSObjectProtocol?
  private var preferenceObserver: NSObjectProtocol?
  private var maintenanceTimer: Timer?

  private init() {}

  func start(launchMode: String) {
    log("OmiApp: Main window content appeared (mode: \(launchMode))")
    guard ownerObserver == nil else { return }
    ownerObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange, object: nil, queue: .main
    ) { _ in
      SiriIndexHooks.ownerChanged()
    }
    preferenceObserver = NotificationCenter.default.addObserver(
      forName: .siriIndexPreferenceChanged, object: nil, queue: .main
    ) { _ in
      SiriIndexHooks.ownerChanged()
      if !SiriIntegrationSettings.isEnabled, #available(macOS 27, *) { Task { await SiriDonations.wipe() } }
    }
    maintenanceTimer = Timer.scheduledTimer(withTimeInterval: 3_600, repeats: true) { _ in
      SiriIndexHooks.rebuild()
    }
    SiriIndexHooks.rebuild()
    #if DEBUG
      if #available(macOS 27, *), ProcessInfo.processInfo.arguments.contains("-omi-siri-probe") {
        Task { await SiriDevProbe.run() }
      }
    #endif
  }

  /// A failed Spotlight wipe leaves the persisted previous owner intact.
  /// SiriIndexer.activeIndex() retries that wipe before it can index the next
  /// owner, so sign-out remains possible without leaking across accounts.
  static func suspendForOwnerTransition() async {
    await RewindIndexer.shared.suspendForOwnerTransition()
    if #available(macOS 15.4, *) {
      do { try await SiriIndexer.shared.wipe() } catch {
        log("Siri index owner wipe pending retry: \(error.localizedDescription)")
      }
    }
    if #available(macOS 27, *) { await SiriDonations.wipe() }
  }
}
