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
}
