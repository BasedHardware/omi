import XCTest

@testable import Omi_Computer

@MainActor
private final class UnsyncedSyncPauseGate {
  private var reached = false
  private var paused: CheckedContinuation<Void, Never>?
  private var observer: CheckedContinuation<Void, Never>?

  func pause() async {
    await withCheckedContinuation { continuation in
      paused = continuation
      reached = true
      observer?.resume()
      observer = nil
    }
  }

  func waitUntilReached() async {
    guard !reached else { return }
    await withCheckedContinuation { continuation in observer = continuation }
  }

  func release() {
    paused?.resume()
    paused = nil
  }
}

private enum UnsyncedSyncTestFailure: Error {
  case createRejected
}

@MainActor
private final class UnsyncedSyncProbe {
  var admissionCalls = 0
  var loads = 0
  var reads: [Int64] = []
  var creates = 0
  var markedIDs: [Int64] = []
  var flushes = 0
}

@MainActor
final class TaskSyncOwnerTestFixture: Sendable {
  private let originalAuthOwner: String?
  private let originalOverride: String?

  init() {
    // omi-test-quality: shared-defaults -- integration: TasksStore is a private-init singleton whose owner authority reads standard defaults; restore both keys through the exclusive transition boundary
    let defaults = UserDefaults.standard
    originalAuthOwner = defaults.string(forKey: .authUserId)
    originalOverride = defaults.string(forKey: .automationOwnerOverride)
  }

  func establish(ownerID: String?) async throws {
    try await transition(authOwner: ownerID, override: nil)
  }

  func restore() async throws {
    try await transition(authOwner: originalAuthOwner, override: originalOverride)
  }

  private func transition(authOwner: String?, override: String?) async throws {
    let plannedOwner = (override ?? authOwner)?.trimmingCharacters(in: .whitespacesAndNewlines)
    _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      allowAutomationOverride: true,
      plannedNextOwner: { _, _ in plannedOwner },
      quiesceVoice: { _, _ in },
      revokeKernelOwner: { _, _ in },
      retargetLocalStorage: { _, _ in },
      prepareLocalStorageTransition: { _, _ in },
      ownerDidChange: {
        await MainActor.run { NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil) }
      },
      { defaults in
        if let authOwner {
          defaults.set(authOwner, forKey: .authUserId)
        } else {
          defaults.removeObject(forKey: .authUserId)
        }
        if let override {
          defaults.set(override, forKey: .automationOwnerOverride)
        } else {
          defaults.removeObject(forKey: .automationOwnerOverride)
        }
      }
    )
  }
}

final class TasksStoreUnsyncedSyncTests: XCTestCase {
  private enum Suspension: CaseIterable, Equatable {
    case initialAdmission, pendingRead, itemAdmission, currentRead, create, acknowledgment
  }

