import Combine
import Foundation

enum ConversationMutationValue: Sendable, Equatable {
  case title(String)
  case starred(Bool)
  case folder(String?)
}

struct ConversationMutationAcknowledgement: Sendable {
  let id: String
  let updatedAt: Date?
  let revision: String?
  let value: ConversationMutationValue
  let conversation: ServerConversation?
}

enum ConversationEntitySource: Sendable, Equatable {
  case cache
  case server
  case mixed
  case seeded
}

enum ConversationSyncState: Sendable, Equatable {
  case synced
  case pending
  case failed(String)
}

struct ConversationEntityMetadata: Sendable, Equatable {
  let completeness: ConversationCompleteness
  let source: ConversationEntitySource
  let fetchedAt: Date
  let listFetchedAt: Date?
  let detailFetchedAt: Date?
  let transcriptFetchedAt: Date?
  let syncState: ConversationSyncState

  init(
    completeness: ConversationCompleteness,
    source: ConversationEntitySource,
    fetchedAt: Date,
    listFetchedAt: Date? = nil,
    detailFetchedAt: Date? = nil,
    transcriptFetchedAt: Date? = nil,
    syncState: ConversationSyncState
  ) {
    self.completeness = completeness
    self.source = source
    self.fetchedAt = fetchedAt
    self.listFetchedAt = listFetchedAt
    self.detailFetchedAt = detailFetchedAt
    self.transcriptFetchedAt = transcriptFetchedAt
    self.syncState = syncState
  }
}

protocol ConversationRemoteServing: Sendable {
  func list(query: ConversationQuery) async throws -> [ServerConversation]
  func count(query: ConversationQuery) async throws -> Int
  func detail(id: String) async throws -> ServerConversation
  func search(query: String, limit: Int) async throws -> [ServerConversation]
  func updateTitle(id: String, title: String) async throws -> ConversationMutationAcknowledgement
  func updateStarred(id: String, starred: Bool) async throws -> ConversationMutationAcknowledgement
  func moveToFolder(id: String, folderId: String?) async throws -> ConversationMutationAcknowledgement
  func delete(id: String) async throws
}

actor LiveConversationRemote: ConversationRemoteServing {
  static let shared = LiveConversationRemote()

  private let api: APIClient

  init(api: APIClient = .shared) {
    self.api = api
  }

  func list(query: ConversationQuery) async throws -> [ServerConversation] {
    let range = Self.dateRange(for: query.selectedDate)
    return try await api.getConversationList(
      limit: query.limit,
      offset: 0,
      statuses: [.completed, .processing],
      includeDiscarded: false,
      startDate: range?.start,
      endDate: range?.end,
      folderId: query.folderId,
      starred: query.showStarredOnly ? true : nil
    )
  }

  func count(query: ConversationQuery) async throws -> Int {
    let range = Self.dateRange(for: query.selectedDate)
    return try await api.getConversationsCount(
      includeDiscarded: false,
      statuses: [.completed, .processing],
      startDate: range?.start,
      endDate: range?.end,
      folderId: query.folderId,
      starred: query.showStarredOnly ? true : nil
    )
  }

  func detail(id: String) async throws -> ServerConversation {
    try await api.getConversation(id: id)
  }

  func search(query: String, limit: Int) async throws -> [ServerConversation] {
    try await api.searchConversations(
      query: query,
      page: 1,
      perPage: limit,
      includeDiscarded: false
    ).items
  }

  func updateTitle(id: String, title: String) async throws -> ConversationMutationAcknowledgement {
    try await api.updateConversationTitle(id: id, title: title)
  }

  func updateStarred(id: String, starred: Bool) async throws -> ConversationMutationAcknowledgement {
    try await api.setConversationStarred(id: id, starred: starred)
  }

  func moveToFolder(id: String, folderId: String?) async throws -> ConversationMutationAcknowledgement {
    try await api.moveConversationToFolder(conversationId: id, folderId: folderId)
  }

  func delete(id: String) async throws {
    try await api.deleteConversation(id: id)
  }

  private static func dateRange(for date: Date?) -> (start: Date, end: Date)? {
    guard let date else { return nil }
    let start = Calendar.current.startOfDay(for: date)
    guard let end = Calendar.current.date(byAdding: .day, value: 1, to: start) else { return nil }
    return (start, end)
  }
}

@MainActor
final class ConversationRepository: ObservableObject {
  static let shared = ConversationRepository()

