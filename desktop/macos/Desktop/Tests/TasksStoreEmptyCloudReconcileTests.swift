import XCTest

@testable import Omi_Computer

/// Regression coverage for the empty-cloud reconcile contract: an account whose
/// incomplete tasks were all completed/deleted on another device must converge
/// to an empty desktop list, but a bogus empty `completed=false` page must never
/// wipe local rows on its own say-so. The empty page only triggers a
/// reconciliation against the independent ID census: census-absent rows are
/// proven gone and hard-deleted; census-present rows are resolved through
/// authoritative per-document reads; a failed census fetch skips everything.
@MainActor
private final class EmptyCloudReconcileProbe {
  var hardDeleteCalls: [Set<String>] = []
  var censusFetches = 0
  var detailFetches: [String] = []
  var visibilityReconciles: [[String]] = []
  var dashboardRefreshes = 0
  /// 0 = pristine cache, bumped after each mutation so loadIncomplete can serve
  /// the cache state the production SQLite would hold at that point.
  var cacheStage = 0
}

final class TasksStoreEmptyCloudReconcileTests: XCTestCase {

  // MARK: - Initial-load reconcile (forceReconcileOnLoad)

  @MainActor
  func testInitialLoadWipesAllStaleSyncedRowsWhenCensusConfirmsAccountHasNoTasks() async {
    let store = TasksStore.shared
    await prepareStore(store)

    let staleTask = task(id: "stale-hard-deleted-on-mobile")
    let probe = EmptyCloudReconcileProbe()
    let operations = TasksStore.OwnerBoundOperations(
      fetchPage: { completed, _, _, _ in
        XCTAssertFalse(completed)
        return .init(items: [], hasMore: false)
      },
      fetchAllTaskIds: { _ in
        probe.censusFetches += 1
        return []
      },
      syncPage: { _, _, _ in },
      hardDeleteAbsent: { ids, _ in
        probe.hardDeleteCalls.append(ids)
        probe.cacheStage += 1
        return 1
      },
      loadIncomplete: { _ in probe.cacheStage == 0 ? [staleTask] : [] },
      refreshDashboard: { _ in probe.dashboardRefreshes += 1 })

    await store.loadIncompleteTasks(operations: operations)

    XCTAssertEqual(probe.censusFetches, 1, "empty cloud page must be checked against the ID census")
    XCTAssertEqual(probe.hardDeleteCalls, [[]], "empty census authorizes the confirmed-empty wipe")
    XCTAssertEqual(probe.detailFetches, [], "no documents exist, so nothing to resolve per-document")
    XCTAssertEqual(store.incompleteTasks, [], "stale local tasks must converge to the empty cloud state")
    XCTAssertEqual(probe.dashboardRefreshes, 1, "dashboard slices must refresh after the wipe")
    XCTAssertNil(store.error)

    let fallback = try? latestFallbackSnapshot()
    XCTAssertEqual(fallback?["area"] as? String, "task_reconcile", "census heal must emit fallback telemetry")
    XCTAssertEqual(fallback?["outcome"] as? String, "recovered")
    XCTAssertEqual(fallback?["to"] as? String, "id_census")
  }

  @MainActor
  func testInitialLoadResolvesStaleRowsAgainstNonEmptyCensusWithoutBlindDeletion() async {
    let store = TasksStore.shared
    await prepareStore(store)

    // Document gone from the cloud entirely (hard-deleted on mobile).
    let absentTask = task(id: "absent-from-census")
    // Document still exists but was completed on mobile; the stale local row
    // must be flipped by an authoritative read, never deleted on the empty
    // page's word.
    let presentTask = task(id: "present-in-census")
    let probe = EmptyCloudReconcileProbe()
    let operations = TasksStore.OwnerBoundOperations(
      fetchPage: { _, _, _, _ in .init(items: [], hasMore: false) },
      fetchAllTaskIds: { _ in
        probe.censusFetches += 1
        return [presentTask.id, "unrelated-completed-doc"]
      },
      fetchTaskDetail: { id, _ in
        probe.detailFetches.append(id)
        return self.task(id: id, completed: true)
      },
      reconcileVisibility: { items, _ in
        probe.visibilityReconciles.append(items.map(\.id))
        XCTAssertTrue(
          items.allSatisfy(\.completed),
          "per-document resolution must carry the authoritative completed state")
        probe.cacheStage = 2
        return items.count
      },
      syncPage: { _, _, _ in },
      hardDeleteAbsent: { ids, _ in
        probe.hardDeleteCalls.append(ids)
        probe.cacheStage = 1
        return 1
      },
      loadIncomplete: { _ in
        switch probe.cacheStage {
        case 0: return [absentTask, presentTask]
        case 1: return [presentTask]
        default: return []
        }
      },
      refreshDashboard: { _ in probe.dashboardRefreshes += 1 })

    await store.loadIncompleteTasks(operations: operations)

    XCTAssertEqual(probe.censusFetches, 1)
    XCTAssertEqual(
      probe.hardDeleteCalls, [Set([presentTask.id, "unrelated-completed-doc"])],
      "deletion must run against the census so only proven-absent rows are removed")
    XCTAssertEqual(
      probe.detailFetches, [presentTask.id],
      "census-present stale rows are resolved per-document, not deleted")
    XCTAssertEqual(probe.visibilityReconciles, [[presentTask.id]])
    XCTAssertEqual(store.incompleteTasks, [], "both stale rows converge: one wiped, one flipped")
    XCTAssertNil(store.error)
  }