  @MainActor
  func testRetryUploadsTheLatestPersistedRecordRatherThanTheEnumeratedSnapshot() async throws {
    _ = try await prepareOwnerFixture()
    let store = TasksStore.shared
    let enumerated = record(id: 1, description: "Original task")
    var current = enumerated
    current.description = "Edited while waiting"
    current.completed = true
    current.taskStatus = "completed"
    current.dueAt = Date(timeIntervalSince1970: 1_800_000_000)
    current.recurrenceRule = "weekly"
    current.recurrenceParentId = "original-repeat-task"
    current.goalId = "goal-1"
    current.workstreamId = "workstream-1"
    current.taskOwner = "user"
    current.priority = "high"
    current.dueConfidence = 0.9
    current.provenanceJson = #"[{"kind":"conversation","id":"source-conversation","scope":"canonical"}]"#
    current.sortOrder = 4
    current.indentLevel = 2
    current.conversationId = "source-conversation"
    current.isLocked = true
    current.metadataJson = #"{"note":"fresh metadata"}"#
    let probe = UnsyncedSyncProbe()

    await store.retryUnsyncedItems(
      includeRecent: true,
      operations: UnsyncedTaskSyncOperations(
        allowsUpload: { true },
        loadPending: { includeRecent in
          XCTAssertTrue(includeRecent)
          probe.loads += 1
          return [enumerated]
        },
        reloadCurrent: { id in
          probe.reads.append(id)
          return current
        },
        createRemote: { projection, authorization in
          probe.creates += 1
          XCTAssertEqual(authorization.ownerID, "task-sync-owner-a")
          XCTAssertTrue(RuntimeOwnerIdentity.isAuthorizationCurrent(authorization))
          XCTAssertEqual(projection.description, current.description)
          XCTAssertTrue(projection.completed)
          XCTAssertEqual(projection.dueAt, current.dueAt)
          XCTAssertEqual(projection.recurrenceRule, "weekly")
          XCTAssertEqual(projection.recurrenceParentId, "original-repeat-task")
          XCTAssertEqual(projection.goalId, "goal-1")
          XCTAssertEqual(projection.workstreamId, "workstream-1")
          XCTAssertEqual(projection.owner?.rawValue, "user")
          XCTAssertEqual(projection.priority?.rawValue, "high")
          XCTAssertEqual(projection.status?.rawValue, "completed")
          XCTAssertEqual(projection.dueConfidence, 0.9)
          XCTAssertEqual(projection.provenance?.count, 1)
          XCTAssertEqual(projection.provenance?.first?.id, "source-conversation")
          XCTAssertEqual(projection.provenance?.first?.kind.rawValue, "conversation")
          XCTAssertEqual(projection.provenance?.first?.scope.rawValue, "canonical")
          XCTAssertEqual(projection.sortOrder, 4)
          XCTAssertEqual(projection.indentLevel, 2)
          XCTAssertEqual(projection.conversationId, "source-conversation")
          XCTAssertEqual(projection.isLocked, true)
          XCTAssertEqual(projection.metadataBox?.value?["note"] as? String, "fresh metadata")
          return self.remoteTask(id: "remote-1", description: projection.description, completed: projection.completed)
        },
        markSynced: { id, remoteID, authorization in
          XCTAssertEqual(remoteID, "remote-1")
          try authorization.require()
          probe.markedIDs.append(id)
        },
        flushDeletions: { probe.flushes += 1 }
      )
    )

    XCTAssertEqual(probe.loads, 1)
    XCTAssertEqual(probe.reads, [1])
    XCTAssertEqual(probe.creates, 1)
    XCTAssertEqual(probe.markedIDs, [1])
    XCTAssertEqual(probe.flushes, 1)
  }

  @MainActor
  func testRetrySkipsMissingDeletedSyncedAndAlreadyLinkedCurrentRows() async throws {
    _ = try await prepareOwnerFixture()
    let probe = UnsyncedSyncProbe()
    let candidates = [record(id: nil)] + (1...5).map { record(id: Int64($0)) }
    await TasksStore.shared.retryUnsyncedItems(
      operations: UnsyncedTaskSyncOperations(
        allowsUpload: { true },
        loadPending: { _ in candidates },
        reloadCurrent: { id in
          probe.reads.append(id)
          var current = self.record(id: id)
          switch id {
          case 1: return nil
          case 2: current.deleted = true
          case 3: current.backendSynced = true
          case 4: current.backendId = "already-linked"
          default: break
          }
          return current
        },
        createRemote: { _, _ in
          probe.creates += 1
          return self.remoteTask(id: "remote-5")
        },
        markSynced: { id, remoteID, _ in
          XCTAssertEqual(remoteID, "remote-5")
          probe.markedIDs.append(id)
        },
        flushDeletions: { probe.flushes += 1 }
      )
    )
    XCTAssertEqual(probe.reads, [1, 2, 3, 4, 5])
    XCTAssertEqual(probe.creates, 1)
    XCTAssertEqual(probe.markedIDs, [5])
  }

