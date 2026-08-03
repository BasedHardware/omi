import Foundation

/// Serializes operations that can change or admit the canonical context
/// projection for one runtime client. Swift actors are reentrant while an
/// operation awaits the Node runtime, so actor isolation alone does not keep
/// a context writer from advancing the snapshot between admission attempts.
///
/// `AgentClient.Session` routes mutating and admission-adjacent bridge calls
/// through this gate. Intentionally excluded:
/// - Read-only journal snapshots (`listJournalTurns`, `listJournalTurnsForControl`)
///   — they do not advance the canonical context projection and must stay
///   callable while projection refresh work is in flight (including from
///   paths that already hold the gate); the gate is not reentrant.
/// - Runtime lifecycle (`start`, `stop`, `interrupt`, auth-handler wiring) —
///   process control, not context projection admission.
/// - Long-running `bridge.query` streaming — only refresh and admission are
///   serialized; the query stream itself runs outside the gate.
actor AgentContextAdmissionGate {
  private struct Waiter {
    let id: UUID
    let continuation: CheckedContinuation<Void, Error>
  }

  private var held = false
  private var waiters: [Waiter] = []

  func withExclusiveAccess<Result: Sendable>(
    _ operation: @escaping @Sendable () async throws -> Result
  ) async throws -> Result {
    try await acquire()
    defer { release() }
    try Task.checkCancellation()
    return try await operation()
  }

  private func acquire() async throws {
    try Task.checkCancellation()
    guard !held else {
      let waiterID = UUID()
      try await withTaskCancellationHandler {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
          waiters.append(Waiter(id: waiterID, continuation: continuation))
        }
      } onCancel: { [weak self] in
        guard let self else { return }
        Task { await self.cancelWaiter(id: waiterID) }
      }
      try Task.checkCancellation()
      return
    }
    held = true
  }

  private func cancelWaiter(id: UUID) {
    guard let index = waiters.firstIndex(where: { $0.id == id }) else { return }
    let waiter = waiters.remove(at: index)
    waiter.continuation.resume(throwing: CancellationError())
  }

  private func release() {
    while !waiters.isEmpty {
      let waiter = waiters.removeFirst()
      waiter.continuation.resume()
      return
    }
    held = false
  }
}
