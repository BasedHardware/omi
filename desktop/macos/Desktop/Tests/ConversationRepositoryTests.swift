import Combine
import XCTest
@testable import Omi_Computer

private actor ConversationTestGate {
  private var released = false
  private var waiters: [CheckedContinuation<Void, Never>] = []
  private var observers: [CheckedContinuation<Void, Never>] = []

  func wait() async {
    observers.forEach { $0.resume() }
    observers.removeAll()
    guard !released else { return }
    await withCheckedContinuation { waiters.append($0) }
  }

  func waitUntilBlocked() async {
    guard !released, waiters.isEmpty else { return }
    await withCheckedContinuation { observers.append($0) }
  }

  func release() {
    released = true
    waiters.forEach { $0.resume() }
    waiters.removeAll()
    observers.forEach { $0.resume() }
    observers.removeAll()
  }
}

private enum ConversationRemoteStubError: Error {
  case mutationFailed
}

private actor ConversationRemoteStub: ConversationRemoteServing {
  var listResult: [ServerConversation]
  var listError: Error?
  var detailById: [String: ServerConversation]
  var detailError: Error?
  var titleResult: ServerConversation?
  var starredResult: ServerConversation?
  var folderResult: ServerConversation?
  var mutationError: Error?
  let listGate: ConversationTestGate?
  let searchResults: [String: [ServerConversation]]
  let searchGates: [String: ConversationTestGate]
  let titleResults: [String: ServerConversation]
  let titleGates: [String: ConversationTestGate]
  let starredGate: ConversationTestGate?
  let deleteGate: ConversationTestGate?
  let titleErrors: [String: Error]
  let starredError: Error?
  let lightweightAcks: Bool
  let statusOnlyAcks: Bool
  private var titleRequests: [String] = []

  init(
    list: [ServerConversation],
    listError: Error? = nil,
    detailById: [String: ServerConversation] = [:],
    detailError: Error? = nil,
    titleResult: ServerConversation? = nil,
    starredResult: ServerConversation? = nil,
    folderResult: ServerConversation? = nil,
    mutationError: Error? = nil,
    listGate: ConversationTestGate? = nil,
    searchResults: [String: [ServerConversation]] = [:],
    searchGates: [String: ConversationTestGate] = [:],
    titleResults: [String: ServerConversation] = [:],
    titleGates: [String: ConversationTestGate] = [:],
    starredGate: ConversationTestGate? = nil,
    deleteGate: ConversationTestGate? = nil,
    titleErrors: [String: Error] = [:],
    starredError: Error? = nil,
    lightweightAcks: Bool = false,
    statusOnlyAcks: Bool = false
  ) {
    listResult = list
    self.listError = listError
    self.detailById = detailById
    self.detailError = detailError
    self.titleResult = titleResult
    self.starredResult = starredResult
    self.folderResult = folderResult
    self.mutationError = mutationError
    self.listGate = listGate
    self.searchResults = searchResults
    self.searchGates = searchGates
    self.titleResults = titleResults
    self.titleGates = titleGates
    self.starredGate = starredGate
    self.deleteGate = deleteGate
    self.titleErrors = titleErrors
    self.starredError = starredError
    self.lightweightAcks = lightweightAcks
    self.statusOnlyAcks = statusOnlyAcks
  }

  func list(query: ConversationQuery) async throws -> [ServerConversation] {
    await listGate?.wait()
    if let listError { throw listError }
    return listResult
  }

  func count(query: ConversationQuery) async throws -> Int { listResult.count }

  func detail(id: String) async throws -> ServerConversation {
    if let detailError { throw detailError }
    return detailById[id] ?? listResult.first { $0.id == id }!
  }

  func search(query: String, limit: Int) async throws -> [ServerConversation] {
    await searchGates[query]?.wait()
    return searchResults[query] ?? listResult
  }

  func updateTitle(id: String, title: String) async throws -> ConversationMutationAcknowledgement {
    titleRequests.append(title)
    await titleGates[title]?.wait()
    if let error = titleErrors[title] { throw error }
    if let mutationError { throw mutationError }
    let conversation = titleResults[title] ?? titleResult ?? listResult.first { $0.id == id }!
    return ConversationMutationAcknowledgement(
      id: id,
      updatedAt: statusOnlyAcks ? nil : conversation.updatedAt,
      revision: statusOnlyAcks ? nil : conversation.revision,
      value: .title(title),
      conversation: (lightweightAcks || statusOnlyAcks) ? nil : conversation
    )
  }

  func updateStarred(id: String, starred: Bool) async throws -> ConversationMutationAcknowledgement {
    await starredGate?.wait()
    if let starredError { throw starredError }
    if let mutationError { throw mutationError }
    let conversation = starredResult ?? listResult.first { $0.id == id }!
    return ConversationMutationAcknowledgement(
      id: id,
      updatedAt: statusOnlyAcks ? nil : conversation.updatedAt,
      revision: statusOnlyAcks ? nil : conversation.revision,
      value: .starred(starred),
      conversation: (lightweightAcks || statusOnlyAcks) ? nil : conversation
    )
  }

  func moveToFolder(id: String, folderId: String?) async throws -> ConversationMutationAcknowledgement {
    if let mutationError { throw mutationError }
    let conversation = folderResult ?? listResult.first { $0.id == id }!
    return ConversationMutationAcknowledgement(
      id: id,
      updatedAt: statusOnlyAcks ? nil : conversation.updatedAt,
      revision: statusOnlyAcks ? nil : conversation.revision,
      value: .folder(folderId),
      conversation: (lightweightAcks || statusOnlyAcks) ? nil : conversation
    )
  }

  func delete(id: String) async throws {
    await deleteGate?.wait()
    if let mutationError { throw mutationError }
  }

  func requestedTitles() -> [String] { titleRequests }

  func setListError(_ error: Error?) { listError = error }
}

