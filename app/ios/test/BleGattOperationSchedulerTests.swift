import Foundation

private final class ScheduledTimeout {
  let action: () -> Void
  var isCancelled = false

  init(action: @escaping () -> Void) {
    self.action = action
  }
}

private final class ManualTimeoutScheduler {
  private(set) var timeouts: [ScheduledTimeout] = []

  func schedule(_: TimeInterval, action: @escaping () -> Void) -> BleGattTimeoutCancellation {
    let timeout = ScheduledTimeout(action: action)
    timeouts.append(timeout)
    return BleGattTimeoutCancellation {
      timeout.isCancelled = true
    }
  }

  func fireNextActive() {
    guard let timeout = timeouts.first(where: { !$0.isCancelled }) else {
      fail("expected an active timeout")
    }
    timeout.action()
  }
}

private func expect(
  _ condition: @autoclosure () -> Bool,
  _ message: String,
  file: StaticString = #filePath,
  line: UInt = #line
) {
  if !condition() {
    fail(message, file: file, line: line)
  }
}

private func fail(
  _ message: String,
  file: StaticString = #filePath,
  line: UInt = #line
) -> Never {
  fatalError("\(file):\(line): \(message)")
}

private func scheduler(
  clock: ManualTimeoutScheduler,
  timedOut: @escaping (BleGattOperationToken) -> Void = { _ in }
) -> BleGattOperationScheduler {
  BleGattOperationScheduler(
    timeout: 10,
    scheduleTimeout: clock.schedule,
    onFatalTimeout: timedOut
  )
}

private let targetA = BleGattTarget(
  serviceUuid: "service", characteristicUuid: "characteristic", instanceId: 1)
private let targetB = BleGattTarget(
  serviceUuid: "service", characteristicUuid: "characteristic", instanceId: 2)

private func testSerializesAndKeepsCompletionsDistinct() {
  let clock = ManualTimeoutScheduler()
  let queue = scheduler(clock: clock)
  queue.beginSession()

  var starts: [UInt64] = []
  var completions: [String] = []

  let first = queue.enqueue(
    kind: .readValue,
    target: targetA,
    start: { starts.append($0.id) },
    completion: { result in
      if case .success(let data) = result {
        completions.append("first:\(data?.first ?? 0)")
      }
    }
  )
  let second = queue.enqueue(
    kind: .readValue,
    target: targetA,
    start: { starts.append($0.id) },
    completion: { result in
      if case .success(let data) = result {
        completions.append("second:\(data?.first ?? 0)")
      }
    }
  )

  expect(first != nil && second != nil, "connected session must accept operations")
  expect(starts == [first!.id], "only one CoreBluetooth operation may be in flight")
  expect(queue.pendingCount == 1, "second same-characteristic request must remain queued")

  expect(
    queue.completeExpected(
      sessionId: first!.sessionId,
      kind: .readValue,
      target: targetA,
      result: .success(Data([11]))
    ),
    "first callback should resolve its exact request"
  )
  expect(completions == ["first:11"], "first callback must not overwrite the second completion")
  expect(
    starts == [first!.id, second!.id], "second request should begin only after the first completes")

  expect(
    queue.completeExpected(
      sessionId: second!.sessionId,
      kind: .readValue,
      target: targetA,
      result: .success(Data([22]))
    ),
    "second callback should resolve its own request"
  )
  expect(completions == ["first:11", "second:22"], "same-target completions must remain distinct")
}

private func testRejectsWrongKindTargetAndSession() {
  let clock = ManualTimeoutScheduler()
  let queue = scheduler(clock: clock)
  queue.beginSession()

  var completionCount = 0
  let token = queue.enqueue(
    kind: .readValue,
    target: targetA,
    start: { _ in },
    completion: { _ in completionCount += 1 }
  )!

  expect(
    !queue.completeExpected(
      sessionId: token.sessionId,
      kind: .setNotifications(true),
      target: targetA,
      result: .success(nil)
    ),
    "notification-state callback must not satisfy a read"
  )
  expect(
    !queue.completeExpected(
      sessionId: token.sessionId,
      kind: .readValue,
      target: targetB,
      result: .success(Data([1]))
    ),
    "a different characteristic instance must not satisfy a read"
  )
  expect(
    !queue.completeExpected(
      sessionId: token.sessionId &+ 1,
      kind: .readValue,
      target: targetA,
      result: .success(Data([1]))
    ),
    "a stale connection session must not satisfy a read"
  )
  expect(completionCount == 0, "unrelated callbacks must leave the active operation untouched")

  expect(
    queue.completeExpected(
      sessionId: token.sessionId,
      kind: .readValue,
      target: targetA,
      result: .success(Data([7]))
    ),
    "exact callback should still complete after unrelated callbacks"
  )
  expect(completionCount == 1, "operation completion must run exactly once")
}

