import Foundation

/// A monotonic capability for asynchronous authentication work.
///
/// `AuthService` is MainActor-isolated, but its async entry points are
/// re-entrant. A restore, sign-in, refresh, invalidation, or sign-out can resume
/// after a newer session operation has already started. This fence lets the
/// completion prove that it still owns the session before it mutates tokens,
/// persisted identity, or published auth state.
struct AuthSessionAttempt: Equatable, Sendable {
  let generation: UInt64
}

final class AuthSessionAttemptFence: @unchecked Sendable {
  private let lock = NSLock()
  private var generation: UInt64 = 0

  func begin() -> AuthSessionAttempt {
    lock.withLock {
      generation &+= 1
      return AuthSessionAttempt(generation: generation)
    }
  }

  func current() -> AuthSessionAttempt {
    lock.withLock {
      AuthSessionAttempt(generation: generation)
    }
  }

  func isCurrent(_ attempt: AuthSessionAttempt) -> Bool {
    lock.withLock { generation == attempt.generation }
  }

  /// Execute a synchronous commit only while `attempt` remains authoritative.
  /// Holding the lock makes beginning a newer attempt mutually exclusive with
  /// the credential/defaults mutation itself.
  func commitIfCurrent<T>(
    _ attempt: AuthSessionAttempt,
    _ operation: () throws -> T
  ) rethrows -> T? {
    try lock.withLock {
      guard generation == attempt.generation else { return nil }
      return try operation()
    }
  }
}
