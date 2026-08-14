import XCTest

@testable import Omi_Computer

/// The resurrection contract. Deleting a synced task used to hard-delete the local row and
/// fire one unretried backend call; if that call failed, nothing anywhere remembered the
/// deletion and the next cloud hydration re-inserted the task — 450 of them came back at
/// once after a reinstall. A deletion the server has not acknowledged must therefore leave
/// a tombstone that hydration refuses to overwrite and a retry pass can flush.
final class ActionItemDeletionSyncTests: XCTestCase {
  private var testUserId = ""
  private var userDir: URL?

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "deletion-sync-test-\(UUID().uuidString)"
    try await RewindDatabase.shared.switchUser(to: testUserId)
    await ActionItemStorage.shared.invalidateCache()
    let appSupport = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first)
    userDir =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }

  override func tearDown() async throws {
    await ActionItemStorage.shared.invalidateCache()
    await RewindDatabase.shared.close()
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    RewindDatabase.currentUserId = nil
    try await super.tearDown()
  }

  private func serverTask(
    id: String,
    deleted: Bool? = false,
    updatedAt: Date = Date(timeIntervalSince1970: 1_750_000_000)
  ) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: "task \(id)",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 1_750_000_000),
      updatedAt: updatedAt,
      dueAt: nil,
      deleted: deleted,
      taskStatus: nil
    )
  }

  /// The core of the bug: the server still returning the task is the *expected* state
  /// while the deletion is unacknowledged, and it must not win.
  func testCloudHydrationDoesNotResurrectAPendingDeletion() async throws {
    try await ActionItemStorage.shared.syncTaskActionItems(
      [serverTask(id: "backend-1")], authorization: .unrestricted)
    try await ActionItemStorage.shared.markActionItemDeletedPendingBackendSync(
      backendId: "backend-1", authorization: .unrestricted)

    // Reinstall/refresh shape: the server, never having heard the delete, sends it again.
    try await ActionItemStorage.shared.syncTaskActionItems(
      [serverTask(id: "backend-1")], authorization: .unrestricted)

    let pending = try await ActionItemStorage.shared.getPendingBackendDeletionIds()
    XCTAssertEqual(pending, ["backend-1"], "hydration must not clear an unacknowledged tombstone")

    let visible = try await ActionItemStorage.shared.getFilteredActionItems(
      limit: 50, completedStates: [false])
    XCTAssertFalse(
      visible.contains { (item: TaskActionItem) in item.id == "backend-1" },
      "a tombstoned task must stay invisible even after the server re-sends it")
  }

  /// The acknowledgement clears the pending flag — and nothing else. Purging the row here
  /// (the old shape) destroyed the only record of *who* retired the task: the backend has no
  /// `deleted_by` field, so the row the Removed lane re-fetches always reports nil.
  func testAcknowledgementClearsPendingButKeepsUserProvenance() async throws {
    try await ActionItemStorage.shared.syncTaskActionItems(
      [serverTask(id: "backend-2")], authorization: .unrestricted)
    try await ActionItemStorage.shared.markActionItemDeletedPendingBackendSync(
      backendId: "backend-2", authorization: .unrestricted)

    let beforeAck = try await ActionItemStorage.shared.getPendingBackendDeletionIds()
    XCTAssertEqual(beforeAck, ["backend-2"])

    // The ack path (deleteTask / flushPendingBackendDeletions after a 2xx).
    try await ActionItemStorage.shared.markActionItemDeletionAcknowledged(
      backendId: "backend-2", authorization: .unrestricted)

    let pending = try await ActionItemStorage.shared.getPendingBackendDeletionIds()
    XCTAssertTrue(pending.isEmpty, "an acknowledged deletion must leave nothing to flush")

    let record = try await ActionItemStorage.shared.getActionItemByBackendId("backend-2")
    XCTAssertEqual(record?.deleted, true, "the ack confirms the retirement, it does not undo it")
    XCTAssertEqual(
      record?.deletedBy, "user",
      "'Removed by me' and the extraction dedup list both read this column")

    let visible = try await ActionItemStorage.shared.getFilteredActionItems(
      limit: 50, completedStates: [false])
    XCTAssertFalse(
      visible.contains { (item: TaskActionItem) in item.id == "backend-2" },
      "a confirmed tombstone must stay out of the live lane")
  }

  /// The Removed lane refetches deleted tasks from the server and syncs them back in. That
  /// hydration used to take the server's absent `deleted_by` as nil, re-filing every user
  /// deletion under "Removed by AI" and emptying the extraction dedup list.
  func testDeletedPageHydrationKeepsUserProvenance() async throws {
    try await ActionItemStorage.shared.syncTaskActionItems(
      [serverTask(id: "backend-5")], authorization: .unrestricted)
    try await ActionItemStorage.shared.markActionItemDeletedPendingBackendSync(
      backendId: "backend-5", authorization: .unrestricted)
    try await ActionItemStorage.shared.markActionItemDeletionAcknowledged(
      backendId: "backend-5", authorization: .unrestricted)

    // What `loadDeletedTasks` syncs back: the server's soft-deleted row, no deleted_by.
    // Stamped after the local ack so the 60s optimistic-update guard does not skip it.
    try await ActionItemStorage.shared.syncTaskActionItems(
      [serverTask(id: "backend-5", deleted: true, updatedAt: Date().addingTimeInterval(300))],
      authorization: .unrestricted)

    let record = try await ActionItemStorage.shared.getActionItemByBackendId("backend-5")
    XCTAssertEqual(record?.deleted, true)
    XCTAssertEqual(
      record?.deletedBy, "user",
      "hydration must not re-attribute a user deletion to the AI")

    let userDeleted = try await ActionItemStorage.shared.getRecentDeletedTasks(deletedBy: "user")
    XCTAssertTrue(
      userDeleted.contains { $0.description == "task backend-5" },
      "task extraction reads this list to stop re-suggesting what the user removed")
  }

  /// The mirror case: a task the server reports as live again has no retirement left to
  /// attribute, so stale provenance must not survive the un-delete.
  func testHydrationClearsProvenanceWhenTheServerRevivesTheTask() async throws {
    try await ActionItemStorage.shared.syncTaskActionItems(
      [serverTask(id: "backend-6")], authorization: .unrestricted)
    try await ActionItemStorage.shared.markActionItemDeletedPendingBackendSync(
      backendId: "backend-6", authorization: .unrestricted)
    try await ActionItemStorage.shared.markActionItemDeletionAcknowledged(
      backendId: "backend-6", authorization: .unrestricted)

    try await ActionItemStorage.shared.syncTaskActionItems(
      [serverTask(id: "backend-6", deleted: false, updatedAt: Date().addingTimeInterval(300))],
      authorization: .unrestricted)

    let record = try await ActionItemStorage.shared.getActionItemByBackendId("backend-6")
    XCTAssertEqual(record?.deleted, false)
    XCTAssertNil(record?.deletedBy, "a live task carries no deletion provenance")
  }

  /// The full-sync purge cleans up acknowledged soft-deletes; it must not eat the durable
  /// record of deletions the server has not confirmed yet.
  func testFullSyncPurgeKeepsPendingTombstones() async throws {
    try await ActionItemStorage.shared.syncTaskActionItems(
      [serverTask(id: "backend-3"), serverTask(id: "backend-4", deleted: true)],
      authorization: .unrestricted)
    try await ActionItemStorage.shared.markActionItemDeletedPendingBackendSync(
      backendId: "backend-3", authorization: .unrestricted)

    _ = try await ActionItemStorage.shared.purgeAllSoftDeletedItems(authorization: .unrestricted)

    let pending = try await ActionItemStorage.shared.getPendingBackendDeletionIds()
    XCTAssertEqual(
      pending, ["backend-3"],
      "purge must remove server-deleted rows but keep unacknowledged tombstones")
  }
}
