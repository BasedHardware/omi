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

  func testAvailabilityTextMarksZeroCountConnectorConnectedAcrossStoreReloads() {
    let connector = ImportConnector.all.first { $0.id == "apple-notes" }!
    let store = ImportConnectorStatusStore()

    store.markSynced(
      connectorID: "apple-notes",
      sourceCount: 0,
      memoryCount: 0,
      lastDeltaCount: 0,
      availabilityText: "Private notes accessible")

    let immediate = store.snapshot(for: connector)
    let reloaded = ImportConnectorStatusStore().snapshot(for: connector)

    XCTAssertTrue(immediate.isConnected)
    XCTAssertEqual(immediate.actionTitle, "Sync now")
    XCTAssertTrue(reloaded.isConnected)
    XCTAssertEqual(reloaded.primaryText, "Private notes accessible")
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
  }
}
