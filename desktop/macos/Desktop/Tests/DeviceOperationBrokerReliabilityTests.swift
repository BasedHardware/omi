import Combine
import CoreBluetooth
import XCTest

@testable import Omi_Computer

@MainActor
final class DeviceOperationBrokerTests: XCTestCase {
  func testLateHandleCannotCompleteReplacementOperation() async throws {
    let clock = ManualDeviceOperationClock()
    let broker = DeviceOperationBroker<String, String>(clock: clock)
    var handles: [DeviceOperationHandle<String>] = []

    let first = Task {
      try await broker.perform(key: "battery", timeout: .seconds(1)) { handle in
        handles.append(handle)
      }
    }
    await waitForBluetoothReliabilityCondition {
      let sleeperCount = await clock.sleeperCount
      return handles.count == 1 && sleeperCount == 1
    }
    let staleHandle = try XCTUnwrap(handles.first)

    await clock.advanceAll()
    await assertBrokerError(.timedOut, from: first)

    let second = Task {
      try await broker.perform(key: "battery") { handle in
        handles.append(handle)
      }
    }
    await waitForBluetoothReliabilityCondition { handles.count == 2 }
    let replacementHandle = handles[1]

    let staleAccepted = await broker.succeed(handle: staleHandle, value: "stale")
    XCTAssertFalse(staleAccepted)
    let pendingAfterStaleCallback = await broker.pendingCount
    XCTAssertEqual(pendingAfterStaleCallback, 1)

    let replacementAccepted = await broker.succeed(
      handle: replacementHandle,
      value: "replacement"
    )
    XCTAssertTrue(replacementAccepted)
    let replacementValue = try await second.value
    XCTAssertEqual(replacementValue, "replacement")
  }

  func testDuplicateKeyIsRejectedWhileFirstOperationIsPending() async throws {
    let broker = DeviceOperationBroker<String, Void>()
    var firstHandle: DeviceOperationHandle<String>?
    let first = Task {
      try await broker.perform(key: "status") { handle in
        firstHandle = handle
      }
    }
    await waitForBluetoothReliabilityCondition { firstHandle != nil }

    do {
      _ = try await broker.perform(key: "status") { _ in }
      XCTFail("Expected duplicate operation to be rejected")
    } catch let error as DeviceOperationBrokerError {
      XCTAssertEqual(error, .operationAlreadyPending)
    }

    _ = await broker.succeed(handle: try XCTUnwrap(firstHandle), value: ())
    _ = try await first.value
  }

  func testAlreadyCancelledTaskNeverStartsPhysicalSideEffect() async {
    let broker = DeviceOperationBroker<String, Void>()
    var startCount = 0

    let task = Task {
      try await broker.perform(key: "cancelled") { _ in
        startCount += 1
      }
    }
    task.cancel()

    await assertBrokerError(.cancelled, from: task)
    XCTAssertEqual(startCount, 0)
    let pendingCount = await broker.pendingCount
    XCTAssertEqual(pendingCount, 0)
  }

