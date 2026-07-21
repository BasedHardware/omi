import Foundation

enum DeviceOperationBrokerError: LocalizedError, Equatable, Sendable {
  case operationAlreadyPending
  case timedOut
  case cancelled
  case disconnected
  case failed(String)

  var errorDescription: String? {
    switch self {
    case .operationAlreadyPending:
      return "Another operation with the same identity is already pending"
    case .timedOut:
      return "Operation timed out"
    case .cancelled:
      return "Operation was cancelled"
    case .disconnected:
      return "Device disconnected before the operation completed"
    case .failed(let reason):
      return reason
    }
  }
}

struct DeviceOperationHandle<Key: Hashable & Sendable>: Hashable, Sendable {
  fileprivate let key: Key
  fileprivate let token: UInt64
}

enum DeviceOperationTermination: Equatable, Sendable {
  case succeeded
  case timedOut
  case cancelled
  case disconnected
  case failed
}

/// Tracks operations whose physical callback identifies only a key, not the
/// broker token. If such an operation terminates before its callback arrives,
/// the key is poisoned until session teardown: starting another operation
/// would let the old callback masquerade as the new operation's response.
@MainActor
final class UncorrelatedOperationGate<Key: Hashable & Sendable> {
  private var handles: [Key: DeviceOperationHandle<Key>] = [:]
  private var poisonedKeys: Set<Key> = []

  func canStart(_ key: Key) -> Bool {
    handles[key] == nil && !poisonedKeys.contains(key)
  }

  @discardableResult
  func register(_ handle: DeviceOperationHandle<Key>) -> Bool {
    guard canStart(handle.key) else { return false }
    handles[handle.key] = handle
    return true
  }

  func takeHandleForCallback(key: Key) -> DeviceOperationHandle<Key>? {
    guard !poisonedKeys.contains(key) else { return nil }
    return handles.removeValue(forKey: key)
  }

  func terminal(
    handle: DeviceOperationHandle<Key>,
    termination: DeviceOperationTermination
  ) {
    guard handles[handle.key] == handle else { return }
    handles.removeValue(forKey: handle.key)
    if termination != .succeeded {
      poisonedKeys.insert(handle.key)
    }
  }

  func reset() {
    handles.removeAll()
    poisonedKeys.removeAll()
  }
}

protocol DeviceOperationClock: Sendable {
  func sleep(for duration: Duration) async throws
}

struct ContinuousDeviceOperationClock: DeviceOperationClock {
  func sleep(for duration: Duration) async throws {
    try await ContinuousClock().sleep(for: duration)
  }
}

