import CryptoKit
import Foundation
@preconcurrency import GRDB

/// Identity of a memory surfaced to the UI: either a backend ID, or the
/// `local_<rowid>` placeholder minted by `MemoryRecord.toServerMemory()` for a
/// local-only row. Mutations must resolve both forms: filtering a local ID by
/// `backendId` silently misses rows whose backend sync failed or is pending.
enum MemoryIdentity: Equatable {
  case backend(String)
  case localRow(Int64)

  init(surfacedId: String) {
    if surfacedId.hasPrefix("local_"), let rowId = Int64(surfacedId.dropFirst(6)) {
      self = .localRow(rowId)
    } else {
      self = .backend(surfacedId)
    }
  }

  var isLocalOnly: Bool {
    if case .localRow = self { return true }
    return false
  }
}

/// Selects which provenance class may participate in a local-memory read.
///
/// This is intentionally separate from ``MemoryLayer``: legacy compatibility
/// rows and unsynced local captures are not product-memory tiers.
enum MemoryRecordReadScope: Sendable {
  /// Preserve the caller's historical mixed-cache behavior.
  case all
  /// Only rows whose lifecycle came from the authoritative canonical API.
  case canonicalProduct
  /// Rows that do not expose a canonical lifecycle, for legacy compatibility.
  case legacyCompatibility
}

enum MemoryLedgerTriggerSnapshotError: Error, Equatable, Sendable {
  case invalidLimit(Int)
}

enum KnowledgeLedgerMirrorSyncError: Error, Equatable, Sendable {
  case ownerChanged
  case invalidSnapshot
  case staleAuthority
  case conflictingAuthority
}

struct KnowledgeLedgerMirrorReceipt: Equatable, Sendable {
  let ownerID: String
  let accountGeneration: Int
  let commitSequence: Int
  let epochID: String
  let contentRevision: String
  let rowCount: Int
  let aliasCount: Int
}

/// The server authority which names one mirror epoch. Cursors are only
/// meaningful inside this authority; a cursor from an older head must never
/// be allowed to activate rows from that older epoch.
struct KnowledgeLedgerMirrorAuthority: Equatable, Sendable {
  let ownerID: String
  let accountGeneration: Int
  let sourceGeneration: Int
  let writerEpoch: Int
  let headCommitID: String
  let commitSequence: Int
  let epochID: String

  func matches(_ snapshot: JITTriggerSnapshot) -> Bool {
    ownerID == snapshot.ownerID
      && accountGeneration == snapshot.accountGeneration
      && headCommitID == snapshot.headCommitID
      && commitSequence == snapshot.commitSequence
  }
}

struct KnowledgeLedgerMirrorMember: Equatable, Sendable {
  let memoryID: String
  let itemRevision: Int
  let status: String
  let sourceState: String
  let canonicalMemoryID: String?
  let contentPurged: Bool
}

enum KnowledgeLedgerMirrorStageResult: Sendable {
  case next(String)
  case activated(KnowledgeLedgerMirrorReceipt)
}

enum MemoryLedgerTriggerSnapshotCompleteness: Equatable, Sendable {
  /// The bounded local query exhausted rows currently present in SQLite. This
  /// does not claim that the server mirror is complete: MemoryStorage has no
  /// durable receipt proving an exhaustive canonical ledger sync.
  case localCacheExhausted
  /// The sentinel row proves that the local query was truncated at its bound.
  case localCacheTruncated
}

struct MemoryLedgerTriggerSnapshotDiagnostics: Equatable, Sendable {
  let completeness: MemoryLedgerTriggerSnapshotCompleteness
  let localRowCount: Int
  let hasMoreLocalRows: Bool
  let isAuthoritative: Bool
  let quarantined: [KnowledgeLedgerTriggerWatchlistProjection.QuarantinedRow]
}

struct MemoryLedgerTriggerSnapshot: Equatable, Sendable {
  let projection: KnowledgeLedgerTriggerWatchlistProjection
  let diagnostics: MemoryLedgerTriggerSnapshotDiagnostics
}

