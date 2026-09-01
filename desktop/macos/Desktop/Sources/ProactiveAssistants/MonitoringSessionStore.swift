import Foundation

/// Persistence seam for the active `MonitoringSessionRecord`, so a crash or
/// quit can be recovered at the next launch (see `MonitoringSessionRecovery`).
/// Small protocol boundary over UserDefaults — mirrors
/// `PendingCanonicalReceiptInvalidationPersisting`
/// (`MainWindow/Tasks/SuggestedTasksStore.swift`) — so tests inject a fake
/// store instead of touching the real UserDefaults domain.
@MainActor
protocol MonitoringSessionPersisting: AnyObject {
  /// The one active session record, if any. Nil once cleared or if nothing
  /// has ever been saved.
  func load() -> MonitoringSessionRecord?
  /// Overwrites the single stored record. Called on start and updated on
  /// every heartbeat, pause, and resume.
  func save(_ record: MonitoringSessionRecord)
  /// Removes the stored record. Called after a normal `stopMonitoring()`
  /// finishes and emits its event, and after a recovered record has been
  /// reported at next launch.
  func clear()
}

/// UserDefaults-backed implementation. JSON-encodes the single active
/// `MonitoringSessionRecord` under one key.
@MainActor
final class MonitoringSessionDefaultsStore: MonitoringSessionPersisting {
  /// Shared production instance. `ProactiveAssistantsPlugin` (writer) and
  /// `AnalyticsManager` (recovery reader at launch) both go through this one
  /// instance so they never disagree about where the record lives.
  ///
  /// Only the full app owns the record. `SingleInstanceGuard` deliberately
  /// permits a rewind-only process (`--mode=rewind`) beside the full app, and
  /// both share one `UserDefaults` domain and one key — so a rewind window is
  /// a second writer to a single slot. It runs `DesktopHomeView`, which
  /// restores persisted capture intent and calls `startMonitoring`, so without
  /// this gate it would overwrite a live session with its own, heartbeat over
  /// it, and stamp it on quit; the full app's hours would then be recovered as
  /// the rewind window's minutes, under the wrong `session_id`.
  ///
  /// Gating the store rather than each call site is deliberate: recovery,
  /// start, heartbeat, pause, resume, and the quit stamp are all writers, and
  /// a future one would silently inherit the hole.
  static let shared = MonitoringSessionDefaultsStore(ownsSession: OMIApp.launchMode == .full)

  static let defaultsKey = "monitoring.activeSession"

  private let defaults: UserDefaults
  private let key: String
  private let ownsSession: Bool

  init(
    defaults: UserDefaults = .standard,
    key: String = MonitoringSessionDefaultsStore.defaultsKey,
    ownsSession: Bool = true
  ) {
    self.defaults = defaults
    self.key = key
    self.ownsSession = ownsSession
  }

  func load() -> MonitoringSessionRecord? {
    guard ownsSession, let data = defaults.data(forKey: key) else { return nil }
    return try? JSONDecoder().decode(MonitoringSessionRecord.self, from: data)
  }

  func save(_ record: MonitoringSessionRecord) {
    guard ownsSession, let data = try? JSONEncoder().encode(record) else { return }
    defaults.set(data, forKey: key)
  }

  func clear() {
    guard ownsSession else { return }
    defaults.removeObject(forKey: key)
  }
}
