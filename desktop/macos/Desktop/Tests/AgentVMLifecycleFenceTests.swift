import XCTest

@testable import Omi_Computer

final class AgentVMLifecycleFenceTests: XCTestCase {
  func testGzipControllerCancellationBeforeLaunchPreventsProcessStart() {
    let controller = GzipProcessController()
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/true")

    controller.cancel()

    XCTAssertThrowsError(try controller.run(process)) { error in
      XCTAssertTrue(error is CancellationError)
    }
    XCTAssertFalse(process.isRunning)
  }

  func testLateLifecycleWorkIsRejectedAfterOwnerTransition() {
    XCTAssertTrue(
      AgentVMService.lifecycleWorkIsCurrent(
        ownerID: "owner-a",
        generation: 4,
        currentOwnerID: "owner-a",
        currentGeneration: 4,
        isCancelled: false))
    XCTAssertFalse(
      AgentVMService.lifecycleWorkIsCurrent(
        ownerID: "owner-a",
        generation: 4,
        currentOwnerID: "owner-b",
        currentGeneration: 5,
        isCancelled: false),
      "an owner-A result must not start sync or publish credentials for owner B")
  }

  func testCancelledLifecycleWorkRemainsRejectedForSameOwner() {
    XCTAssertFalse(
      AgentVMService.lifecycleWorkIsCurrent(
        ownerID: "owner-a",
        generation: 9,
        currentOwnerID: "owner-a",
        currentGeneration: 9,
        isCancelled: true))
  }
}
