import CryptoKit
import Foundation
@preconcurrency import GRDB

// Source metadata remains authoritative in its source table. Only screenshots are searchable today.
enum LocalEmbeddingSourceKind: String, Sendable {
  case screenshot
  case transcriptChunk = "transcript_chunk"
  case memory
}

struct LocalEmbeddingCandidate: Sendable {
  let sourceKind: LocalEmbeddingSourceKind
  let sourceId: Int64
  let capturedAt: Date
  let appName: String
  var vector: [Float] = []
}

struct LocalEmbeddingDocument: Sendable {
  let id: Int64
  let ocrText: String
  let appName: String
  let windowTitle: String?

  var text: String {
    OCREmbeddingService.formatForEmbedding(ocrText: ocrText, appName: appName, windowTitle: windowTitle)
  }
}

enum LocalEmbeddingStoreError: Error { case sourceChanged }

/// Bound to one owner's pool, never resolved again after an asynchronous embedding call.
struct LocalEmbeddingStore: Sendable {
  let pool: DatabasePool

  static func registerMigration(on migrator: inout DatabaseMigrator) {
    migrator.registerMigration("createLocalEmbeddings") { db in
      try db.execute(
        sql: """
          CREATE TABLE local_embeddings (
            sourceKind TEXT NOT NULL CHECK(sourceKind IN ('screenshot', 'transcript_chunk', 'memory')),
            sourceId INTEGER NOT NULL,
            modelId TEXT NOT NULL,
            dimension INTEGER NOT NULL CHECK(dimension > 0),
            textSha256 TEXT NOT NULL,
            vector BLOB NOT NULL CHECK(length(vector) = dimension * 4),
            createdAt DOUBLE NOT NULL,
            UNIQUE(sourceKind, sourceId, modelId)
          );
          CREATE INDEX local_embeddings_model ON local_embeddings(modelId, dimension, sourceKind, sourceId);
          CREATE TRIGGER local_embeddings_screenshot_delete AFTER DELETE ON screenshots BEGIN
            DELETE FROM local_embeddings WHERE sourceKind = 'screenshot' AND sourceId = old.id;
          END;
          CREATE TRIGGER local_embeddings_screenshot_text_update AFTER UPDATE OF ocrText, appName, windowTitle ON screenshots BEGIN
            DELETE FROM local_embeddings WHERE sourceKind = 'screenshot' AND sourceId = old.id;
          END;
          """)
    }
  }

  static func textHash(_ text: String) -> String {
    SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
  }

  func write(
    sourceKind: LocalEmbeddingSourceKind, sourceId: Int64, modelID: String,
    text: String, vector: [Float], authorization: LocalMutationAuthorization
  ) async throws {
    guard !modelID.isEmpty, LocalEmbeddingProbe.valid(vector, dimension: vector.count) else {
      throw LocalInferenceError.invalidResponse("invalid local vector shape")
    }
    let data = vector.withUnsafeBytes { Data($0) }
    try await authorization.withCommitLeaseSuppressingSupersededResult {
      try await pool.write { db in
        try authorization.require()
        if sourceKind == .screenshot {
          guard
            let row = try Row.fetchOne(
              db,
              sql: "SELECT id, ocrText, appName, windowTitle FROM screenshots WHERE id = ?", arguments: [sourceId]),
            let ocrText: String = row["ocrText"]
          else { throw LocalEmbeddingStoreError.sourceChanged }
          let current = LocalEmbeddingDocument(
            id: sourceId, ocrText: ocrText,
            appName: row["appName"], windowTitle: row["windowTitle"])
          guard current.text == text else { throw LocalEmbeddingStoreError.sourceChanged }
        }
        try db.execute(
          sql: """
            INSERT INTO local_embeddings(sourceKind, sourceId, modelId, dimension, textSha256, vector, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sourceKind, sourceId, modelId) DO UPDATE SET
              dimension = excluded.dimension, textSha256 = excluded.textSha256,
              vector = excluded.vector, createdAt = excluded.createdAt
            """,
          arguments: [
            sourceKind.rawValue, sourceId, modelID, vector.count, Self.textHash(text), data,
            Date().timeIntervalSince1970,
          ])
        try authorization.require()
      }
    }
  }

