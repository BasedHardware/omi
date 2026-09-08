import Foundation

enum DeviceCommandQueueError: LocalizedError, Equatable {
  case closed

  var errorDescription: String? {
    "The device command channel is closed"
  }
}

/// Serializes adapter commands that share one uncorrelated BLE write channel.
///
/// Device command responses carry a command ID, but the physical write callback
/// identifies only the characteristic. Keeping the whole request/response
/// exchange serial prevents a second command from being rejected locally after
/// its response gate was registered, and makes callback ownership explicit.
@MainActor
final class DeviceCommandQueue {
  private var tail = Task<Void, Never> {}
  private var nextToken: UInt64 = 0
  private var cancellationActions: [UInt64: @MainActor () -> Void] = [:]
  private var isClosed = false

  func run<Value: Sendable>(
    _ operation: @escaping @MainActor @Sendable () async throws -> Value
  ) async throws -> Value {
    guard !isClosed else { throw DeviceCommandQueueError.closed }

    nextToken &+= 1
    let token = nextToken
    let predecessor = tail
    let task = Task { @MainActor [weak self] in
      await predecessor.value
      guard let self, !self.isClosed else {
        throw DeviceCommandQueueError.closed
      }
      try Task.checkCancellation()
      return try await operation()
    }
    cancellationActions[token] = {
      task.cancel()
    }
    tail = Task { @MainActor [weak self] in
      _ = try? await task.value
      self?.cancellationActions.removeValue(forKey: token)
    }

    return try await withTaskCancellationHandler {
      try await task.value
    } onCancel: {
      task.cancel()
    }
  }

  /// Permanently closes the one-session queue, cancels active and queued
  /// commands, and joins the tail before adapter brokers are reset.
  func close() async {
    guard !isClosed else {
      await tail.value
      return
    }

    isClosed = true
    let actions = Array(cancellationActions.values)
    let drainingTail = tail
    actions.forEach { $0() }
    await drainingTail.value
    cancellationActions.removeAll()
  }
}
