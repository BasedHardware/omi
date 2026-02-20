import Foundation
import GRDB

/// Actor-based database manager for Rewind screenshots
actor RewindDatabase {
    static let shared = RewindDatabase()

    private var dbQueue: DatabasePool?

    /// Track if we recovered from corruption (for UI notification)
    private(set) var didRecoverFromCorruption = false

    /// Track initialization state to prevent concurrent init attempts
    private var initializationTask: Task<Void, Error>?

    /// Path to the running flag file (used to detect unclean shutdown)
    private var runningFlagPath: String?

    /// The user ID this database is configured for (nil = not yet configured → "anonymous")
    private var configuredUserId: String?

    /// The user ID that was actually used to open the current database
    private var openedForUserId: String?

    /// Generation counter — incremented on close() so stale task completions don't corrupt state
    private var initGeneration: Int = 0

    /// Static user ID for nonisolated markCleanShutdown (set by configure(userId:))
    nonisolated(unsafe) static var currentUserId: String?

    /// Monotonic counter incremented by configure(). Used by closeIfStale() to detect
    /// whether a new sign-in session has started since the close was requested.
    nonisolated(unsafe) static var configureGeneration: Int = 0

    /// Runtime error tracking: consecutive SQLITE_IOERR/CORRUPT errors during normal queries.
    /// When this hits the threshold, we close the database so the next initialize() attempt
    /// goes through the full recovery path (WAL cleanup, corruption detection, fresh DB).
    private var consecutiveQueryIOErrors = 0
    private let maxQueryIOErrorsBeforeRecovery = 5

    // MARK: - Initialization

    private init() {}

    /// Whether the database has been successfully initialized
    var isInitialized: Bool { dbQueue != nil }

    /// Get the database pool for other storage actors
    func getDatabaseQueue() -> DatabasePool? {
        return dbQueue
    }

    /// Report a query error from a storage actor or subsystem.
    /// Tracks consecutive SQLITE_IOERR/CORRUPT errors. When the threshold is reached,
    /// closes the database so the next initialize() call triggers recovery.
    func reportQueryError(_ error: Error) {
        guard let dbError = error as? DatabaseError else { return }
        let code = dbError.resultCode
        let extendedCode = dbError.extendedResultCode.rawValue
        let isIOError = code == .SQLITE_IOERR
        let isCorrupt = code == .SQLITE_CORRUPT
        let isCorruptFS = extendedCode == 6922

        guard isIOError || isCorrupt || isCorruptFS else { return }

        consecutiveQueryIOErrors += 1
        if consecutiveQueryIOErrors >= maxQueryIOErrorsBeforeRecovery {
            logError("RewindDatabase: \(consecutiveQueryIOErrors) consecutive I/O errors during queries, closing database for recovery")
            close()
            // Next getDatabaseQueue() returns nil → callers get databaseNotInitialized
            // Next initialize() call will go through full recovery path
        }
    }

    /// Report a successful query, resetting the runtime error counter.
    func reportQuerySuccess() {
        if consecutiveQueryIOErrors > 0 {
            consecutiveQueryIOErrors = 0
        }
    }

    /// Configure the database for a specific user.
    /// Does NOT close or reopen the database — call initialize() after this.
    /// initialize() will detect the user mismatch and reopen if needed.
    func configure(userId: String?) {
        let resolvedId = (userId?.isEmpty == false) ? userId! : "anonymous"
        configuredUserId = resolvedId
        RewindDatabase.currentUserId = resolvedId
        RewindDatabase.configureGeneration += 1
        log("RewindDatabase: Configured for user \(resolvedId) (generation \(RewindDatabase.configureGeneration))")
    }

    /// Close the database only if no new session has started (configure() not called since).
    /// Prevents a stale sign-out Task from closing a freshly opened database.
    func closeIfStale(generation: Int) {
        guard generation == RewindDatabase.configureGeneration else {
            log("RewindDatabase: Skipping stale close (requested gen \(generation), current gen \(RewindDatabase.configureGeneration))")
            return
        }
        close()
    }

    /// Close the database, allowing re-initialization for a different user.
    func close() {
        dbQueue = nil
        initializationTask = nil
        runningFlagPath = nil
        openedForUserId = nil
        initGeneration += 1
        log("RewindDatabase: Closed database (generation \(initGeneration))")
    }

    /// Switch to a different user's database.
    func switchUser(to userId: String?) async throws {
        close()
        configure(userId: userId)
        try await initialize()
    }

    /// Returns the per-user base directory: ~/Library/Application Support/Omi/users/{userId}/
    /// Falls back to the static currentUserId (set synchronously at app start) when
    /// configure() hasn't been called yet (e.g., TierManager triggers init early).
    private func userBaseDirectory() -> URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let userId = configuredUserId ?? RewindDatabase.currentUserId ?? "anonymous"
        return appSupport
            .appendingPathComponent("Omi", isDirectory: true)
            .appendingPathComponent("users", isDirectory: true)
            .appendingPathComponent(userId, isDirectory: true)
    }

    /// Static version of userBaseDirectory for nonisolated markCleanShutdown
    private static func staticUserBaseDirectory() -> URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let userId = currentUserId ?? "anonymous"
        return appSupport
            .appendingPathComponent("Omi", isDirectory: true)
            .appendingPathComponent("users", isDirectory: true)
            .appendingPathComponent(userId, isDirectory: true)
    }

    /// Mark a clean shutdown by removing the running flag file.
    /// Call from applicationWillTerminate to avoid unnecessary integrity checks on next launch.
    /// This is nonisolated so it can be called synchronously from the main thread during termination.
    nonisolated static func markCleanShutdown() {
        let userDir = staticUserBaseDirectory()
        let flagPath = userDir.appendingPathComponent(".omi_running").path
        try? FileManager.default.removeItem(atPath: flagPath)
        log("RewindDatabase: Clean shutdown flagged")
    }

    /// Check if the previous session ended with an unclean shutdown (crash, force quit, etc.)
    func hadUncleanShutdown() -> Bool {
        let flagPath = userBaseDirectory().appendingPathComponent(".omi_running").path
        return FileManager.default.fileExists(atPath: flagPath)
    }

    /// Initialize the database with migrations.
    /// If the DB is already open for the correct user, returns immediately.
    /// If the DB is open for a different user (e.g., "anonymous" before configure was called),
    /// closes it and reopens for the configured user.
    func initialize() async throws {
        let targetUser = configuredUserId ?? RewindDatabase.currentUserId ?? "anonymous"

        // Already initialized for the correct user
        if dbQueue != nil && openedForUserId == targetUser {
            return
        }

        // Initialized for wrong user — close and reopen
        if dbQueue != nil {
            log("RewindDatabase: Re-initializing for user \(targetUser) (was \(openedForUserId ?? "nil"))")
            close()
        }

        // If initialization is in progress, wait for it then re-check
        if let existingTask = initializationTask {
            _ = try? await existingTask.value
            // After waiting, check if the result is for the right user
            if dbQueue != nil && openedForUserId == targetUser {
                return
            }
            // Wrong user or failed — close and proceed
            if dbQueue != nil {
                close()
            }
        }

        // Start initialization
        let myGeneration = initGeneration
        let task = Task {
            try await performInitialization()
        }
        initializationTask = task

        do {
            try await task.value
            // Only clear if no close() happened since we started (generation unchanged)
            if initGeneration == myGeneration {
                initializationTask = nil
            }
        } catch {
            if initGeneration == myGeneration {
                initializationTask = nil
            }
            throw error
        }
    }

    /// Actual initialization logic (called only once at a time)
    private func performInitialization() async throws {
        guard dbQueue == nil else { return }

        let omiDir = userBaseDirectory()

        // Create directory if needed (withIntermediateDirectories creates parents too)
        try FileManager.default.createDirectory(at: omiDir, withIntermediateDirectories: true)

        // Migrate data from legacy path if this is first launch with per-user paths
        migrateFromLegacyPathIfNeeded(to: omiDir)

        let dbPath = omiDir.appendingPathComponent("omi.db").path
        let flagPath = omiDir.appendingPathComponent(".omi_running").path
        runningFlagPath = flagPath
        log("RewindDatabase: Opening database at \(dbPath)")

        // Detect unclean shutdown: if the running flag file exists, the previous launch
        // didn't exit cleanly (crash, force quit, power loss)
        let previousCrashed = FileManager.default.fileExists(atPath: flagPath)
        if previousCrashed {
            log("RewindDatabase: Unclean shutdown detected (running flag exists)")
        }

        // Clean up stale WAL files that can cause disk I/O errors (SQLite error 10)
        if FileManager.default.fileExists(atPath: dbPath) {
            cleanupStaleWALFiles(at: dbPath)
        }

        var config = Configuration()
        config.prepareDatabase { db in
            // Try to enable WAL mode for better crash resistance and performance
            // WAL mode keeps writes in a separate file, making corruption much less likely
            // If WAL fails (disk I/O error, permissions), continue with default journal mode
            do {
                try db.execute(sql: "PRAGMA journal_mode = WAL")
                // synchronous = NORMAL is safe with WAL and much faster than FULL
                try db.execute(sql: "PRAGMA synchronous = NORMAL")
                // Auto-checkpoint every 1000 pages (~4MB) for WAL
                try db.execute(sql: "PRAGMA wal_autocheckpoint = 1000")
            } catch {
                // WAL mode failed - log but continue with default journal mode
                // This can happen with disk I/O errors, permission issues, or full disk
                log("RewindDatabase: WAL mode unavailable (\(error.localizedDescription)), using default journal mode")
            }

            // Enable foreign keys (required)
            try db.execute(sql: "PRAGMA foreign_keys = ON")

            // Set busy timeout to avoid "database is locked" errors (5 seconds)
            try db.execute(sql: "PRAGMA busy_timeout = 5000")
        }

        let queue: DatabasePool
        do {
            queue = try DatabasePool(path: dbPath, configuration: config)
        } catch {
            // If opening fails (e.g. disk I/O error on WAL), try once more without WAL files
            log("RewindDatabase: Failed to open database: \(error), cleaning WAL and retrying...")
            removeWALFiles(at: dbPath)
            do {
                queue = try DatabasePool(path: dbPath, configuration: config)
            } catch let retryError {
                // If still failing, check for database corruption:
                //   - SQLITE_CORRUPT (error 11): malformed database
                //   - SQLITE_IOERR_CORRUPTFS (extended code 6922): filesystem reports file
                //     corruption, commonly caused by migrating WAL files to a new path
                let isCorrupted: Bool
                if let dbError = retryError as? DatabaseError {
                    let isCorruptError = dbError.resultCode == .SQLITE_CORRUPT
                    let isCorruptFS = dbError.extendedResultCode.rawValue == 6922 // SQLITE_IOERR_CORRUPTFS
                    isCorrupted = isCorruptError || isCorruptFS
                } else {
                    isCorrupted = "\(retryError)".contains("malformed")
                }

                if isCorrupted && FileManager.default.fileExists(atPath: dbPath) {
                    log("RewindDatabase: Database is corrupted (error: \(retryError)), attempting recovery...")
                    try await handleCorruptedDatabase(at: dbPath, in: omiDir)
                    // Retry with recovered or fresh database
                    queue = try DatabasePool(path: dbPath, configuration: config)
                } else {
                    throw retryError
                }
            }
        }

        // Post-open health check: verify we can actually run queries on the opened database.
        // This catches cases where the DB opens successfully (PRAGMAs pass) but data queries
        // fail with SQLITE_IOERR — e.g., stale WAL files from migration, page-level corruption.
        var activeQueue = queue
        do {
            try await activeQueue.read { db in
                _ = try Int.fetchOne(db, sql: "SELECT count(*) FROM sqlite_master")
            }
        } catch {
            if let dbError = error as? DatabaseError,
               dbError.resultCode == .SQLITE_IOERR || dbError.resultCode == .SQLITE_CORRUPT {
                log("RewindDatabase: Database opened but queries fail (\(error)), removing WAL and retrying...")
                removeWALFiles(at: dbPath)
                let retryQueue = try DatabasePool(path: dbPath, configuration: config)
                try await retryQueue.read { db in
                    _ = try Int.fetchOne(db, sql: "SELECT count(*) FROM sqlite_master")
                }
                activeQueue = retryQueue
            } else {
                throw error
            }
        }

        dbQueue = activeQueue
        openedForUserId = configuredUserId ?? RewindDatabase.currentUserId ?? "anonymous"
        consecutiveQueryIOErrors = 0

        try migrate(activeQueue)

        // After unclean shutdown, do a cheap schema sanity check (not a full DB scan).
        // PRAGMA quick_check scans the ENTIRE database regardless of the (N) argument
        // (N only limits error reporting), so on large databases (e.g. 4+ GB) it can take 60-90s.
        if previousCrashed {
            log("RewindDatabase: Running lightweight integrity check after unclean shutdown...")
            try verifyDatabaseIntegrity(activeQueue)
        } else {
            // Still log journal mode on clean startup (cheap PRAGMA, no full check)
            try await activeQueue.read { db in
                let journalMode = try String.fetchOne(db, sql: "PRAGMA journal_mode")
                log("RewindDatabase: Journal mode is \(journalMode ?? "unknown")")
            }
        }

        // Set running flag — will be cleared on clean shutdown
        FileManager.default.createFile(atPath: flagPath, contents: nil)

        log("RewindDatabase: Initialized successfully")
    }

    // MARK: - Legacy Migration

    /// Migrate data from the legacy shared path (Omi/) or from the anonymous fallback
    /// (Omi/users/anonymous/) to the per-user path (Omi/users/{userId}/).
    /// Handles both first-time migration (DB move) and partial re-runs (directory merges).
    private func migrateFromLegacyPathIfNeeded(to userDir: URL) {
        let fileManager = FileManager.default
        let appSupport = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let omiDir = appSupport.appendingPathComponent("Omi", isDirectory: true)

        // Determine migration source: prefer legacy root (Omi/omi.db), fall back to anonymous dir.
        // The anonymous fallback covers the case where TierManager or another early caller
        // triggered initialize() before configure(userId:) was called, causing data to land
        // in users/anonymous/ instead of the real user's directory.
        let legacyDB = omiDir.appendingPathComponent("omi.db")
        let anonymousDir = omiDir
            .appendingPathComponent("users", isDirectory: true)
            .appendingPathComponent("anonymous", isDirectory: true)

        let effectiveUserId = configuredUserId ?? RewindDatabase.currentUserId ?? "anonymous"
        let sourceDir: URL
        if fileManager.fileExists(atPath: legacyDB.path) {
            sourceDir = omiDir
        } else if effectiveUserId != "anonymous",
                  fileManager.fileExists(atPath: anonymousDir.path) {
            // Check if anonymous dir has anything worth migrating (DB, Videos, Screenshots, backups)
            let hasContent = ["omi.db", "Screenshots", "Videos", "backups"].contains {
                fileManager.fileExists(atPath: anonymousDir.appendingPathComponent($0).path)
            }
            guard hasContent else { return }
            sourceDir = anonymousDir
        } else {
            return // Nothing to migrate
        }

        // Don't migrate to ourselves
        guard sourceDir.path != userDir.path else { return }

        log("RewindDatabase: Migrating data from \(sourceDir.path) to \(userDir.path)")

        // Items to migrate: omi.db, Screenshots/, Videos/, backups/
        // IMPORTANT: Do NOT move omi.db-wal, omi.db-shm, or .omi_running:
        //   - WAL/SHM files are path-bound. Moving them to a new directory makes them
        //     invalid, causing SQLITE_IOERR_CORRUPTFS (error 6922) on the next open.
        //     SQLite will cleanly recover without stale WAL files.
        //   - .omi_running would falsely trigger unclean-shutdown recovery at the
        //     destination, running an expensive integrity check on the migrated DB.
        let itemsToMove = [
            "omi.db", "Screenshots", "Videos", "backups",
        ]

        // Delete WAL/SHM and running flag at source AND destination — do NOT migrate them.
        // Stale WAL/SHM at the destination (from a prior partial migration or crash) would
        // also cause SQLITE_IOERR_CORRUPTFS when SQLite opens the migrated DB.
        for staleFile in ["omi.db-wal", "omi.db-shm", ".omi_running"] {
            for dir in [sourceDir, userDir] {
                let path = dir.appendingPathComponent(staleFile)
                if fileManager.fileExists(atPath: path.path) {
                    try? fileManager.removeItem(at: path)
                    let label = dir == sourceDir ? "source" : "dest"
                    log("RewindDatabase: Deleted \(staleFile) from \(label) (not migrating)")
                }
            }
        }

        for name in itemsToMove {
            let source = sourceDir.appendingPathComponent(name)
            let dest = userDir.appendingPathComponent(name)
            guard fileManager.fileExists(atPath: source.path) else { continue }

            var isDir: ObjCBool = false
            fileManager.fileExists(atPath: source.path, isDirectory: &isDir)

            do {
                if isDir.boolValue && fileManager.fileExists(atPath: dest.path) {
                    // Both source and dest dirs exist — merge contents (move each child item)
                    let children = try fileManager.contentsOfDirectory(atPath: source.path)
                    var moved = 0
                    for child in children {
                        let childSrc = source.appendingPathComponent(child)
                        let childDst = dest.appendingPathComponent(child)
                        if fileManager.fileExists(atPath: childDst.path) { continue }
                        try fileManager.moveItem(at: childSrc, to: childDst)
                        moved += 1
                    }
                    // Remove source dir if now empty
                    let remaining = try? fileManager.contentsOfDirectory(atPath: source.path)
                    if remaining?.isEmpty == true {
                        try? fileManager.removeItem(at: source)
                    }
                    log("RewindDatabase: Merged \(name) (\(moved) items moved)")
                } else if fileManager.fileExists(atPath: dest.path) {
                    // File already exists at dest — remove stale source copy
                    try? fileManager.removeItem(at: source)
                    log("RewindDatabase: Removed stale \(name) from source (already at dest)")
                } else {
                    try fileManager.moveItem(at: source, to: dest)
                    log("RewindDatabase: Migrated \(name)")
                }
            } catch {
                log("RewindDatabase: Failed to migrate \(name): \(error.localizedDescription)")
            }
        }

        // Clean up source dir if it's now empty (don't leave empty anonymous/ dirs around)
        if sourceDir != omiDir {
            let remaining = try? fileManager.contentsOfDirectory(atPath: sourceDir.path)
            if remaining?.isEmpty == true {
                try? fileManager.removeItem(at: sourceDir)
                log("RewindDatabase: Removed empty source dir \(sourceDir.lastPathComponent)")
            }
        }

        log("RewindDatabase: Legacy migration complete")
    }

    // MARK: - Corruption Detection & Recovery

    /// Check if database file is corrupted using quick_check
    /// Returns true if corrupted, false if OK
    private func checkDatabaseCorruption(at path: String) async -> Bool {
        // Open in read-write mode (NOT readonly) because WAL recovery requires write access.
        // Opening readonly with a pending WAL file causes SQLITE_CANTOPEN (error 14),
        // which is a false positive - the database isn't actually corrupted.
        do {
            let testQueue = try DatabaseQueue(path: path)
            let result = try await testQueue.read { db -> String in
                try String.fetchOne(db, sql: "PRAGMA quick_check(1)") ?? "ok"
            }
            return result.lowercased() != "ok"
        } catch {
            // If we can't even open the database, it's definitely corrupted
            log("RewindDatabase: Database failed to open for integrity check: \(error)")
            return true
        }
    }

    /// Clean up stale WAL/SHM files that can cause disk I/O errors (SQLite error 10, code 3850)
    /// This happens when the app crashes and leaves behind WAL files that are in a bad state
    private func cleanupStaleWALFiles(at dbPath: String) {
        let walPath = dbPath + "-wal"
        let shmPath = dbPath + "-shm"
        let fileManager = FileManager.default

        // Only clean up if WAL file exists and is empty (indicates stale/orphaned WAL)
        // Non-empty WAL files may contain uncommitted data we don't want to lose
        if fileManager.fileExists(atPath: walPath),
           let attrs = try? fileManager.attributesOfItem(atPath: walPath),
           let size = attrs[.size] as? Int64, size == 0 {
            try? fileManager.removeItem(atPath: walPath)
            try? fileManager.removeItem(atPath: shmPath)
            log("RewindDatabase: Cleaned up stale empty WAL/SHM files")
        }
    }

    /// Force-remove WAL/SHM files (last resort when database won't open)
    private func removeWALFiles(at dbPath: String) {
        let fileManager = FileManager.default
        for ext in ["-wal", "-shm"] {
            let filePath = dbPath + ext
            if fileManager.fileExists(atPath: filePath) {
                try? fileManager.removeItem(atPath: filePath)
                log("RewindDatabase: Removed \(ext) file for recovery")
            }
        }
    }

    /// Number of records recovered from corrupted database (0 if none)
    private(set) var recoveredRecordCount: Int = 0

    /// Handle corrupted database: attempt recovery, backup, and recreate
    private func handleCorruptedDatabase(at dbPath: String, in omiDir: URL) async throws {
        let fileManager = FileManager.default

        // Create backup directory
        let backupDir = omiDir.appendingPathComponent("backups", isDirectory: true)
        try fileManager.createDirectory(at: backupDir, withIntermediateDirectories: true)

        // Generate backup filename with timestamp
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd_HHmmss"
        let timestamp = formatter.string(from: Date())
        let backupPath = backupDir.appendingPathComponent("omi_corrupted_\(timestamp).db")

        // Backup the corrupted database (for potential manual recovery)
        log("RewindDatabase: Backing up corrupted database to \(backupPath.path)")
        try fileManager.copyItem(atPath: dbPath, toPath: backupPath.path)

        // Attempt to recover data from corrupted database
        let recoveredPath = omiDir.appendingPathComponent("omi_recovered.db").path
        let recoveredCount = await attemptDataRecovery(from: dbPath, to: recoveredPath)
        recoveredRecordCount = recoveredCount

        if recoveredCount > 0 {
            log("RewindDatabase: Recovered \(recoveredCount) screenshot records from corrupted database")
            // Use recovered database instead of creating fresh one
            try fileManager.removeItem(atPath: dbPath)
            try fileManager.moveItem(atPath: recoveredPath, toPath: dbPath)

            // Remove WAL/SHM files from corrupted database
            for ext in ["-wal", "-shm", "-journal"] {
                let file = dbPath + ext
                if fileManager.fileExists(atPath: file) {
                    try? fileManager.removeItem(atPath: file)
                }
            }

            log("RewindDatabase: Using recovered database with \(recoveredCount) records")
        } else {
            // No data recovered, remove corrupted database and start fresh
            log("RewindDatabase: No data could be recovered, creating fresh database")

            // Clean up recovery attempt if it exists
            if fileManager.fileExists(atPath: recoveredPath) {
                try? fileManager.removeItem(atPath: recoveredPath)
            }

            // Remove corrupted database and associated WAL/SHM files
            let filesToRemove = [
                dbPath,
                dbPath + "-wal",
                dbPath + "-shm",
                dbPath + "-journal"
            ]

            for file in filesToRemove {
                if fileManager.fileExists(atPath: file) {
                    try fileManager.removeItem(atPath: file)
                    log("RewindDatabase: Removed \(file)")
                }
            }
        }

        logError("RewindDatabase: Corrupted database backed up and removed. A fresh database will be created.")

        // Clean up old backups (keep only last 5)
        try await cleanupOldBackups(in: backupDir, keepCount: 5)
    }

    /// Attempt to recover data from a corrupted database using sqlite3 .recover
    /// Returns the number of screenshot records recovered
    private func attemptDataRecovery(from corruptedPath: String, to recoveredPath: String) async -> Int {
        let fileManager = FileManager.default

        // Remove any existing recovered database
        if fileManager.fileExists(atPath: recoveredPath) {
            try? fileManager.removeItem(atPath: recoveredPath)
        }

        // Run sqlite3 recovery in a detached task to avoid blocking the actor
        // Process.waitUntilExit() is synchronous and would deadlock the actor
        let (success, recoveredSQL) = await withCheckedContinuation { (continuation: CheckedContinuation<(Bool, Data), Never>) in
            Task.detached {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/usr/bin/sqlite3")
                process.arguments = [corruptedPath, ".recover"]

                let outputPipe = Pipe()
                process.standardOutput = outputPipe
                process.standardError = FileHandle.nullDevice

                do {
                    try process.run()
                    process.waitUntilExit()

                    if process.terminationStatus == 0 {
                        let data = outputPipe.fileHandleForReading.readDataToEndOfFile()
                        continuation.resume(returning: (true, data))
                    } else {
                        continuation.resume(returning: (false, Data()))
                    }
                } catch {
                    continuation.resume(returning: (false, Data()))
                }
            }
        }

        if success && !recoveredSQL.isEmpty {
            // Import recovered SQL into new database (also in detached task)
            let importSuccess = await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
                Task.detached {
                    let importProcess = Process()
                    importProcess.executableURL = URL(fileURLWithPath: "/usr/bin/sqlite3")
                    importProcess.arguments = [recoveredPath]

                    let inputPipe = Pipe()
                    importProcess.standardInput = inputPipe
                    importProcess.standardOutput = FileHandle.nullDevice
                    importProcess.standardError = FileHandle.nullDevice

                    do {
                        try importProcess.run()
                        inputPipe.fileHandleForWriting.write(recoveredSQL)
                        inputPipe.fileHandleForWriting.closeFile()
                        importProcess.waitUntilExit()
                        continuation.resume(returning: importProcess.terminationStatus == 0)
                    } catch {
                        continuation.resume(returning: false)
                    }
                }
            }

            if importSuccess && fileManager.fileExists(atPath: recoveredPath) {
                return countRecoveredScreenshots(at: recoveredPath)
            }
        }

        // Fallback: Try to read screenshots table directly
        return await attemptDirectTableRecovery(from: corruptedPath, to: recoveredPath)
    }

    /// Fallback recovery: try to read the screenshots table directly
    private func attemptDirectTableRecovery(from corruptedPath: String, to recoveredPath: String) async -> Int {
        var config = Configuration()
        config.readonly = true

        do {
            let corruptedQueue = try DatabaseQueue(path: corruptedPath, configuration: config)

            // Try to read screenshot records
            let screenshots: [(timestamp: Date, appName: String, windowTitle: String?, videoChunkPath: String?, frameOffset: Int?)] = try await corruptedQueue.read { db in
                var results: [(Date, String, String?, String?, Int?)] = []

                // Try to fetch what we can from screenshots table
                let rows = try? Row.fetchAll(db, sql: """
                    SELECT timestamp, appName, windowTitle, videoChunkPath, frameOffset
                    FROM screenshots
                    ORDER BY timestamp DESC
                    LIMIT 100000
                """)

                for row in rows ?? [] {
                    if let timestamp: Date = row["timestamp"],
                       let appName: String = row["appName"] {
                        results.append((
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

            if screenshots.isEmpty {
                return 0
            }

            // Create new database with recovered data
            let recoveredQueue = try DatabaseQueue(path: recoveredPath)

            try await recoveredQueue.write { db in
                // Create minimal screenshots table
                try db.execute(sql: """
                    CREATE TABLE IF NOT EXISTS screenshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME NOT NULL,
                        appName TEXT NOT NULL,
                        windowTitle TEXT,
                        imagePath TEXT NOT NULL DEFAULT '',
                        videoChunkPath TEXT,
                        frameOffset INTEGER,
                        ocrText TEXT,
                        ocrDataJson TEXT,
                        isIndexed INTEGER NOT NULL DEFAULT 0,
                        focusStatus TEXT,
                        extractedTasksJson TEXT,
                        adviceJson TEXT
                    )
                """)

                // Insert recovered records
                for screenshot in screenshots {
                    try db.execute(sql: """
                        INSERT INTO screenshots (timestamp, appName, windowTitle, imagePath, videoChunkPath, frameOffset, isIndexed)
                        VALUES (?, ?, ?, '', ?, ?, 0)
                    """, arguments: [screenshot.timestamp, screenshot.appName, screenshot.windowTitle, screenshot.videoChunkPath, screenshot.frameOffset])
                }
            }

            return screenshots.count

        } catch {
            log("RewindDatabase: Direct table recovery failed: \(error)")
            return 0
        }
    }

    /// Count screenshots in recovered database
    private func countRecoveredScreenshots(at path: String) -> Int {
        do {
            let queue = try DatabaseQueue(path: path)
            return try queue.read { db in
                try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM screenshots") ?? 0
            }
        } catch {
            return 0
        }
    }

    /// Clean up old database backups, keeping only the most recent ones
    private func cleanupOldBackups(in backupDir: URL, keepCount: Int) async throws {
        let fileManager = FileManager.default

        let files = try fileManager.contentsOfDirectory(
            at: backupDir,
            includingPropertiesForKeys: [.creationDateKey],
            options: [.skipsHiddenFiles]
        ).filter { $0.pathExtension == "db" }

        // Sort by creation date, newest first
        let sortedFiles = files.sorted { file1, file2 in
            let date1 = (try? file1.resourceValues(forKeys: [.creationDateKey]).creationDate) ?? Date.distantPast
            let date2 = (try? file2.resourceValues(forKeys: [.creationDateKey]).creationDate) ?? Date.distantPast
            return date1 > date2
        }

        // Remove files beyond keepCount
        for file in sortedFiles.dropFirst(keepCount) {
            try fileManager.removeItem(at: file)
            log("RewindDatabase: Removed old backup \(file.lastPathComponent)")
        }
    }

    /// Verify database integrity after successful initialization
    private func verifyDatabaseIntegrity(_ queue: DatabasePool) throws {
        try queue.read { db in
            // Cheap schema-level check: verify we can read from a core table and the page count.
            // Avoids PRAGMA quick_check which scans the entire DB (75s+ on 4 GB databases).
            let pageCount = try Int.fetchOne(db, sql: "PRAGMA page_count") ?? 0
            let pageSize = try Int.fetchOne(db, sql: "PRAGMA page_size") ?? 0
            let dbSizeMB = (pageCount * pageSize) / (1024 * 1024)
            log("RewindDatabase: Database size ~\(dbSizeMB) MB (\(pageCount) pages)")

            // Verify schema is readable by querying sqlite_master
            let tableCount = try Int.fetchOne(db, sql: "SELECT count(*) FROM sqlite_master WHERE type='table'") ?? 0
            log("RewindDatabase: Schema OK (\(tableCount) tables)")

            // Log journal mode (WAL preferred, but may fall back to delete/rollback)
            let journalMode = try String.fetchOne(db, sql: "PRAGMA journal_mode")
            log("RewindDatabase: Journal mode is \(journalMode ?? "unknown")")

            // Log warning if not using WAL (less crash-resistant)
            if journalMode?.lowercased() != "wal" {
                log("RewindDatabase: WARNING - Not using WAL mode, database may be less crash-resistant")
            }
        }
    }

    // MARK: - Migrations

    private func migrate(_ queue: DatabasePool) throws {
        var migrator = DatabaseMigrator()

        // Migration 1: Create screenshots table
        migrator.registerMigration("createScreenshots") { db in
            try db.create(table: "screenshots") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("timestamp", .datetime).notNull()
                t.column("appName", .text).notNull()
                t.column("windowTitle", .text)
                t.column("imagePath", .text).notNull()
                t.column("ocrText", .text)
                t.column("isIndexed", .boolean).notNull().defaults(to: false)
                t.column("focusStatus", .text)
                t.column("extractedTasksJson", .text)
                t.column("adviceJson", .text)
            }

            // Create indexes
            try db.create(index: "idx_screenshots_timestamp", on: "screenshots", columns: ["timestamp"])
            try db.create(index: "idx_screenshots_appName", on: "screenshots", columns: ["appName"])
            try db.create(index: "idx_screenshots_isIndexed", on: "screenshots", columns: ["isIndexed"])
        }

        // Migration 2: Create FTS5 virtual table for full-text search
        migrator.registerMigration("createScreenshotsFTS") { db in
            try db.execute(sql: """
                CREATE VIRTUAL TABLE screenshots_fts USING fts5(
                    ocrText,
                    windowTitle,
                    content='screenshots',
                    content_rowid='id'
                )
                """)

            // Create triggers to keep FTS in sync
            try db.execute(sql: """
                CREATE TRIGGER screenshots_ai AFTER INSERT ON screenshots BEGIN
                    INSERT INTO screenshots_fts(rowid, ocrText, windowTitle)
                    VALUES (new.id, new.ocrText, new.windowTitle);
                END
                """)

            try db.execute(sql: """
                CREATE TRIGGER screenshots_ad AFTER DELETE ON screenshots BEGIN
                    INSERT INTO screenshots_fts(screenshots_fts, rowid, ocrText, windowTitle)
                    VALUES ('delete', old.id, old.ocrText, old.windowTitle);
                END
                """)

            try db.execute(sql: """
                CREATE TRIGGER screenshots_au AFTER UPDATE ON screenshots BEGIN
                    INSERT INTO screenshots_fts(screenshots_fts, rowid, ocrText, windowTitle)
                    VALUES ('delete', old.id, old.ocrText, old.windowTitle);
                    INSERT INTO screenshots_fts(rowid, ocrText, windowTitle)
                    VALUES (new.id, new.ocrText, new.windowTitle);
                END
                """)
        }

        // Migration 3: Create proactive_extractions table for memories, tasks, and advice
        migrator.registerMigration("createProactiveExtractions") { db in
            try db.create(table: "proactive_extractions") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("screenshotId", .integer)
                    .references("screenshots", onDelete: .cascade)
                t.column("type", .text).notNull() // memory, task, advice
                t.column("content", .text).notNull()
                t.column("category", .text) // memory: system/interesting, advice: productivity/health/etc
                t.column("confidence", .double)
                t.column("reasoning", .text)
                t.column("sourceApp", .text).notNull()
                t.column("contextSummary", .text)
                t.column("priority", .text) // For tasks: high/medium/low
                t.column("isRead", .boolean).notNull().defaults(to: false)
                t.column("isDismissed", .boolean).notNull().defaults(to: false)
                t.column("backendId", .text) // Server ID after sync
                t.column("backendSynced", .boolean).notNull().defaults(to: false)
                t.column("createdAt", .datetime).notNull()
                t.column("updatedAt", .datetime).notNull()
            }

            // Indexes for common queries
            try db.create(index: "idx_extractions_type", on: "proactive_extractions", columns: ["type"])
            try db.create(index: "idx_extractions_screenshot", on: "proactive_extractions", columns: ["screenshotId"])
            try db.create(index: "idx_extractions_synced", on: "proactive_extractions", columns: ["backendSynced"])
            try db.create(index: "idx_extractions_created", on: "proactive_extractions", columns: ["createdAt"])
            try db.create(index: "idx_extractions_type_created", on: "proactive_extractions", columns: ["type", "createdAt"])
        }

        // Migration 4: Create focus_sessions table for focus tracking
        migrator.registerMigration("createFocusSessions") { db in
            try db.create(table: "focus_sessions") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("screenshotId", .integer)
                    .references("screenshots", onDelete: .cascade)
                t.column("status", .text).notNull() // focused, distracted
                t.column("appOrSite", .text).notNull()
                t.column("description", .text).notNull()
                t.column("message", .text)
                t.column("durationSeconds", .integer)
                t.column("backendId", .text)
                t.column("backendSynced", .boolean).notNull().defaults(to: false)
                t.column("createdAt", .datetime).notNull()
            }

            // Indexes for time-based aggregation queries
            try db.create(index: "idx_focus_created", on: "focus_sessions", columns: ["createdAt"])
            try db.create(index: "idx_focus_status", on: "focus_sessions", columns: ["status"])
            try db.create(index: "idx_focus_screenshot", on: "focus_sessions", columns: ["screenshotId"])
            try db.create(index: "idx_focus_synced", on: "focus_sessions", columns: ["backendSynced"])
        }

        // Migration 5: Add ocrDataJson column for bounding boxes
        migrator.registerMigration("addOcrDataJson") { db in
            try db.alter(table: "screenshots") { t in
                t.add(column: "ocrDataJson", .text)
            }
        }

        // Migration 6: Create FTS for proactive_extractions content search
        migrator.registerMigration("createExtractionsFTS") { db in
            try db.execute(sql: """
                CREATE VIRTUAL TABLE proactive_extractions_fts USING fts5(
                    content,
                    reasoning,
                    contextSummary,
                    content='proactive_extractions',
                    content_rowid='id'
                )
                """)

            // Triggers to keep FTS in sync
            try db.execute(sql: """
                CREATE TRIGGER extractions_ai AFTER INSERT ON proactive_extractions BEGIN
                    INSERT INTO proactive_extractions_fts(rowid, content, reasoning, contextSummary)
                    VALUES (new.id, new.content, new.reasoning, new.contextSummary);
                END
                """)

            try db.execute(sql: """
                CREATE TRIGGER extractions_ad AFTER DELETE ON proactive_extractions BEGIN
                    INSERT INTO proactive_extractions_fts(proactive_extractions_fts, rowid, content, reasoning, contextSummary)
                    VALUES ('delete', old.id, old.content, old.reasoning, old.contextSummary);
                END
                """)

            try db.execute(sql: """
                CREATE TRIGGER extractions_au AFTER UPDATE ON proactive_extractions BEGIN
                    INSERT INTO proactive_extractions_fts(proactive_extractions_fts, rowid, content, reasoning, contextSummary)
                    VALUES ('delete', old.id, old.content, old.reasoning, old.contextSummary);
                    INSERT INTO proactive_extractions_fts(rowid, content, reasoning, contextSummary)
                    VALUES (new.id, new.content, new.reasoning, new.contextSummary);
                END
                """)
        }

        // Migration 7: Add video chunk storage columns
        migrator.registerMigration("addVideoChunkColumns") { db in
            try db.alter(table: "screenshots") { t in
                t.add(column: "videoChunkPath", .text)
                t.add(column: "frameOffset", .integer)
            }
            // Make imagePath nullable for new video-based screenshots
            // Note: SQLite doesn't support ALTER COLUMN, but new rows can have NULL imagePath

            // Index for efficient chunk-based queries
            try db.create(index: "idx_screenshots_videoChunkPath",
                          on: "screenshots", columns: ["videoChunkPath"])
        }

        // Migration 8: Rebuild FTS to include appName for better search
        migrator.registerMigration("rebuildFTSWithAppName") { db in
            // Drop old FTS table and triggers
            try db.execute(sql: "DROP TRIGGER IF EXISTS screenshots_ai")
            try db.execute(sql: "DROP TRIGGER IF EXISTS screenshots_ad")
            try db.execute(sql: "DROP TRIGGER IF EXISTS screenshots_au")
            try db.execute(sql: "DROP TABLE IF EXISTS screenshots_fts")

            // Create new FTS table with appName included
            try db.execute(sql: """
                CREATE VIRTUAL TABLE screenshots_fts USING fts5(
                    ocrText,
                    windowTitle,
                    appName,
                    content='screenshots',
                    content_rowid='id',
                    tokenize='unicode61'
                )
                """)

            // Recreate triggers to keep FTS in sync
            try db.execute(sql: """
                CREATE TRIGGER screenshots_ai AFTER INSERT ON screenshots BEGIN
                    INSERT INTO screenshots_fts(rowid, ocrText, windowTitle, appName)
                    VALUES (new.id, new.ocrText, new.windowTitle, new.appName);
                END
                """)

            try db.execute(sql: """
                CREATE TRIGGER screenshots_ad AFTER DELETE ON screenshots BEGIN
                    INSERT INTO screenshots_fts(screenshots_fts, rowid, ocrText, windowTitle, appName)
                    VALUES ('delete', old.id, old.ocrText, old.windowTitle, old.appName);
                END
                """)

            try db.execute(sql: """
                CREATE TRIGGER screenshots_au AFTER UPDATE ON screenshots BEGIN
                    INSERT INTO screenshots_fts(screenshots_fts, rowid, ocrText, windowTitle, appName)
                    VALUES ('delete', old.id, old.ocrText, old.windowTitle, old.appName);
                    INSERT INTO screenshots_fts(rowid, ocrText, windowTitle, appName)
                    VALUES (new.id, new.ocrText, new.windowTitle, new.appName);
                END
                """)

            // Repopulate FTS with existing data
            try db.execute(sql: """
                INSERT INTO screenshots_fts(rowid, ocrText, windowTitle, appName)
                SELECT id, ocrText, windowTitle, appName FROM screenshots
                """)
        }

        // Migration 9: Create normalized OCR storage tables
        migrator.registerMigration("createNormalizedOCR") { db in
            // Table 1: Unique OCR text content (deduplicated)
            try db.create(table: "ocr_texts") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("text", .text).notNull().unique()
                t.column("textHash", .text).notNull()  // SHA256 for fast lookup
                t.column("createdAt", .datetime).notNull()
            }
            try db.create(index: "idx_ocr_texts_hash", on: "ocr_texts", columns: ["textHash"])

            // Table 2: Where each text block appeared (bounding boxes + metadata)
            try db.create(table: "ocr_occurrences") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("ocrTextId", .integer).notNull()
                    .references("ocr_texts", onDelete: .cascade)
                t.column("screenshotId", .integer).notNull()
                    .references("screenshots", onDelete: .cascade)
                // Bounding box (normalized 0-1 coordinates)
                t.column("x", .double).notNull()
                t.column("y", .double).notNull()
                t.column("width", .double).notNull()
                t.column("height", .double).notNull()
                // Metadata
                t.column("confidence", .double)
                t.column("blockOrder", .integer).notNull()  // For reconstructing full text in order
            }
            try db.create(index: "idx_ocr_occurrences_screenshot",
                          on: "ocr_occurrences", columns: ["screenshotId"])
            try db.create(index: "idx_ocr_occurrences_text",
                          on: "ocr_occurrences", columns: ["ocrTextId"])
            // Unique constraint: same text can't appear twice at same position in same screenshot
            try db.create(
                index: "idx_ocr_occurrences_unique",
                on: "ocr_occurrences",
                columns: ["ocrTextId", "screenshotId", "blockOrder"],
                unique: true
            )

            // FTS5 on unique texts only (much smaller index than full ocrText!)
            try db.execute(sql: """
                CREATE VIRTUAL TABLE ocr_texts_fts USING fts5(
                    text,
                    content='ocr_texts',
                    content_rowid='id',
                    tokenize='unicode61'
                )
            """)

            // FTS sync triggers for ocr_texts
            try db.execute(sql: """
                CREATE TRIGGER ocr_texts_ai AFTER INSERT ON ocr_texts BEGIN
                    INSERT INTO ocr_texts_fts(rowid, text) VALUES (new.id, new.text);
                END
            """)
            try db.execute(sql: """
                CREATE TRIGGER ocr_texts_ad AFTER DELETE ON ocr_texts BEGIN
                    INSERT INTO ocr_texts_fts(ocr_texts_fts, rowid, text)
                    VALUES ('delete', old.id, old.text);
                END
            """)

            // Migration status tracking table
            try db.execute(sql: """
                CREATE TABLE IF NOT EXISTS migration_status (
                    name TEXT PRIMARY KEY,
                    completed INTEGER DEFAULT 0,
                    processedCount INTEGER DEFAULT 0,
                    startedAt DATETIME,
                    completedAt DATETIME
                )
            """)
            try db.execute(sql: """
                INSERT OR IGNORE INTO migration_status (name, completed, startedAt)
                VALUES ('ocr_normalization', 0, datetime('now'))
            """)
        }

        // Migration 10: Create transcription storage tables for crash-safe recording
        migrator.registerMigration("createTranscriptionStorage") { db in
            // Recording sessions (parent)
            try db.create(table: "transcription_sessions") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("startedAt", .datetime).notNull()
                t.column("finishedAt", .datetime)
                t.column("source", .text).notNull()              // 'desktop', 'omi', etc.
                t.column("language", .text).notNull().defaults(to: "en")
                t.column("timezone", .text).notNull().defaults(to: "UTC")
                t.column("inputDeviceName", .text)
                t.column("status", .text).notNull().defaults(to: "recording")  // recording|pending_upload|uploading|completed|failed
                t.column("retryCount", .integer).notNull().defaults(to: 0)
                t.column("lastError", .text)
                t.column("backendId", .text)                     // Server conversation ID
                t.column("backendSynced", .boolean).notNull().defaults(to: false)
                t.column("createdAt", .datetime).notNull()
                t.column("updatedAt", .datetime).notNull()
            }

            // Transcript segments (child)
            try db.create(table: "transcription_segments") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("sessionId", .integer).notNull()
                    .references("transcription_sessions", onDelete: .cascade)
                t.column("speaker", .integer).notNull()
                t.column("text", .text).notNull()
                t.column("startTime", .double).notNull()
                t.column("endTime", .double).notNull()
                t.column("segmentOrder", .integer).notNull()
                t.column("createdAt", .datetime).notNull()
            }

            // Indexes for common queries
            try db.create(index: "idx_sessions_status", on: "transcription_sessions", columns: ["status"])
            try db.create(index: "idx_sessions_synced", on: "transcription_sessions", columns: ["backendSynced"])
            try db.create(index: "idx_segments_session", on: "transcription_segments", columns: ["sessionId"])
        }

        // Migration 11: Create live_notes table for AI-generated notes during recording
        migrator.registerMigration("createLiveNotes") { db in
            try db.create(table: "live_notes") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("sessionId", .integer).notNull()
                    .references("transcription_sessions", onDelete: .cascade)
                t.column("text", .text).notNull()
                t.column("timestamp", .datetime).notNull()
                t.column("isAiGenerated", .boolean).notNull().defaults(to: true)
                t.column("segmentStartOrder", .integer)  // Which segment triggered this note
                t.column("segmentEndOrder", .integer)    // End segment for context range
                t.column("createdAt", .datetime).notNull()
                t.column("updatedAt", .datetime).notNull()
            }

            // Index for fetching notes by session
            try db.create(index: "idx_live_notes_session", on: "live_notes", columns: ["sessionId"])
        }

        // Migration 12: Expand transcription storage to match full ServerConversation schema
        migrator.registerMigration("expandTranscriptionSchema") { db in
            // Add structured data columns to transcription_sessions
            try db.alter(table: "transcription_sessions") { t in
                t.add(column: "title", .text)
                t.add(column: "overview", .text)
                t.add(column: "emoji", .text)
                t.add(column: "category", .text)
                t.add(column: "actionItemsJson", .text)
                t.add(column: "eventsJson", .text)
            }

            // Add additional conversation data columns
            try db.alter(table: "transcription_sessions") { t in
                t.add(column: "geolocationJson", .text)
                t.add(column: "photosJson", .text)
                t.add(column: "appsResultsJson", .text)
            }

            // Add conversation status and flags
            try db.alter(table: "transcription_sessions") { t in
                t.add(column: "conversationStatus", .text).defaults(to: "in_progress")
                t.add(column: "discarded", .boolean).defaults(to: false)
                t.add(column: "deleted", .boolean).defaults(to: false)
                t.add(column: "isLocked", .boolean).defaults(to: false)
                t.add(column: "starred", .boolean).defaults(to: false)
                t.add(column: "folderId", .text)
            }

            // Add backend segment data columns to transcription_segments
            try db.alter(table: "transcription_segments") { t in
                t.add(column: "segmentId", .text)
                t.add(column: "speakerLabel", .text)
                t.add(column: "isUser", .boolean).defaults(to: false)
                t.add(column: "personId", .text)
            }

            // Add index for backendId lookups (for syncing)
            try db.create(index: "idx_sessions_backendId", on: "transcription_sessions", columns: ["backendId"])

            // Add index for conversation status filtering
            try db.create(index: "idx_sessions_conversationStatus", on: "transcription_sessions", columns: ["conversationStatus"])

            // Add index for starred conversations
            try db.create(index: "idx_sessions_starred", on: "transcription_sessions", columns: ["starred"])
        }

        // Migration 13: Create task dedup log table for AI deletion tracking
        migrator.registerMigration("createTaskDedupLog") { db in
            try db.create(table: "task_dedup_log") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("deletedTaskId", .text).notNull()
                t.column("deletedDescription", .text).notNull()
                t.column("keptTaskId", .text).notNull()
                t.column("keptDescription", .text).notNull()
                t.column("reason", .text).notNull()
                t.column("deletedAt", .datetime).notNull()
            }
            try db.create(index: "idx_dedup_log_deleted_at",
                          on: "task_dedup_log", columns: ["deletedAt"])
        }

        // Migration 14: Create unified memories table for local-first pattern
        // Stores all memories (extracted, advice/tips, focus-tagged) with bidirectional sync
        migrator.registerMigration("createMemoriesTable") { db in
            try db.create(table: "memories") { t in
                t.autoIncrementedPrimaryKey("id")

                // Backend sync fields
                t.column("backendId", .text).unique()       // Server memory ID
                t.column("backendSynced", .boolean).notNull().defaults(to: false)

                // Core ServerMemory fields
                t.column("content", .text).notNull()
                t.column("category", .text).notNull()       // system, interesting, manual
                t.column("tagsJson", .text)                 // JSON array: ["tips"], ["focus", "focused"]
                t.column("visibility", .text).notNull().defaults(to: "private")
                t.column("reviewed", .boolean).notNull().defaults(to: false)
                t.column("userReview", .boolean)
                t.column("manuallyAdded", .boolean).notNull().defaults(to: false)
                t.column("scoring", .text)
                t.column("source", .text)                   // desktop, omi, screenshot, phone
                t.column("conversationId", .text)

                // Desktop extraction fields
                t.column("screenshotId", .integer)
                    .references("screenshots", onDelete: .setNull)
                t.column("confidence", .double)
                t.column("reasoning", .text)
                t.column("sourceApp", .text)
                t.column("contextSummary", .text)
                t.column("currentActivity", .text)
                t.column("inputDeviceName", .text)

                // Status flags
                t.column("isRead", .boolean).notNull().defaults(to: false)
                t.column("isDismissed", .boolean).notNull().defaults(to: false)
                t.column("deleted", .boolean).notNull().defaults(to: false)

                // Timestamps
                t.column("createdAt", .datetime).notNull()
                t.column("updatedAt", .datetime).notNull()
            }

            // Indexes for common queries
            try db.create(index: "idx_memories_backend_id", on: "memories", columns: ["backendId"])
            try db.create(index: "idx_memories_created", on: "memories", columns: ["createdAt"])
            try db.create(index: "idx_memories_category", on: "memories", columns: ["category"])
            try db.create(index: "idx_memories_synced", on: "memories", columns: ["backendSynced"])
            try db.create(index: "idx_memories_screenshot", on: "memories", columns: ["screenshotId"])
            try db.create(index: "idx_memories_deleted", on: "memories", columns: ["deleted"])

            // Migrate existing memories from proactive_extractions
            // Use INSERT OR IGNORE to handle duplicate backendIds gracefully
            // For records with NULL backendId (unsynced), we insert all of them
            // For records with non-NULL backendId (synced), we keep only the first one per backendId
            try db.execute(sql: """
                INSERT OR IGNORE INTO memories (
                    backendId, backendSynced, content, category, tagsJson, visibility,
                    reviewed, manuallyAdded, source, screenshotId, confidence, reasoning,
                    sourceApp, contextSummary, isRead, isDismissed, deleted, createdAt, updatedAt
                )
                SELECT
                    backendId, backendSynced, content,
                    CASE WHEN category IS NULL THEN 'system' ELSE category END,
                    CASE
                        WHEN type = 'advice' THEN json_array('tips', COALESCE(category, 'other'))
                        ELSE NULL
                    END,
                    'private',
                    0, 0, 'screenshot', screenshotId, confidence, reasoning,
                    sourceApp, contextSummary, isRead, isDismissed, 0, createdAt, updatedAt
                FROM proactive_extractions
                WHERE type IN ('memory', 'advice')
                ORDER BY createdAt DESC
            """)
        }

        // Migration 15: Create action_items table for tasks with bidirectional sync
        migrator.registerMigration("createActionItemsTable") { db in
            try db.create(table: "action_items") { t in
                t.autoIncrementedPrimaryKey("id")

                // Backend sync fields
                t.column("backendId", .text).unique()       // Server action item ID
                t.column("backendSynced", .boolean).notNull().defaults(to: false)

                // Core ActionItem fields
                t.column("description", .text).notNull()
                t.column("completed", .boolean).notNull().defaults(to: false)
                t.column("deleted", .boolean).notNull().defaults(to: false)
                t.column("source", .text)                   // screenshot, conversation, omi
                t.column("conversationId", .text)
                t.column("priority", .text)                 // high, medium, low
                t.column("category", .text)
                t.column("dueAt", .datetime)

                // Desktop extraction fields
                t.column("screenshotId", .integer)
                    .references("screenshots", onDelete: .setNull)
                t.column("confidence", .double)
                t.column("sourceApp", .text)
                t.column("contextSummary", .text)
                t.column("currentActivity", .text)
                t.column("metadataJson", .text)             // Additional extraction metadata

                // Timestamps
                t.column("createdAt", .datetime).notNull()
                t.column("updatedAt", .datetime).notNull()
            }

            // Indexes for common queries
            try db.create(index: "idx_action_items_backend_id", on: "action_items", columns: ["backendId"])
            try db.create(index: "idx_action_items_created", on: "action_items", columns: ["createdAt"])
            try db.create(index: "idx_action_items_completed", on: "action_items", columns: ["completed"])
            try db.create(index: "idx_action_items_synced", on: "action_items", columns: ["backendSynced"])
            try db.create(index: "idx_action_items_deleted", on: "action_items", columns: ["deleted"])
            try db.create(index: "idx_action_items_due", on: "action_items", columns: ["dueAt"])

            // Migrate existing tasks from proactive_extractions
            // Use INSERT OR IGNORE to handle duplicate backendIds gracefully
            try db.execute(sql: """
                INSERT OR IGNORE INTO action_items (
                    backendId, backendSynced, description, completed, deleted, source,
                    priority, category, screenshotId, confidence, sourceApp, contextSummary,
                    createdAt, updatedAt
                )
                SELECT
                    backendId, backendSynced, content, 0, 0, 'screenshot',
                    priority, category, screenshotId, confidence, sourceApp, contextSummary,
                    createdAt, updatedAt
                FROM proactive_extractions
                WHERE type = 'task'
                ORDER BY createdAt DESC
            """)
        }

        // Migration 16: Add tagsJson column to action_items for multi-tag support
        migrator.registerMigration("addActionItemTagsJson") { db in
            try db.alter(table: "action_items") { t in
                t.add(column: "tagsJson", .text)
            }

            // Migrate existing rows: populate tagsJson from category
            try db.execute(sql: """
                UPDATE action_items SET tagsJson = json_array(category) WHERE category IS NOT NULL
            """)
        }

        // Migration 17: Add deletedBy column to action_items for tracking who deleted
        migrator.registerMigration("addActionItemDeletedBy") { db in
            try db.alter(table: "action_items") { t in
                t.add(column: "deletedBy", .text)  // "user", "ai_dedup"
            }
        }

        // Migration 18: Add embedding column to action_items for vector search
        migrator.registerMigration("addActionItemEmbedding") { db in
            try db.alter(table: "action_items") { t in
                t.add(column: "embedding", .blob)  // 3072 Float32s = 12288 bytes (Gemini embedding-001)
            }
        }

        // Migration 19: Create FTS5 virtual table on action_items.description for keyword search
        migrator.registerMigration("createActionItemsFTS") { db in
            try db.execute(sql: """
                CREATE VIRTUAL TABLE action_items_fts USING fts5(
                    description,
                    content='action_items',
                    content_rowid='id',
                    tokenize='unicode61'
                )
                """)

            // Sync triggers
            try db.execute(sql: """
                CREATE TRIGGER action_items_fts_ai AFTER INSERT ON action_items BEGIN
                    INSERT INTO action_items_fts(rowid, description)
                    VALUES (new.id, new.description);
                END
                """)

            try db.execute(sql: """
                CREATE TRIGGER action_items_fts_ad AFTER DELETE ON action_items BEGIN
                    INSERT INTO action_items_fts(action_items_fts, rowid, description)
                    VALUES ('delete', old.id, old.description);
                END
                """)

            try db.execute(sql: """
                CREATE TRIGGER action_items_fts_au AFTER UPDATE ON action_items BEGIN
                    INSERT INTO action_items_fts(action_items_fts, rowid, description)
                    VALUES ('delete', old.id, old.description);
                    INSERT INTO action_items_fts(rowid, description)
                    VALUES (new.id, new.description);
                END
                """)

            // Populate with existing data
            try db.execute(sql: """
                INSERT INTO action_items_fts(rowid, description)
                SELECT id, description FROM action_items
                """)
        }

        // Migration 20: Create ai_user_profiles table for daily AI-generated user profile history
        migrator.registerMigration("createAIUserProfiles") { db in
            try db.create(table: "ai_user_profiles") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("profileText", .text).notNull()
                t.column("dataSourcesUsed", .integer).notNull()
                t.column("backendSynced", .boolean).notNull().defaults(to: false)
                t.column("generatedAt", .datetime).notNull()
            }

            try db.create(index: "idx_ai_user_profiles_generated",
                          on: "ai_user_profiles", columns: ["generatedAt"])
        }

        // Migrations 21-22: One-time data cleanup (already applied, kept for GRDB migration history)
        migrator.registerMigration("clearAIUserProfilesV1") { _ in }
        migrator.registerMigration("clearAIUserProfilesV2") { _ in }

        // Migration 23: Add window title to action items
        migrator.registerMigration("addActionItemWindowTitle") { db in
            try db.alter(table: "action_items") { t in
                t.add(column: "windowTitle", .text)
            }
        }

        // Migration 24: Create observations table for screen context tracking
        migrator.registerMigration("createObservations") { db in
            try db.create(table: "observations") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("screenshotId", .integer).references("screenshots", onDelete: .setNull)
                t.column("appName", .text).notNull()
                t.column("contextSummary", .text).notNull()
                t.column("currentActivity", .text).notNull()
                t.column("hasTask", .boolean).notNull().defaults(to: false)
                t.column("taskTitle", .text)
                t.column("sourceCategory", .text)
                t.column("sourceSubcategory", .text)
                t.column("metadataJson", .text)
                t.column("createdAt", .datetime).notNull()
            }

            try db.create(index: "idx_observations_created", on: "observations", columns: ["createdAt"])
            try db.create(index: "idx_observations_app", on: "observations", columns: ["appName"])
            try db.create(index: "idx_observations_screenshot", on: "observations", columns: ["screenshotId"])
        }

        // Migration 25: Add window title to memories table
        migrator.registerMigration("addMemoryWindowTitle") { db in
            try db.alter(table: "memories") { t in
                t.add(column: "windowTitle", .text)
            }
        }

        // Migration 26: Add window title to focus_sessions table
        migrator.registerMigration("addFocusSessionWindowTitle") { db in
            try db.alter(table: "focus_sessions") { t in
                t.add(column: "windowTitle", .text)
            }
        }

        migrator.registerMigration("backfillActionItemDueAt") { db in
            // Set dueAt to createdAt date at 23:59:00 for all items missing a due date
            // Since createdAt is stored as UTC, we add time to reach end of that UTC day
            // (approximate — exact local timezone conversion isn't possible in pure SQL,
            // but this is close enough for existing tasks)
            try db.execute(sql: """
                UPDATE action_items
                SET dueAt = datetime(date(createdAt), '+23 hours', '+59 minutes'),
                    updatedAt = datetime('now')
                WHERE dueAt IS NULL AND deleted = 0
            """)
        }

        // Migration 28: Add relevance score column for task prioritization
        migrator.registerMigration("addActionItemRelevanceScore") { db in
            try db.alter(table: "action_items") { t in
                t.add(column: "relevanceScore", .integer)
                t.add(column: "scoredAt", .datetime)
            }
        }

        // Migration 29: Backfill relevanceScore for all active tasks with unique sequential values.
        // Already-scored tasks keep their relative order. Unscored tasks go to the bottom.
        // This ensures every active task has a unique relevanceScore (no NULLs, no duplicates).
        migrator.registerMigration("backfillRelevanceScoreSequential") { db in
            // Assign sequential scores 1..N to all active (incomplete, non-deleted) tasks.
            // Ordering: unscored tasks first (by createdAt), then scored tasks (by score).
            // ROW_NUMBER 1 = least relevant (bottom), N = most relevant (top).
            try db.execute(sql: """
                UPDATE action_items
                SET relevanceScore = (
                    SELECT rn FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (
                                   ORDER BY
                                       CASE WHEN relevanceScore IS NOT NULL THEN 1 ELSE 0 END,
                                       COALESCE(relevanceScore, 0),
                                       createdAt
                               ) as rn
                        FROM action_items
                        WHERE completed = 0 AND deleted = 0
                    ) ranked
                    WHERE ranked.id = action_items.id
                ),
                scoredAt = datetime('now')
                WHERE completed = 0 AND deleted = 0
            """)
        }

        // Migration 30: Fix duplicate relevanceScores from migration 29.
        // Migration 29 had a self-referencing UPDATE bug where SQLite reads modified data
        // during the UPDATE loop. Fix: snapshot into a temp table first, then update from it.
        // Score 1 = most important (top), N = least important (bottom).
        migrator.registerMigration("fixRelevanceScoreDuplicates") { db in
            // 1. Snapshot the correct sequential mapping into a temp table
            // ORDER BY DESC so ROW_NUMBER 1 = highest original score = most important
            try db.execute(sql: """
                CREATE TEMP TABLE _score_map AS
                SELECT id,
                       ROW_NUMBER() OVER (
                           ORDER BY
                               COALESCE(relevanceScore, 0) DESC,
                               createdAt ASC
                       ) as new_score
                FROM action_items
                WHERE completed = 0 AND deleted = 0
            """)

            // 2. Update from the snapshot (no self-reference)
            try db.execute(sql: """
                UPDATE action_items
                SET relevanceScore = (
                    SELECT new_score FROM _score_map
                    WHERE _score_map.id = action_items.id
                ),
                scoredAt = datetime('now')
                WHERE id IN (SELECT id FROM _score_map)
            """)

            // 3. Clean up
            try db.execute(sql: "DROP TABLE _score_map")
        }

        // Migration 31: Re-assign clean sequential scores with correct ordering.
        // Score 1 = most important (top), N = least important (bottom).
        // Fixes duplicates at 0 and 100 introduced by old shift logic and prioritization service.
        migrator.registerMigration("reassignRelevanceScoresDescending") { db in
            try db.execute(sql: """
                CREATE TEMP TABLE _score_map2 AS
                SELECT id,
                       ROW_NUMBER() OVER (
                           ORDER BY
                               COALESCE(relevanceScore, 999999) ASC,
                               createdAt ASC
                       ) as new_score
                FROM action_items
                WHERE completed = 0 AND deleted = 0
            """)

            try db.execute(sql: """
                UPDATE action_items
                SET relevanceScore = (
                    SELECT new_score FROM _score_map2
                    WHERE _score_map2.id = action_items.id
                ),
                scoredAt = datetime('now')
                WHERE id IN (SELECT id FROM _score_map2)
            """)

            try db.execute(sql: "DROP TABLE _score_map2")
        }

        // Migration 32: Delete orphaned unsynced action items that have synced duplicates.
        // These were created when saveTaskToSQLite succeeded but markSynced failed,
        // and a later full sync pulled the same task from the backend as a new record.
        // The orphan has no backendId; the duplicate has the proper backendId.
        migrator.registerMigration("deleteOrphanedUnsyncedActionItems") { db in
            let deleted = try Int.fetchOne(db, sql: """
                SELECT COUNT(*) FROM action_items
                WHERE (backendId IS NULL OR backendId = '')
                  AND backendSynced = 0
                  AND EXISTS (
                    SELECT 1 FROM action_items dup
                    WHERE dup.description = action_items.description
                      AND dup.source = action_items.source
                      AND dup.backendId IS NOT NULL AND dup.backendId <> ''
                      AND dup.id <> action_items.id
                  )
            """) ?? 0

            try db.execute(sql: """
                DELETE FROM action_items
                WHERE (backendId IS NULL OR backendId = '')
                  AND backendSynced = 0
                  AND EXISTS (
                    SELECT 1 FROM action_items dup
                    WHERE dup.description = action_items.description
                      AND dup.source = action_items.source
                      AND dup.backendId IS NOT NULL AND dup.backendId <> ''
                      AND dup.id <> action_items.id
                  )
            """)

            print("[RewindDatabase] Migration 32: Deleted \(deleted) orphaned unsynced action items with synced duplicates")
        }

        migrator.registerMigration("addScreenshotEmbedding") { db in
            try db.alter(table: "screenshots") { t in
                t.add(column: "embedding", .blob)
            }
            // Partial index for backfill queries
            try db.execute(sql: """
                CREATE INDEX idx_screenshots_missing_embedding
                ON screenshots(id) WHERE embedding IS NULL AND ocrText IS NOT NULL
            """)
            // Track backfill progress
            try db.execute(sql: """
                INSERT OR IGNORE INTO migration_status (name, completed, startedAt)
                VALUES ('ocr_embedding_backfill', 0, datetime('now'))
            """)
            print("[RewindDatabase] Migration 33: Added embedding column to screenshots")
        }

        migrator.registerMigration("addOCRTextEmbedding") { db in
            try db.alter(table: "ocr_texts") { t in
                t.add(column: "embedding", .blob)
            }
            // Partial index for backfill queries
            try db.execute(sql: """
                CREATE INDEX idx_ocr_texts_missing_embedding
                ON ocr_texts(id) WHERE embedding IS NULL
            """)
            // Track backfill progress
            try db.execute(sql: """
                INSERT OR IGNORE INTO migration_status (name, completed, startedAt)
                VALUES ('ocr_text_embedding_backfill', 0, datetime('now'))
            """)
            // Mark old screenshot embedding backfill as complete (no longer needed)
            try db.execute(sql: """
                UPDATE migration_status SET completed = 1, completedAt = datetime('now')
                WHERE name = 'ocr_embedding_backfill'
            """)
            print("[RewindDatabase] Migration 34: Added embedding column to ocr_texts")
        }

        migrator.registerMigration("addAgentSessionFields") { db in
            try db.alter(table: "action_items") { t in
                t.add(column: "agentStatus", .text)
                t.add(column: "agentSessionName", .text)
                t.add(column: "agentPrompt", .text)
                t.add(column: "agentPlan", .text)
                t.add(column: "agentStartedAt", .datetime)
                t.add(column: "agentCompletedAt", .datetime)
                t.add(column: "agentEditedFilesJson", .text)
            }
            try db.execute(sql: """
                CREATE INDEX idx_action_items_active_agent
                ON action_items(agentStatus)
                WHERE agentStatus IS NOT NULL AND agentStatus NOT IN ('completed', 'failed')
            """)
            print("[RewindDatabase] Migration 35: Added agent session fields to action_items")
        }

        migrator.registerMigration("addSkippedForBattery") { db in
            try db.alter(table: "screenshots") { t in
                t.add(column: "skippedForBattery", .boolean).notNull().defaults(to: false)
            }
        }

        migrator.registerMigration("switchToScreenshotEmbeddings") { db in
            // Clear old per-block embeddings from ocr_texts (no longer used for search)
            try db.execute(sql: "UPDATE ocr_texts SET embedding = NULL WHERE embedding IS NOT NULL")
            // Drop the ocr_texts embedding index
            try db.execute(sql: "DROP INDEX IF EXISTS idx_ocr_texts_missing_embedding")
            // Mark ocr_text backfill as complete (abandoned)
            try db.execute(sql: """
                UPDATE migration_status SET completed = 1, completedAt = datetime('now')
                WHERE name = 'ocr_text_embedding_backfill'
            """)
            // Clear any old screenshot embeddings (from migration 33, wrong granularity)
            try db.execute(sql: "UPDATE screenshots SET embedding = NULL WHERE embedding IS NOT NULL")
            // Reset screenshot embedding backfill to start fresh
            try db.execute(sql: """
                INSERT OR REPLACE INTO migration_status (name, completed, startedAt, processedCount)
                VALUES ('screenshot_embedding_backfill', 0, datetime('now'), 0)
            """)
            print("[RewindDatabase] Migration: Switched to per-screenshot embeddings, reset backfill")
        }

        migrator.registerMigration("reEmbedWithTaskTypes") { db in
            // Clear embeddings created without RETRIEVAL_DOCUMENT task type
            try db.execute(sql: "UPDATE screenshots SET embedding = NULL WHERE embedding IS NOT NULL")
            // Reset backfill to re-embed with task types
            try db.execute(sql: """
                UPDATE migration_status
                SET completed = 0, processedCount = 0, startedAt = datetime('now'), completedAt = NULL
                WHERE name = 'screenshot_embedding_backfill'
            """)
            print("[RewindDatabase] Migration: Reset embeddings for RETRIEVAL_DOCUMENT task type re-backfill")
        }

        migrator.registerMigration("dropNormalizedOCRTables") { db in
            // These tables are unused — all search uses screenshots_fts,
            // all embeddings use screenshots.embedding
            try db.drop(table: "ocr_texts_fts")
            try db.drop(table: "ocr_occurrences")
            try db.drop(table: "ocr_texts")
            // Mark the normalization migration as no longer needed
            try db.execute(sql: """
                UPDATE migration_status SET completed = 1, completedAt = datetime('now')
                WHERE name = 'ocr_normalization'
            """)
            // Track precision reduction migration
            try db.execute(sql: """
                INSERT OR IGNORE INTO migration_status (name, completed, startedAt)
                VALUES ('ocr_precision_reduction', 0, datetime('now'))
            """)
        }

        migrator.registerMigration("resumeEmbeddingBackfill") { db in
            // Fix: previous backfill could mark completed on API error,
            // leaving some screenshots without embeddings. Reset to resume.
            let missing = try Int64.fetchOne(db, sql: """
                SELECT COUNT(*) FROM screenshots
                WHERE embedding IS NULL AND ocrText IS NOT NULL AND LENGTH(ocrText) >= 20
            """) ?? 0
            if missing > 0 {
                try db.execute(sql: """
                    UPDATE migration_status SET completed = 0
                    WHERE name = 'screenshot_embedding_backfill'
                """)
            }
        }

        migrator.registerMigration("fullEmbeddingBackfillV2") { db in
            // Clear ALL embeddings to ensure everyone gets fresh Gemini embeddings
            // Previous versions may have had:
            // - Test limit (only 1000 items embedded)
            // - Incomplete backfills
            // - Wrong embedding parameters
            // This migration ensures all users start fresh with correct embeddings
            try db.execute(sql: "UPDATE screenshots SET embedding = NULL WHERE embedding IS NOT NULL")

            // Reset backfill status to process all screenshots
            try db.execute(sql: """
                UPDATE migration_status
                SET completed = 0, processedCount = 0, startedAt = datetime('now'), completedAt = NULL
                WHERE name = 'screenshot_embedding_backfill'
            """)

            print("[RewindDatabase] Migration: Cleared all embeddings for full Gemini backfill (no test limit)")
        }

        migrator.registerMigration("createGoalsTable") { db in
            try db.create(table: "goals") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("backendId", .text).unique()
                t.column("backendSynced", .boolean).notNull().defaults(to: false)
                t.column("title", .text).notNull()
                t.column("goalDescription", .text)
                t.column("goalType", .text).notNull().defaults(to: "boolean")
                t.column("targetValue", .double).notNull().defaults(to: 1.0)
                t.column("currentValue", .double).notNull().defaults(to: 0.0)
                t.column("minValue", .double).notNull().defaults(to: 0.0)
                t.column("maxValue", .double).notNull().defaults(to: 100.0)
                t.column("unit", .text)
                t.column("isActive", .boolean).notNull().defaults(to: true)
                t.column("completedAt", .datetime)
                t.column("deleted", .boolean).notNull().defaults(to: false)
                t.column("createdAt", .datetime).notNull()
                t.column("updatedAt", .datetime).notNull()
            }
        }

        migrator.registerMigration("addActionItemChatSessionId") { db in
            try db.alter(table: "action_items") { t in
                t.add(column: "chatSessionId", .text)
            }
        }

        // Migration: Create staged_tasks table for AI task staging before promotion
        migrator.registerMigration("createStagedTasksTable") { db in
            try db.create(table: "staged_tasks") { t in
                t.autoIncrementedPrimaryKey("id")

                // Backend sync fields
                t.column("backendId", .text).unique()
                t.column("backendSynced", .boolean).notNull().defaults(to: false)

                // Core fields (same as action_items minus agent fields)
                t.column("description", .text).notNull()
                t.column("completed", .boolean).notNull().defaults(to: false)
                t.column("deleted", .boolean).notNull().defaults(to: false)
                t.column("source", .text)
                t.column("conversationId", .text)
                t.column("priority", .text)
                t.column("category", .text)
                t.column("tagsJson", .text)
                t.column("deletedBy", .text)
                t.column("dueAt", .datetime)

                // Desktop extraction fields
                t.column("screenshotId", .integer)
                    .references("screenshots", onDelete: .setNull)
                t.column("confidence", .double)
                t.column("sourceApp", .text)
                t.column("windowTitle", .text)
                t.column("contextSummary", .text)
                t.column("currentActivity", .text)
                t.column("metadataJson", .text)
                t.column("embedding", .blob)

                // Prioritization fields
                t.column("relevanceScore", .integer)
                t.column("scoredAt", .datetime)

                // Timestamps
                t.column("createdAt", .datetime).notNull()
                t.column("updatedAt", .datetime).notNull()
            }

            // Indexes
            try db.create(index: "idx_staged_tasks_backend_id", on: "staged_tasks", columns: ["backendId"])
            try db.create(index: "idx_staged_tasks_score", on: "staged_tasks", columns: ["relevanceScore"])
            try db.create(index: "idx_staged_tasks_created", on: "staged_tasks", columns: ["createdAt"])
            try db.create(index: "idx_staged_tasks_completed", on: "staged_tasks", columns: ["completed"])
            try db.create(index: "idx_staged_tasks_deleted", on: "staged_tasks", columns: ["deleted"])
        }

        // Migration: Create FTS5 index for staged_tasks
        migrator.registerMigration("createStagedTasksFTS") { db in
            try db.execute(sql: """
                CREATE VIRTUAL TABLE staged_tasks_fts USING fts5(
                    description,
                    content='staged_tasks',
                    content_rowid='id',
                    tokenize='unicode61'
                )
                """)

            try db.execute(sql: """
                CREATE TRIGGER staged_tasks_fts_ai AFTER INSERT ON staged_tasks BEGIN
                    INSERT INTO staged_tasks_fts(rowid, description)
                    VALUES (new.id, new.description);
                END
                """)

            try db.execute(sql: """
                CREATE TRIGGER staged_tasks_fts_ad AFTER DELETE ON staged_tasks BEGIN
                    INSERT INTO staged_tasks_fts(staged_tasks_fts, rowid, description)
                    VALUES ('delete', old.id, old.description);
                END
                """)

            try db.execute(sql: """
                CREATE TRIGGER staged_tasks_fts_au AFTER UPDATE OF description ON staged_tasks BEGIN
                    INSERT INTO staged_tasks_fts(staged_tasks_fts, rowid, description)
                    VALUES ('delete', old.id, old.description);
                    INSERT INTO staged_tasks_fts(rowid, description)
                    VALUES (new.id, new.description);
                END
                """)

            // Populate from existing rows
            try db.execute(sql: """
                INSERT INTO staged_tasks_fts(rowid, description)
                SELECT id, description FROM staged_tasks
                """)
        }

        // One-time migration: move non-top-5 AI tasks from action_items to staged_tasks
        migrator.registerMigration("migrateAITasksToStaged") { db in
            // Get all AI-extracted (screenshot) tasks that are active
            let aiTasks = try Row.fetchAll(db, sql: """
                SELECT * FROM action_items
                WHERE source LIKE '%screenshot%'
                AND (completed IS NULL OR completed = 0)
                AND (deleted IS NULL OR deleted = 0)
                ORDER BY relevanceScore ASC NULLS LAST, createdAt DESC
                """)

            guard !aiTasks.isEmpty else { return }

            // Top 5 stay in action_items with [screen] suffix
            let top5 = Array(aiTasks.prefix(5))
            let rest = Array(aiTasks.dropFirst(5))

            // Add [screen] suffix to top 5 descriptions if not already tagged
            for task in top5 {
                let desc = task["description"] as? String ?? ""
                if !desc.hasSuffix(" [screen]") && !desc.hasPrefix("[screen]") {
                    try db.execute(
                        sql: "UPDATE action_items SET description = ? WHERE id = ?",
                        arguments: [desc + " [screen]", task["id"]]
                    )
                }
            }

            // Move the rest to staged_tasks
            for task in rest {
                try db.execute(sql: """
                    INSERT OR IGNORE INTO staged_tasks (
                        backendId, backendSynced, description, completed, deleted,
                        source, conversationId, priority, category, tagsJson,
                        deletedBy, dueAt, screenshotId, confidence, sourceApp,
                        windowTitle, contextSummary, currentActivity, metadataJson,
                        embedding, relevanceScore, scoredAt, createdAt, updatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, arguments: [
                        task["backendId"], task["backendSynced"],
                        task["description"], task["completed"], task["deleted"],
                        task["source"], task["conversationId"], task["priority"],
                        task["category"], task["tagsJson"], task["deletedBy"],
                        task["dueAt"], task["screenshotId"], task["confidence"],
                        task["sourceApp"], task["windowTitle"], task["contextSummary"],
                        task["currentActivity"], task["metadataJson"], task["embedding"],
                        task["relevanceScore"], task["scoredAt"],
                        task["createdAt"], task["updatedAt"]
                    ])

                // Delete from action_items
                try db.execute(
                    sql: "DELETE FROM action_items WHERE id = ?",
                    arguments: [task["id"]]
                )
            }
        }

        migrator.registerMigration("addActionItemSortOrder") { db in
            try db.execute(sql: "ALTER TABLE action_items ADD COLUMN sortOrder INTEGER")
            try db.execute(sql: "ALTER TABLE action_items ADD COLUMN indentLevel INTEGER")
        }

        // Migration: Delete orphaned unsynced memories that have synced duplicates.
        // Same race condition as action_items migration 32: insertLocalMemory succeeded
        // but before markSynced ran, syncServerMemories pulled the same memory from the
        // API and inserted a second record with the proper backendId.
        migrator.registerMigration("deleteOrphanedUnsyncedMemories") { db in
            let deleted = try Int.fetchOne(db, sql: """
                SELECT COUNT(*) FROM memories
                WHERE (backendId IS NULL OR backendId = '')
                  AND backendSynced = 0
                  AND EXISTS (
                    SELECT 1 FROM memories dup
                    WHERE dup.content = memories.content
                      AND dup.backendId IS NOT NULL AND dup.backendId <> ''
                      AND dup.id <> memories.id
                  )
            """) ?? 0

            try db.execute(sql: """
                DELETE FROM memories
                WHERE (backendId IS NULL OR backendId = '')
                  AND backendSynced = 0
                  AND EXISTS (
                    SELECT 1 FROM memories dup
                    WHERE dup.content = memories.content
                      AND dup.backendId IS NOT NULL AND dup.backendId <> ''
                      AND dup.id <> memories.id
                  )
            """)

            print("[RewindDatabase] Migration: Deleted \(deleted) orphaned unsynced memories with synced duplicates")
        }

        migrator.registerMigration("addActionItemFromStaged") { db in
            try db.execute(sql: "ALTER TABLE action_items ADD COLUMN fromStaged BOOLEAN NOT NULL DEFAULT 0")
        }

        migrator.registerMigration("createIndexedFiles") { db in
            try db.create(table: "indexed_files") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("path", .text).notNull()
                t.column("filename", .text).notNull()
                t.column("fileExtension", .text)
                t.column("fileType", .text).notNull()
                t.column("sizeBytes", .integer).notNull()
                t.column("folder", .text).notNull()
                t.column("depth", .integer).notNull()
                t.column("createdAt", .datetime)
                t.column("modifiedAt", .datetime)
                t.column("indexedAt", .datetime).notNull()
            }

            try db.create(index: "idx_indexed_files_path", on: "indexed_files", columns: ["path"], unique: true)
            try db.create(index: "idx_indexed_files_type", on: "indexed_files", columns: ["fileType"])
            try db.create(index: "idx_indexed_files_folder", on: "indexed_files", columns: ["folder"])
            try db.create(index: "idx_indexed_files_ext", on: "indexed_files", columns: ["fileExtension"])
            try db.create(index: "idx_indexed_files_modified", on: "indexed_files", columns: ["modifiedAt"])
        }

        migrator.registerMigration("createTaskChatMessages") { db in
            try db.create(table: "task_chat_messages") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("taskId", .text).notNull()          // action_items backendId
                t.column("acpSessionId", .text)               // ACP session for resume
                t.column("messageId", .text).notNull()        // UUID from ChatMessage.id
                t.column("sender", .text).notNull()           // "user" or "ai"
                t.column("messageText", .text).notNull()
                t.column("contentBlocksJson", .text)          // JSON-encoded ChatContentBlock array
                t.column("embedding", .blob)                  // 3072 Float32s for vector search
                t.column("createdAt", .datetime).notNull()
                t.column("updatedAt", .datetime).notNull()
                t.column("backendSynced", .boolean).notNull().defaults(to: false)
                t.column("backendMessageId", .text)           // Server-side message ID
            }

            // Indexes for common queries
            try db.create(index: "idx_task_chat_messages_taskId", on: "task_chat_messages", columns: ["taskId"])
            try db.create(index: "idx_task_chat_messages_messageId", on: "task_chat_messages", columns: ["messageId"], unique: true)
            try db.create(index: "idx_task_chat_messages_created", on: "task_chat_messages", columns: ["taskId", "createdAt"])
            // Partial index for unsynced messages (future backend sync)
            try db.execute(sql: """
                CREATE INDEX idx_task_chat_messages_unsynced
                ON task_chat_messages (taskId)
                WHERE backendSynced = 0
            """)
            // Partial index for embedding search
            try db.execute(sql: """
                CREATE INDEX idx_task_chat_messages_embedding
                ON task_chat_messages (taskId)
                WHERE embedding IS NOT NULL
            """)

            // FTS5 for full-text search over messages
            try db.execute(sql: """
                CREATE VIRTUAL TABLE task_chat_messages_fts USING fts5(
                    messageText,
                    content='task_chat_messages',
                    content_rowid='id'
                )
            """)

            try db.execute(sql: """
                CREATE TRIGGER task_chat_messages_ai AFTER INSERT ON task_chat_messages BEGIN
                    INSERT INTO task_chat_messages_fts(rowid, messageText)
                    VALUES (new.id, new.messageText);
                END
            """)

            try db.execute(sql: """
                CREATE TRIGGER task_chat_messages_ad AFTER DELETE ON task_chat_messages BEGIN
                    INSERT INTO task_chat_messages_fts(task_chat_messages_fts, rowid, messageText)
                    VALUES ('delete', old.id, old.messageText);
                END
            """)

            try db.execute(sql: """
                CREATE TRIGGER task_chat_messages_au AFTER UPDATE ON task_chat_messages BEGIN
                    INSERT INTO task_chat_messages_fts(task_chat_messages_fts, rowid, messageText)
                    VALUES ('delete', old.id, old.messageText);
                    INSERT INTO task_chat_messages_fts(rowid, messageText)
                    VALUES (new.id, new.messageText);
                END
            """)
        }

        try migrator.migrate(queue)
    }

    // MARK: - OCR Precision Reduction Migration

    /// Reduce ocrDataJson float precision from 16 to 3 decimal places (~31% size saving)
    /// Runs once in background at startup; safe to interrupt and resume.
    func reduceOCRDataPrecisionIfNeeded() async {
        guard let dbQueue = dbQueue else { return }

        // Check if already completed
        let isComplete: Bool
        do {
            isComplete = try await dbQueue.read { db in
                let completed = try Int.fetchOne(db, sql: """
                    SELECT completed FROM migration_status
                    WHERE name = 'ocr_precision_reduction'
                """) ?? 1
                return completed == 1
            }
        } catch {
            log("RewindDatabase: Failed to check precision migration status: \(error)")
            return
        }

        guard !isComplete else {
            log("RewindDatabase: OCR precision reduction already complete, skipping")
            return
        }

        log("RewindDatabase: Starting OCR precision reduction migration...")

        let batchSize = 500
        var offset = 0
        var totalProcessed = 0
        var totalUpdated = 0
        let decoder = JSONDecoder()
        let encoder = JSONEncoder()

        do {
            while true {
                let currentOffset = offset
                let batch: [(id: Int64, json: String)] = try await dbQueue.read { db in
                    try Row.fetchAll(db, sql: """
                        SELECT id, ocrDataJson FROM screenshots
                        WHERE ocrDataJson IS NOT NULL
                        ORDER BY id
                        LIMIT ? OFFSET ?
                    """, arguments: [batchSize, currentOffset]).compactMap { row in
                        guard let id: Int64 = row["id"],
                              let json: String = row["ocrDataJson"]
                        else { return nil }
                        return (id, json)
                    }
                }

                if batch.isEmpty { break }

                var updates: [(id: Int64, json: String)] = []
                for (id, jsonString) in batch {
                    guard let jsonData = jsonString.data(using: .utf8),
                          let ocrResult = try? decoder.decode(OCRResult.self, from: jsonData)
                    else { continue }

                    // Round all block coordinates to 3 decimal places
                    let roundedBlocks = ocrResult.blocks.map { block in
                        OCRTextBlock(
                            text: block.text,
                            x: (block.x * 1000).rounded() / 1000,
                            y: (block.y * 1000).rounded() / 1000,
                            width: (block.width * 1000).rounded() / 1000,
                            height: (block.height * 1000).rounded() / 1000,
                            confidence: (block.confidence * 1000).rounded() / 1000
                        )
                    }

                    let roundedResult = OCRResult(
                        fullText: ocrResult.fullText,
                        blocks: roundedBlocks,
                        processedAt: ocrResult.processedAt
                    )

                    guard let data = try? encoder.encode(roundedResult),
                          let newJson = String(data: data, encoding: .utf8)
                    else { continue }

                    // Only update if the JSON actually changed (avoid unnecessary writes)
                    if newJson.count < jsonString.count {
                        updates.append((id, newJson))
                    }
                }

                if !updates.isEmpty {
                    let updatesToApply = updates
                    try await dbQueue.write { db in
                        for (id, json) in updatesToApply {
                            try db.execute(
                                sql: "UPDATE screenshots SET ocrDataJson = ? WHERE id = ?",
                                arguments: [json, id]
                            )
                        }
                    }
                    totalUpdated += updates.count
                }

                offset += batchSize
                totalProcessed += batch.count

                if totalProcessed % 5000 == 0 {
                    log("RewindDatabase: Precision reduction — processed \(totalProcessed) rows, updated \(totalUpdated)...")
                    // Update progress
                    let currentProcessed = totalProcessed
                    try? await dbQueue.write { db in
                        try db.execute(sql: """
                            UPDATE migration_status SET processedCount = ?
                            WHERE name = 'ocr_precision_reduction'
                        """, arguments: [currentProcessed])
                    }
                }

                // Small yield to avoid hogging the database
                try? await Task.sleep(nanoseconds: 10_000_000) // 10ms
            }

            // Mark complete
            let finalProcessed = totalProcessed
            try await dbQueue.write { db in
                try db.execute(sql: """
                    UPDATE migration_status
                    SET completed = 1, processedCount = ?, completedAt = datetime('now')
                    WHERE name = 'ocr_precision_reduction'
                """, arguments: [finalProcessed])
            }

            log("RewindDatabase: OCR precision reduction complete — processed \(totalProcessed) rows, updated \(totalUpdated)")
        } catch {
            log("RewindDatabase: OCR precision reduction failed at offset \(offset): \(error)")
        }
    }

    // MARK: - CRUD Operations

    /// Insert a new screenshot record
    @discardableResult
    func insertScreenshot(_ screenshot: Screenshot) throws -> Screenshot {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        return try dbQueue.write { db -> Screenshot in
            let record = screenshot
            try record.insert(db)
            return record
        }
    }

    /// Update OCR text for a screenshot (legacy - without bounding boxes)
    func updateOCRText(id: Int64, ocrText: String) throws {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        try dbQueue.write { db in
            try db.execute(
                sql: "UPDATE screenshots SET ocrText = ?, isIndexed = 1 WHERE id = ?",
                arguments: [ocrText, id]
            )
        }
    }

    /// Update OCR result with bounding boxes for a screenshot
    func updateOCRResult(id: Int64, ocrResult: OCRResult) throws {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        let ocrDataJson: String?
        do {
            let data = try JSONEncoder().encode(ocrResult)
            ocrDataJson = String(data: data, encoding: .utf8)
        } catch {
            ocrDataJson = nil
        }

        try dbQueue.write { db in
            try db.execute(
                sql: "UPDATE screenshots SET ocrText = ?, ocrDataJson = ?, isIndexed = 1, skippedForBattery = 0 WHERE id = ?",
                arguments: [ocrResult.fullText, ocrDataJson, id]
            )
        }
    }

    /// Get screenshots pending OCR processing
    func getPendingOCRScreenshots(limit: Int = 10) throws -> [Screenshot] {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        return try dbQueue.read { db in
            try Screenshot
                .filter(Column("isIndexed") == false)
                .order(Column("timestamp").asc)
                .limit(limit)
                .fetchAll(db)
        }
    }

    /// Get screenshots that were skipped due to battery and need OCR backfill
    func getBatterySkippedScreenshots(limit: Int = 10) throws -> [Screenshot] {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        return try dbQueue.read { db in
            try Screenshot
                .filter(Column("skippedForBattery") == true)
                .order(Column("timestamp").asc)
                .limit(limit)
                .fetchAll(db)
        }
    }

    /// Clear skippedForBattery flag for a screenshot that can't be processed (e.g. missing file)
    func clearSkippedForBattery(id: Int64) throws {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        try dbQueue.write { db in
            try db.execute(
                sql: "UPDATE screenshots SET skippedForBattery = 0 WHERE id = ?",
                arguments: [id]
            )
        }
    }

    /// Get screenshot by ID
    func getScreenshot(id: Int64) throws -> Screenshot? {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        return try dbQueue.read { db in
            try Screenshot.fetchOne(db, key: id)
        }
    }

    // MARK: - Screenshot Embedding Methods

    /// Store embedding BLOB for a screenshot
    func updateScreenshotEmbedding(id: Int64, embedding: Data) throws {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        try dbQueue.write { db in
            try db.execute(
                sql: "UPDATE screenshots SET embedding = ? WHERE id = ?",
                arguments: [embedding, id]
            )
        }
    }

    /// Get screenshots missing embeddings (for backfill)
    func getScreenshotsMissingEmbeddings(limit: Int = 100) throws -> [(id: Int64, ocrText: String, appName: String, windowTitle: String?)] {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        return try dbQueue.read { db in
            try Row.fetchAll(db, sql: """
                SELECT id, ocrText, appName, windowTitle FROM screenshots
                WHERE embedding IS NULL AND ocrText IS NOT NULL AND LENGTH(ocrText) >= 20
                ORDER BY id LIMIT ?
            """, arguments: [limit]).compactMap { row in
                guard let id: Int64 = row["id"],
                      let ocrText: String = row["ocrText"],
                      let appName: String = row["appName"] else { return nil }
                let windowTitle: String? = row["windowTitle"]
                return (id: id, ocrText: ocrText, appName: appName, windowTitle: windowTitle)
            }
        }
    }

    /// Read screenshot embedding BLOBs in batches for disk-based vector search
    func readEmbeddingBatch(startDate: Date, endDate: Date, appFilter: String? = nil, limit: Int = 5000, offset: Int = 0) throws -> [(screenshotId: Int64, embedding: Data)] {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        return try dbQueue.read { db in
            var sql = """
                SELECT id, embedding FROM screenshots
                WHERE embedding IS NOT NULL
                  AND timestamp >= ? AND timestamp <= ?
            """
            var arguments: [DatabaseValueConvertible] = [startDate, endDate]

            if let app = appFilter {
                sql += " AND appName = ?"
                arguments.append(app)
            }

            sql += " ORDER BY id LIMIT ? OFFSET ?"
            arguments.append(limit)
            arguments.append(offset)

            return try Row.fetchAll(db, sql: sql, arguments: StatementArguments(arguments)).compactMap { row in
                guard let id: Int64 = row["id"],
                      let embedding: Data = row["embedding"] else { return nil }
                return (screenshotId: id, embedding: embedding)
            }
        }
    }

    /// Check screenshot embedding backfill status
    func getScreenshotEmbeddingBackfillStatus() throws -> (completed: Bool, processedCount: Int) {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        return try dbQueue.read { db in
            let completed = try Int64.fetchOne(db, sql: """
                SELECT completed FROM migration_status WHERE name = 'screenshot_embedding_backfill'
            """) ?? 1
            let processedCount = try Int64.fetchOne(db, sql: """
                SELECT COALESCE(processedCount, 0) FROM migration_status WHERE name = 'screenshot_embedding_backfill'
            """) ?? 0
            return (
                completed: completed == 1,
                processedCount: Int(processedCount)
            )
        }
    }

    /// Update screenshot embedding backfill progress
    func updateScreenshotEmbeddingBackfillStatus(completed: Bool, processedCount: Int) throws {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        try dbQueue.write { db in
            try db.execute(sql: """
                UPDATE migration_status
                SET completed = ?, processedCount = ?, completedAt = CASE WHEN ? = 1 THEN datetime('now') ELSE completedAt END
                WHERE name = 'screenshot_embedding_backfill'
            """, arguments: [completed ? 1 : 0, processedCount, completed ? 1 : 0])
        }
    }

    /// Get screenshots for a date range
    func getScreenshots(from startDate: Date, to endDate: Date, limit: Int = 100) throws -> [Screenshot] {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        return try dbQueue.read { db in
            try Screenshot
                .filter(Column("timestamp") >= startDate && Column("timestamp") <= endDate)
                .order(Column("timestamp").desc)
                .limit(limit)
                .fetchAll(db)
        }
    }

    /// Get screenshots filtered by allowed apps and browser window title patterns.
    /// For non-browser apps in the allowed list, all windows are returned.
    /// For browser apps, only windows matching at least one pattern are returned.
    func getScreenshotsFiltered(
        from startDate: Date,
        to endDate: Date,
        allowedApps: Set<String>,
        browserApps: Set<String>,
        browserWindowPatterns: [String],
        limit: Int = 100
    ) throws -> [Screenshot] {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        guard !allowedApps.isEmpty else { return [] }

        let nonBrowserApps = allowedApps.subtracting(browserApps)
        let allowedBrowserApps = allowedApps.intersection(browserApps)

        // Build SQL with two conditions OR'd:
        // 1. Non-browser allowed apps (all windows)
        // 2. Browser allowed apps with window title LIKE any pattern
        var conditions: [String] = []
        var arguments: [DatabaseValueConvertible] = []

        // Timestamp range
        arguments.append(startDate)
        arguments.append(endDate)

        // Non-browser apps
        if !nonBrowserApps.isEmpty {
            let placeholders = nonBrowserApps.map { _ in "?" }.joined(separator: ", ")
            conditions.append("appName IN (\(placeholders))")
            for app in nonBrowserApps.sorted() {
                arguments.append(app)
            }
        }

        // Browser apps with window pattern matching
        if !allowedBrowserApps.isEmpty && !browserWindowPatterns.isEmpty {
            let appPlaceholders = allowedBrowserApps.map { _ in "?" }.joined(separator: ", ")
            let patternClauses = browserWindowPatterns.map { _ in "windowTitle LIKE ?" }.joined(separator: " OR ")
            conditions.append("(appName IN (\(appPlaceholders)) AND windowTitle IS NOT NULL AND (\(patternClauses)))")
            for app in allowedBrowserApps.sorted() {
                arguments.append(app)
            }
            for pattern in browserWindowPatterns {
                arguments.append("%\(pattern)%")
            }
        }

        guard !conditions.isEmpty else {
            log("RewindDatabase.getScreenshotsFiltered: No conditions generated, returning empty")
            return []
        }

        let sql = """
            SELECT * FROM screenshots
            WHERE timestamp >= ? AND timestamp <= ? AND (\(conditions.joined(separator: " OR ")))
            ORDER BY timestamp DESC
            LIMIT ?
        """
        arguments.append(limit)

        log("RewindDatabase.getScreenshotsFiltered: Executing query")
        log("  SQL: \(sql)")
        log("  Date range: \(startDate) to \(endDate)")
        log("  nonBrowserApps: \(nonBrowserApps.sorted())")
        log("  allowedBrowserApps: \(allowedBrowserApps.sorted())")
        log("  browserWindowPatterns count: \(browserWindowPatterns.count)")
        log("  Total arguments count: \(arguments.count)")

        return try dbQueue.read { db in
            let results = try Screenshot.fetchAll(db, sql: sql, arguments: StatementArguments(arguments))
            log("RewindDatabase.getScreenshotsFiltered: Returned \(results.count) screenshots")
            return results
        }
    }

    /// Get recent screenshots
    func getRecentScreenshots(limit: Int = 50) throws -> [Screenshot] {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        return try dbQueue.read { db in
            try Screenshot
                .order(Column("timestamp").desc)
                .limit(limit)
                .fetchAll(db)
        }
    }

    /// Get all unique app names
    func getUniqueAppNames() throws -> [String] {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        return try dbQueue.read { db in
            try String.fetchAll(db, sql: "SELECT DISTINCT appName FROM screenshots ORDER BY appName")
        }
    }

    // MARK: - Search

    /// Expand a search query by splitting compound words (camelCase, numbers)
    /// e.g., "ActivityPerformance" -> "(ActivityPerformance* OR Activity* OR Performance*)"
    private func expandSearchQuery(_ query: String) -> String {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "" }

        // Split query into words
        let words = trimmed.components(separatedBy: .whitespaces).filter { !$0.isEmpty }

        let expandedWords = words.map { word -> String in
            var parts: [String] = [word]

            // Split camelCase: "ActivityPerformance" -> ["Activity", "Performance"]
            let camelCaseParts = splitCamelCase(word)
            if camelCaseParts.count > 1 {
                parts.append(contentsOf: camelCaseParts)
            }

            // Split on number boundaries: "test123" -> ["test", "123"]
            let numberParts = splitOnNumbers(word)
            if numberParts.count > 1 {
                parts.append(contentsOf: numberParts)
            }

            // Remove duplicates and create OR query with prefix matching
            let uniqueParts = Array(Set(parts)).filter { $0.count >= 2 }
            if uniqueParts.count == 1 {
                return "\(uniqueParts[0])*"
            } else {
                let prefixParts = uniqueParts.map { "\($0)*" }
                return "(\(prefixParts.joined(separator: " OR ")))"
            }
        }

        return expandedWords.joined(separator: " ")
    }

    /// Split camelCase string into parts
    private func splitCamelCase(_ string: String) -> [String] {
        var parts: [String] = []
        var currentPart = ""

        for char in string {
            if char.isUppercase && !currentPart.isEmpty {
                parts.append(currentPart)
                currentPart = String(char)
            } else {
                currentPart.append(char)
            }
        }

        if !currentPart.isEmpty {
            parts.append(currentPart)
        }

        return parts.filter { $0.count >= 2 }
    }

    /// Split string on number boundaries
    private func splitOnNumbers(_ string: String) -> [String] {
        var parts: [String] = []
        var currentPart = ""
        var wasDigit = false

        for char in string {
            let isDigit = char.isNumber
            if !currentPart.isEmpty && isDigit != wasDigit {
                parts.append(currentPart)
                currentPart = String(char)
            } else {
                currentPart.append(char)
            }
            wasDigit = isDigit
        }

        if !currentPart.isEmpty {
            parts.append(currentPart)
        }

        return parts.filter { $0.count >= 2 }
    }

    /// Full-text search on OCR text, window titles, and app names
    /// - Parameters:
    ///   - query: Search query (supports compound word expansion)
    ///   - appFilter: Optional app name filter (exact match)
    ///   - startDate: Optional start date for time range
    ///   - endDate: Optional end date for time range
    ///   - limit: Maximum results to return
    func search(
        query: String,
        appFilter: String? = nil,
        startDate: Date? = nil,
        endDate: Date? = nil,
        limit: Int = 100
    ) throws -> [Screenshot] {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        // Expand the query for better matching
        let expandedQuery = expandSearchQuery(query)
        guard !expandedQuery.isEmpty else {
            return []
        }

        return try dbQueue.read { db in
            var sql = """
                SELECT screenshots.* FROM screenshots
                JOIN screenshots_fts ON screenshots.id = screenshots_fts.rowid
                WHERE screenshots_fts MATCH ?
                """
            var arguments: [DatabaseValueConvertible] = [expandedQuery]

            // App filter (exact match, separate from FTS)
            if let app = appFilter {
                sql += " AND screenshots.appName = ?"
                arguments.append(app)
            }

            // Time range filtering
            if let start = startDate {
                sql += " AND screenshots.timestamp >= ?"
                arguments.append(start)
            }

            if let end = endDate {
                sql += " AND screenshots.timestamp <= ?"
                arguments.append(end)
            }

            // Order by relevance (BM25) then by timestamp
            sql += " ORDER BY bm25(screenshots_fts) ASC, screenshots.timestamp DESC LIMIT ?"
            arguments.append(limit)

            return try Screenshot.fetchAll(db, sql: sql, arguments: StatementArguments(arguments))
        }
    }

    // MARK: - Delete Result Types

    /// Result of bulk screenshot deletion (for cleanup)
    struct DeleteResult {
        let imagePaths: [String]           // Legacy JPEG paths to delete
        let orphanedVideoChunks: [String]  // Video chunks with all frames deleted
    }

    /// Result of single screenshot deletion
    struct SingleDeleteResult {
        let imagePath: String?
        let videoChunkPath: String?
        let isLastFrameInChunk: Bool
    }

    // MARK: - Cleanup

    /// Delete screenshots older than the specified date
    func deleteScreenshotsOlderThan(_ date: Date) throws -> DeleteResult {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        // First get the image paths to delete (legacy JPEGs)
        let imagePaths = try dbQueue.read { db -> [String] in
            try String.fetchAll(
                db,
                sql: "SELECT imagePath FROM screenshots WHERE timestamp < ? AND imagePath IS NOT NULL",
                arguments: [date]
            )
        }

        // Get video chunk paths that will have frames deleted
        let videoChunksToCheck = try dbQueue.read { db -> [String] in
            try String.fetchAll(
                db,
                sql: "SELECT DISTINCT videoChunkPath FROM screenshots WHERE timestamp < ? AND videoChunkPath IS NOT NULL",
                arguments: [date]
            )
        }

        // Delete the records
        try dbQueue.write { db in
            try db.execute(
                sql: "DELETE FROM screenshots WHERE timestamp < ?",
                arguments: [date]
            )
        }

        // Check which video chunks are now orphaned (no remaining frames)
        let orphanedChunks = try dbQueue.read { db -> [String] in
            var orphaned: [String] = []
            for chunkPath in videoChunksToCheck {
                let remainingCount = try Int.fetchOne(
                    db,
                    sql: "SELECT COUNT(*) FROM screenshots WHERE videoChunkPath = ?",
                    arguments: [chunkPath]
                ) ?? 0
                if remainingCount == 0 {
                    orphaned.append(chunkPath)
                }
            }
            return orphaned
        }

        return DeleteResult(imagePaths: imagePaths, orphanedVideoChunks: orphanedChunks)
    }

    /// Delete a specific screenshot
    func deleteScreenshot(id: Int64) throws -> SingleDeleteResult? {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        // Get the storage info first
        let storageInfo = try dbQueue.read { db -> (imagePath: String?, videoChunkPath: String?)? in
            try Row.fetchOne(
                db,
                sql: "SELECT imagePath, videoChunkPath FROM screenshots WHERE id = ?",
                arguments: [id]
            ).map { row in
                (imagePath: row["imagePath"] as String?, videoChunkPath: row["videoChunkPath"] as String?)
            }
        }

        guard let info = storageInfo else {
            return nil
        }

        // Check if this is the last frame in the video chunk
        var isLastFrame = false
        if let videoChunkPath = info.videoChunkPath {
            let frameCount = try dbQueue.read { db -> Int in
                try Int.fetchOne(
                    db,
                    sql: "SELECT COUNT(*) FROM screenshots WHERE videoChunkPath = ?",
                    arguments: [videoChunkPath]
                ) ?? 0
            }
            isLastFrame = frameCount == 1
        }

        // Delete the record
        try dbQueue.write { db in
            try db.execute(
                sql: "DELETE FROM screenshots WHERE id = ?",
                arguments: [id]
            )
        }

        return SingleDeleteResult(
            imagePath: info.imagePath,
            videoChunkPath: info.videoChunkPath,
            isLastFrameInChunk: isLastFrame
        )
    }

    /// Get total screenshot count
    func getScreenshotCount() throws -> Int {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        return try dbQueue.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM screenshots") ?? 0
        }
    }

    /// Get database statistics
    func getStats() throws -> (total: Int, indexed: Int, oldestDate: Date?, newestDate: Date?) {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        return try dbQueue.read { db in
            let totalCount = try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM screenshots") ?? 0
            let indexedCount = try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM screenshots WHERE isIndexed = 1") ?? 0
            let oldestDate = try Date.fetchOne(db, sql: "SELECT MIN(timestamp) FROM screenshots")
            let newestDate = try Date.fetchOne(db, sql: "SELECT MAX(timestamp) FROM screenshots")

            return (totalCount, indexedCount, oldestDate, newestDate)
        }
    }

    /// Delete all screenshots from a corrupted video chunk
    /// Returns the number of deleted records
    func deleteScreenshotsFromVideoChunk(videoChunkPath: String) throws -> Int {
        guard let dbQueue = dbQueue else {
            throw RewindError.databaseNotInitialized
        }

        let deletedCount = try dbQueue.write { db -> Int in
            // Get count before deletion
            let count = try Int.fetchOne(
                db,
                sql: "SELECT COUNT(*) FROM screenshots WHERE videoChunkPath = ?",
                arguments: [videoChunkPath]
            ) ?? 0

            // Delete all records for this chunk
            try db.execute(
                sql: "DELETE FROM screenshots WHERE videoChunkPath = ?",
                arguments: [videoChunkPath]
            )

            return count
        }

        if deletedCount > 0 {
            log("RewindDatabase: Deleted \(deletedCount) screenshots from corrupted chunk: \(videoChunkPath)")
        }

        return deletedCount
    }
}
