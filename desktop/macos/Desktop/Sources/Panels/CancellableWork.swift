import Foundation

/// A piece of panel work the user can call off.
///
/// Closing the card is an instruction, not a dismissal: the model call behind it should
/// stop, and the day's budget should not be spent on an answer nobody will see. The flag
/// is checked at each phase boundary and the task is cancelled outright, so a request
/// already in flight is torn down rather than merely ignored.
actor CancellableWork {
  private(set) var isCancelled = false
  private var task: Task<Void, Never>?

  nonisolated func cancel() {
    Task { await self.markCancelled() }
  }

  private func markCancelled() {
    isCancelled = true
    task?.cancel()
  }

  /// Runs `body` as a cancellable child. Throws `CancellationError` when the user closed
  /// the card, whether that happened before the work started or while it was running.
  func run<T: Sendable>(_ body: @escaping @Sendable () async throws -> T) async throws -> T {
    guard !isCancelled else { throw CancellationError() }
    let work = Task { try await body() }
    task = Task { _ = try? await work.value }
    defer { task = nil }
    let value = try await work.value
    guard !isCancelled else { throw CancellationError() }
    return value
  }
}
