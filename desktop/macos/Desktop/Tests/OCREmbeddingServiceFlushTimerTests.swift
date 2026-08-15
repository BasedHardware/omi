import XCTest

@testable import Omi_Computer

final class OCREmbeddingServiceFlushTimerTests: XCTestCase {
  func testScheduledFlushReachesEmbedderWithoutCancellingItself() async throws {
    let sleeper = ManualFlushSleeper()
    let embedder = ControlledBatchEmbedder()
    let writes = TimerFlushWriteSpy()
    let service = makeService(sleeper: sleeper, embedder: embedder, writes: writes)
    guard let ownerSnapshot = RewindCaptureOwnerSnapshot.capture() else {
      XCTFail("expected an active Rewind owner generation")
      return
    }

    await service.embedScreenshot(
      id: 101,
      ocrText: String(repeating: "timer flush screenshot text ", count: 2),
      appName: "Notes",
      windowTitle: "Timer regression",
      ownerSnapshot: ownerSnapshot)

    await sleeper.waitForInvocation(1)
    await sleeper.releaseInvocation(1)
    await embedder.waitForInvocation(1)

    let cancelledAtEntry = await embedder.wasCancelledAtEntry(invocation: 1)
    XCTAssertEqual(cancelledAtEntry, false, "the scheduled flush must not cancel its own embedding task")
    guard cancelledAtEntry == false else {
      await service.reset()
      return
    }

    await writes.waitForCount(1)
    let writtenIDs = await writes.ids
    XCTAssertEqual(writtenIDs, [101])
    let pending = await service.pendingCount
    XCTAssertEqual(pending, 0)
    await service.reset()
  }

  func testExplicitFlushCancelsInFlightTimerAndFailedCancellationReschedules() async throws {
    let sleeper = ManualFlushSleeper()
    let embedder = ControlledBatchEmbedder(blockFirstInvocation: true)
    let writes = TimerFlushWriteSpy()
    let service = makeService(sleeper: sleeper, embedder: embedder, writes: writes)
    guard let ownerSnapshot = RewindCaptureOwnerSnapshot.capture() else {
      XCTFail("expected an active Rewind owner generation")
      return
    }

    await service.embedScreenshot(
      id: 202,
      ocrText: String(repeating: "externally cancelled timer text ", count: 2),
      appName: "Safari",
      windowTitle: nil,
      ownerSnapshot: ownerSnapshot)

    await sleeper.waitForInvocation(1)
    await sleeper.releaseInvocation(1)
    await embedder.waitForInvocation(1)

    // The scheduled flush is suspended in its embedder. An explicit flush must
    // cancel that timer-owned task without cancelling this caller.
    await service.flushPendingEmbeddings()
    await embedder.releaseFirstInvocation()

    // Cancellation makes the first embed fail and re-queue. The stale timer
    // must not clear the replacement that owns that re-queued item.
    await sleeper.waitForInvocation(2)
    await sleeper.releaseInvocation(2)
    await embedder.waitForInvocation(2)
    await writes.waitForCount(1)

    let cancellationAfterRelease = await embedder.wasCancelledAfterRelease(invocation: 1)
    XCTAssertEqual(cancellationAfterRelease, true)
    let secondCancelledAtEntry = await embedder.wasCancelledAtEntry(invocation: 2)
    XCTAssertEqual(secondCancelledAtEntry, false)
    let writtenIDs = await writes.ids
    XCTAssertEqual(writtenIDs, [202])
    let pending = await service.pendingCount
    XCTAssertEqual(pending, 0)
    await service.reset()
  }

  func testPendingTimerDoesNotRetainService() async throws {
    let sleeper = ManualFlushSleeper()
    let embedder = ControlledBatchEmbedder()
    let writes = TimerFlushWriteSpy()
    guard let ownerSnapshot = RewindCaptureOwnerSnapshot.capture() else {
      XCTFail("expected an active Rewind owner generation")
      return
    }

    var service: OCREmbeddingService? = makeService(
      sleeper: sleeper, embedder: embedder, writes: writes)
    weak var weakService: OCREmbeddingService?
    weakService = service
    await service?.embedScreenshot(
      id: 303,
      ocrText: String(repeating: "service lifetime timer text ", count: 2),
      appName: "Terminal",
      windowTitle: nil,
      ownerSnapshot: ownerSnapshot)
    await sleeper.waitForInvocation(1)

    service = nil

    XCTAssertNil(weakService, "the stored timer task must not form a retain cycle with the service")
    await sleeper.releaseInvocation(1)
  }

