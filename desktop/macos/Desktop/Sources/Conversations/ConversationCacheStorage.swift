import Foundation
import GRDB

struct ConversationCompleteness: OptionSet, Codable, Equatable, Sendable {
  let rawValue: Int

  static let list = ConversationCompleteness(rawValue: 1 << 0)
  static let detail = ConversationCompleteness(rawValue: 1 << 1)
  static let transcript = ConversationCompleteness(rawValue: 1 << 2)
}

struct ConversationQuery: Equatable, Sendable {
  let showStarredOnly: Bool
  let selectedDate: Date?
  let folderId: String?
  let limit: Int

  init(
    showStarredOnly: Bool = false,
    selectedDate: Date? = nil,
    folderId: String? = nil,
    limit: Int = 50
  ) {
    self.showStarredOnly = showStarredOnly
    self.selectedDate = selectedDate
    self.folderId = folderId
    self.limit = limit
  }

  var key: String {
    let day = selectedDate.map { Calendar.current.startOfDay(for: $0).timeIntervalSince1970.description } ?? "all"
    return "starred=\(showStarredOnly);day=\(day);folder=\(folderId ?? "all");limit=\(limit)"
  }
}

struct ConversationCacheEntry: Equatable, Sendable {
  let conversation: ServerConversation
  let completeness: ConversationCompleteness
  let cacheWrittenAt: Date
  let listFetchedAt: Date?
  let detailFetchedAt: Date?
  let transcriptFetchedAt: Date?

  init(
    conversation: ServerConversation,
    completeness: ConversationCompleteness,
    cacheWrittenAt: Date,
    listFetchedAt: Date? = nil,
    detailFetchedAt: Date? = nil,
    transcriptFetchedAt: Date? = nil
  ) {
    self.conversation = conversation
    self.completeness = completeness
    self.cacheWrittenAt = cacheWrittenAt
    self.listFetchedAt = listFetchedAt ?? (completeness.contains(.list) ? cacheWrittenAt : nil)
    self.detailFetchedAt = detailFetchedAt ?? (completeness.contains(.detail) ? cacheWrittenAt : nil)
    self.transcriptFetchedAt = transcriptFetchedAt ?? (completeness.contains(.transcript) ? cacheWrittenAt : nil)
  }
}

protocol ConversationCachePersisting: Sendable {
  func load(query: ConversationQuery, accountId: String) async throws -> [ConversationCacheEntry]
  func load(id: String, accountId: String) async throws -> ConversationCacheEntry?
  func isEmpty(accountId: String) async throws -> Bool
  func applyServerSnapshot(
    _ conversations: [ServerConversation],
    query: ConversationQuery,
    fetchedAt: Date,
    accountId: String
  ) async throws
  func upsertServerConversation(
    _ conversation: ServerConversation,
    completeness: ConversationCompleteness,
    fetchedAt: Date,
    accountId: String,
    preserveProjectionFreshness: Bool
  ) async throws
  func remove(id: String, accountId: String) async throws
  func loadPendingMutations(accountId: String) async throws -> [String: ConversationPendingMutation]
  func savePendingMutation(
    _ mutation: ConversationPendingMutation?,
    conversationId: String,
    accountId: String
  ) async throws
  func invalidateCache() async
}

private enum ConversationCacheScopeError: Error {
  case accountChanged
}

private struct ConversationCacheRecord: Codable, FetchableRecord, PersistableRecord {
  static let databaseTableName = "conversation_cache"

  let id: String
  let payload: Data
  let serverRevision: String?
  let serverUpdatedAt: Date?
  let cacheWrittenAt: Date
  let listFetchedAt: Date?
  let detailFetchedAt: Date?
  let transcriptFetchedAt: Date?
  let completeness: Int
  let createdAt: Date
  let starred: Bool
  let folderId: String?
  let status: String
  let discarded: Bool
  let deleted: Bool
}

private struct ConversationQuerySnapshotRecord: Codable, FetchableRecord, PersistableRecord {
  static let databaseTableName = "conversation_query_snapshots"

  let queryKey: String
  let conversationIdsJson: String
  let fetchedAt: Date
}

private struct ConversationPendingMutationRecord: Codable, FetchableRecord, PersistableRecord {
  static let databaseTableName = "conversation_pending_mutations"

  let conversationId: String
  let payload: Data
  let updatedAt: Date
}

enum ConversationProjectionMerge {
  static func isProvablyOlder(incoming: ServerConversation, than cached: ServerConversation) -> Bool {
    guard let incomingUpdatedAt = incoming.updatedAt, let cachedUpdatedAt = cached.updatedAt else {
      return false
    }
    return incomingUpdatedAt < cachedUpdatedAt
  }

