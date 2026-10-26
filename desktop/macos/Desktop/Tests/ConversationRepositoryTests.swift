import XCTest

@testable import Omi_Computer

@MainActor
final class ConversationRepositoryTests: XCTestCase {
  func testDiscardedScopeReachesListCountAndSearch() async throws {
    let remote = FakeConversationRemote()
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    let query = ConversationListQuery(starredOnly: true, date: nil, folderId: "work", includeDiscarded: true)
    await repository.load(query: query)
    _ = try await repository.search(text: "synthetic", includeDiscarded: true)
    XCTAssertEqual(remote.listQueries, [query])
    XCTAssertEqual(remote.countQueries, [query])
    XCTAssertEqual(remote.searchDiscardedScopes, [true])
    XCTAssertTrue(query.hasFilters)
  }

  func testRestorePublishesAndCachesFullCanonicalResponse() async throws {
    let hidden = makeConversation(revision: 1, discarded: true)
    let restored = makeConversation(
      title: "Restored", overview: "New summary", revision: 2, transcript: "Retained audio transcript")
    let remote = FakeConversationRemote(listResult: .success([hidden]))
    remote.restoreResult = .success(restored)
    let local = FakeConversationLocal()
    let repository = ConversationRepository(remote: remote, local: local)
    await repository.load(
      query: ConversationListQuery(starredOnly: false, date: nil, folderId: nil, includeDiscarded: true))
    local.stored.removeAll()
    let result = try await repository.restore(id: hidden.id)
    XCTAssertEqual(result, restored)
    XCTAssertEqual(repository.conversations, [restored])
    XCTAssertEqual(local.stored, [restored])
  }

  func testFailedRestoreKeepsHiddenCardAndCacheIntact() async {
    let hidden = makeConversation(revision: 1, discarded: true)
    let remote = FakeConversationRemote(listResult: .success([hidden]))
    // A server returning 200 with the old discard must never read as success.
    remote.restoreResult = .success(hidden)
    let local = FakeConversationLocal()
    let repository = ConversationRepository(remote: remote, local: local)
    await repository.load(
      query: ConversationListQuery(starredOnly: false, date: nil, folderId: nil, includeDiscarded: true))
    local.stored.removeAll()
    do {
      _ = try await repository.restore(id: hidden.id)
      XCTFail("A still-discarded response cannot complete restore")
    } catch {
      XCTAssertTrue(error is ConversationRestoreError)
    }
    XCTAssertEqual(repository.conversations, [hidden])
    XCTAssertTrue(local.stored.isEmpty)
  }

  func testStaleSearchIndexCannotUndoRestoreButNewerDecisionCan() async throws {
    let hidden = makeConversation(revision: 1, discarded: true)
    let restored = makeConversation(revision: 2, transcript: "Retained transcript")
    let remote = FakeConversationRemote(searchResult: .success([hidden]))
    remote.restoreResult = .success(restored)
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    _ = try await repository.restore(id: hidden.id)
    let staleHits = try await repository.search(text: "synthetic", includeDiscarded: true)
    XCTAssertEqual(staleHits, [restored])
    XCTAssertEqual(staleHits.first?.transcriptSegments.first?.text, "Retained transcript")
    remote.searchResult = .success([makeConversation(title: "Old summary", revision: 1)])
    let staleVisibleHits = try await repository.search(text: "synthetic", includeDiscarded: true)
    XCTAssertEqual(staleVisibleHits, [restored])
    remote.searchResult = .success([restored])
    _ = try await repository.search(text: "synthetic", includeDiscarded: true)
    remote.searchResult = .success([hidden])
    let staleAfterFresh = try await repository.search(text: "synthetic", includeDiscarded: true)
    XCTAssertEqual(staleAfterFresh, [restored], "A fresh detail must not release the floor for a lagging search index")
    let newer = makeConversation(revision: 3, discarded: true)
    remote.searchResult = .success([newer])
    let freshHits = try await repository.search(text: "synthetic", includeDiscarded: true)
    XCTAssertEqual(freshHits, [newer])
  }

  func testRestoreDoesNotOverrideDeletedServerTruth() async throws {
    let restored = makeConversation(revision: 2)
    let deleted = makeConversation(revision: 3, discarded: true, deleted: true)
    let remote = FakeConversationRemote(searchResult: .success([deleted]))
    remote.restoreResult = .success(restored)
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    _ = try await repository.restore(id: restored.id)
    let results = try await repository.search(text: "synthetic", includeDiscarded: true)
    XCTAssertTrue(try XCTUnwrap(results.first).deleted)
    XCTAssertTrue(
      ConversationSearchResultFilter.apply(
        results, starredOnly: false, date: nil, folderId: nil, includeDiscarded: true
      ).isEmpty)
  }

  func testSparseListAfterRestoreRetainsTranscriptForOfflineDetail() async throws {
    let restored = makeConversation(revision: 2, transcript: "Retained transcript")
    let sparse = makeConversation(title: "Fresh list title", revision: 3)
    let remote = FakeConversationRemote(listResult: .success([sparse]))
    remote.restoreResult = .success(restored)
    let local = FakeConversationLocal(detailResult: restored)
    let repository = ConversationRepository(remote: remote, local: local)
    _ = try await repository.restore(id: restored.id)
    await repository.load(query: .all)
    var cachedPaint: ServerConversation?
    let offline = try await repository.detail(id: restored.id, seed: restored) { cachedPaint = $0 }
    XCTAssertEqual(cachedPaint?.transcriptSegments.first?.text, "Retained transcript")
    XCTAssertEqual(offline.transcriptSegments.first?.text, "Retained transcript")
    XCTAssertTrue(offline.transcriptSegmentsIncluded)
    XCTAssertEqual(offline.title, "Fresh list title")
    XCTAssertEqual(offline.updatedAt, sparse.updatedAt)
  }

