import Foundation

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

protocol ConversationRemoteDataSource {
  func list(query: ConversationListQuery) async throws -> [ServerConversation]
  func count(query: ConversationListQuery) async throws -> Int
  func detail(id: String) async throws -> ServerConversation
  func search(text: String) async throws -> [ServerConversation]
  func setStarred(id: String, starred: Bool) async throws -> ServerConversation
  func updateTitle(id: String, title: String) async throws -> ServerConversation
  func moveToFolder(id: String, folderId: String?) async throws -> ServerConversation
  func delete(id: String) async throws
}

protocol ConversationLocalDataSource {
  func list(query: ConversationListQuery) async throws -> [ServerConversation]
  func count(query: ConversationListQuery) async throws -> Int
  func detail(id: String) async throws -> ServerConversation?
  func store(
    _ conversation: ServerConversation,
    scope: ConversationCacheWriteScope,
    generation: Int
  ) async throws
  func delete(
    id: String,
    scope: ConversationCacheWriteScope,
    generation: Int
  ) async throws
}

struct LiveConversationRemoteDataSource: ConversationRemoteDataSource {
  func list(query: ConversationListQuery) async throws -> [ServerConversation] {
    let range = query.dateRange
    return try await APIClient.shared.getConversations(
      limit: 50,
      offset: 0,
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

  func delete(id: String) async throws {
    try await APIClient.shared.deleteConversation(id: id)
  }
}

struct LiveConversationLocalDataSource: ConversationLocalDataSource {
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

  func delete(
    id: String,
    scope: ConversationCacheWriteScope,
    generation: Int
  ) async throws {
    try await TranscriptionStorage.shared.deleteByBackendId(
      id,
      cacheScope: scope,
      cacheGeneration: generation
    )
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
  private var currentQuery: ConversationListQuery?

  private(set) var conversations: [ServerConversation] = []
  private(set) var count: Int?
  private(set) var isLoading = false
  private(set) var error: String?
  var onSnapshot: ((ConversationRepositorySnapshot) -> Void)?

  init(remote: ConversationRemoteDataSource, local: ConversationLocalDataSource) {
    self.remote = remote
    self.local = local
  }

  convenience init() {
    self.init(remote: LiveConversationRemoteDataSource(), local: LiveConversationLocalDataSource())
  }

  func load(query: ConversationListQuery, includeCache: Bool = true) async {
    let session = cacheWriteScope.capture()
    requestGeneration += 1
    let generation = requestGeneration
    let queryChanged = currentQuery != query
    currentQuery = query
    isLoading = true
    error = nil
    if queryChanged {
      conversations = []
      count = nil
      emit(.cache)
    }

    if includeCache && query.date == nil {
      do {
        let cached = try await local.list(query: query)
        guard generation == requestGeneration else { return }
        if !cached.isEmpty {
          let cachedCount = try? await local.count(query: query)
          guard generation == requestGeneration else { return }
          conversations = cached
          count = cachedCount
          emit(.cache)
        }
      } catch {
        // Cache failure is recoverable: the server fetch below remains authoritative.
      }
    }

    do {
      async let listTask = remote.list(query: query)
      async let countTask = remote.count(query: query)
      let server = try await listTask
      let serverCount = try? await countTask
      guard generation == requestGeneration else { return }

      let result = ConversationReconciliationPolicy.mergeList(
        server: server,
        current: conversations,
        pendingMutations: pendingMutations,
        pendingMutationTTL: .greatestFiniteMagnitude
      )
      for conversation in server where result.pendingMutations[conversation.id] != nil {
        updateMutationBaseline(id: conversation.id, canonical: conversation)
      }
      pendingMutations = result.pendingMutations
      mutationBaselines = mutationBaselines.filter { pendingMutations[$0.key] != nil }
      conversations = result.conversations
      count = serverCount ?? count
      isLoading = false
      emit(.server)
      await storeInBackground(server, session: session)
    } catch {
      guard generation == requestGeneration else { return }
      isLoading = false
      if conversations.isEmpty {
        self.error = error.localizedDescription
      }
      emit(conversations.isEmpty ? .server : .cache)
    }
  }

  func refresh(query: ConversationListQuery) async {
    await load(query: query, includeCache: false)
  }

  func search(text: String) async throws -> [ServerConversation] {
    let session = cacheWriteScope.capture()
    searchGeneration += 1
    let generation = searchGeneration
    let results = try await remote.search(text: text)
    guard generation == searchGeneration else { throw CancellationError() }
    await storeInBackground(results, session: session)
    return results
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
    let session = cacheWriteScope.capture()
    if let cached = try? await local.detail(id: id) {
      try ensureCurrentSession(session)
      onCached?(cached)
    }

    do {
      let server = try await remote.detail(id: id)
      try ensureCurrentSession(session)
      try? await local.store(server, scope: cacheWriteScope, generation: session)
      try ensureCurrentSession(session)
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
      if let cached = try? await local.detail(id: id) {
        try ensureCurrentSession(session)
        return cached
      }
      try ensureCurrentSession(session)
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
    if removedVisibleRow, let count {
      self.count = max(0, count - 1)
    }
    emit(.server)
  }

  func delete(id: String) async throws {
    guard deletionTokens[id] == nil else { throw CancellationError() }
    let session = cacheWriteScope.capture()
    let deletionToken = UUID()
    deletionTokens[id] = deletionToken
    let token = await acquireMutationSlot(id: id)
    defer {
      releaseMutationSlot(id: id, token: token)
      if deletionTokens[id] == deletionToken {
        deletionTokens.removeValue(forKey: id)
      }
    }

    try ensureCurrentSession(session)
    try Task.checkCancellation()
    try await remote.delete(id: id)
    try ensureCurrentSession(session)
    try? await local.delete(id: id, scope: cacheWriteScope, generation: session)
    try ensureCurrentSession(session)
    remove(id: id)
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
    conversations = []
    count = nil
    error = nil
    isLoading = false
    pendingMutations = [:]
    mutationBaselines = [:]
    emit(.server)
  }

  private func mutate(
    id: String,
    operation: MutationOperation,
    remotely: () async throws -> ServerConversation
  ) async throws {
    guard deletionTokens[id] == nil else { throw CancellationError() }
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
       let index = conversations.firstIndex(where: { $0.id == id }) {
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
       incomingRevision < existingRevision {
      return
    }
    mutationBaselines[id] = canonical
  }

  private func discardMutationBaselineIfSettled(id: String) {
    if pendingMutations[id] == nil {
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
       incoming < current {
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
    for conversation in server {
      try? await local.store(conversation, scope: cacheWriteScope, generation: session)
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
