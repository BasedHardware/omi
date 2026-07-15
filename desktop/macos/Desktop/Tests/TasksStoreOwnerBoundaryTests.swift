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
  var migrations = 0
}

final class TasksStoreOwnerBoundaryTests: XCTestCase {
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
  func testSuspendedStartupMigrationCannotContinueIntoReplacementOwner() async {
    let defaults = UserDefaults.standard
    let fullSyncKey = "tasksFullSyncCompleted_v9_owner-a"
    let ownerAMigrationKey = "stagedTasksMigrationCompleted_v4_owner-a"
    let ownerBMigrationKey = "stagedTasksMigrationCompleted_v4_owner-b"
    let ownerAConversationKey = "conversationItemsMigrationCompleted_v4_owner-a"
    let keys = [fullSyncKey, ownerAMigrationKey, ownerBMigrationKey, ownerAConversationKey]
    let previousValues = Dictionary(uniqueKeysWithValues: keys.map { ($0, defaults.object(forKey: $0)) })
    let store = TasksStore.shared
    defer {
      for key in keys { restore(previousValues[key] ?? nil, key: key, defaults: defaults) }
    }
    await prepareOwnerBoundaryTest(store: store)
    defaults.set(true, forKey: fullSyncKey)
    defaults.removeObject(forKey: ownerAMigrationKey)
    defaults.removeObject(forKey: ownerBMigrationKey)
    defaults.removeObject(forKey: ownerAConversationKey)

    let gate = TasksStorePauseGate()
    let probe = TasksStoreOperationProbe()
    let operations = TasksStore.OwnerBoundOperations(
      migrateAI: { ownerID in
        XCTAssertEqual(ownerID, "owner-a")
        probe.remoteRequests += 1
        await gate.pause()
      },
      migrateConversation: { _ in probe.migrations += 1 })

    let maintenanceTasks = store.scheduleStartupMaintenanceIfNeeded(
      relevanceBackfill: { _ in },
      operations: operations)
    await gate.waitUntilStarted()
    switchOwner(to: "owner-b", defaults: defaults)
    await gate.release()
    for task in maintenanceTasks { await task.value }

    XCTAssertEqual(probe.remoteRequests, 1)
    XCTAssertEqual(probe.migrations, 0)
    XCTAssertTrue(defaults.bool(forKey: ownerAMigrationKey))
    XCTAssertFalse(defaults.bool(forKey: ownerBMigrationKey))
    XCTAssertFalse(defaults.bool(forKey: ownerAConversationKey))
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
  private func task(id: String, completed: Bool = false) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: id,
      completed: completed,
      createdAt: Date(timeIntervalSince1970: 0))
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
