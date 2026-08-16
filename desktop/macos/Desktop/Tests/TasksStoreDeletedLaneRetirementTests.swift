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
/// The lane is the authority on retirement, so `fetchDeletedPage` stamps it
/// rather than asking the projection to infer it.
@MainActor
private final class DeletedLaneProbe {
  var syncedPages: [[TaskActionItem]] = []
  /// Stand-in for the SQLite cache. `syncTaskActionItems` persists
  /// `deleted: item.isRetired` and the `.deleted` scope query reads that column,
  /// so only rows the client considers retired come back in the deleted list.
  var cache: [TaskActionItem] = []
}

final class TasksStoreDeletedLaneRetirementTests: XCTestCase {

  /// The regression: a deleted-lane row that carries neither legacy `deleted`
  /// nor a recognized retired status must still reach the cache retired.
  @MainActor
  func testDeletedLaneRowIsRetiredBeforeItReachesTheLocalCache() async throws {
    let store = TasksStore.shared
    await prepareStore(store)

    let serverRow = task(id: "deleted-on-phone", taskStatus: "active")
    XCTAssertFalse(
      serverRow.isRetired,
      "fixture must reproduce the server shape that made this bug: retired by lane, live by projection")

    let probe = DeletedLaneProbe()
    let operations = TasksStore.OwnerBoundOperations(
      fetchDeletedPage: { _, _, _ in .init(items: [serverRow], hasMore: false) },
      syncPage: { items, _, _ in
        probe.syncedPages.append(items)
        probe.cache = items.filter { $0.isRetired }
      },
      loadDeleted: { _ in probe.cache })

    await store.loadDeletedTasks(operations: operations)

    let synced = try XCTUnwrap(probe.syncedPages.first, "the deleted page must be synced to the cache")
    XCTAssertEqual(synced.map(\.id), ["deleted-on-phone"])
    XCTAssertTrue(
      synced.allSatisfy { $0.isRetired },
      "a row from the deleted lane must never be written to the local cache as live — that is the resurrection")
    XCTAssertEqual(
      store.deletedTasks.map(\.id),
      ["deleted-on-phone"],
      "the retired row must show up in the deleted list instead of vanishing from every surface")
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