  static func merge(
    incoming: ServerConversation,
    incomingCompleteness: ConversationCompleteness,
    cached: ConversationCacheEntry?,
    fetchedAt: Date = Date()
  ) -> ConversationCacheEntry {
    guard let cached else {
      return ConversationCacheEntry(
        conversation: incoming,
        completeness: incomingCompleteness,
        cacheWrittenAt: fetchedAt
      )
    }

    // Known server ordering wins first: a delayed revocation must not undo a
    // newer unlock/restore. An unversioned revocation remains fail-closed.
    if isProvablyOlder(incoming: incoming, than: cached.conversation) {
      return cached
    }

    // A current or unversioned lock/discard/delete response revokes locally
    // cached detail. Never resurrect sensitive fields from an older projection.
    if incoming.isLocked || incoming.deleted || incoming.discarded {
      return ConversationCacheEntry(
        conversation: incoming,
        completeness: incomingCompleteness,
        cacheWrittenAt: fetchedAt
      )
    }

    if incoming.updatedAt == nil, cached.conversation.updatedAt != nil {
      return cached
    }

    let mergedCompleteness = cached.completeness.union(incomingCompleteness)
    guard !incomingCompleteness.contains(.detail), cached.completeness.contains(.detail) else {
      return ConversationCacheEntry(
        conversation: incoming,
        completeness: mergedCompleteness,
        cacheWrittenAt: fetchedAt,
        listFetchedAt: incomingCompleteness.contains(.list) ? fetchedAt : cached.listFetchedAt,
        detailFetchedAt: incomingCompleteness.contains(.detail) ? fetchedAt : cached.detailFetchedAt,
        transcriptFetchedAt: incomingCompleteness.contains(.transcript) ? fetchedAt : cached.transcriptFetchedAt
      )
    }

    let cachedConversation = cached.conversation
    let preserveTranscript = !incomingCompleteness.contains(.transcript)
      && cached.completeness.contains(.transcript)
    let structured = Structured(
      title: incoming.structured.title,
      overview: incoming.structured.overview,
      emoji: incoming.structured.emoji,
      category: incoming.structured.category,
      actionItems: cachedConversation.structured.actionItems,
      events: cachedConversation.structured.events
    )

    let merged = ServerConversation(
      id: incoming.id,
      createdAt: incoming.createdAt,
      startedAt: incoming.startedAt,
      finishedAt: incoming.finishedAt,
      structured: structured,
      transcriptSegments: preserveTranscript
        ? cachedConversation.transcriptSegments : incoming.transcriptSegments,
      transcriptSegmentsIncluded: preserveTranscript
        ? cachedConversation.transcriptSegmentsIncluded : incoming.transcriptSegmentsIncluded,
      geolocation: cachedConversation.geolocation,
      photos: cachedConversation.photos,
      appsResults: cachedConversation.appsResults,
      source: incoming.source,
      language: incoming.language,
      status: incoming.status,
      discarded: incoming.discarded,
      deleted: incoming.deleted,
      isLocked: incoming.isLocked,
      starred: incoming.starred,
      folderId: incoming.folderId,
      inputDeviceName: incoming.inputDeviceName,
      deferred: incoming.deferred,
      updatedAt: incoming.updatedAt,
      revision: incoming.revision
    )
    return ConversationCacheEntry(
      conversation: merged,
      completeness: mergedCompleteness,
      cacheWrittenAt: fetchedAt,
      listFetchedAt: incomingCompleteness.contains(.list) ? fetchedAt : cached.listFetchedAt,
      detailFetchedAt: incomingCompleteness.contains(.detail) ? fetchedAt : cached.detailFetchedAt,
      transcriptFetchedAt: incomingCompleteness.contains(.transcript) ? fetchedAt : cached.transcriptFetchedAt
    )
  }
}

