import Foundation

enum LocalMutationAuthorizationError: Error, Equatable {
  case revoked
}

/// Serializes effective-owner transitions against owner-bound local commits.
///
/// A transition reserves the fence as soon as it arrives, so later mutations
/// cannot starve it. Mutation leases do not hold a thread-owned lock while an
/// async database write is running; the actor only tracks their identities.
/// This also lets MainActor auth/automation transitions suspend instead of
/// blocking the main thread while SQLite finishes a physical commit.
actor EffectiveOwnerTransitionFence {
  struct MutationLease: Sendable {
    fileprivate let id: UUID
  }

  static let shared = EffectiveOwnerTransitionFence()

  private var activeMutationLeaseIDs: Set<UUID> = []
  private var transitionActive = false
  private var transitionWaiters: [CheckedContinuation<Void, Never>] = []
  private var mutationWaiters: [CheckedContinuation<Void, Never>] = []
  private var pendingTransitionObservers: [CheckedContinuation<Void, Never>] = []
  private var pendingMutationObservers: [CheckedContinuation<Void, Never>] = []

  func acquireMutationLease(
    validating validator: @Sendable () -> Bool
  ) async throws -> MutationLease {
    while transitionActive || !transitionWaiters.isEmpty {
      await withCheckedContinuation { continuation in
        mutationWaiters.append(continuation)
        let observers = pendingMutationObservers
        pendingMutationObservers.removeAll()
        observers.forEach { $0.resume() }
      }
    }

    guard validator() else { throw LocalMutationAuthorizationError.revoked }
    let lease = MutationLease(id: UUID())
    activeMutationLeaseIDs.insert(lease.id)
    return lease
  }

  func releaseMutationLease(_ lease: MutationLease) {
    guard activeMutationLeaseIDs.remove(lease.id) != nil else { return }
    admitNextTransitionIfPossible()
  }

  /// Perform an effective-owner mutation and deliver its cache-invalidation
  /// signal before admitting work for the new owner.
  func performEffectiveOwnerTransition<T: Sendable>(
    currentOwner: @Sendable () -> String?,
    plannedNextOwner: @Sendable (_ previousOwner: String?) -> String?,
    beginAuthorizationRevocation: @Sendable (_ previousOwner: String?) -> Void = { _ in },
    endAuthorizationRevocation: @Sendable () -> Void = {},
    quiescePreviousOwner: @Sendable (
      _ previousOwner: String?, _ plannedNextOwner: String?
    ) async -> Void,
    transition: @Sendable () async throws -> T,
    retargetLocalStorage: @Sendable (_ previousOwner: String?, _ nextOwner: String?) async -> Void,
    ownerDidChange: @Sendable () async -> Void
  ) async rethrows -> T {
    await beginTransition()
    var authorizationRevoked = false
    do {
      let previousOwner = currentOwner()
      let plannedOwner = plannedNextOwner(previousOwner)
      // Voice capture/provider transports are physical authorities, not cache
      // projections. Drain the previous owner's authority while defaults still
      // resolve to that owner. The transition reservation keeps new local
      // mutation leases parked across every suspension in this phase.
      if previousOwner != plannedOwner {
        beginAuthorizationRevocation(previousOwner)
        authorizationRevoked = true
        await quiescePreviousOwner(previousOwner, plannedOwner)
      }
      let result = try await transition()
      let nextOwner = currentOwner()
      // The pool boundary is part of the owner transition, not an eventual
      // observer side effect. New-owner mutation leases stay parked until the
      // old pool is closed and the next target is configured.
      await retargetLocalStorage(previousOwner, nextOwner)
      if previousOwner != nextOwner {
        await ownerDidChange()
      }
      // Owner-derived projections clear synchronously from the notification
      // while neither A nor B is authorized. Expose B only after those callbacks
      // return, then release parked mutation leases in `endTransition()`.
      if authorizationRevoked {
        endAuthorizationRevocation()
        authorizationRevoked = false
      }
      endTransition()
      return result
    } catch {
      if authorizationRevoked {
        endAuthorizationRevocation()
      }
      endTransition()
      throw error
    }
  }

  /// Deterministic concurrency seam used by behavioral tests. Returning means
  /// an exclusive owner transition is queued behind at least one active commit
  /// lease; no wall-clock polling is needed.
  func waitUntilTransitionIsPending() async {
    guard transitionWaiters.isEmpty else { return }
    await withCheckedContinuation { continuation in
      pendingTransitionObservers.append(continuation)
    }
  }

  /// Deterministic concurrency seam used by behavioral tests. Returning means
  /// at least one mutation is parked behind the exclusive transition phase.
  func waitUntilMutationIsPending() async {
    guard mutationWaiters.isEmpty else { return }
    await withCheckedContinuation { continuation in
      pendingMutationObservers.append(continuation)
    }
  }

  private func beginTransition() async {
    if !transitionActive && activeMutationLeaseIDs.isEmpty {
      transitionActive = true
      return
    }

    await withCheckedContinuation { continuation in
      transitionWaiters.append(continuation)
      let observers = pendingTransitionObservers
      pendingTransitionObservers.removeAll()
      observers.forEach { $0.resume() }
    }
  }

  private func endTransition() {
    if !transitionWaiters.isEmpty {
      // Keep the transition reservation active while handing it to the next
      // owner change; mutations remain parked until the transition queue drains.
      transitionWaiters.removeFirst().resume()
      return
    }

    transitionActive = false
    let waiters = mutationWaiters
    mutationWaiters.removeAll()
    waiters.forEach { $0.resume() }
  }

  private func admitNextTransitionIfPossible() {
    guard activeMutationLeaseIDs.isEmpty, !transitionActive, !transitionWaiters.isEmpty else {
      return
    }
    transitionActive = true
    transitionWaiters.removeFirst().resume()
  }
}

/// A capability fence that is re-evaluated inside the actual storage
/// transaction, after actor/queue scheduling. Callers may preflight for fast
/// failure, but only `require()` at the mutation boundary authorizes a write.
struct LocalMutationAuthorization: Sendable {
  private let validator: @Sendable () -> Bool

  static let unrestricted = LocalMutationAuthorization { true }

  init(_ validator: @escaping @Sendable () -> Bool) {
    self.validator = validator
  }

  func require() throws {
    guard validator() else { throw LocalMutationAuthorizationError.revoked }
  }

  /// Hold an effective-owner lease through the complete awaited operation.
  /// For GRDB writes this means the lease remains active after the transaction
  /// closure returns and until GRDB has committed or rolled back on disk.
  func withCommitLease<T: Sendable>(
    _ operation: @escaping @Sendable () async throws -> T
  ) async throws -> T {
    let fence = EffectiveOwnerTransitionFence.shared
    let lease = try await fence.acquireMutationLease(validating: validator)
    do {
      let result = try await operation()
      await fence.releaseMutationLease(lease)
      return result
    } catch {
      await fence.releaseMutationLease(lease)
      throw error
    }
  }
}