private actor ConversationCacheStub: ConversationCachePersisting {
  private struct PendingTitleObserver {
    let conversationId: String
    let title: String
    let continuation: CheckedContinuation<Void, Never>
  }

  private var entries: [String: ConversationCacheEntry]
  private var order: [String]
  private var pending: [String: ConversationPendingMutation]
  private let idLoadGate: ConversationTestGate?
  private let listLoadGate: ConversationTestGate?
  private let pendingLoadGate: ConversationTestGate?
  private let pendingSaveError: Error?
  private var serverUpsertAccounts: [String] = []
  private var pendingTitleObservers: [PendingTitleObserver] = []

  init(
    entries: [ConversationCacheEntry] = [],
    pending: [String: ConversationPendingMutation] = [:],
    idLoadGate: ConversationTestGate? = nil,
    listLoadGate: ConversationTestGate? = nil,
    pendingLoadGate: ConversationTestGate? = nil,
    pendingSaveError: Error? = nil
  ) {
    self.entries = Dictionary(uniqueKeysWithValues: entries.map { ($0.conversation.id, $0) })
    order = entries.map { $0.conversation.id }
    self.pending = pending
    self.idLoadGate = idLoadGate
    self.listLoadGate = listLoadGate
    self.pendingLoadGate = pendingLoadGate
    self.pendingSaveError = pendingSaveError
  }

  func load(query: ConversationQuery, accountId: String) async throws -> [ConversationCacheEntry] {
    await listLoadGate?.wait()
    return order.compactMap { entries[$0] }.filter { entry in
      (!query.showStarredOnly || entry.conversation.starred)
        && (query.folderId == nil || entry.conversation.folderId == query.folderId)
    }
  }

  func load(id: String, accountId: String) async throws -> ConversationCacheEntry? {
    await idLoadGate?.wait()
    return entries[id]
  }
  func isEmpty(accountId: String) async throws -> Bool { entries.isEmpty }

  func applyServerSnapshot(
    _ conversations: [ServerConversation],
    query: ConversationQuery,
    fetchedAt: Date,
    accountId: String
  ) async throws {
    serverUpsertAccounts.append(accountId)
    for conversation in conversations {
      let cached = entries[conversation.id]
      var completeness: ConversationCompleteness = [.list]
      if conversation.transcriptSegmentsIncluded { completeness.insert(.transcript) }
      entries[conversation.id] = ConversationProjectionMerge.merge(
        incoming: conversation,
        incomingCompleteness: completeness,
        cached: cached,
        fetchedAt: fetchedAt
      )
    }
    order = conversations.map(\.id)
  }

  func upsertServerConversation(
    _ conversation: ServerConversation,
    completeness: ConversationCompleteness,
    fetchedAt: Date,
    accountId: String,
    preserveProjectionFreshness: Bool = false
  ) async throws {
    serverUpsertAccounts.append(accountId)
    let previous = entries[conversation.id]
    entries[conversation.id] = ConversationProjectionMerge.merge(
      incoming: conversation,
      incomingCompleteness: completeness,
      cached: entries[conversation.id],
      fetchedAt: fetchedAt
    )
    if preserveProjectionFreshness, let previous, let merged = entries[conversation.id] {
      entries[conversation.id] = ConversationCacheEntry(
        conversation: merged.conversation,
        completeness: merged.completeness,
        cacheWrittenAt: fetchedAt,
        listFetchedAt: previous.listFetchedAt,
        detailFetchedAt: previous.detailFetchedAt,
        transcriptFetchedAt: previous.transcriptFetchedAt
      )
    }
    if !order.contains(conversation.id) { order.append(conversation.id) }
  }

  func remove(id: String, accountId: String) async throws {
    entries.removeValue(forKey: id)
    order.removeAll { $0 == id }
  }

  func loadPendingMutations(accountId: String) async throws -> [String: ConversationPendingMutation] {
    let snapshot = pending
    await pendingLoadGate?.wait()
    return snapshot
  }

  func savePendingMutation(
    _ mutation: ConversationPendingMutation?,
    conversationId: String,
    accountId: String
  ) async throws {
    if let pendingSaveError { throw pendingSaveError }
    if let mutation, !mutation.isEmpty {
      pending[conversationId] = mutation
    } else {
      pending.removeValue(forKey: conversationId)
    }
    let ready = pendingTitleObservers.filter {
      $0.conversationId == conversationId && pending[conversationId]?.title == $0.title
    }
    pendingTitleObservers.removeAll { observer in
      ready.contains { $0.conversationId == observer.conversationId && $0.title == observer.title }
    }
    ready.forEach { $0.continuation.resume() }
  }

  func invalidateCache() async {}

  func recordedServerUpsertAccounts() -> [String] { serverUpsertAccounts }

  func waitUntilPendingTitle(_ title: String, conversationId: String) async {
    if pending[conversationId]?.title == title { return }
    await withCheckedContinuation { continuation in
      pendingTitleObservers.append(
        PendingTitleObserver(
          conversationId: conversationId,
          title: title,
          continuation: continuation
        )
      )
    }
  }
}

@MainActor
final class ConversationRepositoryTests: XCTestCase {
  func testCacheRendersBeforeBlockedServerRefreshThenReconciles() async throws {
    let cached = makeConversation(id: "c1", title: "Cached", overview: "old", revision: "1")
    let server = makeConversation(id: "c1", title: "Server", overview: "fresh", revision: "2")
    let cache = ConversationCacheStub(entries: [entry(cached)])
    let gate = ConversationTestGate()
    let remote = ConversationRemoteStub(list: [server], listGate: gate)
    let repository = ConversationRepository(
      remote: remote,
      cache: cache,
      legacyMigrationEnabled: false
    )

    let load = Task { await repository.load(query: ConversationQuery()) }
    await gate.waitUntilBlocked()

    XCTAssertEqual(repository.conversations.first?.structured.title, "Cached")
    XCTAssertFalse(repository.isLoading, "cached first paint should clear the blocking loading state")

    await gate.release()
    await load.value

    XCTAssertEqual(repository.conversations.first?.structured.title, "Server")
    XCTAssertEqual(repository.conversations.first?.structured.overview, "fresh")
  }

