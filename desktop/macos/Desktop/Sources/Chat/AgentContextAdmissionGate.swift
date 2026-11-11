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
    private let lock = NSLock()
    private var cancelled = false
    private var continuation: CheckedContinuation<WakeReason, Never>?

    func cancel() -> CheckedContinuation<WakeReason, Never>? {
      lock.lock()
      defer { lock.unlock() }
      cancelled = true
      let continuation = continuation
      self.continuation = nil
      return continuation
    }

    func register(_ continuation: CheckedContinuation<WakeReason, Never>) -> Bool {
      lock.lock()
      defer { lock.unlock() }
      guard !cancelled else { return false }
      self.continuation = continuation
      return true
    }

    func isCancelled() -> Bool {
      lock.lock()
      defer { lock.unlock() }
      return cancelled
    }

    func takeContinuation() -> CheckedContinuation<WakeReason, Never>? {
      lock.lock()
      defer { lock.unlock() }
      let continuation = continuation
      self.continuation = nil
      return continuation
    }
  }

  private enum WakeReason {
    case granted
    case cancelled
  }

  private struct WaiterSlot {
    let handle: WaiterHandle
  }

  private var held = false
  private var releasePending = false
  private var waiters: [WaiterSlot] = []
  private var waiterHead = 0
  private let onWaiterRegistered: (@Sendable () -> Void)?
  private let beforeResumingGrantedWaiter: (@Sendable () -> Void)?

  init(
    onWaiterRegistered: (@Sendable () -> Void)? = nil,
    beforeResumingGrantedWaiter: (@Sendable () -> Void)? = nil
  ) {
    self.onWaiterRegistered = onWaiterRegistered
    self.beforeResumingGrantedWaiter = beforeResumingGrantedWaiter
  }

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
      if let continuation = handle.cancel() {
        continuation.resume(returning: .cancelled)
      }
      Task { await self.finalizeCancelledWaiter(handle: handle) }
    }

    switch wakeReason {
    case .granted:
      return true
    case .cancelled:
      finalizeCancelledWaiter(handle: handle)
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
    guard handle.register(continuation) else {
      continuation.resume(returning: .cancelled)
      return
    }
    onWaiterRegistered?()
    if releasePending {
      releasePending = false
      release()
    }
  }

  private func finalizeCancelledWaiter(handle: WaiterHandle) {
    guard let index = waiters.firstIndex(where: { $0.handle === handle }) else { return }
    if index == waiterHead {
      advanceWaiterHeadPastCancelled()
    }
    compactWaitersIfNeeded()
    if releasePending {
      releasePending = false
      release()
      return
    }
    if waiterHead >= waiters.count, !held {
      waiters.removeAll(keepingCapacity: true)
      waiterHead = 0
    }
  }

  private func release() {
    advanceWaiterHeadPastCancelled()
    while waiterHead < waiters.count {
      let handle = waiters[waiterHead].handle
      if handle.isCancelled() {
        waiterHead += 1
        continue
      }
      if let continuation = handle.takeContinuation() {
        waiterHead += 1
        compactWaitersIfNeeded()
        beforeResumingGrantedWaiter?()
        continuation.resume(returning: .granted)
        return
      }
      if handle.isCancelled() {
        waiterHead += 1
        continue
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
    while waiterHead < waiters.count, waiters[waiterHead].handle.isCancelled() {
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
