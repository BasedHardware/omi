import Foundation

/// A thread-safe count of calls, for code that has to prove how many times a
/// closure ran from whichever task it ran on.
public final class LockedCounter: @unchecked Sendable {
  private let lock = NSLock()
  private var calls = 0

  public init() {}

  public var count: Int { lock.withLock { calls } }

  /// Adds one and returns the new count.
  @discardableResult
  public func increment() -> Int {
    lock.withLock {
      calls += 1
      return calls
    }
  }
}
