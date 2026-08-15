import Foundation

struct ContextVisitStateMachine: Equatable {
  enum Phase: Equatable {
    case idle
    case active(ContextVisitFence)
  }
  private(set) var phase: Phase = .idle
  private(set) var generation: Int64 = 0

  mutating func begin(_ fence: ContextVisitFence) {
    generation = fence.contextGeneration
    phase = .active(fence)
  }

  mutating func takeActive() -> ContextVisitFence? {
    guard case .active(let fence) = phase else { return nil }
    phase = .idle
    return fence
  }

  mutating func reset() {
    phase = .idle
    generation = 0
  }

  var activeFence: ContextVisitFence? {
    guard case .active(let fence) = phase else { return nil }
    return fence
  }
}

/// Pure gate for sleep/wake and lock/unlock rearm. Extracted so the same-context
/// resume contract is unit-testable without AppKit system events.
enum ContextVisitSystemResumePolicy {
  static func shouldInterrupt(activeVisitStartedAt: Date, eventTime: Date) -> Bool {
    activeVisitStartedAt <= eventTime
  }

  static func shouldRearmContextVisit(
    bucketsEnabled: Bool,
    wasMonitoringBeforeEvent: Bool,
    isMonitoring: Bool,
    appName: String?,
    isAppExcluded: Bool,
    displayAvailable: Bool = true
  ) -> Bool {
    guard bucketsEnabled, wasMonitoringBeforeEvent, isMonitoring, displayAvailable else { return false }
    guard let appName, !appName.isEmpty, !isAppExcluded else { return false }
    return true
  }
}