private func testTimeoutFailsWholeSessionWithoutStartingQueuedWork() {
  let clock = ManualTimeoutScheduler()
  var timedOutToken: BleGattOperationToken?
  let queue = scheduler(clock: clock) { timedOutToken = $0 }
  queue.beginSession()

  var starts: [String] = []
  var failures: [BleGattOperationSchedulerError] = []
  let first = queue.enqueue(
    kind: .writeWithResponse,
    target: targetA,
    start: { _ in starts.append("first") },
    completion: {
      if case .failure(let error as BleGattOperationSchedulerError) = $0 {
        failures.append(error)
      }
    }
  )!
  _ = queue.enqueue(
    kind: .readValue,
    target: targetB,
    start: { _ in starts.append("second") },
    completion: {
      if case .failure(let error as BleGattOperationSchedulerError) = $0 {
        failures.append(error)
      }
    }
  )

  clock.fireNextActive()

  expect(starts == ["first"], "queued work must not start on a timed-out CoreBluetooth session")
  expect(
    failures == [.timedOut, .timedOut],
    "timeout must fail active and queued callers deterministically")
  expect(timedOutToken == first, "timeout hook must identify the exact failed operation")
  expect(!queue.isSessionActive, "timeout must invalidate the connection session")
  expect(
    queue.activeToken == nil && queue.pendingCount == 0, "timeout must leave no orphaned operations"
  )

  var disconnectedFailure: BleGattOperationSchedulerError?
  let rejected = queue.enqueue(
    kind: .readValue,
    target: targetA,
    start: { _ in fail("inactive session must not start new work") },
    completion: {
      if case .failure(let error as BleGattOperationSchedulerError) = $0 {
        disconnectedFailure = error
      }
    }
  )
  expect(rejected == nil, "timed-out session must reject new work until reconnect")
  expect(disconnectedFailure == .disconnected, "rejected caller must receive an explicit failure")
}

private func testDiagnosticsRssiTimeoutDoesNotTearDownTheSession() {
  let clock = ManualTimeoutScheduler()
  var fatalTimeouts = 0
  let queue = scheduler(clock: clock) { _ in fatalTimeouts += 1 }
  queue.beginSession()

  var starts: [BleGattOperationKind] = []
  var rssiTimedOut = false
  let rssi = queue.enqueue(
    kind: .readRssi,
    target: .rssi,
    fatalOnTimeout: false,
    start: { starts.append($0.kind) },
    completion: { result in
      if case .failure(BleGattOperationSchedulerError.timedOut) = result {
        rssiTimedOut = true
      }
    }
  )!
  let read = queue.enqueue(
    kind: .readValue,
    target: targetA,
    start: { starts.append($0.kind) },
    completion: { _ in }
  )!

  clock.fireNextActive()

  expect(rssiTimedOut, "missing diagnostics callback must fail that RSSI sample")
  expect(fatalTimeouts == 0, "diagnostics timeout must not request a reconnect")
  expect(queue.isSessionActive, "diagnostics timeout must preserve the healthy GATT session")
  expect(starts == [.readRssi, .readValue], "queued production work must continue after RSSI timeout")
  expect(queue.activeToken == read, "the next serialized operation should become active")
  expect(!queue.complete(token: rssi, result: .success(nil)), "late RSSI callback must remain fenced")
}