  private func makeService(
    sleeper: ManualFlushSleeper,
    embedder: ControlledBatchEmbedder,
    writes: TimerFlushWriteSpy
  ) -> OCREmbeddingService {
    OCREmbeddingService(
      batchEmbedderForTesting: { texts, _ in
        try await embedder.embed(texts: texts)
      },
      embeddingWriterForTesting: { screenshotID, _ in
        await writes.record(screenshotID)
      },
      flushSleeperForTesting: { _ in
        try await sleeper.sleep()
      })
  }
}

private actor ManualFlushSleeper {
  private var invocationCount = 0
  private var invocationWaiters: [(target: Int, continuation: CheckedContinuation<Void, Never>)] = []
  private var sleepContinuations: [Int: CheckedContinuation<Void, Never>] = [:]

  func sleep() async throws {
    invocationCount += 1
    let invocation = invocationCount
    resumeSatisfiedInvocationWaiters()
    await withCheckedContinuation { continuation in
      sleepContinuations[invocation] = continuation
    }
    try Task.checkCancellation()
  }

  func waitForInvocation(_ target: Int) async {
    if invocationCount >= target { return }
    await withCheckedContinuation { continuation in
      invocationWaiters.append((target, continuation))
    }
  }

  func releaseInvocation(_ invocation: Int) {
    sleepContinuations.removeValue(forKey: invocation)?.resume()
  }

  private func resumeSatisfiedInvocationWaiters() {
    let satisfied = invocationWaiters.filter { $0.target <= invocationCount }
    invocationWaiters.removeAll { $0.target <= invocationCount }
    for waiter in satisfied {
      waiter.continuation.resume()
    }
  }
}

private actor ControlledBatchEmbedder {
  private let dimension = EmbeddingService.embeddingDimension
  private let blockFirstInvocation: Bool
  private let firstInvocationRelease = TimerFlushAsyncGate()
  private var cancelledAtEntry: [Bool] = []
  private var cancelledAfterRelease: [Bool] = []
  private var invocationWaiters: [(target: Int, continuation: CheckedContinuation<Void, Never>)] = []

  init(blockFirstInvocation: Bool = false) {
    self.blockFirstInvocation = blockFirstInvocation
  }

  func embed(texts: [String]) async throws -> [[Float]] {
    let invocation = cancelledAtEntry.count + 1
    cancelledAtEntry.append(Task.isCancelled)
    resumeSatisfiedInvocationWaiters()

    if blockFirstInvocation, invocation == 1 {
      await firstInvocationRelease.wait()
    }

    cancelledAfterRelease.append(Task.isCancelled)
    try Task.checkCancellation()
    return texts.map { _ in [Float](repeating: 0, count: dimension) }
  }

  func waitForInvocation(_ target: Int) async {
    if cancelledAtEntry.count >= target { return }
    await withCheckedContinuation { continuation in
      invocationWaiters.append((target, continuation))
    }
  }

  func releaseFirstInvocation() async {
    await firstInvocationRelease.open()
  }

  func wasCancelledAtEntry(invocation: Int) -> Bool {
    cancelledAtEntry[invocation - 1]
  }

  func wasCancelledAfterRelease(invocation: Int) -> Bool {
    cancelledAfterRelease[invocation - 1]
  }

  private func resumeSatisfiedInvocationWaiters() {
    let satisfied = invocationWaiters.filter { $0.target <= cancelledAtEntry.count }
    invocationWaiters.removeAll { $0.target <= cancelledAtEntry.count }
    for waiter in satisfied {
      waiter.continuation.resume()
    }
  }
}

private actor TimerFlushWriteSpy {
  private(set) var ids: [Int64] = []
  private var countWaiters: [(target: Int, continuation: CheckedContinuation<Void, Never>)] = []

  func record(_ id: Int64) {
    ids.append(id)
    let satisfied = countWaiters.filter { $0.target <= ids.count }
    countWaiters.removeAll { $0.target <= ids.count }
    for waiter in satisfied {
      waiter.continuation.resume()
    }
  }

  func waitForCount(_ target: Int) async {
    if ids.count >= target { return }
    await withCheckedContinuation { continuation in
      countWaiters.append((target, continuation))
    }
  }
}

private actor TimerFlushAsyncGate {
  private var isOpen = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func open() {
    guard !isOpen else { return }
    isOpen = true
    let pending = waiters
    waiters.removeAll()
    for waiter in pending { waiter.resume() }
  }

  func wait() async {
    if isOpen { return }
    await withCheckedContinuation { waiters.append($0) }
  }
}
