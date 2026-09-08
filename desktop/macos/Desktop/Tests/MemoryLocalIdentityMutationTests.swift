import XCTest

@testable import Omi_Computer

/// Regression coverage for local-only memories surfaced to the desktop UI as
/// `local_<rowid>`. These rows do not have server IDs, so they must be mutated
/// through their SQLite row and never sent to the backend delete endpoint.
@MainActor
final class MemoryLocalIdentityMutationTests: XCTestCase {
  private var userDir: URL?

  override func setUp() async throws {
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memory-local-identity")
    userDir = fixture.userDir
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
  }

  func testSurfacedIdParsing() {
    XCTAssertEqual(MemoryIdentity(surfacedId: "local_42"), .localRow(42))
    XCTAssertTrue(MemoryIdentity(surfacedId: "local_42").isLocalOnly)
    XCTAssertEqual(MemoryIdentity(surfacedId: "memory-42"), .backend("memory-42"))
    XCTAssertFalse(MemoryIdentity(surfacedId: "memory-42").isLocalOnly)
    XCTAssertEqual(MemoryIdentity(surfacedId: "local_invalid"), .backend("local_invalid"))
  }

  func testLocalOnlyDeleteStaysDeletedAcrossStorageReloadAndUndoRestoresIt() async throws {
    let localMemory = try await insertLocalMemory(content: "unsynced memory to delete")
    let surfaced = try XCTUnwrap(localMemory.toServerMemory())
    XCTAssertTrue(surfaced.id.hasPrefix("local_"))

    try await MemoryStorage.shared.deleteMemory(surfacedId: surfaced.id)
    let afterDelete = try await MemoryStorage.shared.getLocalMemories(limit: 100)
    XCTAssertFalse(afterDelete.contains { $0.id == surfaced.id }, "local delete must persist in SQLite across reloads")

    try await MemoryStorage.shared.restoreMemory(surfacedId: surfaced.id)
    let afterUndo = try await MemoryStorage.shared.getLocalMemories(limit: 100)
    XCTAssertTrue(afterUndo.contains { $0.id == surfaced.id }, "undo must restore the same local-only memory")
  }

  func testLocalOnlyDeleteNeverCallsServerAndBackendDeleteStillDoes() async throws {
    let localMemory = try await insertLocalMemory(content: "local memory")
    let local = try XCTUnwrap(localMemory.toServerMemory())
    let server = makeMemory(id: "server-memory")
    try await MemoryStorage.shared.syncServerMemories([server])

    let requests = DeleteRequestRecorder()
    let viewModel = MemoriesViewModel(deleteMemoryRequest: { id in
      await requests.record(id)
    })

    viewModel.memories = [local]
    await viewModel.deleteMemory(local)
    await viewModel.confirmDelete().value
    let localRequestIDs = await requests.ids
    let localRowsAfterDelete = try await MemoryStorage.shared.getLocalMemories(limit: 100)
    XCTAssertEqual(localRequestIDs, [])
    XCTAssertFalse(
      localRowsAfterDelete.contains { $0.id == local.id },
      "local-only delete must remain absent after the view-model finalizes it")

    viewModel.memories = [server]
    await viewModel.deleteMemory(server)
    await viewModel.confirmDelete().value
    let backendRequestIDs = await requests.ids
    XCTAssertEqual(backendRequestIDs, [server.id])
  }

  private func insertLocalMemory(content: String) async throws -> MemoryRecord {
    try await MemoryStorage.shared.insertLocalMemory(MemoryRecord(content: content))
  }

  private func makeMemory(id: String) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "Memory \(id)",
      category: .system,
      tier: .longTerm,
      tierIsExplicit: true,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: 2),
      conversationId: nil,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: false,
      scoring: nil,
      source: "desktop",
      confidence: nil,
      sourceApp: nil,
      contextSummary: nil,
      isRead: false,
      isDismissed: false,
      tags: [],
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: nil,
      windowTitle: nil,
      headline: nil
    )
  }
}

private actor DeleteRequestRecorder {
  private var recordedIDs: [String] = []

  func record(_ id: String) {
    recordedIDs.append(id)
  }

  var ids: [String] { recordedIDs }
}