  @MainActor
  func testInitialLoadResolvesMoreThanOnePageOfCensusPresentStaleRowsInOnePass() async {
    let store = TasksStore.shared
    await prepareStore(store)

    // More rows than TasksStore.pageSize (100) so a single-page resolution
    // would strand the tail; the reconcile must drain the whole set in one pass.
    let staleTasks = (0..<105).map { task(id: "census-present-\($0)") }
    let staleIds = Set(staleTasks.map(\.id))
    let probe = EmptyCloudReconcileProbe()
    let operations = TasksStore.OwnerBoundOperations(
      fetchPage: { _, _, _, _ in .init(items: [], hasMore: false) },
      fetchAllTaskIds: { _ in
        probe.censusFetches += 1
        return staleTasks.map(\.id)
      },
      fetchTaskDetail: { id, _ in
        probe.detailFetches.append(id)
        return self.task(id: id, completed: true)
      },
      reconcileVisibility: { items, _ in
        probe.visibilityReconciles.append(items.map(\.id))
        probe.cacheStage = 2
        return items.count
      },
      syncPage: { _, _, _ in },
      hardDeleteAbsent: { ids, _ in
        probe.hardDeleteCalls.append(ids)
        if probe.cacheStage == 0 { probe.cacheStage = 1 }
        return 0
      },
      loadIncomplete: { _ in probe.cacheStage == 2 ? [] : staleTasks },
      refreshDashboard: { _ in })

    await store.loadIncompleteTasks(operations: operations)

    XCTAssertEqual(probe.hardDeleteCalls, [staleIds])
    XCTAssertEqual(
      Set(probe.detailFetches), staleIds,
      "every census-present stale row must be resolved in the same pass, not just the first page")
    XCTAssertEqual(probe.detailFetches.count, staleTasks.count, "each document is read exactly once")
    XCTAssertEqual(probe.visibilityReconciles.flatMap { $0 }.count, staleTasks.count)
    XCTAssertEqual(store.incompleteTasks, [], "the full stale set converges in one reconcile pass")
    XCTAssertNil(store.error)
  }

  @MainActor
  func testInitialLoadKeepsLocalTasksWhenCensusFetchFails() async {
    let store = TasksStore.shared
    await prepareStore(store)

    let staleTask = task(id: "stale-but-unconfirmed")
    let probe = EmptyCloudReconcileProbe()
    let operations = TasksStore.OwnerBoundOperations(
      fetchPage: { _, _, _, _ in .init(items: [], hasMore: false) },
      fetchAllTaskIds: { _ in
        probe.censusFetches += 1
        throw URLError(.badServerResponse)
      },
      syncPage: { _, _, _ in },
      hardDeleteAbsent: { ids, _ in
        probe.hardDeleteCalls.append(ids)
        return 1
      },
      loadIncomplete: { _ in [staleTask] },
      refreshDashboard: { _ in })

    await store.loadIncompleteTasks(operations: operations)

    XCTAssertEqual(probe.censusFetches, 1)
    XCTAssertEqual(probe.hardDeleteCalls, [], "a failed census fetch must never wipe local rows")
    XCTAssertEqual(store.incompleteTasks.map(\.id), [staleTask.id], "stale rows stay until the census confirms")
    XCTAssertNil(store.error)

    let fallback = try? latestFallbackSnapshot()
    XCTAssertEqual(fallback?["area"] as? String, "task_reconcile", "fail-open skip must emit degraded telemetry")
    XCTAssertEqual(fallback?["outcome"] as? String, "degraded")
    XCTAssertEqual(fallback?["to"] as? String, "none")
  }

  @MainActor
  func testInitialLoadSkipsCensusWhenLocalCacheAlreadyEmpty() async {
    let store = TasksStore.shared
    await prepareStore(store)

    let probe = EmptyCloudReconcileProbe()
    let operations = TasksStore.OwnerBoundOperations(
      fetchPage: { _, _, _, _ in .init(items: [], hasMore: false) },
      fetchAllTaskIds: { _ in
        probe.censusFetches += 1
        return []
      },
      syncPage: { _, _, _ in },
      hardDeleteAbsent: { ids, _ in
        probe.hardDeleteCalls.append(ids)
        return 0
      },
      loadIncomplete: { _ in [] },
      refreshDashboard: { _ in })

    await store.loadIncompleteTasks(operations: operations)

    XCTAssertEqual(probe.censusFetches, 0, "nothing to reconcile — no census round-trip")
    XCTAssertEqual(probe.hardDeleteCalls, [])
    XCTAssertEqual(store.incompleteTasks, [])
  }

