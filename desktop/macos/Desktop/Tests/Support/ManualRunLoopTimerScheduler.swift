import Foundation

@testable import Omi_Computer

/// Uses real, unscheduled timers so invalidation is measured without introducing
/// run-loop sources. Advancing time and delivering a tick are separate operations.
@MainActor
final class ManualRunLoopTimerScheduler {
  private(set) var now = Date(timeIntervalSince1970: 1_700_000_000)
  private(set) var timers: [Timer] = []

  var activeTimerCount: Int { timers.filter(\.isValid).count }

  func schedule(interval: TimeInterval, tick: @escaping @MainActor () -> Void) -> OwnedRunLoopTimer {
    let timer = Timer(timeInterval: interval, repeats: true) { _ in
      MainActor.assumeIsolated { tick() }
    }
    timers.append(timer)
    return OwnedRunLoopTimer(timer)
  }

  func advance(by interval: TimeInterval) {
    now.addTimeInterval(interval)
  }

  func fire() {
    for timer in timers where timer.isValid {
      timer.fire()
    }
  }
}
