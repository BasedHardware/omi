import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeVoiceContextSingleFlightTests: XCTestCase {
  // An actor (Sendable) so it can cross into the nonisolated single-flight
  // closures without tripping Swift's sending/data-race checks; serialized
  // access also closes the startCount/continuation race the class form had.
  private actor Gate {
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
    for _ in 0..<100 {
      if await gate.startCount != 0 { break }
      await Task.yield()
    }
  }

  func testCancelledTurnWaiterDoesNotCancelSharedReadiness() async {
    let singleFlight = RealtimeVoiceContextSingleFlight()
    let gate = Gate()

    let speculative = singleFlight.joinOrStart { await gate.run() }
    let turnWaiter = Task { await singleFlight.joinOrStart { await gate.run() }.value }
    await waitUntilStarted(gate)

    let startedCount = await gate.startCount
    XCTAssertEqual(startedCount, 1)
    XCTAssertTrue(singleFlight.isRunning)

    turnWaiter.cancel()
    await gate.finish(true)

    let speculativeResult = await speculative.value
    let turnWaiterResult = await turnWaiter.value
    XCTAssertTrue(speculativeResult)
    XCTAssertTrue(turnWaiterResult)
    await Task.yield()
    XCTAssertFalse(singleFlight.isRunning)
    let finalCount = await gate.startCount
    XCTAssertEqual(finalCount, 1)
  }

  func testForcedRefreshDoesNotReuseAnOlderSpeculativeRead() async {
    let singleFlight = RealtimeVoiceContextSingleFlight()
    let speculativeGate = Gate()
    let forcedGate = Gate()

    let speculative = singleFlight.joinOrStart { await speculativeGate.run() }
    await waitUntilStarted(speculativeGate)
    let forced = singleFlight.restart { await forcedGate.run() }
    await waitUntilStarted(forcedGate)

    let speculativeStarted = await speculativeGate.startCount
    let forcedStarted = await forcedGate.startCount
    XCTAssertEqual(speculativeStarted, 1)
    XCTAssertEqual(forcedStarted, 1)
    XCTAssertTrue(singleFlight.isRunning)

    await speculativeGate.finish(false)
    await forcedGate.finish(true)

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
    await failedGate.finish(false)
    let failedResult = await failed.value
    XCTAssertFalse(failedResult)
    XCTAssertFalse(singleFlight.isRunning)

    let retry = singleFlight.joinOrStart { await retryGate.run() }
    await waitUntilStarted(retryGate)
    let retryStarted = await retryGate.startCount
    XCTAssertEqual(retryStarted, 1)
    await retryGate.finish(true)
    let retryResult = await retry.value
    XCTAssertTrue(retryResult)
  }
}
