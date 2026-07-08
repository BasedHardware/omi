import XCTest

@testable import Omi_Computer

@MainActor
final class ImportConnectorStatusStoreTests: XCTestCase {
  override func setUp() {
    super.setUp()
    resetImportConnectorDefaults()
    UserDefaults.standard.set("test-user", forKey: .authUserId)
  }

  override func tearDown() {
    resetImportConnectorDefaults()
    UserDefaults.standard.removeObject(forKey: .authUserId)
    super.tearDown()
  }

  func testSuccessfulZeroCountImportStaysConnectedAcrossStoreReloads() {
    let connector = ImportConnector.all.first { $0.id == "email" }!
    let syncedAt = Date(timeIntervalSince1970: 1_700_000_000)
    let store = ImportConnectorStatusStore()

    store.markSynced(
      connectorID: "email",
      sourceCount: 0,
      memoryCount: 0,
      lastDeltaCount: 0,
      syncedAt: syncedAt)

    let immediate = store.snapshot(for: connector)
    let reloaded = ImportConnectorStatusStore().snapshot(for: connector)

    XCTAssertTrue(immediate.isConnected)
    XCTAssertEqual(immediate.actionTitle, "Sync now")
    XCTAssertEqual(immediate.primaryText, "0 emails")
    XCTAssertTrue(reloaded.isConnected)
    XCTAssertEqual(reloaded.primaryText, "0 emails")
  }

  func testLocalFilesStartNotConnectedWithoutSuccessfulScan() {
    let connector = ImportConnector.all.first { $0.id == "local-files" }!
    let snapshot = ImportConnectorStatusStore().snapshot(for: connector)

    XCTAssertFalse(snapshot.isConnected)
    XCTAssertEqual(snapshot.actionTitle, "Connect")
    XCTAssertEqual(snapshot.primaryText, "Not connected")
  }

  func testSuccessfulZeroFileScanStaysConnectedAcrossStoreReloads() {
    let connector = ImportConnector.all.first { $0.id == "local-files" }!
    let syncedAt = Date(timeIntervalSince1970: 1_700_000_000)
    let store = ImportConnectorStatusStore()

    store.markSynced(
      connectorID: "local-files",
      sourceCount: 0,
      memoryCount: nil,
      lastDeltaCount: 0,
      availabilityText: "On-device index",
      syncedAt: syncedAt)

    let immediate = store.snapshot(for: connector)
    let reloaded = ImportConnectorStatusStore().snapshot(for: connector)

    XCTAssertTrue(immediate.isConnected)
    XCTAssertEqual(immediate.actionTitle, "Sync now")
    XCTAssertEqual(immediate.primaryText, "0 files indexed")
    XCTAssertTrue(reloaded.isConnected)
    XCTAssertEqual(reloaded.primaryText, "0 files indexed")
  }

  func testAvailabilityTextAloneDoesNotMarkConnectorConnected() {
    let connector = ImportConnector.all.first { $0.id == "apple-notes" }!
    UserDefaults.standard.set(
      "Private notes accessible",
      forKey: "appsImportConnectorAvailabilityText.test-user.apple-notes")

    let store = ImportConnectorStatusStore()
    let snapshot = store.snapshot(for: connector)
    let reloaded = ImportConnectorStatusStore().snapshot(for: connector)

    XCTAssertFalse(snapshot.isConnected)
    XCTAssertFalse(reloaded.isConnected)
  }

  func testPositiveCountWithoutSuccessfulSyncDoesNotMarkConnectorConnected() {
    let connector = ImportConnector.all.first { $0.id == "calendar" }!

    UserDefaults.standard.set(3, forKey: "appsImportConnectorSourceCount.test-user.calendar")
    let snapshot = ImportConnectorStatusStore().snapshot(for: connector)

    XCTAssertFalse(snapshot.isConnected)
    XCTAssertEqual(snapshot.actionTitle, "Connect")
  }

  func testLegacyManualImportCountStillMarksConnectorConnected() {
    let connector = ImportConnector.all.first { $0.id == "chatgpt" }!

    UserDefaults.standard.set(4, forKey: "onboardingChatGPTImportedMemoriesCount.test-user")
    let snapshot = ImportConnectorStatusStore().snapshot(for: connector)

    XCTAssertTrue(snapshot.isConnected)
    XCTAssertEqual(snapshot.actionTitle, "Update")
  }

