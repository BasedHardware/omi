import Foundation

/// The run loop retains a scheduled timer, so releasing its feature owner is
/// insufficient. This token owns invalidation even when explicit stop is missed.
/// Keep callbacks weakly bound to the feature owner to avoid a retain cycle.
final class OwnedRunLoopTimer {
  let timer: Timer

  init(_ timer: Timer) {
    self.timer = timer
  }

  func cancel() {
    timer.invalidate()
  }

  deinit {
    timer.invalidate()
  }

  typealias Scheduler = @MainActor (TimeInterval, @escaping @MainActor () -> Void) -> OwnedRunLoopTimer

  @MainActor
  static func schedule(interval: TimeInterval, tick: @escaping @MainActor () -> Void) -> OwnedRunLoopTimer {
    let timer = Timer(timeInterval: interval, repeats: true) { _ in
      MainActor.assumeIsolated { tick() }
    }
    RunLoop.main.add(timer, forMode: .common)
    return OwnedRunLoopTimer(timer)
  }
}