  func screenshotsNeedingEmbedding(modelID: String, olderThan cutoff: Date, limit: Int = 100) throws
    -> [LocalEmbeddingDocument]
  {
    try pool.read { db in
      try Row.fetchAll(
        db,
        sql: """
          WITH ranked AS (\(RewindDatabase.compactedScreenshotRankingSQL))
          SELECT id, ocrText, appName, windowTitle FROM ranked
          WHERE bucketRank = 1 AND NOT EXISTS (
            SELECT 1 FROM local_embeddings e WHERE e.sourceKind = 'screenshot'
              AND e.sourceId = ranked.id AND e.modelId = ?)
          ORDER BY id DESC LIMIT ?
          """, arguments: [Int64(cutoff.timeIntervalSince1970.rounded(.down)), modelID, max(0, min(limit, 500))]
      ).map { row in
        LocalEmbeddingDocument(
          id: row["id"], ocrText: row["ocrText"], appName: row["appName"], windowTitle: row["windowTitle"])
      }
    }
  }

  func keywordCandidates(query: String, startDate: Date?, endDate: Date?, appFilter: String?) throws
    -> [LocalEmbeddingCandidate]
  {
    let tokens = query.split(whereSeparator: { !$0.isLetter && !$0.isNumber }).prefix(64)
    guard !tokens.isEmpty else { return [] }
    let match = tokens.map { "\"\($0)\"" }.joined(separator: " AND ")
    return try pool.read { db in
      var sql = """
        SELECT s.id, s.timestamp, s.appName FROM screenshots s
        JOIN screenshots_fts ON s.id = screenshots_fts.rowid WHERE screenshots_fts MATCH ?
        """
      var args: [DatabaseValueConvertible] = [match]
      Self.filter(&sql, &args, startDate: startDate, endDate: endDate, appFilter: appFilter)
      sql += " ORDER BY bm25(screenshots_fts), s.timestamp DESC, s.id DESC LIMIT 50"
      return try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args)).map(Self.candidate)
    }
  }

  func readBatch(
    modelID: String, dimension: Int, startDate: Date?, endDate: Date?, appFilter: String?,
    limit: Int = 5000, offset: Int = 0
  ) throws -> [LocalEmbeddingCandidate] {
    try pool.read { db in
      var sql = """
        SELECT s.id, s.timestamp, s.appName, e.vector FROM local_embeddings e
        JOIN screenshots s ON e.sourceKind = 'screenshot' AND s.id = e.sourceId
        WHERE e.modelId = ? AND e.dimension = ?
        """
      var args: [DatabaseValueConvertible] = [modelID, dimension]
      Self.filter(&sql, &args, startDate: startDate, endDate: endDate, appFilter: appFilter)
      sql += " ORDER BY s.timestamp DESC, s.id DESC LIMIT ? OFFSET ?"
      args.append(max(0, min(limit, 5000)))
      args.append(max(0, offset))
      return try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args)).map { row in
        var value = Self.candidate(row)
        let data: Data = row["vector"]
        if data.count == dimension * MemoryLayout<Float>.size {
          value.vector = data.withUnsafeBytes { raw in
            (0..<dimension).map { raw.loadUnaligned(fromByteOffset: $0 * 4, as: Float.self) }
          }
        }
        return value
      }
    }
  }

  private static func candidate(_ row: Row) -> LocalEmbeddingCandidate {
    LocalEmbeddingCandidate(
      sourceKind: .screenshot, sourceId: row["id"], capturedAt: row["timestamp"], appName: row["appName"])
  }

  private static func filter(
    _ sql: inout String, _ args: inout [DatabaseValueConvertible],
    startDate: Date?, endDate: Date?, appFilter: String?
  ) {
    if let startDate {
      sql += " AND s.timestamp >= ?"
      args.append(startDate)
    }
    if let endDate {
      sql += " AND s.timestamp <= ?"
      args.append(endDate)
    }
    if let appFilter {
      sql += " AND s.appName = ?"
      args.append(appFilter)
    }
  }
}

extension RewindDatabase {
  func localEmbeddingStore(owner: RewindCaptureOwnerSnapshot) throws -> LocalEmbeddingStore {
    guard owner.isCurrent() else { throw LocalMutationAuthorizationError.revoked }
    guard let pool = getDatabaseQueue() else { throw RewindError.databaseNotInitialized }
    return LocalEmbeddingStore(pool: pool)
  }
}