  @MainActor
  func testRejectedCreateRemainsUnsyncedAndDoesNotBlockTheNextItem() async throws {
    _ = try await prepareOwnerFixture()
    let probe = UnsyncedSyncProbe()
    let candidates = [record(id: 1, description: "Rejected"), record(id: 2, description: "Accepted")]
    await TasksStore.shared.retryUnsyncedItems(
      operations: UnsyncedTaskSyncOperations(
        allowsUpload: { true },
        loadPending: { _ in candidates },
        reloadCurrent: { id in candidates.first { $0.id == id } },
        createRemote: { projection, _ in
          probe.creates += 1
          if projection.description == "Rejected" { throw UnsyncedSyncTestFailure.createRejected }
          return self.remoteTask(id: "remote-2")
        },
        markSynced: { id, _, _ in probe.markedIDs.append(id) },
        flushDeletions: { probe.flushes += 1 }
      )
    )
    XCTAssertEqual(probe.creates, 2)
    XCTAssertEqual(probe.markedIDs, [2])
    XCTAssertEqual(probe.flushes, 1)
  }

  @MainActor
  func testMalformedProvenanceIsNotUploadedLossilyOrMarkedSynced() async throws {
    _ = try await prepareOwnerFixture()
    let probe = UnsyncedSyncProbe()
    var malformed = record(id: 1)
    malformed.provenanceJson = #"[{"kind":"conversation"}]"#
    let valid = record(id: 2)
    await TasksStore.shared.retryUnsyncedItems(
      operations: UnsyncedTaskSyncOperations(
        allowsUpload: { true },
        loadPending: { _ in [malformed, valid] },
        reloadCurrent: { id in id == 1 ? malformed : valid },
        createRemote: { _, _ in
          probe.creates += 1
          return self.remoteTask(id: "remote-2")
        },
        markSynced: { id, _, _ in probe.markedIDs.append(id) },
        flushDeletions: {}
      )
    )
    XCTAssertEqual(probe.creates, 1)
    XCTAssertEqual(probe.markedIDs, [2])
  }

  @MainActor
  func testConcurrentRetryDoesNotUploadTwiceAndItsLeaseReleasesAfterCompletion() async throws {
    _ = try await prepareOwnerFixture()
    let gate = UnsyncedSyncPauseGate()
    let probe = UnsyncedSyncProbe()
    var current = record(id: 1)
    let operations = UnsyncedTaskSyncOperations(
      allowsUpload: { true },
      loadPending: { _ in
        probe.loads += 1
        return [current]
      },
      reloadCurrent: { _ in current },
      createRemote: { _, _ in
        probe.creates += 1
        await gate.pause()
        return self.remoteTask(id: "remote-1")
      },
      markSynced: { id, remoteID, _ in
        probe.markedIDs.append(id)
        current.backendId = remoteID
        current.backendSynced = true
      },
      flushDeletions: { probe.flushes += 1 }
    )
    let first = Task { await TasksStore.shared.retryUnsyncedItems(operations: operations) }
    defer { gate.release() }
    await gate.waitUntilReached()
    await TasksStore.shared.retryUnsyncedItems(operations: operations)
    XCTAssertEqual(probe.loads, 1)
    XCTAssertEqual(probe.creates, 1)
    gate.release()
    await first.value
    await TasksStore.shared.retryUnsyncedItems(operations: operations)
    XCTAssertEqual(probe.loads, 2, "a finished invocation must release its active-retry lease")
    XCTAssertEqual(probe.creates, 1)
    XCTAssertEqual(probe.markedIDs, [1])
  }

  @MainActor
  func testOwnerSwitchRevokesWorkSuspendedAtEveryRetryBoundary() async throws {
    let fixture = try await prepareOwnerFixture()
    for suspension in Suspension.allCases {
      try await assertRevokedRetry(suspension: suspension, reauthenticateSameOwner: false, fixture: fixture)
    }
  }

  @MainActor
  func testSameUIDReauthenticationRevokesWorkSuspendedAtEveryRetryBoundary() async throws {
    let fixture = try await prepareOwnerFixture()
    for suspension in Suspension.allCases {
      try await assertRevokedRetry(suspension: suspension, reauthenticateSameOwner: true, fixture: fixture)
    }
  }

