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
  private final class WaiterHandle: @unchecked Sendable {
    var cancelled = false
    var continuation: CheckedContinuation<WakeReason, Never>?
  }

  private enum WakeReason {
    case granted
    case cancelled
  }

  private struct WaiterSlot {
    let handle: WaiterHandle
    var continuation: CheckedContinuation<WakeReason, Never>?
  }

  private var held = false
  private var releasePending = false
  private var waiters: [WaiterSlot] = []
  private var waiterHead = 0

  func withExclusiveAccess<Result: Sendable>(
    _ operation: @escaping @Sendable () async throws -> Result
  ) async throws -> Result {
    guard try await waitToAcquire() else {
      throw CancellationError()
    }
    defer { release() }
    return try await operation()
  }

  private func waitToAcquire() async throws -> Bool {
    guard held else {
      held = true
      return true
    }

    let handle = WaiterHandle()
    let slotIndex = appendWaiterSlot(handle: handle)
    let wakeReason: WakeReason = await withTaskCancellationHandler {
      await withCheckedContinuation { (continuation: CheckedContinuation<WakeReason, Never>) in
        registerWaiter(slotIndex: slotIndex, handle: handle, continuation: continuation)
      }
    } onCancel: {
      handle.cancelled = true
      if let continuation = handle.continuation {
        handle.continuation = nil
        continuation.resume(returning: .cancelled)
      }
      Task { await self.finalizeCancelledWaiter(at: slotIndex) }
    }

    switch wakeReason {
    case .granted:
      return true
    case .cancelled:
      finalizeCancelledWaiter(at: slotIndex)
      return false
    }
  }

  private func appendWaiterSlot(handle: WaiterHandle) -> Int {
    compactWaitersIfNeeded()
    waiters.append(WaiterSlot(handle: handle))
    return waiters.count - 1
  }

  private func registerWaiter(
    slotIndex: Int,
    handle: WaiterHandle,
    continuation: CheckedContinuation<WakeReason, Never>
  ) {
    guard waiters.indices.contains(slotIndex) else {
      continuation.resume(returning: .cancelled)
      return
    }
    if handle.cancelled {
      continuation.resume(returning: .cancelled)
      return
    }
    handle.continuation = continuation
    waiters[slotIndex].continuation = continuation
    if releasePending {
      releasePending = false
      release()
    }
  }

  private func finalizeCancelledWaiter(at index: Int) {
    guard waiters.indices.contains(index) else { return }
    waiters[index].continuation = nil
    waiters[index].handle.cancelled = true
    if index == waiterHead {
      advanceWaiterHeadPastCancelled()
    }
    compactWaitersIfNeeded()
    if waiterHead >= waiters.count, !held {
      waiters.removeAll(keepingCapacity: true)
      waiterHead = 0
    }
  }

  private func release() {
    advanceWaiterHeadPastCancelled()
    while waiterHead < waiters.count {
      if waiters[waiterHead].handle.cancelled {
        waiterHead += 1
        continue
      }
      if let continuation = waiters[waiterHead].continuation {
        waiters[waiterHead].continuation = nil
        waiterHead += 1
        compactWaitersIfNeeded()
        continuation.resume(returning: .granted)
        return
      }
      releasePending = true
      return
    }
    held = false
    releasePending = false
    waiters.removeAll(keepingCapacity: true)
    waiterHead = 0
  }

  private func advanceWaiterHeadPastCancelled() {
    while waiterHead < waiters.count, waiters[waiterHead].handle.cancelled {
      waiterHead += 1
    }
    compactWaitersIfNeeded()
  }

  private func compactWaitersIfNeeded() {
    guard waiterHead > 32, waiterHead > waiters.count / 2 else { return }
    waiters.removeFirst(waiterHead)
    waiterHead = 0
  }
}
