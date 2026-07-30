import XCTest

@testable import Omi_Computer

/// The Brain Map inspector cites memories by id. Resolving those citations is
/// a cache lookup, not a scan of whatever the Memories list happens to be
/// showing: the visible array is one page of a tier-filtered, device-scoped
/// browse, so citations routinely fall outside it and the inspector reported
/// them as "not loaded yet" while they sat on disk.
final class MemoryCitationResolutionTests: XCTestCase {
  private var userDir: URL?

  override func setUp() async throws {
    try await super.setUp()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memory-citation")
    userDir = fixture.userDir
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
    try await super.tearDown()
  }

  func testCitedMemoriesResolveFromTheCacheEvenWhenOutsideTheVisiblePage() async throws {
    let cited = makeMemory(id: "cited-1", content: "the cited one", tier: .longTerm)
    let unrelated = makeMemory(id: "unrelated-1", content: "not cited", tier: .longTerm)
    try await MemoryStorage.shared.syncServerMemories([cited, unrelated])

    let resolved = try await MemoryStorage.shared.getMemories(backendIds: ["cited-1"])

    XCTAssertEqual(resolved.map(\.id), ["cited-1"])
    XCTAssertEqual(resolved.first?.content, "the cited one")
  }

  /// A citation set spans tiers and dismissal states because the graph was
  /// built from every memory, not from one browsing view. Applying the list's
  /// filters here would drop evidence the user can plainly see cited.
  func testCitationLookupIgnoresTierAndDismissalFilters() async throws {
    let shortTerm = makeMemory(id: "short-1", content: "short term", tier: .shortTerm)
    let dismissed = makeMemory(
      id: "dismissed-1", content: "dismissed", tier: .longTerm, isDismissed: true)
    try await MemoryStorage.shared.syncServerMemories([shortTerm, dismissed])

    let resolved = try await MemoryStorage.shared.getMemories(
      backendIds: ["short-1", "dismissed-1"])

    XCTAssertEqual(Set(resolved.map(\.id)), ["short-1", "dismissed-1"])
  }

  func testUnknownCitationsAreAbsentRatherThanFabricated() async throws {
    try await MemoryStorage.shared.syncServerMemories([
      makeMemory(id: "known-1", content: "known", tier: .longTerm)
    ])

    let resolved = try await MemoryStorage.shared.getMemories(
      backendIds: ["known-1", "never-existed"])

    XCTAssertEqual(resolved.map(\.id), ["known-1"])
    let empty = try await MemoryStorage.shared.getMemories(backendIds: [])
    XCTAssertTrue(empty.isEmpty)
  }

  /// Duplicate ids across an entity's connections must not duplicate evidence
  /// rows, and the inspector reads newest-first like the list it came from.
  func testResolutionDeduplicatesIdsAndReturnsNewestFirst() async throws {
    let older = makeMemory(
      id: "older", content: "older", tier: .longTerm,
      createdAt: Date(timeIntervalSince1970: 1_000))
    let newer = makeMemory(
      id: "newer", content: "newer", tier: .longTerm,
      createdAt: Date(timeIntervalSince1970: 9_000))
    try await MemoryStorage.shared.syncServerMemories([older, newer])

    let resolved = try await MemoryStorage.shared.getMemories(
      backendIds: ["older", "newer", "older"])

    XCTAssertEqual(resolved.map(\.id), ["newer", "older"])
  }

  private func makeMemory(
    id: String,
    content: String,
    tier: MemoryLayer,
    isDismissed: Bool = false,
    createdAt: Date = Date(timeIntervalSince1970: 1)
  ) -> ServerMemory {
    ServerMemory(
      id: id,
      content: content,
      category: .system,
      tier: tier,
      tierIsExplicit: true,
      createdAt: createdAt,
      updatedAt: createdAt,
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
      isDismissed: isDismissed,
      tags: [],
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: nil,
      windowTitle: nil,
      headline: nil
    )
  }
}
