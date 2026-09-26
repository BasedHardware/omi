import XCTest

@testable import Omi_Computer

@MainActor
final class MonitoringSessionStoreTests: XCTestCase {
  /// Suite name kept alongside its store rather than stashed inside it: the
  /// name is test scaffolding, not app state, and writing it into the defaults
  /// under an inline key is exactly what `omi_inline_userdefaults_key` forbids.
  private var suitesToRemove: [(name: String, defaults: UserDefaults)] = []

  // No `super.tearDown()`: Xcode 16.4 rejects the non-Sendable XCTestCase
  // transfer it implies from a `@MainActor` async hook, and the repo gate fails
  // it. Matches the convention in APIClientAuthRetryTests and friends. A
  // synchronous override is not the alternative — it is nonisolated and so
  // cannot touch this actor-isolated state at all.
  override func tearDown() async throws {
    for suite in suitesToRemove {
      suite.defaults.removePersistentDomain(forName: suite.name)
    }
    suitesToRemove.removeAll()
  }

  /// A private defaults suite per test, so persistence is exercised for real
  /// without any test seeing another's state.
  private func makeDefaults() throws -> UserDefaults {
    let suiteName = "MonitoringSessionStoreTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    suitesToRemove.append((suiteName, defaults))
    return defaults
  }

  func testLoadReturnsNilWhenNothingSaved() throws {
    let store = MonitoringSessionDefaultsStore(defaults: try makeDefaults())
    XCTAssertNil(store.load())
  }

  func testSaveThenLoadRoundTripsTheRecord() throws {
    let store = MonitoringSessionDefaultsStore(defaults: try makeDefaults())
    let record = MonitoringSessionRecord(
      sessionID: "session-1",
      startedAt: Date(timeIntervalSinceReferenceDate: 0),
      lastHeartbeatAt: Date(timeIntervalSinceReferenceDate: 60),
      pausedSeconds: 5,
      pauseStartedAt: Date(timeIntervalSinceReferenceDate: 45),
      endedAt: nil,
      endReason: nil
    )

    store.save(record)

    XCTAssertEqual(store.load(), record)
  }

  /// `pauseStartedAt` was added after the first version of this record shipped
  /// to nightly builds. A stored record without the key must still decode —
  /// otherwise the upgrade silently drops every in-flight session instead of
  /// recovering it.
  func testARecordStoredWithoutPauseStartedAtStillDecodes() throws {
    let defaults = try makeDefaults()
    let legacy = """
      {"sessionID":"legacy-1","startedAt":0,"lastHeartbeatAt":60,"pausedSeconds":5}
      """
    defaults.set(Data(legacy.utf8), forKey: MonitoringSessionDefaultsStore.defaultsKey)

    let loaded = MonitoringSessionDefaultsStore(defaults: defaults).load()

    XCTAssertEqual(loaded?.sessionID, "legacy-1")
    XCTAssertNil(loaded?.pauseStartedAt)
    XCTAssertEqual(loaded?.pausedSeconds, 5)
  }

  // MARK: - Session ownership

  /// `SingleInstanceGuard` deliberately allows a rewind-only process
  /// (`--mode=rewind`) beside the full app. Both share one `UserDefaults`
  /// domain and one key, and the rewind window runs `DesktopHomeView`, which
  /// restores capture intent and calls `startMonitoring` — so without an
  /// ownership gate it is a second writer to a single slot, overwriting a live
  /// session with its own and stamping it on quit.
  ///
  /// The gate lives on the store rather than on each call site because start,
  /// heartbeat, pause, resume, recovery, and the quit stamp are all writers.
  func testANonOwningProcessNeitherReadsNorWritesTheSharedRecord() throws {
    let defaults = try makeDefaults()
    let owner = MonitoringSessionDefaultsStore(defaults: defaults)
    let record = MonitoringSessionRecord(
      sessionID: "owned-session",
      startedAt: Date(timeIntervalSinceReferenceDate: 0),
      lastHeartbeatAt: Date(timeIntervalSinceReferenceDate: 600),
      pausedSeconds: 0,
      pauseStartedAt: nil,
      endedAt: nil,
      endReason: nil
    )
    owner.save(record)

    let guest = MonitoringSessionDefaultsStore(defaults: defaults, ownsSession: false)

    XCTAssertNil(guest.load(), "a non-owning process must not recover another process's live session")

    guest.save(
      MonitoringSessionRecord(
        sessionID: "guest-session",
        startedAt: Date(timeIntervalSinceReferenceDate: 100),
        lastHeartbeatAt: Date(timeIntervalSinceReferenceDate: 100),
        pausedSeconds: 0,
        pauseStartedAt: nil,
        endedAt: nil,
        endReason: nil
      ))
    XCTAssertEqual(owner.load(), record, "a non-owning process must not overwrite the live session")

    guest.clear()
    XCTAssertEqual(owner.load(), record, "a non-owning process must not clear the live session")
  }

  func testClearRemovesTheRecord() throws {
    let store = MonitoringSessionDefaultsStore(defaults: try makeDefaults())
    store.save(
      MonitoringSessionRecord(
        sessionID: "session-2",
        startedAt: Date(timeIntervalSinceReferenceDate: 0),
        lastHeartbeatAt: Date(timeIntervalSinceReferenceDate: 0),
        pausedSeconds: 0,
        pauseStartedAt: nil,
        endedAt: nil,
        endReason: nil
      ))

    store.clear()

    XCTAssertNil(store.load())
  }
}