  @MainActor
  private func assertRevokedRetry(
    suspension: Suspension,
    reauthenticateSameOwner: Bool,
    fixture: TaskSyncOwnerTestFixture
  ) async throws {
    try await fixture.establish(ownerID: "task-sync-owner-a")
    let store = TasksStore.shared
    store.resetSessionState()
    let gate = UnsyncedSyncPauseGate()
    let probe = UnsyncedSyncProbe()
    let candidate = record(id: 1)
    let originalAuthorization = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let operations = UnsyncedTaskSyncOperations(
      allowsUpload: {
        probe.admissionCalls += 1
        if (suspension == .initialAdmission && probe.admissionCalls == 1)
          || (suspension == .itemAdmission && probe.admissionCalls == 2)
        {
          await gate.pause()
        }
        return true
      },
      loadPending: { _ in
        probe.loads += 1
        if suspension == .pendingRead { await gate.pause() }
        return [candidate]
      },
      reloadCurrent: { id in
        probe.reads.append(id)
        if suspension == .currentRead { await gate.pause() }
        return candidate
      },
      createRemote: { _, authorization in
        XCTAssertEqual(authorization, originalAuthorization)
        probe.creates += 1
        if suspension == .create { await gate.pause() }
        return self.remoteTask(id: "obsolete-remote")
      },
      markSynced: { id, _, authorization in
        if suspension == .acknowledgment { await gate.pause() }
        try authorization.require()
        probe.markedIDs.append(id)
      },
      flushDeletions: { probe.flushes += 1 }
    )
    let work = Task { await store.retryUnsyncedItems(operations: operations) }
    await gate.waitUntilReached()
    do {
      // Reapplying the same owner is deliberately not a new authenticated
      // session. Cross the signed-out boundary before signing back into A.
      if reauthenticateSameOwner { try await fixture.establish(ownerID: nil) }
      try await fixture.establish(ownerID: reauthenticateSameOwner ? "task-sync-owner-a" : "task-sync-owner-b")
      let replacementAuthorization = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
      XCTAssertNotEqual(originalAuthorization.authorizationGeneration, replacementAuthorization.authorizationGeneration)
      XCTAssertFalse(RuntimeOwnerIdentity.isAuthorizationCurrent(originalAuthorization))
    } catch {
      gate.release()
      await work.value
      throw error
    }
    let sentinel = remoteTask(id: "replacement-owner-visible-task")
    store.incompleteTasks = [sentinel]
    gate.release()
    await work.value

    XCTAssertEqual(
      probe.creates, suspension == .create || suspension == .acknowledgment ? 1 : 0,
      "unexpected create after \(suspension)")
    XCTAssertTrue(probe.markedIDs.isEmpty, "revoked receipt cannot mark local state after \(suspension)")
    XCTAssertEqual(probe.flushes, 0, "revoked work cannot continue into deletion flush after \(suspension)")
    XCTAssertEqual(store.incompleteTasks.map(\.id), [sentinel.id])
    XCTAssertNil(store.error)
  }

  private func record(id: Int64?, description: String = "Pending task") -> ActionItemRecord {
    ActionItemRecord(id: id, description: description, source: "manual")
  }

  private func remoteTask(id: String, description: String = "Uploaded task", completed: Bool = false) -> TaskActionItem
  {
    TaskActionItem(
      id: id, description: description, completed: completed,
      createdAt: Date(timeIntervalSince1970: 1_800_000_000))
  }

  @MainActor
  private func prepareOwnerFixture() async throws -> TaskSyncOwnerTestFixture {
    let fixture = TaskSyncOwnerTestFixture()
    addTeardownBlock { @MainActor in
      try await fixture.restore()
      TasksStore.shared.resetSessionState()
    }
    try await fixture.establish(ownerID: "task-sync-owner-a")
    TasksStore.shared.resetSessionState()
    return fixture
  }
}
