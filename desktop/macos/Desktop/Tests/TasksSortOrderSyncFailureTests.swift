import XCTest

@testable import Omi_Computer

private actor SortOrderCommitGate {
  private var started = false
  private var released = false

  func pause() async {
    started = true
    while !released { await Task.yield() }
  }

  func waitUntilStarted() async {
    while !started { await Task.yield() }
  }

  func release() { released = true }
}

@MainActor
private final class SortOrderSyncProbe {
  var backendWrites = 0
}

final class TasksSortOrderSyncFailureTests: XCTestCase {
  func testSyncFailureMessageNamesBothFailedDestinations() {
    let failure = TaskSortOrderSyncFailure(
      storageErrorDescription: "database is locked",
      backendErrorDescription: "offline"
    )

    XCTAssertEqual(
      failure.message,
      "Could not save task order to this Mac or Omi Cloud. Retry when your connection is available."
    )
  }

  func testSyncFailureMessageNamesBackendOnlyFailure() {
    let failure = TaskSortOrderSyncFailure(
      storageErrorDescription: nil,
      backendErrorDescription: "offline"
    )

    XCTAssertEqual(
      failure.message,
      "Task order was saved on this Mac, but not synced to Omi Cloud. Retry when your connection is available."
    )
  }

  @MainActor
  func testSortOrderSyncFailuresArePublishedWithPendingRetry() {
    let viewModel = TasksViewModel()

    viewModel.recordSortOrderSyncFailure(
      storageErrorDescription: nil,
      backendErrorDescription: "offline",
      updates: [(id: "task-1", sortOrder: 1000, indentLevel: 0)]
    )

    XCTAssertEqual(
      viewModel.sortOrderSyncFailure?.message,
      "Task order was saved on this Mac, but not synced to Omi Cloud. Retry when your connection is available."
    )
    XCTAssertTrue(viewModel.hasPendingSortOrderRetry)
  }

  @MainActor
  func testSuspendedSortCommitCannotReviveAfterSameOwnerSignsBackIn() async {
    let previousOwner = RuntimeOwnerIdentity.currentOwnerId()
    await transition(to: "sort-owner-a")

    let gate = SortOrderCommitGate()
    let probe = SortOrderSyncProbe()
    let viewModel = TasksViewModel(
      sortOrderSyncOperations: .init(
        updateStorage: { _, _ in await gate.pause() },
        updateBackend: { _, _ in probe.backendWrites += 1 }
      )
    )
    viewModel.recordSortOrderSyncFailure(
      storageErrorDescription: nil,
      backendErrorDescription: "retry",
      updates: [(id: "owner-a-task", sortOrder: 1, indentLevel: 0)]
    )

    let retry = viewModel.retrySortOrderSync()
    await gate.waitUntilStarted()
    await transition(to: nil)
    await transition(to: "sort-owner-a")
    await gate.release()
    await retry?.value

    XCTAssertEqual(probe.backendWrites, 0)
    XCTAssertNil(viewModel.sortOrderSyncFailure)
    XCTAssertFalse(viewModel.hasPendingSortOrderRetry)
    XCTAssertTrue(viewModel.categoryOrder.isEmpty)
    XCTAssertTrue(viewModel.indentLevels.isEmpty)
    await transition(to: previousOwner)
  }

  @MainActor
  func testLegacyOrderingIsAdoptedOnlyByLaunchOwnerBeforeGlobalKeysArePurged() async throws {
    let previousOwner = RuntimeOwnerIdentity.currentOwnerId()
    await transition(to: "sort-legacy-owner")
    let suite = "TasksSortOrderLegacyAdoption.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set([TaskCategory.today.rawValue: ["task-1"]], forKey: "TasksCategoryOrder")
    defaults.set(["task-1": 2], forKey: "TasksIndentLevels")
    defaults.set(true, forKey: "TasksSortOrderMigrated")

    let viewModel = TasksViewModel(
      sortOrderSyncOperations: .init(
        updateStorage: { _, _ in },
        updateBackend: { _, _ in }
      ),
      orderingDefaults: defaults
    )

    XCTAssertEqual(viewModel.categoryOrder[.today], ["task-1"])
    XCTAssertEqual(viewModel.indentLevels["task-1"], 2)
    XCTAssertNil(defaults.object(forKey: "TasksCategoryOrder"))
    XCTAssertNil(defaults.object(forKey: "TasksIndentLevels"))
    XCTAssertNil(defaults.object(forKey: "TasksSortOrderMigrated"))
    XCTAssertNotNil(
      defaults.object(forKey: "TasksCategoryOrder.owner.sort-legacy-owner"))
    XCTAssertFalse(
      defaults.bool(forKey: "TasksSortOrderMigrated.owner.unrelated-owner"),
      "the former global completion bit must not authorize another owner")
    await transition(to: previousOwner)
  }

  @MainActor
  private func transition(to ownerID: String?) async {
    _ = await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      plannedNextOwner: { _, _ in ownerID },
      quiesceVoice: { _, _ in },
      retargetLocalStorage: { _, _ in },
      ownerDidChange: {
        await MainActor.run {
          NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
        }
      }
    ) { defaults in
      defaults.removeObject(forKey: .automationOwnerOverride)
      if let ownerID {
        defaults.set(ownerID, forKey: .authUserId)
      } else {
        defaults.removeObject(forKey: .authUserId)
      }
    }
  }
}
