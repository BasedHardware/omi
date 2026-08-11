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

  init(store: ContextBucketStore) { self.store = store }

  func transition(
    toApp appName: String,
    windowTitle: String?,
    departingFrame: CapturedFrame?,
    now: Date = Date()
  ) async throws -> Transition {
    if !reconciled {
      _ = try await store.reconcileInterruptedVisits(now: now)
      try await store.runDeterministicGC(now: now)
      lastGCAt = now
      reconciled = true
    }
    if now.timeIntervalSince(lastGCAt) >= 24 * 60 * 60 {
      try await store.runDeterministicGC(now: now)
      lastGCAt = now
    }
    let departure = try await finalizeActive(
      departingFrame: departingFrame, exitReason: "context_switch", now: now)
    let nextGeneration = state.generation + 1
    let arriving = try await store.startVisit(
      appName: appName,
      windowTitle: windowTitle,
      contextGeneration: nextGeneration,
      startedAt: now)
    state.begin(arriving)
    return Transition(
      departingFence: departure.fence,
      departingQualified: departure.qualified,
      arrivingFence: arriving)
  }

  func leaveForExcludedContext(
    departingFrame: CapturedFrame?, now: Date = Date()
  ) async throws -> Departure {
    try await finalizeActive(
      departingFrame: departingFrame, exitReason: "excluded_context", now: now)
  }

  func interruptForSleep(now: Date = Date()) async {
    guard let active = state.takeActive() else { return }
    do {
      try await store.finalizeVisit(
        active, outcome: "interrupted", exitReason: "system_sleep", lastScreenshotID: nil, endedAt: now)
    } catch {
      logError("ContextVisitCoordinator: sleep finalization failed", error: error)
    }
  }

  private func finalizeActive(
    departingFrame: CapturedFrame?, exitReason: String, now: Date
  ) async throws -> Departure {
    guard let departing = state.takeActive() else {
      return Departure(fence: nil, qualified: false)
    }
    let qualified = now.timeIntervalSince(departing.startedAt) >= 1
    try await store.finalizeVisit(
      departing,
      outcome: qualified ? "completed" : "discarded",
      exitReason: exitReason,
      lastScreenshotID: departingFrame?.screenshotId,
      endedAt: now)
    return Departure(fence: departing, qualified: qualified)
  }

  @MainActor static func interruptForSleepIfEnabled() {
    guard ContextBucketsFeature.isEnabled else { return }
    Task { await ContextVisitCoordinator.shared.interruptForSleep() }
  }
}
