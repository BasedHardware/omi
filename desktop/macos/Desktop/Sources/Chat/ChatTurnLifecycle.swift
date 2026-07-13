import Foundation

enum ChatTurnRevocationReason: Equatable, Sendable {
  case stop(ChatTurnStopReason)
  case toolStall
  case watchdogTimeout
}

/// Product authority for one in-flight chat turn.
///
/// This state deliberately lives outside analytics: disabling or refactoring
/// telemetry must never make a stopped or timed-out bridge result authoritative.
@MainActor
final class ChatTurnLifecycle {
  enum State: Equatable, Sendable {
    case active
    case completed
    case revoked(ChatTurnRevocationReason)
  }

  private(set) var state: State = .active

  var acceptsResult: Bool { state == .active }
  var revocationReason: ChatTurnRevocationReason? {
    guard case .revoked(let reason) = state else { return nil }
    return reason
  }
  var stopReason: ChatTurnStopReason? {
    guard case .revoked(.stop(let reason)) = state else { return nil }
    return reason
  }

  @discardableResult
  func revoke(_ reason: ChatTurnRevocationReason) -> Bool {
    guard state == .active else { return false }
    state = .revoked(reason)
    return true
  }

  @discardableResult
  func complete() -> Bool {
    guard state == .active else { return false }
    state = .completed
    return true
  }
}

struct ChatQueryResultAuthority {
  static func acceptsContinuation(
    currentGeneration: Int,
    turnGeneration: Int,
    turnAcceptsResult: Bool
  ) -> Bool {
    currentGeneration == turnGeneration && turnAcceptsResult
  }

  static func accepts(
    currentGeneration: Int,
    resultGeneration: Int,
    turnAcceptsResult: Bool,
    watchdogFired: Bool,
    toolStallAbortFired: Bool
  ) -> Bool {
    acceptsContinuation(
      currentGeneration: currentGeneration,
      turnGeneration: resultGeneration,
      turnAcceptsResult: turnAcceptsResult
    )
      && !watchdogFired
      && !toolStallAbortFired
  }
}

/// Generation ownership for ChatProvider's single-send bridge lock.
///
/// A stopped turn can finish unwinding after the stop grace period has already
/// released the bridge and a newer turn has acquired it. Cleanup from the old
/// task may release only the generation it originally acquired.
struct ChatSendLockOwnership: Equatable, Sendable {
  private(set) var generation: Int?

  var isHeld: Bool { generation != nil }

  @discardableResult
  mutating func acquire(generation: Int) -> Bool {
    guard self.generation == nil else { return false }
    self.generation = generation
    return true
  }

  @discardableResult
  mutating func release(generation: Int) -> Bool {
    guard self.generation == generation else { return false }
    self.generation = nil
    return true
  }
}

/// Generation-keyed ownership for terminal side effects that can race a late
/// adapter result (journal status/callback today). Claim removes the target
/// atomically, so only one path can finalize it and an older path cannot consume
/// a newer generation's work.
struct ChatTerminalTargetRegistry<T> {
  private var targets: [Int: T] = [:]

  mutating func register(_ target: T, generation: Int) {
    targets[generation] = target
  }

  mutating func claim(generation: Int) -> T? {
    targets.removeValue(forKey: generation)
  }
}

/// Orders coalesced streaming journal writes ahead of the exact terminal
/// mutation for the same assistant turn. Claiming is synchronous on the main
/// actor, so no later streaming callback can enqueue after terminalization has
/// taken ownership; an already queued write is drained before the caller sends
/// the terminal mutation to the kernel.
@MainActor
final class ChatJournalWriteCoordinator {
  private var updateTasks: [String: Task<Void, Never>] = [:]
  private var terminalizingMessageIDs: Set<String> = []

  @discardableResult
  func schedule(
    messageID: String,
    operation: @escaping @MainActor @Sendable () async -> Void
  ) -> Bool {
    guard !terminalizingMessageIDs.contains(messageID) else { return false }
    let previous = updateTasks[messageID]
    let task = Task { @MainActor in
      _ = await previous?.value
      guard !Task.isCancelled else { return }
      await operation()
    }
    updateTasks[messageID] = task
    return true
  }

  func beginTerminalization(messageID: String) async -> Bool {
    guard terminalizingMessageIDs.insert(messageID).inserted else { return false }
    _ = await updateTasks.removeValue(forKey: messageID)?.value
    return true
  }

  func cancelAll() {
    for task in updateTasks.values { task.cancel() }
    updateTasks.removeAll()
    terminalizingMessageIDs.removeAll()
  }
}

/// Collects bridge callbacks that were emitted before `query()` returned so
/// ChatProvider can apply them before it finalizes the visible response.
///
/// Agent adapters invoke callbacks synchronously but those callbacks hop to the
/// main actor. Without an explicit drain, the query continuation can win that
/// hop and persist a response before its last delta or tool event is applied.
final class ChatTurnCallbackQueue: @unchecked Sendable {
  private let lock = NSLock()
  private let generation: Int
  private let lifecycle: ChatTurnLifecycle
  private let currentGeneration: @MainActor @Sendable () -> Int
  private var tasks: [Task<Void, Never>] = []

  @MainActor
  init(
    generation: Int,
    lifecycle: ChatTurnLifecycle,
    currentGeneration: @escaping @MainActor @Sendable () -> Int
  ) {
    self.generation = generation
    self.lifecycle = lifecycle
    self.currentGeneration = currentGeneration
  }

  /// Every adapter callback crosses this one admission gate. Keeping the
  /// generation and lifecycle checks here prevents a newly added callback from
  /// accidentally bypassing stop/supersession authority.
  func submit(_ operation: @escaping @MainActor @Sendable () async -> Void) {
    let task = Task { @MainActor in
      guard currentGeneration() == generation, lifecycle.acceptsResult else { return }
      await operation()
    }
    lock.withLock {
      tasks.append(task)
    }
  }

  func drain() async {
    while true {
      let pending = lock.withLock {
        let snapshot = tasks
        tasks.removeAll(keepingCapacity: true)
        return snapshot
      }
      guard !pending.isEmpty else { return }
      for task in pending {
        await task.value
      }
    }
  }
}
