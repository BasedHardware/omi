import XCTest

@testable import Omi_Computer

@MainActor
final class ImportConnectorStatusStoreTests: XCTestCase {
  override func setUp() {
    super.setUp()
    resetImportConnectorDefaults()
  }

  override func tearDown() {
    resetImportConnectorDefaults()
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
    UserDefaults.standard.set("Private notes accessible", forKey: "appsImportConnectorAvailabilityText.apple-notes")

    let store = ImportConnectorStatusStore()
    let snapshot = store.snapshot(for: connector)
    let reloaded = ImportConnectorStatusStore().snapshot(for: connector)

    XCTAssertFalse(snapshot.isConnected)
    XCTAssertFalse(reloaded.isConnected)
  }

  func testPositiveCountWithoutSuccessfulSyncDoesNotMarkConnectorConnected() {
    let connector = ImportConnector.all.first { $0.id == "calendar" }!

    UserDefaults.standard.set(3, forKey: "appsImportConnectorSourceCount.calendar")
    let snapshot = ImportConnectorStatusStore().snapshot(for: connector)

    XCTAssertFalse(snapshot.isConnected)
    XCTAssertEqual(snapshot.actionTitle, "Connect")
  }

  func testLegacyManualImportCountStillMarksConnectorConnected() {
    let connector = ImportConnector.all.first { $0.id == "chatgpt" }!

    UserDefaults.standard.set(4, forKey: "onboardingChatGPTImportedMemoriesCount")
    let snapshot = ImportConnectorStatusStore().snapshot(for: connector)

    XCTAssertTrue(snapshot.isConnected)
    XCTAssertEqual(snapshot.actionTitle, "Update")
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
      }
    }
    UserDefaults.standard.removeObject(forKey: "onboardingChatGPTImportedMemoriesCount")
    UserDefaults.standard.removeObject(forKey: "onboardingClaudeImportedMemoriesCount")
  }
}
