import XCTest

@testable import Omi_Computer

final class AccountCutoverControlTests: XCTestCase {
  func testLegacyDefaultAllowsProductTraffic() {
    let gate = AccountCutoverGate()
    let control = AccountCutoverControl.legacyDefault
    XCTAssertEqual(gate.decide(control), .allowProductTraffic)
    XCTAssertTrue(gate.shouldUploadOfflineQueues(control))
    XCTAssertFalse(gate.shouldQuarantineOfflineQueues(control))
  }

  func testForceUpgradeFailsClosed() {
    let gate = AccountCutoverGate()
    var control = AccountCutoverControl.legacyDefault
    control.clientAction = .forceUpgrade
    control.productTrafficAllowed = false
    XCTAssertEqual(gate.decide(control), .forceUpgrade)
    XCTAssertFalse(gate.shouldUploadOfflineQueues(control))
  }

  func testMigrationMaintenanceDrainsQueues() {
    let gate = AccountCutoverGate()
    var control = AccountCutoverControl.legacyDefault
    control.state = .migrating
    control.clientAction = .migrationMaintenance
    control.productTrafficAllowed = false
    control.offlineQueueInstruction = .drain
    XCTAssertEqual(gate.decide(control), .migrationMaintenance)
    XCTAssertTrue(gate.shouldUploadOfflineQueues(control))
  }

  func testQuarantineBlocksOfflineQueuesAndSurfacesStrandedData() {
    let gate = AccountCutoverGate()
    var control = AccountCutoverControl.legacyDefault
    control.state = .rolledBackStranded
    control.clientAction = .migrationMaintenance
    control.productTrafficAllowed = false
    control.offlineQueueInstruction = .quarantine
    control.strandedNewData = true
    XCTAssertTrue(gate.shouldQuarantineOfflineQueues(control))
    XCTAssertFalse(gate.shouldUploadOfflineQueues(control))
    XCTAssertTrue(control.strandedNewData)
  }

  @MainActor
  func testManagerAppliesFetchedControl() async {
    let manager = AccountCutoverControlManager {
      var control = AccountCutoverControl.legacyDefault
      control.state = .migrating
      control.clientAction = .migrationMaintenance
      control.productTrafficAllowed = false
      control.offlineQueueInstruction = .drain
      control.accountGeneration = 2
      return control
    }
    await manager.refresh()
    XCTAssertEqual(manager.decision, .migrationMaintenance)
    XCTAssertEqual(manager.control.accountGeneration, 2)
    XCTAssertTrue(manager.allowsOfflineQueueUpload)
  }
}