  // MARK: - Auto-refresh reconcile (refreshTasksIfNeeded)

  @MainActor
  func testAutoRefreshConvergesStaleListWhenCloudEmptiedElsewhere() async {
    let previousSignedIn = AuthService.shared.isSignedIn
    let store = TasksStore.shared
    defer {
      store.isActive = false
      AuthService.shared.isSignedIn = previousSignedIn
    }
    await prepareStore(store)
    AuthService.shared.isSignedIn = true
    // Activate before the first load: the didSet refresh-spawn is gated on
    // hasLoadedIncomplete, so this cannot fire a default-operations refresh.
    store.isActive = false
    store.isActive = true

    // Seed the store with one live task so the follow-up refresh models
    // "everything was completed on mobile after the desktop loaded".
    let liveTask = task(id: "live-task")
    let initialOperations = TasksStore.OwnerBoundOperations(
      fetchPage: { _, _, _, _ in .init(items: [liveTask], hasMore: false) },
      fetchAllTaskIds: { _ in [liveTask.id] },
      syncPage: { _, _, _ in },
      hardDeleteAbsent: { _, _ in 0 },
      loadIncomplete: { _ in [liveTask] },
      refreshDashboard: { _ in })
    await store.loadIncompleteTasks(operations: initialOperations)
    XCTAssertEqual(store.incompleteTasks.map(\.id), [liveTask.id])

    let probe = EmptyCloudReconcileProbe()
    let refreshOperations = TasksStore.OwnerBoundOperations(
      fetchPage: { _, _, _, _ in .init(items: [], hasMore: false) },
      fetchAllTaskIds: { _ in
        probe.censusFetches += 1
        return []
      },
      syncPage: { _, _, _ in },
      hardDeleteAbsent: { ids, _ in
        probe.hardDeleteCalls.append(ids)
        probe.cacheStage += 1
        return 1
      },
      loadIncomplete: { _ in probe.cacheStage == 0 ? [liveTask] : [] },
      loadDeleted: { _ in [] },
      refreshDashboard: { _ in })

    await store.refreshTasksIfNeeded(operations: refreshOperations)

    XCTAssertEqual(probe.censusFetches, 1)
    XCTAssertEqual(probe.hardDeleteCalls, [[]])
    XCTAssertEqual(store.incompleteTasks, [], "auto-refresh must converge a stale list to the empty cloud state")
    XCTAssertNil(store.error)
  }

  // MARK: - Storage layer

  func testHardDeleteAbsentTasksWithConfirmedEmptyWipesOnlySyncedRows() async throws {
    let fixture = try await RewindStorageTestIsolation.setUp(
      userIdPrefix: "empty-cloud-reconcile-test")
    addTeardownBlock {
      await RewindStorageTestIsolation.tearDown(userDir: fixture.userDir)
    }

    // One synced stale row (exists locally, gone from the cloud) and one
    // locally-created row that has not been pushed yet.
    try await ActionItemStorage.shared.syncTaskActionItems(
      [
        TaskActionItem(
          id: "synced-stale",
          description: "completed on mobile long ago",
          completed: false,
          createdAt: Date(timeIntervalSince1970: 0))
      ],
      authorization: .unrestricted)
    _ = try await ActionItemStorage.shared.insertLocalActionItem(
      ActionItemRecord(description: "created offline, not pushed"),
      authorization: .unrestricted)

    // Default (unconfirmed) empty set stays fail-closed.
    let unconfirmed = try await ActionItemStorage.shared.hardDeleteAbsentTasks(
      apiIds: [],
      authorization: .unrestricted)
    XCTAssertEqual(unconfirmed, 0, "unconfirmed empty API set must not delete anything")

    let deleted = try await ActionItemStorage.shared.hardDeleteAbsentTasks(
      apiIds: [],
      authorization: .unrestricted,
      confirmedEmpty: true)
    XCTAssertEqual(deleted, 1, "confirmed-empty wipe removes exactly the synced stale row")

    let remaining = try await ActionItemStorage.shared.getLocalActionItems(
      limit: 10,
      offset: 0,
      completed: false)
    XCTAssertEqual(
      remaining.map(\.description), ["created offline, not pushed"],
      "locally-created unsynced rows must survive a confirmed-empty wipe")
  }

