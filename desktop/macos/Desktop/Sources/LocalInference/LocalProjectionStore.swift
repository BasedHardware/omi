import Foundation
@preconcurrency import GRDB

/// Exact stored `client_processing` bytes. A retry must send `json` unchanged.
struct StoredClientProjection: Sendable, Equatable {
  var transcriptSha256: String
  var json: Data
}

protocol LocalProjectionStoring: Sendable {
  func load(sessionId: Int64) async throws -> StoredClientProjection?
  func save(sessionId: Int64, projection: StoredClientProjection) async throws
}

/// In-process store for hermetic summarizer tests. Not the production path.
actor MemoryLocalProjectionStore: LocalProjectionStoring {
  private var rows: [Int64: StoredClientProjection] = [:]

  func load(sessionId: Int64) async throws -> StoredClientProjection? {
    rows[sessionId]
  }

  func save(sessionId: Int64, projection: StoredClientProjection) async throws {
    rows[sessionId] = projection
  }
}

/// GRDB-backed store against `transcription_sessions.clientProcessingJson`.
///
/// The queue is injected so tests can use an in-memory database that has run
/// only `addClientProcessingProjection`. Production passes the Rewind pool.
actor GRDBLocalProjectionStore: LocalProjectionStoring {
  private let queue: any DatabaseWriter

  init(queue: any DatabaseWriter) {
    self.queue = queue
  }

  func load(sessionId: Int64) async throws -> StoredClientProjection? {
    try await queue.read { db in
      guard
        let json = try String.fetchOne(
          db,
          sql: "SELECT clientProcessingJson FROM transcription_sessions WHERE id = ?",
          arguments: [sessionId]
        ), !json.isEmpty
      else {
        return nil
      }
      let data = Data(json.utf8)
      let payload = try ClientProcessingContract.decode(data)
      return StoredClientProjection(transcriptSha256: payload.transcriptSha256, json: data)
    }
  }

  func save(sessionId: Int64, projection: StoredClientProjection) async throws {
    let json = String(decoding: projection.json, as: UTF8.self)
    try await queue.write { db in
      try db.execute(
        sql: """
          UPDATE transcription_sessions
          SET clientProcessingJson = ?, updatedAt = ?
          WHERE id = ?
          """,
        arguments: [json, Date(), sessionId]
      )
    }
  }
}