  @Published private(set) var entitiesById: [String: ServerConversation] = [:]
  @Published private(set) var metadataById: [String: ConversationEntityMetadata] = [:]
  @Published private(set) var conversationIds: [String] = []
  @Published private(set) var searchResultIds: [String] = []
  @Published private(set) var isLoading = false
  @Published private(set) var isSearching = false
  @Published private(set) var error: String?
  @Published private(set) var searchError: String?
  @Published private(set) var totalCount: Int?
  @Published private(set) var filteredCount: Int?

  var conversations: [ServerConversation] {
    conversationIds.compactMap { entitiesById[$0] }
  }

  var searchResults: [ServerConversation] {
    searchResultIds.compactMap { entitiesById[$0] }
  }

  private let remote: any ConversationRemoteServing
  private let cache: any ConversationCachePersisting
  private let now: @Sendable () -> Date
  private let accountIdProvider: @MainActor () -> String
  private var pendingMutations: [String: ConversationPendingMutation] = [:]
  private var currentQuery = ConversationQuery()
  private var generation: UInt64 = 0
  private var searchGeneration: UInt64 = 0
  private var mutationDrainTokens: [String: UUID] = [:]
  private var didAttemptLegacyMigration = false
  private let legacyMigrationEnabled: Bool

  init(
    remote: any ConversationRemoteServing = LiveConversationRemote.shared,
    cache: any ConversationCachePersisting = ConversationCacheStorage.shared,
    now: @escaping @Sendable () -> Date = { Date() },
    accountIdProvider: @escaping @MainActor () -> String = {
      RewindDatabase.currentUserId ?? "anonymous"
    },
    legacyMigrationEnabled: Bool = true
  ) {
    self.remote = remote
    self.cache = cache
    self.now = now
    self.accountIdProvider = accountIdProvider
    self.legacyMigrationEnabled = legacyMigrationEnabled
  }

  func conversation(id: String) -> ServerConversation? {
    entitiesById[id]
  }

  func metadata(id: String) -> ConversationEntityMetadata? {
    metadataById[id]
  }

  func seed(_ conversation: ServerConversation) {
    if let existing = entitiesById[conversation.id],
       let existingUpdatedAt = existing.updatedAt,
       let incomingUpdatedAt = conversation.updatedAt,
       existingUpdatedAt > incomingUpdatedAt {
      return
    }
    entitiesById[conversation.id] = applyPending(to: conversation)
    let completeness: ConversationCompleteness = conversation.transcriptSegmentsIncluded
      ? [.list, .detail, .transcript] : [.list]
    let seededAt = now()
    metadataById[conversation.id] = ConversationEntityMetadata(
      completeness: completeness,
      source: .seeded,
      fetchedAt: seededAt,
      listFetchedAt: seededAt,
      detailFetchedAt: completeness.contains(.detail) ? seededAt : nil,
      transcriptFetchedAt: completeness.contains(.transcript) ? seededAt : nil,
      syncState: pendingMutations[conversation.id] == nil ? .synced : .pending
    )
  }

  func load(query: ConversationQuery) async {
    currentQuery = query
    generation &+= 1
    let requestGeneration = generation
    let accountId = accountIdProvider()
    isLoading = true
    error = nil

    await migrateLegacyCacheIfNeeded(query: query, accountId: accountId, requestGeneration: requestGeneration)

    do {
      async let cachedTask = cache.load(query: query, accountId: accountId)
      async let pendingTask = cache.loadPendingMutations(accountId: accountId)
      let (cached, pending) = try await (cachedTask, pendingTask)
      guard requestGeneration == generation, accountId == accountIdProvider() else { return }
      pendingMutations = pending
      publish(cached.map(\.conversation), ids: cached.map { $0.conversation.id })
      publishMetadata(cached, source: .cache)
      if !cached.isEmpty {
        isLoading = false
      }
    } catch {
      guard requestGeneration == generation, accountId == accountIdProvider() else { return }
      logError("ConversationRepository: cache-first load failed", error: error)
    }

    await refresh(query: query, requestGeneration: requestGeneration, accountId: accountId)
  }

  func refresh() async {
    generation &+= 1
    await refresh(query: currentQuery, requestGeneration: generation, accountId: accountIdProvider())
  }

