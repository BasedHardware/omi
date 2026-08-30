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
