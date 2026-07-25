import Dispatch
import Foundation

enum BleGattOperationKind: Equatable {
  case readValue
  case writeWithResponse
  case writeWithoutResponse
  case setNotifications(Bool)
  case readRssi
}

enum BleGattReadAdmission: Equatable {
  case start
  case rejectNotifying

  static func evaluate(isNotifying: Bool) -> BleGattReadAdmission {
    isNotifying ? .rejectNotifying : .start
  }
}

enum BleGattNotificationStateAdmission: Equatable {
  case complete
  case ignoreMismatchedState

  static func evaluate(
    requestedEnabled: Bool,
    actualIsNotifying: Bool
  ) -> BleGattNotificationStateAdmission {
    requestedEnabled == actualIsNotifying ? .complete : .ignoreMismatchedState
  }
}

struct BleGattTarget: Equatable {
  let serviceUuid: String
  let characteristicUuid: String
  let instanceId: UInt64

  static let rssi = BleGattTarget(serviceUuid: "", characteristicUuid: "rssi", instanceId: 0)
}

struct BleGattOperationToken: Equatable {
  let id: UInt64
  let sessionId: UInt64
  let kind: BleGattOperationKind
  let target: BleGattTarget
}

enum BleGattOperationSchedulerError: Error, Equatable, LocalizedError {
  case disconnected
  case sessionReplaced
  case timedOut

  var errorDescription: String? {
    switch self {
    case .disconnected:
      return "Peripheral disconnected before the BLE operation completed"
    case .sessionReplaced:
      return "BLE connection session was replaced"
    case .timedOut:
      return "BLE operation timed out"
    }
  }
}

struct BleGattTimeoutCancellation {
  let cancel: () -> Void
}

/// Serializes CoreBluetooth operations for one peripheral connection.
///
/// CoreBluetooth callbacks do not carry request IDs. Keeping one request in flight
/// and binding it to a connection session, operation kind, and characteristic
/// instance prevents a late or unrelated callback from completing the wrong caller.
final class BleGattOperationScheduler {
  typealias Completion = (Result<Data?, Error>) -> Void
  typealias TimeoutScheduler = (TimeInterval, @escaping () -> Void) -> BleGattTimeoutCancellation

  private struct PendingOperation {
    let token: BleGattOperationToken
    let fatalOnTimeout: Bool
    let start: (BleGattOperationToken) -> Void
    let completion: Completion
  }

  private let timeout: TimeInterval
  private let scheduleTimeout: TimeoutScheduler
  private let onFatalTimeout: (BleGattOperationToken) -> Void

  private var nextOperationId: UInt64 = 0
  private(set) var sessionId: UInt64 = 0
  private(set) var isSessionActive = false
  private var pending: [PendingOperation] = []
  private var active: PendingOperation?
  private var timeoutCancellation: BleGattTimeoutCancellation?

  var activeToken: BleGattOperationToken? { active?.token }
  var pendingCount: Int { pending.count }

  init(
    timeout: TimeInterval = 10,
    scheduleTimeout: @escaping TimeoutScheduler = BleGattOperationScheduler.scheduleOnMainQueue,
    onFatalTimeout: @escaping (BleGattOperationToken) -> Void = { _ in }
  ) {
    self.timeout = timeout
    self.scheduleTimeout = scheduleTimeout
    self.onFatalTimeout = onFatalTimeout
  }

  func beginSession() {
    isSessionActive = false
    drain(with: BleGattOperationSchedulerError.sessionReplaced)
    sessionId &+= 1
    isSessionActive = true
  }

  func endSession(with error: Error = BleGattOperationSchedulerError.disconnected) {
    isSessionActive = false
    drain(with: error)
    sessionId &+= 1
  }

  @discardableResult
  func enqueue(
    kind: BleGattOperationKind,
    target: BleGattTarget,
    fatalOnTimeout: Bool = true,
    start: @escaping (BleGattOperationToken) -> Void,
    completion: @escaping Completion
  ) -> BleGattOperationToken? {
    guard isSessionActive else {
      completion(.failure(BleGattOperationSchedulerError.disconnected))
      return nil
    }

    nextOperationId &+= 1
    let token = BleGattOperationToken(
      id: nextOperationId, sessionId: sessionId, kind: kind, target: target)
    pending.append(
      PendingOperation(
        token: token,
        fatalOnTimeout: fatalOnTimeout,
        start: start,
        completion: completion
      ))
    startNextIfNeeded()
    return token
  }

