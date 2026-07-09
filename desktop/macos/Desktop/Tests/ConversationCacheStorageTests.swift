import XCTest
import OmiSupport
@testable import Omi_Computer

final class ConversationCacheStorageTests: XCTestCase {
  private var testUserId = ""
  private var userDirectories: [URL] = []

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "conversation-cache-test-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await ConversationCacheStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()
    userDirectories = [directory(for: testUserId)]
  }

  override func tearDown() async throws {
    await ConversationCacheStorage.shared.invalidateCache()
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
    for userDirectory in userDirectories { try? FileManager.default.removeItem(at: userDirectory) }
    try await super.tearDown()
  }

  func testRealDatabaseMigrationPreservesDetailAcrossPartialListRefresh() async throws {
    let detail = conversation(
      title: "Cached detail",
      overview: "Cached overview",
      revision: "2",
      updatedAt: Date(timeIntervalSince1970: 2),
      transcript: [segment("complete transcript")],
      transcriptIncluded: true
    )
    try await ConversationCacheStorage.shared.upsertServerConversation(
      detail,
      completeness: [.list, .detail, .transcript],
      fetchedAt: Date(timeIntervalSince1970: 2),
      accountId: testUserId
    )

    let list = conversation(
      title: "Fresh list title",
      overview: "Fresh overview",
      revision: "3",
      updatedAt: Date(timeIntervalSince1970: 3)
    )
    try await ConversationCacheStorage.shared.applyServerSnapshot(
      [list],
      query: ConversationQuery(),
      fetchedAt: Date(timeIntervalSince1970: 3),
      accountId: testUserId
    )

    let loaded = try await ConversationCacheStorage.shared.load(id: "c1", accountId: testUserId)
    let cached = try XCTUnwrap(loaded)
    XCTAssertEqual(cached.conversation.structured.title, "Fresh list title")
    XCTAssertEqual(cached.conversation.structured.overview, "Fresh overview")
    XCTAssertEqual(cached.conversation.transcriptSegments.map(\.text), ["complete transcript"])
    XCTAssertTrue(cached.completeness.contains(.detail))
    XCTAssertTrue(cached.completeness.contains(.transcript))
    XCTAssertEqual(cached.listFetchedAt, Date(timeIntervalSince1970: 3))
    XCTAssertEqual(cached.detailFetchedAt, Date(timeIntervalSince1970: 2))
    XCTAssertEqual(cached.transcriptFetchedAt, Date(timeIntervalSince1970: 2))
  }

  func testPendingMutationAndFilteredQuerySurviveStorageRoundTrip() async throws {
    let starred = conversation(
      title: "Starred",
      overview: "Overview",
      revision: "1",
      updatedAt: Date(timeIntervalSince1970: 1),
      starred: true
    )
    let query = ConversationQuery(showStarredOnly: true)
    try await ConversationCacheStorage.shared.applyServerSnapshot(
      [starred],
      query: query,
      fetchedAt: Date(timeIntervalSince1970: 1),
      accountId: testUserId
    )
    var mutation = ConversationPendingMutation()
    mutation.setStarred(false)
    try await ConversationCacheStorage.shared.savePendingMutation(
      mutation,
      conversationId: "c1",
      accountId: testUserId
    )
    let visible = try await ConversationCacheStorage.shared.load(query: query, accountId: testUserId)
    let pending = try await ConversationCacheStorage.shared.loadPendingMutations(accountId: testUserId)

    XCTAssertEqual(visible.map { $0.conversation.id }, ["c1"])
    XCTAssertEqual(pending["c1"]?.starred, false)
  }

  func testAccountSwitchCannotReadPreviousAccountsConversationCache() async throws {
    let firstAccountConversation = conversation(
      title: "First account only",
      overview: "Private",
      revision: "1",
      updatedAt: Date(timeIntervalSince1970: 1)
    )
    try await ConversationCacheStorage.shared.upsertServerConversation(
      firstAccountConversation,
      completeness: [.list],
      fetchedAt: Date(timeIntervalSince1970: 1),
      accountId: testUserId
    )

    let secondUserId = "conversation-cache-test-\(UUID().uuidString)"
    userDirectories.append(directory(for: secondUserId))
    try await RewindDatabase.shared.switchUser(to: secondUserId)

    let leaked = try await ConversationCacheStorage.shared.load(id: "c1", accountId: secondUserId)

    XCTAssertNil(leaked)
  }

  private func conversation(
    title: String,
    overview: String,
    revision: String,
    updatedAt: Date,
    transcript: [TranscriptSegment] = [],
    transcriptIncluded: Bool = false,
    starred: Bool = false
  ) -> ServerConversation {
    let createdAt = Date(timeIntervalSince1970: 1_000)
    return ServerConversation(
      id: "c1",
      createdAt: createdAt,
      startedAt: createdAt,
      finishedAt: createdAt.addingTimeInterval(60),
      structured: Structured(
        title: title,
        overview: overview,
        emoji: "💬",
        category: "other",
        actionItems: [],
        events: []
      ),
      transcriptSegments: transcript,
      transcriptSegmentsIncluded: transcriptIncluded,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: "en",
      status: .completed,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: starred,
      folderId: nil,
      inputDeviceName: nil,
      updatedAt: updatedAt,
      revision: revision
    )
  }

  private func segment(_ text: String) -> TranscriptSegment {
    TranscriptSegment(
      id: "segment-1",
      text: text,
      speaker: "SPEAKER_00",
      isUser: true,
      personId: nil,
      start: 0,
      end: 1
    )
  }

  private func directory(for userId: String) -> URL {
    DesktopLocalProfile.applicationSupportURL()
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(userId, isDirectory: true)
  }
}
