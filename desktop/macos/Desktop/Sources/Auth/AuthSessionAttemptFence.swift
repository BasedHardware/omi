import Foundation
import os

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
  /// Serialises `begin` against `commitIfCurrent` so a newer attempt cannot
  /// start while a commit's credential/defaults mutation is mid-flight.
  ///
  /// **Never taken by the read paths.** A commit's operation can post a
  /// `UserDefaults` change notification, and notification delivery to
  /// queue-based observers is synchronous — a background commit can therefore
  /// legitimately wait on the main thread. If the main thread then needed this
  /// lock merely to *read* the current attempt (`APIClient.buildHeaders` does,
  /// on every request), the app deadlocked with a frozen UI: the shipped
  /// sign-in screen whose buttons answered nothing (#11374 follow-up).
  private let commitLock = NSLock()
  /// The generation value, behind its own micro-lock that is never held across
  /// caller code — readers always complete promptly on any thread.
  private let generation = OSAllocatedUnfairLock<UInt64>(initialState: 0)

  func begin() -> AuthSessionAttempt {
    commitLock.withLock {
      generation.withLock { value in
        value &+= 1
        return AuthSessionAttempt(generation: value)
      }
    }
  }

  func current() -> AuthSessionAttempt {
    AuthSessionAttempt(generation: generation.withLock { $0 })
  }

  func isCurrent(_ attempt: AuthSessionAttempt) -> Bool {
    generation.withLock { $0 } == attempt.generation
  }

  /// Execute a synchronous commit only while `attempt` remains authoritative.
  /// Holding `commitLock` makes beginning a newer attempt mutually exclusive
  /// with the credential/defaults mutation itself; reads stay lock-free.
  func commitIfCurrent<T>(
    _ attempt: AuthSessionAttempt,
    _ operation: () throws -> T
  ) rethrows -> T? {
    try commitLock.withLock {
      guard generation.withLock({ $0 }) == attempt.generation else { return nil }
      return try operation()
    }
  }
}