  private func refresh(query: ConversationQuery, requestGeneration: UInt64, accountId: String) async {
    do {
      async let listTask = remote.list(query: query)
      async let countTask = remote.count(query: query)
      let server = try await listTask
      guard requestGeneration == generation, query == currentQuery, accountId == accountIdProvider() else { return }

      try await reconcilePendingMutations(with: server, accountId: accountId)
      try await cache.applyServerSnapshot(server, query: query, fetchedAt: now(), accountId: accountId)
      let cached = try await cache.load(query: query, accountId: accountId)
      guard requestGeneration == generation, query == currentQuery, accountId == accountIdProvider() else { return }
      publish(cached.map(\.conversation), ids: cached.map { $0.conversation.id })
      publishMetadata(cached, source: .server)

      do {
        let count = try await countTask
        guard requestGeneration == generation, accountId == accountIdProvider() else { return }
        if query.showStarredOnly || query.selectedDate != nil || query.folderId != nil {
          filteredCount = count
        } else {
          totalCount = count
          filteredCount = nil
        }
      } catch {
        logError("ConversationRepository: count refresh failed", error: error)
      }

      isLoading = false
      await retryPendingMutations(requestGeneration: requestGeneration, accountId: accountId)
    } catch {
      guard requestGeneration == generation, query == currentQuery, accountId == accountIdProvider() else { return }
      if conversations.isEmpty {
        self.error = error.localizedDescription
      }
      isLoading = false
      logError("ConversationRepository: server refresh failed", error: error)
    }
  }

  func loadDetail(id: String) async {
    let requestGeneration = generation
    let accountId = accountIdProvider()
    do {
      if let cached = try await cache.load(id: id, accountId: accountId) {
        guard requestGeneration == generation, accountId == accountIdProvider() else { return }
        entitiesById[id] = applyPending(to: cached.conversation)
        metadataById[id] = metadata(for: cached, source: .cache)
      }
    } catch {
      logError("ConversationRepository: cached detail load failed", error: error)
    }

    do {
      let detail = try await remote.detail(id: id)
      guard requestGeneration == generation, accountId == accountIdProvider() else { return }
      var completeness: ConversationCompleteness = [.list, .detail]
      if detail.transcriptSegmentsIncluded {
        completeness.insert(.transcript)
      }
      try await cache.upsertServerConversation(
        detail,
        completeness: completeness,
        fetchedAt: now(),
        accountId: accountId,
        preserveProjectionFreshness: false
      )
      let merged = try await cache.load(id: id, accountId: accountId)?.conversation ?? detail
      guard requestGeneration == generation, accountId == accountIdProvider() else { return }
      entitiesById[id] = applyPending(to: merged)
      if let entry = try await cache.load(id: id, accountId: accountId) {
        guard requestGeneration == generation, accountId == accountIdProvider() else { return }
        metadataById[id] = metadata(for: entry, source: .server)
      }
    } catch {
      guard requestGeneration == generation else { return }
      if case APIError.httpError(let statusCode, _) = error, statusCode == 404 {
        try? await cache.remove(id: id, accountId: accountId)
        guard requestGeneration == generation, accountId == accountIdProvider() else { return }
        entitiesById.removeValue(forKey: id)
        metadataById.removeValue(forKey: id)
        conversationIds.removeAll { $0 == id }
        searchResultIds.removeAll { $0 == id }
        return
      }
      if case APIError.httpError(let statusCode, _) = error,
         [402, 403].contains(statusCode),
         let current = entitiesById[id] {
        let redacted = Self.redactedLockedConversation(current)
        let redactedAt = now()
        try? await cache.upsertServerConversation(
          redacted,
          completeness: [.list],
          fetchedAt: redactedAt,
          accountId: accountId,
          preserveProjectionFreshness: false
        )
        guard requestGeneration == generation, accountId == accountIdProvider() else { return }
        entitiesById[id] = redacted
        metadataById[id] = ConversationEntityMetadata(
          completeness: [.list],
          source: .server,
          fetchedAt: redactedAt,
          listFetchedAt: redactedAt,
          syncState: .synced
        )
        return
      }
      logError("ConversationRepository: detail refresh failed", error: error)
    }
  }

