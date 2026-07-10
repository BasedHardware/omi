import XCTest
@testable import Omi_Computer

@MainActor
final class ConversationRepositoryTests: XCTestCase {
  func testLoadEmitsCacheImmediatelyThenCanonicalServerState() async {
    let cached = makeConversation(
      title: "Cached title",
      overview: "Old summary",
      status: .processing,
      revision: 1
    )
    let server = makeConversation(
      title: "Server title",
      overview: "Fresh summary",
      status: .completed,
      revision: 2
    )
    let remote = FakeConversationRemote(listResult: .success([server]), countResult: .success(1))
    let local = FakeConversationLocal(listResult: [cached], count: 1)
    let repository = ConversationRepository(remote: remote, local: local)
    var snapshots: [ConversationRepositorySnapshot] = []
    repository.onSnapshot = { snapshots.append($0) }

    await repository.load(query: .all)

    XCTAssertEqual(snapshots.map(\.source), [.cache, .cache, .server])
    XCTAssertTrue(snapshots[0].conversations.isEmpty, "A new query must not show rows from an obsolete filter")
    XCTAssertEqual(snapshots[1].conversations[0].structured.title, "Cached title")
    XCTAssertTrue(snapshots[1].isLoading, "Cache first paint must not pretend revalidation is finished")
    XCTAssertEqual(snapshots[2].conversations[0].structured.overview, "Fresh summary")
    XCTAssertEqual(snapshots[2].conversations[0].status, .completed)
    XCTAssertFalse(snapshots[2].isLoading)
    XCTAssertEqual(local.stored.map(\.updatedAt), [server.updatedAt])
  }

  func testServerFailureKeepsUsefulCacheVisibleWithoutBlankingTheList() async {
    let cached = makeConversation(title: "Available offline", revision: 1)
    let remote = FakeConversationRemote(listResult: .failure(TestFailure.offline))
    let repository = ConversationRepository(
      remote: remote,
      local: FakeConversationLocal(listResult: [cached], count: 1)
    )
    var snapshots: [ConversationRepositorySnapshot] = []
    repository.onSnapshot = { snapshots.append($0) }

    await repository.load(query: .all)

    XCTAssertEqual(snapshots.last?.conversations.map(\.structured.title), ["Available offline"])
    XCTAssertNil(snapshots.last?.error)
    XCTAssertFalse(snapshots.last?.isLoading ?? true)
  }

  func testDetailPaintsCachedTranscriptThenRevalidatesServerOwnedFields() async throws {
    let seed = makeConversation(title: "List title", overview: "List summary", revision: 1)
    let cachedDetail = makeConversation(
      title: "Cached detail",
      overview: "Cached summary",
      revision: 1,
      transcript: "cached transcript"
    )
    let serverDetail = makeConversation(
      title: "Canonical title",
      overview: "Fresh server summary",
      status: .completed,
      revision: 3,
      transcript: "server transcript"
    )
    let remote = FakeConversationRemote(
      listResult: .success([seed]),
      countResult: .success(1),
      detailResult: .success(serverDetail)
    )
    let local = FakeConversationLocal(detailResult: cachedDetail)
    let repository = ConversationRepository(remote: remote, local: local)
    var cachedPaints: [ServerConversation] = []
    await repository.load(query: .all)

    let result = try await repository.detail(id: seed.id, seed: seed) { cachedPaints.append($0) }

    XCTAssertEqual(cachedPaints.map(\.transcript), ["You: cached transcript"])
    XCTAssertEqual(result.structured.overview, "Fresh server summary")
    XCTAssertEqual(result.transcript, "You: server transcript")
    XCTAssertEqual(local.stored.last?.updatedAt, serverDetail.updatedAt)
    XCTAssertEqual(repository.conversations[0].structured.overview, "Fresh server summary")
  }

