import Foundation

/// Event-driven service that promotes top-ranked staged tasks to action_items.
/// Fires when a user completes/deletes a task, on app startup, and on a 5-minute safety-net timer.
/// Purely programmatic — no AI calls. One task at a time via the backend promote endpoint.
actor TaskPromotionService {
  static let shared = TaskPromotionService()

  struct Operations {
    let legacyPromotionEnabled:
      @Sendable (
        _ authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
      ) async -> Bool
    let promote:
      @Sendable (
        _ authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
      ) async throws -> PromoteResponse?
    let insertLocal:
      @Sendable (
        _ record: ActionItemRecord,
        _ authorization: LocalMutationAuthorization
      ) async throws -> Void

    static let live = Operations(
      legacyPromotionEnabled: { authorizationSnapshot in
        do {
          let control = try await APIClient.shared.getCandidateWorkflowControl(
            expectedOwnerId: authorizationSnapshot.ownerID,
            authorizationSnapshot: authorizationSnapshot
          )
          return TaskCaptureModePolicy.allowsLegacyPromotion(control.workflowMode)
        } catch {
          guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
            return false
          }
          DesktopDiagnosticsManager.shared.recordFallback(
            area: "other",
            from: "workflow_control",
            to: "promotion_disabled",
            reason: "other",
            outcome: .degraded
          )
          return false
        }
      },
      promote: { authorizationSnapshot in
        let gate = TaskLegacyEffectGate {
          let control = try? await APIClient.shared.getCandidateWorkflowControl(
            expectedOwnerId: authorizationSnapshot.ownerID,
            authorizationSnapshot: authorizationSnapshot
          )
          return control?.workflowMode
        }
        return try await gate.perform(.promotion) {
          try await APIClient.shared.promoteTopStagedTask(
            expectedOwnerId: authorizationSnapshot.ownerID,
            authorizationSnapshot: authorizationSnapshot
          )
        }
      },
      insertLocal: { record, authorization in
        _ = try await ActionItemStorage.shared.insertLocalActionItem(
          record,
          authorization: authorization
        )
      }
    )
  }

  private struct OwnerLease: Equatable, Sendable {
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    var ownerID: String { authorizationSnapshot.ownerID }
  }

  private let promotionDebounceInterval: TimeInterval = 30
  private let operations: Operations
  private let ownerIDProvider: @Sendable () -> String?
  private var safetyTimer: Task<Void, Never>?
  private var ownerChangeTask: Task<Void, Never>?
  private var promotionLease: OwnerLease?
  private var activeOwnerLease: OwnerLease?
  private var lastPromotedAt = Date.distantPast

  init(
    operations: Operations = .live,
    ownerIDProvider: @escaping @Sendable () -> String? = {
      RuntimeOwnerIdentity.currentOwnerId()
    }
  ) {
    self.operations = operations
    self.ownerIDProvider = ownerIDProvider
  }

  // MARK: - Lifecycle

  /// Promote any pending staged tasks immediately on service start, then keep a
  /// short safety-net ticking to catch anything that slips through event-driven paths.
  func start() {
    ensureOwnerChangeObserver()
    Task { [weak self] in
      guard let self else { return }
      await self.startLegacyPromotion()
    }
  }

  private func startLegacyPromotion() async {
    startSafetyTimer()
    log("TaskPromotion: Legacy compatibility service started")
    await promoteIfNeeded()
  }

  func stop() {
    safetyTimer?.cancel()
    safetyTimer = nil
    ownerChangeTask?.cancel()
    ownerChangeTask = nil
    promotionLease = nil
    activeOwnerLease = nil
    lastPromotedAt = .distantPast
    log("TaskPromotion: Service stopped")
  }

  private func ensureOwnerChangeObserver() {
    guard ownerChangeTask == nil else { return }
    ownerChangeTask = Task { [weak self] in
      for await _ in NotificationCenter.default.notifications(named: .runtimeOwnerDidChange) {
        guard !Task.isCancelled, let self else { return }
        await self.handleOwnerChangeNotification()
      }
    }
  }

  private func handleOwnerChangeNotification() {
    if let activeOwnerLease,
      RuntimeOwnerIdentity.captureAuthorizationSnapshot()
        == activeOwnerLease.authorizationSnapshot,
      isCurrent(activeOwnerLease)
    {
      return
    }
    resetOwnerState()
  }

  func processOwnerChangeNotificationForTesting() {
    handleOwnerChangeNotification()
  }

  private func resetOwnerState() {
    promotionLease = nil
    activeOwnerLease = nil
    lastPromotedAt = .distantPast
  }

  private func captureOwnerLease(
    expectedOwnerID: String?,
    authorizationSnapshot suppliedAuthorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) -> OwnerLease? {
    if let suppliedAuthorizationSnapshot {
      if let expectedOwnerID {
        let normalizedExpectedOwnerID =
          expectedOwnerID
          .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalizedExpectedOwnerID.isEmpty,
          normalizedExpectedOwnerID == suppliedAuthorizationSnapshot.ownerID
        else {
          return nil
        }
      }
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(suppliedAuthorizationSnapshot) else {
        return nil
      }
      if let activeOwnerLease,
        !RuntimeOwnerIdentity.isAuthorizationCurrent(
          activeOwnerLease.authorizationSnapshot
        )
      {
        resetOwnerState()
      }
      let lease = OwnerLease(authorizationSnapshot: suppliedAuthorizationSnapshot)
      activeOwnerLease = lease
      return lease
    }
    let requestedOwner = expectedOwnerID ?? ownerIDProvider()
    guard
      let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
        expectedOwnerID: requestedOwner
      )
    else { return nil }
    let lease = OwnerLease(authorizationSnapshot: snapshot)
    if let activeOwnerLease,
      !RuntimeOwnerIdentity.isAuthorizationCurrent(activeOwnerLease.authorizationSnapshot)
    {
      resetOwnerState()
    }
    activeOwnerLease = lease
    return lease
  }

  private func isCurrent(_ lease: OwnerLease) -> Bool {
    RuntimeOwnerIdentity.isAuthorizationCurrent(lease.authorizationSnapshot)
      && !Task.isCancelled
  }

  private func startSafetyTimer() {
    safetyTimer?.cancel()
    safetyTimer = Task { [weak self] in
      while !Task.isCancelled {
        try? await Task.sleep(nanoseconds: 60 * 1_000_000_000)  // 60 seconds
        guard !Task.isCancelled else { break }
        guard let self = self else { break }
        log("TaskPromotion: Safety-net timer fired")
        await self.promoteIfNeeded(bypassDebounce: true)
      }
    }
  }

  // MARK: - Promotion

  /// Event-driven: called after task complete/delete, and on app startup.
  /// Loops calling the backend promote endpoint until it returns promoted=false
  /// (either cap reached or no staged tasks available).
  /// Returns the list of promoted tasks so callers can insert them directly.
  @discardableResult
  func promoteIfNeeded(
    bypassDebounce: Bool = false,
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async -> [TaskActionItem] {
    ensureOwnerChangeObserver()
    guard
      let lease = captureOwnerLease(
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return [] }
    guard await operations.legacyPromotionEnabled(lease.authorizationSnapshot) else { return [] }
    guard isCurrent(lease) else { return [] }
    guard promotionLease == nil else {
      log("TaskPromotion: Already promoting, skipping")
      return []
    }
    let secondsSinceLastPromotion = Date().timeIntervalSince(lastPromotedAt)
    guard bypassDebounce || secondsSinceLastPromotion >= promotionDebounceInterval else {
      log("TaskPromotion: Debounced — promoted \(Int(secondsSinceLastPromotion))s ago")
      return []
    }
    promotionLease = lease
    defer {
      if promotionLease == lease {
        promotionLease = nil
      }
    }

    var promotedTasks: [TaskActionItem] = []
    // Promote at most one task per trigger. The safety timer plus explicit
    // task lifecycle events naturally fill the compatibility list quietly.
    let maxIterations = 1

    for _ in 0..<maxIterations {
      do {
        guard let response = try await operations.promote(lease.authorizationSnapshot) else {
          log("TaskPromotion: Mode changed; stopping before promotion write")
          break
        }

        guard isCurrent(lease) else { return [] }
        if response.promoted, let promotedTask = response.promotedTask {
          // Sync promoted task to local ActionItemStorage
          do {
            let record = ActionItemRecord.from(promotedTask)
            guard isCurrent(lease) else { return [] }
            try await operations.insertLocal(
              record,
              LocalMutationAuthorization {
                RuntimeOwnerIdentity.isAuthorizationCurrent(
                  lease.authorizationSnapshot
                )
              }
            )
            guard isCurrent(lease) else { return [] }
            log("TaskPromotion: Synced promoted task to local ActionItemStorage")
          } catch {
            guard isCurrent(lease) else { return [] }
            log("TaskPromotion: Failed to sync promoted task locally: \(error)")
          }

          guard isCurrent(lease) else { return [] }
          lastPromotedAt = Date()
          promotedTasks.append(promotedTask)
          log("TaskPromotion: Promoted task \(promotedTask.id) — \"\(promotedTask.description.prefix(60))\"")

        } else {
          let reason = response.reason ?? "cap reached or no staged tasks"
          log("TaskPromotion: No more promotions — \(reason)")
          break
        }
      } catch {
        guard isCurrent(lease) else { return [] }
        log("TaskPromotion: Promote API call failed: \(error)")
        break
      }
    }

    if !promotedTasks.isEmpty, isCurrent(lease) {
      let count = promotedTasks.count
      log("TaskPromotion: Promoted \(count) tasks total")
      await MainActor.run {
        AnalyticsManager.shared.taskPromoted(taskCount: count)
      }
    }
    return isCurrent(lease) ? promotedTasks : []
  }
}