  func search(_ query: String, limit: Int = 50) async {
    searchGeneration &+= 1
    let requestSearchGeneration = searchGeneration
    guard !query.isEmpty else {
      searchResultIds = []
      isSearching = false
      return
    }
    let requestGeneration = generation
    let accountId = accountIdProvider()
    isSearching = true
    searchError = nil
    do {
      let results = try await remote.search(query: query, limit: limit)
      guard requestGeneration == generation, requestSearchGeneration == searchGeneration,
            accountId == accountIdProvider() else { return }
      for result in results {
        try await cache.upsertServerConversation(
          result,
          completeness: result.transcriptSegmentsIncluded ? [.list, .transcript] : [.list],
          fetchedAt: now(),
          accountId: accountId,
          preserveProjectionFreshness: false
        )
        guard requestGeneration == generation, requestSearchGeneration == searchGeneration,
              accountId == accountIdProvider() else { return }
        let merged = try await cache.load(id: result.id, accountId: accountId)?.conversation ?? result
        guard requestGeneration == generation, requestSearchGeneration == searchGeneration,
              accountId == accountIdProvider() else { return }
        entitiesById[result.id] = applyPending(to: merged)
        if let entry = try await cache.load(id: result.id, accountId: accountId) {
          guard requestGeneration == generation, requestSearchGeneration == searchGeneration,
                accountId == accountIdProvider() else { return }
          metadataById[result.id] = metadata(for: entry, source: .server)
        }
      }
      searchResultIds = results.map(\.id)
      isSearching = false
      searchError = nil
    } catch {
      guard requestGeneration == generation, requestSearchGeneration == searchGeneration else { return }
      searchError = error.localizedDescription
      isSearching = false
      logError("ConversationRepository: search failed", error: error)
    }
  }

  func clearSearch() {
    searchGeneration &+= 1
    searchResultIds = []
    isSearching = false
    searchError = nil
  }

  func updateTitle(id: String, title: String) async throws {
    let requestGeneration = generation
    let accountId = accountIdProvider()
    var mutation = pendingMutations[id] ?? ConversationPendingMutation()
    mutation.setTitle(title)
    try await stage(
      mutation: mutation,
      conversationId: id,
      accountId: accountId,
      requestGeneration: requestGeneration
    )
    try await drainMutations(id: id, requestGeneration: requestGeneration, accountId: accountId)
  }

  func updateStarred(id: String, starred: Bool) async throws {
    let requestGeneration = generation
    let accountId = accountIdProvider()
    var mutation = pendingMutations[id] ?? ConversationPendingMutation()
    mutation.setStarred(starred)
    try await stage(
      mutation: mutation,
      conversationId: id,
      accountId: accountId,
      requestGeneration: requestGeneration
    )
    try await drainMutations(id: id, requestGeneration: requestGeneration, accountId: accountId)
  }

  func moveToFolder(id: String, folderId: String?) async throws {
    let requestGeneration = generation
    let accountId = accountIdProvider()
    var mutation = pendingMutations[id] ?? ConversationPendingMutation()
    mutation.setFolderId(folderId)
    try await stage(
      mutation: mutation,
      conversationId: id,
      accountId: accountId,
      requestGeneration: requestGeneration
    )
    try await drainMutations(id: id, requestGeneration: requestGeneration, accountId: accountId)
  }

  func delete(id: String) async throws {
    let requestGeneration = generation
    let accountId = accountIdProvider()
    do {
      try await remote.delete(id: id)
      guard requestGeneration == generation, accountId == accountIdProvider() else {
        throw CancellationError()
      }
      try await cache.remove(id: id, accountId: accountId)
      pendingMutations.removeValue(forKey: id)
      try await cache.savePendingMutation(nil, conversationId: id, accountId: accountId)
      entitiesById.removeValue(forKey: id)
      conversationIds.removeAll { $0 == id }
      searchResultIds.removeAll { $0 == id }
    } catch {
      guard requestGeneration == generation, accountId == accountIdProvider() else {
        throw CancellationError()
      }
      self.error = error.localizedDescription
      if let existing = metadataById[id] {
        metadataById[id] = ConversationEntityMetadata(
          completeness: existing.completeness,
          source: existing.source,
          fetchedAt: existing.fetchedAt,
          listFetchedAt: existing.listFetchedAt,
          detailFetchedAt: existing.detailFetchedAt,
          transcriptFetchedAt: existing.transcriptFetchedAt,
          syncState: .failed(error.localizedDescription)
        )
      }
      throw error
    }
  }

  func resetSession() {
    generation &+= 1
    searchGeneration &+= 1
    entitiesById = [:]
    metadataById = [:]
    conversationIds = []
    searchResultIds = []
    pendingMutations = [:]
    mutationDrainTokens = [:]
    totalCount = nil
    filteredCount = nil
    isLoading = false
    isSearching = false
    error = nil
    searchError = nil
    currentQuery = ConversationQuery()
    didAttemptLegacyMigration = false
    Task { await cache.invalidateCache() }
  }

