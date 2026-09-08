import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeVoiceContextSingleFlightTests: XCTestCase {
  @MainActor
  private final class Gate {
    var startCount = 0
    var continuation: CheckedContinuation<Bool, Never>?
    var startedWaiters: [CheckedContinuation<Void, Never>] = []

    func run() async -> Bool {
      return await withCheckedContinuation { continuation in
        self.continuation = continuation
        startCount += 1
        for waiter in startedWaiters {
          waiter.resume()
        }
        startedWaiters.removeAll()
      }
    }

    func waitUntilStarted() async {
      guard startCount == 0 else { return }
      await withCheckedContinuation { continuation in
        startedWaiters.append(continuation)
      }
    }

    func finish(_ result: Bool) {
      continuation?.resume(returning: result)
      continuation = nil
    }
  }

  @MainActor
  private final class Signal {
    private var didFire = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func fire() {
      didFire = true
      for waiter in waiters {
        waiter.resume()
      }
      waiters.removeAll()
    }

    func wait() async {
      guard !didFire else { return }
      await withCheckedContinuation { continuation in
        waiters.append(continuation)
      }
    }
  }

  private func waitUntilStarted(_ gate: Gate) async {
    await gate.waitUntilStarted()
  }

  func testCancelledTurnWaiterDoesNotCancelSharedReadiness() async {
    let singleFlight = RealtimeVoiceContextSingleFlight()
    let gate = Gate()
    let turnWaiterJoined = Signal()

    let speculative = singleFlight.joinOrStart { await gate.run() }
    let turnWaiter = Task {
      let sharedReadiness = singleFlight.joinOrStart { await gate.run() }
      turnWaiterJoined.fire()
      return await sharedReadiness.value
    }
    await waitUntilStarted(gate)
    await turnWaiterJoined.wait()

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
