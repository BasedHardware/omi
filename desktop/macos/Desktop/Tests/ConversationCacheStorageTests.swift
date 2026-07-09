import XCTest
import OmiSupport
@testable import Omi_Computer

private actor ConversationCacheAccountScope {
  private var accountId: String

  init(_ accountId: String) {
    self.accountId = accountId
  }

  func current() -> String { accountId }
  func switchTo(_ accountId: String) { self.accountId = accountId }
}

private final class ConversationCacheMergeRaceGate: @unchecked Sendable {
  private let lock = NSLock()
  private let releaseFirstRead = DispatchSemaphore(value: 0)
  private var reads = 0
  private var firstReadObserved = false
  private var secondAttemptObserved = false
  private var firstReadWaiters: [CheckedContinuation<Void, Never>] = []
  private var secondAttemptWaiters: [CheckedContinuation<Void, Never>] = []

  func afterRead() {
    lock.lock()
    reads += 1
    let isFirst = reads == 1
    if isFirst {
      firstReadObserved = true
      firstReadWaiters.forEach { $0.resume() }
      firstReadWaiters.removeAll()
    }
    lock.unlock()
    guard isFirst else { return }
    releaseFirstRead.wait()
  }

  func waitUntilFirstRead() async {
    await withCheckedContinuation { continuation in
      lock.lock()
      if firstReadObserved {
        lock.unlock()
        continuation.resume()
      } else {
        firstReadWaiters.append(continuation)
        lock.unlock()
      }
    }
  }

  func signalSecondAttempt() {
    lock.lock()
    secondAttemptObserved = true
    secondAttemptWaiters.forEach { $0.resume() }
    secondAttemptWaiters.removeAll()
    lock.unlock()
  }

  func waitUntilSecondAttempted() async {
    await withCheckedContinuation { continuation in
      lock.lock()
      if secondAttemptObserved {
        lock.unlock()
        continuation.resume()
      } else {
        secondAttemptWaiters.append(continuation)
        lock.unlock()
      }
    }
  }

  func release() {
    releaseFirstRead.signal()
  }
}

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

    do {
      _ = try await ConversationCacheStorage.shared.load(id: "c1", accountId: testUserId)
      XCTFail("an operation carrying the previous account scope must be rejected")
    } catch {
      // Expected: the cache refuses to pair an old account token with the new pool.
    }
  }

  func testAccountSwitchDuringPoolLookupRejectsOldScopeBeforeRead() async throws {
    let queueValue = await RewindDatabase.shared.getDatabaseQueue()
    let firstAccountQueue = try XCTUnwrap(queueValue)
    let secondUserId = "conversation-cache-test-\(UUID().uuidString)"
    let accountScope = ConversationCacheAccountScope(testUserId)
    let storage = ConversationCacheStorage(
      currentAccountIdProvider: { await accountScope.current() },
      initializeDatabase: {},
      databaseQueueProvider: {
        await accountScope.switchTo(secondUserId)
        return firstAccountQueue
      }
    )

    do {
      _ = try await storage.load(id: "c1", accountId: testUserId)
      XCTFail("the old account scope must be rechecked after pool lookup")
    } catch {
      // Expected: the pool was resolved while the account scope changed.
    }
  }

  func testConcurrentMergeTransactionCannotLetDelayedOlderResponseWin() async throws {
    let baseline = conversation(
      title: "Baseline",
      overview: "Initial",
      revision: "1",
      updatedAt: Date(timeIntervalSince1970: 1)
    )
    try await ConversationCacheStorage.shared.upsertServerConversation(
      baseline,
      completeness: [.list],
      fetchedAt: Date(timeIntervalSince1970: 1),
      accountId: testUserId
    )

    let gate = ConversationCacheMergeRaceGate()
    let delayedStorage = ConversationCacheStorage(
      afterCachedRecordRead: { _ in gate.afterRead() }
    )
    let newerStorage = ConversationCacheStorage(
      beforeMergeTransaction: { _ in gate.signalSecondAttempt() }
    )
    let delayedOlder = conversation(
      title: "Delayed older",
      overview: "Must not win",
      revision: "2",
      updatedAt: Date(timeIntervalSince1970: 2)
    )
    let newer = conversation(
      title: "Newer",
      overview: "Canonical",
      revision: "3",
      updatedAt: Date(timeIntervalSince1970: 3)
    )

    let olderTask = Task {
      try await delayedStorage.upsertServerConversation(
        delayedOlder,
        completeness: [.list],
        fetchedAt: Date(timeIntervalSince1970: 2),
        accountId: testUserId
      )
    }
    await gate.waitUntilFirstRead()
    let newerTask = Task {
      try await newerStorage.upsertServerConversation(
        newer,
        completeness: [.list],
        fetchedAt: Date(timeIntervalSince1970: 3),
        accountId: testUserId
      )
    }
    await gate.waitUntilSecondAttempted()
    gate.release()
    try await olderTask.value
    try await newerTask.value

    let loadedValue = try await newerStorage.load(id: "c1", accountId: testUserId)
    let loaded = try XCTUnwrap(loadedValue)
    XCTAssertEqual(loaded.conversation.structured.title, "Newer")
    XCTAssertEqual(loaded.conversation.revision, "3")
  }

  func testSelectedDateQueryStillMatchesDateEncodedCacheRows() async throws {
    let cached = conversation(
      title: "Selected day",
      overview: "Date-filtered",
      revision: "1",
      updatedAt: Date(timeIntervalSince1970: 1)
    )
    try await ConversationCacheStorage.shared.upsertServerConversation(
      cached,
      completeness: [.list],
      fetchedAt: Date(timeIntervalSince1970: 1),
      accountId: testUserId
    )

    let selectedDate = Date(timeIntervalSince1970: 1_000)
    let loaded = try await ConversationCacheStorage.shared.load(
      query: ConversationQuery(selectedDate: selectedDate),
      accountId: testUserId
    )

    XCTAssertEqual(loaded.map { $0.conversation.id }, ["c1"])
  }

  func testSameSecondOlderSnapshotCannotOverwriteNewerCachedVersion() async throws {
    let newerTime = Date(timeIntervalSince1970: 1_000.9009)
    let olderTime = Date(timeIntervalSince1970: 1_000.9005)
    let newer = conversation(
      title: "Newer",
      overview: "Canonical",
      revision: "newer",
      updatedAt: newerTime
    )
    try await ConversationCacheStorage.shared.upsertServerConversation(
      newer,
      completeness: [.list],
      fetchedAt: newerTime,
      accountId: testUserId
    )

    let roundTrippedValue = try await ConversationCacheStorage.shared.load(id: "c1", accountId: testUserId)
    let roundTripped = try XCTUnwrap(roundTrippedValue)
    XCTAssertEqual(
      try XCTUnwrap(roundTripped.conversation.updatedAt).timeIntervalSince1970,
      newerTime.timeIntervalSince1970,
      accuracy: 0.000_001
    )

    let delayedOlder = conversation(
      title: "Older",
      overview: "Must not win",
      revision: "older",
      updatedAt: olderTime
    )
    try await ConversationCacheStorage.shared.applyServerSnapshot(
      [delayedOlder],
      query: ConversationQuery(),
      fetchedAt: Date(timeIntervalSince1970: 2_000),
      accountId: testUserId
    )

    let loadedValue = try await ConversationCacheStorage.shared.load(id: "c1", accountId: testUserId)
    let loaded = try XCTUnwrap(loadedValue)
    XCTAssertEqual(loaded.conversation.structured.title, "Newer")
    XCTAssertEqual(loaded.conversation.revision, "newer")
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