private func testDisconnectCancelsOnceAndFencesLateCallbacks() {
  let clock = ManualTimeoutScheduler()
  let queue = scheduler(clock: clock)
  queue.beginSession()

  var completions: [BleGattOperationSchedulerError] = []
  let oldToken = queue.enqueue(
    kind: .readValue,
    target: targetA,
    start: { _ in },
    completion: {
      if case .failure(let error as BleGattOperationSchedulerError) = $0 {
        completions.append(error)
      }
    }
  )!
  _ = queue.enqueue(
    kind: .setNotifications(true),
    target: targetB,
    start: { _ in },
    completion: {
      if case .failure(let error as BleGattOperationSchedulerError) = $0 {
        completions.append(error)
      }
    }
  )

  queue.endSession()
  expect(
    completions == [.disconnected, .disconnected], "disconnect must fail every caller exactly once")
  queue.endSession()
  expect(completions.count == 2, "duplicate disconnect callbacks must not duplicate completions")

  queue.beginSession()
  var newCompletionCount = 0
  let newToken = queue.enqueue(
    kind: .readValue,
    target: targetA,
    start: { _ in },
    completion: { _ in newCompletionCount += 1 }
  )!
  expect(newToken.sessionId != oldToken.sessionId, "reconnect must create a new operation session")
  expect(
    !queue.completeExpected(
      sessionId: oldToken.sessionId,
      kind: oldToken.kind,
      target: oldToken.target,
      result: .success(Data([1]))
    ),
    "late callback from the disconnected session must be ignored"
  )
  expect(newCompletionCount == 0, "late callback must not complete the new request")
  expect(
    queue.completeExpected(
      sessionId: newToken.sessionId,
      kind: newToken.kind,
      target: newToken.target,
      result: .success(Data([2]))
    ),
    "new session callback should complete normally"
  )
  expect(newCompletionCount == 1, "new request must complete once")
}

private func testSessionTransitionRejectsReentrantWork() {
  let clock = ManualTimeoutScheduler()
  let queue = scheduler(clock: clock)
  queue.beginSession()

  var reentrantStartCount = 0
  var reentrantFailure: BleGattOperationSchedulerError?
  _ = queue.enqueue(
    kind: .readValue,
    target: targetA,
    start: { _ in },
    completion: { _ in
      _ = queue.enqueue(
        kind: .writeWithResponse,
        target: targetB,
        start: { _ in reentrantStartCount += 1 },
        completion: {
          if case .failure(let error as BleGattOperationSchedulerError) = $0 {
            reentrantFailure = error
          }
        }
      )
    }
  )

  queue.endSession()
  expect(reentrantStartCount == 0, "disconnect completion must not start work in the dead session")
  expect(
    reentrantFailure == .disconnected, "reentrant work must receive explicit disconnected failure")
  expect(
    queue.activeToken == nil && queue.pendingCount == 0,
    "session transition must leave no orphaned work")
}

private func testNotificationStateIsSerializedWithDataCommands() {
  let clock = ManualTimeoutScheduler()
  let queue = scheduler(clock: clock)
  queue.beginSession()

  var starts: [BleGattOperationKind] = []
  let subscribe = queue.enqueue(
    kind: .setNotifications(true),
    target: targetA,
    start: { starts.append($0.kind) },
    completion: { _ in }
  )!
  let write = queue.enqueue(
    kind: .writeWithResponse,
    target: targetB,
    start: { starts.append($0.kind) },
    completion: { _ in }
  )!

  expect(starts == [.setNotifications(true)], "CCCD change must serialize with GATT data commands")
  expect(
    queue.completeExpected(
      sessionId: subscribe.sessionId,
      kind: subscribe.kind,
      target: subscribe.target,
      result: .success(nil)
    ),
    "CCCD callback should resolve exact subscription operation"
  )
  expect(
    starts == [.setNotifications(true), .writeWithResponse],
    "write should start after subscription callback")
  expect(
    queue.completeExpected(
      sessionId: write.sessionId,
      kind: write.kind,
      target: write.target,
      result: .success(nil)
    ),
    "write callback should resolve after serialized subscription"
  )
}