  func testSuccessfulMutationHasOptimisticUXThenSettlesFromCanonicalSnapshot() async throws {
    let initial = makeConversation(overview: "Before processing", starred: false, revision: 1)
    let canonical = makeConversation(overview: "Processing finished", starred: true, revision: 2)
    let remote = FakeConversationRemote(
      listResult: .success([initial]),
      countResult: .success(1),
      starResult: .success(canonical)
    )
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    var snapshots: [ConversationRepositorySnapshot] = []
    repository.onSnapshot = { snapshots.append($0) }
    await repository.load(query: .all)
    snapshots.removeAll()

    try await repository.setStarred(id: initial.id, starred: true)

    XCTAssertEqual(snapshots.map(\.source), [.optimistic, .server])
    XCTAssertTrue(snapshots[0].conversations[0].starred)
    XCTAssertEqual(snapshots[0].conversations[0].structured.overview, "Before processing")
    XCTAssertTrue(snapshots[1].conversations[0].starred)
    XCTAssertEqual(snapshots[1].conversations[0].structured.overview, "Processing finished")
    XCTAssertEqual(snapshots[1].conversations[0].updatedAt, canonical.updatedAt)
  }

  func testFailedMutationRollsBackTheExactVisibleState() async {
    let initial = makeConversation(title: "Original", starred: false, revision: 1)
    let remote = FakeConversationRemote(
      listResult: .success([initial]),
      countResult: .success(1),
      titleResult: .failure(TestFailure.offline)
    )
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    var snapshots: [ConversationRepositorySnapshot] = []
    repository.onSnapshot = { snapshots.append($0) }
    await repository.load(query: .all)
    snapshots.removeAll()

    do {
      try await repository.updateTitle(id: initial.id, title: "Optimistic")
      XCTFail("Expected mutation failure")
    } catch {
      XCTAssertEqual(snapshots.map(\.source), [.optimistic, .rollback])
      XCTAssertEqual(snapshots[0].conversations[0].structured.title, "Optimistic")
      XCTAssertEqual(snapshots[1].conversations, [initial])
    }
  }

  func testOlderCanonicalResponseCannotRegressNewerVisibleRevision() async throws {
    let current = makeConversation(title: "Current", revision: 5)
    let staleMutationResponse = makeConversation(title: "Stale", revision: 4)
    let remote = FakeConversationRemote(
      listResult: .success([current]),
      countResult: .success(1),
      titleResult: .success(staleMutationResponse)
    )
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    await repository.load(query: .all)

    try await repository.updateTitle(id: current.id, title: "Optimistic")

    XCTAssertEqual(repository.conversations[0].structured.title, "Optimistic")
    XCTAssertEqual(repository.conversations[0].updatedAt, current.updatedAt)
  }

  func testCanonicalMutationRemovesRowThatNoLongerMatchesActiveFilter() async throws {
    let starred = makeConversation(starred: true, revision: 1)
    let canonical = makeConversation(starred: false, revision: 2)
    let remote = FakeConversationRemote(
      listResult: .success([starred]),
      countResult: .success(1),
      starResult: .success(canonical)
    )
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    await repository.load(
      query: ConversationListQuery(starredOnly: true, date: nil, folderId: nil)
    )

    try await repository.setStarred(id: starred.id, starred: false)

    XCTAssertTrue(repository.conversations.isEmpty)
    XCTAssertEqual(repository.count, 0)
  }

  func testDeleteWaitsForServerSuccessBeforeRemovingVisibleAndCachedState() async throws {
    let conversation = makeConversation(revision: 1)
    let remote = FakeConversationRemote(
      listResult: .success([conversation]),
      countResult: .success(1),
      deleteResult: .success(())
    )
    let local = FakeConversationLocal()
    let repository = ConversationRepository(remote: remote, local: local)
    await repository.load(query: .all)

    try await repository.delete(id: conversation.id)

    XCTAssertEqual(remote.deletedIds, [conversation.id])
    XCTAssertEqual(local.deletedIds, [conversation.id])
    XCTAssertTrue(repository.conversations.isEmpty)
    XCTAssertEqual(repository.count, 0)
  }

