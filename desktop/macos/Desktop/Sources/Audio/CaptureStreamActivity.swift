import Foundation

/// Evidence that a capture driver is still delivering PCM, not merely that HAL
/// accepted its start. Each driver owns its own instance; a replacement cannot
/// inherit another driver's liveness. Silence is valid PCM for the system tap.
final class CaptureStreamActivity: @unchecked Sendable {
  private let lock = NSLock()
  private var lastFrameAt: TimeInterval?
  private let now: @Sendable () -> TimeInterval
  static let freshnessWindow: TimeInterval = 5

  init(now: @escaping @Sendable () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) {
    self.now = now
  }

  func notePCM(byteCount: Int) {
    guard byteCount >= MemoryLayout<Int16>.size else { return }
    lock.withLock { lastFrameAt = now() }
  }

  var hasRecentFrames: Bool {
    lock.withLock {
      guard let lastFrameAt else { return false }
      let age = now() - lastFrameAt
      return age >= 0 && age <= Self.freshnessWindow
    }
  }

  func reset() {
    lock.withLock { lastFrameAt = nil }
  }
}
