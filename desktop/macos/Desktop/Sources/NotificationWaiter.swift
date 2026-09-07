import Foundation

/// Catches the next notification of one name, from the moment it is made.
///
/// Made before the action that provokes the notification, so an answer posted
/// synchronously during that action — the way a mounted surface acknowledges
/// a rebuild request — is not missed; then awaited, with a bound. `extract`
/// reduces the notification to a `Sendable` value on the posting thread.
final class NotificationWaiter<Payload: Sendable>: @unchecked Sendable {
  private let lock = NSLock()
  private var received: Payload?
  private var continuation: CheckedContinuation<Payload?, Never>?
  private var observer: NSObjectProtocol?

  init(name: Notification.Name, extract: @escaping @Sendable (Notification) -> Payload) {
    observer = NotificationCenter.default.addObserver(forName: name, object: nil, queue: nil) { [weak self] note in
      self?.deliver(extract(note))
    }
  }

  deinit {
    if let observer { NotificationCenter.default.removeObserver(observer) }
  }

  private func deliver(_ payload: Payload) {
    lock.lock()
    guard received == nil else {
      lock.unlock()
      return
    }
    received = payload
    let waiting = continuation
    continuation = nil
    lock.unlock()
    waiting?.resume(returning: payload)
  }

  /// The payload, or `nil` once `timeout` has passed without a notification.
  func wait(for timeout: Duration) async -> Payload? {
    await awaitWithTimeout(timeout) { [self] in
      await withCheckedContinuation { (continuation: CheckedContinuation<Payload?, Never>) in
        lock.lock()
        if let received {
          lock.unlock()
          continuation.resume(returning: received)
          return
        }
        self.continuation = continuation
        lock.unlock()
      }
    } ?? nil
  }
}
