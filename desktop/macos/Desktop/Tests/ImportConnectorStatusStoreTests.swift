import XCTest

@testable import Omi_Computer

@MainActor
final class ImportConnectorStatusStoreTests: XCTestCase {
  func testSuccessfulZeroCountImportStaysConnectedAcrossStoreReloads() {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let connector = ImportConnector.all.first { $0.id == "email" }!
    let syncedAt = Date(timeIntervalSince1970: 1_700_000_000)
    let store = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user")

    store.markSynced(
      connectorID: "email",
      sourceCount: 0,
      memoryCount: 0,
      lastDeltaCount: 0,
      syncedAt: syncedAt)

    let immediate = store.snapshot(for: connector)
    let reloaded = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user").snapshot(
      for: connector)

    XCTAssertTrue(immediate.isConnected)
    XCTAssertEqual(immediate.actionTitle, "Sync now")
    XCTAssertEqual(immediate.primaryText, "0 emails")
    XCTAssertTrue(reloaded.isConnected)
    XCTAssertEqual(reloaded.primaryText, "0 emails")
  }

  func testLocalFilesStartNotConnectedWithoutSuccessfulScan() {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let connector = ImportConnector.all.first { $0.id == "local-files" }!
    let snapshot = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user").snapshot(
      for: connector)

    XCTAssertFalse(snapshot.isConnected)
    XCTAssertEqual(snapshot.actionTitle, "Connect")
    XCTAssertEqual(snapshot.primaryText, "Not connected")
  }

  func testSuccessfulZeroFileScanStaysConnectedAcrossStoreReloads() {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let connector = ImportConnector.all.first { $0.id == "local-files" }!
    let syncedAt = Date(timeIntervalSince1970: 1_700_000_000)
    let store = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user")

    store.markSynced(
      connectorID: "local-files",
      sourceCount: 0,
      memoryCount: nil,
      lastDeltaCount: 0,
      availabilityText: "On-device index",
      syncedAt: syncedAt)

    let immediate = store.snapshot(for: connector)
    let reloaded = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user").snapshot(
      for: connector)

    XCTAssertTrue(immediate.isConnected)
    XCTAssertEqual(immediate.actionTitle, "Sync now")
    XCTAssertEqual(immediate.primaryText, "0 files indexed")
    XCTAssertTrue(reloaded.isConnected)
    XCTAssertEqual(reloaded.primaryText, "0 files indexed")
  }

  func testAvailabilityTextAloneDoesNotMarkConnectorConnected() {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let connector = ImportConnector.all.first { $0.id == "apple-notes" }!
    defaults.set("Private notes accessible", forKey: "appsImportConnectorAvailabilityText.apple-notes")

    let store = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user")
    let snapshot = store.snapshot(for: connector)
    let reloaded = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user").snapshot(
      for: connector)

    XCTAssertFalse(snapshot.isConnected)
    XCTAssertFalse(reloaded.isConnected)
  }

  func testPositiveCountWithoutSuccessfulSyncDoesNotMarkConnectorConnected() {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let connector = ImportConnector.all.first { $0.id == "calendar" }!

    defaults.set(3, forKey: "appsImportConnectorSourceCount.calendar")
    let snapshot = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user").snapshot(
      for: connector)

    XCTAssertFalse(snapshot.isConnected)
    XCTAssertEqual(snapshot.actionTitle, "Connect")
  }

  func testEventKitAccessProbePreservesImportedMetrics() {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let connector = ImportConnector.all.first { $0.id == "apple-calendar" }!
    let store = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user")

    store.markSynced(connectorID: connector.id, sourceCount: 500, memoryCount: 500)
    store.applyAppleEventKitStatus(.connected(itemCount: 1), connectorID: connector.id)

    let snapshot = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user").snapshot(for: connector)
    XCTAssertEqual(snapshot.primaryText, "500 events • 500 memories")
  }

  func testLegacyManualImportCountStillMarksConnectorConnected() {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let connector = ImportConnector.all.first { $0.id == "chatgpt" }!

    defaults.set(4, forKey: "onboardingChatGPTImportedMemoriesCount")
    let snapshot = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user").snapshot(
      for: connector)

    XCTAssertTrue(snapshot.isConnected)
    XCTAssertEqual(snapshot.actionTitle, "Update")
  }

  func testConnectorMetricsAreScopedToTheSignedInAccount() {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let connector = ImportConnector.all.first { $0.id == "email" }!

    let userAStore = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "user-a")
    userAStore.markSynced(connectorID: "email", sourceCount: 12)

    let userBStore = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "user-b")
    XCTAssertFalse(userBStore.snapshot(for: connector).isConnected)

    let reloadedUserAStore = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "user-a")
    XCTAssertTrue(reloadedUserAStore.snapshot(for: connector).isConnected)
    XCTAssertEqual(reloadedUserAStore.snapshot(for: connector).primaryText, "12 emails")
  }

  private func makeDefaults() -> (defaults: UserDefaults, suiteName: String) {
    let suiteName = "ImportConnectorStatusStoreTests.\(UUID().uuidString)"
    return (UserDefaults(suiteName: suiteName)!, suiteName)
  }
}