  /// Compatibility setter used while AppState callers migrate. It updates the
  /// single repository projection rather than creating a second owner.
  func replaceVisibleConversations(_ conversations: [ServerConversation]) {
    publish(conversations, ids: conversations.map(\.id))
  }

  private func publish(_ conversations: [ServerConversation], ids: [String]) {
    for conversation in conversations {
      entitiesById[conversation.id] = applyPending(to: conversation)
    }
    conversationIds = ids.filter { id in
      guard let conversation = entitiesById[id] else { return false }
      return matchesCurrentQuery(conversation)
    }
  }

  private func publishMetadata(
    _ entries: [ConversationCacheEntry],
    source: ConversationEntitySource
  ) {
    for entry in entries {
      metadataById[entry.conversation.id] = metadata(for: entry, source: source)
    }
  }

  private func metadata(
    for entry: ConversationCacheEntry,
    source: ConversationEntitySource
  ) -> ConversationEntityMetadata {
    let hasOlderRichProjection = source == .server && (
      entry.detailFetchedAt.map { $0 < (entry.listFetchedAt ?? entry.cacheWrittenAt) } == true
        || entry.transcriptFetchedAt.map { $0 < (entry.listFetchedAt ?? entry.cacheWrittenAt) } == true
    )
    return ConversationEntityMetadata(
      completeness: entry.completeness,
      source: hasOlderRichProjection ? .mixed : source,
      fetchedAt: entry.listFetchedAt ?? entry.cacheWrittenAt,
      listFetchedAt: entry.listFetchedAt,
      detailFetchedAt: entry.detailFetchedAt,
      transcriptFetchedAt: entry.transcriptFetchedAt,
      syncState: pendingMutations[entry.conversation.id] == nil ? .synced : .pending
    )
  }

  private func matchesCurrentQuery(_ conversation: ServerConversation) -> Bool {
    guard !conversation.deleted, !conversation.discarded else { return false }
    if currentQuery.showStarredOnly, !conversation.starred { return false }
    if let folderId = currentQuery.folderId, conversation.folderId != folderId { return false }
    if let selectedDate = currentQuery.selectedDate {
      let start = Calendar.current.startOfDay(for: selectedDate)
      guard let end = Calendar.current.date(byAdding: .day, value: 1, to: start),
            conversation.createdAt >= start, conversation.createdAt < end
      else { return false }
    }
    return true
  }

  private func reconcileVisibleMembership(for id: String) {
    guard let conversation = entitiesById[id] else {
      conversationIds.removeAll { $0 == id }
      return
    }
    if matchesCurrentQuery(conversation) {
      if !conversationIds.contains(id) { conversationIds.append(id) }
      conversationIds.sort {
        (entitiesById[$0]?.createdAt ?? .distantPast) > (entitiesById[$1]?.createdAt ?? .distantPast)
      }
      if conversationIds.count > currentQuery.limit {
        conversationIds = Array(conversationIds.prefix(currentQuery.limit))
      }
    } else {
      conversationIds.removeAll { $0 == id }
    }
  }

  private func applyPending(to conversation: ServerConversation) -> ServerConversation {
    ConversationReconciliationPolicy.apply(
      mutation: pendingMutations[conversation.id],
      to: conversation
    )
  }

  private func stage(
    mutation: ConversationPendingMutation,
    conversationId: String,
    accountId: String,
    requestGeneration: UInt64
  ) async throws {
    guard requestGeneration == generation, accountId == accountIdProvider() else {
      throw CancellationError()
    }
    pendingMutations[conversationId] = mutation
    try await cache.savePendingMutation(mutation, conversationId: conversationId, accountId: accountId)
    guard requestGeneration == generation, accountId == accountIdProvider() else {
      throw CancellationError()
    }
    guard let current = entitiesById[conversationId] else { return }
    let optimistic = ConversationReconciliationPolicy.apply(mutation: mutation, to: current)
    entitiesById[conversationId] = optimistic
    let existingMetadata = metadataById[conversationId]
    metadataById[conversationId] = ConversationEntityMetadata(
      completeness: existingMetadata?.completeness ?? [.list],
      source: existingMetadata?.source ?? .cache,
      fetchedAt: existingMetadata?.fetchedAt ?? now(),
      listFetchedAt: existingMetadata?.listFetchedAt,
      detailFetchedAt: existingMetadata?.detailFetchedAt,
      transcriptFetchedAt: existingMetadata?.transcriptFetchedAt,
      syncState: .pending
    )
    reconcileVisibleMembership(for: conversationId)
  }

