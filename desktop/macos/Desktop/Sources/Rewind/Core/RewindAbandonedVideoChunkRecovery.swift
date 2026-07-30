import Foundation
@preconcurrency import GRDB

/// A durable sidecar journal for chunks whose writer was cancelled before it
/// could produce a playable MP4 trailer. Markers are intentionally stored
/// beside the per-user Videos directory so the next startup can finish cleanup
/// against the same user database.
enum RewindAbandonedVideoChunkJournal {
  private static let directoryName = ".abandoned-video-chunks"

  private struct Marker: Codable {
    let relativePath: String
  }

  struct MarkerFile: Sendable {
    let relativePath: String
    let url: URL
  }

  @discardableResult
  static func record(reservation: RewindVideoChunkReservation, in videosDirectory: URL) throws -> MarkerFile {
    let markerDirectory = videosDirectory.appendingPathComponent(directoryName, isDirectory: true)
    try FileManager.default.createDirectory(at: markerDirectory, withIntermediateDirectories: true)

    let markerURL = markerDirectory.appendingPathComponent("\(reservation.generation)-\(UUID().uuidString).json")
    let data = try JSONEncoder().encode(Marker(relativePath: reservation.relativePath))
    try data.write(to: markerURL, options: .atomic)
    return MarkerFile(relativePath: reservation.relativePath, url: markerURL)
  }

  static func markers(in videosDirectory: URL) throws -> [MarkerFile] {
    let markerDirectory = videosDirectory.appendingPathComponent(directoryName, isDirectory: true)
    guard FileManager.default.fileExists(atPath: markerDirectory.path) else {
      return []
    }

    return try FileManager.default.contentsOfDirectory(
      at: markerDirectory,
      includingPropertiesForKeys: nil,
      options: [.skipsHiddenFiles]
    ).compactMap { markerURL in
      guard markerURL.pathExtension == "json" else { return nil }
      let marker = try JSONDecoder().decode(Marker.self, from: Data(contentsOf: markerURL))
      _ = try videoURL(relativePath: marker.relativePath, in: videosDirectory)
      return MarkerFile(relativePath: marker.relativePath, url: markerURL)
    }
  }

  static func remove(_ marker: MarkerFile) throws {
    try FileManager.default.removeItem(at: marker.url)
  }

  static func videoURL(relativePath: String, in videosDirectory: URL) throws -> URL {
    let trimmed = relativePath.trimmingCharacters(in: .whitespacesAndNewlines)
    let components = trimmed.split(separator: "/", omittingEmptySubsequences: false)
    guard components.count == 2,
      components.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." }),
      trimmed.hasSuffix(".mp4")
    else {
      throw RewindError.storageError("Invalid abandoned video chunk path")
    }

    let root = videosDirectory.standardizedFileURL
    let candidate = root.appendingPathComponent(trimmed).standardizedFileURL
    guard candidate.path.hasPrefix(root.path + "/") else {
      throw RewindError.storageError("Abandoned video chunk path escapes storage")
    }
    return candidate
  }
}

/// The tombstone is the database half of abandoned-chunk recovery. It rejects
/// late OCR/indexing writes after file recovery has removed the chunk.
enum RewindAbandonedVideoChunkQuarantine {
  private static let tableName = "abandoned_video_chunks"

  static func registerMigration(on migrator: inout DatabaseMigrator) {
    migrator.registerMigration("quarantineAbandonedVideoChunks") { db in
      try db.execute(
        sql: """
          CREATE TABLE \(tableName) (
            videoChunkPath TEXT PRIMARY KEY NOT NULL
          )
          """
      )
    }
  }

  static func requireAvailable(_ db: Database, videoChunkPath: String) throws {
    let isAbandoned =
      try Int.fetchOne(
        db,
        sql: "SELECT EXISTS(SELECT 1 FROM \(tableName) WHERE videoChunkPath = ?)",
        arguments: [videoChunkPath]
      ) ?? 0
    guard isAbandoned == 0 else {
      throw RewindAbandonedVideoChunkError(relativePath: videoChunkPath)
    }
  }
}

extension RewindDatabase {
  /// Insert a screenshot only when its video generation was not durably
  /// abandoned. This is the persistence boundary for late OCR continuations.
  @discardableResult
  func insertScreenshot(_ screenshot: Screenshot) throws -> Screenshot {
    guard let dbQueue = getDatabaseQueue() else {
      throw RewindError.databaseNotInitialized
    }

    return try dbQueue.write { db in
      if let videoChunkPath = screenshot.videoChunkPath, !videoChunkPath.isEmpty {
        try RewindAbandonedVideoChunkQuarantine.requireAvailable(db, videoChunkPath: videoChunkPath)
      }
      var record = screenshot
      // `imagePath` is NOT NULL in SQLite, whereas video-backed screenshots
      // carry nil in the model.
      if record.imagePath == nil { record.imagePath = "" }
      try record.insert(db)
      return record
    }
  }

  /// Tombstone a cancelled writer generation and remove every persisted frame
  /// in one transaction. Repeating this after a filesystem failure is safe.
  @discardableResult
  func abandonVideoChunk(relativePath: String) throws -> Int {
    guard let dbQueue = getDatabaseQueue() else {
      throw RewindError.databaseNotInitialized
    }
    guard !relativePath.isEmpty else {
      throw RewindError.storageError("Cannot abandon a video chunk with an empty path")
    }

    return try dbQueue.write { db in
      try db.execute(
        sql: "INSERT OR IGNORE INTO abandoned_video_chunks (videoChunkPath) VALUES (?)",
        arguments: [relativePath]
      )
      let deletedCount =
        try Int.fetchOne(
          db,
          sql: "SELECT COUNT(*) FROM screenshots WHERE videoChunkPath = ?",
          arguments: [relativePath]
        ) ?? 0
      try db.execute(sql: "DELETE FROM screenshots WHERE videoChunkPath = ?", arguments: [relativePath])
      return deletedCount
    }
  }
}