  func testDeleteFailureKeepsVisibleAndCachedStateIntact() async {
    let conversation = makeConversation(revision: 1)
    let remote = FakeConversationRemote(
      listResult: .success([conversation]),
      countResult: .success(1),
      deleteResult: .failure(TestFailure.offline)
    )
    let local = FakeConversationLocal()
    let repository = ConversationRepository(remote: remote, local: local)
    await repository.load(query: .all)

    do {
      try await repository.delete(id: conversation.id)
      XCTFail("Expected delete failure")
    } catch {
      XCTAssertEqual(repository.conversations, [conversation])
      XCTAssertTrue(local.deletedIds.isEmpty)
      XCTAssertEqual(repository.count, 1)
    }
  }

  func testSupersededRequestCannotReplaceRowsFromTheNewerFilter() async {
    let first = makeConversation(id: "first", title: "First folder", revision: 1)
    let second = makeConversation(id: "second", title: "Second folder", revision: 2)
    let suspendedLists = SuspendedConversationLists()
    let remote = FakeConversationRemote(countResult: .success(1))
    remote.listHandler = { query in
      await suspendedLists.result(for: query.folderId ?? "all")
    }
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    let firstQuery = ConversationListQuery(starredOnly: false, date: nil, folderId: "first")
    let secondQuery = ConversationListQuery(starredOnly: false, date: nil, folderId: "second")

    let firstLoad = Task { await repository.load(query: firstQuery, includeCache: false) }
    await suspendedLists.waitUntilRequested("first")
    let secondLoad = Task { await repository.load(query: secondQuery, includeCache: false) }
    await suspendedLists.waitUntilRequested("second")
    await suspendedLists.resume("second", with: [second])
    await secondLoad.value
    await suspendedLists.resume("first", with: [first])
    await firstLoad.value

    XCTAssertEqual(repository.conversations.map(\.id), ["second"])
    XCTAssertEqual(repository.conversations.map(\.structured.title), ["Second folder"])
  }

  func testSupersededSearchIsCancelledInsteadOfReturningStaleResults() async throws {
    let first = makeConversation(id: "first", title: "Old query", revision: 1)
    let second = makeConversation(id: "second", title: "New query", revision: 2)
    let suspendedSearches = SuspendedConversationLists()
    let remote = FakeConversationRemote()
    remote.searchHandler = { text in
      await suspendedSearches.result(for: text)
    }
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())

    let firstSearch = Task { try await repository.search(text: "old") }
    await suspendedSearches.waitUntilRequested("old")
    let secondSearch = Task { try await repository.search(text: "new") }
    await suspendedSearches.waitUntilRequested("new")
    await suspendedSearches.resume("new", with: [second])
    let currentResults = try await secondSearch.value
    await suspendedSearches.resume("old", with: [first])

    XCTAssertEqual(currentResults.map(\.id), ["second"])
    do {
      _ = try await firstSearch.value
      XCTFail("Expected the superseded search to be cancelled")
    } catch is CancellationError {
      // Expected: an old query can never overwrite the current results.
    }
  }

  private func makeConversation(
    id: String = "conversation-1",
    title: String = "Title",
    overview: String = "Overview",
    status: ConversationStatus = .completed,
    starred: Bool = false,
    revision: TimeInterval,
    transcript: String? = nil
  ) -> ServerConversation {
    let created = Date(timeIntervalSince1970: 100)
    let segments = transcript.map {
      [
        TranscriptSegment(
          id: "segment-1",
          backendId: "segment-1",
          text: $0,
          speaker: "SPEAKER_00",
          isUser: true,
          personId: nil,
          start: 0,
          end: 1
        )
      ]
    } ?? []
    return ServerConversation(
      id: id,
      createdAt: created,
      updatedAt: Date(timeIntervalSince1970: revision),
      startedAt: created,
      finishedAt: created.addingTimeInterval(60),
      structured: Structured(
        title: title,
        overview: overview,
        emoji: "💬",
        category: "other",
        actionItems: [],
        events: []
      ),
      transcriptSegments: segments,
      transcriptSegmentsIncluded: transcript != nil,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: "en",
      status: status,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: starred,
      folderId: nil,
      inputDeviceName: nil
    )
  }
}

private extension ConversationListQuery {
  static let all = ConversationListQuery(starredOnly: false, date: nil, folderId: nil)
}

private enum TestFailure: Error {
  case offline
}

