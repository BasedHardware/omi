import Foundation

@MainActor
protocol DelayedActionCancellation: AnyObject {
  func cancel()
}

@MainActor
protocol DelayedActionScheduling {
  @discardableResult
  func schedule(
    after interval: TimeInterval,
    action: @escaping @MainActor () -> Void
  ) -> DelayedActionCancellation
}

@MainActor
private final class TaskDelayedActionCancellation: DelayedActionCancellation {
  private var task: Task<Void, Never>?

  init(task: Task<Void, Never>) {
    self.task = task
  }

  func cancel() {
    task?.cancel()
    task = nil
  }
}

/// Production scheduler for cancellable UI deadlines. Consumers inject a
/// manual implementation in tests, so watchdog and debounce behavior never
/// depends on wall-clock sleeps.
@MainActor
final class TaskDelayedActionScheduler: DelayedActionScheduling {
  func schedule(
    after interval: TimeInterval,
    action: @escaping @MainActor () -> Void
  ) -> DelayedActionCancellation {
    let task = Task { @MainActor in
      do {
        try await Task.sleep(nanoseconds: UInt64(max(0, interval) * 1_000_000_000))
      } catch {
        return
      }
      guard !Task.isCancelled else { return }
      action()
    }
    return TaskDelayedActionCancellation(task: task)
  }
}
