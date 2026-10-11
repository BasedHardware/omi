import Darwin
import Foundation
@preconcurrency import GRDB
import os

/// Bounded `sqlite3 <corrupted> .recover | sqlite3 <recovered>` for a corrupted Rewind database.
///
/// `.recover` prints the whole database as SQL. Its stdout is wired straight into the
/// importer's stdin, so no byte of the dump passes through this process: there is no pipe
/// for us to drain and nothing to hold in memory. (Reading the dump only after
/// `waitUntilExit()` deadlocked as soon as it outgrew the ~64 KB pipe buffer: `.recover`
/// blocked on write and never exited.) A deadline terminates both children, and the caller
/// is resumed from their termination handlers instead of parking a thread in `waitUntilExit()`.
enum RewindSQLiteRecoveryPipeline {
  enum Outcome: Equatable, Sendable {
    case completed
    case timedOut
    case launchFailed
    case exited(recoverStatus: Int32, importStatus: Int32)
  }

  static let systemSQLite3URL = URL(fileURLWithPath: "/usr/bin/sqlite3")
  /// Recovery runs during database initialization. Past this, a fresh database (with the
  /// corrupted file kept in `backups/`) beats an app that never finishes starting.
  static let defaultTimeoutSeconds: TimeInterval = 120

  static func run(
    corruptedPath: String,
    recoveredPath: String,
    sqlite3URL: URL = systemSQLite3URL,
    timeoutSeconds: TimeInterval = defaultTimeoutSeconds,
    killGraceSeconds: TimeInterval = 2
  ) async -> Outcome {
    var fds: [Int32] = [-1, -1]
    guard pipe(&fds) == 0 else { return .launchFailed }
    let readFD = fds[0]
    let writeFD = fds[1]
    // Only the dup2'd copies (stdin of the importer, stdout of `.recover`) may reach a
    // child. A stray inherited write end would keep the importer from ever seeing EOF.
    _ = fcntl(readFD, F_SETFD, FD_CLOEXEC)
    _ = fcntl(writeFD, F_SETFD, FD_CLOEXEC)
    // Raw descriptors rather than a shared `Pipe`: `Process` closes a `Pipe`'s far end
    // on launch, which is wrong when both ends go to two different children. These
    // handles never close on their own; `closeParentEnds()` closes each exactly once.
    let sqlReadEnd = FileHandle(fileDescriptor: readFD, closeOnDealloc: false)
    let sqlWriteEnd = FileHandle(fileDescriptor: writeFD, closeOnDealloc: false)
    func closeParentEnds() {
      Darwin.close(readFD)
      Darwin.close(writeFD)
    }

    let recover = Process()
    recover.executableURL = sqlite3URL
    recover.arguments = [corruptedPath, ".recover"]
    recover.standardInput = FileHandle.nullDevice
    recover.standardOutput = sqlWriteEnd
    recover.standardError = FileHandle.nullDevice

    let importer = Process()
    importer.executableURL = sqlite3URL
    importer.arguments = [recoveredPath]
    importer.standardInput = sqlReadEnd
    importer.standardOutput = FileHandle.nullDevice
    importer.standardError = FileHandle.nullDevice

    let recoverExit = ProcessExitLatch()
    let importExit = ProcessExitLatch()
    recover.terminationHandler = { recoverExit.signal($0.terminationStatus) }
    importer.terminationHandler = { importExit.signal($0.terminationStatus) }

    do {
      try importer.run()
    } catch {
      closeParentEnds()
      return .launchFailed
    }
    do {
      try recover.run()
    } catch {
      // Dropping our write end gives the already-running importer EOF.
      closeParentEnds()
      importer.terminate()
      _ = await importExit.wait()
      return .launchFailed
    }
    // Each child now holds its own end. Ours must go, or the importer never sees EOF.
    closeParentEnds()

    let timedOut = OSAllocatedUnfairLock(initialState: false)
    let deadline = DispatchWorkItem {
      let running = [recover, importer].filter { $0.isRunning }
      guard !running.isEmpty else { return }
      timedOut.withLock { $0 = true }
      for process in running {
        process.terminate()
      }
      DispatchQueue.global().asyncAfter(deadline: .now() + killGraceSeconds) {
        for process in running where process.isRunning {
          kill(process.processIdentifier, SIGKILL)
        }
      }
    }
    DispatchQueue.global().asyncAfter(deadline: .now() + timeoutSeconds, execute: deadline)

    let recoverStatus = await recoverExit.wait()
    let importStatus = await importExit.wait()
    deadline.cancel()

    if timedOut.withLock({ $0 }) { return .timedOut }
    guard recoverStatus == 0, importStatus == 0 else {
      return .exited(recoverStatus: recoverStatus, importStatus: importStatus)
    }
    return .completed
  }
}

