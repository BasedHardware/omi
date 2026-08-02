import Foundation

/// Serializes operations that can change or admit the canonical context
/// projection for one runtime client. Swift actors are reentrant while an
/// operation awaits the Node runtime, so actor isolation alone does not keep
/// a context writer from advancing the snapshot between admission attempts.
actor AgentContextAdmissionGate {
  private var held = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func withExclusiveAccess<Result: Sendable>(
    _ operation: @escaping @Sendable () async throws -> Result
  ) async rethrows -> Result {
    await acquire()
    defer { release() }
    return try await operation()
  }

  private func acquire() async {
    guard held else {
      held = true
      return
    }
    await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
      waiters.append(continuation)
    }
  }

  private func release() {
    guard !waiters.isEmpty else {
      held = false
      return
    }
    waiters.removeFirst().resume()
  }
}
