import CryptoKit
import Foundation
@preconcurrency import GRDB

// Source metadata remains authoritative in its source table.
// Hybrid search filters by sourceKind so screen search never mixes in transcripts or memories.
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
    migrator.registerMigration("createTranscriptChunksAndMemoriesFTS") { db in
      if try db.tableExists("transcription_sessions") == false {
        try db.create(table: "transcription_sessions") { t in
          t.autoIncrementedPrimaryKey("id")
        }
      }
      if try db.tableExists("memories") == false {
        try db.create(table: "memories") { t in
          t.autoIncrementedPrimaryKey("id")
          t.column("content", .text).notNull().defaults(to: "")
          t.column("deleted", .boolean).notNull().defaults(to: false)
          t.column("createdAt", .datetime).notNull().defaults(sql: "CURRENT_TIMESTAMP")
          t.column("sourceApp", .text)
        }
      }
      try db.execute(
        sql: """
          CREATE TABLE transcript_chunks (
            id INTEGER PRIMARY KEY,
            sessionId INTEGER NOT NULL REFERENCES transcription_sessions(id) ON DELETE CASCADE,
            chunkIndex INTEGER NOT NULL,
            text TEXT NOT NULL,
            textSha256 TEXT NOT NULL,
            startedAt DATETIME NOT NULL,
            sourceSegmentCount INTEGER NOT NULL DEFAULT 0,
            sourceMaxSegmentId INTEGER NOT NULL DEFAULT 0,
            UNIQUE(sessionId, chunkIndex)
          );
          CREATE INDEX transcript_chunks_session ON transcript_chunks(sessionId, chunkIndex);
          CREATE VIRTUAL TABLE transcript_chunks_fts USING fts5(
            text, content='transcript_chunks', content_rowid='id'
          );
          CREATE TRIGGER transcript_chunks_ai AFTER INSERT ON transcript_chunks BEGIN
            INSERT INTO transcript_chunks_fts(rowid, text) VALUES (new.id, new.text);
          END;
          CREATE TRIGGER transcript_chunks_ad AFTER DELETE ON transcript_chunks BEGIN
            INSERT INTO transcript_chunks_fts(transcript_chunks_fts, rowid, text)
            VALUES ('delete', old.id, old.text);
          END;
          CREATE TRIGGER transcript_chunks_au AFTER UPDATE OF text ON transcript_chunks BEGIN
            INSERT INTO transcript_chunks_fts(transcript_chunks_fts, rowid, text)
            VALUES ('delete', old.id, old.text);
            INSERT INTO transcript_chunks_fts(rowid, text) VALUES (new.id, new.text);
          END;
          CREATE TRIGGER local_embeddings_transcript_delete AFTER DELETE ON transcript_chunks BEGIN
            DELETE FROM local_embeddings WHERE sourceKind = 'transcript_chunk' AND sourceId = old.id;
          END;
          CREATE TRIGGER local_embeddings_transcript_text_update AFTER UPDATE OF text, textSha256 ON transcript_chunks BEGIN
            DELETE FROM local_embeddings WHERE sourceKind = 'transcript_chunk' AND sourceId = old.id;
          END;
          CREATE VIRTUAL TABLE memories_fts USING fts5(
            content, content='memories', content_rowid='id'
          );
          CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
          END;
          CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
          END;
          CREATE TRIGGER memories_au AFTER UPDATE OF content ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
            INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
          END;
          CREATE TRIGGER local_embeddings_memory_delete AFTER DELETE ON memories BEGIN
            DELETE FROM local_embeddings WHERE sourceKind = 'memory' AND sourceId = old.id;
          END;
          CREATE TRIGGER local_embeddings_memory_text_update AFTER UPDATE OF content ON memories
          WHEN old.content IS NOT new.content
          BEGIN
            DELETE FROM local_embeddings WHERE sourceKind = 'memory' AND sourceId = old.id;
          END;
          INSERT INTO memories_fts(memories_fts) VALUES('rebuild');
          """)
    }
  }

  static func textHash(_ text: String) -> String {
    SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
  }

  func write(
    sourceKind: LocalEmbeddingSourceKind, sourceId: Int64, modelID: String,
    text: String, vector: [Float], dimension: Int, authorization: LocalMutationAuthorization
  ) async throws {
    guard !modelID.isEmpty, LocalEmbeddingProbe.valid(vector, dimension: dimension) else {
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
        } else if sourceKind == .transcriptChunk {
          guard
            let current = try String.fetchOne(
              db, sql: "SELECT text FROM transcript_chunks WHERE id = ?", arguments: [sourceId]),
            current == text
          else { throw LocalEmbeddingStoreError.sourceChanged }
        } else if sourceKind == .memory {
          guard
            let current = try String.fetchOne(
              db, sql: "SELECT content FROM memories WHERE id = ? AND COALESCE(deleted, 0) = 0", arguments: [sourceId]
            ),
            current == text
          else { throw LocalEmbeddingStoreError.sourceChanged }
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
            sourceKind.rawValue, sourceId, modelID, dimension, Self.textHash(text), data,
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

  func keywordCandidates(
    query: String, startDate: Date?, endDate: Date?, appFilter: String?,
    sourceKinds: Set<LocalEmbeddingSourceKind> = [.screenshot]
  ) throws -> [LocalEmbeddingCandidate] {
    let tokens = query.split(whereSeparator: { !$0.isLetter && !$0.isNumber }).prefix(64)
    guard !tokens.isEmpty, !sourceKinds.isEmpty else { return [] }
    let match = tokens.map { "\"\($0)\"" }.joined(separator: " AND ")
    var candidates: [LocalEmbeddingCandidate] = []
    try pool.read { db in
      if sourceKinds.contains(.screenshot) {
        var sql = """
          SELECT s.id, s.timestamp, s.appName FROM screenshots s
          JOIN screenshots_fts ON s.id = screenshots_fts.rowid WHERE screenshots_fts MATCH ?
          """
        var args: [DatabaseValueConvertible] = [match]
        Self.filter(
          &sql, &args, alias: "s", timestamp: "timestamp", app: "appName", startDate: startDate, endDate: endDate,
          appFilter: appFilter)
        sql += " ORDER BY bm25(screenshots_fts), s.timestamp DESC, s.id DESC LIMIT 50"
        candidates.append(
          contentsOf: try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args)).map {
            Self.candidate($0, kind: .screenshot)
          })
      }
      if sourceKinds.contains(.transcriptChunk) {
        var sql = """
          SELECT t.id, t.startedAt AS timestamp, 'Transcript' AS appName FROM transcript_chunks t
          JOIN transcript_chunks_fts ON t.id = transcript_chunks_fts.rowid WHERE transcript_chunks_fts MATCH ?
          """
        var args: [DatabaseValueConvertible] = [match]
        Self.filter(
          &sql, &args, alias: "t", timestamp: "startedAt", app: nil, startDate: startDate, endDate: endDate,
          appFilter: nil)
        sql += " ORDER BY bm25(transcript_chunks_fts), t.startedAt DESC, t.id DESC LIMIT 50"
        candidates.append(
          contentsOf: try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args)).map {
            Self.candidate($0, kind: .transcriptChunk)
          })
      }
      if sourceKinds.contains(.memory) {
        var sql = """
          SELECT m.id, m.createdAt AS timestamp, COALESCE(m.sourceApp, 'Memory') AS appName FROM memories m
          JOIN memories_fts ON m.id = memories_fts.rowid
          WHERE COALESCE(m.deleted, 0) = 0 AND memories_fts MATCH ?
          """
        var args: [DatabaseValueConvertible] = [match]
        Self.filter(
          &sql, &args, alias: "m", timestamp: "createdAt", app: "sourceApp", startDate: startDate, endDate: endDate,
          appFilter: appFilter)
        sql += " ORDER BY bm25(memories_fts), m.createdAt DESC, m.id DESC LIMIT 50"
        candidates.append(
          contentsOf: try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args)).map {
            Self.candidate($0, kind: .memory)
          })
      }
    }
    return Array(candidates.prefix(50))
  }

  func readBatch(
    modelID: String, dimension: Int, startDate: Date?, endDate: Date?, appFilter: String?,
    limit: Int = 5000, offset: Int = 0, sourceKinds: Set<LocalEmbeddingSourceKind> = [.screenshot]
  ) throws -> [LocalEmbeddingCandidate] {
    guard !sourceKinds.isEmpty else { return [] }
    return try pool.read { db in
      var parts: [String] = []
      var args: [DatabaseValueConvertible] = []
      if sourceKinds.contains(.screenshot) {
        var sql = """
          SELECT s.id, s.timestamp, s.appName, e.vector, e.sourceKind FROM local_embeddings e
          JOIN screenshots s ON e.sourceKind = 'screenshot' AND s.id = e.sourceId
          WHERE e.modelId = ? AND e.dimension = ?
          """
        args.append(modelID)
        args.append(dimension)
        Self.filter(
          &sql, &args, alias: "s", timestamp: "timestamp", app: "appName", startDate: startDate, endDate: endDate,
          appFilter: appFilter)
        parts.append(sql)
      }
      if sourceKinds.contains(.transcriptChunk) {
        var sql = """
          SELECT t.id, t.startedAt AS timestamp, 'Transcript' AS appName, e.vector, e.sourceKind FROM local_embeddings e
          JOIN transcript_chunks t ON e.sourceKind = 'transcript_chunk' AND t.id = e.sourceId
          WHERE e.modelId = ? AND e.dimension = ?
          """
        args.append(modelID)
        args.append(dimension)
        Self.filter(
          &sql, &args, alias: "t", timestamp: "startedAt", app: nil, startDate: startDate, endDate: endDate,
          appFilter: nil)
        parts.append(sql)
      }
      if sourceKinds.contains(.memory) {
        var sql = """
          SELECT m.id, m.createdAt AS timestamp, COALESCE(m.sourceApp, 'Memory') AS appName, e.vector, e.sourceKind
          FROM local_embeddings e
          JOIN memories m ON e.sourceKind = 'memory' AND m.id = e.sourceId
          WHERE e.modelId = ? AND e.dimension = ? AND COALESCE(m.deleted, 0) = 0
          """
        args.append(modelID)
        args.append(dimension)
        Self.filter(
          &sql, &args, alias: "m", timestamp: "createdAt", app: "sourceApp", startDate: startDate, endDate: endDate,
          appFilter: appFilter)
        parts.append(sql)
      }
      guard !parts.isEmpty else { return [] }
      let sql =
        parts.map { "SELECT * FROM (\( $0 ))" }.joined(separator: " UNION ALL ")
        + " ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?"
      args.append(max(0, min(limit, 5000)))
      args.append(max(0, offset))
      return try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args)).map { row in
        let kind = LocalEmbeddingSourceKind(rawValue: row["sourceKind"]) ?? .screenshot
        var value = Self.candidate(row, kind: kind)
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

  func upsertTranscriptChunks(_ chunks: [TranscriptChunkRecord], authorization: LocalMutationAuthorization)
    async throws -> [TranscriptChunkRecord]
  {
    try await authorization.withCommitLeaseSuppressingSupersededResult {
      try await pool.write { db in
        try authorization.require()
        let stored = try Self.insertTranscriptChunks(chunks, db: db)
        try authorization.require()
        return stored
      }
    }
  }

  func replaceTranscriptChunks(
    sessionId: Int64, chunks: [TranscriptChunkRecord], authorization: LocalMutationAuthorization
  ) async throws -> [TranscriptChunkRecord] {
    try await authorization.withCommitLeaseSuppressingSupersededResult {
      try await pool.write { db in
        try authorization.require()
        try db.execute(sql: "DELETE FROM transcript_chunks WHERE sessionId = ?", arguments: [sessionId])
        let stored = try Self.insertTranscriptChunks(chunks, db: db)
        try authorization.require()
        return stored
      }
    }
  }

  func transcriptChunkPreviews(ids: [Int64], limit: Int = 50) throws -> [Int64: (text: String, startedAt: Date)] {
    let bounded = Array(ids.prefix(max(0, min(limit, 50))))
    guard !bounded.isEmpty else { return [:] }
    return try pool.read { db in
      var previews: [Int64: (text: String, startedAt: Date)] = [:]
      let placeholders = bounded.map { _ in "?" }.joined(separator: ",")
      let rows = try Row.fetchAll(
        db,
        sql: "SELECT id, text, startedAt FROM transcript_chunks WHERE id IN (\(placeholders))",
        arguments: StatementArguments(bounded))
      for row in rows {
        let id: Int64 = row["id"]
        let text: String = row["text"]
        let startedAt: Date = row["startedAt"]
        previews[id] = (text, startedAt)
      }
      return previews
    }
  }

  func sessionsNeedingTranscriptChunks(limit: Int = 20) throws -> [Int64] {
    try pool.read { db in
      let bound = max(0, min(limit, 50))
      var needed: [Int64] = []
      var seen = Set<Int64>()
      func appendUnique(_ ids: [Int64]) {
        for id in ids where seen.insert(id).inserted {
          needed.append(id)
        }
      }
      let hasSegments = try db.tableExists("transcription_segments")
      let hasStatus = try db.columns(in: "transcription_sessions").contains { $0.name == "status" }
      if hasSegments {
        let completed =
          hasStatus
          ? "AND s.status = 'completed'\n            "
          : ""
        let unchunked = try Int64.fetchAll(
          db,
          sql: """
            SELECT s.id FROM transcription_sessions s
            WHERE EXISTS (SELECT 1 FROM transcription_segments g WHERE g.sessionId = s.id)
              AND NOT EXISTS (SELECT 1 FROM transcript_chunks c WHERE c.sessionId = s.id)
              \(completed)
            ORDER BY s.id DESC LIMIT ?
            """,
          arguments: [bound])
        appendUnique(unchunked)
      }
      let hasFingerprint = try db.columns(in: "transcript_chunks").contains {
        $0.name == "sourceSegmentCount"
      }
      if hasSegments {
        let completedPred = hasStatus ? "s.status = 'completed' AND " : ""
        let mismatch: String
        if hasFingerprint {
          mismatch = """
            (
                NOT EXISTS (SELECT 1 FROM transcription_segments g WHERE g.sessionId = s.id)
                OR (SELECT COUNT(*) FROM transcription_segments g WHERE g.sessionId = s.id)
                   != (SELECT c.sourceSegmentCount FROM transcript_chunks c WHERE c.sessionId = s.id LIMIT 1)
                OR COALESCE((SELECT MAX(g.id) FROM transcription_segments g WHERE g.sessionId = s.id), 0)
                   != (SELECT c.sourceMaxSegmentId FROM transcript_chunks c WHERE c.sessionId = s.id LIMIT 1)
              )
            """
        } else {
          mismatch = "NOT EXISTS (SELECT 1 FROM transcription_segments g WHERE g.sessionId = s.id)"
        }
        let stale = try Int64.fetchAll(
          db,
          sql: """
            SELECT s.id FROM transcription_sessions s
            WHERE \(completedPred)EXISTS (SELECT 1 FROM transcript_chunks c WHERE c.sessionId = s.id)
              AND \(mismatch)
            ORDER BY s.id DESC LIMIT ?
            """,
          arguments: [bound])
        for id in stale where seen.insert(id).inserted {
          if try Self.sessionChunksNeedRewrite(sessionId: id, db: db) {
            needed.append(id)
          }
        }
      }
      return needed
    }
  }

  func filterNeedingEmbedding(
    items: [(Int64, String)], sourceKind: LocalEmbeddingSourceKind, modelID: String
  ) throws -> [(Int64, String)] {
    guard !items.isEmpty, !modelID.isEmpty else { return [] }
    return try pool.read { db in
      var storedHash: [Int64: String] = [:]
      var uniqueIds: [Int64] = []
      var seen = Set<Int64>()
      for item in items where seen.insert(item.0).inserted {
        uniqueIds.append(item.0)
      }
      for start in stride(from: 0, to: uniqueIds.count, by: 400) {
        let slice = Array(uniqueIds[start..<min(start + 400, uniqueIds.count)])
        let placeholders = slice.map { _ in "?" }.joined(separator: ",")
        var args: [DatabaseValueConvertible] = [sourceKind.rawValue, modelID]
        args.append(contentsOf: slice)
        let rows = try Row.fetchAll(
          db,
          sql: """
            SELECT sourceId, textSha256 FROM local_embeddings
            WHERE sourceKind = ? AND modelId = ? AND sourceId IN (\(placeholders))
            """,
          arguments: StatementArguments(args))
        for row in rows {
          storedHash[row["sourceId"]] = row["textSha256"]
        }
      }
      return items.filter { storedHash[$0.0] != Self.textHash($0.1) }
    }
  }

  func memoriesNeedingEmbedding(modelID: String, limit: Int = 100) throws -> [(id: Int64, content: String)] {
    try pool.read { db in
      try Row.fetchAll(
        db,
        sql: """
          SELECT id, content FROM memories
          WHERE COALESCE(deleted, 0) = 0 AND LENGTH(content) > 0 AND NOT EXISTS (
            SELECT 1 FROM local_embeddings e WHERE e.sourceKind = 'memory'
              AND e.sourceId = memories.id AND e.modelId = ?)
          ORDER BY id DESC LIMIT ?
          """,
        arguments: [modelID, max(0, min(limit, 200))]
      ).compactMap { row in
        guard let id: Int64 = row["id"], let content: String = row["content"] else { return nil }
        return (id, content)
      }
    }
  }

  func transcriptChunksNeedingEmbedding(modelID: String, limit: Int = 100) throws -> [TranscriptChunkRecord] {
    try pool.read { db in
      try Row.fetchAll(
        db,
        sql: """
          SELECT id, sessionId, chunkIndex, text, textSha256, startedAt FROM transcript_chunks
          WHERE NOT EXISTS (
            SELECT 1 FROM local_embeddings e WHERE e.sourceKind = 'transcript_chunk'
              AND e.sourceId = transcript_chunks.id AND e.modelId = ?)
          ORDER BY id DESC LIMIT ?
          """,
        arguments: [modelID, max(0, min(limit, 200))]
      ).map {
        TranscriptChunkRecord(
          id: $0["id"], sessionId: $0["sessionId"], chunkIndex: $0["chunkIndex"],
          text: $0["text"], textSha256: $0["textSha256"], startedAt: $0["startedAt"])
      }
    }
  }

  private static func insertTranscriptChunks(_ chunks: [TranscriptChunkRecord], db: Database) throws
    -> [TranscriptChunkRecord]
  {
    var stored: [TranscriptChunkRecord] = []
    stored.reserveCapacity(chunks.count)
    var fingerprintBySession: [Int64: (count: Int, maxId: Int64)] = [:]
    for chunk in chunks {
      let fingerprint: (count: Int, maxId: Int64)
      if let cached = fingerprintBySession[chunk.sessionId] {
        fingerprint = cached
      } else {
        let computed = try Self.segmentSourceFingerprint(sessionId: chunk.sessionId, db: db)
        fingerprintBySession[chunk.sessionId] = computed
        fingerprint = computed
      }
      try db.execute(
        sql: """
          INSERT INTO transcript_chunks(
            sessionId, chunkIndex, text, textSha256, startedAt, sourceSegmentCount, sourceMaxSegmentId)
          VALUES (?, ?, ?, ?, ?, ?, ?)
          """,
        arguments: [
          chunk.sessionId, chunk.chunkIndex, chunk.text, chunk.textSha256, chunk.startedAt,
          fingerprint.count, fingerprint.maxId,
        ])
      let id = try Int64.fetchOne(
        db,
        sql: "SELECT id FROM transcript_chunks WHERE sessionId = ? AND chunkIndex = ?",
        arguments: [chunk.sessionId, chunk.chunkIndex])
      stored.append(
        TranscriptChunkRecord(
          id: id, sessionId: chunk.sessionId, chunkIndex: chunk.chunkIndex,
          text: chunk.text, textSha256: chunk.textSha256, startedAt: chunk.startedAt))
    }
    return stored
  }

  private static func segmentSourceFingerprint(sessionId: Int64, db: Database) throws -> (count: Int, maxId: Int64) {
    guard try db.tableExists("transcription_segments") else { return (0, 0) }
    let count =
      try Int.fetchOne(
        db, sql: "SELECT COUNT(*) FROM transcription_segments WHERE sessionId = ?", arguments: [sessionId]) ?? 0
    let maxId =
      try Int64.fetchOne(
        db, sql: "SELECT COALESCE(MAX(id), 0) FROM transcription_segments WHERE sessionId = ?", arguments: [sessionId]
      ) ?? 0
    return (count, maxId)
  }

  private static func sessionChunksNeedRewrite(sessionId: Int64, db: Database) throws -> Bool {
    let origin: Date
    if try db.columns(in: "transcription_sessions").contains(where: { $0.name == "startedAt" }),
      let startedAt = try Date.fetchOne(
        db, sql: "SELECT startedAt FROM transcription_sessions WHERE id = ?", arguments: [sessionId])
    {
      origin = startedAt
    } else {
      origin = Date(timeIntervalSince1970: 0)
    }
    let segments = try Row.fetchAll(
      db,
      sql: """
        SELECT text, segmentOrder, startTime FROM transcription_segments
        WHERE sessionId = ? ORDER BY segmentOrder, startTime
        """,
      arguments: [sessionId]
    ).map { row in
      TranscriptChunker.Segment(
        text: row["text"], order: row["segmentOrder"],
        startedAt: origin.addingTimeInterval(row["startTime"]))
    }
    let expected = TranscriptChunker.chunks(sessionId: sessionId, segments: segments)
    let stored = try Row.fetchAll(
      db,
      sql: """
        SELECT chunkIndex, textSha256, startedAt FROM transcript_chunks
        WHERE sessionId = ? ORDER BY chunkIndex
        """,
      arguments: [sessionId])
    guard stored.count == expected.count else { return true }
    for (chunk, row) in zip(expected, stored) {
      let index: Int = row["chunkIndex"]
      let hash: String = row["textSha256"]
      let startedAt: Date = row["startedAt"]
      if index != chunk.chunkIndex || hash != chunk.textSha256 || startedAt != chunk.startedAt {
        return true
      }
    }
    return false
  }

  private static func candidate(_ row: Row, kind: LocalEmbeddingSourceKind) -> LocalEmbeddingCandidate {
    LocalEmbeddingCandidate(
      sourceKind: kind, sourceId: row["id"], capturedAt: row["timestamp"], appName: row["appName"])
  }

  private static func filter(
    _ sql: inout String, _ args: inout [DatabaseValueConvertible],
    alias: String, timestamp: String, app: String?,
    startDate: Date?, endDate: Date?, appFilter: String?
  ) {
    if let startDate {
      sql += " AND \(alias).\(timestamp) >= ?"
      args.append(startDate)
    }
    if let endDate {
      sql += " AND \(alias).\(timestamp) <= ?"
      args.append(endDate)
    }
    if let appFilter, let app {
      sql += " AND \(alias).\(app) = ?"
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