/// One-shot latch filled from `Process.terminationHandler`. Awaiting it suspends the
/// caller rather than blocking a thread in `waitUntilExit()`.
private final class ProcessExitLatch: Sendable {
  private struct State {
    var status: Int32?
    var waiter: CheckedContinuation<Int32, Never>?
  }

  private let state = OSAllocatedUnfairLock(initialState: State())

  func signal(_ status: Int32) {
    let waiter: CheckedContinuation<Int32, Never>? = state.withLock { current in
      guard current.status == nil else { return nil }
      current.status = status
      let pending = current.waiter
      current.waiter = nil
      return pending
    }
    waiter?.resume(returning: status)
  }

  func wait() async -> Int32 {
    await withCheckedContinuation { continuation in
      let status: Int32? = state.withLock { current in
        if let status = current.status { return status }
        current.waiter = continuation
        return nil
      }
      if let status {
        continuation.resume(returning: status)
      }
    }
  }
}

// MARK: - Corrupted-file handling

extension RewindDatabase {
  /// The last migration of the schema the direct-table fallback rebuilds: the first point
  /// in the ladder where `screenshots` carries every column that fallback copies.
  static let directRecoveryBaselineMigration = "addVideoChunkColumns"

  /// Moves a corrupted `omi.db` (with its WAL and rollback journal) to `backupPath`, and
  /// deletes whatever cannot be moved, so that nothing is left at `dbPath`.
  ///
  /// This runs before any recovery attempt. While the corrupted file stayed at `omi.db`,
  /// a recovery that hung, failed, or was cut short by quitting the app left the next
  /// launch to find the same file and repeat the same recovery, forever. Once it is out
  /// of the way the worst case is a fresh database.
  ///
  /// - Returns: the backup to salvage from, or nil when the file could only be deleted.
  /// - Throws: only when a file at `dbPath` (or a sidecar that SQLite would replay into a
  ///   fresh database there) could be neither moved nor deleted.
  static func moveCorruptedDatabaseAside(
    dbPath: String,
    backupPath: String,
    fileManager: FileManager = .default
  ) throws -> String? {
    var movedTo: String?
    if fileManager.fileExists(atPath: dbPath) {
      do {
        let backupDir = (backupPath as NSString).deletingLastPathComponent
        try fileManager.createDirectory(atPath: backupDir, withIntermediateDirectories: true)
        try fileManager.moveItem(atPath: dbPath, toPath: backupPath)
        movedTo = backupPath
      } catch {
        log("RewindDatabase: Could not move corrupted database aside (\(error.localizedDescription)); deleting it")
        try fileManager.removeItem(atPath: dbPath)
      }
    }

    // The WAL and rollback journal belong to the corrupted file: keep them with the backup
    // so salvage (and manual recovery) sees the same state. Left at `dbPath`, SQLite would
    // replay them into the fresh database. The shared-memory index is always rebuilt.
    for suffix in ["-wal", "-journal", "-shm"] {
      let sidecar = dbPath + suffix
      guard fileManager.fileExists(atPath: sidecar) else { continue }
      if let movedTo, suffix != "-shm",
        (try? fileManager.moveItem(atPath: sidecar, toPath: movedTo + suffix)) != nil
      {
        continue
      }
      try fileManager.removeItem(atPath: sidecar)
    }
    return movedTo
  }

  /// Removes a database file and every SQLite sidecar next to it. Best effort.
  static func removeDatabaseFiles(at path: String, fileManager: FileManager = .default) {
    for suffix in ["", "-wal", "-shm", "-journal"] where fileManager.fileExists(atPath: path + suffix) {
      try? fileManager.removeItem(atPath: path + suffix)
    }
  }