/// Owns one pending operation per key and guarantees exactly one terminal result.
///
/// Device callbacks, timeouts, cancellation, and disconnect can all race. They
/// converge here so only the first terminal event removes and resumes a pending
/// continuation; every late event is an explicit no-op.
actor DeviceOperationBroker<Key: Hashable & Sendable, Value: Sendable> {
  private struct PendingOperation {
    let handle: DeviceOperationHandle<Key>
    let continuation: CheckedContinuation<Value, Error>
    let onTerminal:
      @MainActor @Sendable (
        DeviceOperationHandle<Key>,
        DeviceOperationTermination
      ) -> Void
    var timeoutTask: Task<Void, Never>?
    var startTask: Task<Result<Void, DeviceOperationBrokerError>, Never>?
    var completionToken: UInt64?
  }

  private struct CompletionClaim {
    let operation: PendingOperation
    let token: UInt64
  }

  private let clock: any DeviceOperationClock
  private var nextToken: UInt64 = 0
  private var nextCompletionToken: UInt64 = 0
  private var pending: [Key: PendingOperation] = [:]

  init(clock: any DeviceOperationClock = ContinuousDeviceOperationClock()) {
    self.clock = clock
  }

  func perform(
    key: Key,
    timeout: Duration? = nil,
    onTerminal:
      @escaping @MainActor @Sendable (
        DeviceOperationHandle<Key>,
        DeviceOperationTermination
      ) -> Void = { _, _ in },
    start: @escaping @MainActor @Sendable (DeviceOperationHandle<Key>) async throws -> Void
  ) async throws -> Value {
    guard pending[key] == nil else {
      throw DeviceOperationBrokerError.operationAlreadyPending
    }
    guard !Task.isCancelled else {
      throw DeviceOperationBrokerError.cancelled
    }

    nextToken &+= 1
    let handle = DeviceOperationHandle(key: key, token: nextToken)

    return try await withTaskCancellationHandler {
      try await withCheckedThrowingContinuation { continuation in
        var operation = PendingOperation(
          handle: handle,
          continuation: continuation,
          onTerminal: onTerminal,
          timeoutTask: nil,
          startTask: nil,
          completionToken: nil
        )

        if let timeout {
          operation.timeoutTask = Task { [clock] in
            do {
              try await clock.sleep(for: timeout)
            } catch {
              return
            }
            await self.finish(
              handle: handle,
              result: .failure(DeviceOperationBrokerError.timedOut)
            )
          }
        }

        pending[key] = operation
        if Task.isCancelled {
          Task {
            await self.finish(
              handle: handle,
              result: .failure(DeviceOperationBrokerError.cancelled)
            )
          }
          return
        }
        let startTask = Task<Result<Void, DeviceOperationBrokerError>, Never> { @MainActor in
          guard !Task.isCancelled,
            await self.isPending(handle: handle)
          else {
            return Result.failure(DeviceOperationBrokerError.cancelled)
          }
          do {
            try await start(handle)
            return Result.success(())
          } catch {
            return Result.failure(
              DeviceOperationBrokerError.failed(error.localizedDescription)
            )
          }
        }
        pending[key]?.startTask = startTask
        Task {
          guard case .failure(let error) = await startTask.value else { return }
          await self.finish(handle: handle, result: .failure(error))
        }
      }
    } onCancel: {
      Task {
        await self.finish(
          handle: handle,
          result: .failure(DeviceOperationBrokerError.cancelled)
        )
      }
    }
  }

  @discardableResult
  func succeed(handle: DeviceOperationHandle<Key>, value: Value) async -> Bool {
    guard let claim = claimPending(handle: handle) else { return false }
    let operation = claim.operation
    operation.timeoutTask?.cancel()
    let startResult = await operation.startTask?.value
    guard removePending(handle: handle, completionToken: claim.token) != nil else {
      return false
    }
    if let startResult, case .failure(let error) = startResult {
      await operation.onTerminal(handle, termination(for: error))
      operation.continuation.resume(throwing: error)
    } else {
      await operation.onTerminal(handle, .succeeded)
      operation.continuation.resume(returning: value)
    }
    return true
  }

  @discardableResult
  func fail(handle: DeviceOperationHandle<Key>, reason: String) async -> Bool {
    guard let claim = claimPending(handle: handle) else { return false }
    let operation = claim.operation
    operation.timeoutTask?.cancel()
    if let startTask = operation.startTask {
      _ = await startTask.value
    }
    guard removePending(handle: handle, completionToken: claim.token) != nil else {
      return false
    }
    await operation.onTerminal(handle, .failed)
    operation.continuation.resume(
      throwing: DeviceOperationBrokerError.failed(reason)
    )
    return true
  }

  func cancelAll(reason: DeviceOperationBrokerError = .cancelled) async {
    // Session shutdown deliberately supersedes even a callback that has
    // already claimed completion. Claim every current entry before the
    // first suspension so keys remain unavailable while physical starts
    // drain, and so only this cancellation wave can resume them.
    let handles = pending.values.map(\.handle)
    let claims = handles.compactMap { handle in
      claimPending(handle: handle, replacingExistingClaim: true)
    }
    for claim in claims {
      let operation = claim.operation
      operation.timeoutTask?.cancel()
      operation.startTask?.cancel()
      if let startTask = operation.startTask {
        _ = await startTask.value
      }
      guard
        removePending(
          handle: operation.handle,
          completionToken: claim.token
        ) != nil
      else {
        continue
      }
      await operation.onTerminal(operation.handle, termination(for: reason))
      operation.continuation.resume(throwing: reason)
    }
  }

  func hasPendingOperation(for key: Key) -> Bool {
    pending[key] != nil
  }

  var pendingCount: Int {
    pending.count
  }

  private func finish(
    handle: DeviceOperationHandle<Key>,
    result: Result<Value, Error>
  ) async {
    // Ordinary terminal sources (timeout, caller cancellation, and start
    // failure) may only claim an unclaimed operation. Once a physical
    // callback owns completion, they are late signals and must not steal
    // or double-resume the continuation while its start task drains.
    guard let claim = claimPending(handle: handle) else { return }
    let operation = claim.operation
    operation.timeoutTask?.cancel()
    operation.startTask?.cancel()
    if let startTask = operation.startTask {
      _ = await startTask.value
    }
    guard removePending(handle: handle, completionToken: claim.token) != nil else {
      return
    }
    await operation.onTerminal(handle, termination(for: result))
    operation.continuation.resume(with: result)
  }

  private func isPending(handle: DeviceOperationHandle<Key>) -> Bool {
    pending[handle.key]?.handle == handle
  }

  private func removePending(
    handle: DeviceOperationHandle<Key>,
    completionToken: UInt64
  ) -> PendingOperation? {
    guard pending[handle.key]?.handle == handle,
      pending[handle.key]?.completionToken == completionToken
    else {
      return nil
    }
    return pending.removeValue(forKey: handle.key)
  }

  private func claimPending(
    handle: DeviceOperationHandle<Key>,
    replacingExistingClaim: Bool = false
  ) -> CompletionClaim? {
    guard var operation = pending[handle.key],
      operation.handle == handle,
      replacingExistingClaim || operation.completionToken == nil
    else {
      return nil
    }
    nextCompletionToken &+= 1
    operation.completionToken = nextCompletionToken
    pending[handle.key] = operation
    return CompletionClaim(operation: operation, token: nextCompletionToken)
  }

  private func termination(
    for result: Result<Value, Error>
  ) -> DeviceOperationTermination {
    switch result {
    case .success:
      return .succeeded
    case .failure(let error as DeviceOperationBrokerError):
      return termination(for: error)
    case .failure:
      return .failed
    }
  }

  private func termination(
    for error: DeviceOperationBrokerError
  ) -> DeviceOperationTermination {
    switch error {
    case .timedOut:
      return .timedOut
    case .cancelled:
      return .cancelled
    case .disconnected:
      return .disconnected
    case .operationAlreadyPending, .failed:
      return .failed
    }
  }
}
