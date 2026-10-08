import Foundation
@preconcurrency import ObjectiveC

/// Synchronous session fence for conversation cache transaction admission.
///
/// A reset advances the generation immediately, so no later write from the
/// previous account can enter SQLite. A write already admitted keeps using the
/// per-user database pool it captured before reset; the lock is never held over
/// database work, so sign-out cannot stall the main actor behind a large write.
final class ConversationCacheWriteScope: @unchecked Sendable {
  private let lock = NSLock()
  private var generation = 0

  func capture() -> Int {
    lock.lock()
    defer { lock.unlock() }
    return generation
  }

  func advance() {
    lock.lock()
    generation += 1
    lock.unlock()
  }

  func ensureCurrent(_ expected: Int) throws {
    guard isCurrent(expected) else { throw CancellationError() }
  }

  func isCurrent(_ expected: Int) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    return generation == expected
  }

  func withCurrent<T>(_ expected: Int, _ operation: () throws -> T) throws -> T {
    try ensureCurrent(expected)
    return try operation()
  }
}

struct ConversationListQuery: Equatable {
  let starredOnly: Bool
  let date: Date?
  let folderId: String?

  var hasFilters: Bool { starredOnly || date != nil || folderId != nil }

  var dateRange: (start: Date?, end: Date?) {
    guard let date else { return (nil, nil) }
    let calendar = Calendar.current
    let start = calendar.startOfDay(for: date)
    return (start, calendar.date(byAdding: .day, value: 1, to: start))
  }
}

enum ConversationSnapshotSource: Equatable {
  case cache
  case server
  case optimistic
  case rollback
}

struct ConversationRepositorySnapshot: Equatable {
  let conversations: [ServerConversation]
  let count: Int?
  let isLoading: Bool
  let error: String?
  let source: ConversationSnapshotSource
}

protocol ConversationRemoteDataSource: Sendable {
  func list(query: ConversationListQuery, offset: Int, limit: Int) async throws -> [ServerConversation]
  func count(query: ConversationListQuery) async throws -> Int
  func detail(id: String) async throws -> ServerConversation
  func search(text: String) async throws -> [ServerConversation]
  func setStarred(id: String, starred: Bool) async throws -> ServerConversation
  func updateTitle(id: String, title: String) async throws -> ServerConversation
  func moveToFolder(id: String, folderId: String?) async throws -> ServerConversation
  func delete(id: String, authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?) async throws
}

protocol ConversationLocalDataSource: Sendable {
  func list(query: ConversationListQuery) async throws -> [ServerConversation]
  func count(query: ConversationListQuery) async throws -> Int
  func detail(id: String) async throws -> ServerConversation?
  func store(
    _ conversation: ServerConversation,
    scope: ConversationCacheWriteScope,
    generation: Int
  ) async throws
  func storeMany(
    _ conversations: [ServerConversation],
    scope: ConversationCacheWriteScope,
    generation: Int
  ) async throws
  func deletionIDs() async throws -> Set<String>
  func pendingDeletionIDs() async throws -> Set<String>
  func prepareDeletion(id: String, scope: ConversationCacheWriteScope, generation: Int) async throws
  func confirmDeletion(id: String, scope: ConversationCacheWriteScope, generation: Int) async throws
  func rollbackDeletion(id: String, scope: ConversationCacheWriteScope, generation: Int) async throws
}

extension ConversationLocalDataSource {
  func storeMany(
    _ conversations: [ServerConversation], scope: ConversationCacheWriteScope, generation: Int
  ) async throws {
    for conversation in conversations { try? await store(conversation, scope: scope, generation: generation) }
  }
}

struct LiveConversationRemoteDataSource: ConversationRemoteDataSource {
  func list(query: ConversationListQuery, offset: Int, limit: Int) async throws -> [ServerConversation] {
    let range = query.dateRange
    return try await APIClient.shared.getConversations(
      limit: limit,
      offset: offset,
      statuses: [.completed, .processing],
      includeDiscarded: false,
      startDate: range.start,
      endDate: range.end,
      folderId: query.folderId,
      starred: query.starredOnly ? true : nil
    )
  }

  func count(query: ConversationListQuery) async throws -> Int {
    let range = query.dateRange
    return try await APIClient.shared.getConversationsCount(
      includeDiscarded: false,
      statuses: [.completed, .processing],
      startDate: range.start,
      endDate: range.end,
      folderId: query.folderId,
      starred: query.starredOnly ? true : nil
    )
  }