  private func acceptCanonical(
    _ canonical: ServerConversation,
    requestGeneration: UInt64,
    accountId: String
  ) async throws {
    guard requestGeneration == generation, accountId == accountIdProvider() else {
      throw CancellationError()
    }
    var completeness: ConversationCompleteness = [.list, .detail]
    if canonical.transcriptSegmentsIncluded {
      completeness.insert(.transcript)
    }
    let prior = try await cache.load(id: canonical.id, accountId: accountId)
    try await cache.upsertServerConversation(
      canonical,
      completeness: completeness,
      fetchedAt: now(),
      accountId: accountId,
      preserveProjectionFreshness: false
    )
    let mergedCanonical = try await cache.load(id: canonical.id, accountId: accountId)?.conversation ?? canonical
    guard requestGeneration == generation, accountId == accountIdProvider() else {
      throw CancellationError()
    }

    var mutation = pendingMutations[canonical.id]
    let canonicalCanConfirmMutation = canonical.updatedAt != nil || canonical.revision != nil
      || (prior?.conversation.updatedAt == nil && prior?.conversation.revision == nil)
    if canonicalCanConfirmMutation {
      mutation?.clearResolvedFields(matching: canonical)
    }
    if let mutation, !mutation.isEmpty {
      pendingMutations[canonical.id] = mutation
      try await cache.savePendingMutation(mutation, conversationId: canonical.id, accountId: accountId)
    } else {
      pendingMutations.removeValue(forKey: canonical.id)
      try await cache.savePendingMutation(nil, conversationId: canonical.id, accountId: accountId)
    }
    entitiesById[canonical.id] = applyPending(to: mergedCanonical)
    if let entry = try await cache.load(id: canonical.id, accountId: accountId) {
      metadataById[canonical.id] = metadata(for: entry, source: .server)
    }
    reconcileVisibleMembership(for: canonical.id)
  }

  private func drainMutations(
    id: String,
    requestGeneration: UInt64,
    accountId: String
  ) async throws {
    guard mutationDrainTokens[id] == nil else { return }
    let drainToken = UUID()
    mutationDrainTokens[id] = drainToken
    defer {
      if mutationDrainTokens[id] == drainToken {
        mutationDrainTokens.removeValue(forKey: id)
      }
    }
    var firstPermanentFailure: Error?

    while let mutation = pendingMutations[id], !mutation.isEmpty {
      guard requestGeneration == generation, accountId == accountIdProvider() else {
        throw CancellationError()
      }
      let attemptedValue: ConversationMutationValue
      if let title = mutation.title {
        attemptedValue = .title(title)
      } else if let starred = mutation.starred {
        attemptedValue = .starred(starred)
      } else if mutation.hasFolderIdMutation {
        attemptedValue = .folder(mutation.folderId)
      } else {
        return
      }
      do {
        let acknowledgement: ConversationMutationAcknowledgement
        switch attemptedValue {
        case .title(let title):
          acknowledgement = try await remote.updateTitle(id: id, title: title)
        case .starred(let starred):
          acknowledgement = try await remote.updateStarred(id: id, starred: starred)
        case .folder(let folderId):
          acknowledgement = try await remote.moveToFolder(id: id, folderId: folderId)
        }
        let confirmed = try await acceptAcknowledgement(
          acknowledgement,
          requestGeneration: requestGeneration,
          accountId: accountId
        )
        if !confirmed { return }
      } catch {
        let permanent = Self.isPermanentMutationFailure(error)
        try await handleMutationFailure(
          error,
          attemptedValue: attemptedValue,
          id: id,
          requestGeneration: requestGeneration,
          accountId: accountId
        )
        if permanent {
          if firstPermanentFailure == nil { firstPermanentFailure = error }
          continue
        }
        throw error
      }
    }
    if let firstPermanentFailure { throw firstPermanentFailure }
  }

