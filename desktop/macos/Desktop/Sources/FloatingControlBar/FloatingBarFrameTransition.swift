import AppKit
import Foundation

/// One owner for every floating-bar frame snap and animation.
///
/// Starting a new transition invalidates the previous completion by construction:
/// completions capture a token, and only the current token may land. Hover
/// collapse and close-settle work that used to live on a hand-managed
/// `DispatchWorkItem` or `asyncAfter` are scheduled through the same owner so a
/// later snap cannot leave a stale resize behind.
final class FloatingBarFrameTransition {
  struct Token: Equatable {
    fileprivate let id: UInt64
  }

  private var generation: UInt64 = 0
  private(set) var pendingTarget: NSRect?
  private var scheduledWork: DispatchWorkItem?

  var currentGeneration: UInt64 { generation }
  var isAnimating: Bool { pendingTarget != nil }

  /// Begin a new snap or animation. Any in-flight completion or scheduled
  /// settle from a previous `start`/`schedule` is stale.
  @discardableResult
  func start(pendingTarget: NSRect? = nil) -> Token {
    generation &+= 1
    scheduledWork?.cancel()
    scheduledWork = nil
    self.pendingTarget = pendingTarget
    return Token(id: generation)
  }

  func isCurrent(_ token: Token) -> Bool {
    token.id == generation
  }

  func clearPending(if token: Token) {
    guard isCurrent(token) else { return }
    pendingTarget = nil
  }

  func dropPendingWithoutInvalidating() {
    pendingTarget = nil
  }

  /// Cancel in-flight completions without aiming at a new frame.
  func invalidate() {
    _ = start(pendingTarget: nil)
    pendingTarget = nil
  }

  func cancelScheduled() {
    scheduledWork?.cancel()
    scheduledWork = nil
  }
  func scheduleOnNextTurn(_ work: @escaping () -> Void) {
    let token = start()
    let item = DispatchWorkItem { [weak self] in
      guard let self, self.isCurrent(token) else { return }
      work()
    }
    scheduledWork = item
    DispatchQueue.main.async(execute: item)
  }
}