actor ContextVisitCoordinator {
  static let shared = ContextVisitCoordinator(store: .shared)

  struct Transition: Sendable {
    let departingFence: ContextVisitFence?
    let departingQualified: Bool
    let arrivingFence: ContextVisitFence
  }

  struct Departure: Sendable {
    let fence: ContextVisitFence?
    let qualified: Bool
  }

  private let store: ContextBucketStore
  private var state = ContextVisitStateMachine()
  private var reconciled = false
  private var lastGCAt = Date.distantPast
  private var transitionInFlight = false
  private var transitionWaiters: [CheckedContinuation<Void, Never>] = []
  private var ownerChangeTask: Task<Void, Never>?

  init(store: ContextBucketStore) { self.store = store }

  func transition(
    toApp appName: String,
    windowTitle: String?,
    departingFrame: CapturedFrame?,
    now: Date = Date(),
    handles: [WorkHistoryHandle] = [],
    bundleID: String? = nil
  ) async throws -> Transition {
    let arrivingIdentity = Self.resolvedVisitIdentity(
      appName: appName, windowTitle: windowTitle, handles: handles, bundleID: bundleID)
    ensureOwnerChangeObserver()
    await waitForTransitionTurn()
    defer { releaseTransitionTurn() }
    try await ensureReconciled(now: now)
    if now.timeIntervalSince(lastGCAt) >= 24 * 60 * 60 {
      _ = try await store.reconcileAbandonedDeliveries(now: now)
      try await store.runDeterministicGC(now: now)
      lastGCAt = now
    }
    let departure = try await finalizeActive(
      departingFrame: departingFrame, exitReason: "context_switch", now: now)
    // Finalization can discover that the database pool was replaced while the
    // old visit was active. Reconcile the replacement pool before opening the
    // arriving visit so the abandoned row is not left live indefinitely.
    try await ensureReconciled(now: now)
    let nextGeneration = state.generation + 1
    let arriving = try await store.startVisit(
      appName: appName,
      windowTitle: windowTitle,
      contextGeneration: nextGeneration,
      startedAt: now,
      handles: arrivingIdentity.handles,
      bundleID: arrivingIdentity.bundleID)
    state.begin(arriving)
    return Transition(
      departingFence: departure.fence,
      departingQualified: departure.qualified,
      arrivingFence: arriving)
  }

  func leaveForExcludedContext(
    departingFrame: CapturedFrame?, now: Date = Date()
  ) async throws -> Departure {
    ensureOwnerChangeObserver()
    await waitForTransitionTurn()
    defer { releaseTransitionTurn() }
    return try await finalizeActive(
      departingFrame: departingFrame, exitReason: "excluded_context", now: now)
  }

  func interruptForSleep(now: Date = Date()) async {
    ensureOwnerChangeObserver()
    await waitForTransitionTurn()
    defer { releaseTransitionTurn() }
    guard let active = state.activeFence else { return }
    // The system event is captured before this actor hop. If a wake/unlock
    // already opened a newer visit, the delayed interrupt belongs to the old
    // visit and must not tear down the fresh one.
    guard
      ContextVisitSystemResumePolicy.shouldInterrupt(
        activeVisitStartedAt: active.startedAt, eventTime: now)
    else { return }
    do {
      try await store.finalizeVisit(
        active, outcome: "interrupted", exitReason: "system_sleep", lastScreenshotID: nil, endedAt: now)
      _ = state.takeActive()
    } catch {
      // A pool/owner retarget invalidates the fence epoch. Drop the in-memory
      // fence so the next wake rearm or transition can start cleanly instead of
      // permanently failing on the stale generation.
      if case ContextBucketStoreError.staleFence = error {
        _ = state.takeActive()
        reconciled = false
      }
      logError("ContextVisitCoordinator: sleep finalization failed", error: error)
    }
  }

  /// Sleep/lock clears the active visit; wake/unlock must open a fresh visit for
  /// the still-frontmost context even when app/title did not change.
  @discardableResult
  func rearmAfterSystemResume(
    appName: String,
    windowTitle: String?,
    now: Date = Date(),
    handles: [WorkHistoryHandle] = [],
    bundleID: String? = nil
  ) async throws -> ContextVisitFence {
    let arrivingIdentity = Self.resolvedVisitIdentity(
      appName: appName, windowTitle: windowTitle, handles: handles, bundleID: bundleID)
    ensureOwnerChangeObserver()
    await waitForTransitionTurn()
    defer { releaseTransitionTurn() }
    try await ensureReconciled(now: now)
    if state.activeFence != nil {
      do {
        _ = try await finalizeActive(
          departingFrame: nil, exitReason: "system_resume", now: now)
      } catch {
        if case ContextBucketStoreError.staleFence = error {
          _ = state.takeActive()
          reconciled = false
        } else {
          throw error
        }
      }
    }
    try await ensureReconciled(now: now)
    let nextGeneration = state.generation + 1
    let arriving = try await store.startVisit(
      appName: appName,
      windowTitle: windowTitle,
      contextGeneration: nextGeneration,
      startedAt: now,
      handles: arrivingIdentity.handles,
      bundleID: arrivingIdentity.bundleID)
    state.begin(arriving)
    return arriving
  }

  /// Drop any in-memory visit tied to a closed pool/owner. The next transition
  /// re-reconciles against the new database generation.
  func resetForOwnerOrPoolChange() async {
    await waitForTransitionTurn()
    defer { releaseTransitionTurn() }
    state.reset()
    reconciled = false
  }

  func activeFenceForTesting() -> ContextVisitFence? { state.activeFence }

  func beginForTesting(_ fence: ContextVisitFence) {
    state.begin(fence)
  }

  private static func resolvedVisitIdentity(
    appName: String,
    windowTitle: String?,
    handles: [WorkHistoryHandle],
    bundleID: String?
  ) -> (handles: [WorkHistoryHandle], bundleID: String?) {
    if !handles.isEmpty {
      return (handles, bundleID)
    }
    let snapshot = WorkHistoryHandleExtractor.liveSnapshot(appName: appName, windowTitle: windowTitle)
    return (WorkHistoryHandleExtractor.handles(from: snapshot), snapshot.bundleID)
  }

  private func finalizeActive(
    departingFrame: CapturedFrame?, exitReason: String, now: Date
  ) async throws -> Departure {
    guard let departing = state.activeFence else {
      return Departure(fence: nil, qualified: false)
    }
    let qualified = now.timeIntervalSince(departing.startedAt) >= 1
    do {
      try await store.finalizeVisit(
        departing,
        outcome: qualified ? "completed" : "discarded",
        exitReason: exitReason,
        lastScreenshotID: departingFrame?.screenshotId,
        endedAt: now)
      _ = state.takeActive()
      return Departure(fence: departing, qualified: qualified)
    } catch {
      if case ContextBucketStoreError.staleFence = error {
        _ = state.takeActive()
        reconciled = false
        return Departure(fence: nil, qualified: false)
      }
      throw error
    }
  }

  private func ensureReconciled(now: Date) async throws {
    guard !reconciled else { return }
    _ = try await store.reconcileInterruptedVisits(now: now)
    _ = try await store.reconcileAbandonedDeliveries(now: now)
    try await store.runDeterministicGC(now: now)
    lastGCAt = now
    reconciled = true
  }

  private func ensureOwnerChangeObserver() {
    guard ownerChangeTask == nil else { return }
    ownerChangeTask = Task { [weak self] in
      for await _ in NotificationCenter.default.notifications(named: .runtimeOwnerDidChange) {
        guard !Task.isCancelled, let self else { return }
        await self.resetForOwnerOrPoolChange()
      }
    }
  }

  private func waitForTransitionTurn() async {
    guard transitionInFlight else {
      transitionInFlight = true
      return
    }
    await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
      transitionWaiters.append(continuation)
    }
  }

  private func releaseTransitionTurn() {
    if transitionWaiters.isEmpty {
      transitionInFlight = false
    } else {
      transitionWaiters.removeFirst().resume()
    }
  }

  @MainActor static func interruptForSleepIfEnabled() {
    guard ContextBucketsFeature.isEnabled else { return }
    let eventTime = Date()
    Task { await ContextVisitCoordinator.shared.interruptForSleep(now: eventTime) }
  }
}