  func testListProjectionCannotEraseCompleteCachedTranscript() {
    let cached = makeConversation(
      id: "c1",
      title: "Cached",
      overview: "old",
      revision: "1",
      transcript: [makeSegment(text: "offline transcript")],
      transcriptIncluded: true
    )
    let incoming = makeConversation(
      id: "c1",
      title: "Server",
      overview: "fresh",
      revision: "2",
      transcript: [],
      transcriptIncluded: false
    )

    let merged = ConversationProjectionMerge.merge(
      incoming: incoming,
      incomingCompleteness: [.list],
      cached: ConversationCacheEntry(
        conversation: cached,
        completeness: [.list, .detail, .transcript],
        cacheWrittenAt: Date(timeIntervalSince1970: 1)
      )
    )

    XCTAssertEqual(merged.conversation.structured.overview, "fresh")
    XCTAssertEqual(merged.conversation.transcriptSegments.map(\.text), ["offline transcript"])
    XCTAssertTrue(merged.completeness.contains(.transcript))
  }

  func testSeedIsIdempotentAndCannotDowngradeEqualVersionDetail() {
    let rich = makeConversation(
      id: "c1",
      title: "Canonical",
      revision: "2",
      transcript: [makeSegment(text: "complete transcript")],
      transcriptIncluded: true
    )
    let listProjection = makeConversation(id: "c1", title: "Canonical", revision: "2")
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(list: []),
      cache: ConversationCacheStub(),
      legacyMigrationEnabled: false
    )
    repository.seed(rich)
    var notifications = 0
    let cancellable = repository.objectWillChange.sink { notifications += 1 }

    repository.seed(listProjection)

