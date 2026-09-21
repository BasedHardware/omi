import Foundation
@preconcurrency import GRDB

struct RewindDatabasePoolSnapshot: @unchecked Sendable {
  let pool: DatabasePool?
  let generation: Int
}

struct RewindDatabasePoolSource: Sendable {
  let initialize: @Sendable () async throws -> Void
  let snapshot: @Sendable () async -> RewindDatabasePoolSnapshot

  static let shared = RewindDatabasePoolSource(
    initialize: {
      try await RewindDatabase.shared.initialize()
    },
    snapshot: {
      let snapshot = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
      return RewindDatabasePoolSnapshot(pool: snapshot.pool, generation: snapshot.generation)
    }
  )
}

/// Shared database lifecycle owner for actors backed by the Rewind database.
///
/// Domain repositories keep their queries and errors. This actor owns the
/// replaceable `DatabasePool` reference, validates its generation before every
/// hand-off, and reopens the database after an owner switch or recovery.
actor RewindRepository {
  private let owner: String
  private let source: RewindDatabasePoolSource
  private var cachedPool: DatabasePool?
  /// `nil` marks an explicitly injected pool. It remains valid until the owner
  /// invalidates it; the next acquisition then falls back to the shared source.
  private var cachedGeneration: Int?

  init(
    owner: String,
    source: RewindDatabasePoolSource = .shared,
    initialPool: DatabasePool? = nil
  ) {
    self.owner = owner
    self.source = source
    cachedPool = initialPool
    cachedGeneration = nil
  }

  func databasePool() async throws -> DatabasePool? {
    if let cachedPool {
      if cachedGeneration == nil {
        return cachedPool
      }

      let current = await source.snapshot()
      if current.generation == cachedGeneration, current.pool != nil {
        return cachedPool
      }
    }

    cachedPool = nil
    cachedGeneration = nil

    do {
      try await source.initialize()
    } catch {
      log("\(owner): Database initialization failed: \(error.localizedDescription)")
      throw error
    }

    let current = await source.snapshot()
    cachedPool = current.pool
    cachedGeneration = current.pool == nil ? nil : current.generation
    return current.pool
  }

  func invalidate() {
    cachedPool = nil
    cachedGeneration = nil
  }

  /// Rebuild one domain-owned FTS projection on the exact pool whose write
  /// failed. Durable source rows are never dropped or rewritten.
  func repairFTS(
    _ definition: RewindFTSDefinition,
    in databasePool: DatabasePool,
    reason: String
  ) async throws {
    try await databasePool.write { database in
      try definition.recreate(in: database)
    }
    log("\(owner): Rebuilt \(definition.virtualTable) after \(reason)")
  }
}

/// Definition of an external-content FTS5 projection and its repair contract.
/// Identifiers are code-owned constants; user input never reaches this type.
struct RewindFTSDefinition: Sendable {
  let virtualTable: String
  let contentTable: String
  let contentRowID: String
  let indexedColumns: [String]
  let tokenizer: String

  init(
    virtualTable: String,
    contentTable: String,
    contentRowID: String = "id",
    indexedColumns: [String],
    tokenizer: String = "unicode61"
  ) {
    let identifiers = [virtualTable, contentTable, contentRowID] + indexedColumns
    precondition(identifiers.allSatisfy(Self.isSafeIdentifier))
    precondition(!indexedColumns.isEmpty)
    precondition(!tokenizer.contains("'"))
    self.virtualTable = virtualTable
    self.contentTable = contentTable
    self.contentRowID = contentRowID
    self.indexedColumns = indexedColumns
    self.tokenizer = tokenizer
  }

  static let actionItems = RewindFTSDefinition(
    virtualTable: "action_items_fts",
    contentTable: "action_items",
    indexedColumns: ["description"]
  )

  /// Keep classification narrow so unrelated write or constraint failures are
  /// never hidden by a repair retry.
  func matchesRepairableError(_ error: Error) -> Bool {
    guard let databaseError = error as? DatabaseError else { return false }
    let message = "\(databaseError)".lowercased()
    guard message.contains(virtualTable.lowercased()) || message.contains("vtable constructor failed") else {
      return false
    }

    return databaseError.resultCode == .SQLITE_IOERR
      || databaseError.resultCode == .SQLITE_CORRUPT
      || message.contains("no such table")
      || message.contains("malformed")
      || message.contains("database disk image is malformed")
      || databaseError.extendedResultCode.rawValue == 6922
  }

  func install(in database: Database, populateExistingRows: Bool) throws {
    let columnDefinitions = indexedColumns.joined(separator: ",\n    ")
    try database.execute(
      sql: """
        CREATE VIRTUAL TABLE \(virtualTable) USING fts5(
            \(columnDefinitions),
            content='\(contentTable)',
            content_rowid='\(contentRowID)',
            tokenize='\(tokenizer)'
        )
        """)

    let insertColumns = (["rowid"] + indexedColumns).joined(separator: ", ")
    let newValues = (["new.\(contentRowID)"] + indexedColumns.map { "new.\($0)" }).joined(separator: ", ")
    let oldValues = (["old.\(contentRowID)"] + indexedColumns.map { "old.\($0)" }).joined(separator: ", ")

    try database.execute(
      sql: """
        CREATE TRIGGER \(virtualTable)_ai AFTER INSERT ON \(contentTable) BEGIN
            INSERT INTO \(virtualTable)(\(insertColumns))
            VALUES (\(newValues));
        END
        """)

    try database.execute(
      sql: """
        CREATE TRIGGER \(virtualTable)_ad AFTER DELETE ON \(contentTable) BEGIN
            INSERT INTO \(virtualTable)(\(virtualTable), \(insertColumns))
            VALUES ('delete', \(oldValues));
        END
        """)

    try database.execute(
      sql: """
        CREATE TRIGGER \(virtualTable)_au AFTER UPDATE ON \(contentTable) BEGIN
            INSERT INTO \(virtualTable)(\(virtualTable), \(insertColumns))
            VALUES ('delete', \(oldValues));
            INSERT INTO \(virtualTable)(\(insertColumns))
            VALUES (\(newValues));
        END
        """)

    guard populateExistingRows else { return }
    let sourceColumns = ([contentRowID] + indexedColumns).joined(separator: ", ")
    try database.execute(
      sql: """
        INSERT INTO \(virtualTable)(\(insertColumns))
        SELECT \(sourceColumns) FROM \(contentTable)
        """)
  }

  func recreate(in database: Database) throws {
    try dropIfPresent(in: database)
    try install(in: database, populateExistingRows: true)
  }

  private func dropIfPresent(in database: Database) throws {
    try database.execute(sql: "DROP TRIGGER IF EXISTS \(virtualTable)_ai")
    try database.execute(sql: "DROP TRIGGER IF EXISTS \(virtualTable)_ad")
    try database.execute(sql: "DROP TRIGGER IF EXISTS \(virtualTable)_au")

    do {
      try database.execute(sql: "DROP TABLE IF EXISTS \(virtualTable)")
    } catch {
      for suffix in ["data", "idx", "content", "docsize", "config"] {
        try database.execute(sql: "DROP TABLE IF EXISTS \(virtualTable)_\(suffix)")
      }
      try database.execute(sql: "DROP TABLE IF EXISTS \(virtualTable)")
    }
  }

  private static func isSafeIdentifier(_ value: String) -> Bool {
    guard let first = value.unicodeScalars.first,
      CharacterSet.letters.union(CharacterSet(charactersIn: "_")).contains(first)
    else { return false }
    return value.unicodeScalars.dropFirst().allSatisfy {
      CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_")).contains($0)
    }
  }
}