  /// Screenshot count of a `.recover`ed database, or nil when it is not safe to open as
  /// `omi.db`. `.recover` copies `grdb_migrations` like any other table, so rows lost to
  /// corruption can leave a ledger that claims less (or other) than the schema holds. The
  /// ledger must therefore be a gap-free prefix of the migration ladder: only then is
  /// "run the remaining migrations" the ordinary upgrade path rather than a re-run of a
  /// migration whose table or column already exists (which fails on every launch).
  static func validatedRecoveredScreenshotCount(at path: String, ownerID: String) -> Int? {
    let migrator = makeMigrator(contextBucketOwnerID: ownerID, legacyOwnerFallback: nil)
    do {
      let queue = try DatabaseQueue(path: path)
      defer { try? queue.close() }
      return try queue.read { db -> Int? in
        let applied = try migrator.appliedMigrations(db)
        guard !applied.isEmpty, try migrator.completedMigrations(db) == applied else { return nil }
        guard try db.tableExists("screenshots") else { return nil }
        return try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM screenshots") ?? 0
      }
    } catch {
      log("RewindDatabase: Recovered database failed validation: \(error)")
      return nil
    }
  }

  /// Fallback when `.recover` fails: copy what the corrupted `screenshots` table still yields
  /// into a new database at `recoveredPath`.
  ///
  /// The new database is built by the migration ladder itself, up to `directRecoveryBaselineMigration`,
  /// so its schema and its `grdb_migrations` ledger agree. `migrate` then continues from the
  /// next migration, exactly as it would for a user upgrading from that version. A
  /// hand-written table here previously carried later-migration columns without a ledger,
  /// so `migrate` re-ran the ladder from the top and failed on every launch.
  ///
  /// - Returns: the number of screenshots copied (0 when there was nothing to copy).
  static func rebuildScreenshotsFromCorruptedDatabase(
    at corruptedPath: String,
    into recoveredPath: String,
    ownerID: String
  ) async -> Int {
    var config = Configuration()
    config.readonly = true

    do {
      let corruptedQueue = try DatabaseQueue(path: corruptedPath, configuration: config)
      let screenshots:
        [(timestamp: Date, appName: String, windowTitle: String?, videoChunkPath: String?, frameOffset: Int?)] =
          try await corruptedQueue.read { db in
            var results: [(Date, String, String?, String?, Int?)] = []
            let rows = try? Row.fetchAll(
              db,
              sql: """
                    SELECT timestamp, appName, windowTitle, videoChunkPath, frameOffset
                    FROM screenshots
                    ORDER BY timestamp DESC
                    LIMIT 100000
                """)
            for row in rows ?? [] {
              if let timestamp: Date = row["timestamp"],
                let appName: String = row["appName"]
              {
                results.append(
                  (
                    timestamp,
                    appName,
                    row["windowTitle"] as String?,
                    row["videoChunkPath"] as String?,
                    row["frameOffset"] as Int?
                  ))
              }
            }
            return results
          }
      try? corruptedQueue.close()

      if screenshots.isEmpty {
        return 0
      }

      let recoveredQueue = try DatabaseQueue(path: recoveredPath)
      defer { try? recoveredQueue.close() }
      try makeMigrator(contextBucketOwnerID: ownerID, legacyOwnerFallback: nil)
        .migrate(recoveredQueue, upTo: directRecoveryBaselineMigration)
      try await recoveredQueue.write { db in
        for screenshot in screenshots {
          try db.execute(
            sql: """
                  INSERT INTO screenshots (timestamp, appName, windowTitle, imagePath, videoChunkPath, frameOffset, isIndexed)
                  VALUES (?, ?, ?, '', ?, ?, 0)
              """,
            arguments: [
              screenshot.timestamp, screenshot.appName, screenshot.windowTitle, screenshot.videoChunkPath,
              screenshot.frameOffset,
            ])
        }
      }
      return screenshots.count
    } catch {
      log("RewindDatabase: Direct table recovery failed: \(error)")
      return 0
    }
  }
}
