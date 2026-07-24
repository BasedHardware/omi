import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeVoiceContextSingleFlightTests: XCTestCase {
  private final class Gate {
    var startCount = 0
    var continuation: CheckedContinuation<Bool, Never>?

    func run() async -> Bool {
      startCount += 1
      return await withCheckedContinuation { continuation in
        self.continuation = continuation
      }
    }

    func finish(_ result: Bool) {
      continuation?.resume(returning: result)
      continuation = nil
    }
  }

  private func waitUntilStarted(_ gate: Gate) async {
    for _ in 0..<100 where gate.startCount == 0 {
      await Task.yield()
    }
  }

  func testCancelledTurnWaiterDoesNotCancelSharedReadiness() async {
    let singleFlight = RealtimeVoiceContextSingleFlight()
    let gate = Gate()

    let speculative = singleFlight.joinOrStart { await gate.run() }
    let turnWaiter = Task { await singleFlight.joinOrStart { await gate.run() }.value }
    await waitUntilStarted(gate)

    XCTAssertEqual(gate.startCount, 1)
    XCTAssertTrue(singleFlight.isRunning)

    turnWaiter.cancel()
    gate.finish(true)

    let speculativeResult = await speculative.value
    let turnWaiterResult = await turnWaiter.value
    XCTAssertTrue(speculativeResult)
    XCTAssertTrue(turnWaiterResult)
    await Task.yield()
    XCTAssertFalse(singleFlight.isRunning)
    XCTAssertEqual(gate.startCount, 1)
  }

  func testForcedRefreshDoesNotReuseAnOlderSpeculativeRead() async {
    let singleFlight = RealtimeVoiceContextSingleFlight()
    let speculativeGate = Gate()
    let forcedGate = Gate()

    let speculative = singleFlight.joinOrStart { await speculativeGate.run() }
    await waitUntilStarted(speculativeGate)
    let forced = singleFlight.restart { await forcedGate.run() }
    await waitUntilStarted(forcedGate)

    XCTAssertEqual(speculativeGate.startCount, 1)
    XCTAssertEqual(forcedGate.startCount, 1)
    XCTAssertTrue(singleFlight.isRunning)

    speculativeGate.finish(false)
    forcedGate.finish(true)

    let speculativeResult = await speculative.value
    let forcedResult = await forced.value
    XCTAssertFalse(speculativeResult)
    XCTAssertTrue(forcedResult)
    XCTAssertFalse(singleFlight.isRunning)
  }

  func testCompletedFailureClearsBeforeAnotherReadJoins() async {
    let singleFlight = RealtimeVoiceContextSingleFlight()
    let failedGate = Gate()
    let retryGate = Gate()

    let failed = singleFlight.joinOrStart { await failedGate.run() }
    await waitUntilStarted(failedGate)
    failedGate.finish(false)
    let failedResult = await failed.value
    XCTAssertFalse(failedResult)
    XCTAssertFalse(singleFlight.isRunning)

    let retry = singleFlight.joinOrStart { await retryGate.run() }
    await waitUntilStarted(retryGate)
    XCTAssertEqual(retryGate.startCount, 1)
    retryGate.finish(true)
    let retryResult = await retry.value
    XCTAssertTrue(retryResult)
  }
}