  func detail(id: String) async throws -> ServerConversation {
    try await APIClient.shared.getConversation(id: id)
  }

  func search(text: String) async throws -> [ServerConversation] {
    try await APIClient.shared.searchConversations(
      query: text,
      page: 1,
      perPage: 50,
      includeDiscarded: false
    ).items
  }

  func setStarred(id: String, starred: Bool) async throws -> ServerConversation {
    try await APIClient.shared.setConversationStarred(id: id, starred: starred)
  }

  func updateTitle(id: String, title: String) async throws -> ServerConversation {
    try await APIClient.shared.updateConversationTitle(id: id, title: title)
  }

  func moveToFolder(id: String, folderId: String?) async throws -> ServerConversation {
    try await APIClient.shared.moveConversationToFolder(conversationId: id, folderId: folderId)
  }

  func delete(id: String, authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?) async throws {
    guard let authorizationSnapshot else { throw AuthError.userChangedDuringRequest }
    try await APIClient.shared.deleteConversation(id: id, authorizationSnapshot: authorizationSnapshot)
  }
}

struct LiveConversationLocalDataSource: ConversationLocalDataSource {
  func deletionIDs() async throws -> Set<String> {
    try await TranscriptionStorage.shared.getConversationDeletionIDs()
  }

  func pendingDeletionIDs() async throws -> Set<String> {
    try await TranscriptionStorage.shared.getPendingConversationDeletionIDs()
  }

  func prepareDeletion(id: String, scope: ConversationCacheWriteScope, generation: Int) async throws {
    try await TranscriptionStorage.shared.prepareConversationDeletion(
      backendId: id, cacheScope: scope, cacheGeneration: generation)
  }

  func confirmDeletion(id: String, scope: ConversationCacheWriteScope, generation: Int) async throws {
    try await TranscriptionStorage.shared.confirmConversationDeletion(
      backendId: id, cacheScope: scope, cacheGeneration: generation)
  }

  func rollbackDeletion(id: String, scope: ConversationCacheWriteScope, generation: Int) async throws {
    try await TranscriptionStorage.shared.rollbackConversationDeletion(
      backendId: id, cacheScope: scope, cacheGeneration: generation)
  }

  func list(query: ConversationListQuery) async throws -> [ServerConversation] {
    guard query.date == nil else { return [] }
    return try await TranscriptionStorage.shared.getLocalConversations(
      limit: 50,
      starredOnly: query.starredOnly,
      folderId: query.folderId
    )
  }

  func count(query: ConversationListQuery) async throws -> Int {
    guard query.date == nil else { return 0 }
    return try await TranscriptionStorage.shared.getLocalConversationsCount(
      starredOnly: query.starredOnly,
      folderId: query.folderId
    )
  }

  func detail(id: String) async throws -> ServerConversation? {
    try await TranscriptionStorage.shared.getCachedConversation(id: id)
  }

  func store(
    _ conversation: ServerConversation,
    scope: ConversationCacheWriteScope,
    generation: Int
  ) async throws {
    _ = try await TranscriptionStorage.shared.syncServerConversation(
      conversation,
      cacheScope: scope,
      cacheGeneration: generation
    )
  }

  func storeMany(
    _ conversations: [ServerConversation], scope: ConversationCacheWriteScope, generation: Int
  ) async throws {
    var committed: [String] = []
    for conversation in conversations {
      do {
        _ = try await TranscriptionStorage.shared.syncServerConversation(
          conversation, cacheScope: scope, cacheGeneration: generation, notifySiri: false)
        committed.append(conversation.id)
      } catch { log("Conversation cache sync deferred: \(error.localizedDescription)") }
    }
    if scope.isCurrent(generation) { SiriIndexHooks.conversationsChanged(committed) }
  }

}

/// Sole owner of desktop Conversations cache/network reconciliation.
/// AppState is a presentation adapter; views do not choose cache versus API.
@MainActor
final class ConversationRepository {
  private struct MutationWaiter {
    let token: UUID
    let continuation: CheckedContinuation<Void, Never>
  }

  private enum MutationOperation {
    case starred(requested: Bool, mutationId: UUID)
    case title(requested: String, mutationId: UUID)
    case folder(requested: String?, mutationId: UUID)