  private func acceptAcknowledgement(
    _ acknowledgement: ConversationMutationAcknowledgement,
    requestGeneration: UInt64,
    accountId: String
  ) async throws -> Bool {
    guard requestGeneration == generation, accountId == accountIdProvider() else {
      throw CancellationError()
    }
    if let conversation = acknowledgement.conversation {
      try await acceptCanonical(
        conversation,
        requestGeneration: requestGeneration,
        accountId: accountId
      )
      return true
    }

    guard acknowledgement.updatedAt != nil || acknowledgement.revision != nil else {
      // A legacy status-only 2xx proves request acceptance but not which
      // projection/version a mixed rollout will serve next. Keep the durable
      // overlay until a list response contains the requested value.
      return false
    }

    guard let current = entitiesById[acknowledgement.id] else { return true }
    var acknowledgedMutation = ConversationPendingMutation()
    switch acknowledgement.value {
    case .title(let title): acknowledgedMutation.setTitle(title)
    case .starred(let starred): acknowledgedMutation.setStarred(starred)
    case .folder(let folderId): acknowledgedMutation.setFolderId(folderId)
    }
    let acknowledged = Self.withServerVersion(
      ConversationReconciliationPolicy.apply(mutation: acknowledgedMutation, to: current),
      updatedAt: acknowledgement.updatedAt,
      revision: acknowledgement.revision
    )
    let cached = try await cache.load(id: acknowledgement.id, accountId: accountId)
    try await cache.upsertServerConversation(
      acknowledged,
      completeness: cached?.completeness ?? [.list],
      fetchedAt: now(),
      accountId: accountId,
      preserveProjectionFreshness: true
    )
    guard requestGeneration == generation, accountId == accountIdProvider() else {
      throw CancellationError()
    }

    var pending = pendingMutations[acknowledgement.id]
    pending?.clearAcknowledged(acknowledgement.value)
    if let pending, !pending.isEmpty {
      pendingMutations[acknowledgement.id] = pending
      try await cache.savePendingMutation(
        pending,
        conversationId: acknowledgement.id,
        accountId: accountId
      )
    } else {
      pendingMutations.removeValue(forKey: acknowledgement.id)
      try await cache.savePendingMutation(nil, conversationId: acknowledgement.id, accountId: accountId)
    }
    let merged = try await cache.load(id: acknowledgement.id, accountId: accountId)
    guard requestGeneration == generation, accountId == accountIdProvider() else {
      throw CancellationError()
    }
    if let merged {
      entitiesById[acknowledgement.id] = applyPending(to: merged.conversation)
      metadataById[acknowledgement.id] = metadata(for: merged, source: .server)
      reconcileVisibleMembership(for: acknowledgement.id)
    }
    return true
  }

  private func handleMutationFailure(
    _ failure: Error,
    attemptedValue: ConversationMutationValue,
    id: String,
    requestGeneration: UInt64,
    accountId: String
  ) async throws {
    guard requestGeneration == generation, accountId == accountIdProvider() else {
      throw CancellationError()
    }
    let message = failure.localizedDescription
    let existingMetadata = metadataById[id]
    metadataById[id] = ConversationEntityMetadata(
      completeness: existingMetadata?.completeness ?? [.list],
      source: existingMetadata?.source ?? .cache,
      fetchedAt: existingMetadata?.fetchedAt ?? now(),
      listFetchedAt: existingMetadata?.listFetchedAt,
      detailFetchedAt: existingMetadata?.detailFetchedAt,
      transcriptFetchedAt: existingMetadata?.transcriptFetchedAt,
      syncState: Self.isPermanentMutationFailure(failure) ? .failed(message) : .pending
    )
    guard Self.isPermanentMutationFailure(failure) else { return }

    var pending = pendingMutations[id]
    pending?.clearAcknowledged(attemptedValue)
    if let pending, !pending.isEmpty {
      pendingMutations[id] = pending
      try await cache.savePendingMutation(pending, conversationId: id, accountId: accountId)
    } else {
      pendingMutations.removeValue(forKey: id)
      try await cache.savePendingMutation(nil, conversationId: id, accountId: accountId)
    }
    await loadDetail(id: id)
    if entitiesById[id] != nil {
      let refreshedMetadata = metadataById[id]
      metadataById[id] = ConversationEntityMetadata(
        completeness: refreshedMetadata?.completeness ?? [.list],
        source: refreshedMetadata?.source ?? .server,
        fetchedAt: refreshedMetadata?.fetchedAt ?? now(),
        listFetchedAt: refreshedMetadata?.listFetchedAt,
        detailFetchedAt: refreshedMetadata?.detailFetchedAt,
        transcriptFetchedAt: refreshedMetadata?.transcriptFetchedAt,
        syncState: .failed(message)
      )
    }
  }

