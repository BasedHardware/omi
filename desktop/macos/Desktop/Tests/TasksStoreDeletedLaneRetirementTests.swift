import XCTest

@testable import Omi_Computer

/// Regression coverage for the deleted lane's retirement contract.
///
/// `TaskActionItem.isRetired` re-derives retirement from the response body:
/// `deleted == true`, or a canonical status of `cancelled`/`superseded`. Its own
/// doc comment records that list responses may omit legacy `deleted` and project
/// retirement through canonical lifecycle status — and that status vocabulary is
/// open, so any value outside those two reads as live.
///
/// `ActionItemRecord.from(_:)` persists `deleted: item.isRetired`, and the
/// `.deleted` scope query reads that column back. So a row arriving from the
/// deleted lane without either marker was written to the local cache as **live**:
/// the deleted list came back empty (`Fetched 100 deleted tasks` /
/// `Showing 0 deleted tasks` in the field log) and the same rows reappeared as
/// live tasks. Deleting a task on one device and then signing in on a new
/// machine un-deleted it.
///
/// The lane was therefore treated as the authority and `fetchDeletedPage`
/// stamped every row it returned. That went wrong in the other direction, and
/// far more expensively: `GET /v1/action-items` has no `deleted` parameter.
/// FastAPI drops the unknown query item and the handler's stream skips
/// soft-deleted documents outright, so the "deleted lane" answered with the
/// owner's *live* first page — and each visit to Removed tombstoned a hundred
/// live tasks in the local cache. Completing one of them from a chat task card
/// read the tombstone back and rendered "Task is no longer available" over the
/// task the reader had just ticked.
///
/// So the contract is now the other way round: the lane keeps the rows the
/// response itself reports retired and drops the rest. Showing fewer rows in
/// Removed is a gap; manufacturing retirement is data loss.
@MainActor
private final class DeletedLaneProbe {
  var syncedPages: [[TaskActionItem]] = []
  /// Stand-in for the SQLite cache. `syncTaskActionItems` persists
  /// `deleted: item.isRetired` and the `.deleted` scope query reads that column,
  /// so only rows the client considers retired come back in the deleted list.
  var cache: [TaskActionItem] = []
}

final class TasksStoreDeletedLaneRetirementTests: XCTestCase {

  /// The regression this file now guards: a row the response reports as **live**
  /// must not be written to the local cache retired, however it was fetched.
  ///
  /// This is the shape the real endpoint returns for every row, because it
  /// ignores `deleted=true` entirely. Stamping it retired is what tombstoned
  /// the owner's live tasks a page at a time.
  @MainActor
  func testLiveRowFromTheDeletedLaneIsNeverTombstonedLocally() async throws {
    let store = TasksStore.shared
    await prepareStore(store)

    let serverRow = task(id: "still-open", taskStatus: "active")
    XCTAssertFalse(
      serverRow.isRetired,
      "fixture must reproduce what the endpoint actually answers with: an ordinary live task")

    let probe = DeletedLaneProbe()
    let operations = TasksStore.OwnerBoundOperations(
      fetchDeletedPage: { _, _, _ in .init(items: [serverRow], hasMore: false) },
      syncPage: { items, _, _ in
        probe.syncedPages.append(items)
        probe.cache = items.filter { $0.isRetired }
      },
      loadDeleted: { _ in probe.cache })

    await store.loadDeletedTasks(operations: operations)

    let synced = probe.syncedPages.first ?? []
    XCTAssertTrue(
      synced.allSatisfy { !$0.isRetired },
      "a live row must reach the cache live — writing it retired is what took the owner's tasks away")
    XCTAssertTrue(
      probe.cache.isEmpty,
      "nothing may be tombstoned locally on the strength of the lane it was fetched from")
    XCTAssertTrue(
      store.deletedTasks.isEmpty,
      "Removed showing nothing is the honest answer here; showing live tasks is not")
  }

  /// A row the server already marked retired keeps its own marker: the lane
  /// states retirement, it does not restate or overwrite provenance.
  @MainActor
  func testAlreadyRetiredRowIsPassedThroughUnchanged() async throws {
    let store = TasksStore.shared
    await prepareStore(store)

    let serverRow = task(id: "cancelled-upstream", taskStatus: "cancelled")
    XCTAssertTrue(serverRow.isRetired, "fixture must already satisfy the projection")

    let probe = DeletedLaneProbe()
    let operations = TasksStore.OwnerBoundOperations(
      fetchDeletedPage: { _, _, _ in .init(items: [serverRow], hasMore: false) },
      syncPage: { items, _, _ in
        probe.syncedPages.append(items)
        probe.cache = items.filter { $0.isRetired }
      },
      loadDeleted: { _ in probe.cache })

    await store.loadDeletedTasks(operations: operations)

    let synced = try XCTUnwrap(probe.syncedPages.first)
    XCTAssertEqual(synced, [serverRow], "an already-retired row must round-trip untouched")
    XCTAssertEqual(store.deletedTasks.map(\.id), ["cancelled-upstream"])
  }

  // MARK: - Helpers

  @MainActor
  private func task(id: String, taskStatus: String? = nil) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: id,
      completed: false,
      createdAt: Date(timeIntervalSince1970: 0),
      taskStatus: taskStatus)
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
      finalOwner == "deleted-lane-bootstrap-a"
      ? "deleted-lane-bootstrap-b"
      : "deleted-lane-bootstrap-a"
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

  private func normalizedOwner(_ value: String?) -> String? {
    guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines),
      !trimmed.isEmpty
    else { return nil }
    return trimmed
  }
}
