import AppKit
import Foundation

/// The floating bar's ~250 ms cursor poll, armed only while there is a second screen to move to.
///
/// The poll runs on the **main** queue, and it used to be unconditional: on the single-screen Mac
/// most of them are, that was four run-loop wake-ups a second for the life of the process, each one
/// re-reading `NSScreen.screens.count` and returning. Screen parameters changing is the only thing
/// that can change that answer, so the bar re-syncs from that notification instead of asking four
/// times a second.
///
/// Arming is a policy, not a side effect of construction, so `isTracking` states it and a test can
/// drive it through `screenCount` without attaching a display.
@MainActor
final class CursorScreenTracker {
  private let screenCount: () -> Int
  private var timer: DispatchSourceTimer?
  private var onTick: (@MainActor () -> Void)?

  init(screenCount: @escaping () -> Int = { NSScreen.screens.count }) {
    self.screenCount = screenCount
  }

  /// Whether the poll is running right now.
  var isTracking: Bool { timer != nil }

  /// Adopts `onTick` as the poll body and arms for the current layout.
  func start(onTick: @escaping @MainActor () -> Void) {
    self.onTick = onTick
    sync()
  }

  /// Re-decides whether the poll should be running. Idempotent: re-arming an already-armed tracker
  /// keeps the existing timer rather than stacking a second one.
  func sync() {
    guard screenCount() > 1 else {
      timer?.cancel()
      timer = nil
      return
    }
    guard timer == nil, let onTick else { return }
    let source = DispatchSource.makeTimerSource(queue: .main)
    source.schedule(deadline: .now(), repeating: .milliseconds(250))
    source.setEventHandler { MainActor.assumeIsolated { onTick() } }
    source.resume()
    timer = source
  }
}
