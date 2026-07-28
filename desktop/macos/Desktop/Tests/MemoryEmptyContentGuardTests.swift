import GRDB
import XCTest

@testable import Omi_Computer

/// Regression coverage for a QA-observed local cache row: a synced memory
/// with `content == ""` (backendId 068275f2-fffe-42ac-bdec-783cd008f3e9,
/// manuallyAdded=1) rendered as a blank card in Memories/Atlas UI.
///
/// Every UI-facing read (`getLocalMemories`, `getFilteredMemories`,
/// `searchLocalMemories`, `getMemories(backendIds:)`) funnels through
/// `MemoryRecord.toServerMemory()`, so that is the single choke point that
/// must reject blank content — mirroring the existing malformed-tier guard
/// in the same function.
final class MemoryEmptyContentGuardTests: XCTestCase {
  private var testUserId: String?
  private var userDir: URL?

  override func setUp() async throws {
    try await super.setUp()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memory-empty-content")
    testUserId = fixture.testUserId
    userDir = fixture.userDir
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
    try await super.tearDown()
  }

  /// Reproduces the sync path: the backend returns a memory whose content is
  /// empty. Before the fix, `toServerMemory()` had no content check, so this
  /// row surfaced to the UI as a blank card.
  func testSyncedEmptyContentMemoryIsExcludedFromLocalReads() async throws {
    let backendId = "empty-content-\(UUID().uuidString)"
    let serverMemory = makeMemory(id: backendId, content: "", manuallyAdded: true)

    try await MemoryStorage.shared.syncServerMemories([serverMemory])

    // The raw row is still cached (no write path is touched by the fix)...
    let rawRecord = try await MemoryStorage.shared.getMemoryByBackendId(backendId)
    XCTAssertNotNil(rawRecord, "Sync should still cache the raw row locally")
    XCTAssertEqual(rawRecord?.content, "")

    // ...but it must never surface through any UI-facing read.
    let local = try await MemoryStorage.shared.getLocalMemories(limit: 50, tiers: nil, includeDismissed: true)
    XCTAssertFalse(local.map(\.id).contains(backendId), "Empty-content memory must not appear in getLocalMemories")

    let filtered = try await MemoryStorage.shared.getFilteredMemories(limit: 50, tiers: nil, includeDismissed: true)
    XCTAssertFalse(
      filtered.map(\.id).contains(backendId), "Empty-content memory must not appear in getFilteredMemories")

    let byId = try await MemoryStorage.shared.getMemories(backendIds: [backendId])
    XCTAssertTrue(byId.isEmpty, "Empty-content memory must not appear even in direct backendId lookups")
  }

  /// Whitespace-only content is functionally empty (nothing renders); the
  /// guard trims before checking so a lone space/newline does not slip past.
  func testWhitespaceOnlyContentIsExcludedFromLocalReads() async throws {
    let backendId = "whitespace-content-\(UUID().uuidString)"
    let serverMemory = makeMemory(id: backendId, content: "   \n", manuallyAdded: false)

    try await MemoryStorage.shared.syncServerMemories([serverMemory])

    let local = try await MemoryStorage.shared.getLocalMemories(limit: 50, tiers: nil, includeDismissed: true)
    XCTAssertFalse(local.map(\.id).contains(backendId))
  }

  /// Sanity check: a normal non-empty memory is unaffected by the guard.
  func testNonEmptyContentMemoryStillSurfaces() async throws {
    let backendId = "non-empty-content-\(UUID().uuidString)"
    let serverMemory = makeMemory(id: backendId, content: "Remember to buy milk", manuallyAdded: false)

    try await MemoryStorage.shared.syncServerMemories([serverMemory])

    let local = try await MemoryStorage.shared.getLocalMemories(limit: 50, tiers: nil, includeDismissed: true)
    XCTAssertTrue(local.map(\.id).contains(backendId))
  }

  private func makeMemory(
    id: String,
    content: String,
    manuallyAdded: Bool
  ) -> ServerMemory {
    ServerMemory(
      id: id,
      content: content,
      category: .system,
      tier: .shortTerm,
      tierIsExplicit: true,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: 1),
      conversationId: nil,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: manuallyAdded,
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
