import Foundation

/// Resume-at-most-once gate for continuation races (see RealtimeHubController.value(of:)).
final class RealtimeHubResumeOnceGate: @unchecked Sendable {
  private let lock = NSLock()
  private var done = false
  func first() -> Bool {
    lock.lock()
    defer { lock.unlock() }
    if done { return false }
    done = true
    return true
  }
}