    func stage(in mutation: inout ConversationPendingMutation) {
      switch self {
      case .starred(let requested, let mutationId): mutation.setStarred(requested, mutationId: mutationId)
      case .title(let requested, let mutationId): mutation.setTitle(requested, mutationId: mutationId)
      case .folder(let requested, let mutationId): mutation.setFolderId(requested, mutationId: mutationId)
      }
    }

    func clearIfCurrent(in mutation: inout ConversationPendingMutation) -> Bool {
      switch self {
      case .starred(_, let mutationId): return mutation.clearStarred(mutationId: mutationId)
      case .title(_, let mutationId): return mutation.clearTitle(mutationId: mutationId)
      case .folder(_, let mutationId): return mutation.clearFolderId(mutationId: mutationId)
      }
    }

    func rollback(_ conversation: ServerConversation, to baseline: ServerConversation) -> ServerConversation {
      var rollback = ConversationPendingMutation()
      switch self {
      case .starred:
        rollback.setStarred(baseline.starred)
      case .title:
        rollback.setTitle(baseline.structured.title)
      case .folder:
        rollback.setFolderId(baseline.folderId)
      }
      return ConversationReconciliationPolicy.apply(mutation: rollback, to: conversation)
    }
  }

  private let remote: ConversationRemoteDataSource
  private let local: ConversationLocalDataSource
  private let cacheWriteScope = ConversationCacheWriteScope()
  private var requestGeneration = 0
  private var searchGeneration = 0
  private var pendingMutations: [String: ConversationPendingMutation] = [:]
  private var mutationBaselines: [String: ServerConversation] = [:]
  private var activeMutationTokens: [String: UUID] = [:]
  private var mutationWaiters: [String: [MutationWaiter]] = [:]
  private var deletionTokens: [String: UUID] = [:]
  private var deletedIDs = Set<String>()
  private var deletionStateRevision = 0
  private var deletionRecoveryTask: Task<Void, Never>?
  private var deletionRecoveryCursor: String?
  private var currentQuery: ConversationListQuery?
  private var nextPageOffset = 0
  private var serverPagingCount: Int?
  private var excludedServerIDs = Set<String>()
  private var isLoadingMore = false

  private(set) var conversations: [ServerConversation] = []
  private(set) var count: Int?
  private(set) var hasMore = false
  private(set) var isLoading = false
  private(set) var error: String?
  var onSnapshot: ((ConversationRepositorySnapshot) -> Void)?
  private nonisolated(unsafe) var ownerChangeObserver: NSObjectProtocol?

