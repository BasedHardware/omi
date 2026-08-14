import Foundation

@testable import Omi_Computer

@MainActor
final class ManualDelayedActionCancellation: DelayedActionCancellation {
  private(set) var isCancelled = false

  func cancel() {
    isCancelled = true
  }
}

@MainActor
final class ManualDelayedActionScheduler: DelayedActionScheduling {
  private struct ScheduledAction {
    let cancellation: ManualDelayedActionCancellation
    let action: @MainActor () -> Void
  }

  private var scheduledActions: [ScheduledAction] = []

  var activeCount: Int {
    scheduledActions.filter { !$0.cancellation.isCancelled }.count
  }

  @discardableResult
  func schedule(
    after interval: TimeInterval,
    action: @escaping @MainActor () -> Void
  ) -> DelayedActionCancellation {
    _ = interval
    let cancellation = ManualDelayedActionCancellation()
    scheduledActions.append(.init(cancellation: cancellation, action: action))
    return cancellation
  }

  @discardableResult
  func fireNext() -> Bool {
    guard let index = scheduledActions.firstIndex(where: { !$0.cancellation.isCancelled }) else {
      return false
    }
    let scheduled = scheduledActions.remove(at: index)
    scheduled.action()
    return true
  }
}
