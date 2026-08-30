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
  static let shared = MonitoringSessionDefaultsStore()

  static let defaultsKey = "monitoring.activeSession"

  private let defaults: UserDefaults
  private let key: String

  init(defaults: UserDefaults = .standard, key: String = MonitoringSessionDefaultsStore.defaultsKey) {
    self.defaults = defaults
    self.key = key
  }

  func load() -> MonitoringSessionRecord? {
    guard let data = defaults.data(forKey: key) else { return nil }
    return try? JSONDecoder().decode(MonitoringSessionRecord.self, from: data)
  }

  func save(_ record: MonitoringSessionRecord) {
    guard let data = try? JSONEncoder().encode(record) else { return }
    defaults.set(data, forKey: key)
  }

  func clear() {
    defaults.removeObject(forKey: key)
  }
}