  private func reconcilePendingMutations(
    with server: [ServerConversation],
    accountId: String
  ) async throws {
    for conversation in server {
      guard var mutation = pendingMutations[conversation.id] else { continue }
      if let current = entitiesById[conversation.id] {
        if ConversationProjectionMerge.isProvablyOlder(incoming: conversation, than: current) {
          continue
        }
        if conversation.updatedAt == nil, conversation.revision == nil,
           current.updatedAt != nil || current.revision != nil {
          continue
        }
      }
      mutation.clearResolvedFields(matching: conversation)
      if mutation.isEmpty {
        pendingMutations.removeValue(forKey: conversation.id)
        try await cache.savePendingMutation(nil, conversationId: conversation.id, accountId: accountId)
      } else {
        pendingMutations[conversation.id] = mutation
        try await cache.savePendingMutation(mutation, conversationId: conversation.id, accountId: accountId)
      }
    }
  }

  private static func isPermanentMutationFailure(_ error: Error) -> Bool {
    guard case APIError.httpError(let statusCode, _) = error else { return false }
    return (400..<500).contains(statusCode) && ![408, 425, 429].contains(statusCode)
  }

  private static func withServerVersion(
    _ conversation: ServerConversation,
    updatedAt: Date?,
    revision: String?
  ) -> ServerConversation {
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
      updatedAt: updatedAt ?? conversation.updatedAt,
      revision: revision ?? conversation.revision
    )
  }

  private static func redactedLockedConversation(_ conversation: ServerConversation) -> ServerConversation {
    ServerConversation(
      id: conversation.id,
      createdAt: conversation.createdAt,
      startedAt: conversation.startedAt,
      finishedAt: conversation.finishedAt,
      structured: Structured(
        title: conversation.structured.title,
        overview: conversation.structured.overview,
        emoji: conversation.structured.emoji,
        category: conversation.structured.category,
        actionItems: [],
        events: []
      ),
      transcriptSegments: [],
      transcriptSegmentsIncluded: true,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: conversation.source,
      language: conversation.language,
      status: conversation.status,
      discarded: conversation.discarded,
      deleted: conversation.deleted,
      isLocked: true,
      starred: conversation.starred,
      folderId: conversation.folderId,
      inputDeviceName: conversation.inputDeviceName,
      deferred: conversation.deferred,
      updatedAt: conversation.updatedAt,
      revision: conversation.revision
    )
  }

  private func retryPendingMutations(requestGeneration: UInt64, accountId: String) async {
    for id in Array(pendingMutations.keys) {
      guard requestGeneration == generation, accountId == accountIdProvider() else { return }
      do {
        try await drainMutations(id: id, requestGeneration: requestGeneration, accountId: accountId)
      } catch {
        logError("ConversationRepository: pending mutation retry failed", error: error)
      }
    }
  }

  private func migrateLegacyCacheIfNeeded(
    query: ConversationQuery,
    accountId: String,
    requestGeneration: UInt64
  ) async {
    guard legacyMigrationEnabled, !didAttemptLegacyMigration else { return }
    didAttemptLegacyMigration = true
    do {
      guard try await cache.isEmpty(accountId: accountId) else { return }
      let legacy = try await TranscriptionStorage.shared.getLocalConversations(
        limit: query.limit,
        starredOnly: query.showStarredOnly,
        folderId: query.folderId
      )
      guard !legacy.isEmpty else { return }
      guard requestGeneration == generation, accountId == accountIdProvider() else { return }
      try await cache.applyServerSnapshot(legacy, query: query, fetchedAt: now(), accountId: accountId)
      for conversation in legacy {
        guard let session = try await TranscriptionStorage.shared.getSessionByBackendId(conversation.id),
              let sessionId = session.id
        else { continue }
        let segments = try await TranscriptionStorage.shared.getSegments(sessionId: sessionId)
        guard !segments.isEmpty else { continue }
        var migrated = conversation
        migrated.transcriptSegments = segments.map { $0.toTranscriptSegment() }
        migrated.transcriptSegmentsIncluded = true
        try await cache.upsertServerConversation(
          migrated,
          completeness: [.list, .transcript],
          fetchedAt: now(),
          accountId: accountId,
          preserveProjectionFreshness: false
        )
      }
    } catch {
      logError("ConversationRepository: legacy cache migration failed", error: error)
    }
  }
}