/// Actor-based storage manager for memories with bidirectional sync
/// Provides local-first caching for fast startup and background sync with backend
actor MemoryStorage {
  static let shared = MemoryStorage()

  private var _dbQueue: DatabasePool?
  private var _dbGeneration = -1
  private var isInitialized = false

  private init() {}

  /// Invalidate cached DB queue (called on user switch / sign-out)
  func invalidateCache() {
    _dbQueue = nil
    isInitialized = false
  }

  /// Ensure database is initialized before use
  private func ensureInitialized() async throws -> DatabasePool {
    if let db = _dbQueue, await RewindDatabase.shared.poolGeneration() == _dbGeneration {
      return db
    }

    // Initialize RewindDatabase which creates our tables via migrations
    do {
      try await RewindDatabase.shared.initialize()
    } catch {
      log("MemoryStorage: Database initialization failed: \(error.localizedDescription)")
      throw error
    }

    let (queue, generation) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let db = queue else {
      throw MemoryStorageError.databaseNotInitialized
    }

    _dbQueue = db
    _dbGeneration = generation
    isInitialized = true
    return db
  }

  private static func applyTierFilter(_ query: QueryInterfaceRequest<MemoryRecord>, tiers: [MemoryLayer]?)
    -> QueryInterfaceRequest<MemoryRecord>
  {
    guard let tiers = tiers, !tiers.isEmpty else { return query }
    return query.filter(tiers.map { $0.rawValue }.contains(Column("tier")))
  }

  private static func applyRecordReadScope(
    _ query: QueryInterfaceRequest<MemoryRecord>,
    scope: MemoryRecordReadScope
  ) -> QueryInterfaceRequest<MemoryRecord> {
    switch scope {
    case .all:
      return query
    case .canonicalProduct:
      return query.filter(Column("tierIsExplicit") == true)
    case .legacyCompatibility:
      return query.filter(Column("tierIsExplicit") == false)
    }
  }

  private static func appendRecordReadScopeCondition(
    _ conditions: inout [String],
    scope: MemoryRecordReadScope
  ) {
    switch scope {
    case .all:
      return
    case .canonicalProduct:
      conditions.append("tierIsExplicit = 1")
    case .legacyCompatibility:
      conditions.append("tierIsExplicit = 0")
    }
  }

  private static func appendTierCondition(
    _ conditions: inout [String], _ arguments: inout [DatabaseValue], tiers: [MemoryLayer]?
  ) {
    guard let tiers = tiers, !tiers.isEmpty else { return }
    let placeholders = tiers.map { _ in "?" }.joined(separator: ", ")
    conditions.append("tier IN (\(placeholders))")
    for tier in tiers {
      if let dbValue = DatabaseValue(value: tier.rawValue) {
        arguments.append(dbValue)
      }
    }
  }

  // MARK: - Local-First Read Operations

  /// Get memories from local cache for instant display
  /// Supports filtering by category and tags
  func getLocalMemories(
    limit: Int = 50,
    offset: Int = 0,
    category: String? = nil,
    tags: [String]? = nil,
    tiers: [MemoryLayer]? = [.shortTerm, .longTerm],
    scope: MemoryRecordReadScope = .all,
    includeDismissed: Bool = false
  ) async throws -> [ServerMemory] {
    let db = try await ensureInitialized()

    return try await db.read { database in
      var query =
        MemoryRecord
        .filter(Column("deleted") == false)
      // Show ALL local memories (synced or not) for local-first experience

      if !includeDismissed {
        query = query.filter(Column("isDismissed") == false)
      }

      if let category = category {
        query = query.filter(Column("category") == category)
      }

      query = Self.applyTierFilter(query, tiers: tiers)
      query = Self.applyRecordReadScope(
        query,
        scope: scope
      )

      // Tag filtering using JSON
      if let tags = tags, !tags.isEmpty {
        for tag in tags {
          // Use LIKE for JSON array contains check
          query = query.filter(Column("tagsJson").like("%\"\(tag)\"%"))
        }
      }

      let records =
        try query
        .order(Column("createdAt").desc)
        .limit(limit, offset: offset)
        .fetchAll(database)

      return records.compactMap { $0.toServerMemory() }
    }
  }

  /// Local rows whose backend create never landed, oldest first.
  ///
  /// A memory only reaches chat recall, the phone, and the knowledge graph once
  /// the backend has it, so a failed sync has to be retried rather than left as
  /// a permanently local row.
  func unsyncedLocalMemories(limit: Int) async throws -> [MemoryRecord] {
    guard limit > 0 else { return [] }
    let db = try await ensureInitialized()

    return try await db.read { database in
      try MemoryRecord
        .filter(Column("deleted") == false)
        .filter(Column("backendId") == nil)
        .order(Column("createdAt").asc)
        .limit(limit)
        .fetchAll(database)
    }
  }

  /// Read a bounded, newest-first snapshot of mirrored canonical candidates.
  ///
  /// The caller supplies the bound from its authoritative sync/list contract;
  /// this seam deliberately invents no client-side cap. One sentinel row
  /// detects local truncation. Even an exhausted local cache is marked
  /// non-authoritative because this storage actor does not persist a proof that
  /// the server's canonical ledger was exhaustively mirrored.
  func getCanonicalTriggerSnapshot(limit: Int) async throws -> MemoryLedgerTriggerSnapshot {
    guard limit > 0, limit < Int.max else {
      throw MemoryLedgerTriggerSnapshotError.invalidLimit(limit)
    }
    let db = try await ensureInitialized()
    let records = try await db.read { database in
      try MemoryRecord.fetchAll(
        database,
        sql: """
          SELECT * FROM memories
          WHERE backendId IS NOT NULL
            AND ledgerMetadataJson IS NOT NULL
            AND CASE
              WHEN json_valid(ledgerMetadataJson)
                THEN json_extract(ledgerMetadataJson, '$.kind') = 'trigger'
              ELSE instr(ledgerMetadataJson, '"kind":"trigger"') > 0
            END
          ORDER BY updatedAt DESC, backendId ASC
          LIMIT ?
          """,
        arguments: [limit + 1]
      )
    }

    let hasMoreLocalRows = records.count > limit
    let boundedRecords = Array(records.prefix(limit))
    let projection = KnowledgeLedgerTriggerCompiler.project(records: boundedRecords)
    let diagnostics = MemoryLedgerTriggerSnapshotDiagnostics(
      completeness: hasMoreLocalRows ? .localCacheTruncated : .localCacheExhausted,
      localRowCount: boundedRecords.count,
      hasMoreLocalRows: hasMoreLocalRows,
      isAuthoritative: false,
      quarantined: projection.quarantined
    )
    return MemoryLedgerTriggerSnapshot(projection: projection, diagnostics: diagnostics)
  }

  /// Get count of local memories
  func getLocalMemoriesCount(
    category: String? = nil,
    tags: [String]? = nil,
    tiers: [MemoryLayer]? = [.shortTerm, .longTerm],
    scope: MemoryRecordReadScope = .all,
    includeDismissed: Bool = false
  ) async throws -> Int {
    let db = try await ensureInitialized()

    return try await db.read { database in
      var query =
        MemoryRecord
        .filter(Column("deleted") == false)
      // Count ALL local memories (synced or not) for local-first experience

      if !includeDismissed {
        query = query.filter(Column("isDismissed") == false)
      }

      if let category = category {
        query = query.filter(Column("category") == category)
      }

      query = Self.applyTierFilter(query, tiers: tiers)
      query = Self.applyRecordReadScope(
        query,
        scope: scope
      )

      if let tags = tags, !tags.isEmpty {
        for tag in tags {
          query = query.filter(Column("tagsJson").like("%\"\(tag)\"%"))
        }
      }

      return try query.fetchCount(database)
    }
  }

  /// Fetch specific memories by their backend id.
  ///
  /// Deliberately unfiltered by tier, device scope, or dismissal: the caller
  /// already knows exactly which memories it wants because something else
  /// (a knowledge-graph edge, a citation) named them. Applying the list's
  /// browsing filters here would silently drop cited evidence and make it look
  /// like the memory does not exist.
  func getMemories(backendIds: [String]) async throws -> [ServerMemory] {
    let wanted = Array(Set(backendIds.filter { !$0.isEmpty }))
    guard !wanted.isEmpty else { return [] }
    let db = try await ensureInitialized()

    // SQLite caps host parameters per statement, and an entity in a large graph
    // can cite more ids than that, so read in chunks rather than one IN (...).
    let chunkSize = 400
    var found: [ServerMemory] = []
    for start in stride(from: 0, to: wanted.count, by: chunkSize) {
      let chunk = Array(wanted[start..<min(start + chunkSize, wanted.count)])
      let records = try await db.read { database in
        try MemoryRecord
          .filter(Column("deleted") == false)
          .filter(chunk.contains(Column("backendId")))
          .order(Column("createdAt").desc)
          .fetchAll(database)
      }
      found.append(contentsOf: records.compactMap { $0.toServerMemory() })
    }
    return found.sorted { $0.createdAt > $1.createdAt }
  }

  /// Get memories matching ANY of the specified tags (OR logic)
  /// Used for filter dropdowns where selecting multiple tags shows items matching any tag
  func getFilteredMemories(
    limit: Int = 200,
    offset: Int = 0,
    matchAnyTag: [String]? = nil,  // OR logic: matches any of these tags
    matchAnyCategory: [String]? = nil,  // OR logic: matches any of these categories
    excludeTags: [String]? = nil,  // Exclude memories containing these tags
    tiers: [MemoryLayer]? = [.shortTerm, .longTerm],
    scope: MemoryRecordReadScope = .all,
    includeDismissed: Bool = false
  ) async throws -> [ServerMemory] {
    let db = try await ensureInitialized()

    return try await db.read { database in
      // Build SQL for complex OR/AND logic
      var conditions: [String] = ["deleted = 0"]
      var arguments: [DatabaseValue] = []

      if !includeDismissed {
        conditions.append("isDismissed = 0")
      }

      Self.appendTierCondition(&conditions, &arguments, tiers: tiers)
      Self.appendRecordReadScopeCondition(&conditions, scope: scope)

      // Tag OR conditions
      if let tags = matchAnyTag, !tags.isEmpty {
        let tagConditions = tags.map { _ in "tagsJson LIKE ?" }.joined(separator: " OR ")
        conditions.append("(\(tagConditions))")
        for tag in tags {
          if let dbValue = DatabaseValue(value: "%\"\(tag)\"%") {
            arguments.append(dbValue)
          }
        }
      }

      // Category OR conditions
      if let categories = matchAnyCategory, !categories.isEmpty {
        let placeholders = categories.map { _ in "?" }.joined(separator: ", ")
        conditions.append("category IN (\(placeholders))")
        for cat in categories {
          if let dbValue = DatabaseValue(value: cat) {
            arguments.append(dbValue)
          }
        }
      }

      // Exclude tags
      if let excludeTags = excludeTags, !excludeTags.isEmpty {
        for tag in excludeTags {
          conditions.append("tagsJson NOT LIKE ?")
          if let dbValue = DatabaseValue(value: "%\"\(tag)\"%") {
            arguments.append(dbValue)
          }
        }
      }

      let sql = """
            SELECT * FROM memories
            WHERE \(conditions.joined(separator: " AND "))
            ORDER BY createdAt DESC
            LIMIT ? OFFSET ?
        """
      if let limitValue = DatabaseValue(value: limit) {
        arguments.append(limitValue)
      }
      if let offsetValue = DatabaseValue(value: offset) {
        arguments.append(offsetValue)
      }

      let records = try MemoryRecord.fetchAll(database, sql: sql, arguments: StatementArguments(arguments))
      return records.compactMap { $0.toServerMemory() }
    }
  }

  /// Search memories by content text (case-insensitive)
  /// Queries SQLite directly for efficient full-database search
  func searchLocalMemories(
    query searchText: String,
    limit: Int = 100,
    offset: Int = 0,
    category: String? = nil,
    tags: [String]? = nil,
    tiers: [MemoryLayer]? = [.shortTerm, .longTerm],
    scope: MemoryRecordReadScope = .all,
    includeDismissed: Bool = false
  ) async throws -> [ServerMemory] {
    let db = try await ensureInitialized()

    return try await db.read { database in
      var query =
        MemoryRecord
        .filter(Column("deleted") == false)

      if !includeDismissed {
        query = query.filter(Column("isDismissed") == false)
      }

      // Search in content (case-insensitive)
      if !searchText.isEmpty {
        query = query.filter(Column("content").like("%\(searchText)%"))
      }

      if let category = category {
        query = query.filter(Column("category") == category)
      }

      query = Self.applyTierFilter(query, tiers: tiers)
      query = Self.applyRecordReadScope(
        query,
        scope: scope
      )

      if let tags = tags, !tags.isEmpty {
        for tag in tags {
          query = query.filter(Column("tagsJson").like("%\"\(tag)\"%"))
        }
      }

      let records =
        try query
        .order(Column("createdAt").desc)
        .limit(limit, offset: offset)
        .fetchAll(database)

      return records.compactMap { $0.toServerMemory() }
    }
  }

  /// Get count of unread tips from SQLite
  func getUnreadTipsCount() async throws -> Int {
    let db = try await ensureInitialized()

    return try await db.read { database in
      let sql = """
            SELECT COUNT(*) FROM memories
            WHERE deleted = 0 AND isDismissed = 0
            AND tagsJson LIKE '%"tips"%'
            AND isRead = 0
        """
      return try Int.fetchOne(database, sql: sql) ?? 0
    }
  }

  /// Get count of memories matching search query
  func searchLocalMemoriesCount(
    query searchText: String,
    category: String? = nil,
    tags: [String]? = nil,
    tiers: [MemoryLayer]? = [.shortTerm, .longTerm],
    includeDismissed: Bool = false
  ) async throws -> Int {
    let db = try await ensureInitialized()

    return try await db.read { database in
      var query =
        MemoryRecord
        .filter(Column("deleted") == false)

      if !includeDismissed {
        query = query.filter(Column("isDismissed") == false)
      }

      if !searchText.isEmpty {
        query = query.filter(Column("content").like("%\(searchText)%"))
      }

      if let category = category {
        query = query.filter(Column("category") == category)
      }

      query = Self.applyTierFilter(query, tiers: tiers)

      if let tags = tags, !tags.isEmpty {
        for tag in tags {
          query = query.filter(Column("tagsJson").like("%\"\(tag)\"%"))
        }
      }

      return try query.fetchCount(database)
    }
  }

  /// Get a memory by local ID
  func getMemory(id: Int64) async throws -> MemoryRecord? {
    let db = try await ensureInitialized()

    return try await db.read { database in
      try MemoryRecord.fetchOne(database, key: id)
    }
  }

  /// Get a memory by backend ID
  func getMemoryByBackendId(_ backendId: String) async throws -> MemoryRecord? {
    let db = try await ensureInitialized()

    return try await db.read { database in
      try MemoryRecord
        .filter(Column("backendId") == backendId)
        .fetchOne(database)
    }
  }

  // MARK: - Bidirectional Sync Operations

  /// Sync a single ServerMemory to local storage (upsert)
  /// Used when fetching from API to cache locally
  @discardableResult
  func syncServerMemory(_ memory: ServerMemory) async throws -> Int64 {
    let db = try await ensureInitialized()

    return try await db.write { database -> Int64 in
      // Check if memory already exists by backendId
      if var existingRecord =
        try MemoryRecord
        .filter(Column("backendId") == memory.id)
        .fetchOne(database)
      {
        // Update existing record
        existingRecord.updateFrom(memory)
        try existingRecord.update(database)
        guard let recordId = existingRecord.id else {
          throw MemoryStorageError.syncFailed("Record ID is nil after update")
        }
        return recordId
      } else {
        // Insert new record, catching UNIQUE constraint from concurrent syncs
        do {
          let newRecord = try MemoryRecord.from(memory).inserted(database)
          guard let recordId = newRecord.id else {
            throw MemoryStorageError.syncFailed("Record ID is nil after insert")
          }
          return recordId
        } catch let dbError as DatabaseError where dbError.resultCode == .SQLITE_CONSTRAINT {
          // Race: another sync path already inserted this backendId — update instead
          if var record = try MemoryRecord.filter(Column("backendId") == memory.id).fetchOne(database) {
            record.updateFrom(memory)
            try record.update(database)
            return record.id ?? 0
          }
          throw dbError
        }
      }
    }
  }

  /// Sync multiple ServerMemory objects to local storage (batch upsert)
  /// Used for efficient background sync after API fetch
  func syncServerMemories(_ memories: [ServerMemory]) async throws {
    let db = try await ensureInitialized()

    let (skipped, adopted, inserted) = try await db.write { database -> (Int, Int, Int) in
      try Self.reconcileServerMemories(memories, in: database)
    }

    if skipped > 0 || adopted > 0 {
      log(
        "MemoryStorage: Synced \(memories.count - skipped) memories from backend (skipped \(skipped) newer local, adopted \(adopted) orphans)"
      )
    } else {
      log("MemoryStorage: Synced \(memories.count) memories from backend")
    }
    if inserted > 0 {
      HomeKnowledgeCountInvalidation.post()
    }
  }

  /// Upsert a server snapshot, then tombstone synced locals whose backendId is absent.
  /// Local-only rows (backendId NULL) are preserved. No-op when the snapshot is empty.
  @discardableResult
  func syncServerMemoriesAndPruneAbsent(
    _ memories: [ServerMemory],
    within scope: MemoryLayerScope
  ) async throws -> Int {
    try await syncServerMemories(memories)
    // An empty snapshot is authoritative, not a no-op: the sole caller
    // (refreshMemoriesAfterConversationCascade) exhaustively fetches the
    // whole backend. If the cascade delete removed every default-scope
    // memory, `memories` is empty and synced local rows must be tombstoned.
    // softDeleteSyncedOrphans only touches rows with a non-nil backendId,
    // so local-only (unsynced) rows are preserved even with an empty keep-set.
    return try await softDeleteSyncedOrphans(
      keepingBackendIds: Set(memories.map(\.id)),
      within: scope
    )
  }

  /// Cache an exhaustively fetched current canonical-ledger snapshot.
  ///
  /// Absence is authoritative only for the turn's in-memory prompt projection;
  /// it must never reuse the general `deleted` tombstone. Compatibility mode
  /// reads that tombstone as a real user/server deletion, so mutating it here
  /// would make flag-off, kill-switch, or stale-receipt rollback irreversible.
  @discardableResult
  func syncAuthoritativeKnowledgeLedgerSnapshot(
    _ memories: [ServerMemory],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> Int {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw KnowledgeLedgerMirrorSyncError.ownerChanged
    }
    let db = try await ensureInitialized()
    let inserted = try await db.write { database -> Int in
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
        throw KnowledgeLedgerMirrorSyncError.ownerChanged
      }
      let (_, _, inserted) = try Self.reconcileServerMemories(memories, in: database)
      // Throwing from this GRDB write closure rolls back every upsert above,
      // so an owner transition can never commit a prefix.
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
        throw KnowledgeLedgerMirrorSyncError.ownerChanged
      }
      return inserted
    }
    if inserted > 0 { HomeKnowledgeCountInvalidation.post() }
    return inserted
  }

  /// Atomically activates a complete, server-fenced mirror epoch. General
  /// memory-cache rows are only upserted; absence and privacy tombstones live
  /// in dedicated membership so compatibility rollback never loses history.
  @discardableResult
  func syncAuthoritativeKnowledgeLedgerMirror(
    _ snapshot: KnowledgeLedgerMirrorSnapshot,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KnowledgeLedgerMirrorReceipt {
    guard snapshot.ownerID == authorizationSnapshot.ownerID,
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    else { throw KnowledgeLedgerMirrorSyncError.ownerChanged }
    let db = try await ensureInitialized()
    let receipt = try await db.write { database in
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
        throw KnowledgeLedgerMirrorSyncError.ownerChanged
      }
      let result = try Self.reconcileAuthoritativeKnowledgeLedgerMirror(
        snapshot,
        in: database,
        now: Date())
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
        throw KnowledgeLedgerMirrorSyncError.ownerChanged
      }
      return result
    }
    HomeKnowledgeCountInvalidation.post()
    return receipt
  }

  /// Durably stages one signed cursor page. Partial chains survive process
  /// interruption but can never replace the active epoch; only a valid final
  /// page performs compatibility-cache reconciliation and activation.
  func stageAuthoritativeKnowledgeLedgerMirrorPage(
    _ page: KnowledgeLedgerMirrorPage,
    requestedCursor: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KnowledgeLedgerMirrorStageResult {
    guard page.ownerID == authorizationSnapshot.ownerID,
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    else { throw KnowledgeLedgerMirrorSyncError.ownerChanged }
    let db = try await ensureInitialized()
    let result = try await db.write { database in
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
        throw KnowledgeLedgerMirrorSyncError.ownerChanged
      }
      let result = try Self.stageAuthoritativeKnowledgeLedgerMirrorPage(
        page,
        requestedCursor: requestedCursor,
        in: database,
        now: Date())
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
        throw KnowledgeLedgerMirrorSyncError.ownerChanged
      }
      return result
    }
    if case .activated = result { HomeKnowledgeCountInvalidation.post() }
    return result
  }

  static func stageAuthoritativeKnowledgeLedgerMirrorPage(
    _ page: KnowledgeLedgerMirrorPage,
    requestedCursor: String?,
    in database: Database,
    now: Date
  ) throws -> KnowledgeLedgerMirrorStageResult {
    try validateKnowledgeLedgerMirrorPage(page)
    let ownerID = page.ownerID
    if requestedCursor == nil {
      try clearKnowledgeLedgerMirrorStaging(ownerID: ownerID, in: database)
      try database.execute(
        sql: """
          INSERT INTO jit_knowledge_ledger_mirror_staging_epochs
            (ownerID, accountGeneration, sourceGeneration, writerEpoch, headCommitID,
             commitSequence, epochID, expectedCursorHash, expectedCursor, contentRevision,
             chainRevision, scannedCount, projectedCount, pageCount, updatedAt)
          VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, '', '', 0, 0, 0, ?)
          """,
        arguments: [
          ownerID, page.accountGeneration, page.sourceGeneration, page.writerEpoch,
          page.headCommitID, page.commitSequence, page.epochID, now,
        ])
    }

    guard
      let state = try Row.fetchOne(
        database,
        sql: "SELECT * FROM jit_knowledge_ledger_mirror_staging_epochs WHERE ownerID = ?",
        arguments: [ownerID])
    else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
    let expectedCursorHash: String? = state["expectedCursorHash"]
    let actualCursorHash = requestedCursor.map(cursorDigest)
    guard expectedCursorHash == actualCursorHash,
      (state["accountGeneration"] as Int) == page.accountGeneration,
      (state["sourceGeneration"] as Int) == page.sourceGeneration,
      (state["writerEpoch"] as Int) == page.writerEpoch,
      (state["headCommitID"] as String) == page.headCommitID,
      (state["commitSequence"] as Int) == page.commitSequence,
      (state["epochID"] as String) == page.epochID
    else { throw KnowledgeLedgerMirrorSyncError.conflictingAuthority }

    let priorScanned: Int = state["scannedCount"]
    let priorProjected: Int = state["projectedCount"]
    guard page.scannedCount >= priorScanned,
      page.projectedCount >= priorProjected,
      page.projectedCount - priorProjected == page.rows.count,
      page.scannedCount - priorScanned >= page.rows.count
    else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }

    let encoder = JSONEncoder()
    for row in page.rows {
      guard
        try Int.fetchOne(
          database,
          sql: """
            SELECT COUNT(*) FROM jit_knowledge_ledger_mirror_staging_members
            WHERE ownerID = ? AND memoryID = ?
            """,
          arguments: [ownerID, row.memoryID]) == 0
      else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
      let encodedRecord: Data?
      if let memory = row.memory {
        encodedRecord = try encoder.encode(MemoryRecord.from(memory))
      } else {
        encodedRecord = nil
      }
      try database.execute(
        sql: """
          INSERT INTO jit_knowledge_ledger_mirror_staging_members
            (ownerID, epochID, memoryID, itemRevision, status, sourceState,
             canonicalMemoryID, contentPurged, memoryRecordJSON)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
          """,
        arguments: [
          ownerID, page.epochID, row.memoryID, row.itemRevision, row.status, row.sourceState,
          row.canonicalMemoryID, row.contentPurged, encodedRecord,
        ])
    }
    for alias in page.aliases {
      let priorTargets = try String.fetchAll(
        database,
        sql: """
          SELECT DISTINCT canonicalMemoryID FROM jit_knowledge_ledger_mirror_staging_aliases
          WHERE ownerID = ? AND aliasMemoryID = ?
          """,
        arguments: [ownerID, alias.aliasMemoryID])
      guard priorTargets.isEmpty || priorTargets == [alias.canonicalMemoryID] else {
        throw KnowledgeLedgerMirrorSyncError.invalidSnapshot
      }
      try database.execute(
        sql: """
          INSERT OR IGNORE INTO jit_knowledge_ledger_mirror_staging_aliases
            (ownerID, epochID, aliasMemoryID, canonicalMemoryID, sourceMemoryID, reason)
          VALUES (?, ?, ?, ?, ?, ?)
          """,
        arguments: [
          ownerID, page.epochID, alias.aliasMemoryID, alias.canonicalMemoryID,
          alias.sourceMemoryID, alias.reason,
        ])
    }

    let priorContentRevision: String = state["contentRevision"]
    let contentRevision = chainedPageRevision(
      prior: priorContentRevision,
      pageRevision: page.pageRevision)
    let nextCursorHash: String?
    if let nextCursor = page.nextCursor {
      let digest = cursorDigest(nextCursor)
      let seen =
        try Int.fetchOne(
          database,
          sql: """
            SELECT COUNT(*) FROM jit_knowledge_ledger_mirror_staging_cursors
            WHERE ownerID = ? AND cursorHash = ?
            """,
          arguments: [ownerID, digest]) ?? 0
      guard seen == 0 else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
      try database.execute(
        sql: """
          INSERT INTO jit_knowledge_ledger_mirror_staging_cursors (ownerID, cursorHash)
          VALUES (?, ?)
          """,
        arguments: [ownerID, digest])
      nextCursorHash = digest
    } else {
      nextCursorHash = nil
    }
    try database.execute(
      sql: """
        UPDATE jit_knowledge_ledger_mirror_staging_epochs SET
          expectedCursorHash = ?, expectedCursor = ?, contentRevision = ?, chainRevision = ?,
          scannedCount = ?, projectedCount = ?, pageCount = pageCount + 1, updatedAt = ?
        WHERE ownerID = ?
        """,
      arguments: [
        nextCursorHash, page.nextCursor, contentRevision, page.chainRevision, page.scannedCount,
        page.projectedCount, now, ownerID,
      ])

    guard page.finalPage else {
      guard let nextCursor = page.nextCursor else {
        throw KnowledgeLedgerMirrorSyncError.invalidSnapshot
      }
      return .next(nextCursor)
    }
    guard page.nextCursor == nil else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
    let receipt = try activateStagedKnowledgeLedgerMirror(
      ownerID: ownerID,
      page: page,
      contentRevision: contentRevision,
      in: database,
      now: now)
    try clearKnowledgeLedgerMirrorStaging(ownerID: ownerID, in: database)
    return .activated(receipt)
  }

  private static func activateStagedKnowledgeLedgerMirror(
    ownerID: String,
    page: KnowledgeLedgerMirrorPage,
    contentRevision: String,
    in database: Database,
    now: Date
  ) throws -> KnowledgeLedgerMirrorReceipt {
    let memberRows = try Row.fetchAll(
      database,
      sql: """
        SELECT * FROM jit_knowledge_ledger_mirror_staging_members
        WHERE ownerID = ? ORDER BY memoryID
        """,
      arguments: [ownerID])
    guard memberRows.count == page.projectedCount else {
      throw KnowledgeLedgerMirrorSyncError.invalidSnapshot
    }
    let decoder = JSONDecoder()
    let rows = try memberRows.map { row -> KnowledgeLedgerMirrorRow in
      let contentPurged: Bool = row["contentPurged"]
      let payload: Data? = row["memoryRecordJSON"]
      let memory: ServerMemory?
      if contentPurged {
        guard payload == nil else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
        memory = nil
      } else {
        guard let payload,
          let decoded = try? decoder.decode(MemoryRecord.self, from: payload),
          let restored = decoded.toServerMemory(),
          restored.id == (row["memoryID"] as String)
        else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
        memory = restored
      }
      return KnowledgeLedgerMirrorRow(
        memoryID: row["memoryID"],
        itemRevision: row["itemRevision"],
        status: row["status"],
        sourceState: row["sourceState"],
        canonicalMemoryID: row["canonicalMemoryID"],
        contentPurged: contentPurged,
        memory: memory)
    }
    let aliases = try Row.fetchAll(
      database,
      sql: """
        SELECT * FROM jit_knowledge_ledger_mirror_staging_aliases
        WHERE ownerID = ? ORDER BY aliasMemoryID, canonicalMemoryID, reason
        """,
      arguments: [ownerID]
    ).map { row in
      KnowledgeLedgerMirrorAlias(
        aliasMemoryID: row["aliasMemoryID"],
        canonicalMemoryID: row["canonicalMemoryID"],
        sourceMemoryID: row["sourceMemoryID"],
        reason: row["reason"])
    }
    try validateKnowledgeLedgerMirrorAliases(aliases, rowIDs: Set(rows.map(\.memoryID)))
    return try reconcileAuthoritativeKnowledgeLedgerMirror(
      KnowledgeLedgerMirrorSnapshot(
        ownerID: ownerID,
        accountGeneration: page.accountGeneration,
        sourceGeneration: page.sourceGeneration,
        writerEpoch: page.writerEpoch,
        headCommitID: page.headCommitID,
        commitSequence: page.commitSequence,
        epochID: page.epochID,
        contentRevision: contentRevision,
        chainRevision: page.chainRevision,
        scannedCount: page.scannedCount,
        projectedCount: page.projectedCount,
        rows: rows,
        aliases: aliases),
      in: database,
      now: now)
  }

  private static func validateKnowledgeLedgerMirrorPage(_ page: KnowledgeLedgerMirrorPage) throws {
    let statuses: Set<String> = ["active", "superseded", "hidden", "tombstoned"]
    let sourceStates: Set<String> = ["active", "missing", "tombstoned", "purged"]
    guard page.schemaVersion == KnowledgeLedgerMirrorSnapshot.schemaVersion,
      !page.ownerID.isEmpty,
      page.accountGeneration >= 0,
      page.sourceGeneration >= 0,
      page.writerEpoch >= 0,
      page.commitSequence >= 0,
      !page.headCommitID.isEmpty,
      isDigest(page.epochID), isDigest(page.pageRevision), isDigest(page.chainRevision),
      page.scannedCount >= 0, page.projectedCount >= 0,
      page.failureReason == nil,
      page.finalPage == (page.nextCursor == nil),
      page.nextCursor.map({ !$0.isEmpty && $0.count <= 2_048 }) ?? true,
      Set(page.rows.map(\.memoryID)).count == page.rows.count
    else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
    for row in page.rows {
      guard !row.memoryID.isEmpty, row.memoryID.count <= 256, !row.memoryID.contains("/"),
        row.itemRevision > 0, statuses.contains(row.status), sourceStates.contains(row.sourceState)
      else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
      if row.contentPurged {
        guard row.status == "tombstoned", ["tombstoned", "purged"].contains(row.sourceState),
          row.memory == nil
        else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
      } else {
        guard let memory = row.memory, memory.id == row.memoryID,
          memory.ledgerMetadata["ledger_schema_version"] == "knowledge_ledger.v1"
        else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
      }
    }
    for alias in page.aliases {
      guard !alias.aliasMemoryID.isEmpty, alias.aliasMemoryID.count <= 256,
        !alias.aliasMemoryID.contains("/"), !alias.canonicalMemoryID.isEmpty,
        alias.canonicalMemoryID.count <= 256, !alias.canonicalMemoryID.contains("/"),
        alias.sourceMemoryID == alias.aliasMemoryID,
        alias.aliasMemoryID != alias.canonicalMemoryID,
        alias.reason == "canonical_memory_id" || alias.reason == "superseded_by"
      else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
    }
  }

  private static func validateKnowledgeLedgerMirrorAliases(
    _ aliases: [KnowledgeLedgerMirrorAlias], rowIDs: Set<String>
  ) throws {
    var targets: [String: String] = [:]
    for alias in aliases {
      guard rowIDs.contains(alias.aliasMemoryID), rowIDs.contains(alias.canonicalMemoryID),
        targets[alias.aliasMemoryID].map({ $0 == alias.canonicalMemoryID }) ?? true
      else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
      targets[alias.aliasMemoryID] = alias.canonicalMemoryID
    }
    for start in targets.keys {
      var seen = Set<String>()
      var current: String? = start
      while let node = current, let next = targets[node] {
        guard seen.insert(node).inserted else {
          throw KnowledgeLedgerMirrorSyncError.invalidSnapshot
        }
        current = next
      }
    }
  }

  private static func clearKnowledgeLedgerMirrorStaging(ownerID: String, in database: Database) throws {
    for table in [
      "jit_knowledge_ledger_mirror_staging_members",
      "jit_knowledge_ledger_mirror_staging_aliases",
      "jit_knowledge_ledger_mirror_staging_cursors",
      "jit_knowledge_ledger_mirror_staging_epochs",
    ] {
      try database.execute(sql: "DELETE FROM \(table) WHERE ownerID = ?", arguments: [ownerID])
    }
  }

  func stagedKnowledgeLedgerMirrorCursor(ownerID: String) async throws -> String? {
    let db = try await ensureInitialized()
    return try await db.read { database in
      try String.fetchOne(
        database,
        sql: "SELECT expectedCursor FROM jit_knowledge_ledger_mirror_staging_epochs WHERE ownerID = ?",
        arguments: [ownerID])
    }
  }

  func stagedKnowledgeLedgerMirrorAuthority(ownerID: String) async throws
    -> KnowledgeLedgerMirrorAuthority?
  {
    let db = try await ensureInitialized()
    return try await db.read { database in
      guard
        let row = try Row.fetchOne(
          database,
          sql: """
            SELECT accountGeneration, sourceGeneration, writerEpoch, headCommitID,
                   commitSequence, epochID
            FROM jit_knowledge_ledger_mirror_staging_epochs WHERE ownerID = ?
            """,
          arguments: [ownerID])
      else { return nil }
      return KnowledgeLedgerMirrorAuthority(
        ownerID: ownerID,
        accountGeneration: row["accountGeneration"],
        sourceGeneration: row["sourceGeneration"],
        writerEpoch: row["writerEpoch"],
        headCommitID: row["headCommitID"],
        commitSequence: row["commitSequence"],
        epochID: row["epochID"])
    }
  }

  func authoritativeKnowledgeLedgerMirrorIsFresh(
    ownerID: String,
    accountGeneration: Int,
    headCommitID: String,
    commitSequence: Int
  ) async throws -> Bool {
    let db = try await ensureInitialized()
    return try await db.read { database in
      guard
        let row = try Row.fetchOne(
          database,
          sql: """
            SELECT accountGeneration, headCommitID, commitSequence
            FROM jit_knowledge_ledger_mirror_receipts WHERE ownerID = ?
            """,
          arguments: [ownerID])
      else { return false }
      return (row["accountGeneration"] as Int) == accountGeneration
        && (row["headCommitID"] as String) == headCommitID
        && (row["commitSequence"] as Int) == commitSequence
    }
  }

  func authoritativeKnowledgeLedgerMirrorReceipt(ownerID: String) async throws
    -> KnowledgeLedgerMirrorReceipt?
  {
    let db = try await ensureInitialized()
    return try await db.read { database in
      guard
        let row = try Row.fetchOne(
          database,
          sql: """
            SELECT accountGeneration, commitSequence, epochID, contentRevision, rowCount, aliasCount
            FROM jit_knowledge_ledger_mirror_receipts WHERE ownerID = ?
            """,
          arguments: [ownerID])
      else { return nil }
      return KnowledgeLedgerMirrorReceipt(
        ownerID: ownerID,
        accountGeneration: row["accountGeneration"],
        commitSequence: row["commitSequence"],
        epochID: row["epochID"],
        contentRevision: row["contentRevision"],
        rowCount: row["rowCount"],
        aliasCount: row["aliasCount"])
    }
  }

  /// Re-reads the active receipt's complete authority after activation. This
  /// is intentionally separate from the freshness fast path so callers can
  /// prove that the epoch they just activated is still the known server head.
  func authoritativeKnowledgeLedgerMirrorAuthority(ownerID: String) async throws
    -> KnowledgeLedgerMirrorAuthority?
  {
    let db = try await ensureInitialized()
    return try await db.read { database in
      guard
        let row = try Row.fetchOne(
          database,
          sql: """
            SELECT accountGeneration, sourceGeneration, writerEpoch, headCommitID,
                   commitSequence, epochID
            FROM jit_knowledge_ledger_mirror_receipts WHERE ownerID = ?
            """,
          arguments: [ownerID])
      else { return nil }
      return KnowledgeLedgerMirrorAuthority(
        ownerID: ownerID,
        accountGeneration: row["accountGeneration"],
        sourceGeneration: row["sourceGeneration"],
        writerEpoch: row["writerEpoch"],
        headCommitID: row["headCommitID"],
        commitSequence: row["commitSequence"],
        epochID: row["epochID"])
    }
  }

  func clearKnowledgeLedgerMirrorStaging(ownerID: String) async throws {
    let db = try await ensureInitialized()
    try await db.write { database in
      try Self.clearKnowledgeLedgerMirrorStaging(ownerID: ownerID, in: database)
    }
  }

  private static func cursorDigest(_ cursor: String) -> String {
    SHA256.hash(data: Data(cursor.utf8)).map { String(format: "%02x", $0) }.joined()
  }

  private static func chainedPageRevision(prior: String, pageRevision: String) -> String {
    let payload = prior.isEmpty ? pageRevision : "\(prior)\n\(pageRevision)"
    return SHA256.hash(data: Data(payload.utf8)).map { String(format: "%02x", $0) }.joined()
  }

  private static func isDigest(_ value: String) -> Bool {
    value.count == 64 && value.allSatisfy { $0.isHexDigit && !$0.isUppercase }
  }

  static func reconcileAuthoritativeKnowledgeLedgerMirror(
    _ snapshot: KnowledgeLedgerMirrorSnapshot,
    in database: Database,
    now: Date
  ) throws -> KnowledgeLedgerMirrorReceipt {
    guard !snapshot.ownerID.isEmpty,
      snapshot.accountGeneration >= 0,
      snapshot.sourceGeneration >= 0,
      snapshot.writerEpoch >= 0,
      snapshot.commitSequence >= 0,
      snapshot.epochID.count == 64,
      snapshot.contentRevision.count == 64,
      snapshot.chainRevision.count == 64,
      snapshot.projectedCount == snapshot.rows.count,
      snapshot.scannedCount >= snapshot.projectedCount
    else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }
    let uniqueRows = Set(snapshot.rows.map(\.memoryID))
    guard uniqueRows.count == snapshot.rows.count,
      snapshot.rows.allSatisfy({ row in
        !row.memoryID.isEmpty && row.itemRevision > 0
          && (row.contentPurged ? row.memory == nil : row.memory?.id == row.memoryID)
      })
    else { throw KnowledgeLedgerMirrorSyncError.invalidSnapshot }

    if let prior = try Row.fetchOne(
      database,
      sql: """
        SELECT accountGeneration, commitSequence, epochID, contentRevision, rowCount, aliasCount
        FROM jit_knowledge_ledger_mirror_receipts WHERE ownerID = ?
        """,
      arguments: [snapshot.ownerID])
    {
      let priorGeneration: Int = prior["accountGeneration"]
      let priorSequence: Int = prior["commitSequence"]
      let priorEpoch: String = prior["epochID"]
      let priorContentRevision: String = prior["contentRevision"]
      if snapshot.accountGeneration < priorGeneration
        || (snapshot.accountGeneration == priorGeneration && snapshot.commitSequence < priorSequence)
      {
        throw KnowledgeLedgerMirrorSyncError.staleAuthority
      }
      if snapshot.accountGeneration == priorGeneration, snapshot.commitSequence == priorSequence {
        guard snapshot.epochID == priorEpoch, snapshot.contentRevision == priorContentRevision else {
          throw KnowledgeLedgerMirrorSyncError.conflictingAuthority
        }
        return KnowledgeLedgerMirrorReceipt(
          ownerID: snapshot.ownerID,
          accountGeneration: snapshot.accountGeneration,
          commitSequence: snapshot.commitSequence,
          epochID: snapshot.epochID,
          contentRevision: snapshot.contentRevision,
          rowCount: prior["rowCount"],
          aliasCount: prior["aliasCount"])
      }
    }

    let purgedMemoryIDs = snapshot.rows.filter(\.contentPurged).map(\.memoryID)
    for memoryID in purgedMemoryIDs {
      // Explicit content deletion is stronger than the compatibility mirror:
      // remove the local row (including content and evidence) in this same
      // SQLite transaction. Merely absent legacy rows never enter this list.
      _ =
        try MemoryRecord
        .filter(Column("backendId") == memoryID)
        .deleteAll(database)
    }
    _ = try reconcileServerMemories(snapshot.rows.compactMap(\.memory), in: database)
    try database.execute(
      sql: "DELETE FROM jit_knowledge_ledger_mirror_members WHERE ownerID = ?",
      arguments: [snapshot.ownerID])
    try database.execute(
      sql: "DELETE FROM jit_knowledge_ledger_mirror_aliases WHERE ownerID = ?",
      arguments: [snapshot.ownerID])
    for row in snapshot.rows {
      try database.execute(
        sql: """
          INSERT INTO jit_knowledge_ledger_mirror_members
            (ownerID, memoryID, itemRevision, status, sourceState, canonicalMemoryID, contentPurged)
          VALUES (?, ?, ?, ?, ?, ?, ?)
          """,
        arguments: [
          snapshot.ownerID, row.memoryID, row.itemRevision, row.status, row.sourceState,
          row.canonicalMemoryID, row.contentPurged,
        ])
    }
    for alias in snapshot.aliases {
      guard uniqueRows.contains(alias.aliasMemoryID), uniqueRows.contains(alias.canonicalMemoryID) else {
        throw KnowledgeLedgerMirrorSyncError.invalidSnapshot
      }
      try database.execute(
        sql: """
          INSERT INTO jit_knowledge_ledger_mirror_aliases
            (ownerID, aliasMemoryID, canonicalMemoryID, sourceMemoryID, reason)
          VALUES (?, ?, ?, ?, ?)
          """,
        arguments: [
          snapshot.ownerID, alias.aliasMemoryID, alias.canonicalMemoryID, alias.sourceMemoryID,
          alias.reason,
        ])
    }
    try database.execute(
      sql: "DELETE FROM jit_knowledge_ledger_mirror_receipts WHERE ownerID != ?",
      arguments: [snapshot.ownerID])
    try database.execute(
      sql: """
        INSERT INTO jit_knowledge_ledger_mirror_receipts
          (ownerID, accountGeneration, sourceGeneration, writerEpoch, headCommitID, commitSequence,
           epochID, contentRevision, chainRevision, scannedCount, projectedCount, rowCount, aliasCount, updatedAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ownerID) DO UPDATE SET
          accountGeneration = excluded.accountGeneration,
          sourceGeneration = excluded.sourceGeneration,
          writerEpoch = excluded.writerEpoch,
          headCommitID = excluded.headCommitID,
          commitSequence = excluded.commitSequence,
          epochID = excluded.epochID,
          contentRevision = excluded.contentRevision,
          chainRevision = excluded.chainRevision,
          scannedCount = excluded.scannedCount,
          projectedCount = excluded.projectedCount,
          rowCount = excluded.rowCount,
          aliasCount = excluded.aliasCount,
          updatedAt = excluded.updatedAt
        """,
      arguments: [
        snapshot.ownerID, snapshot.accountGeneration, snapshot.sourceGeneration, snapshot.writerEpoch,
        snapshot.headCommitID, snapshot.commitSequence, snapshot.epochID, snapshot.contentRevision,
        snapshot.chainRevision, snapshot.scannedCount, snapshot.projectedCount, snapshot.rows.count,
        snapshot.aliases.count, now,
      ])
    return KnowledgeLedgerMirrorReceipt(
      ownerID: snapshot.ownerID,
      accountGeneration: snapshot.accountGeneration,
      commitSequence: snapshot.commitSequence,
      epochID: snapshot.epochID,
      contentRevision: snapshot.contentRevision,
      rowCount: snapshot.rows.count,
      aliasCount: snapshot.aliases.count)
  }

  func getAuthoritativeKnowledgeLedgerMirrorMembers(ownerID: String) async throws
    -> [KnowledgeLedgerMirrorMember]
  {
    let db = try await ensureInitialized()
    return try await db.read { database in
      try Row.fetchAll(
        database,
        sql: """
          SELECT memoryID, itemRevision, status, sourceState, canonicalMemoryID, contentPurged
          FROM jit_knowledge_ledger_mirror_members WHERE ownerID = ? ORDER BY memoryID
          """,
        arguments: [ownerID]
      ).map { row in
        KnowledgeLedgerMirrorMember(
          memoryID: row["memoryID"],
          itemRevision: row["itemRevision"],
          status: row["status"],
          sourceState: row["sourceState"],
          canonicalMemoryID: row["canonicalMemoryID"],
          contentPurged: row["contentPurged"])
      }
    }
  }

  private static func reconcileServerMemories(
    _ memories: [ServerMemory],
    in database: Database
  ) throws -> (skipped: Int, adopted: Int, inserted: Int) {
    var skipped = 0
    var adopted = 0
    var inserted = 0
    for memory in memories {
      if var existingRecord =
        try MemoryRecord
        .filter(Column("backendId") == memory.id)
        .fetchOne(database)
      {
        if existingRecord.updatedAt > memory.updatedAt {
          var authoritativeFieldsChanged = existingRecord.mergeAuthoritativeTierFrom(memory)
          if existingRecord.mergeAuthoritativeLedgerMetadataFrom(memory) {
            authoritativeFieldsChanged = true
          }
          if existingRecord.mergeAuthoritativeLedgerEvidenceFrom(memory) {
            authoritativeFieldsChanged = true
          }
          if authoritativeFieldsChanged { try existingRecord.update(database) }
          skipped += 1
          continue
        }
        existingRecord.updateFrom(memory)
        try existingRecord.update(database)
      } else if var orphan =
        try MemoryRecord
        .filter(Column("backendSynced") == false)
        .filter(Column("backendId") == nil)
        .filter(Column("content") == memory.content)
        .fetchOne(database)
      {
        orphan.backendId = memory.id
        orphan.backendSynced = true
        orphan.updateFrom(memory)
        try orphan.update(database)
        adopted += 1
      } else {
        do {
          _ = try MemoryRecord.from(memory).inserted(database)
          inserted += 1
        } catch let dbError as DatabaseError where dbError.resultCode == .SQLITE_CONSTRAINT {
          if var record = try MemoryRecord.filter(Column("backendId") == memory.id).fetchOne(database) {
            record.updateFrom(memory)
            try record.update(database)
          } else {
            throw dbError
          }
        }
      }
    }
    return (skipped, adopted, inserted)
  }

  // MARK: - Local Extraction Operations

  /// Insert a locally extracted memory (before backend sync)
  /// Used by MemoryAssistant and InsightAssistant
  @discardableResult
  func insertLocalMemory(_ record: MemoryRecord) async throws -> MemoryRecord {
    let db = try await ensureInitialized()

    var insertRecord = record
    insertRecord.backendSynced = false  // Mark as not yet synced

    let recordToInsert = insertRecord
    let inserted = try await db.write { database in
      try recordToInsert.inserted(database)
    }

    log("MemoryStorage: Inserted local memory (id: \(inserted.id ?? -1))")
    HomeKnowledgeCountInvalidation.post()
    return inserted
  }

  /// Mark a local memory as synced with backend ID
  func markSynced(id: Int64, backendId: String) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      guard let record = try MemoryRecord.fetchOne(database, key: id) else {
        throw MemoryStorageError.recordNotFound
      }

      // Check if another record already has this backendId
      // (race: syncServerMemories inserted it from an API fetch before we got here)
      if let existing =
        try MemoryRecord
        .filter(Column("backendId") == backendId)
        .fetchOne(database)
      {
        // Another record owns this backendId — delete our local duplicate
        if existing.id != record.id {
          try record.delete(database)
          return
        }
      }

      var mutableRecord = record
      mutableRecord.backendId = backendId
      mutableRecord.backendSynced = true
      try mutableRecord.update(database)
    }

    log("MemoryStorage: Marked memory \(id) as synced (backendId: \(backendId))")
  }

  /// Reconcile a known local capture with the authoritative create receipt.
  ///
  /// A local record has no product-tier authority before the server responds.
  /// Updating it from the receipt prevents a canonical Short-term item from
  /// being rendered as the local model's legacy Long-term default.
  func markSynced(id: Int64, serverMemory: ServerMemory) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      guard var record = try MemoryRecord.fetchOne(database, key: id) else {
        throw MemoryStorageError.recordNotFound
      }

      if let existing =
        try MemoryRecord
        .filter(Column("backendId") == serverMemory.id)
        .fetchOne(database),
        existing.id != record.id
      {
        try record.delete(database)
        return
      }

      record.backendId = serverMemory.id
      record.backendSynced = true
      record.updateFrom(serverMemory)
      try record.update(database)
    }

    log("MemoryStorage: Reconciled memory \(id) from authoritative create receipt (backendId: \(serverMemory.id))")
  }

  /// Get memories that haven't been synced to backend yet
  func getUnsyncedMemories() async throws -> [MemoryRecord] {
    let db = try await ensureInitialized()

    return try await db.read { database in
      try MemoryRecord
        .filter(Column("backendSynced") == false)
        .filter(Column("deleted") == false)
        .order(Column("createdAt").asc)
        .fetchAll(database)
    }
  }

  // MARK: - Update Operations

  /// Update memory read status
  func updateReadStatus(id: Int64, isRead: Bool) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      guard var record = try MemoryRecord.fetchOne(database, key: id) else {
        throw MemoryStorageError.recordNotFound
      }

      record.isRead = isRead
      record.updatedAt = Date()
      try record.update(database)
    }
  }

  /// Update memory dismissed status
  func updateDismissedStatus(id: Int64, isDismissed: Bool) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      guard var record = try MemoryRecord.fetchOne(database, key: id) else {
        throw MemoryStorageError.recordNotFound
      }

      record.isDismissed = isDismissed
      record.updatedAt = Date()
      try record.update(database)
    }
  }

  /// Mark memories as read within a tier scope.
  func markAllAsRead(scope: MemoryLayerScope) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      var conditions = ["isRead = 0"]
      var arguments: [DatabaseValue] = []
      guard let updatedAt = DatabaseValue(value: Date()) else { return }
      arguments.append(updatedAt)
      Self.appendTierCondition(&conditions, &arguments, tiers: scope.tiers)

      try database.execute(
        sql: "UPDATE memories SET isRead = 1, updatedAt = ? WHERE \(conditions.joined(separator: " AND "))",
        arguments: StatementArguments(arguments)
      )
    }

    log("MemoryStorage: Marked memories as read for scope \(scope.sqlTierRawValues)")
  }

  /// Soft delete a memory
  func deleteMemory(id: Int64) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      guard var record = try MemoryRecord.fetchOne(database, key: id) else {
        throw MemoryStorageError.recordNotFound
      }

      record.deleted = true
      record.updatedAt = Date()
      try record.update(database)
    }

    log("MemoryStorage: Soft deleted memory \(id)")
    HomeKnowledgeCountInvalidation.post()
  }

  /// Soft-delete synced memories tied to a deleted conversation (local cache hygiene).
  @discardableResult
  func softDeleteMemoriesByConversationId(_ conversationId: String) async throws -> Int {
    let db = try await ensureInitialized()

    let deleted = try await db.write { database -> Int in
      try database.execute(
        sql: "UPDATE memories SET deleted = 1, updatedAt = ? WHERE deleted = 0 AND conversationId = ?",
        arguments: [Date(), conversationId]
      )
      return database.changesCount
    }
    if deleted > 0 {
      HomeKnowledgeCountInvalidation.post()
    }
    return deleted
  }

  /// Soft delete a memory by backend ID
  func deleteMemoryByBackendId(_ backendId: String) async throws {
    try await deleteMemory(surfacedId: backendId)
  }

  /// Soft-delete a memory addressed by either a backend ID or a surfaced
  /// `local_<rowid>` placeholder.
  func deleteMemory(surfacedId: String) async throws {
    switch MemoryIdentity(surfacedId: surfacedId) {
    case .localRow(let rowId):
      try await deleteMemory(id: rowId)
    case .backend(let backendId):
      let db = try await ensureInitialized()

      try await db.write { database in
        try database.execute(
          sql: "UPDATE memories SET deleted = 1, updatedAt = ? WHERE backendId = ?",
          arguments: [Date(), backendId]
        )
      }

      log("MemoryStorage: Soft deleted memory with backendId \(backendId)")
      HomeKnowledgeCountInvalidation.post()
    }
  }

  /// Restore a soft-deleted memory addressed by either a backend ID or a
  /// surfaced `local_<rowid>` placeholder. Used by undo/delete-failure paths;
  /// callers must requery the active tier scope instead of appending directly
  /// to UI arrays.
  func restoreMemory(surfacedId: String) async throws {
    switch MemoryIdentity(surfacedId: surfacedId) {
    case .localRow(let rowId):
      let db = try await ensureInitialized()

      try await db.write { database in
        guard var record = try MemoryRecord.fetchOne(database, key: rowId) else {
          throw MemoryStorageError.recordNotFound
        }
        record.deleted = false
        record.updatedAt = Date()
        try record.update(database)
      }

      log("MemoryStorage: Restored local memory \(rowId)")
      HomeKnowledgeCountInvalidation.post()
    case .backend(let backendId):
      let db = try await ensureInitialized()

      try await db.write { database in
        try database.execute(
          sql: "UPDATE memories SET deleted = 0, updatedAt = ? WHERE backendId = ?",
          arguments: [Date(), backendId]
        )
      }

      log("MemoryStorage: Restored memory with backendId \(backendId)")
      HomeKnowledgeCountInvalidation.post()
    }
  }

  /// Restore a soft-deleted memory by backend ID. Kept for existing callers;
  /// surfaced local IDs are resolved by `restoreMemory(surfacedId:)` as well.
  func restoreMemoryByBackendId(_ backendId: String) async throws {
    try await restoreMemory(surfacedId: backendId)
  }

  /// Soft-delete synced memories whose backendId is no longer present on the
  /// backend. Used by the one-time cache reconcile to clear orphaned local rows
  /// that diverged from the authoritative backend (e.g. after the server-side
  /// category cleanup). Local-only unsynced memories (backendId NULL) are kept.
  @discardableResult
  func softDeleteSyncedOrphans(
    keepingBackendIds keep: Set<String>,
    within scope: MemoryLayerScope
  ) async throws -> Int {
    let db = try await ensureInitialized()

    let removed = try await db.write { database -> Int in
      var query =
        MemoryRecord
        .filter(Column("backendId") != nil)
        .filter(Column("deleted") == false)
      query = Self.applyTierFilter(query, tiers: scope.tiers)

      let candidates = try query.fetchAll(database)

      var removed = 0
      for var record in candidates {
        guard let backendId = record.backendId, !keep.contains(backendId) else { continue }
        record.deleted = true
        record.updatedAt = Date()
        try record.update(database)
        removed += 1
      }
      return removed
    }
    if removed > 0 {
      HomeKnowledgeCountInvalidation.post()
    }
    return removed
  }

  /// Soft delete memories within a tier scope.
  func deleteAllMemories(scope: MemoryLayerScope) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      var conditions = ["deleted = 0"]
      var arguments: [DatabaseValue] = []
      guard let updatedAt = DatabaseValue(value: Date()) else { return }
      arguments.append(updatedAt)
      Self.appendTierCondition(&conditions, &arguments, tiers: scope.tiers)

      try database.execute(
        sql: "UPDATE memories SET deleted = 1, updatedAt = ? WHERE \(conditions.joined(separator: " AND "))",
        arguments: StatementArguments(arguments)
      )
    }

    log("MemoryStorage: Soft deleted memories for scope \(scope.sqlTierRawValues)")
    HomeKnowledgeCountInvalidation.post()
  }

  /// Update content by backend ID
  func updateContentByBackendId(_ backendId: String, content: String) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      try database.execute(
        sql: "UPDATE memories SET content = ?, updatedAt = ? WHERE backendId = ?",
        arguments: [content, Date(), backendId]
      )
    }
  }

  /// Update visibility by backend ID
  func updateVisibilityByBackendId(_ backendId: String, visibility: String) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      try database.execute(
        sql: "UPDATE memories SET visibility = ?, updatedAt = ? WHERE backendId = ?",
        arguments: [visibility, Date(), backendId]
      )
    }
  }

  /// Update visibility for memories within a tier scope.
  func updateVisibility(scope: MemoryLayerScope, visibility: String) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      var conditions = ["deleted = 0"]
      var arguments: [DatabaseValue] = []
      guard
        let visibilityValue = DatabaseValue(value: visibility),
        let updatedAt = DatabaseValue(value: Date())
      else { return }
      arguments.append(visibilityValue)
      arguments.append(updatedAt)
      Self.appendTierCondition(&conditions, &arguments, tiers: scope.tiers)

      try database.execute(
        sql: "UPDATE memories SET visibility = ?, updatedAt = ? WHERE \(conditions.joined(separator: " AND "))",
        arguments: StatementArguments(arguments)
      )
    }
  }

  /// Update read status by backend ID
  func updateReadStatusByBackendId(_ backendId: String, isRead: Bool) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      try database.execute(
        sql: "UPDATE memories SET isRead = ?, updatedAt = ? WHERE backendId = ?",
        arguments: [isRead, Date(), backendId]
      )
    }
  }

  // MARK: - Stats

  /// Get memory storage statistics
  func getStats() async throws -> (total: Int, synced: Int, unsynced: Int, unread: Int) {
    let db = try await ensureInitialized()

    return try await db.read { database in
      let total =
        try MemoryRecord
        .filter(Column("deleted") == false)
        .fetchCount(database)

      let synced =
        try MemoryRecord
        .filter(Column("deleted") == false)
        .filter(Column("backendSynced") == true)
        .fetchCount(database)

      let unsynced =
        try MemoryRecord
        .filter(Column("deleted") == false)
        .filter(Column("backendSynced") == false)
        .fetchCount(database)

      let unread =
        try MemoryRecord
        .filter(Column("deleted") == false)
        .filter(Column("isRead") == false)
        .filter(Column("isDismissed") == false)
        .fetchCount(database)

      return (total, synced, unsynced, unread)
    }
  }

  // MARK: - Cleanup

  /// Permanently delete old dismissed memories
  func cleanupOldDismissedMemories(olderThan date: Date) async throws -> Int {
    let db = try await ensureInitialized()

    return try await db.write { database in
      let count =
        try Int.fetchOne(
          database,
          sql: "SELECT COUNT(*) FROM memories WHERE isDismissed = 1 AND updatedAt < ?",
          arguments: [date]
        ) ?? 0

      try database.execute(
        sql: "DELETE FROM memories WHERE isDismissed = 1 AND updatedAt < ?",
        arguments: [date]
      )

      return count
    }
  }
}
