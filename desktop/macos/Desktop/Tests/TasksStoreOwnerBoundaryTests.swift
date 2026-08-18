import Combine
import XCTest

@testable import Omi_Computer

private actor TasksStorePauseGate {
  private var started = false
  private var released = false

  func pause() async {
    started = true
    while !released {
      await Task.yield()
    }
  }

  func waitUntilStarted() async {
    while !started {
      await Task.yield()
    }
  }

  func release() {
    released = true
  }
}

private enum TasksStoreOwnerBoundaryFailure: LocalizedError {
  case backendRejected

  var errorDescription: String? { "backend rejected" }
}

@MainActor
private final class TasksStoreOperationProbe {
  var localWrites = 0
  var remoteRequests = 0
  var remoteSyncs = 0
  var rollbacks = 0
  var dashboardRefreshes = 0
  var hardDeletes = 0
}

final class TasksStoreOwnerBoundaryTests: XCTestCase {
  @MainActor
  func testToggleNeverPublishesAnIntervalWithoutTheCanonicalTask() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)
    let original = task(id: "published-toggle")
    let completed = task(id: original.id, completed: true)
    store.incompleteTasks = [original]
    var visibility: [Bool] = []
    let observation = Publishers.CombineLatest(store.$incompleteTasks, store.$completedTasks)
      .dropFirst()
      .sink { incomplete, completed in
        visibility.append((incomplete + completed).contains { $0.id == original.id })
      }

    await store.toggleTask(
      original,
      operationOverrides: TasksStore.ToggleOperationOverrides(
        updateLocal: { _, _ in completed },
        refreshDashboard: { _ in },
        updateRemote: { _, _ in completed },
        syncRemote: { _, _ in },
        rollbackLocal: {}
      )
    )

    withExtendedLifetime(observation) {
      XCTAssertFalse(visibility.isEmpty)
      XCTAssertTrue(visibility.allSatisfy { $0 })
    }
  }

  @MainActor
  func testToggleRollbackNeverPublishesAnIntervalWithoutTheCanonicalTask() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)
    let original = task(id: "published-toggle-rollback")
    let completed = task(id: original.id, completed: true)
    store.incompleteTasks = [original]
    var visibility: [Bool] = []
    let observation = Publishers.CombineLatest(store.$incompleteTasks, store.$completedTasks)
      .dropFirst()
      .sink { incomplete, completed in
        visibility.append((incomplete + completed).contains { $0.id == original.id })
      }

    await store.toggleTask(
      original,
      operationOverrides: TasksStore.ToggleOperationOverrides(
        updateLocal: { _, _ in completed },
        refreshDashboard: { _ in },
        updateRemote: { _, _ in throw TasksStoreOwnerBoundaryFailure.backendRejected },
        syncRemote: { _, _ in },
        rollbackLocal: {}
      )
    )

    withExtendedLifetime(observation) {
      XCTAssertFalse(visibility.isEmpty)
      XCTAssertTrue(visibility.allSatisfy { $0 })
    }
    XCTAssertEqual(store.incompleteTasks, [original])
    XCTAssertTrue(store.completedTasks.isEmpty)
  }

  @MainActor
  func testCanonicalTaskResolutionRepublishesCompletedLocalTaskBeforeRemoteFetch() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)
    let completed = task(id: "completed-chat-card", completed: true)
    var remoteFetches = 0

    let resolved = await store.resolveCanonicalTask(
      id: completed.id,
      operations: TasksStore.OwnerBoundOperations(
        fetchTaskDetail: { _, _ in
          remoteFetches += 1
          return nil
        },
        loadTaskDetail: { id, ownerID in
          XCTAssertEqual(id, completed.id)
          XCTAssertEqual(ownerID, "owner-a")
          return completed
        }
      )
    )

    XCTAssertEqual(resolved, completed)
    XCTAssertEqual(store.completedTasks, [completed])
    XCTAssertTrue(store.incompleteTasks.isEmpty)
    XCTAssertEqual(remoteFetches, 0)
  }

  @MainActor
  func testNoDeadlinePaginationUsesAPIConsumptionOffsetInsteadOfLocalPresentationCount() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let dated = task(id: "dated", dueAt: Date(timeIntervalSince1970: 1_700_000_100))
    let firstPage = (0..<100).map { task(id: "undated-\($0)") }
    let initialSurface = TasksStore.OwnerBoundOperations.IncompleteTaskSurface(
      datedTasks: [dated],
      noDeadlineTasks: firstPage,
      hasMoreNoDeadline: true,
      apiConsumedNoDeadlineCount: 100
    )
    var requestedOffsets: [Int] = []
    var pageNumber = 0
    let operations = TasksStore.OwnerBoundOperations(
      fetchIncompleteSurface: { _ in initialSurface },
      fetchDatedTasks: { _ in [dated] },
      fetchNoDeadlinePage: { offset, _, _ in
        requestedOffsets.append(offset)
        defer { pageNumber += 1 }
        if pageNumber == 0 {
          return .init(items: [firstPage[0], self.task(id: "undated-100")], hasMore: true)
        }
        return .init(items: [self.task(id: "undated-101")], hasMore: false)
      },
      syncPage: { _, _, _ in },
      loadIncompleteSurface: { _ in initialSurface }
    )

    await store.loadIncompleteTasks(allowInitialReconciliation: false, operations: operations)
    guard let firstAnchor = firstPage.last else {
      XCTFail("Expected the first page to provide a pagination anchor")
      return
    }
    await store.loadMoreIncompleteIfNeeded(currentTask: firstAnchor, operations: operations)
    guard let nextAnchor = store.incompleteTasks.last else {
      XCTFail("Expected the loaded tasks to provide a pagination anchor")
      return
    }
    await store.loadMoreIncompleteIfNeeded(currentTask: nextAnchor, operations: operations)

    XCTAssertEqual(requestedOffsets, [100, 102])
    XCTAssertEqual(store.incompleteTasks.filter { $0.dueAt == nil }.count, 102)
    XCTAssertEqual(Set(store.incompleteTasks.map(\.id)).count, store.incompleteTasks.count)
  }

  @MainActor
  func testFullSyncReloadPreservesExpandedNoDeadlineWindowAndAllDatedRows() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let expanded = (0..<150).map { task(id: "undated-\($0)") }
    store.incompleteTasks = expanded
    let dated = (0..<3).map {
      task(id: "dated-\($0)", dueAt: Date(timeIntervalSince1970: 1_700_000_100 + Double($0)))
    }
    var requestedLimit: Int?
    let operations = TasksStore.OwnerBoundOperations(
      loadIncompleteSurfaceForLimit: { _, limit in
        requestedLimit = limit
        return .init(
          datedTasks: dated,
          noDeadlineTasks: expanded,
          hasMoreNoDeadline: true
        )
      }
    )

    await store.reloadIncompleteTaskSurfaceAfterFullSync(operations: operations)

    XCTAssertEqual(requestedLimit, 150)
    XCTAssertEqual(store.incompleteTasks.filter { $0.dueAt != nil }.map(\.id), dated.map(\.id))
    XCTAssertEqual(store.incompleteTasks.filter { $0.dueAt == nil }.count, 150)
    XCTAssertTrue(store.hasMoreIncompleteTasks)
  }

  @MainActor
  func testReloadIncompleteTasksPreservesExpandedNoDeadlineAPICursor() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let dated = task(id: "dated", dueAt: Date(timeIntervalSince1970: 1_700_000_100))
    let firstPage = (0..<100).map { task(id: "undated-\($0)") }
    let secondPage = (100..<150).map { task(id: "undated-\($0)") }
    let initialSurface = TasksStore.OwnerBoundOperations.IncompleteTaskSurface(
      datedTasks: [dated],
      noDeadlineTasks: firstPage,
      hasMoreNoDeadline: true,
      apiConsumedNoDeadlineCount: 100
    )
    let expandedSurface = TasksStore.OwnerBoundOperations.IncompleteTaskSurface(
      datedTasks: [dated],
      noDeadlineTasks: firstPage + secondPage,
      hasMoreNoDeadline: true,
      apiConsumedNoDeadlineCount: 150
    )
    let refreshedSurface = TasksStore.OwnerBoundOperations.IncompleteTaskSurface(
      datedTasks: [dated],
      noDeadlineTasks: firstPage,
      hasMoreNoDeadline: true,
      apiConsumedNoDeadlineCount: 100
    )
    var requestedOffsets: [Int] = []
    var pageNumber = 0
    let operations = TasksStore.OwnerBoundOperations(
      fetchIncompleteSurface: { _ in refreshedSurface },
      fetchDatedTasks: { _ in [dated] },
      fetchNoDeadlinePage: { offset, _, _ in
        requestedOffsets.append(offset)
        defer { pageNumber += 1 }
        switch pageNumber {
        case 0:
          return .init(items: secondPage, hasMore: true)
        case 1:
          return .init(items: [self.task(id: "undated-150")], hasMore: false)
        default:
          return .init(items: [], hasMore: false)
        }
      },
      syncPage: { _, _, _ in },
      loadIncompleteSurface: { _ in initialSurface },
      loadIncompleteSurfaceForLimit: { _, limit in
        XCTAssertEqual(limit, 150)
        return expandedSurface
      }
    )

    await store.loadIncompleteTasks(allowInitialReconciliation: false, operations: operations)
    guard let firstAnchor = firstPage.last else {
      XCTFail("Expected the first page to provide a pagination anchor")
      return
    }
    await store.loadMoreIncompleteIfNeeded(currentTask: firstAnchor, operations: operations)
    XCTAssertEqual(requestedOffsets, [100])

    requestedOffsets = []
    pageNumber = 0
    await store.loadIncompleteTasks(allowInitialReconciliation: false, operations: operations)
    guard let expandedAnchor = store.incompleteTasks.last(where: { $0.dueAt == nil }) else {
      XCTFail("Expected a No Deadline pagination anchor after refresh")
      return
    }
    await store.loadMoreIncompleteIfNeeded(currentTask: expandedAnchor, operations: operations)

    XCTAssertEqual(requestedOffsets, [150])
  }

  @MainActor
  func testNoDeadlinePaginationReplacesDatedProjectionWithServerFetch() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let staleDated = task(id: "dated", dueAt: Date(timeIntervalSince1970: 1_000))
    let freshDated = task(id: "dated", dueAt: Date(timeIntervalSince1970: 1_700_000_100))
    let firstPage = (0..<100).map { task(id: "undated-\($0)") }
    store.incompleteTasks = [staleDated] + firstPage

    let initialSurface = TasksStore.OwnerBoundOperations.IncompleteTaskSurface(
      datedTasks: [staleDated],
      noDeadlineTasks: firstPage,
      hasMoreNoDeadline: true,
      apiConsumedNoDeadlineCount: 100
    )
    let operations = TasksStore.OwnerBoundOperations(
      fetchIncompleteSurface: { _ in initialSurface },
      fetchDatedTasks: { _ in [freshDated] },
      fetchNoDeadlinePage: { _, _, _ in
        .init(items: [self.task(id: "undated-100")], hasMore: false)
      },
      syncPage: { _, _, _ in },
      loadIncompleteSurface: { _ in initialSurface }
    )

    await store.loadIncompleteTasks(allowInitialReconciliation: false, operations: operations)
    guard let anchor = firstPage.last else {
      XCTFail("Expected the first page to provide a pagination anchor")
      return
    }
    await store.loadMoreIncompleteIfNeeded(currentTask: anchor, operations: operations)

    let refreshedDated = store.incompleteTasks.first(where: { $0.id == "dated" })
    XCTAssertEqual(refreshedDated?.dueAt, freshDated.dueAt)
    XCTAssertEqual(store.incompleteTasks.filter { $0.dueAt != nil }.map(\.id), ["dated"])
  }

  @MainActor
  func testOwnerFenceDuringNoDeadlinePageAlwaysClearsLoadingState() async {
    let defaults = UserDefaults.standard
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let firstPage = (0..<100).map { task(id: "undated-\($0)") }
    let surface = TasksStore.OwnerBoundOperations.IncompleteTaskSurface(
      datedTasks: [],
      noDeadlineTasks: firstPage,
      hasMoreNoDeadline: true
    )
    let gate = TasksStorePauseGate()
    let operations = TasksStore.OwnerBoundOperations(
      fetchIncompleteSurface: { _ in surface },
      fetchDatedTasks: { _ in [] },
      fetchNoDeadlinePage: { _, _, _ in
        await gate.pause()
        return .init(items: [self.task(id: "late-owner-a")], hasMore: false)
      },
      syncPage: { _, _, _ in },
      loadIncompleteSurface: { _ in surface }
    )
    await store.loadIncompleteTasks(allowInitialReconciliation: false, operations: operations)

    guard let firstAnchor = firstPage.last else {
      XCTFail("Expected the first page to provide a pagination anchor")
      return
    }
    let load = Task { @MainActor in
      await store.loadMoreIncompleteIfNeeded(currentTask: firstAnchor, operations: operations)
    }
    await gate.waitUntilStarted()
    XCTAssertTrue(store.isLoadingMore)
    illegallyMutateOwnerDefaults(to: "owner-b", defaults: defaults)
    await gate.release()
    await load.value

    XCTAssertFalse(store.isLoadingMore)
    XCTAssertFalse(store.incompleteTasks.contains { $0.id == "late-owner-a" })
  }

  func testStaticGuardRetiredLocalStagingMigrationDoesNotWriteTaskRows() throws {
    let source = try productionSource("Rewind/Core/RewindDatabase.swift")
    let migrationMarker = "migrator.registerMigration(\"migrateAITasksToStaged\")"
    let migrationStart = try XCTUnwrap(source.range(of: migrationMarker)?.lowerBound)
    let nextMigration = source.range(
      of: "\n    migrator.registerMigration(",
      range: migrationStart..<source.endIndex
    )
    let migrationBody = String(source[migrationStart..<(nextMigration?.lowerBound ?? source.endIndex)])

    // omi-test-quality: source-inspection -- static tripwire for the retired
    // migration; a behavioral recovery test covers server-side task restoration.
    XCTAssertFalse(
      migrationBody.contains("db.execute"),
      "the retired local staging migration must never move or delete action_items"
    )
  }

  func testStaticGuardTasksStoreHasNoUnrestrictedSQLiteMutationCallSites() throws {
    let lines = try productionSource("Stores/TasksStore.swift")
      .components(separatedBy: .newlines)
    let mutationNames = [
      "syncTaskActionItems(",
      "insertLocalActionItem(",
      "markSynced(",
      "updateCompletionStatus(",
      "updateActionItemFields(",
      "deleteActionItemByBackendId(",
      "markActionItemDeletionAcknowledged(",
      "deleteActionItemsByBackendIds(",
      "compactScoresAfterRemoval(",
      "hardDeleteAbsentTasks(",
      "markAbsentTasksAsStaged(",
      "purgeAllSoftDeletedItems(",
      "backfillUnscoredTasks(",
      "updateSortOrders(",
    ]

    for (index, line) in lines.enumerated() {
      guard mutationNames.contains(where: line.contains) else { continue }
      let windowEnd = min(lines.endIndex, index + 16)
      let callWindow = lines[index..<windowEnd].joined(separator: "\n")
      XCTAssertTrue(
        callWindow.contains("authorization:"),
        "TasksStore SQLite mutation at line \(index + 1) must carry LocalMutationAuthorization")
    }
    XCTAssertFalse(lines.joined(separator: "\n").contains("updateChatSessionId"))
    let storageSource = try productionSource("Rewind/Core/ActionItemStorage.swift")
    XCTAssertFalse(storageSource.contains("func updateChatSessionId"))
    XCTAssertNil(
      storageSource.range(
        of: #"authorization\s*:\s*LocalMutationAuthorization\s*=\s*\.unrestricted"#,
        options: .regularExpression),
      "ActionItemStorage mutators must require an explicit authorization capability")
  }

  func testStaticGuardEveryActionItemStorageWriteRequiresCommitAuthorization() throws {
    let lines = try productionSource("Rewind/Core/ActionItemStorage.swift")
      .components(separatedBy: .newlines)

    for (writeIndex, line) in lines.enumerated() where line.contains("db.write") {
      guard let functionIndex = lines[..<writeIndex].lastIndex(where: { $0.contains("func ") }) else {
        return XCTFail("ActionItemStorage write at line \(writeIndex + 1) has no function owner")
      }
      let functionPrefix = lines[functionIndex...writeIndex].joined(separator: "\n")
      XCTAssertTrue(
        functionPrefix.contains("authorization: LocalMutationAuthorization"),
        "ActionItemStorage write at line \(writeIndex + 1) must require explicit authorization")
      XCTAssertTrue(
        functionPrefix.contains("authorization.withCommitLease"),
        "ActionItemStorage write at line \(writeIndex + 1) must hold the transition fence through commit")
      let validationWindow = lines[writeIndex..<min(lines.endIndex, writeIndex + 8)]
        .joined(separator: "\n")
      XCTAssertTrue(
        validationWindow.contains("authorization.require()"),
        "ActionItemStorage write at line \(writeIndex + 1) must revalidate inside its transaction")
    }
  }

  @MainActor
  func testPausedDashboardRefreshCannotPublishAfterOwnerSwitch() async {
    let defaults = UserDefaults.standard
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let ownerATask = task(id: "owner-a-dashboard")
    let ownerBTask = task(id: "owner-b-dashboard")
    store.overdueTasks = [ownerATask]
    let gate = TasksStorePauseGate()

    let refresh = Task { @MainActor in
      await store.loadDashboardTasks(
        loader: {
          await gate.pause()
          return TasksStore.DashboardTaskSnapshot(
            overdue: [ownerBTask],
            today: [ownerBTask],
            noDueDate: [ownerBTask])
        })
    }
    await gate.waitUntilStarted()
    illegallyMutateOwnerDefaults(to: "owner-b", defaults: defaults)
    await gate.release()
    await refresh.value

    XCTAssertEqual(store.overdueTasks.map(\.id), [ownerATask.id])
    XCTAssertTrue(store.todaysTasks.isEmpty)
    XCTAssertTrue(store.tasksWithoutDueDate.isEmpty)
  }

  @MainActor
  func testDefaultToggleEntrypointCapturesOwnerBeforeItsFirstAwait() async {
    let defaults = UserDefaults.standard
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let task = task(id: "owner-a-default-toggle")
    let dashboardSentinel = self.task(id: "owner-b-dashboard-sentinel")
    store.incompleteTasks = [task]
    store.overdueTasks = [dashboardSentinel]
    let gate = TasksStorePauseGate()

    let operation = Task { @MainActor in
      await store.toggleTask(
        task,
        beforeLocalMutation: {
          await gate.pause()
        })
    }
    await gate.waitUntilStarted()
    illegallyMutateOwnerDefaults(to: "owner-b", defaults: defaults)
    await gate.release()
    await operation.value

    XCTAssertEqual(store.incompleteTasks.map(\.id), [task.id])
    XCTAssertTrue(store.completedTasks.isEmpty)
    XCTAssertEqual(store.overdueTasks.map(\.id), [dashboardSentinel.id])
    XCTAssertNil(store.error)
  }

  @MainActor
  func testDefaultDeleteEntrypointCapturesOwnerBeforeItsFirstAwait() async {
    let defaults = UserDefaults.standard
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let task = task(id: "owner-a-default-delete")
    let dashboardSentinel = self.task(id: "owner-b-dashboard-sentinel")
    store.incompleteTasks = [task]
    store.overdueTasks = [dashboardSentinel]
    let gate = TasksStorePauseGate()

    let operation = Task { @MainActor in
      await store.deleteTask(
        task,
        beforeLocalMutation: {
          await gate.pause()
        })
    }
    await gate.waitUntilStarted()
    illegallyMutateOwnerDefaults(to: "owner-b", defaults: defaults)
    await gate.release()
    await operation.value

    XCTAssertEqual(store.incompleteTasks.map(\.id), [task.id])
    XCTAssertTrue(store.completedTasks.isEmpty)
    XCTAssertEqual(store.overdueTasks.map(\.id), [dashboardSentinel.id])
    XCTAssertNil(store.error)
  }

  @MainActor
  func testPinnedToolSnapshotCannotRecaptureSameUIDAfterSessionGenerationChanges() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)
    guard
      let ownerASnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
        expectedOwnerID: "owner-a"
      )
    else {
      XCTFail("owner-a authorization snapshot was unavailable")
      return
    }
    store.resetSessionState()
    let ownerATask = task(id: "owner-a-old-tool-toggle")
    let optimisticTask = task(id: ownerATask.id, completed: true)
    store.incompleteTasks = [ownerATask]
    let gate = TasksStorePauseGate()
    let probe = TasksStoreOperationProbe()

    let operation = Task { @MainActor in
      await store.toggleTask(
        ownerATask,
        expectedOwnerID: "owner-a",
        authorizationSnapshot: ownerASnapshot,
        beforeLocalMutation: { await gate.pause() },
        operationOverrides: TasksStore.ToggleOperationOverrides(
          updateLocal: { _, _ in
            probe.localWrites += 1
            return optimisticTask
          },
          refreshDashboard: { _ in probe.dashboardRefreshes += 1 },
          updateRemote: { _, _ in
            probe.remoteRequests += 1
            return optimisticTask
          },
          syncRemote: { _, _ in probe.remoteSyncs += 1 },
          rollbackLocal: { probe.rollbacks += 1 }
        )
      )
    }
    await gate.waitUntilStarted()

    // The effective uid is the same again, but this is a new authenticated
    // generation. An old authorized tool must not mint a fresh TasksStore lease.
    await transitionEffectiveOwner(to: nil)
    await transitionEffectiveOwner(to: "owner-a")
    await gate.release()
    await operation.value

    XCTAssertEqual(probe.localWrites, 0)
    XCTAssertEqual(probe.dashboardRefreshes, 0)
    XCTAssertEqual(probe.remoteRequests, 0)
    XCTAssertEqual(probe.remoteSyncs, 0)
    XCTAssertEqual(probe.rollbacks, 0)
    XCTAssertTrue(
      store.incompleteTasks.isEmpty,
      "the owner transition must purge the prior session's visible task arrays")
    XCTAssertTrue(store.completedTasks.isEmpty)
  }

  @MainActor
  func testLateDefaultToggleAPIResponseCannotApplyOrRollbackInReplacementOwner() async {
    let defaults = UserDefaults.standard
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let ownerATask = task(id: "owner-a-api-toggle")
    let optimisticTask = task(id: ownerATask.id, completed: true)
    let ownerBTask = task(id: "owner-b-task")
    let ownerBDashboard = task(id: "owner-b-dashboard")
    store.incompleteTasks = [ownerATask]
    let gate = TasksStorePauseGate()
    let probe = TasksStoreOperationProbe()

    let operation = Task { @MainActor in
      await store.toggleTask(
        ownerATask,
        operationOverrides: TasksStore.ToggleOperationOverrides(
          updateLocal: { _, ownerID in
            XCTAssertEqual(ownerID, "owner-a")
            probe.localWrites += 1
            return optimisticTask
          },
          refreshDashboard: { ownerID in
            XCTAssertEqual(ownerID, "owner-a")
            probe.dashboardRefreshes += 1
          },
          updateRemote: { _, ownerID in
            XCTAssertEqual(ownerID, "owner-a")
            probe.remoteRequests += 1
            await gate.pause()
            return optimisticTask
          },
          syncRemote: { _, _ in
            probe.remoteSyncs += 1
          },
          rollbackLocal: {
            probe.rollbacks += 1
          }))
    }
    await gate.waitUntilStarted()
    illegallyMutateOwnerDefaults(to: "owner-b", defaults: defaults)
    store.incompleteTasks = [ownerBTask]
    store.completedTasks = []
    store.overdueTasks = [ownerBDashboard]
    store.error = nil
    await gate.release()
    await operation.value

    XCTAssertEqual(probe.localWrites, 1)
    XCTAssertEqual(probe.remoteRequests, 1)
    XCTAssertEqual(probe.remoteSyncs, 0)
    XCTAssertEqual(probe.rollbacks, 0)
    XCTAssertEqual(probe.dashboardRefreshes, 1)
    XCTAssertEqual(store.incompleteTasks.map(\.id), [ownerBTask.id])
    XCTAssertTrue(store.completedTasks.isEmpty)
    XCTAssertEqual(store.overdueTasks.map(\.id), [ownerBDashboard.id])
    XCTAssertNil(store.error)
  }

  @MainActor
  func testPausedBackendRollbackCannotRewriteReplacementOwnerArrays() async {
    let defaults = UserDefaults.standard
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let original = task(id: "owner-a-toggle", completed: false)
    let optimistic = task(id: original.id, completed: true)
    store.completedTasks = [optimistic]
    let gate = TasksStorePauseGate()

    let rollback = Task { @MainActor in
      await store.rollbackToggleAfterBackendFailure(
        task: original,
        attemptedCompleted: true,
        backendError: TasksStoreOwnerBoundaryFailure.backendRejected,
        expectedOwnerID: "owner-a",
        rollbackStorage: {
          await gate.pause()
        })
    }
    await gate.waitUntilStarted()
    illegallyMutateOwnerDefaults(to: "owner-b", defaults: defaults)
    await gate.release()
    await rollback.value

    XCTAssertEqual(store.completedTasks.map(\.id), [optimistic.id])
    XCTAssertTrue(store.incompleteTasks.isEmpty)
    XCTAssertNil(store.error)
  }

  @MainActor
  func testSuspendedOrdinaryLoadCannotWriteOrPublishAfterOwnerSwitch() async {
    let defaults = UserDefaults.standard
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let gate = TasksStorePauseGate()
    let probe = TasksStoreOperationProbe()
    let lateOwnerATask = task(id: "late-owner-a-load")
    let ownerBSentinel = task(id: "owner-b-load-sentinel")
    let operations = TasksStore.OwnerBoundOperations(
      fetchPage: { completed, offset, _, ownerID in
        XCTAssertFalse(completed)
        XCTAssertEqual(offset, 0)
        XCTAssertEqual(ownerID, "owner-a")
        await gate.pause()
        return .init(items: [lateOwnerATask], hasMore: false)
      },
      syncPage: { _, _, _ in probe.localWrites += 1 },
      hardDeleteAbsent: { _, _ in
        probe.hardDeletes += 1
        return 0
      },
      loadIncomplete: { ownerID in
        XCTAssertEqual(ownerID, "owner-a")
        return []
      })

    let load = Task { @MainActor in
      await store.loadIncompleteTasks(operations: operations)
    }
    await gate.waitUntilStarted()
    switchOwner(to: "owner-b", defaults: defaults)
    store.incompleteTasks = [ownerBSentinel]
    await gate.release()
    await load.value

    XCTAssertEqual(probe.localWrites, 0)
    XCTAssertEqual(probe.hardDeletes, 0)
    XCTAssertEqual(store.incompleteTasks.map(\.id), [ownerBSentinel.id])
    XCTAssertFalse(store.isLoadingIncomplete)
    XCTAssertNil(store.error)
  }

  @MainActor
  func testSuspendedStartupPageCannotMutateCacheDefaultsOrUIAfterOwnerSwitch() async {
    let defaults = UserDefaults.standard
    let ownerASyncKey = "tasksFullSyncCompleted_v9_owner-a"
    let ownerBSyncKey = "tasksFullSyncCompleted_v9_owner-b"
    let previousASync = defaults.object(forKey: ownerASyncKey)
    let previousBSync = defaults.object(forKey: ownerBSyncKey)
    let store = TasksStore.shared
    defer {
      restore(previousASync, key: ownerASyncKey, defaults: defaults)
      restore(previousBSync, key: ownerBSyncKey, defaults: defaults)
    }
    await prepareOwnerBoundaryTest(store: store)
    defaults.removeObject(forKey: ownerASyncKey)
    defaults.removeObject(forKey: ownerBSyncKey)

    let gate = TasksStorePauseGate()
    let probe = TasksStoreOperationProbe()
    let ownerBSentinel = task(id: "owner-b-startup-sentinel")
    let operations = TasksStore.OwnerBoundOperations(
      fetchPage: { completed, offset, _, ownerID in
        XCTAssertFalse(completed)
        XCTAssertEqual(offset, 0)
        XCTAssertEqual(ownerID, "owner-a")
        await gate.pause()
        return .init(items: [self.task(id: "late-owner-a-startup")], hasMore: false)
      },
      syncPage: { _, _, _ in probe.localWrites += 1 },
      markAbsent: { _, _ in probe.hardDeletes += 1 },
      purgeDeleted: { _ in
        probe.hardDeletes += 1
        return 0
      },
      restoreLegacyConversationItems: { _, _ in .init(restored: 0, skippedExisting: 0, hasMore: false, nextCursor: nil)
      })

    let maintenanceTasks = store.scheduleStartupMaintenanceIfNeeded(
      relevanceBackfill: { _ in },
      operations: operations)
    await gate.waitUntilStarted()
    switchOwner(to: "owner-b", defaults: defaults)
    store.incompleteTasks = [ownerBSentinel]
    await gate.release()
    for task in maintenanceTasks { await task.value }

    XCTAssertEqual(probe.localWrites, 0)
    XCTAssertEqual(probe.hardDeletes, 0)
    XCTAssertFalse(defaults.bool(forKey: ownerASyncKey))
    XCTAssertFalse(defaults.bool(forKey: ownerBSyncKey))
    XCTAssertEqual(store.incompleteTasks.map(\.id), [ownerBSentinel.id])
    XCTAssertFalse(store.hasScheduledStartupMaintenance)
  }

  @MainActor
  func testSuspendedStartupRecoveryCannotContinueIntoReplacementOwner() async {
    let defaults = UserDefaults.standard
    let fullSyncKey = "tasksFullSyncCompleted_v9_owner-a"
    let ownerARecoveryKey = "restoreLegacyConversationItemsCompleted_v1_owner-a"
    let ownerBRecoveryKey = "restoreLegacyConversationItemsCompleted_v1_owner-b"
    let keys = [fullSyncKey, ownerARecoveryKey, ownerBRecoveryKey]
    let previousValues = Dictionary(uniqueKeysWithValues: keys.map { ($0, defaults.object(forKey: $0)) })
    let store = TasksStore.shared
    defer {
      for key in keys { restore(previousValues[key] ?? nil, key: key, defaults: defaults) }
    }
    await prepareOwnerBoundaryTest(store: store)
    defaults.set(true, forKey: fullSyncKey)
    defaults.removeObject(forKey: ownerARecoveryKey)
    defaults.removeObject(forKey: ownerBRecoveryKey)

    let gate = TasksStorePauseGate()
    let probe = TasksStoreOperationProbe()
    let operations = TasksStore.OwnerBoundOperations(
      restoreLegacyConversationItems: { ownerID, _ in
        XCTAssertEqual(ownerID, "owner-a")
        probe.remoteRequests += 1
        await gate.pause()
        return .init(restored: 1, skippedExisting: 0, hasMore: false, nextCursor: nil)
      })

    let maintenanceTasks = store.scheduleStartupMaintenanceIfNeeded(
      relevanceBackfill: { _ in },
      operations: operations)
    await gate.waitUntilStarted()
    switchOwner(to: "owner-b", defaults: defaults)
    await gate.release()
    for task in maintenanceTasks { await task.value }

    XCTAssertEqual(probe.remoteRequests, 1)
    XCTAssertFalse(defaults.bool(forKey: ownerARecoveryKey))
    XCTAssertFalse(defaults.bool(forKey: ownerBRecoveryKey))
    XCTAssertFalse(store.hasScheduledStartupMaintenance)
  }

  @MainActor
  func testSuspendedPaginationCannotAppendOrSyncAfterOwnerSwitch() async {
    let defaults = UserDefaults.standard
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let trigger = task(id: "owner-a-page-trigger")
    let ownerBSentinel = task(id: "owner-b-page-sentinel")
    store.incompleteTasks = [trigger]
    store.hasMoreIncompleteTasks = true
    let gate = TasksStorePauseGate()
    let probe = TasksStoreOperationProbe()
    let operations = TasksStore.OwnerBoundOperations(
      fetchPage: { completed, _, _, ownerID in
        XCTAssertFalse(completed)
        XCTAssertEqual(ownerID, "owner-a")
        await gate.pause()
        return .init(items: [self.task(id: "late-owner-a-page")], hasMore: false)
      },
      syncPage: { _, _, _ in probe.localWrites += 1 })

    let pagination = Task { @MainActor in
      await store.loadMoreIncompleteIfNeeded(currentTask: trigger, operations: operations)
    }
    await gate.waitUntilStarted()
    switchOwner(to: "owner-b", defaults: defaults)
    store.incompleteTasks = [ownerBSentinel]
    await gate.release()
    await pagination.value

    XCTAssertEqual(probe.localWrites, 0)
    XCTAssertEqual(store.incompleteTasks.map(\.id), [ownerBSentinel.id])
    XCTAssertFalse(store.isLoadingMore)
  }

  @MainActor
  func testSuspendedActivationRefreshCannotSyncOrPublishAfterOwnerSwitch() async {
    let defaults = UserDefaults.standard
    let previousSignedIn = AuthService.shared.isSignedIn
    let store = TasksStore.shared
    defer {
      store.isActive = false
      AuthService.shared.isSignedIn = previousSignedIn
    }
    await prepareOwnerBoundaryTest(store: store)
    AuthService.shared.isSignedIn = true
    store.isActive = false
    store.isActive = true

    let ownerATask = task(id: "owner-a-refresh-base")
    let initialOperations = TasksStore.OwnerBoundOperations(
      fetchPage: { _, _, _, ownerID in
        XCTAssertEqual(ownerID, "owner-a")
        return .init(items: [], hasMore: false)
      },
      syncPage: { _, _, _ in },
      hardDeleteAbsent: { _, _ in 0 },
      loadIncomplete: { ownerID in
        XCTAssertEqual(ownerID, "owner-a")
        return [ownerATask]
      })
    await store.loadIncompleteTasks(operations: initialOperations)
    XCTAssertEqual(store.incompleteTasks.map(\.id), [ownerATask.id])

    let gate = TasksStorePauseGate()
    let probe = TasksStoreOperationProbe()
    let ownerBSentinel = task(id: "owner-b-refresh-sentinel")
    let suspendedOperations = TasksStore.OwnerBoundOperations(
      fetchPage: { completed, _, _, ownerID in
        XCTAssertFalse(completed)
        XCTAssertEqual(ownerID, "owner-a")
        await gate.pause()
        return .init(items: [self.task(id: "late-owner-a-refresh")], hasMore: false)
      },
      syncPage: { _, _, _ in probe.localWrites += 1 },
      hardDeleteAbsent: { _, _ in
        probe.hardDeletes += 1
        return 1
      },
      loadIncomplete: { _ in [ownerATask] })

    let refresh = Task { @MainActor in
      await store.refreshTasksIfNeeded(operations: suspendedOperations)
    }
    await gate.waitUntilStarted()
    switchOwner(to: "owner-b", defaults: defaults)
    store.incompleteTasks = [ownerBSentinel]
    await gate.release()
    await refresh.value

    XCTAssertEqual(probe.localWrites, 0)
    XCTAssertEqual(probe.hardDeletes, 0)
    XCTAssertEqual(store.incompleteTasks.map(\.id), [ownerBSentinel.id])
    XCTAssertNil(store.error)
  }

  @MainActor
  func testSuspendedPeriodicReconciliationCannotDeleteForReplacementOwner() async {
    let defaults = UserDefaults.standard
    let previousSignedIn = AuthService.shared.isSignedIn
    let store = TasksStore.shared
    defer {
      AuthService.shared.isSignedIn = previousSignedIn
    }
    await prepareOwnerBoundaryTest(store: store)
    AuthService.shared.isSignedIn = true
    let recoveryKey = "restoreLegacyConversationItemsCompleted_v1_owner-a"
    let priorRecoveryValue = defaults.object(forKey: recoveryKey)
    defaults.set(true, forKey: recoveryKey)
    defer {
      if let priorRecoveryValue {
        defaults.set(priorRecoveryValue, forKey: recoveryKey)
      } else {
        defaults.removeObject(forKey: recoveryKey)
      }
    }

    let gate = TasksStorePauseGate()
    let probe = TasksStoreOperationProbe()
    let ownerBSentinel = task(id: "owner-b-reconcile-sentinel")
    let operations = TasksStore.OwnerBoundOperations(
      fetchPage: { completed, _, _, ownerID in
        XCTAssertFalse(completed)
        XCTAssertEqual(ownerID, "owner-a")
        await gate.pause()
        return .init(items: [self.task(id: "late-owner-a-reconcile")], hasMore: false)
      },
      hardDeleteAbsent: { _, _ in
        probe.hardDeletes += 1
        return 1
      })

    let reconciliation = Task { @MainActor in
      await store.reconcileWithAPIIfNeeded(operations: operations)
    }
    await gate.waitUntilStarted()
    switchOwner(to: "owner-b", defaults: defaults)
    store.incompleteTasks = [ownerBSentinel]
    await gate.release()
    await reconciliation.value

    XCTAssertEqual(probe.hardDeletes, 0)
    XCTAssertEqual(store.incompleteTasks.map(\.id), [ownerBSentinel.id])
  }

  @MainActor
  func testChatFirstUpdateRollsBackRejectedRenameThroughStoreSeam() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let original = task(id: "owner-a-chat-first-update")
    let optimistic = TaskActionItem(
      id: original.id,
      description: "Renamed task",
      completed: false,
      createdAt: original.createdAt)
    store.incompleteTasks = [original]
    let probe = TasksStoreOperationProbe()

    let outcome = await store.updateTask(
      original,
      description: optimistic.description,
      remoteFailureBehavior: .rollbackForChatFirst,
      operationOverrides: TasksStore.TaskUpdateOperationOverrides(
        updateLocal: { ownerID in
          XCTAssertEqual(ownerID, "owner-a")
          probe.localWrites += 1
          return optimistic
        },
        updateRemote: { ownerID in
          XCTAssertEqual(ownerID, "owner-a")
          probe.remoteRequests += 1
          throw TasksStoreOwnerBoundaryFailure.backendRejected
        },
        syncRemote: { _, _ in probe.remoteSyncs += 1 },
        rollbackLocal: { probe.rollbacks += 1 }
      )
    )

    XCTAssertEqual(outcome, .rolledBackAfterRemoteFailure)
    XCTAssertEqual(probe.localWrites, 1)
    XCTAssertEqual(probe.remoteRequests, 1)
    XCTAssertEqual(probe.remoteSyncs, 0)
    XCTAssertEqual(probe.rollbacks, 1)
    XCTAssertEqual(store.incompleteTasks, [original])
  }

  @MainActor
  func testLegacyUpdatePreservesItsLocalEditAfterRemoteFailure() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let original = task(id: "owner-a-legacy-update")
    let optimistic = TaskActionItem(
      id: original.id,
      description: "Locally renamed task",
      completed: false,
      createdAt: original.createdAt)
    store.incompleteTasks = [original]
    let probe = TasksStoreOperationProbe()

    let outcome = await store.updateTask(
      original,
      description: optimistic.description,
      operationOverrides: TasksStore.TaskUpdateOperationOverrides(
        updateLocal: { _ in
          probe.localWrites += 1
          return optimistic
        },
        updateRemote: { _ in
          probe.remoteRequests += 1
          throw TasksStoreOwnerBoundaryFailure.backendRejected
        },
        syncRemote: { _, _ in probe.remoteSyncs += 1 },
        rollbackLocal: { probe.rollbacks += 1 }
      )
    )

    XCTAssertEqual(outcome, .preservedLocalAfterRemoteFailure)
    XCTAssertEqual(probe.localWrites, 1)
    XCTAssertEqual(probe.remoteRequests, 1)
    XCTAssertEqual(probe.remoteSyncs, 0)
    XCTAssertEqual(probe.rollbacks, 0)
    XCTAssertEqual(store.incompleteTasks, [optimistic])
  }

  @MainActor
  func testChatFirstUpdateCannotRollBackIntoReplacementOwner() async {
    let defaults = UserDefaults.standard
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let original = task(id: "owner-a-chat-first-owner-update")
    let optimistic = TaskActionItem(
      id: original.id,
      description: "Renamed task",
      completed: false,
      createdAt: original.createdAt)
    let replacement = task(id: "owner-b-chat-first-sentinel")
    store.incompleteTasks = [original]
    let gate = TasksStorePauseGate()
    let probe = TasksStoreOperationProbe()

    let operation = Task { @MainActor in
      await store.updateTask(
        original,
        description: optimistic.description,
        remoteFailureBehavior: .rollbackForChatFirst,
        operationOverrides: TasksStore.TaskUpdateOperationOverrides(
          updateLocal: { _ in
            probe.localWrites += 1
            return optimistic
          },
          updateRemote: { _ in
            probe.remoteRequests += 1
            await gate.pause()
            throw TasksStoreOwnerBoundaryFailure.backendRejected
          },
          syncRemote: { _, _ in probe.remoteSyncs += 1 },
          rollbackLocal: { probe.rollbacks += 1 }
        )
      )
    }
    await gate.waitUntilStarted()
    illegallyMutateOwnerDefaults(to: "owner-b", defaults: defaults)
    store.incompleteTasks = [replacement]
    await gate.release()
    let outcome = await operation.value

    XCTAssertEqual(outcome, .ownerChanged)
    XCTAssertEqual(probe.localWrites, 1)
    XCTAssertEqual(probe.remoteRequests, 1)
    XCTAssertEqual(probe.remoteSyncs, 0)
    XCTAssertEqual(probe.rollbacks, 0)
    XCTAssertEqual(store.incompleteTasks, [replacement])
    XCTAssertNil(store.error)
  }

  @MainActor
  func testChatFirstUpdateReportsRollbackFailureWithoutPretendingTheOwnerChanged() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)

    let original = task(id: "owner-a-chat-first-rollback-failure")
    let optimistic = TaskActionItem(
      id: original.id,
      description: "Renamed task",
      completed: false,
      createdAt: original.createdAt)
    store.incompleteTasks = [original]

    let outcome = await store.updateTask(
      original,
      description: optimistic.description,
      remoteFailureBehavior: .rollbackForChatFirst,
      operationOverrides: TasksStore.TaskUpdateOperationOverrides(
        updateLocal: { _ in optimistic },
        updateRemote: { _ in throw TasksStoreOwnerBoundaryFailure.backendRejected },
        syncRemote: { _, _ in },
        rollbackLocal: { throw TasksStoreOwnerBoundaryFailure.backendRejected }
      )
    )

    XCTAssertEqual(outcome, .rollbackFailed)
    XCTAssertEqual(store.incompleteTasks, [optimistic])
    XCTAssertEqual(store.error, "backend rejected")
  }

  @MainActor
  func testBulkDeleteRemoteRejectionPreservesEveryLocalRow() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)
    let locked = task(id: "locked")
    let unlocked = task(id: "unlocked")
    store.incompleteTasks = [locked, unlocked]
    var remoteAttempts = 0
    var localDeletes = 0
    let operations = TasksStore.BulkDeleteOperations(
      loadLocalTasks: { [locked, unlocked] },
      deleteLocalTaskIDs: { _, _ in localDeletes += 1 },
      deleteRemoteTaskIDs: { _, _, _ in
        remoteAttempts += 1
        throw TasksStoreOwnerBoundaryFailure.backendRejected
      }
    )

    let outcome = await store.deleteMultipleTasks(
      ids: [locked.id, unlocked.id],
      expectedOwnerID: "owner-a",
      operations: operations
    )

    XCTAssertEqual(outcome, .remoteFailure(confirmedIDs: []))
    XCTAssertEqual(remoteAttempts, 1)
    XCTAssertEqual(localDeletes, 0)
    XCTAssertEqual(store.incompleteTasks, [locked, unlocked])
  }

  @MainActor
  func testBulkDeleteConfirmsRemoteBeforeCommittingLocalMutation() async {
    let store = TasksStore.shared
    await prepareOwnerBoundaryTest(store: store)
    let first = task(id: "first")
    let second = task(id: "second")
    store.incompleteTasks = [first, second]
    var operationOrder: [String] = []
    let operations = TasksStore.BulkDeleteOperations(
      loadLocalTasks: { [first, second] },
      deleteLocalTaskIDs: { _, _ in operationOrder.append("local") },
      deleteRemoteTaskIDs: { _, _, _ in operationOrder.append("remote") }
    )

    let outcome = await store.deleteMultipleTasks(
      ids: [first.id, second.id],
      expectedOwnerID: "owner-a",
      operations: operations
    )

    XCTAssertEqual(outcome, .deletedEverywhere)
    XCTAssertEqual(operationOrder, ["remote", "local"])
    XCTAssertTrue(store.incompleteTasks.isEmpty)
  }

  @MainActor
  private func task(id: String, completed: Bool = false, dueAt: Date? = nil) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: id,
      completed: completed,
      createdAt: Date(timeIntervalSince1970: 0),
      dueAt: dueAt)
  }

  private func productionSource(_ relativePath: String) throws -> String {
    let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let sourceURL =
      testsURL
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    // omi-test-quality: source-inspection -- static contract: forbids ownerless storage mutation APIs
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  @MainActor
  private func switchOwner(to ownerID: String, defaults: UserDefaults) {
    illegallyMutateOwnerDefaults(to: ownerID, defaults: defaults, notify: true)
  }

  @MainActor
  private func illegallyMutateOwnerDefaults(
    to ownerID: String,
    defaults: UserDefaults,
    notify: Bool = false
  ) {
    // Deliberately bypass the transition authority: these tests simulate an
    // illegal mid-flight defaults mutation and prove captured work fails shut.
    defaults.set(ownerID, forKey: .authUserId)
    if notify {
      NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
    }
  }

  @MainActor
  private func prepareOwnerBoundaryTest(store: TasksStore) async {
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
      finalOwner == "tasks-owner-boundary-bootstrap-a"
      ? "tasks-owner-boundary-bootstrap-b"
      : "tasks-owner-boundary-bootstrap-a"
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
  private func transitionEffectiveOwner(to ownerID: String?) async {
    await transitionEffectiveOwner(authOwnerID: ownerID, automationOverrideID: nil)
  }

  @MainActor
  private func transitionEffectiveOwner(
    authOwnerID: String?,
    automationOverrideID: String?
  ) async {
    let plannedOwner = normalizedOwner(automationOverrideID) ?? normalizedOwner(authOwnerID)
    do {
      _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        allowAutomationOverride: true,
        plannedNextOwner: { _, _ in plannedOwner },
        quiesceVoice: { _, _ in },
        revokeKernelOwner: { _, _ in },
        retargetLocalStorage: { _, _ in },
        ownerDidChange: {
          await MainActor.run {
            NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
          }
        },
        { defaults in
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
      )
    } catch {
      XCTFail("owner transition failed: \(error)")
    }
  }

  private func normalizedOwner(_ ownerID: String?) -> String? {
    guard let normalized = ownerID?.trimmingCharacters(in: .whitespacesAndNewlines),
      !normalized.isEmpty
    else { return nil }
    return normalized
  }

  @MainActor
  private func restore(_ value: Any?, key: String, defaults: UserDefaults) {
    if let value {
      defaults.set(value, forKey: key)
    } else {
      defaults.removeObject(forKey: key)
    }
  }
}
