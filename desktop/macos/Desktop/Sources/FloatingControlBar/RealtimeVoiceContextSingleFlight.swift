import Foundation

/// Controller-owned readiness work is shared across speculative warmup and the
/// active PTT turn. Cancelling a turn waiter must not cancel the underlying
/// owner-scoped snapshot, otherwise a cold first turn leaves the hub cold until
/// the user presses PTT a second time.
@MainActor
final class RealtimeVoiceContextSingleFlight {
  private struct Flight {
    let id: UInt64
    let task: Task<Bool, Never>
  }

  private var activeFlight: Flight?
  private var nextFlightID: UInt64 = 0

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
    nextFlightID &+= 1
    let flightID = nextFlightID
    let task = Task { @MainActor [weak self] in
      let result = await operation()
      if let self, self.activeFlight?.id == flightID {
        self.activeFlight = nil
      }
      return result
    }
    activeFlight = Flight(id: flightID, task: task)
    return task
  }

  func cancel() {
    let flight = activeFlight
    activeFlight = nil
    flight?.task.cancel()
  }
}
