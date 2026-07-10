import Foundation

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
  func store(_ conversation: ServerConversation) async throws
  func delete(id: String) async throws
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

  func store(_ conversation: ServerConversation) async throws {
    _ = try await TranscriptionStorage.shared.syncServerConversation(conversation)
  }

  func delete(id: String) async throws {
    try await TranscriptionStorage.shared.deleteByBackendId(id)
  }
}

/// Sole owner of desktop Conversations cache/network reconciliation.
/// AppState is a presentation adapter; views do not choose cache versus API.
@MainActor
final class ConversationRepository {
  private let remote: ConversationRemoteDataSource
  private let local: ConversationLocalDataSource
  private var requestGeneration = 0
  private var searchGeneration = 0
  private var pendingMutations: [String: ConversationPendingMutation] = [:]
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
      pendingMutations = result.pendingMutations
      conversations = result.conversations
      count = serverCount ?? count
      isLoading = false
      emit(.server)
      await storeInBackground(server)
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
    searchGeneration += 1
    let generation = searchGeneration
    let results = try await remote.search(text: text)
    guard generation == searchGeneration else { throw CancellationError() }
    await storeInBackground(results)
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
    if let cached = try? await local.detail(id: id) {
      onCached?(cached)
    }

    do {
      let server = try await remote.detail(id: id)
      try? await local.store(server)
      replaceVisible(server)
      emit(.server)
      return server
    } catch {
      if let cached = try? await local.detail(id: id) {
        return cached
      }
      return seed
    }
  }

  func setStarred(id: String, starred: Bool) async throws {
    let previous = conversations
    var mutation = pendingMutations[id] ?? ConversationPendingMutation()
    mutation.setStarred(starred)
    pendingMutations[id] = mutation
    applyPending(id: id)
    emit(.optimistic)

    do {
      let canonical = try await remote.setStarred(id: id, starred: starred)
      pendingMutations.removeValue(forKey: id)
      replaceVisible(canonical)
      try? await local.store(canonical)
      emit(.server)
    } catch {
      pendingMutations.removeValue(forKey: id)
      conversations = previous
      emit(.rollback)
      throw error
    }
  }

  func updateTitle(id: String, title: String) async throws {
    let previous = conversations
    var mutation = pendingMutations[id] ?? ConversationPendingMutation()
    mutation.setTitle(title)
    pendingMutations[id] = mutation
    applyPending(id: id)
    emit(.optimistic)

    do {
      let canonical = try await remote.updateTitle(id: id, title: title)
      pendingMutations.removeValue(forKey: id)
      replaceVisible(canonical)
      try? await local.store(canonical)
      emit(.server)
    } catch {
      pendingMutations.removeValue(forKey: id)
      conversations = previous
      emit(.rollback)
      throw error
    }
  }

  func moveToFolder(id: String, folderId: String?) async throws {
    let previous = conversations
    var mutation = pendingMutations[id] ?? ConversationPendingMutation()
    mutation.setFolderId(folderId)
    pendingMutations[id] = mutation
    applyPending(id: id)
    emit(.optimistic)

    do {
      let canonical = try await remote.moveToFolder(id: id, folderId: folderId)
      pendingMutations.removeValue(forKey: id)
      replaceVisible(canonical)
      try? await local.store(canonical)
      emit(.server)
    } catch {
      pendingMutations.removeValue(forKey: id)
      conversations = previous
      emit(.rollback)
      throw error
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
    try await remote.delete(id: id)
    try? await local.delete(id: id)
    remove(id: id)
  }

  func reset() {
    requestGeneration += 1
    searchGeneration += 1
    conversations = []
    count = nil
    error = nil
    isLoading = false
    pendingMutations = [:]
    emit(.server)
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

  private func storeInBackground(_ server: [ServerConversation]) async {
    for conversation in server {
      try? await local.store(conversation)
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