  func testClaimedCallbackSuccessWinsLateTimeoutAndCallerCancellation() async throws {
    let clock = ManualDeviceOperationClock()
    let broker = DeviceOperationBroker<String, String>(clock: clock)
    var handle: DeviceOperationHandle<String>?
    var startContinuation: CheckedContinuation<Void, Never>?
    var terminations: [DeviceOperationTermination] = []
    let operation = Task {
      try await broker.perform(
        key: "command",
        timeout: .seconds(1),
        onTerminal: { _, termination in
          terminations.append(termination)
        }
      ) { operationHandle in
        handle = operationHandle
        await withCheckedContinuation { continuation in
          startContinuation = continuation
        }
      }
    }
    await waitForBluetoothReliabilityCondition {
      let sleeperCount = await clock.sleeperCount
      return handle != nil && startContinuation != nil && sleeperCount == 1
    }

    var callbackReturned = false
    let operationHandle = try XCTUnwrap(handle)
    let callback = Task {
      let accepted = await broker.succeed(
        handle: operationHandle,
        value: "response"
      )
      callbackReturned = true
      return accepted
    }
    for _ in 0..<10 { await Task.yield() }
    XCTAssertFalse(callbackReturned)
    let pendingWhileDraining = await broker.pendingCount
    XCTAssertEqual(pendingWhileDraining, 1)
    do {
      _ = try await broker.perform(key: "command") { _ in }
      XCTFail("A completing key must remain unavailable until start drains")
    } catch let error as DeviceOperationBrokerError {
      XCTAssertEqual(error, .operationAlreadyPending)
    }

    // succeed() has already claimed terminal ownership, but is waiting for
    // the physical start to drain. The manual clock intentionally ignores
    // task cancellation, so both terminal sources really reach finish().
    operation.cancel()
    await clock.advanceAll()
    for _ in 0..<10 { await Task.yield() }
    XCTAssertFalse(callbackReturned)
    XCTAssertTrue(terminations.isEmpty)
    let pendingAfterLateTerminals = await broker.pendingCount
    XCTAssertEqual(pendingAfterLateTerminals, 1)

    startContinuation?.resume()
    startContinuation = nil
    let callbackAccepted = await callback.value
    let operationValue = try await operation.value
    XCTAssertTrue(callbackAccepted)
    XCTAssertEqual(operationValue, "response")
    XCTAssertEqual(terminations, [.succeeded])
    let pendingAfterCompletion = await broker.pendingCount
    XCTAssertEqual(pendingAfterCompletion, 0)
  }

  func testCallbackFailureWaitsForPhysicalStartToDrain() async throws {
    let broker = DeviceOperationBroker<String, Void>()
    var handle: DeviceOperationHandle<String>?
    var startContinuation: CheckedContinuation<Void, Never>?
    let operation = Task {
      try await broker.perform(key: "command") { operationHandle in
        handle = operationHandle
        await withCheckedContinuation { continuation in
          startContinuation = continuation
        }
      }
    }
    await waitForBluetoothReliabilityCondition { handle != nil && startContinuation != nil }

    var callbackReturned = false
    let operationHandle = try XCTUnwrap(handle)
    let callback = Task {
      let accepted = await broker.fail(
        handle: operationHandle,
        reason: "response failed"
      )
      callbackReturned = true
      return accepted
    }
    for _ in 0..<10 { await Task.yield() }
    XCTAssertFalse(callbackReturned)

    startContinuation?.resume()
    startContinuation = nil
    let callbackAccepted = await callback.value
    XCTAssertTrue(callbackAccepted)
    await assertBrokerError(.failed("response failed"), from: operation)
  }

  func testCancelAllClaimsAndCompletesEveryPendingKey() async {
    let broker = DeviceOperationBroker<String, Void>()
    var startedKeys: Set<String> = []
    var terminations: [String: DeviceOperationTermination] = [:]

    let first = Task {
      try await broker.perform(
        key: "first",
        onTerminal: { _, termination in
          terminations["first"] = termination
        }
      ) { _ in
        startedKeys.insert("first")
      }
    }
    let second = Task {
      try await broker.perform(
        key: "second",
        onTerminal: { _, termination in
          terminations["second"] = termination
        }
      ) { _ in
        startedKeys.insert("second")
      }
    }
    await waitForBluetoothReliabilityCondition { startedKeys == ["first", "second"] }

    await broker.cancelAll(reason: .disconnected)

    await assertBrokerError(.disconnected, from: first)
    await assertBrokerError(.disconnected, from: second)
    XCTAssertEqual(
      terminations,
      [
        "first": .disconnected,
        "second": .disconnected,
      ])
    let pendingCount = await broker.pendingCount
    XCTAssertEqual(pendingCount, 0)
  }

  private func assertBrokerError<Value>(
    _ expected: DeviceOperationBrokerError,
    from task: Task<Value, Error>,
    file: StaticString = #filePath,
    line: UInt = #line
  ) async {
    do {
      _ = try await task.value
      XCTFail("Expected broker error", file: file, line: line)
    } catch let error as DeviceOperationBrokerError {
      XCTAssertEqual(error, expected, file: file, line: line)
    } catch {
      XCTFail("Unexpected error: \(error)", file: file, line: line)
    }
  }
}
