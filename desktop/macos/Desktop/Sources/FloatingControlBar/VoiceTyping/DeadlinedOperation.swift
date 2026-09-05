import Foundation

/// Runs an async operation under a hard deadline and returns the moment the
/// deadline passes, whether or not the operation has noticed it was cancelled.
///
/// A task group races the operation against a sleeper, but the group scope
/// waits for its cancelled child before returning — and an HTTP call stuck in
/// a token refresh, or a decoder in the middle of a buffer, is not at a
/// suspension point that honours cancellation. The dictation caps (12 s for the
/// backend recognizer, 6 s for the polisher) are promises to a user watching an
/// empty caret, so the deadline is enforced here at the boundary: the work is
/// cancelled and abandoned, and its late result, if any, is dropped.
///
/// Cancelling the *calling* task cancels the work and surfaces as
/// `CancellationError`, never as a timeout, so a superseded turn does not fall
/// through to a fallback recognizer.
enum DeadlinedOperation {

  enum Failure: Error, Equatable {
    case timedOut
  }

  static func run<T: Sendable>(
    seconds: TimeInterval,
    _ operation: @escaping @Sendable () async throws -> T
  ) async throws -> T {
    let outcome = Outcome<T>()
    let work = Task { () -> Void in
      do {
        let value = try await operation()
        outcome.settle(.success(value))
      } catch {
        outcome.settle(.failure(error))
      }
    }
    let timer = Task { () -> Void in
      try? await Task.sleep(nanoseconds: UInt64(max(0, seconds) * 1_000_000_000))
      guard !Task.isCancelled else { return }
      if outcome.settle(.failure(Failure.timedOut)) { work.cancel() }
    }
    return try await withTaskCancellationHandler {
      try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<T, Error>) in
        outcome.deliver(to: continuation)
      }
    } onCancel: {
      if outcome.settle(.failure(CancellationError())) {
        work.cancel()
        timer.cancel()
      }
    }
  }

  /// The first result to arrive wins; every later one is dropped. The
  /// continuation is resumed exactly once, whichever of the three parties
  /// (work, timer, outer cancellation) gets there first.
  private final class Outcome<T: Sendable>: @unchecked Sendable {
    private let lock = NSLock()
    private var result: Result<T, Error>?
    private var continuation: CheckedContinuation<T, Error>?

    /// Returns true when this call decided the outcome.
    @discardableResult
    func settle(_ new: Result<T, Error>) -> Bool {
      lock.lock()
      guard result == nil else {
        lock.unlock()
        return false
      }
      result = new
      let pending = continuation
      continuation = nil
      lock.unlock()
      pending?.resume(with: new)
      return true
    }

    func deliver(to continuation: CheckedContinuation<T, Error>) {
      lock.lock()
      if let result {
        lock.unlock()
        continuation.resume(with: result)
        return
      }
      self.continuation = continuation
      lock.unlock()
    }
  }
}