private final class FakeConversationRemote: ConversationRemoteDataSource {
  var listResult: Result<[ServerConversation], Error>
  var countResult: Result<Int, Error>
  var detailResult: Result<ServerConversation, Error>
  var starResult: Result<ServerConversation, Error>
  var titleResult: Result<ServerConversation, Error>
  var folderResult: Result<ServerConversation, Error>
  var searchResult: Result<[ServerConversation], Error>
  var deleteResult: Result<Void, Error>
  var listHandler: ((ConversationListQuery) async throws -> [ServerConversation])?
  var searchHandler: ((String) async throws -> [ServerConversation])?
  var deletedIds: [String] = []

  init(
    listResult: Result<[ServerConversation], Error> = .success([]),
    countResult: Result<Int, Error> = .success(0),
    detailResult: Result<ServerConversation, Error> = .failure(TestFailure.offline),
    starResult: Result<ServerConversation, Error> = .failure(TestFailure.offline),
    titleResult: Result<ServerConversation, Error> = .failure(TestFailure.offline),
    folderResult: Result<ServerConversation, Error> = .failure(TestFailure.offline),
    searchResult: Result<[ServerConversation], Error> = .success([]),
    deleteResult: Result<Void, Error> = .failure(TestFailure.offline)
  ) {
    self.listResult = listResult
    self.countResult = countResult
    self.detailResult = detailResult
    self.starResult = starResult
    self.titleResult = titleResult
    self.folderResult = folderResult
    self.searchResult = searchResult
    self.deleteResult = deleteResult
  }

  func list(query: ConversationListQuery) async throws -> [ServerConversation] {
    if let listHandler { return try await listHandler(query) }
    return try listResult.get()
  }
  func count(query: ConversationListQuery) async throws -> Int { try countResult.get() }
  func detail(id: String) async throws -> ServerConversation { try detailResult.get() }
  func search(text: String) async throws -> [ServerConversation] {
    if let searchHandler { return try await searchHandler(text) }
    return try searchResult.get()
  }
  func setStarred(id: String, starred: Bool) async throws -> ServerConversation { try starResult.get() }
  func updateTitle(id: String, title: String) async throws -> ServerConversation { try titleResult.get() }
  func moveToFolder(id: String, folderId: String?) async throws -> ServerConversation { try folderResult.get() }
  func delete(id: String) async throws {
    try deleteResult.get()
    deletedIds.append(id)
  }
}

private final class FakeConversationLocal: ConversationLocalDataSource {
  var listResult: [ServerConversation]
  var countValue: Int
  var detailResult: ServerConversation?
  var stored: [ServerConversation] = []
  var deletedIds: [String] = []

  init(
    listResult: [ServerConversation] = [],
    count: Int = 0,
    detailResult: ServerConversation? = nil
  ) {
    self.listResult = listResult
    self.countValue = count
    self.detailResult = detailResult
  }

  func list(query: ConversationListQuery) async throws -> [ServerConversation] { listResult }
  func count(query: ConversationListQuery) async throws -> Int { countValue }
  func detail(id: String) async throws -> ServerConversation? { detailResult }
  func store(_ conversation: ServerConversation) async throws { stored.append(conversation) }
  func delete(id: String) async throws { deletedIds.append(id) }
}

private actor SuspendedConversationLists {
  private var requested: Set<String> = []
  private var requestWaiters: [String: CheckedContinuation<Void, Never>] = [:]
  private var resultContinuations: [String: CheckedContinuation<[ServerConversation], Never>] = [:]

  func result(for key: String) async -> [ServerConversation] {
    requested.insert(key)
    requestWaiters.removeValue(forKey: key)?.resume()
    return await withCheckedContinuation { continuation in
      resultContinuations[key] = continuation
    }
  }

  func waitUntilRequested(_ key: String) async {
    if requested.contains(key) { return }
    await withCheckedContinuation { continuation in
      requestWaiters[key] = continuation
    }
  }

  func resume(_ key: String, with conversations: [ServerConversation]) {
    resultContinuations.removeValue(forKey: key)?.resume(returning: conversations)
  }
}