private func testLateEnableCallbackCannotCompleteActiveDisable() {
  let clock = ManualTimeoutScheduler()
  let queue = scheduler(clock: clock)
  queue.beginSession()

  let enable = queue.enqueue(
    kind: .setNotifications(true),
    target: targetA,
    start: { _ in },
    completion: { _ in }
  )!
  let disable = queue.enqueue(
    kind: .setNotifications(false),
    target: targetA,
    start: { _ in },
    completion: { _ in }
  )!

  func applyCallback(actualIsNotifying: Bool) -> Bool {
    guard let active = queue.activeToken,
      case .setNotifications(let requestedEnabled) = active.kind,
      BleGattNotificationStateAdmission.evaluate(
        requestedEnabled: requestedEnabled,
        actualIsNotifying: actualIsNotifying
      ) == .complete
    else {
      return false
    }
    return queue.completeExpected(
      sessionId: active.sessionId,
      kind: active.kind,
      target: active.target,
      result: .success(nil)
    )
  }

  expect(applyCallback(actualIsNotifying: true), "enable callback should complete active enable")
  expect(queue.activeToken == disable, "disable should become active after enable")
  expect(
    !applyCallback(actualIsNotifying: true),
    "late enable callback must not complete an active disable"
  )
  expect(queue.activeToken == disable, "mismatched callback must leave disable in flight")
  expect(
    applyCallback(actualIsNotifying: false), "matching disable callback should complete disable")
  expect(queue.activeToken == nil, "matching disable callback should drain the queue")
  expect(enable.kind == .setNotifications(true), "test must exercise enable before disable")
}

private func testNotificationFailureFencesDependentCommands() {
  struct NotificationFailure: Error {}

  let clock = ManualTimeoutScheduler()
  let queue = scheduler(clock: clock)
  queue.beginSession()

  var starts: [BleGattOperationKind] = []
  var failures = 0
  let subscribe = queue.enqueue(
    kind: .setNotifications(true),
    target: targetA,
    start: { starts.append($0.kind) },
    completion: {
      if case .failure = $0 { failures += 1 }
    }
  )!
  _ = queue.enqueue(
    kind: .writeWithResponse,
    target: targetB,
    start: { starts.append($0.kind) },
    completion: {
      if case .failure = $0 { failures += 1 }
    }
  )

  expect(
    queue.failExpectedAndInvalidate(
      sessionId: subscribe.sessionId,
      kind: subscribe.kind,
      target: subscribe.target,
      error: NotificationFailure()
    ),
    "exact subscription error should invalidate the operation session"
  )
  expect(
    starts == [.setNotifications(true)], "dependent write must not run after subscription failure")
  expect(failures == 2, "subscription failure must reach active and dependent callers")
  expect(!queue.isSessionActive, "failed subscription must require a clean reconnect")
}

private func testSubscribeThenSameTargetReadRechecksNotificationState() {
  struct ReadWhileNotifying: Error {}

  let clock = ManualTimeoutScheduler()
  let queue = scheduler(clock: clock)
  queue.beginSession()

  var isNotifying = false
  var coreBluetoothReadCount = 0
  var readFailureCount = 0
  let subscribe = queue.enqueue(
    kind: .setNotifications(true),
    target: targetA,
    start: { _ in },
    completion: { _ in }
  )!
  _ = queue.enqueue(
    kind: .readValue,
    target: targetA,
    start: { token in
      switch BleGattReadAdmission.evaluate(isNotifying: isNotifying) {
      case .start:
        coreBluetoothReadCount += 1
      case .rejectNotifying:
        queue.complete(token: token, result: .failure(ReadWhileNotifying()))
      }
    },
    completion: {
      if case .failure = $0 { readFailureCount += 1 }
    }
  )

  isNotifying = true
  expect(
    queue.completeExpected(
      sessionId: subscribe.sessionId,
      kind: subscribe.kind,
      target: subscribe.target,
      result: .success(nil)
    ),
    "subscription callback should release the queued read"
  )
  expect(
    coreBluetoothReadCount == 0,
    "queued read must recheck and avoid CoreBluetooth once notifications start")
  expect(readFailureCount == 1, "ambiguous read must fail immediately instead of timing out")
  expect(queue.activeToken == nil, "rejected queued read must not remain stuck in flight")
  expect(
    queue.isSessionActive, "safe read rejection must not tear down an otherwise healthy session")
}

