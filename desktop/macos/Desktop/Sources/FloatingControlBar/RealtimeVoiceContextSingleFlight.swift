import Foundation

/// Controller-owned readiness work is shared across speculative warmup and the
/// active PTT turn. Cancelling a turn waiter must not cancel the underlying
/// owner-scoped snapshot, otherwise a cold first turn leaves the hub cold until
/// the user presses PTT a second time.
@MainActor
final class RealtimeVoiceContextSingleFlight {
  private final class Flight {
    var task: Task<Bool, Never>!
  }

  private var activeFlight: Flight?

  var isRunning: Bool {
    activeFlight != nil
  }

  @discardableResult
  func joinOrStart(
    _ operation: @escaping @MainActor @Sendable () async -> Bool
  ) -> Task<Bool, Never> {
    if let activeFlight {
      return activeFlight.task
    }
    return start(operation)
  }

  @discardableResult
  func restart(
    _ operation: @escaping @MainActor @Sendable () async -> Bool
  ) -> Task<Bool, Never> {
    cancel()
    return start(operation)
  }

  private func start(
    _ operation: @escaping @MainActor @Sendable () async -> Bool
  ) -> Task<Bool, Never> {
    let flight = Flight()
    flight.task = Task { @MainActor [weak self, weak flight] in
      let result = await operation()
      if let self, let flight, self.activeFlight === flight {
        self.activeFlight = nil
      }
      return result
    }
    activeFlight = flight
    return flight.task
  }

  func cancel() {
    let flight = activeFlight
    activeFlight = nil
    flight?.task.cancel()
  }
}