  func testVisibilityReconcileDerivesDeletionFromCancelledStatusOnlyWhenOptedIn() async throws {
    let fixture = try await RewindStorageTestIsolation.setUp(
      userIdPrefix: "cancelled-status-reconcile-test")
    addTeardownBlock {
      await RewindStorageTestIsolation.tearDown(userDir: fixture.userDir)
    }

    try await ActionItemStorage.shared.syncTaskActionItems(
      [
        TaskActionItem(
          id: "soft-deleted-in-cloud",
          description: "retired by the backend",
          completed: false,
          createdAt: Date(timeIntervalSince1970: 0))
      ],
      authorization: .unrestricted)

    // The wire model has no `deleted` field for list/detail reads; soft
    // deletion arrives as status=cancelled.
    let cancelledWireItem = TaskActionItem(
      id: "soft-deleted-in-cloud",
      description: "retired by the backend",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 0),
      taskStatus: "cancelled")

    let withoutOptIn = try await ActionItemStorage.shared.reconcileDashboardVisibilityFields(
      [cancelledWireItem],
      authorization: .unrestricted)
    XCTAssertEqual(withoutOptIn, 0, "default callers keep the existing no-derivation semantics")

    let withOptIn = try await ActionItemStorage.shared.reconcileDashboardVisibilityFields(
      [cancelledWireItem],
      authorization: .unrestricted,
      deriveDeletedFromCancelledStatus: true)
    XCTAssertEqual(withOptIn, 1)

    let visible = try await ActionItemStorage.shared.getLocalActionItems(
      limit: 10,
      offset: 0,
      completed: false)
    XCTAssertEqual(visible, [], "a cancelled-status document must leave the To Do list")
  }

  // MARK: - Helpers

  /// Latest fallback_triggered snapshot from the shared diagnostics manager
  /// (same attachment-read pattern as DesktopDiagnosticsManagerTests).
  private func latestFallbackSnapshot() throws -> [String: Any] {
    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }
    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    return try XCTUnwrap(snapshots.last(where: { ($0["event"] as? String) == "fallback_triggered" }))
  }

  @MainActor
  private func task(id: String, completed: Bool = false) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: id,
      completed: completed,
      createdAt: Date(timeIntervalSince1970: 0))
  }

  @MainActor
  private func prepareStore(_ store: TasksStore) async {
    let defaults = UserDefaults.standard
    let previousAuthOwner = defaults.string(forKey: .authUserId)
    let previousOverride = defaults.string(forKey: .automationOwnerOverride)
    addTeardownBlock { @MainActor [weak self] in
      guard let self else { return }
      await self.establishEffectiveOwner(
        authOwnerID: previousAuthOwner,
        automationOverrideID: previousOverride)
      store.resetSessionState()
    }
    await establishEffectiveOwner(authOwnerID: "owner-a", automationOverrideID: nil)
    store.resetSessionState()
  }

  @MainActor
  private func establishEffectiveOwner(
    authOwnerID: String?,
    automationOverrideID: String?
  ) async {
    let finalOwner = normalizedOwner(automationOverrideID) ?? normalizedOwner(authOwnerID)
    let bootstrap =
      finalOwner == "empty-cloud-bootstrap-a"
      ? "empty-cloud-bootstrap-b"
      : "empty-cloud-bootstrap-a"
    if RuntimeOwnerIdentity.currentOwnerId(allowAutomationOverride: true) == bootstrap {
      await transitionEffectiveOwner(authOwnerID: nil, automationOverrideID: nil)
    } else {
      await transitionEffectiveOwner(authOwnerID: bootstrap, automationOverrideID: nil)
    }
    await transitionEffectiveOwner(
      authOwnerID: authOwnerID,
      automationOverrideID: automationOverrideID)
  }

  @MainActor
  private func transitionEffectiveOwner(
    authOwnerID: String?,
    automationOverrideID: String?
  ) async {
    let plannedOwner = normalizedOwner(automationOverrideID) ?? normalizedOwner(authOwnerID)
    _ = await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      allowAutomationOverride: true,
      plannedNextOwner: { _, _ in plannedOwner },
      quiesceVoice: { _, _ in },
      revokeKernelOwner: { _, _ in },
      retargetLocalStorage: { _, _ in },
      ownerDidChange: {
        await MainActor.run {
          NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
        }
      }
    ) { defaults in
      if let authOwnerID {
        defaults.set(authOwnerID, forKey: .authUserId)
      } else {
        defaults.removeObject(forKey: .authUserId)
      }
      if let automationOverrideID {
        defaults.set(automationOverrideID, forKey: .automationOwnerOverride)
      } else {
        defaults.removeObject(forKey: .automationOwnerOverride)
      }
    }
  }

  private func normalizedOwner(_ value: String?) -> String? {
    guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines),
      !trimmed.isEmpty
    else { return nil }
    return trimmed
  }
}
