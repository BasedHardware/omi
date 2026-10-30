import Foundation

/// Keep pixels in a removable slot; stream wakeups never retain excluded pending frames.
final class ScreenTaskFrameMailbox: @unchecked Sendable {
  enum Kind: Sendable { case contextSwitch, timerFallback }
  private let lock = NSLock()
  private var pending: (CapturedFrame, Kind)?
  func enqueue(_ frame: CapturedFrame, kind: Kind) { lock.withLock { pending = (frame, kind) } }
  func take() -> (CapturedFrame, Kind)? {
    lock.withLock {
      defer { pending = nil }
      return pending
    }
  }
  func purge(app: String) { lock.withLock { if pending?.0.appName == app { pending = nil } } }
}

extension Notification.Name {
  static let screenCaptureExclusionChanged = Notification.Name("screenCaptureExclusionChanged")
}
