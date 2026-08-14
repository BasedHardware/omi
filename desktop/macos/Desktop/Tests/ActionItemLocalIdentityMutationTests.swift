import XCTest

@testable import Omi_Computer

/// Regression coverage for mutating unsynced tasks surfaced with a
/// "local_<rowid>" id.
///
/// A task created offline (or whose create POST failed) has no `backendId`
/// yet, so `toTaskActionItem()` surfaces it as "local_<rowid>". The store's
/// mutation paths used to address SQLite purely by the `backendId` column:
/// delete matched zero rows and silently no-opped (the "deleted" task
/// resurrected on next launch), and toggle/update threw `recordNotFound`.
final class ActionItemLocalIdentityMutationTests: XCTestCase {
  private let testUserId = "local-identity-test-\(UUID().uuidString)"
  private lazy var userDir: URL? = {
    guard
      let appSupport = FileManager.default
        .urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    else { return nil }
    return
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }()

  override func setUp() async throws {
    try await super.setUp()
    try await RewindDatabase.shared.switchUser(to: testUserId)
    await ActionItemStorage.shared.invalidateCache()
  }

  override func tearDown() async throws {
    await ActionItemStorage.shared.invalidateCache()
    await RewindDatabase.shared.close()
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    RewindDatabase.currentUserId = nil
    try await super.tearDown()
  }

  func testSurfacedIdParsing() {
    XCTAssertEqual(ActionItemTaskIdentity(surfacedId: "local_42"), .localRow(42))
    XCTAssertTrue(ActionItemTaskIdentity(surfacedId: "local_42").isLocalOnly)
    XCTAssertEqual(ActionItemTaskIdentity(surfacedId: "abc123"), .backend("abc123"))
    XCTAssertFalse(ActionItemTaskIdentity(surfacedId: "abc123").isLocalOnly)
    // A malformed "local_" id that is not a rowid falls back to backend-id
    // matching, preserving the pre-fix lookup behavior for odd backend ids.
    XCTAssertEqual(ActionItemTaskIdentity(surfacedId: "local_x"), .backend("local_x"))
  }

  func testDeleteResolvesLocalSurfacedId() async throws {
    // This isolated storage fixture deliberately has no runtime owner.
    let inserted = try await ActionItemStorage.shared.insertLocalActionItem(
      ActionItemRecord(description: "unsynced task to delete", source: "test"),
      authorization: .unrestricted)
    let surfacedId = inserted.toTaskActionItem().id
    XCTAssertTrue(surfacedId.hasPrefix("local_"), "unsynced row must surface a local_ id")

    try await ActionItemStorage.shared.deleteActionItemByBackendId(
      surfacedId, deletedBy: "user", authorization: .unrestricted)

    let after = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: surfacedId)
    XCTAssertNil(after, "delete by surfaced local_ id must remove the SQLite row, not no-op")
  }

  func testToggleCompletionResolvesLocalSurfacedId() async throws {
    let inserted = try await ActionItemStorage.shared.insertLocalActionItem(
      ActionItemRecord(description: "unsynced task to toggle", source: "test"),
      authorization: .unrestricted)
    let surfacedId = inserted.toTaskActionItem().id
    XCTAssertTrue(surfacedId.hasPrefix("local_"))

    try await ActionItemStorage.shared.updateCompletionStatus(
      backendId: surfacedId, completed: true, authorization: .unrestricted)

    let after = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: surfacedId)
    XCTAssertEqual(after?.completed, true, "toggle by surfaced local_ id must persist")
  }

  func testUpdateFieldsResolvesLocalSurfacedId() async throws {
    let inserted = try await ActionItemStorage.shared.insertLocalActionItem(
      ActionItemRecord(description: "unsynced task to edit", source: "test"),
      authorization: .unrestricted)
    let surfacedId = inserted.toTaskActionItem().id
    XCTAssertTrue(surfacedId.hasPrefix("local_"))

    try await ActionItemStorage.shared.updateActionItemFields(
      backendId: surfacedId, description: "edited description", authorization: .unrestricted)

    let after = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: surfacedId)
    XCTAssertEqual(after?.description, "edited description", "edit by surfaced local_ id must persist")
  }

  /// Undoing the delete of a local-only task must re-insert exactly one UNSYNCED
  /// row — not fabricate a synced backend id from the "local_<rowid>" placeholder
  /// and not create a duplicate. The pending create-sync remains the single
  /// writer that gives it a real backend id.
  func testRestoreLocalOnlyTaskReinsertsSingleUnsyncedRow() async throws {
    let inserted = try await ActionItemStorage.shared.insertLocalActionItem(
      ActionItemRecord(description: "offline completed task", source: "test"),
      authorization: .unrestricted)
    let surfacedId = inserted.toTaskActionItem().id
    XCTAssertTrue(surfacedId.hasPrefix("local_"))

    // Completed offline, before any sync.
    try await ActionItemStorage.shared.updateCompletionStatus(
      backendId: surfacedId, completed: true, authorization: .unrestricted)
    guard let taskToRestore = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: surfacedId)
    else { return XCTFail("expected the completed local-only task") }
    XCTAssertTrue(taskToRestore.completed)

    // Delete removes the local row (deleteTask hard-deletes for a local_ id).
    try await ActionItemStorage.shared.deleteActionItemByBackendId(
      surfacedId, deletedBy: "user", authorization: .unrestricted)

    // Restore via the store's local-only restore record. localOnlyRestoreRecord
    // is a @MainActor static, so the call hops to the main actor (await).
    let record = await TasksStore.localOnlyRestoreRecord(from: taskToRestore)
    XCTAssertNil(record.backendId, "must not carry the local_ placeholder as a backend id")
    XCTAssertFalse(record.backendSynced, "restored local-only task stays unsynced")
    XCTAssertEqual(record.completed, true, "completion state is preserved across restore")
    try await ActionItemStorage.shared.insertLocalActionItem(record, authorization: .unrestricted)

    let restored = try await ActionItemStorage.shared.getLocalActionItems(
      limit: 100, offset: 0, completed: true)
    let matches = restored.filter { $0.description == "offline completed task" }
    XCTAssertEqual(matches.count, 1, "restore must produce exactly one row, never a duplicate")
    XCTAssertTrue(
      matches[0].id.hasPrefix("local_"),
      "restored task stays an unsynced local_ task, not a fabricated backend id")
  }
}