  init(remote: ConversationRemoteDataSource, local: ConversationLocalDataSource) {
    self.remote = remote
    self.local = local
    // Owner fencing: an in-place account switch posts only
    // .runtimeOwnerDidChange (never .userDidSignOut), so without this reset the
    // previous owner's conversations keep rendering for the next account and
    // ConversationsPage.onAppear skips its reload because the array is
    // non-empty. Mirrors TasksStore.resetSessionState's subscription.
    ownerChangeObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange, object: nil, queue: nil
    ) { [weak self] _ in
      MainActor.assumeIsolated {
        self?.reset()
      }
    }
  }

  deinit {
    deletionRecoveryTask?.cancel()
    if let ownerChangeObserver {
      NotificationCenter.default.removeObserver(ownerChangeObserver)
    }
  }

  convenience init() {
    self.init(remote: LiveConversationRemoteDataSource(), local: LiveConversationLocalDataSource())
  }

  private static let pageSize = 50

  /// `pageSize` is no longer part of the decision: `GET /v1/conversations` post-filters each page
  /// after Firestore has applied the limit, so a request for 50 answering with 47 is a full page and
  /// not the last one. Only an empty page — or an authoritative count already reached — ends the
  /// list. See `ServerPaging`.
  private static func hasMorePages(loaded: Int, totalCount: Int?, received: Int) -> Bool {
    ServerPaging.hasMore(received: received, loaded: loaded, total: totalCount)
  }

  func load(query: ConversationListQuery, includeCache: Bool = true) async {
    let session = cacheWriteScope.capture()
    requestGeneration += 1
    let generation = requestGeneration
    let queryChanged = currentQuery != query
    currentQuery = query
    isLoading = true
    error = nil
    // A cached count is useful for display but must never suppress a full
    // server page when the authoritative count request is unavailable.
    serverPagingCount = nil
    excludedServerIDs = []
    if queryChanged {
      conversations = []
      count = nil
      nextPageOffset = 0
      hasMore = false
      emit(.cache)
    }

    do {
      try await reloadDeletionState(session: session)
      guard generation == requestGeneration else { return }
      scheduleDeletionRecovery(session: session)
    } catch {
      guard generation == requestGeneration else { return }
      isLoading = false
      self.error = UserFacingErrorPresentation.message(for: error, while: .conversations)
      emit(.server)
      return
    }

    if includeCache && query.date == nil {
      do {
        let cached = try await local.list(query: query)
        guard generation == requestGeneration else { return }
        if !cached.isEmpty {
          let cachedCount = try? await local.count(query: query)
          try await reloadDeletionState(session: session)
          guard generation == requestGeneration else { return }
          // Overlay in-flight optimistic mutations before publishing, mirroring
          // the server merge path (mergeList → apply). Without this, a load()
          // that races a pending star/title/folder edit (e.g. the user toggles a
          // filter mid-mutation) paints the bare cached rows and visually reverts
          // the edit until the remote call lands.
          let visible = visibleConversations(cached)
          conversations = visible.map {
            ConversationReconciliationPolicy.apply(mutation: pendingMutations[$0.id], to: $0)
          }
          count = cachedCount.map { max(0, $0 - (cached.count - visible.count)) }
          emit(.cache)
        }
      } catch {
        // Cache failure is recoverable: the server fetch below remains authoritative.
      }
    }

    do {
      async let listTask = remote.list(query: query, offset: 0, limit: Self.pageSize)
      async let countTask = remote.count(query: query)
      let server = try await listTask
      let serverCount = try? await countTask
      try await reloadDeletionState(session: session)
      guard generation == requestGeneration else { return }

      let visible = visibleConversations(server)

      let result = ConversationReconciliationPolicy.mergeList(
        server: visible,
        current: conversations,
        pendingMutations: pendingMutations,
        pendingMutationTTL: .greatestFiniteMagnitude
      )
      for conversation in visible where result.pendingMutations[conversation.id] != nil {
        updateMutationBaseline(id: conversation.id, canonical: conversation)
      }
      pendingMutations = result.pendingMutations
      mutationBaselines = mutationBaselines.filter { pendingMutations[$0.key] != nil }
      conversations = result.conversations
      if let serverCount {
        serverPagingCount = serverCount
        excludedServerIDs.formUnion(server.filter { isDeleted($0.id) || $0.deleted }.map(\.id))
        count = max(0, serverCount - excludedServerIDs.count)
      }
      nextPageOffset = server.count
      hasMore = Self.hasMorePages(
        loaded: nextPageOffset,
        totalCount: serverPagingCount,
        received: server.count
      )
      isLoading = false
      emit(.server)
      await storeInBackground(visible, session: session)
    } catch {
      guard generation == requestGeneration else { return }
      isLoading = false
      if conversations.isEmpty {
        self.error = UserFacingErrorPresentation.message(for: error, while: .conversations)
      }
      emit(conversations.isEmpty ? .server : .cache)
    }
  }

  func refresh(query: ConversationListQuery) async {
    await load(query: query, includeCache: false)
  }

  /// Fetch the next server page without discarding conversations already visible.
  /// The backend owns each returned row; the existing page order remains stable.
  func loadMore() async {
    guard let query = currentQuery, hasMore, !isLoading, !isLoadingMore else { return }

    let session = cacheWriteScope.capture()
    requestGeneration += 1
    let generation = requestGeneration
    let offset = nextPageOffset
    isLoadingMore = true
    defer { isLoadingMore = false }

    do {
      let server = try await remote.list(query: query, offset: offset, limit: Self.pageSize)
      try await reloadDeletionState(session: session)
      guard generation == requestGeneration, currentQuery == query else { return }

      let visible = visibleConversations(server)

      let result = ConversationReconciliationPolicy.mergeList(
        server: visible,
        current: [],
        pendingMutations: pendingMutations,
        pendingMutationTTL: .greatestFiniteMagnitude
      )
      for conversation in visible where result.pendingMutations[conversation.id] != nil {
        updateMutationBaseline(id: conversation.id, canonical: conversation)
      }
      pendingMutations = result.pendingMutations
      mutationBaselines = mutationBaselines.filter { pendingMutations[$0.key] != nil }
      mergeNextPage(result.conversations)
      excludedServerIDs.formUnion(server.filter { isDeleted($0.id) || $0.deleted }.map(\.id))
      if let serverPagingCount { count = max(0, serverPagingCount - excludedServerIDs.count) }
      nextPageOffset = offset + server.count
      hasMore = Self.hasMorePages(
        loaded: nextPageOffset,
        totalCount: serverPagingCount,
        received: server.count
      )
      emit(.server)
      await storeInBackground(visible, session: session)
    } catch {
      guard generation == requestGeneration else { return }
      emit(.server)
    }
  }

  func search(text: String) async throws -> [ServerConversation] {
    let session = cacheWriteScope.capture()
    searchGeneration += 1
    let generation = searchGeneration
    let results = try await remote.search(text: text)
    guard generation == searchGeneration else { throw CancellationError() }
    try await reloadDeletionState(session: session)
    let visible = visibleConversations(results)
    await storeInBackground(visible, session: session)
    try ensureCurrentSession(session)
    guard generation == searchGeneration else { throw CancellationError() }
    return visibleConversations(visible)
  }

  func cancelSearch() {
    searchGeneration += 1
  }

  /// Return cache immediately through `onCached`, then always revalidate with
  /// the server. A list projection can never suppress detail revalidation.
  func detail(
    id: String,
    seed: ServerConversation,
    onCached: ((ServerConversation) -> Void)? = nil
  ) async throws -> ServerConversation {
    try await detail(id: id, fallback: seed, onCached: onCached)
  }

  /// A detail known only by id — another device's recording of an event, which
  /// the loaded list may not hold. Same cache-then-revalidate path, but with no
  /// seed to fall back on a failed fetch with nothing cached throws.
  func detail(id: String) async throws -> ServerConversation {
    try await detail(id: id, fallback: nil, onCached: nil)
  }

  private func detail(
    id: String,
    fallback seed: ServerConversation?,
    onCached: ((ServerConversation) -> Void)?
  ) async throws -> ServerConversation {
    let session = cacheWriteScope.capture()
    try await reloadDeletionState(session: session)
    try ensureNotDeleted(id)
    if let cached = try? await local.detail(id: id) {
      try ensureCurrentSession(session)
      try ensureNotDeleted(id)
      onCached?(cached)
    }

    do {
      let server = try await remote.detail(id: id)
      try ensureCurrentSession(session)
      try await reloadDeletionState(session: session)
      try ensureNotDeleted(id)
      try? await local.store(server, scope: cacheWriteScope, generation: session)
      try ensureCurrentSession(session)
      try ensureNotDeleted(id)
      if pendingMutations[id] != nil {
        updateMutationBaseline(id: id, canonical: server)
      }
      replaceVisible(server)
      applyPending(id: id)
      emit(.server)
      return server
    } catch is CancellationError {
      throw CancellationError()
    } catch {
      try ensureCurrentSession(session)
      try ensureNotDeleted(id)
      if let cached = try? await local.detail(id: id) {
        try ensureCurrentSession(session)
        try ensureNotDeleted(id)
        return cached
      }
      try ensureCurrentSession(session)
      try ensureNotDeleted(id)
      guard let seed else { throw error }
      return seed
    }
  }

  func setStarred(id: String, starred: Bool) async throws {
    let operation = MutationOperation.starred(requested: starred, mutationId: UUID())
    try await mutate(id: id, operation: operation) {
      try await self.remote.setStarred(id: id, starred: starred)
    }
  }

  func updateTitle(id: String, title: String) async throws {
    let operation = MutationOperation.title(requested: title, mutationId: UUID())
    try await mutate(id: id, operation: operation) {
      try await self.remote.updateTitle(id: id, title: title)
    }
  }

  /// Replace a conversation in local state with a freshly-fetched server
  /// version. Used after reprocess so the row sees the new `status` and full
  /// `structured` payload (not just title), which matters when reprocess
  /// transitions a `.failed` conversation back to `.completed`.
  func replace(_ conversation: ServerConversation) {
    guard !isDeleted(conversation.id) else { return }
    let session = cacheWriteScope.capture()
    replaceVisible(conversation)
    emit(.server)
    Task {
      try? await local.store(conversation, scope: cacheWriteScope, generation: session)
    }
  }

  func moveToFolder(id: String, folderId: String?) async throws {
    let operation = MutationOperation.folder(requested: folderId, mutationId: UUID())
    try await mutate(id: id, operation: operation) {
      try await self.remote.moveToFolder(id: id, folderId: folderId)
    }
  }

  func remove(id: String) {
    let removedVisibleRow = conversations.contains { $0.id == id }
    conversations.removeAll { $0.id == id }
    pendingMutations.removeValue(forKey: id)
    mutationBaselines.removeValue(forKey: id)
    if removedVisibleRow, let count {
      self.count = max(0, count - 1)
    }
    emit(.server)
  }

  func delete(id: String) async throws {
    guard deletionTokens[id] == nil else { throw CancellationError() }
    let session = cacheWriteScope.capture()
    let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot()
    let deletionToken = UUID()
    deletionTokens[id] = deletionToken
    let token = await acquireMutationSlot(id: id)
    defer {
      releaseMutationSlot(id: id, token: token)
      if deletionTokens[id] == deletionToken {
        deletionTokens.removeValue(forKey: id)
      }
    }

    let baseline = mutationBaselines[id] ?? conversations.first { $0.id == id }
    let baselineIndex = conversations.firstIndex { $0.id == id }
    var prepared = false
    var acknowledged = false
    var hadPriorDeletion = false
    do {
      try ensureCurrentSession(session)
      try Task.checkCancellation()
      hadPriorDeletion = try await local.deletionIDs().contains(id)
      try ensureCurrentSession(session)
      try await local.prepareDeletion(id: id, scope: cacheWriteScope, generation: session)
      try ensureCurrentSession(session)
      prepared = true
      deletionStateRevision += 1
      deletedIDs.insert(id)
      remove(id: id)
      try await remote.delete(id: id, authorizationSnapshot: authorizationSnapshot)
      acknowledged = true
      try ensureCurrentSession(session)
      try await local.confirmDeletion(id: id, scope: cacheWriteScope, generation: session)
      try ensureCurrentSession(session)
    } catch is CancellationError {
      // Cancellation cannot prove the server did not accept the request. Keep durable
      // intent so the next foreground/restart can safely retry it for this owner.
      throw CancellationError()
    } catch {
      try ensureCurrentSession(session)
      guard !Task.isCancelled else { throw CancellationError() }
      if prepared && !acknowledged && !hadPriorDeletion {
        try await local.rollbackDeletion(id: id, scope: cacheWriteScope, generation: session)
        try ensureCurrentSession(session)
        deletionStateRevision += 1
        deletedIDs.remove(id)
        try await reloadDeletionState(session: session)
        if !deletedIDs.contains(id), let baseline, matchesCurrentQuery(baseline),
          !conversations.contains(where: { $0.id == id })
        {
          conversations.insert(baseline, at: min(baselineIndex ?? 0, conversations.count))
          if let count { self.count = count + 1 }
          emit(.rollback)
        }
      }
      throw error
    }
  }

  func reset() {
    requestGeneration += 1
    searchGeneration += 1
    cacheWriteScope.advance()
    for waiters in mutationWaiters.values {
      for waiter in waiters {
        waiter.continuation.resume()
      }
    }
    mutationWaiters = [:]
    activeMutationTokens = [:]
    deletionTokens = [:]
    deletedIDs = []
    deletionStateRevision += 1
    deletionRecoveryTask?.cancel()
    deletionRecoveryTask = nil
    deletionRecoveryCursor = nil
    conversations = []
    count = nil
    nextPageOffset = 0
    serverPagingCount = nil
    excludedServerIDs = []
    hasMore = false
    isLoadingMore = false
    error = nil
    isLoading = false
    pendingMutations = [:]
    mutationBaselines = [:]
    emit(.server)
  }

  private func mergeNextPage(_ page: [ServerConversation]) {
    var indexByID = [String: Int]()
    for (index, conversation) in conversations.enumerated() {
      indexByID[conversation.id] = index
    }
    for conversation in page {
      if let index = indexByID[conversation.id] {
        conversations[index] = conversation
      } else {
        indexByID[conversation.id] = conversations.count
        conversations.append(conversation)
      }
    }
  }

  private func mutate(
    id: String,
    operation: MutationOperation,
    remotely: () async throws -> ServerConversation
  ) async throws {
    guard !isDeleted(id), deletionTokens[id] == nil else { throw CancellationError() }
    let session = cacheWriteScope.capture()
    if mutationBaselines[id] == nil {
      mutationBaselines[id] = conversations.first { $0.id == id }
    }
    var mutation = pendingMutations[id] ?? ConversationPendingMutation()
    operation.stage(in: &mutation)
    pendingMutations[id] = mutation
    applyPending(id: id)
    emit(.optimistic)

    let token = await acquireMutationSlot(id: id)
    defer { releaseMutationSlot(id: id, token: token) }

    do {
      try Task.checkCancellation()
      try ensureCurrentSession(session)
      let canonical = try await remotely()
      try ensureCurrentSession(session)
      updateMutationBaseline(id: id, canonical: canonical)
      _ = clearPendingField(id: id, operation: operation)
      replaceVisible(canonical)
      applyPending(id: id)
      try? await local.store(canonical, scope: cacheWriteScope, generation: session)
      try ensureCurrentSession(session)
      emit(.server)
      discardMutationBaselineIfSettled(id: id)
    } catch is CancellationError {
      if cacheWriteScope.isCurrent(session) {
        rollbackPendingField(id: id, operation: operation)
      }
      throw CancellationError()
    } catch {
      try ensureCurrentSession(session)
      rollbackPendingField(id: id, operation: operation)
      throw error
    }
  }

  private func rollbackPendingField(id: String, operation: MutationOperation) {
    let shouldRollback = clearPendingField(id: id, operation: operation)
    if shouldRollback,
      let baseline = mutationBaselines[id],
      let index = conversations.firstIndex(where: { $0.id == id })
    {
      conversations[index] = operation.rollback(conversations[index], to: baseline)
      applyPending(id: id)
    }
    emit(.rollback)
    discardMutationBaselineIfSettled(id: id)
  }

  private func clearPendingField(id: String, operation: MutationOperation) -> Bool {
    guard var mutation = pendingMutations[id] else { return false }
    let cleared = operation.clearIfCurrent(in: &mutation)
    if mutation.isEmpty {
      pendingMutations.removeValue(forKey: id)
    } else {
      pendingMutations[id] = mutation
    }
    return cleared
  }

  private func updateMutationBaseline(id: String, canonical: ServerConversation) {
    guard let existing = mutationBaselines[id] else {
      mutationBaselines[id] = canonical
      return
    }
    if let incomingRevision = canonical.updatedAt,
      let existingRevision = existing.updatedAt,
      incomingRevision < existingRevision
    {
      return
    }
    mutationBaselines[id] = canonical
  }

  private func discardMutationBaselineIfSettled(id: String) {
    if pendingMutations[id] == nil && deletionTokens[id] == nil {
      mutationBaselines.removeValue(forKey: id)
    }
  }

  private func acquireMutationSlot(id: String) async -> UUID {
    let token = UUID()
    guard activeMutationTokens[id] != nil else {
      activeMutationTokens[id] = token
      return token
    }
    await withCheckedContinuation { continuation in
      mutationWaiters[id, default: []].append(
        MutationWaiter(token: token, continuation: continuation)
      )
    }
    return token
  }

  private func releaseMutationSlot(id: String, token: UUID) {
    guard activeMutationTokens[id] == token else { return }
    guard var waiters = mutationWaiters[id], !waiters.isEmpty else {
      activeMutationTokens.removeValue(forKey: id)
      mutationWaiters.removeValue(forKey: id)
      return
    }
    let next = waiters.removeFirst()
    activeMutationTokens[id] = next.token
    if waiters.isEmpty {
      mutationWaiters.removeValue(forKey: id)
    } else {
      mutationWaiters[id] = waiters
    }
    next.continuation.resume()
  }

  private func ensureCurrentSession(_ generation: Int) throws {
    try cacheWriteScope.ensureCurrent(generation)
  }

  private func applyPending(id: String) {
    guard let index = conversations.firstIndex(where: { $0.id == id }) else { return }
    conversations[index] = ConversationReconciliationPolicy.apply(
      mutation: pendingMutations[id],
      to: conversations[index]
    )
  }

  private func replaceVisible(_ conversation: ServerConversation) {
    guard !isDeleted(conversation.id) else { return }
    guard matchesCurrentQuery(conversation) else {
      let removedVisibleRow = conversations.contains { $0.id == conversation.id }
      conversations.removeAll { $0.id == conversation.id }
      if removedVisibleRow, let count {
        self.count = max(0, count - 1)
      }
      return
    }
    guard let index = conversations.firstIndex(where: { $0.id == conversation.id }) else { return }
    let existing = conversations[index]
    if let incoming = conversation.updatedAt,
      let current = existing.updatedAt,
      incoming < current
    {
      return
    }
    conversations[index] = conversation
  }

  private func matchesCurrentQuery(_ conversation: ServerConversation) -> Bool {
    guard let query = currentQuery else { return true }
    if query.starredOnly && !conversation.starred { return false }
    if let folderId = query.folderId, conversation.folderId != folderId { return false }
    if let date = query.date {
      let calendar = Calendar.current
      let start = calendar.startOfDay(for: date)
      guard let end = calendar.date(byAdding: .day, value: 1, to: start) else { return false }
      let conversationDate = conversation.startedAt ?? conversation.createdAt
      if conversationDate < start || conversationDate >= end { return false }
    }
    return true
  }

  private func storeInBackground(_ server: [ServerConversation], session: Int) async {
    try? await local.storeMany(visibleConversations(server), scope: cacheWriteScope, generation: session)
  }

  private func isDeleted(_ id: String) -> Bool {
    deletedIDs.contains(id)
  }

  private func ensureNotDeleted(_ id: String) throws {
    guard !isDeleted(id) else { throw CancellationError() }
  }

  private func visibleConversations(_ rows: [ServerConversation]) -> [ServerConversation] {
    rows.filter { !$0.deleted && !isDeleted($0.id) }
  }

  private func reloadDeletionState(session: Int) async throws {
    let revision = deletionStateRevision
    let ids = try await local.deletionIDs()
    try ensureCurrentSession(session)
    // A read started before a delete/rollback must not replace its newer local state.
    if revision == deletionStateRevision { deletedIDs.formUnion(ids) }
  }

  private func scheduleDeletionRecovery(session: Int) {
    guard deletionRecoveryTask == nil else { return }
    let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot()
    deletionRecoveryTask = Task { [weak self] in
      guard let self else { return }
      defer {
        if self.cacheWriteScope.isCurrent(session) { self.deletionRecoveryTask = nil }
      }
      do {
        let ids = try await self.local.pendingDeletionIDs()
        try self.ensureCurrentSession(session)
        let ordered = ids.sorted()
        let cursor = self.deletionRecoveryCursor
        let remaining = ordered.filter { id in cursor.map { id > $0 } ?? true }
        let wrapped = ordered.filter { id in cursor.map { id <= $0 } ?? false }
        // Rotate bounded batches so an old failing delete cannot starve later valid intents.
        for id in (remaining + wrapped).prefix(Self.pageSize) {
          try Task.checkCancellation()
          try self.ensureCurrentSession(session)
          guard self.deletionTokens[id] == nil else { continue }
          self.deletionRecoveryCursor = id
          let deletionToken = UUID()
          self.deletionTokens[id] = deletionToken
          let token = await self.acquireMutationSlot(id: id)
          defer {
            self.releaseMutationSlot(id: id, token: token)
            if self.deletionTokens[id] == deletionToken { self.deletionTokens.removeValue(forKey: id) }
          }
          do {
            try self.ensureCurrentSession(session)
            try Task.checkCancellation()
            try await self.remote.delete(id: id, authorizationSnapshot: authorizationSnapshot)
            try self.ensureCurrentSession(session)
            try await self.local.confirmDeletion(id: id, scope: self.cacheWriteScope, generation: session)
          } catch is CancellationError {
            throw CancellationError()
          } catch {
            try self.ensureCurrentSession(session)
            self.error = UserFacingErrorPresentation.message(for: error, while: .conversations)
            self.emit(.server)
            // Leave the marker pending; another refresh or foreground retries the intent.
          }
        }
      } catch is CancellationError {
        // The original owner's durable intent survives a reset or cancellation.
      } catch {
        guard self.cacheWriteScope.isCurrent(session) else { return }
        self.error = UserFacingErrorPresentation.message(for: error, while: .conversations)
        self.emit(.server)
      }
    }
  }

  /// Foreground recovery is owned by the same repository as user-initiated deletion.
  func retryPendingDeletions() async {
    let session = cacheWriteScope.capture()
    do {
      try await reloadDeletionState(session: session)
      scheduleDeletionRecovery(session: session)
      await deletionRecoveryTask?.value
    } catch is CancellationError {
      // The original owner's durable intent survives a reset or cancellation.
    } catch {
      guard cacheWriteScope.isCurrent(session) else { return }
      self.error = UserFacingErrorPresentation.message(for: error, while: .conversations)
      emit(.server)
    }
  }

  private func emit(_ source: ConversationSnapshotSource) {
    onSnapshot?(
      ConversationRepositorySnapshot(
        conversations: conversations,
        count: count,
        isLoading: isLoading,
        error: error,
        source: source
      )
    )
  }
}
