import XCTest

@testable import Omi_Computer

@MainActor
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

  func testMigrationMaintenanceQuarantinesQueues() {
    let gate = AccountCutoverGate()
    var control = AccountCutoverControl.legacyDefault
    control.state = .migrating
    control.clientAction = .migrationMaintenance
    control.productTrafficAllowed = false
    control.offlineQueueInstruction = .quarantine
    XCTAssertEqual(gate.decide(control), .migrationMaintenance)
    XCTAssertFalse(gate.shouldUploadOfflineQueues(control))
    XCTAssertTrue(gate.shouldQuarantineOfflineQueues(control))
  }

  func testDrainOnlyWhileProductTrafficAllowed() {
    let gate = AccountCutoverGate()
    var control = AccountCutoverControl.legacyDefault
    control.offlineQueueInstruction = .drain
    XCTAssertTrue(gate.shouldUploadOfflineQueues(control))

    control.clientAction = .migrationMaintenance
    control.productTrafficAllowed = false
    control.state = .migrating
    XCTAssertFalse(gate.shouldUploadOfflineQueues(control))
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

  func testManagerStartsPendingAndBlocksProductShell() {
    let manager = AccountCutoverControlManager(
      fetchControl: { AccountCutoverControl.legacyDefault },
      currentOwnerID: { "owner-a" }
    )
    manager.resetForTesting()
    XCTAssertEqual(manager.bootstrapPhase, .pending)
    XCTAssertTrue(manager.blocksProductTraffic)
    XCTAssertFalse(manager.isProductShellAdmitted)
    XCTAssertFalse(manager.allowsOfflineQueueUpload)
    XCTAssertEqual(manager.overlayDecision, .migrationMaintenance)
  }

  func testManagerAppliesFetchedControl() async {
    let manager = AccountCutoverControlManager(
      fetchControl: {
        var control = AccountCutoverControl.legacyDefault
        control.state = .migrating
        control.clientAction = .migrationMaintenance
        control.productTrafficAllowed = false
        control.offlineQueueInstruction = .quarantine
        control.accountGeneration = 2
        return control
      },
      currentOwnerID: { "owner-a" }
    )
    await manager.bindCurrentOwnerAndRefresh()
    XCTAssertEqual(manager.bootstrapPhase, .ready)
    XCTAssertEqual(manager.decision, .migrationMaintenance)
    XCTAssertEqual(manager.control.accountGeneration, 2)
    XCTAssertFalse(manager.allowsOfflineQueueUpload)
    XCTAssertTrue(manager.blocksProductTraffic)
    XCTAssertFalse(manager.isProductShellAdmitted)
  }

  func testRefreshFailureRetainsLastConfirmedControl() async {
    final class FetchState: @unchecked Sendable {
      var shouldFail = false
    }
    let state = FetchState()
    let manager = AccountCutoverControlManager(
      fetchControl: {
        if state.shouldFail {
          throw APIError.invalidResponse
        }
        var control = AccountCutoverControl.legacyDefault
        control.state = .migrating
        control.clientAction = .migrationMaintenance
        control.productTrafficAllowed = false
        control.offlineQueueInstruction = .quarantine
        control.accountGeneration = 7
        return control
      },
      currentOwnerID: { "owner-a" }
    )

    await manager.bindCurrentOwnerAndRefresh()
    XCTAssertEqual(manager.control.accountGeneration, 7)
    XCTAssertEqual(manager.decision, .migrationMaintenance)

    state.shouldFail = true
    await manager.refresh()
    XCTAssertEqual(manager.bootstrapPhase, .ready)
    XCTAssertEqual(manager.control.accountGeneration, 7)
    XCTAssertEqual(manager.decision, .migrationMaintenance)
    XCTAssertFalse(manager.allowsOfflineQueueUpload)
  }

  func testOwnerChangeResetsToPendingAndDiscardsStaleFetch() async {
    final class OwnerState: @unchecked Sendable {
      var ownerID = "owner-a"
      var releaseSlowFetch: CheckedContinuation<Void, Never>?
    }
    let state = OwnerState()
    let slowStarted = expectation(description: "slow fetch started")

    let manager = AccountCutoverControlManager(
      fetchControl: {
        let owner = state.ownerID
        if owner == "owner-a" {
          slowStarted.fulfill()
          await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            state.releaseSlowFetch = continuation
          }
          var control = AccountCutoverControl.legacyDefault
          control.accountGeneration = 11
          control.clientAction = .migrationMaintenance
          control.productTrafficAllowed = false
          return control
        }
        var control = AccountCutoverControl.legacyDefault
        control.accountGeneration = 22
        return control
      },
      currentOwnerID: { state.ownerID }
    )

    let staleTask = Task { await manager.bindCurrentOwnerAndRefresh() }
    await fulfillment(of: [slowStarted], timeout: 2)

    state.ownerID = "owner-b"
    await manager.bindCurrentOwnerAndRefresh()
    state.releaseSlowFetch?.resume()
    state.releaseSlowFetch = nil
    _ = await staleTask.value

    XCTAssertEqual(manager.bootstrapPhase, .ready)
    XCTAssertEqual(manager.control.accountGeneration, 22)
    XCTAssertTrue(manager.isProductShellAdmitted)
  }

  func testFirstFetchFailureStaysPendingBlocked() async {
    let manager = AccountCutoverControlManager(
      fetchControl: { throw APIError.invalidResponse },
      currentOwnerID: { "owner-a" }
    )
    await manager.bindCurrentOwnerAndRefresh()
    XCTAssertEqual(manager.bootstrapPhase, .pending)
    XCTAssertTrue(manager.blocksProductTraffic)
    XCTAssertFalse(manager.allowsOfflineQueueUpload)
  }

  func testOfflineUploadAdmissionRequiresReadyAllowingControl() {
    let manager = AccountCutoverControlManager(
      fetchControl: { AccountCutoverControl.legacyDefault },
      currentOwnerID: { "owner-a" }
    )
    manager.resetForTesting()
    XCTAssertFalse(AccountCutoverOfflineUploadAdmission.allowsUpload(manager: manager))

    var blocked = AccountCutoverControl.legacyDefault
    blocked.clientAction = .migrationMaintenance
    blocked.productTrafficAllowed = false
    manager.apply(blocked)
    XCTAssertFalse(AccountCutoverOfflineUploadAdmission.allowsUpload(manager: manager))

    manager.apply(.legacyDefault)
    XCTAssertTrue(AccountCutoverOfflineUploadAdmission.allowsUpload(manager: manager))
  }
}