  func testSparseSearchAfterRestoreRetainsTranscriptButExplicitEmptyDetailWins() async throws {
    let restored = makeConversation(revision: 2, transcript: "Retained transcript")
    let sparse = makeConversation(revision: 3)
    var empty = makeConversation(revision: 4)
    empty.transcriptSegmentsIncluded = true
    let remote = FakeConversationRemote(searchResult: .success([sparse]))
    remote.restoreResult = .success(restored)
    let local = FakeConversationLocal(detailResult: restored)
    let repository = ConversationRepository(remote: remote, local: local)
    _ = try await repository.restore(id: restored.id)
    let hits = try await repository.search(text: "synthetic", includeDiscarded: true)
    XCTAssertEqual(hits.first?.transcriptSegments.first?.text, "Retained transcript")
    let offline = try await repository.detail(id: restored.id)
    XCTAssertEqual(offline.transcriptSegments.first?.text, "Retained transcript")
    remote.detailResult = .success(empty)
    let canonical = try await repository.detail(id: restored.id)
    XCTAssertTrue(canonical.transcriptSegments.isEmpty)
    XCTAssertTrue(canonical.transcriptSegmentsIncluded)
    XCTAssertEqual(canonical.updatedAt, empty.updatedAt)
  }

  func testSparseRestoreResponseDoesNotMaskCachedTranscriptOffline() async throws {
    let cached = makeConversation(revision: 1, transcript: "Cached retained transcript", discarded: true)
    let restored = makeConversation(title: "Restored", revision: 2)
    let remote = FakeConversationRemote()
    remote.restoreResult = .success(restored)
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal(detailResult: cached))
    _ = try await repository.restore(id: restored.id)
    var cachedPaint: ServerConversation?
    let offline = try await repository.detail(id: restored.id, seed: restored) { cachedPaint = $0 }
    XCTAssertEqual(cachedPaint?.transcriptSegments.first?.text, "Cached retained transcript")
    XCTAssertEqual(offline.transcriptSegments.first?.text, "Cached retained transcript")
    XCTAssertFalse(offline.discarded)
    XCTAssertEqual(offline.title, "Restored")
  }

  func testRestoreWithoutResponseRevisionAdoptsFreshServerChanges() async throws {
    let restored = makeConversation(title: "Restored", revision: nil)
    let fresh = makeConversation(title: "Later title", revision: 3)
    let remote = FakeConversationRemote(searchResult: .success([fresh]))
    remote.restoreResult = .success(restored)
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    _ = try await repository.restore(id: restored.id)
    let freshHits = try await repository.search(text: "synthetic", includeDiscarded: true)
    XCTAssertEqual(freshHits, [fresh])
    remote.searchResult = .success([makeConversation(revision: 2, discarded: true)])
    let staleHits = try await repository.search(text: "synthetic", includeDiscarded: true)
    XCTAssertEqual(staleHits, [fresh])
  }

  func testRestorePrewriteRevisionCannotAuthorizeAnInflightHiddenResponse() async throws {
    let restored = makeConversation(revision: 1)
    let hidden = makeConversation(revision: 2, discarded: true)
    let remote = FakeConversationRemote(searchResult: .success([hidden]))
    remote.restoreResult = .success(restored)
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    _ = try await repository.restore(id: restored.id)
    let staleHits = try await repository.search(text: "synthetic", includeDiscarded: true)
    XCTAssertEqual(staleHits, [restored], "The POST can echo a revision older than an in-flight GET")
  }

  func testStaleCacheCannotRehideConfirmedRestoreWhenOffline() async throws {
    let hidden = makeConversation(revision: 1, discarded: true)
    let restored = makeConversation(revision: 2)
    let remote = FakeConversationRemote(listResult: .failure(TestFailure.offline))
    remote.restoreResult = .success(restored)
    let local = FakeConversationLocal(listResult: [hidden], count: 1)
    let repository = ConversationRepository(remote: remote, local: local)
    _ = try await repository.restore(id: hidden.id)
    await repository.load(
      query: ConversationListQuery(starredOnly: false, date: nil, folderId: nil, includeDiscarded: true))
    XCTAssertEqual(repository.conversations, [restored])
  }

  func testRestoreFromPreviousAccountCannotPublishOrCache() async throws {
    let hidden = makeConversation(revision: 1, discarded: true)
    let restored = makeConversation(revision: 2)
    let suspended = SuspendedConversationResults()
    let remote = FakeConversationRemote(listResult: .success([hidden]))
    remote.restoreHandler = { try await suspended.result(for: $0) }
    let local = FakeConversationLocal()
    let repository = ConversationRepository(remote: remote, local: local)
    await repository.load(
      query: ConversationListQuery(starredOnly: false, date: nil, folderId: nil, includeDiscarded: true))
    local.stored.removeAll()
    let task = Task { try await repository.restore(id: hidden.id) }
    await suspended.waitUntilRequested(hidden.id)
    repository.reset()
    await suspended.resume(hidden.id, with: .success(restored))
    do {
      _ = try await task.value
      XCTFail("The previous account response must be cancelled")
    } catch is CancellationError {
    }
    XCTAssertTrue(repository.conversations.isEmpty)
    XCTAssertTrue(local.stored.isEmpty)
  }

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
    XCTAssertEqual(local.storeBatchCalls, 1, "A server page must enter the cache through one Siri sync batch")
  }

  func testCacheReloadDuringPendingMutationKeepsOptimisticStar() async throws {
    let unstarred = makeConversation(starred: false, revision: 1)
    let suspendedStars = SuspendedConversationResults()
    let remote = FakeConversationRemote(listResult: .success([unstarred]), countResult: .success(1))
    remote.starHandler = { starred in try await suspendedStars.result(for: String(starred)) }
    // The local cache still holds the pre-mutation (un-starred) row.
    let local = FakeConversationLocal(listResult: [unstarred], count: 1)
    let repository = ConversationRepository(remote: remote, local: local)
    await repository.load(query: .all)

    // Stage the optimistic star; the remote is suspended, so the mutation stays
    // pending (pendingMutations retains it) while we reload.
    let starTask = Task { try await repository.setStarred(id: unstarred.id, starred: true) }
    await suspendedStars.waitUntilRequested("true")
    XCTAssertTrue(repository.conversations[0].starred, "precondition: optimistic star is visible")

    // The user toggles a filter mid-mutation → load() re-runs the cache-first
    // path. Capture only the cache emit.
    var cacheSnapshots: [ConversationRepositorySnapshot] = []
    repository.onSnapshot = { if $0.source == .cache { cacheSnapshots.append($0) } }
    await repository.load(query: .all)

    XCTAssertEqual(
      cacheSnapshots.last?.conversations.first?.starred, true,
      "A cache reload mid-mutation must reapply the pending optimistic star, not revert it")

    // Let the mutation settle so the task doesn't leak.
    await suspendedStars.resume("true", with: .success(makeConversation(starred: true, revision: 2)))
    try await starTask.value
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

  func testLoadMoreAppendsTheNextServerPageWithoutReplacingTheVisibleList() async {
    let firstPage = (0..<50).map { index in
      makeConversation(id: "conversation-\(index)", title: "Conversation \(index)", revision: 100 - Double(index))
    }
    let second = makeConversation(id: "second", title: "Older", revision: 1)
    let remote = FakeConversationRemote(listResult: .success(firstPage), countResult: .success(51))
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())

    await repository.load(query: .all, includeCache: false)
    remote.listResult = .success([second])
    await repository.loadMore()

    XCTAssertEqual(repository.conversations.map(\.id), firstPage.map(\.id) + ["second"])
    XCTAssertEqual(remote.listRequests.map(\.offset), [0, 50])
    XCTAssertEqual(remote.listRequests.map(\.limit), [50, 50])
  }

  func testLoadMoreRemainsAvailableWhenServerCountFailsOverCachedCount() async {
    let firstPage = (0..<50).map { index in
      makeConversation(id: "conversation-\(index)", title: "Conversation \(index)", revision: 100 - Double(index))
    }
    let second = makeConversation(id: "second", title: "Older", revision: 1)
    let remote = FakeConversationRemote(listResult: .success(firstPage), countResult: .failure(TestFailure.offline))
    let repository = ConversationRepository(
      remote: remote,
      local: FakeConversationLocal(listResult: firstPage, count: 50)
    )

    await repository.load(query: .all)
    XCTAssertTrue(repository.hasMore)

    remote.listResult = .success([second])
    await repository.loadMore()

    XCTAssertEqual(repository.conversations.map(\.id), firstPage.map(\.id) + ["second"])
    XCTAssertEqual(remote.listRequests.map(\.offset), [0, 50])
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

  func testDetailByIdFetchesAConversationTheListNeverLoaded() async throws {
    let member = makeConversation(id: "other-device", title: "Pendant recording", revision: 2)
    let remote = FakeConversationRemote(detailResult: .success(member))
    let local = FakeConversationLocal()
    let repository = ConversationRepository(remote: remote, local: local)

    let result = try await repository.detail(id: "other-device")

    XCTAssertEqual(result.structured.title, "Pendant recording")
    XCTAssertEqual(local.stored.map(\.id), ["other-device"], "A fetched member is cached like any detail")
  }

  func testDetailByIdWithNothingCachedThrowsInsteadOfInventingARow() async {
    let repository = ConversationRepository(
      remote: FakeConversationRemote(detailResult: .failure(TestFailure.offline)),
      local: FakeConversationLocal()
    )
    do {
      _ = try await repository.detail(id: "missing")
      XCTFail("A failed by-id fetch with no cache and no seed must throw")
    } catch {
      XCTAssertTrue(error is TestFailure)
    }
  }

  func testDetailByIdFallsBackToTheCacheWhenOffline() async throws {
    let cached = makeConversation(id: "other-device", title: "Cached pendant", revision: 1)
    let repository = ConversationRepository(
      remote: FakeConversationRemote(detailResult: .failure(TestFailure.offline)),
      local: FakeConversationLocal(detailResult: cached)
    )
    let result = try await repository.detail(id: "other-device")
    XCTAssertEqual(result.structured.title, "Cached pendant")
  }

  func testResetRejectsDetailResponseFromPreviousSessionBeforeCacheWrite() async {
    let initial = makeConversation(title: "Previous account", revision: 1)
    let staleDetail = makeConversation(title: "Stale detail", revision: 2, transcript: "private transcript")
    let suspendedDetails = SuspendedConversationResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.detailHandler = { id in try await suspendedDetails.result(for: id) }
    let local = FakeConversationLocal()
    let repository = ConversationRepository(remote: remote, local: local)
    await repository.load(query: .all)
    local.stored.removeAll()

    let detailTask = Task {
      try await repository.detail(id: initial.id, seed: initial)
    }
    await suspendedDetails.waitUntilRequested(initial.id)
    repository.reset()
    await suspendedDetails.resume(initial.id, with: .success(staleDetail))

    do {
      _ = try await detailTask.value
      XCTFail("A detail response from the previous session must be cancelled")
    } catch is CancellationError {
      // Expected: stale account data must not publish or enter the current cache.
    } catch {
      XCTFail("Expected CancellationError, got \(error)")
    }
    XCTAssertTrue(repository.conversations.isEmpty)
    XCTAssertTrue(local.stored.isEmpty)
  }

  func testResetRejectsDetailCacheWriteSuspendedBeforeTransactionAdmission() async {
    let initial = makeConversation(title: "Previous account", revision: 1)
    let staleDetail = makeConversation(title: "Stale detail", revision: 2, transcript: "private transcript")
    let suspendedWrites = SuspendedCacheWrites()
    let remote = FakeConversationRemote(
      listResult: .success([initial]),
      countResult: .success(1),
      detailResult: .success(staleDetail)
    )
    let local = FakeConversationLocal()
    let repository = ConversationRepository(remote: remote, local: local)
    await repository.load(query: .all)
    local.stored.removeAll()
    local.events.removeAll()
    local.storeHandler = { conversation in await suspendedWrites.suspend(conversation.id) }

    let detailTask = Task { try await repository.detail(id: initial.id, seed: initial) }
    await suspendedWrites.waitUntilRequested(initial.id)
    repository.reset()
    await suspendedWrites.resume(initial.id)

    do {
      _ = try await detailTask.value
      XCTFail("A cache write fenced by reset must cancel the detail request")
    } catch is CancellationError {
      // Expected.
    } catch {
      XCTFail("Expected CancellationError, got \(error)")
    }
    XCTAssertTrue(local.stored.isEmpty)
    XCTAssertTrue(repository.conversations.isEmpty)
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

  func testResetRejectsMutationAcknowledgementFromPreviousSessionBeforeCacheWrite() async {
    let initial = makeConversation(title: "Previous account", revision: 1)
    let staleCanonical = makeConversation(title: "Stale acknowledgement", revision: 2)
    let suspendedTitles = SuspendedConversationResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.titleHandler = { title in try await suspendedTitles.result(for: title) }
    let local = FakeConversationLocal()
    let repository = ConversationRepository(remote: remote, local: local)
    await repository.load(query: .all)
    local.stored.removeAll()

    let mutationTask = Task {
      try await repository.updateTitle(id: initial.id, title: "New title")
    }
    await suspendedTitles.waitUntilRequested("New title")
    repository.reset()
    await suspendedTitles.resume("New title", with: .success(staleCanonical))

    do {
      try await mutationTask.value
      XCTFail("A mutation acknowledgement from the previous session must be cancelled")
    } catch is CancellationError {
      // Expected: stale account data must not publish or enter the current cache.
    } catch {
      XCTFail("Expected CancellationError, got \(error)")
    }
    XCTAssertTrue(repository.conversations.isEmpty)
    XCTAssertTrue(local.stored.isEmpty)
  }

  func testConcurrentTitleAndStarMutationsKeepBothOptimisticFieldsUntilAcknowledged() async throws {
    let initial = makeConversation(title: "Original", starred: false, revision: 1)
    let titleCanonical = makeConversation(title: "Renamed", starred: false, revision: 2)
    let starCanonical = makeConversation(title: "Renamed", starred: true, revision: 3)
    let suspendedTitles = SuspendedConversationResults()
    let suspendedStars = SuspendedConversationResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.titleHandler = { title in try await suspendedTitles.result(for: title) }
    remote.starHandler = { starred in try await suspendedStars.result(for: String(starred)) }
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    await repository.load(query: .all)

    let titleTask = Task { try await repository.updateTitle(id: initial.id, title: "Renamed") }
    await suspendedTitles.waitUntilRequested("Renamed")
    let starTask = Task { try await repository.setStarred(id: initial.id, starred: true) }
    await waitUntil { repository.conversations.first?.starred == true }

    XCTAssertEqual(repository.conversations[0].structured.title, "Renamed")
    XCTAssertTrue(repository.conversations[0].starred)
    let starRequestedBeforeTitleSettled = await suspendedStars.wasRequested("true")
    XCTAssertFalse(starRequestedBeforeTitleSettled, "Remote mutations for one conversation must be serialized")

    await suspendedTitles.resume("Renamed", with: .success(titleCanonical))
    try await titleTask.value
    XCTAssertEqual(repository.conversations[0].structured.title, "Renamed")
    XCTAssertTrue(
      repository.conversations[0].starred, "The title acknowledgement must not erase the queued star intent")

    await suspendedStars.waitUntilRequested("true")
    await suspendedStars.resume("true", with: .success(starCanonical))
    try await starTask.value
    XCTAssertEqual(repository.conversations, [starCanonical])
  }

  func testConcurrentTitleFailureRollsBackOnlyTitleAndKeepsStarIntent() async throws {
    let initial = makeConversation(title: "Original", starred: false, revision: 1)
    let starCanonical = makeConversation(title: "Original", starred: true, revision: 2)
    let suspendedTitles = SuspendedConversationResults()
    let suspendedStars = SuspendedConversationResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.titleHandler = { title in try await suspendedTitles.result(for: title) }
    remote.starHandler = { starred in try await suspendedStars.result(for: String(starred)) }
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    await repository.load(query: .all)

    let titleTask = Task { try await repository.updateTitle(id: initial.id, title: "Rejected") }
    await suspendedTitles.waitUntilRequested("Rejected")
    let starTask = Task { try await repository.setStarred(id: initial.id, starred: true) }
    await waitUntil { repository.conversations.first?.starred == true }

    await suspendedTitles.resume("Rejected", with: .failure(TestFailure.offline))
    do {
      try await titleTask.value
      XCTFail("Expected title failure")
    } catch TestFailure.offline {
      // Expected: the title caller receives its own failure.
    }
    XCTAssertEqual(repository.conversations[0].structured.title, "Original")
    XCTAssertTrue(repository.conversations[0].starred, "An unrelated optimistic star must survive title rollback")

    await suspendedStars.waitUntilRequested("true")
    await suspendedStars.resume("true", with: .success(starCanonical))
    try await starTask.value
    XCTAssertEqual(repository.conversations, [starCanonical])
  }

  func testQueuedSameFieldFailuresRollBackToLastConfirmedValue() async {
    let initial = makeConversation(title: "Original", revision: 1)
    let suspendedTitles = SuspendedConversationResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.titleHandler = { title in try await suspendedTitles.result(for: title) }
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    await repository.load(query: .all)

    let firstTask = Task { try await repository.updateTitle(id: initial.id, title: "First rejected title") }
    await suspendedTitles.waitUntilRequested("First rejected title")
    let secondTask = Task { try await repository.updateTitle(id: initial.id, title: "Second rejected title") }
    await waitUntil { repository.conversations.first?.structured.title == "Second rejected title" }
    let secondRequestedEarly = await suspendedTitles.wasRequested("Second rejected title")
    XCTAssertFalse(secondRequestedEarly)

    await suspendedTitles.resume("First rejected title", with: .failure(TestFailure.offline))
    do {
      try await firstTask.value
      XCTFail("Expected first title failure")
    } catch TestFailure.offline {
      // Expected.
    } catch {
      XCTFail("Unexpected first title error: \(error)")
    }

    await suspendedTitles.waitUntilRequested("Second rejected title")
    await suspendedTitles.resume("Second rejected title", with: .failure(TestFailure.offline))
    do {
      try await secondTask.value
      XCTFail("Expected second title failure")
    } catch TestFailure.offline {
      // Expected.
    } catch {
      XCTFail("Unexpected second title error: \(error)")
    }

    XCTAssertEqual(repository.conversations, [initial])
  }

  func testDuplicateTitleFailureDoesNotClearNewerIdenticalIntent() async {
    let initial = makeConversation(title: "Original", revision: 1)
    let sequencedTitles = SequencedConversationResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.titleHandler = { title in try await sequencedTitles.result(for: title) }
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    var optimisticCount = 0
    repository.onSnapshot = { snapshot in
      if snapshot.source == .optimistic { optimisticCount += 1 }
    }
    await repository.load(query: .all)

    let firstTask = Task { try await repository.updateTitle(id: initial.id, title: "Same title") }
    await sequencedTitles.waitUntilRequestCount(1)
    let secondTask = Task { try await repository.updateTitle(id: initial.id, title: "Same title") }
    await waitUntil { optimisticCount == 2 }

    await sequencedTitles.resume(at: 0, with: .failure(TestFailure.offline))
    do {
      try await firstTask.value
      XCTFail("Expected first title failure")
    } catch TestFailure.offline {
      // Expected.
    } catch {
      XCTFail("Unexpected first title error: \(error)")
    }
    XCTAssertEqual(repository.conversations[0].structured.title, "Same title")

    await sequencedTitles.waitUntilRequestCount(2)
    await sequencedTitles.resume(at: 1, with: .failure(TestFailure.offline))
    do {
      try await secondTask.value
      XCTFail("Expected second title failure")
    } catch TestFailure.offline {
      // Expected.
    } catch {
      XCTFail("Unexpected second title error: \(error)")
    }
    XCTAssertEqual(repository.conversations, [initial])
  }

  func testCyclicTitleAcknowledgementsAndRefreshPreserveLatestIntent() async throws {
    let initial = makeConversation(title: "Original", revision: 1)
    let firstCanonical = makeConversation(title: "A", revision: 2)
    let secondCanonical = makeConversation(title: "B", revision: 3)
    let thirdCanonical = makeConversation(title: "A", revision: 4)
    let sequencedTitles = SequencedConversationResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.titleHandler = { title in try await sequencedTitles.result(for: title) }
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    var optimisticCount = 0
    repository.onSnapshot = { snapshot in
      if snapshot.source == .optimistic { optimisticCount += 1 }
    }
    await repository.load(query: .all)

    let firstTask = Task { try await repository.updateTitle(id: initial.id, title: "A") }
    await sequencedTitles.waitUntilRequestCount(1)
    let secondTask = Task { try await repository.updateTitle(id: initial.id, title: "B") }
    let thirdTask = Task { try await repository.updateTitle(id: initial.id, title: "A") }
    await waitUntil { optimisticCount == 3 }

    remote.listResult = .success([firstCanonical])
    await repository.refresh(query: .all)
    XCTAssertEqual(
      repository.conversations[0].structured.title,
      "A",
      "A refresh reflecting the first A must not clear the newer queued A operation"
    )

    await sequencedTitles.resume(at: 0, with: .success(firstCanonical))
    try await firstTask.value
    XCTAssertEqual(repository.conversations[0].structured.title, "A")

    await sequencedTitles.waitUntilRequestCount(2)
    await sequencedTitles.resume(at: 1, with: .success(secondCanonical))
    try await secondTask.value
    XCTAssertEqual(repository.conversations[0].structured.title, "A")

    await sequencedTitles.waitUntilRequestCount(3)
    await sequencedTitles.resume(at: 2, with: .success(thirdCanonical))
    try await thirdTask.value
    XCTAssertEqual(repository.conversations, [thirdCanonical])
  }

  private func waitUntil(_ condition: () -> Bool) async {
    for _ in 0..<1_000 {
      if condition() { return }
      await Task.yield()
    }
    XCTFail("Condition did not become true after yielding to pending tasks")
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

  func testCurrentSessionCancellationRollsBackItsOptimisticField() async {
    let initial = makeConversation(title: "Original", revision: 1)
    let suspendedTitles = SuspendedConversationResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.titleHandler = { title in try await suspendedTitles.result(for: title) }
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    var snapshots: [ConversationRepositorySnapshot] = []
    repository.onSnapshot = { snapshots.append($0) }
    await repository.load(query: .all)
    snapshots.removeAll()

    let task = Task { try await repository.updateTitle(id: initial.id, title: "Cancelled") }
    await suspendedTitles.waitUntilRequested("Cancelled")
    await suspendedTitles.resume("Cancelled", with: .failure(CancellationError()))

    do {
      try await task.value
      XCTFail("Expected cancellation")
    } catch is CancellationError {
      // Expected.
    } catch {
      XCTFail("Expected CancellationError, got \(error)")
    }
    XCTAssertEqual(snapshots.map(\.source), [.optimistic, .rollback])
    XCTAssertEqual(repository.conversations, [initial])
  }

  func testTaskCancelledWhileQueuedRollsBackWithoutCallingRemote() async throws {
    let initial = makeConversation(title: "Original", revision: 1)
    let firstCanonical = makeConversation(title: "First", revision: 2)
    let suspendedTitles = SuspendedConversationResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.titleHandler = { title in try await suspendedTitles.result(for: title) }
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    var optimisticCount = 0
    repository.onSnapshot = { snapshot in
      if snapshot.source == .optimistic { optimisticCount += 1 }
    }
    await repository.load(query: .all)

    let firstTask = Task { try await repository.updateTitle(id: initial.id, title: "First") }
    await suspendedTitles.waitUntilRequested("First")
    let queuedTask = Task { try await repository.updateTitle(id: initial.id, title: "Never sent") }
    await waitUntil { optimisticCount == 2 }
    queuedTask.cancel()

    await suspendedTitles.resume("First", with: .success(firstCanonical))
    try await firstTask.value
    do {
      try await queuedTask.value
      XCTFail("Expected queued task cancellation")
    } catch is CancellationError {
      // Expected.
    } catch {
      XCTFail("Expected CancellationError, got \(error)")
    }

    let queuedRequestWasSent = await suspendedTitles.wasRequested("Never sent")
    XCTAssertFalse(queuedRequestWasSent)
    XCTAssertEqual(repository.conversations, [firstCanonical])
  }

  func testSuccessfulMutationCommitsCanonicalStateDespiteCallerCancellationAfterRemote() async throws {
    let initial = makeConversation(title: "Original", revision: 1)
    let canonical = makeConversation(title: "Applied", revision: 2)
    let suspendedTitles = SuspendedConversationResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.titleHandler = { title in try await suspendedTitles.result(for: title) }
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    await repository.load(query: .all)

    let task = Task { try await repository.updateTitle(id: initial.id, title: "Applied") }
    await suspendedTitles.waitUntilRequested("Applied")
    await suspendedTitles.resume("Applied", with: .success(canonical))
    task.cancel()

    _ = try? await task.value
    XCTAssertEqual(repository.conversations, [canonical])
  }

  func testDeleteCancelledWhileQueuedDoesNotCallRemote() async throws {
    let initial = makeConversation(title: "Original", revision: 1)
    let firstCanonical = makeConversation(title: "First", revision: 2)
    let suspendedTitles = SuspendedConversationResults()
    let suspendedDeletes = SuspendedVoidResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.titleHandler = { title in try await suspendedTitles.result(for: title) }
    remote.deleteHandler = { id in try await suspendedDeletes.result(for: id) }
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    await repository.load(query: .all)

    let titleTask = Task { try await repository.updateTitle(id: initial.id, title: "First") }
    await suspendedTitles.waitUntilRequested("First")
    let deleteTask = Task { try await repository.delete(id: initial.id) }
    deleteTask.cancel()

    await suspendedTitles.resume("First", with: .success(firstCanonical))
    try await titleTask.value
    do {
      try await deleteTask.value
      XCTFail("Expected queued delete cancellation")
    } catch is CancellationError {
      // Expected.
    } catch {
      XCTFail("Expected CancellationError, got \(error)")
    }

    XCTAssertTrue(remote.deletedIds.isEmpty)
    XCTAssertEqual(repository.conversations, [firstCanonical])
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

  func testDeletingALoadedRowKeepsLoadMoreAlignedWithTheServerPage() async throws {
    // Regression: the server pages conversations by offset, so deleting a
    // loaded row shifts every older row up one slot. Without lowering
    // nextPageOffset alongside count, loadMore() re-requests one row too
    // late and skips the row that moved into the loaded window.
    let firstPage = (0..<50).map { index in
      makeConversation(id: "conversation-\(index)", title: "Conversation \(index)", revision: 100 - Double(index))
    }
    let skippedIfBuggy = makeConversation(id: "fifty-first", title: "Should not be skipped", revision: 1)
    let remote = FakeConversationRemote(
      listResult: .success(firstPage), countResult: .success(51), deleteResult: .success(()))
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    await repository.load(query: .all, includeCache: false)
    XCTAssertTrue(repository.hasMore)

    try await repository.delete(id: firstPage[0].id)

    remote.listResult = .success([skippedIfBuggy])
    await repository.loadMore()

    XCTAssertEqual(remote.listRequests.last?.offset, 49, "a loaded-row delete must shift the next offset back by one")
    XCTAssertTrue(repository.conversations.contains { $0.id == skippedIfBuggy.id })
  }

  func testUnstarringUnderTheStarredFilterKeepsLoadMoreAlignedWithTheServerPage() async throws {
    let starred = makeConversation(starred: true, revision: 1)
    let canonical = makeConversation(starred: false, revision: 2)
    let skippedIfBuggy = makeConversation(id: "skipped", title: "Should not be skipped", starred: true, revision: 3)
    let remote = FakeConversationRemote(
      listResult: .success([starred]), countResult: .success(2), starResult: .success(canonical))
    let repository = ConversationRepository(remote: remote, local: FakeConversationLocal())
    await repository.load(query: ConversationListQuery(starredOnly: true, date: nil, folderId: nil))
    XCTAssertTrue(repository.hasMore)

    try await repository.setStarred(id: starred.id, starred: false)
    XCTAssertTrue(repository.conversations.isEmpty, "precondition: the unstarred row left the Starred filter")

    remote.listResult = .success([skippedIfBuggy])
    await repository.loadMore()

    XCTAssertEqual(remote.listRequests.last?.offset, 0, "unstarring the only loaded row must not skip ahead")
    XCTAssertTrue(repository.conversations.contains { $0.id == skippedIfBuggy.id })
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

  func testDeleteSerializesBehindMutationAndCannotBeUndoneByItsAcknowledgement() async throws {
    let initial = makeConversation(title: "Original", revision: 1)
    let renamed = makeConversation(title: "Renamed", revision: 2)
    let suspendedTitles = SuspendedConversationResults()
    let suspendedDeletes = SuspendedVoidResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.titleHandler = { title in try await suspendedTitles.result(for: title) }
    remote.deleteHandler = { id in try await suspendedDeletes.result(for: id) }
    let local = FakeConversationLocal()
    let repository = ConversationRepository(remote: remote, local: local)
    await repository.load(query: .all)
    local.events.removeAll()

    let titleTask = Task { try await repository.updateTitle(id: initial.id, title: "Renamed") }
    await suspendedTitles.waitUntilRequested("Renamed")
    let deleteTask = Task { try await repository.delete(id: initial.id) }

    await suspendedTitles.resume("Renamed", with: .success(renamed))
    try await titleTask.value
    await suspendedDeletes.waitUntilRequested(initial.id)
    await suspendedDeletes.resume(initial.id, with: .success(()))
    try await deleteTask.value

    XCTAssertEqual(local.events, ["store:\(initial.id)", "delete:\(initial.id)"])
    XCTAssertTrue(repository.conversations.isEmpty)
    XCTAssertEqual(repository.count, 0)
  }

  func testResetRejectsDeleteAcknowledgementFromPreviousSession() async {
    let initial = makeConversation(title: "Previous account", revision: 1)
    let suspendedDeletes = SuspendedVoidResults()
    let remote = FakeConversationRemote(listResult: .success([initial]), countResult: .success(1))
    remote.deleteHandler = { id in try await suspendedDeletes.result(for: id) }
    let local = FakeConversationLocal()
    let repository = ConversationRepository(remote: remote, local: local)
    await repository.load(query: .all)

    let deleteTask = Task { try await repository.delete(id: initial.id) }
    await suspendedDeletes.waitUntilRequested(initial.id)
    repository.reset()
    await suspendedDeletes.resume(initial.id, with: .success(()))

    do {
      try await deleteTask.value
      XCTFail("A delete acknowledgement from the previous session must be cancelled")
    } catch is CancellationError {
      // Expected.
    } catch {
      XCTFail("Expected CancellationError, got \(error)")
    }
    XCTAssertTrue(local.deletedIds.isEmpty)
    XCTAssertTrue(repository.conversations.isEmpty)
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

  func testRuntimeOwnerChangeClearsThePreviousAccountsConversations() async {
    // Regression: an in-place account switch posts only .runtimeOwnerDidChange
    // (never .userDidSignOut). Without the repository's own owner fence, the
    // previous account's conversations kept rendering for the next account and
    // ConversationsPage.onAppear skipped its reload because the array was
    // non-empty.
    let previousOwners = makeConversation(title: "Previous account's conversation", revision: 1)
    let remote = FakeConversationRemote(
      listResult: .success([previousOwners]), countResult: .success(1))
    let repository = ConversationRepository(
      remote: remote,
      local: FakeConversationLocal(listResult: [], count: 0)
    )
    var snapshots: [ConversationRepositorySnapshot] = []
    repository.onSnapshot = { snapshots.append($0) }
    await repository.load(query: .all)
    XCTAssertFalse(repository.conversations.isEmpty, "precondition: previous account's rows are loaded")

    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)

    XCTAssertTrue(
      repository.conversations.isEmpty,
      "an in-place account switch must clear the previous account's conversations")
    XCTAssertEqual(
      snapshots.last?.conversations.count, 0,
      "the cleared state must be published so the UI empties and the page reloads")
  }

  private func makeConversation(
    id: String = "conversation-1",
    title: String = "Title",
    overview: String = "Overview",
    status: ConversationStatus = .completed,
    starred: Bool = false,
    revision: TimeInterval?,
    transcript: String? = nil,
    discarded: Bool = false,
    deleted: Bool = false
  ) -> ServerConversation {
    let created = Date(timeIntervalSince1970: 100)
    let segments =
      transcript.map {
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
      updatedAt: revision.map { Date(timeIntervalSince1970: $0) },
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
      discarded: discarded,
      deleted: deleted,
      isLocked: false,
      starred: starred,
      folderId: nil,
      inputDeviceName: nil
    )
  }
}

extension ConversationListQuery {
  fileprivate static let all = ConversationListQuery(starredOnly: false, date: nil, folderId: nil)
}

private enum TestFailure: Error {
  case offline
}

@MainActor
private final class FakeConversationRemote: ConversationRemoteDataSource {
  var listResult: Result<[ServerConversation], Error>
  var countResult: Result<Int, Error>
  var detailResult: Result<ServerConversation, Error>
  var starResult: Result<ServerConversation, Error>
  var titleResult: Result<ServerConversation, Error>
  var folderResult: Result<ServerConversation, Error>
  var searchResult: Result<[ServerConversation], Error>
  var restoreResult: Result<ServerConversation, Error> = .failure(TestFailure.offline)
  var restoreHandler: ((String) async throws -> ServerConversation)?
  var listQueries: [ConversationListQuery] = []
  var countQueries: [ConversationListQuery] = []
  var searchDiscardedScopes: [Bool] = []
  var deleteResult: Result<Void, Error>
  var listHandler: ((ConversationListQuery) async throws -> [ServerConversation])?
  var searchHandler: ((String) async throws -> [ServerConversation])?
  var detailHandler: ((String) async throws -> ServerConversation)?
  var starHandler: ((Bool) async throws -> ServerConversation)?
  var titleHandler: ((String) async throws -> ServerConversation)?
  var deleteHandler: ((String) async throws -> Void)?
  var deletedIds: [String] = []
  var listRequests: [(offset: Int, limit: Int)] = []

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

  func list(query: ConversationListQuery, offset: Int, limit: Int) async throws -> [ServerConversation] {
    listQueries.append(query)
    listRequests.append((offset: offset, limit: limit))
    if let listHandler { return try await listHandler(query) }
    return try listResult.get()
  }
  func count(query: ConversationListQuery) async throws -> Int {
    countQueries.append(query)
    return try countResult.get()
  }
  func detail(id: String) async throws -> ServerConversation {
    if let detailHandler { return try await detailHandler(id) }
    return try detailResult.get()
  }
  func search(text: String, includeDiscarded: Bool) async throws -> [ServerConversation] {
    searchDiscardedScopes.append(includeDiscarded)
    if let searchHandler { return try await searchHandler(text) }
    return try searchResult.get()
  }
  func restore(id: String) async throws -> ServerConversation {
    if let restoreHandler { return try await restoreHandler(id) }
    return try restoreResult.get()
  }
  func setStarred(id: String, starred: Bool) async throws -> ServerConversation {
    if let starHandler { return try await starHandler(starred) }
    return try starResult.get()
  }
  func updateTitle(id: String, title: String) async throws -> ServerConversation {
    if let titleHandler { return try await titleHandler(title) }
    return try titleResult.get()
  }
  func moveToFolder(id: String, folderId: String?) async throws -> ServerConversation { try folderResult.get() }
  func delete(id: String) async throws {
    if let deleteHandler {
      try await deleteHandler(id)
      deletedIds.append(id)
      return
    }
    try deleteResult.get()
    deletedIds.append(id)
  }
}

@MainActor
private final class FakeConversationLocal: ConversationLocalDataSource {
  var listResult: [ServerConversation]
  var countValue: Int
  var detailResult: ServerConversation?
  var stored: [ServerConversation] = []
  var storeBatchCalls = 0
  var deletedIds: [String] = []
  var events: [String] = []
  var storeHandler: ((ServerConversation) async throws -> Void)?

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
  func store(
    _ conversation: ServerConversation,
    scope: ConversationCacheWriteScope,
    generation: Int
  ) async throws {
    if let storeHandler { try await storeHandler(conversation) }
    try scope.withCurrent(generation) {
      stored.append(conversation)
      events.append("store:\(conversation.id)")
    }
  }

  func storeMany(
    _ conversations: [ServerConversation],
    scope: ConversationCacheWriteScope,
    generation: Int
  ) async throws {
    storeBatchCalls += 1
    for conversation in conversations {
      try await store(conversation, scope: scope, generation: generation)
    }
  }

  func delete(
    id: String,
    scope: ConversationCacheWriteScope,
    generation: Int
  ) async throws {
    try scope.withCurrent(generation) {
      deletedIds.append(id)
      events.append("delete:\(id)")
    }
  }
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

private actor SuspendedConversationResults {
  private var requested: Set<String> = []
  private var requestWaiters: [String: CheckedContinuation<Void, Never>] = [:]
  private var resultContinuations: [String: CheckedContinuation<ServerConversation, Error>] = [:]

  func result(for key: String) async throws -> ServerConversation {
    requested.insert(key)
    requestWaiters.removeValue(forKey: key)?.resume()
    return try await withCheckedThrowingContinuation { continuation in
      resultContinuations[key] = continuation
    }
  }

  func waitUntilRequested(_ key: String) async {
    if requested.contains(key) { return }
    await withCheckedContinuation { continuation in
      requestWaiters[key] = continuation
    }
  }

  func wasRequested(_ key: String) -> Bool {
    requested.contains(key)
  }

  func resume(_ key: String, with result: Result<ServerConversation, Error>) {
    resultContinuations.removeValue(forKey: key)?.resume(with: result)
  }
}

private actor SequencedConversationResults {
  private var requestedValues: [String] = []
  private var requestCountWaiters: [Int: [CheckedContinuation<Void, Never>]] = [:]
  private var resultContinuations: [Int: CheckedContinuation<ServerConversation, Error>] = [:]

  func result(for value: String) async throws -> ServerConversation {
    let index = requestedValues.count
    requestedValues.append(value)
    let requestCount = requestedValues.count
    for count in requestCountWaiters.keys where count <= requestCount {
      let waiters = requestCountWaiters.removeValue(forKey: count) ?? []
      for waiter in waiters { waiter.resume() }
    }
    return try await withCheckedThrowingContinuation { continuation in
      resultContinuations[index] = continuation
    }
  }

  func waitUntilRequestCount(_ count: Int) async {
    if requestedValues.count >= count { return }
    await withCheckedContinuation { continuation in
      requestCountWaiters[count, default: []].append(continuation)
    }
  }

  func resume(at index: Int, with result: Result<ServerConversation, Error>) {
    resultContinuations.removeValue(forKey: index)?.resume(with: result)
  }
}

private actor SuspendedVoidResults {
  private var requested: Set<String> = []
  private var requestWaiters: [String: CheckedContinuation<Void, Never>] = [:]
  private var resultContinuations: [String: CheckedContinuation<Void, Error>] = [:]

  func result(for key: String) async throws {
    requested.insert(key)
    requestWaiters.removeValue(forKey: key)?.resume()
    return try await withCheckedThrowingContinuation { continuation in
      resultContinuations[key] = continuation
    }
  }

  func waitUntilRequested(_ key: String) async {
    if requested.contains(key) { return }
    await withCheckedContinuation { continuation in
      requestWaiters[key] = continuation
    }
  }

  func resume(_ key: String, with result: Result<Void, Error>) {
    resultContinuations.removeValue(forKey: key)?.resume(with: result)
  }
}

private actor SuspendedCacheWrites {
  private var requested: Set<String> = []
  private var requestWaiters: [String: CheckedContinuation<Void, Never>] = [:]
  private var writeContinuations: [String: CheckedContinuation<Void, Never>] = [:]

  func suspend(_ key: String) async {
    requested.insert(key)
    requestWaiters.removeValue(forKey: key)?.resume()
    await withCheckedContinuation { continuation in
      writeContinuations[key] = continuation
    }
  }

  func waitUntilRequested(_ key: String) async {
    if requested.contains(key) { return }
    await withCheckedContinuation { continuation in
      requestWaiters[key] = continuation
    }
  }

  func resume(_ key: String) {
    writeContinuations.removeValue(forKey: key)?.resume()
  }
}