  func testConnectorMetricsAreScopedBySignedInUser() {
    let connector = ImportConnector.all.first { $0.id == "email" }!
    let syncedAt = Date(timeIntervalSince1970: 1_700_000_000)
    let store = ImportConnectorStatusStore()

    store.markSynced(connectorID: "email", sourceCount: 12, memoryCount: 2, syncedAt: syncedAt)

    UserDefaults.standard.set("other-user", forKey: .authUserId)
    let otherUserSnapshot = ImportConnectorStatusStore().snapshot(for: connector)

    UserDefaults.standard.set("test-user", forKey: .authUserId)
    let originalUserSnapshot = ImportConnectorStatusStore().snapshot(for: connector)

    XCTAssertFalse(otherUserSnapshot.isConnected)
    XCTAssertEqual(otherUserSnapshot.actionTitle, "Connect")
    XCTAssertTrue(originalUserSnapshot.isConnected)
    XCTAssertEqual(originalUserSnapshot.primaryText, "12 emails • 2 memories")
  }

  func testResetSessionStateClearsConnectorMetricsUntilCurrentUserReloads() {
    let connector = ImportConnector.all.first { $0.id == "email" }!
    let syncedAt = Date(timeIntervalSince1970: 1_700_000_000)
    let store = ImportConnectorStatusStore()

    store.markSynced(connectorID: "email", sourceCount: 12, memoryCount: 2, syncedAt: syncedAt)
    XCTAssertTrue(store.snapshot(for: connector).isConnected)

    UserDefaults.standard.removeObject(forKey: .authUserId)
    store.resetSessionState()
    XCTAssertFalse(store.snapshot(for: connector).isConnected)

    UserDefaults.standard.set("test-user", forKey: .authUserId)
    XCTAssertTrue(ImportConnectorStatusStore().snapshot(for: connector).isConnected)
  }

  func testOmiDeviceHistoryMigratesLegacyGlobalKeyToCurrentUser() {
    UserDefaults.standard.set(true, forKey: "home-omi-device-account-history")
    UserDefaults.standard.set("test-user", forKey: .authUserId)

    let store = HomeStatusStore()

    XCTAssertTrue(store.accountHasOmiDeviceConversations)
    XCTAssertTrue(UserDefaults.standard.bool(forKey: "home-omi-device-account-history.test-user"))
  }

  private func resetImportConnectorDefaults() {
    let prefixes = [
      "appsImportConnectorSourceCount.",
      "appsImportConnectorMemoryCount.",
      "appsImportConnectorLastSyncedAt.",
      "appsImportConnectorLastDeltaCount.",
      "appsImportConnectorHasLastDelta.",
      "appsImportConnectorAvailabilityText.",
    ]
    for connector in ImportConnector.all {
      for prefix in prefixes {
        UserDefaults.standard.removeObject(forKey: prefix + connector.id)
        UserDefaults.standard.removeObject(forKey: prefix + "test-user." + connector.id)
        UserDefaults.standard.removeObject(forKey: prefix + "other-user." + connector.id)
      }
    }
    UserDefaults.standard.removeObject(forKey: "onboardingChatGPTImportedMemoriesCount")
    UserDefaults.standard.removeObject(forKey: "onboardingClaudeImportedMemoriesCount")
    UserDefaults.standard.removeObject(forKey: "onboardingChatGPTImportedMemoriesCount.test-user")
    UserDefaults.standard.removeObject(forKey: "onboardingClaudeImportedMemoriesCount.test-user")
    UserDefaults.standard.removeObject(forKey: "onboardingChatGPTImportedMemoriesCount.other-user")
    UserDefaults.standard.removeObject(forKey: "onboardingClaudeImportedMemoriesCount.other-user")
    UserDefaults.standard.removeObject(forKey: "home-omi-device-account-history")
    UserDefaults.standard.removeObject(forKey: "home-omi-device-account-history.test-user")
    UserDefaults.standard.removeObject(forKey: "home-omi-device-account-history.other-user")
  }
}