  func contains(kind: BleGattOperationKind, target: BleGattTarget) -> Bool {
    if active?.token.kind == kind, active?.token.target == target {
      return true
    }
    return pending.contains { $0.token.kind == kind && $0.token.target == target }
  }

  /// Resolve only the exact operation currently in flight.
  ///
  /// A callback from another characteristic, another operation kind, or a
  /// previous connection session is deliberately ignored.
  @discardableResult
  func completeExpected(
    sessionId: UInt64,
    kind: BleGattOperationKind,
    target: BleGattTarget,
    result: Result<Data?, Error>
  ) -> Bool {
    guard let operation = active else { return false }
    let token = operation.token
    guard token.sessionId == sessionId, token.kind == kind, token.target == target else {
      return false
    }
    complete(token: token, result: result)
    return true
  }

  @discardableResult
  func complete(token: BleGattOperationToken, result: Result<Data?, Error>) -> Bool {
    guard let operation = active, operation.token == token else { return false }
    timeoutCancellation?.cancel()
    timeoutCancellation = nil
    active = nil
    operation.completion(result)
    startNextIfNeeded()
    return true
  }

  /// Fail the exact active operation and every queued dependent operation
  /// without starting anything else on the compromised connection session.
  @discardableResult
  func failExpectedAndInvalidate(
    sessionId: UInt64,
    kind: BleGattOperationKind,
    target: BleGattTarget,
    error: Error
  ) -> Bool {
    guard let operation = active else { return false }
    let token = operation.token
    guard token.sessionId == sessionId, token.kind == kind, token.target == target else {
      return false
    }

    isSessionActive = false
    drain(with: error)
    self.sessionId &+= 1
    return true
  }

  private func startNextIfNeeded() {
    guard isSessionActive, active == nil, !pending.isEmpty else { return }
    let operation = pending.removeFirst()
    active = operation
    let token = operation.token
    timeoutCancellation = scheduleTimeout(timeout) { [weak self] in
      self?.handleTimeout(token: token)
    }
    operation.start(token)
  }

  private func handleTimeout(token: BleGattOperationToken) {
    guard let timedOutOperation = active, timedOutOperation.token == token else { return }

    if !timedOutOperation.fatalOnTimeout {
      timeoutCancellation = nil
      active = nil
      timedOutOperation.completion(.failure(BleGattOperationSchedulerError.timedOut))
      startNextIfNeeded()
      return
    }

    let operations = [active].compactMap { $0 } + pending
    timeoutCancellation = nil
    active = nil
    pending.removeAll()
    isSessionActive = false
    sessionId &+= 1

    for operation in operations {
      operation.completion(.failure(BleGattOperationSchedulerError.timedOut))
    }
    onFatalTimeout(token)
  }

  private func drain(with error: Error) {
    timeoutCancellation?.cancel()
    timeoutCancellation = nil
    let operations = [active].compactMap { $0 } + pending
    active = nil
    pending.removeAll()
    for operation in operations {
      operation.completion(.failure(error))
    }
  }

  private static func scheduleOnMainQueue(
    interval: TimeInterval,
    action: @escaping () -> Void
  ) -> BleGattTimeoutCancellation {
    let workItem = DispatchWorkItem(block: action)
    DispatchQueue.main.asyncAfter(deadline: .now() + interval, execute: workItem)
    return BleGattTimeoutCancellation(cancel: workItem.cancel)
  }
}

enum BleReconnectBackoff {
  static func delay(forAttempt attempt: Int) -> TimeInterval {
    let boundedAttempt = min(max(attempt, 0), 6)
    return min(30, 0.5 * pow(2, Double(boundedAttempt)))
  }
}

/// Owns reconnect backoff across the complete BLE readiness lifecycle.
///
/// A CoreBluetooth transport connection is not yet a usable device: service and
/// characteristic discovery can still fail. Only `deviceReady()` resets the
/// accumulated failures.
final class BleReconnectLifecycle {
  enum Phase: Equatable {
    case idle
    case waitingToReconnect
    case transportConnected
    case ready
  }

  private(set) var phase: Phase = .idle
  private(set) var failureCount = 0

  func transportConnected() {
    phase = .transportConnected
  }

  func nextReconnectDelay() -> TimeInterval {
    let delay = BleReconnectBackoff.delay(forAttempt: failureCount)
    failureCount = min(failureCount + 1, 6)
    phase = .waitingToReconnect
    return delay
  }

  func deviceReady() {
    failureCount = 0
    phase = .ready
  }
}