private func testNotificationTransitionCoalescesLatestDesiredState() {
  let state = BleGattNotificationTransitionState(confirmed: false)

  expect(state.request(true) == true, "initial enable should start immediately")
  expect(state.request(false) == nil, "disable should wait behind the active enable")
  expect(state.request(true) == nil, "latest enable should replace the queued disable intent")
  expect(
    state.complete(attempted: true, success: true) == nil,
    "completed enable should not launch the superseded disable")
  expect(state.currentInFlight == nil, "coalesced final state should have no transition in flight")
  expect(state.request(true) == nil, "confirmed final state should not generate a redundant write")
}

private func testNotificationTransitionRunsOppositeLatestState() {
  let state = BleGattNotificationTransitionState(confirmed: false)

  expect(state.request(true) == true, "initial enable should start immediately")
  expect(state.request(false) == nil, "disable should wait for the active enable callback")
  expect(
    state.complete(attempted: true, success: true) == false,
    "latest opposite state should start after the active transition")
  expect(state.currentInFlight == false, "follow-up disable should be marked in flight")
  expect(
    state.complete(attempted: false, success: true) == nil,
    "confirmed latest state should finish without another transition")
}

private func testFailedNotificationTransitionWaitsForSessionRecovery() {
  let state = BleGattNotificationTransitionState(confirmed: false)

  expect(state.request(true) == true, "initial enable should start immediately")
  expect(
    state.complete(attempted: true, success: false) == nil,
    "failed transition must not retry on the compromised session")
  expect(state.currentInFlight == nil, "failed transition must release its in-flight marker")
}

private func testReconnectBackoffIsBounded() {
  expect(BleReconnectBackoff.delay(forAttempt: 0) == 0.5, "first reconnect should be prompt")
  expect(BleReconnectBackoff.delay(forAttempt: 1) == 1, "repeated failure should back off")
  expect(BleReconnectBackoff.delay(forAttempt: 4) == 8, "backoff should grow exponentially")
  expect(
    BleReconnectBackoff.delay(forAttempt: 6) == 30, "backoff should cap before becoming excessive")
  expect(BleReconnectBackoff.delay(forAttempt: 100) == 30, "backoff cap must hold for long outages")
}

private func testReconnectBackoffResetsOnlyAfterDeviceReady() {
  let lifecycle = BleReconnectLifecycle()

  lifecycle.transportConnected()
  expect(
    lifecycle.phase == .transportConnected,
    "transport connect should enter setup without claiming ready")
  expect(lifecycle.nextReconnectDelay() == 0.5, "first setup failure should use the initial delay")

  lifecycle.transportConnected()
  expect(lifecycle.failureCount == 1, "transport reconnect must preserve the setup failure count")
  expect(
    lifecycle.nextReconnectDelay() == 1, "second setup failure should continue exponential backoff")

  lifecycle.transportConnected()
  expect(lifecycle.failureCount == 2, "another transport reconnect must still preserve backoff")
  expect(lifecycle.nextReconnectDelay() == 2, "repeated setup failures must keep increasing delay")

  lifecycle.transportConnected()
  lifecycle.deviceReady()
  expect(lifecycle.phase == .ready, "successful setup should be the readiness boundary")
  expect(lifecycle.failureCount == 0, "only device-ready should reset accumulated setup failures")
  expect(
    lifecycle.nextReconnectDelay() == 0.5,
    "failure after a ready session should restart initial backoff")
}

@main
private enum BleGattOperationSchedulerTests {
  static func main() {
    testSerializesAndKeepsCompletionsDistinct()
    testRejectsWrongKindTargetAndSession()
    testTimeoutFailsWholeSessionWithoutStartingQueuedWork()
    testDiagnosticsRssiTimeoutDoesNotTearDownTheSession()
    testDisconnectCancelsOnceAndFencesLateCallbacks()
    testSessionTransitionRejectsReentrantWork()
    testNotificationStateIsSerializedWithDataCommands()
    testLateEnableCallbackCannotCompleteActiveDisable()
    testNotificationFailureFencesDependentCommands()
    testSubscribeThenSameTargetReadRechecksNotificationState()
    testNotificationTransitionCoalescesLatestDesiredState()
    testNotificationTransitionRunsOppositeLatestState()
    testFailedNotificationTransitionWaitsForSessionRecovery()
    testReconnectBackoffIsBounded()
    testReconnectBackoffResetsOnlyAfterDeviceReady()
    print("BleGattOperationSchedulerTests: PASS")
  }
}