    XCTAssertEqual(repository.conversation(id: "c1")?.transcriptSegments.map(\.text), ["complete transcript"])
    XCTAssertTrue(repository.metadata(id: "c1")?.completeness.contains(.detail) == true)
    XCTAssertEqual(notifications, 0)
    withExtendedLifetime(cancellable) {}
  }

  func testSeedPublishesSameVersionTranscriptSpeakerChanges() {
    let originalSegment = TranscriptSegment(
      id: "segment-1",
      text: "Speaker text",
      speaker: "SPEAKER_00",
      isUser: false,
      personId: nil,
      start: 0,
      end: 1
    )
    let reassignedSegment = TranscriptSegment(
      id: "segment-1",
      text: "Speaker text",
      speaker: "SPEAKER_00",
      isUser: true,
      personId: "person-1",
      start: 0,
      end: 1
    )
    let original = makeConversation(
      id: "c1",
      revision: "2",
      transcript: [originalSegment],
      transcriptIncluded: true
    )
    let reassigned = makeConversation(
      id: "c1",
      revision: "2",
      transcript: [reassignedSegment],
      transcriptIncluded: true
    )
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(list: []),
      cache: ConversationCacheStub(),
      legacyMigrationEnabled: false
    )
    repository.seed(original)
    var notifications = 0
    let cancellable = repository.objectWillChange.sink { notifications += 1 }

    repository.seed(reassigned)

    XCTAssertGreaterThan(notifications, 0)
    XCTAssertEqual(repository.conversation(id: "c1")?.transcriptSegments.first?.personId, "person-1")
    XCTAssertTrue(repository.conversation(id: "c1")?.transcriptSegments.first?.isUser == true)
    withExtendedLifetime(cancellable) {}
  }

  func testPendingJournalLoadCannotEraseConcurrentlyStagedIntent() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let gate = ConversationTestGate()
    let cache = ConversationCacheStub(entries: [entry(original)], pendingLoadGate: gate)
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(list: [original], statusOnlyAcks: true),
      cache: cache,
      legacyMigrationEnabled: false
    )

    let load = Task { await repository.load(query: ConversationQuery()) }
    await gate.waitUntilBlocked()
    try await repository.updateTitle(id: "c1", title: "Durable rename")
    await gate.release()
    await load.value

    XCTAssertEqual(repository.conversation(id: "c1")?.structured.title, "Durable rename")
    let pending = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertEqual(pending["c1"]?.title, "Durable rename")
  }

  func testJournalSaveFailureRestoresInMemoryIntentAndNeverCallsRemote() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let cache = ConversationCacheStub(
      entries: [entry(original)],
      pendingSaveError: ConversationRemoteStubError.mutationFailed
    )
    let remote = ConversationRemoteStub(list: [original])
    let repository = ConversationRepository(remote: remote, cache: cache, legacyMigrationEnabled: false)
    repository.seed(original)

    do {
      try await repository.updateTitle(id: "c1", title: "Must not linger")
      XCTFail("journal failure should surface")
    } catch {}

    XCTAssertEqual(repository.conversation(id: "c1")?.structured.title, "Original")
    let requestedTitles = await remote.requestedTitles()
    XCTAssertTrue(requestedTitles.isEmpty)
  }

  func testFailedMutationSurvivesRestartAndClearsOnlyAfterCanonicalAck() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let cache = ConversationCacheStub(entries: [entry(original)])
    let failingRemote = ConversationRemoteStub(
      list: [original],
      mutationError: ConversationRemoteStubError.mutationFailed
    )
    let firstRepository = ConversationRepository(
      remote: failingRemote,
      cache: cache,
      legacyMigrationEnabled: false
    )
    firstRepository.seed(original)

    do {
      try await firstRepository.updateTitle(id: "c1", title: "Durable title")
      XCTFail("mutation should fail")
    } catch {}

    XCTAssertEqual(firstRepository.conversation(id: "c1")?.structured.title, "Durable title")
    let pendingAfterFailure = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertEqual(pendingAfterFailure["c1"]?.title, "Durable title")

    let acknowledged = makeConversation(id: "c1", title: "Durable title", revision: "2")
    let recoveringRemote = ConversationRemoteStub(list: [original], titleResult: acknowledged)
    let secondRepository = ConversationRepository(
      remote: recoveringRemote,
      cache: cache,
      legacyMigrationEnabled: false
    )

    await secondRepository.load(query: ConversationQuery())

    XCTAssertEqual(secondRepository.conversation(id: "c1")?.structured.title, "Durable title")
    let pendingAfterRecovery = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertNil(pendingAfterRecovery["c1"])
  }

  func testAccountResetRejectsResponseFromPreviousGeneration() async {
    let server = makeConversation(id: "old-account", revision: "2")
    let gate = ConversationTestGate()
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(list: [server], listGate: gate),
      cache: ConversationCacheStub(),
      legacyMigrationEnabled: false
    )

    let load = Task { await repository.load(query: ConversationQuery()) }
    await gate.waitUntilBlocked()
    repository.resetSession()
    await gate.release()
    await load.value

    XCTAssertTrue(repository.conversations.isEmpty)
    XCTAssertNil(repository.conversation(id: "old-account"))
  }

  func testAccountChangeCannotPublishBlockedCacheReadBeforeResetOrdering() async {
    let accountA = makeConversation(id: "account-a-only", revision: "1")
    let gate = ConversationTestGate()
    var accountId = "account-a"
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(list: []),
      cache: ConversationCacheStub(entries: [entry(accountA)], listLoadGate: gate),
      accountIdProvider: { accountId },
      legacyMigrationEnabled: false
    )

    let load = Task { await repository.load(query: ConversationQuery()) }
    await gate.waitUntilBlocked()
    accountId = "account-b"
    await gate.release()
    await load.value

    XCTAssertNil(repository.conversation(id: "account-a-only"))
    XCTAssertTrue(repository.conversations.isEmpty)
  }

  func testOlderSearchCannotReplaceNewerSearchResults() async {
    let oldResult = makeConversation(id: "old", title: "Old result", revision: "1")
    let newResult = makeConversation(id: "new", title: "New result", revision: "2")
    let oldSearchGate = ConversationTestGate()
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(
        list: [],
        searchResults: ["old": [oldResult], "new": [newResult]],
        searchGates: ["old": oldSearchGate]
      ),
      cache: ConversationCacheStub(),
      legacyMigrationEnabled: false
    )

    let oldSearch = Task { await repository.search("old") }
    await oldSearchGate.waitUntilBlocked()
    await repository.search("new")
    await oldSearchGate.release()
    await oldSearch.value

    XCTAssertEqual(repository.searchResults.map(\.id), ["new"])
    XCTAssertFalse(repository.isSearching)
  }

  func testPersistedOptimisticMutationRespectsActiveFilterAfterRestart() async {
    let starred = makeConversation(id: "c1", revision: "1", starred: true)
    var pending = ConversationPendingMutation()
    pending.setStarred(false)
    let gate = ConversationTestGate()
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(
        list: [starred],
        mutationError: ConversationRemoteStubError.mutationFailed,
        listGate: gate
      ),
      cache: ConversationCacheStub(entries: [entry(starred)], pending: ["c1": pending]),
      legacyMigrationEnabled: false
    )

    let load = Task { await repository.load(query: ConversationQuery(showStarredOnly: true)) }
    await gate.waitUntilBlocked()

    XCTAssertTrue(repository.conversations.isEmpty)

    await gate.release()
    await load.value
    XCTAssertTrue(repository.conversations.isEmpty)
  }

  func testOlderMutationAckCannotOverwriteNewerCanonicalRevision() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let firstAck = makeConversation(id: "c1", title: "First", revision: "2")
    let secondAck = makeConversation(id: "c1", title: "Second", revision: "3")
    let firstGate = ConversationTestGate()
    let cache = ConversationCacheStub(entries: [entry(original)])
    let remote = ConversationRemoteStub(
      list: [original],
      titleResults: ["First": firstAck, "Second": secondAck],
      titleGates: ["First": firstGate]
    )
    let repository = ConversationRepository(
      remote: remote,
      cache: cache,
      legacyMigrationEnabled: false
    )
    repository.seed(original)

    let first = Task { try await repository.updateTitle(id: "c1", title: "First") }
    await firstGate.waitUntilBlocked()
    let requestsWhileFirstBlocked = await remote.requestedTitles()
    XCTAssertEqual(requestsWhileFirstBlocked, ["First"])
    let second = Task { try await repository.updateTitle(id: "c1", title: "Second") }
    await cache.waitUntilPendingTitle("Second", conversationId: "c1")
    let requestsAfterSecondIntent = await remote.requestedTitles()
    XCTAssertEqual(requestsAfterSecondIntent, ["First"])
    await firstGate.release()
    try await first.value
    try await second.value

    XCTAssertEqual(repository.conversation(id: "c1")?.structured.title, "Second")
    let completedRequests = await remote.requestedTitles()
    XCTAssertEqual(completedRequests, ["First", "Second"])
    let pending = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertNil(pending["c1"])
  }

  func testLockedListProjectionPurgesCachedSensitiveDetail() {
    let cached = makeConversation(
      id: "c1",
      revision: "1",
      transcript: [makeSegment(text: "sensitive cached transcript")],
      transcriptIncluded: true
    )
    let locked = makeConversation(id: "c1", revision: "2", isLocked: true)

    let merged = ConversationProjectionMerge.merge(
      incoming: locked,
      incomingCompleteness: [.list],
      cached: ConversationCacheEntry(
        conversation: cached,
        completeness: [.list, .detail, .transcript],
        cacheWrittenAt: Date(timeIntervalSince1970: 1)
      )
    )

    XCTAssertTrue(merged.conversation.isLocked)
    XCTAssertTrue(merged.conversation.transcriptSegments.isEmpty)
    XCTAssertFalse(merged.completeness.contains(.detail))
    XCTAssertFalse(merged.completeness.contains(.transcript))
  }

  func testOlderDetailResponseCannotRegressNewerCachedRevision() async {
    let newer = makeConversation(id: "c1", title: "Newer", revision: "3")
    let older = makeConversation(id: "c1", title: "Older", revision: "2")
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(list: [older], detailById: ["c1": older]),
      cache: ConversationCacheStub(entries: [entry(newer)]),
      legacyMigrationEnabled: false
    )

    await repository.loadDetail(id: "c1")

    XCTAssertEqual(repository.conversation(id: "c1")?.structured.title, "Newer")
    XCTAssertEqual(repository.conversation(id: "c1")?.revision, "3")
  }

  func testOldAccountMutationAckCannotWriteOrPublishAfterReset() async {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let acknowledged = makeConversation(id: "c1", title: "Old account", revision: "2")
    let gate = ConversationTestGate()
    let cache = ConversationCacheStub(entries: [entry(original)])
    let remote = ConversationRemoteStub(
      list: [original],
      titleResults: ["Old account": acknowledged],
      titleGates: ["Old account": gate]
    )
    var accountId = "account-a"
    let repository = ConversationRepository(
      remote: remote,
      cache: cache,
      accountIdProvider: { accountId },
      legacyMigrationEnabled: false
    )
    repository.seed(original)

    let mutation = Task { try? await repository.updateTitle(id: "c1", title: "Old account") }
    await gate.waitUntilBlocked()
    repository.resetSession()
    accountId = "account-b"
    await gate.release()
    await mutation.value

    XCTAssertTrue(repository.conversations.isEmpty)
    XCTAssertNil(repository.conversation(id: "c1"))
    let serverAccounts = await cache.recordedServerUpsertAccounts()
    XCTAssertTrue(serverAccounts.isEmpty)
  }

  func testOldAccountCachedDetailCannotPublishAfterReset() async {
    let cached = makeConversation(id: "c1", title: "Account A", revision: "1")
    let gate = ConversationTestGate()
    let cache = ConversationCacheStub(entries: [entry(cached)], idLoadGate: gate)
    var accountId = "account-a"
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(list: [cached]),
      cache: cache,
      accountIdProvider: { accountId },
      legacyMigrationEnabled: false
    )

    let detail = Task { await repository.loadDetail(id: "c1") }
    await gate.waitUntilBlocked()
    repository.resetSession()
    accountId = "account-b"
    await gate.release()
    await detail.value

    XCTAssertNil(repository.conversation(id: "c1"))
  }

  func testPermanentMutationFailureRollsBackAndStopsRetrying() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let cache = ConversationCacheStub(entries: [entry(original)])
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(
        list: [original],
        detailById: ["c1": original],
        mutationError: APIError.httpError(statusCode: 400, detail: "invalid title")
      ),
      cache: cache,
      legacyMigrationEnabled: false
    )
    repository.seed(original)

    do {
      try await repository.updateTitle(id: "c1", title: "Rejected")
      XCTFail("permanent failure should surface")
    } catch {}

    XCTAssertEqual(repository.conversation(id: "c1")?.structured.title, "Original")
    let pending = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertNil(pending["c1"])
    guard case .failed = repository.metadata(id: "c1")?.syncState else {
      return XCTFail("permanent failure should remain visible on the entity")
    }
  }

  func testRejectedOlderTitleDoesNotEraseNewerQueuedIntent() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let accepted = makeConversation(id: "c1", title: "Second", revision: "3")
    let firstGate = ConversationTestGate()
    let cache = ConversationCacheStub(entries: [entry(original)])
    let remote = ConversationRemoteStub(
      list: [original],
      detailById: ["c1": original],
      titleResults: ["Second": accepted],
      titleGates: ["First": firstGate],
      titleErrors: ["First": APIError.httpError(statusCode: 400, detail: "invalid title")]
    )
    let repository = ConversationRepository(remote: remote, cache: cache, legacyMigrationEnabled: false)
    repository.seed(original)

    let first = Task { try? await repository.updateTitle(id: "c1", title: "First") }
    await firstGate.waitUntilBlocked()
    let second = Task { try await repository.updateTitle(id: "c1", title: "Second") }
    await cache.waitUntilPendingTitle("Second", conversationId: "c1")
    await firstGate.release()
    await first.value
    try await second.value

    XCTAssertEqual(repository.conversation(id: "c1")?.structured.title, "Second")
    let requests = await remote.requestedTitles()
    let pending = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertEqual(requests, ["First", "Second"])
    XCTAssertNil(pending["c1"])
  }

  func testMissingFolderFailureDoesNotDeleteConversation() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let cache = ConversationCacheStub(entries: [entry(original)])
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(
        list: [original],
        detailById: ["c1": original],
        mutationError: APIError.httpError(statusCode: 404, detail: "Folder not found")
      ),
      cache: cache,
      legacyMigrationEnabled: false
    )
    repository.seed(original)

    do {
      try await repository.moveToFolder(id: "c1", folderId: "missing")
      XCTFail("missing folder should surface")
    } catch {}

    XCTAssertEqual(repository.conversation(id: "c1")?.id, "c1")
    XCTAssertNil(repository.conversation(id: "c1")?.folderId)
    let cached = try await cache.load(id: "c1", accountId: "anonymous")
    let pending = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertNotNil(cached)
    XCTAssertNil(pending["c1"])
  }

  func testPermanentFailureWithOfflineDetailRollsBackFromCanonicalCacheAcrossRestart() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let cache = ConversationCacheStub(entries: [entry(original)])
    let failingRemote = ConversationRemoteStub(
      list: [original],
      detailError: ConversationRemoteStubError.mutationFailed,
      mutationError: APIError.httpError(statusCode: 400, detail: "invalid title")
    )
    let firstRepository = ConversationRepository(remote: failingRemote, cache: cache, legacyMigrationEnabled: false)
    firstRepository.seed(original)

    do {
      try await firstRepository.updateTitle(id: "c1", title: "Rejected")
      XCTFail("permanent failure should surface")
    } catch {}

    XCTAssertEqual(firstRepository.conversation(id: "c1")?.structured.title, "Original")
    let pending = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertNil(pending["c1"])

    let restartGate = ConversationTestGate()
    let restarted = ConversationRepository(
      remote: ConversationRemoteStub(list: [original], listGate: restartGate),
      cache: cache,
      legacyMigrationEnabled: false
    )
    let load = Task { await restarted.load(query: ConversationQuery()) }
    await restartGate.waitUntilBlocked()
    XCTAssertEqual(restarted.conversation(id: "c1")?.structured.title, "Original")
    await restartGate.release()
    await load.value
  }

  func testLightweightMutationAckAdvancesRevisionAndClearsOnlyAcknowledgedField() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let titleAck = makeConversation(id: "c1", title: "Renamed", revision: "2")
    let cache = ConversationCacheStub(entries: [entry(original)])
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(
        list: [original],
        titleResult: titleAck,
        lightweightAcks: true
      ),
      cache: cache,
      legacyMigrationEnabled: false
    )
    repository.seed(original)

    try await repository.updateTitle(id: "c1", title: "Renamed")

    XCTAssertEqual(repository.conversation(id: "c1")?.structured.title, "Renamed")
    XCTAssertEqual(repository.conversation(id: "c1")?.revision, "2")
    let pending = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertNil(pending["c1"])
    XCTAssertEqual(repository.metadata(id: "c1")?.syncState, .synced)
    let cached = try await cache.load(id: "c1", accountId: "anonymous")
    XCTAssertEqual(cached?.listFetchedAt, Date(timeIntervalSince1970: 1))
  }

  func testConcurrentMutationFailureReturnsToItsCallerWithoutLeakingOverlayIntoCanonicalCache() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1", starred: false)
    let starredAck = makeConversation(id: "c1", title: "Original", revision: "2", starred: true)
    let starredGate = ConversationTestGate()
    let cache = ConversationCacheStub(entries: [entry(original)])
    let remote = ConversationRemoteStub(
      list: [original],
      detailError: ConversationRemoteStubError.mutationFailed,
      starredResult: starredAck,
      starredGate: starredGate,
      titleErrors: ["Rejected": APIError.httpError(statusCode: 400, detail: "invalid title")],
      lightweightAcks: true
    )
    let repository = ConversationRepository(remote: remote, cache: cache, legacyMigrationEnabled: false)
    repository.seed(original)

    let starTask = Task { try await repository.updateStarred(id: "c1", starred: true) }
    await starredGate.waitUntilBlocked()
    let titleTask = Task { try await repository.updateTitle(id: "c1", title: "Rejected") }
    await cache.waitUntilPendingTitle("Rejected", conversationId: "c1")
    await starredGate.release()

    try await starTask.value
    do {
      try await titleTask.value
      XCTFail("the rejected title caller must receive its own failure")
    } catch {}

    let cachedCanonical = try await cache.load(id: "c1", accountId: "anonymous")
    let canonical = try XCTUnwrap(cachedCanonical)
    XCTAssertEqual(canonical.conversation.structured.title, "Original")
    XCTAssertTrue(canonical.conversation.starred)

    let restartGate = ConversationTestGate()
    let restarted = ConversationRepository(
      remote: ConversationRemoteStub(list: [starredAck], listGate: restartGate),
      cache: cache,
      legacyMigrationEnabled: false
    )
    let load = Task { await restarted.load(query: ConversationQuery()) }
    await restartGate.waitUntilBlocked()
    XCTAssertEqual(restarted.conversation(id: "c1")?.structured.title, "Original")
    XCTAssertTrue(restarted.conversation(id: "c1")?.starred == true)
    await restartGate.release()
    await load.value
  }

  func testConcurrentDuplicateMutationCallersSharePermanentFailure() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let gate = ConversationTestGate()
    let remote = ConversationRemoteStub(
      list: [original],
      detailById: ["c1": original],
      titleGates: ["Rejected": gate],
      titleErrors: ["Rejected": APIError.httpError(statusCode: 400, detail: "invalid title")]
    )
    let waiterRegistered = expectation(description: "duplicate caller joined the in-flight mutation")
    let repository = ConversationRepository(
      remote: remote,
      cache: ConversationCacheStub(entries: [entry(original)]),
      onMutationWaiterRegistered: { id, value in
        if id == "c1", value == .title("Rejected") { waiterRegistered.fulfill() }
      },
      legacyMigrationEnabled: false
    )
    repository.seed(original)

    let first = Task { try await repository.updateTitle(id: "c1", title: "Rejected") }
    await gate.waitUntilBlocked()
    let second = Task { try await repository.updateTitle(id: "c1", title: "Rejected") }
    await fulfillment(of: [waiterRegistered], timeout: 1)
    await gate.release()

    for task in [first, second] {
      do {
        try await task.value
        XCTFail("every caller of the rejected intent must receive the permanent failure")
      } catch {}
    }
    let requestedTitles = await remote.requestedTitles()
    XCTAssertEqual(requestedTitles, ["Rejected"])
    XCTAssertEqual(repository.conversation(id: "c1")?.structured.title, "Original")
  }

  func testStarredFilterMembershipReturnsAfterPermanentRollback() async throws {
    let original = makeConversation(id: "c1", revision: "1", starred: true)
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(
        list: [original],
        detailById: ["c1": original],
        starredError: APIError.httpError(statusCode: 400, detail: "rejected")
      ),
      cache: ConversationCacheStub(entries: [entry(original)]),
      legacyMigrationEnabled: false
    )
    await repository.load(query: ConversationQuery(showStarredOnly: true))

    do {
      try await repository.updateStarred(id: "c1", starred: false)
      XCTFail("permanent failure should surface")
    } catch {}

    XCTAssertEqual(repository.conversationIds, ["c1"])
    XCTAssertTrue(repository.conversation(id: "c1")?.starred == true)
  }

  func testFolderFilterMembershipReturnsAfterPermanentRollback() async throws {
    let original = makeConversation(id: "c1", revision: "1", folderId: "inbox")
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(
        list: [original],
        detailById: ["c1": original],
        mutationError: APIError.httpError(statusCode: 404, detail: "folder missing")
      ),
      cache: ConversationCacheStub(entries: [entry(original)]),
      legacyMigrationEnabled: false
    )
    await repository.load(query: ConversationQuery(folderId: "inbox"))

    do {
      try await repository.moveToFolder(id: "c1", folderId: "missing")
      XCTFail("permanent failure should surface")
    } catch {}

    XCTAssertEqual(repository.conversationIds, ["c1"])
    XCTAssertEqual(repository.conversation(id: "c1")?.folderId, "inbox")
  }

  func testMutatingSearchOnlyEntityCannotInjectItIntoActiveListSnapshot() async throws {
    let listed = makeConversation(id: "listed", revision: "1")
    let searched = makeConversation(id: "searched", title: "Search result", revision: "2")
    let renamed = makeConversation(id: "searched", title: "Renamed", revision: "3")
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(
        list: [listed],
        searchResults: ["needle": [searched]],
        titleResults: ["Renamed": renamed],
        lightweightAcks: true
      ),
      cache: ConversationCacheStub(entries: [entry(listed)]),
      legacyMigrationEnabled: false
    )
    await repository.load(query: ConversationQuery(limit: 1))
    await repository.search("needle")

    try await repository.updateTitle(id: "searched", title: "Renamed")

    XCTAssertEqual(repository.conversationIds, ["listed"])
    XCTAssertEqual(repository.conversation(id: "searched")?.structured.title, "Renamed")
  }

  func testSuccessfulRefreshClearsStaleRepositoryError() async {
    let original = makeConversation(id: "c1", revision: "1")
    let remote = ConversationRemoteStub(
      list: [original],
      listError: ConversationRemoteStubError.mutationFailed
    )
    let repository = ConversationRepository(
      remote: remote,
      cache: ConversationCacheStub(),
      legacyMigrationEnabled: false
    )

    await repository.load(query: ConversationQuery())
    XCTAssertNotNil(repository.error)

    await remote.setListError(nil)
    await repository.refresh()

    XCTAssertNil(repository.error)
    XCTAssertEqual(repository.conversationIds, ["c1"])
  }

  func testStatusOnlyAckKeepsOverlayUntilListConfirmsRequestedValue() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let cache = ConversationCacheStub(entries: [entry(original)])
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(list: [original], statusOnlyAcks: true),
      cache: cache,
      legacyMigrationEnabled: false
    )
    repository.seed(original)

    try await repository.updateTitle(id: "c1", title: "Pending rename")
    await repository.load(query: ConversationQuery())

    XCTAssertEqual(repository.conversation(id: "c1")?.structured.title, "Pending rename")
    let pending = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertEqual(pending["c1"]?.title, "Pending rename")
    XCTAssertEqual(repository.metadata(id: "c1")?.syncState, .pending)
  }

  func testStatusOnlyAckClearsAfterVersionedListConfirmsRequestedValue() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let confirmed = makeConversation(id: "c1", title: "Pending rename", revision: "2")
    let cache = ConversationCacheStub(entries: [entry(original)])
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(list: [confirmed], statusOnlyAcks: true),
      cache: cache,
      legacyMigrationEnabled: false
    )
    repository.seed(original)

    try await repository.updateTitle(id: "c1", title: "Pending rename")
    await repository.load(query: ConversationQuery())

    XCTAssertEqual(repository.conversation(id: "c1")?.structured.title, "Pending rename")
    let pending = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertNil(pending["c1"])
    XCTAssertEqual(repository.metadata(id: "c1")?.syncState, .synced)
  }

  func testMatchingUnversionedListCannotClearOverlayOnVersionedCache() async throws {
    let original = makeConversation(id: "c1", title: "Original", revision: "1")
    let confirmedWithoutVersion = withoutServerVersion(
      makeConversation(id: "c1", title: "Pending rename", revision: "2")
    )
    let cache = ConversationCacheStub(entries: [entry(original)])
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(list: [confirmedWithoutVersion], statusOnlyAcks: true),
      cache: cache,
      legacyMigrationEnabled: false
    )
    repository.seed(original)

    try await repository.updateTitle(id: "c1", title: "Pending rename")
    await repository.load(query: ConversationQuery())

    XCTAssertEqual(repository.conversation(id: "c1")?.structured.title, "Pending rename")
    let pending = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertEqual(pending["c1"]?.title, "Pending rename")
  }

  func testUnversionedListCannotOverwriteVersionedCache() {
    let versioned = makeConversation(id: "c1", title: "Versioned", revision: "2")
    var unversioned = makeConversation(id: "c1", title: "Old instance", revision: "1")
    unversioned = ServerConversation(
      id: unversioned.id,
      createdAt: unversioned.createdAt,
      startedAt: unversioned.startedAt,
      finishedAt: unversioned.finishedAt,
      structured: unversioned.structured,
      transcriptSegments: unversioned.transcriptSegments,
      transcriptSegmentsIncluded: unversioned.transcriptSegmentsIncluded,
      geolocation: unversioned.geolocation,
      photos: unversioned.photos,
      appsResults: unversioned.appsResults,
      source: unversioned.source,
      language: unversioned.language,
      status: unversioned.status,
      discarded: unversioned.discarded,
      deleted: unversioned.deleted,
      isLocked: unversioned.isLocked,
      starred: unversioned.starred,
      folderId: unversioned.folderId,
      inputDeviceName: unversioned.inputDeviceName,
      updatedAt: nil,
      revision: nil
    )

    let merged = ConversationProjectionMerge.merge(
      incoming: unversioned,
      incomingCompleteness: [.list],
      cached: entry(versioned)
    )

    XCTAssertEqual(merged.conversation.structured.title, "Versioned")
    XCTAssertEqual(merged.conversation.revision, "2")
  }

  func testDelayedOlderLockCannotPurgeNewerUnlockedDetail() {
    let unlocked = makeConversation(
      id: "c1",
      revision: "3",
      transcript: [makeSegment(text: "newer detail")],
      transcriptIncluded: true
    )
    let staleLocked = makeConversation(id: "c1", revision: "2", isLocked: true)

    let merged = ConversationProjectionMerge.merge(
      incoming: staleLocked,
      incomingCompleteness: [.list],
      cached: entry(unlocked)
    )

    XCTAssertFalse(merged.conversation.isLocked)
    XCTAssertEqual(merged.conversation.transcriptSegments.map(\.text), ["newer detail"])
    XCTAssertTrue(merged.completeness.contains(.detail))
  }

  func testDelayedOlderTombstoneCannotOverrideNewerRestore() {
    let restored = makeConversation(id: "c1", revision: "3")
    let staleDeleted = makeConversation(id: "c1", revision: "2", deleted: true)

    let merged = ConversationProjectionMerge.merge(
      incoming: staleDeleted,
      incomingCompleteness: [.list],
      cached: entry(restored)
    )

    XCTAssertFalse(merged.conversation.deleted)
    XCTAssertEqual(merged.conversation.revision, "3")
  }

  func testUnversionedLockStillPurgesCachedSensitiveDetailFailClosed() {
    let cached = makeConversation(
      id: "c1",
      revision: "3",
      transcript: [makeSegment(text: "sensitive")],
      transcriptIncluded: true
    )
    let unversionedLock = withoutServerVersion(makeConversation(id: "c1", revision: "4", isLocked: true))

    let merged = ConversationProjectionMerge.merge(
      incoming: unversionedLock,
      incomingCompleteness: [.list],
      cached: entry(cached)
    )

    XCTAssertTrue(merged.conversation.isLocked)
    XCTAssertTrue(merged.conversation.transcriptSegments.isEmpty)
    XCTAssertFalse(merged.completeness.contains(.detail))
  }

  func testOlderVersionedListCannotClearNewerPendingIntent() async throws {
    let current = makeConversation(id: "c1", title: "Current", revision: "3")
    let staleMatching = makeConversation(id: "c1", title: "Desired", revision: "2")
    let cache = ConversationCacheStub(entries: [entry(current)])
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(list: [staleMatching], statusOnlyAcks: true),
      cache: cache,
      legacyMigrationEnabled: false
    )
    repository.seed(current)

    try await repository.updateTitle(id: "c1", title: "Desired")
    await repository.load(query: ConversationQuery())

    XCTAssertEqual(repository.conversation(id: "c1")?.structured.title, "Desired")
    let pending = try await cache.loadPendingMutations(accountId: "anonymous")
    XCTAssertEqual(pending["c1"]?.title, "Desired")
  }

  func testStaleDeleteFailureCannotMarkNewSessionEntityFailed() async {
    let original = makeConversation(id: "c1", revision: "1")
    let gate = ConversationTestGate()
    var accountId = "account-a"
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(
        list: [original],
        mutationError: APIError.httpError(statusCode: 500, detail: "delete failed"),
        deleteGate: gate
      ),
      cache: ConversationCacheStub(entries: [entry(original)]),
      accountIdProvider: { accountId },
      legacyMigrationEnabled: false
    )
    repository.seed(original)

    let deletion = Task { try? await repository.delete(id: "c1") }
    await gate.waitUntilBlocked()
    repository.resetSession()
    accountId = "account-b"
    await gate.release()
    await deletion.value

    XCTAssertNil(repository.conversation(id: "c1"))
    XCTAssertNil(repository.metadata(id: "c1"))
    XCTAssertNil(repository.error)
  }

  func testServerListMetadataReportsMixedProjectionFreshness() async {
    let detail = makeConversation(
      id: "c1",
      title: "Cached detail",
      revision: "2",
      transcript: [makeSegment(text: "rich")],
      transcriptIncluded: true
    )
    let list = makeConversation(id: "c1", title: "Fresh list", revision: "3")
    let cached = ConversationCacheEntry(
      conversation: detail,
      completeness: [.list, .detail, .transcript],
      cacheWrittenAt: Date(timeIntervalSince1970: 2)
    )
    let repository = ConversationRepository(
      remote: ConversationRemoteStub(list: [list]),
      cache: ConversationCacheStub(entries: [cached]),
      now: { Date(timeIntervalSince1970: 3) },
      legacyMigrationEnabled: false
    )

    await repository.load(query: ConversationQuery())

    let metadata = repository.metadata(id: "c1")
    XCTAssertEqual(metadata?.source, .mixed)
    XCTAssertEqual(metadata?.listFetchedAt, Date(timeIntervalSince1970: 3))
    XCTAssertEqual(metadata?.detailFetchedAt, Date(timeIntervalSince1970: 2))
    XCTAssertEqual(metadata?.transcriptFetchedAt, Date(timeIntervalSince1970: 2))
  }

  func testConversationCacheCodableRoundTripPreservesProjectionMetadata() throws {
    let original = makeConversation(
      id: "c1",
      revision: "2",
      transcript: [makeSegment(text: "cached transcript")],
      transcriptIncluded: true,
      deleted: true,
      inputDeviceName: "MacBook Microphone"
    )
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601

    let decoded = try decoder.decode(ServerConversation.self, from: encoder.encode(original))

    XCTAssertEqual(decoded.revision, original.revision)
    XCTAssertEqual(decoded.updatedAt, original.updatedAt)
    XCTAssertEqual(decoded.inputDeviceName, "MacBook Microphone")
    XCTAssertTrue(decoded.deleted)
    XCTAssertTrue(decoded.transcriptSegmentsIncluded)
    XCTAssertEqual(decoded.transcriptSegments.map(\.text), ["cached transcript"])
  }

  private func entry(_ conversation: ServerConversation) -> ConversationCacheEntry {
    ConversationCacheEntry(
      conversation: conversation,
      completeness: conversation.transcriptSegmentsIncluded ? [.list, .detail, .transcript] : [.list],
      cacheWrittenAt: Date(timeIntervalSince1970: 1)
    )
  }

  private func makeConversation(
    id: String,
    title: String = "Title",
    overview: String = "Overview",
    revision: String,
    starred: Bool = false,
    folderId: String? = nil,
    transcript: [TranscriptSegment] = [],
    transcriptIncluded: Bool = false,
    deleted: Bool = false,
    inputDeviceName: String? = nil,
    isLocked: Bool = false
  ) -> ServerConversation {
    let createdAt = Date(timeIntervalSince1970: 1_000)
    return ServerConversation(
      id: id,
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
      deleted: deleted,
      isLocked: isLocked,
      starred: starred,
      folderId: folderId,
      inputDeviceName: inputDeviceName,
      updatedAt: Date(timeIntervalSince1970: Double(revision) ?? 1),
      revision: revision
    )
  }

  private func withoutServerVersion(_ conversation: ServerConversation) -> ServerConversation {
    ServerConversation(
      id: conversation.id,
      createdAt: conversation.createdAt,
      startedAt: conversation.startedAt,
      finishedAt: conversation.finishedAt,
      structured: conversation.structured,
      transcriptSegments: conversation.transcriptSegments,
      transcriptSegmentsIncluded: conversation.transcriptSegmentsIncluded,
      geolocation: conversation.geolocation,
      photos: conversation.photos,
      appsResults: conversation.appsResults,
      source: conversation.source,
      language: conversation.language,
      status: conversation.status,
      discarded: conversation.discarded,
      deleted: conversation.deleted,
      isLocked: conversation.isLocked,
      starred: conversation.starred,
      folderId: conversation.folderId,
      inputDeviceName: conversation.inputDeviceName,
      deferred: conversation.deferred,
      updatedAt: nil,
      revision: nil
    )
  }

  private func makeSegment(text: String) -> TranscriptSegment {
    TranscriptSegment(
      id: UUID().uuidString,
      text: text,
      speaker: "SPEAKER_00",
      isUser: true,
      personId: nil,
      start: 0,
      end: 1
    )
  }

}