actor ConversationCacheStorage: ConversationCachePersisting {
  static let shared = ConversationCacheStorage()

  private init() {}

  func invalidateCache() async {}

  private func db(accountId: String) async throws -> DatabasePool {
    // RewindDatabase owns account scoping. Resolve its current pool on every
    // operation so a delayed sign-out task can never leave this actor holding
    // the previous account's DatabasePool.
    guard Self.currentAccountId == accountId else {
      throw ConversationCacheScopeError.accountChanged
    }
    try await RewindDatabase.shared.initialize()
    guard Self.currentAccountId == accountId else {
      throw ConversationCacheScopeError.accountChanged
    }
    guard let queue = await RewindDatabase.shared.getDatabaseQueue() else {
      throw TranscriptionStorageError.databaseNotInitialized
    }
    return queue
  }

  private static var currentAccountId: String {
    RewindDatabase.currentUserId ?? "anonymous"
  }

  func isEmpty(accountId: String) async throws -> Bool {
    let queue = try await db(accountId: accountId)
    return try await queue.read { db in
      try ConversationCacheRecord.fetchCount(db) == 0
    }
  }

  func load(query: ConversationQuery, accountId: String) async throws -> [ConversationCacheEntry] {
    let queue = try await db(accountId: accountId)
    let records = try await queue.read { db -> [ConversationCacheRecord] in
      if let snapshot = try ConversationQuerySnapshotRecord.fetchOne(db, key: query.key),
         let data = snapshot.conversationIdsJson.data(using: .utf8),
         let ids = try? JSONDecoder().decode([String].self, from: data) {
        let byId = Dictionary(
          uniqueKeysWithValues: try ConversationCacheRecord
            .filter(ids.contains(Column("id")))
            .fetchAll(db)
            .map { ($0.id, $0) }
        )
        return ids.compactMap { byId[$0] }.filter { Self.matches($0, query: query) }
      }

      var request = ConversationCacheRecord
        .filter(Column("deleted") == false)
        .filter(Column("discarded") == false)
      if query.showStarredOnly {
        request = request.filter(Column("starred") == true)
      }
      if let folderId = query.folderId {
        request = request.filter(Column("folderId") == folderId)
      }
      if let selectedDate = query.selectedDate {
        let start = Calendar.current.startOfDay(for: selectedDate)
        let end = Calendar.current.date(byAdding: .day, value: 1, to: start)!
        request = request
          .filter(Column("createdAt") >= start)
          .filter(Column("createdAt") < end)
      }
      return try request.order(Column("createdAt").desc).limit(query.limit).fetchAll(db)
    }
    return try records.map(Self.decode)
  }

  func load(id: String, accountId: String) async throws -> ConversationCacheEntry? {
    let queue = try await db(accountId: accountId)
    guard let record = try await queue.read({ db in
      try ConversationCacheRecord.fetchOne(db, key: id)
    }) else { return nil }
    return try Self.decode(record)
  }

  func applyServerSnapshot(
    _ conversations: [ServerConversation],
    query: ConversationQuery,
    fetchedAt: Date,
    accountId: String
  ) async throws {
    let queue = try await db(accountId: accountId)
    let idsData = try JSONEncoder().encode(conversations.map(\.id))
    let idsJson = String(decoding: idsData, as: UTF8.self)
    var records: [ConversationCacheRecord] = []
    for conversation in conversations {
      let incomingCompleteness = Self.listCompleteness(for: conversation)
      let cachedRecord = try await queue.read { db in
        try ConversationCacheRecord.fetchOne(db, key: conversation.id)
      }
      let cached = try cachedRecord.map(Self.decode)
      let merged = ConversationProjectionMerge.merge(
        incoming: conversation,
        incomingCompleteness: incomingCompleteness,
        cached: cached,
        fetchedAt: fetchedAt
      )
      records.append(try Self.record(from: merged, writtenAt: fetchedAt))
    }
    let recordsToSave = records
    try await queue.write { db in
      for record in recordsToSave {
        try record.save(db)
      }
      try ConversationQuerySnapshotRecord(
        queryKey: query.key,
        conversationIdsJson: idsJson,
        fetchedAt: fetchedAt
      ).save(db)
    }
  }

  func upsertServerConversation(
    _ conversation: ServerConversation,
    completeness: ConversationCompleteness,
    fetchedAt: Date,
    accountId: String,
    preserveProjectionFreshness: Bool = false
  ) async throws {
    let queue = try await db(accountId: accountId)
    let cachedRecord = try await queue.read { db in
      try ConversationCacheRecord.fetchOne(db, key: conversation.id)
    }
    let cached = try cachedRecord.map(Self.decode)
    var merged = ConversationProjectionMerge.merge(
      incoming: conversation,
      incomingCompleteness: completeness,
      cached: cached,
      fetchedAt: fetchedAt
    )
    if preserveProjectionFreshness, let cached {
      merged = ConversationCacheEntry(
        conversation: merged.conversation,
        completeness: merged.completeness,
        cacheWrittenAt: fetchedAt,
        listFetchedAt: cached.listFetchedAt,
        detailFetchedAt: cached.detailFetchedAt,
        transcriptFetchedAt: cached.transcriptFetchedAt
      )
    }
    let updated = try Self.record(from: merged, writtenAt: fetchedAt)
    try await queue.write { db in
      try updated.save(db)
    }
  }

  func remove(id: String, accountId: String) async throws {
    let queue = try await db(accountId: accountId)
    try await queue.write { db in
      _ = try ConversationCacheRecord.deleteOne(db, key: id)
      let snapshots = try ConversationQuerySnapshotRecord.fetchAll(db)
      for snapshot in snapshots {
        guard let data = snapshot.conversationIdsJson.data(using: .utf8),
              var ids = try? JSONDecoder().decode([String].self, from: data),
              ids.contains(id)
        else { continue }
        ids.removeAll { $0 == id }
        let encoded = try JSONEncoder().encode(ids)
        try ConversationQuerySnapshotRecord(
          queryKey: snapshot.queryKey,
          conversationIdsJson: String(decoding: encoded, as: UTF8.self),
          fetchedAt: snapshot.fetchedAt
        ).save(db)
      }
    }
  }

  func loadPendingMutations(accountId: String) async throws -> [String: ConversationPendingMutation] {
    let queue = try await db(accountId: accountId)
    let records = try await queue.read { db in
      try ConversationPendingMutationRecord.fetchAll(db)
    }
    return Dictionary(uniqueKeysWithValues: try records.map { record in
      (record.conversationId, try Self.decoder().decode(ConversationPendingMutation.self, from: record.payload))
    })
  }

  func savePendingMutation(
    _ mutation: ConversationPendingMutation?,
    conversationId: String,
    accountId: String
  ) async throws {
    let queue = try await db(accountId: accountId)
    let payload = try mutation.map { try Self.encoder().encode($0) }
    try await queue.write { db in
      guard let mutation, !mutation.isEmpty, let payload else {
        _ = try ConversationPendingMutationRecord.deleteOne(db, key: conversationId)
        return
      }
      try ConversationPendingMutationRecord(
        conversationId: conversationId,
        payload: payload,
        updatedAt: Date()
      ).save(db)
    }
  }

  private static func listCompleteness(for conversation: ServerConversation) -> ConversationCompleteness {
    var completeness: ConversationCompleteness = [.list]
    if conversation.transcriptSegmentsIncluded {
      completeness.insert(.transcript)
    }
    return completeness
  }

  private static func matches(_ record: ConversationCacheRecord, query: ConversationQuery) -> Bool {
    guard !record.deleted, !record.discarded else { return false }
    if query.showStarredOnly, !record.starred { return false }
    if let folderId = query.folderId, record.folderId != folderId { return false }
    if let selectedDate = query.selectedDate {
      let start = Calendar.current.startOfDay(for: selectedDate)
      guard let end = Calendar.current.date(byAdding: .day, value: 1, to: start),
            record.createdAt >= start, record.createdAt < end
      else { return false }
    }
    return true
  }

  private static func decode(_ record: ConversationCacheRecord) throws -> ConversationCacheEntry {
    var conversation = try decoder().decode(ServerConversation.self, from: record.payload)
    let completeness = ConversationCompleteness(rawValue: record.completeness)
    conversation.transcriptSegmentsIncluded = completeness.contains(.transcript)
    return ConversationCacheEntry(
      conversation: conversation,
      completeness: completeness,
      cacheWrittenAt: record.cacheWrittenAt,
      listFetchedAt: record.listFetchedAt,
      detailFetchedAt: record.detailFetchedAt,
      transcriptFetchedAt: record.transcriptFetchedAt
    )
  }

  private static func record(from entry: ConversationCacheEntry, writtenAt: Date) throws -> ConversationCacheRecord {
    let conversation = entry.conversation
    return ConversationCacheRecord(
      id: conversation.id,
      payload: try encoder().encode(conversation),
      serverRevision: conversation.revision,
      serverUpdatedAt: conversation.updatedAt,
      cacheWrittenAt: writtenAt,
      listFetchedAt: entry.listFetchedAt,
      detailFetchedAt: entry.detailFetchedAt,
      transcriptFetchedAt: entry.transcriptFetchedAt,
      completeness: entry.completeness.rawValue,
      createdAt: conversation.createdAt,
      starred: conversation.starred,
      folderId: conversation.folderId,
      status: conversation.status.rawValue,
      discarded: conversation.discarded,
      deleted: conversation.deleted
    )
  }

  private static func encoder() -> JSONEncoder {
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    return encoder
  }

  private static func decoder() -> JSONDecoder {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return decoder
  }
}
