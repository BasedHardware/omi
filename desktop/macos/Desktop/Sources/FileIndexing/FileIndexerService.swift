import Darwin
import Foundation
import GRDB

// MARK: - FileIndexerService

actor FileIndexerService {
    static let shared = FileIndexerService()

    private var _dbQueue: DatabasePool?
    private var isScanning = false
    private let scanPolicy: FileIndexScanPolicy

    /// Batch insert size
    private let batchSize: Int

    private init() {
        scanPolicy = .standard
        batchSize = 500
    }

    init(databasePool: DatabasePool, scanPolicy: FileIndexScanPolicy = .standard, batchSize: Int = 500) {
        _dbQueue = databasePool
        self.scanPolicy = scanPolicy
        self.batchSize = batchSize
    }

    // MARK: - Database Access

    private func ensureDB() async throws -> DatabasePool {
        if let db = _dbQueue { return db }

        try await RewindDatabase.shared.initialize()
        guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
            throw FileIndexerError.databaseNotInitialized
        }
        _dbQueue = db
        return db
    }

    func invalidateCache() {
        _dbQueue = nil
    }

    /// Returns the total number of indexed files in the database
    func getIndexedFileCount() async -> Int {
        guard let db = try? await ensureDB() else { return 0 }
        do {
            return try await db.read { database in
                try Int.fetchOne(database, sql: "SELECT COUNT(*) FROM indexed_files") ?? 0
            }
        } catch {
            log("FileIndexer: Failed to get indexed file count: \(error)")
            return 0
        }
    }

    // MARK: - Onboarding Pipeline

    /// Main entry point: scan files → post notification → chat AI does the analysis
    func runOnboardingPipeline() async {
        guard !UserDefaults.standard.bool(forKey: "hasCompletedFileIndexing") else {
            log("FileIndexer: Already completed, skipping")
            return
        }

        guard !isScanning else {
            log("FileIndexer: Scan already in progress, skipping")
            return
        }

        isScanning = true
        defer { isScanning = false }

        log("FileIndexer: Starting onboarding pipeline")

        let home = FileManager.default.homeDirectoryForCurrentUser
        let foldersToScan = scanPolicy.standardScanRoots(homeURL: home)

        // 1. Scan files
        let scanResult = await scanFolders(foldersToScan)
        if let failure = scanResult.failure {
            log("FileIndexer: Onboarding scan failed after \(scanResult.indexedCount) files: \(failure.logMessage)")
            return
        }

        let totalFiles = scanResult.indexedCount
        guard totalFiles > 0 else {
            log("FileIndexer: No files found, skipping")
            await MainActor.run {
                UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")
            }
            return
        }
        log("FileIndexer: Scanned \(totalFiles) files")

        // 2. Mark complete and set pending chat flag for ChatPage to pick up
        await MainActor.run {
            UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")
            // Set pending flag so ChatPage picks it up when it mounts (or on next navigation)
            if UserDefaults.standard.integer(forKey: "pendingFileIndexingChat") == 0 {
                UserDefaults.standard.set(totalFiles, forKey: "pendingFileIndexingChat")
            }
        }

        // 3. Post notification so ChatPage can trigger AI analysis (if already mounted)
        await MainActor.run {
            NotificationCenter.default.post(
                name: .fileIndexingComplete,
                object: nil,
                userInfo: ["totalFiles": totalFiles]
            )
        }
        log("FileIndexer: Pipeline complete, posted fileIndexingComplete notification")
    }

    // MARK: - Background Re-scan

    /// Incremental background re-scan of all standard folders.
    /// Updates metadata for existing files and adds new ones.
    func backgroundRescan() async {
        guard !isScanning else {
            log("FileIndexer: Scan already in progress, skipping background rescan")
            return
        }

        isScanning = true
        defer { isScanning = false }

        log("FileIndexer: Starting background rescan")

        let home = FileManager.default.homeDirectoryForCurrentUser
        let folders = scanPolicy.standardScanRoots(homeURL: home)

        let scanResult = await scanFolders(folders, incremental: true)
        if let failure = scanResult.failure {
            log("FileIndexer: Background rescan failed after \(scanResult.indexedCount) files: \(failure.logMessage)")
            return
        }
        log("FileIndexer: Background rescan complete, \(scanResult.indexedCount) files indexed")
    }

    // MARK: - File Scanning

    /// Scan folders and store file metadata in indexed_files table
    /// Returns the number of files indexed, plus a failure when the local index could not be saved.
    @discardableResult
    func scanFolders(_ folders: [URL], incremental: Bool = false) async -> FileIndexingScanResult {
        let db: DatabasePool
        do {
            db = try await ensureDB()
        } catch {
            log("FileIndexer: DB init failed: \(error.localizedDescription)")
            return FileIndexingScanResult(indexedCount: 0, failure: FileIndexingFailure.classify(error))
        }

        // For incremental scans, load existing index for O(1) lookup
        let existingIndex: [String: Date?] = incremental ? loadExistingIndex(from: db) : [:]
        var scannedPaths = Set<String>()

        if incremental {
            log("FileIndexer: Loaded \(existingIndex.count) existing paths for incremental scan")
        }

        let fm = FileManager.default
        let home = fm.homeDirectoryForCurrentUser.path
        var totalFiles = 0
        var batch: [IndexedFileRecord] = []

        let resourceKeys: [URLResourceKey] = [
            .fileSizeKey, .creationDateKey, .contentModificationDateKey,
            .isRegularFileKey, .isDirectoryKey
        ]

        for folder in folders {
            guard fm.fileExists(atPath: folder.path) else { continue }

            let folderName = folder.lastPathComponent
            log("FileIndexer: Scanning ~/\(folderName)")

            if let failure = scanDirectory(
                url: folder,
                folderName: folderName,
                homePath: home,
                depth: 0,
                resourceKeys: resourceKeys,
                fm: fm,
                batch: &batch,
                totalFiles: &totalFiles,
                db: db,
                existingIndex: existingIndex,
                scannedPaths: &scannedPaths
            ) {
                return FileIndexingScanResult(indexedCount: totalFiles, failure: failure)
            }
        }

        // Flush remaining batch
        if !batch.isEmpty {
            let insertedCount = batch.count
            if let failure = insertBatch(batch, into: db) {
                return FileIndexingScanResult(indexedCount: totalFiles, failure: failure)
            }
            totalFiles += insertedCount
        }

        // For incremental scans, remove files that no longer exist on disk
        if incremental && !existingIndex.isEmpty {
            if let failure = deleteRemovedFiles(
                scannedPaths: scannedPaths,
                existingPaths: Set(existingIndex.keys),
                db: db
            ) {
                return FileIndexingScanResult(indexedCount: totalFiles, failure: failure)
            }
        }

        return FileIndexingScanResult(indexedCount: totalFiles)
    }

    private func scanDirectory(
        url: URL,
        folderName: String,
        homePath: String,
        depth: Int,
        resourceKeys: [URLResourceKey],
        fm: FileManager,
        batch: inout [IndexedFileRecord],
        totalFiles: inout Int,
        db: DatabasePool,
        existingIndex: [String: Date?],
        scannedPaths: inout Set<String>
    ) -> FileIndexingFailure? {
        guard scanPolicy.shouldScanDirectory(atDepth: depth) else { return nil }

        let contents: [URL]
        do {
            contents = try fm.contentsOfDirectory(
                at: url,
                includingPropertiesForKeys: resourceKeys,
                options: [.skipsHiddenFiles]
            )
        } catch {
            log("FileIndexer: Cannot read \(url.lastPathComponent): \(error.localizedDescription)")
            return nil
        }

        for item in contents {
            // Check directory
            let resourceValues = try? item.resourceValues(forKeys: Set(resourceKeys))
            let isDirectory = resourceValues?.isDirectory ?? false

            if isDirectory {
                switch scanPolicy.planDirectoryEntry(item) {
                case .skipSubtree:
                    continue
                case .indexPackage:
                    guard let record = scanPolicy.makePackageRecord(
                        for: item,
                        folderName: folderName,
                        homePath: homePath,
                        depth: depth,
                        createdAt: resourceValues?.creationDate,
                        modifiedAt: resourceValues?.contentModificationDate
                    ) else {
                        continue
                    }
                    scannedPaths.insert(record.path)
                    // Skip unchanged files (incremental scan)
                    if let existingModified = existingIndex[record.path],
                       let newModified = resourceValues?.contentModificationDate,
                       let existing = existingModified,
                       abs(existing.timeIntervalSince(newModified)) < 1.0 {
                        continue
                    }
                    batch.append(record)
                    if batch.count >= batchSize {
                        let insertedCount = batch.count
                        if let failure = insertBatch(batch, into: db) {
                            return failure
                        }
                        totalFiles += insertedCount
                        batch.removeAll(keepingCapacity: true)
                    }
                    continue
                case .descend:
                    if let failure = scanDirectory(
                        url: item,
                        folderName: folderName,
                        homePath: homePath,
                        depth: depth + 1,
                        resourceKeys: resourceKeys,
                        fm: fm,
                        batch: &batch,
                        totalFiles: &totalFiles,
                        db: db,
                        existingIndex: existingIndex,
                        scannedPaths: &scannedPaths
                    ) {
                        return failure
                    }
                    continue
                }
            }

            // Regular file
            guard let record = scanPolicy.makeFileRecord(
                for: item,
                folderName: folderName,
                homePath: homePath,
                depth: depth,
                isRegularFile: resourceValues?.isRegularFile == true,
                sizeBytes: Int64(resourceValues?.fileSize ?? 0),
                createdAt: resourceValues?.creationDate,
                modifiedAt: resourceValues?.contentModificationDate
            ) else {
                continue
            }

            scannedPaths.insert(record.path)
            // Skip unchanged files (incremental scan)
            if let existingModified = existingIndex[record.path],
               let newModified = resourceValues?.contentModificationDate,
               let existing = existingModified,
               abs(existing.timeIntervalSince(newModified)) < 1.0 {
                continue
            }

            batch.append(record)

            if batch.count >= batchSize {
                let insertedCount = batch.count
                if let failure = insertBatch(batch, into: db) {
                    return failure
                }
                totalFiles += insertedCount
                batch.removeAll(keepingCapacity: true)
            }
        }

        return nil
    }

    private func insertBatch(_ records: [IndexedFileRecord], into db: DatabasePool) -> FileIndexingFailure? {
        do {
            try db.write { database in
                for record in records {
                    // Upsert: insert new files, update metadata for existing ones
                    try database.execute(
                        sql: """
                            INSERT INTO indexed_files (path, filename, fileExtension, fileType, sizeBytes, folder, depth, createdAt, modifiedAt, indexedAt)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(path) DO UPDATE SET
                                sizeBytes = excluded.sizeBytes,
                                modifiedAt = excluded.modifiedAt,
                                indexedAt = excluded.indexedAt
                            """,
                        arguments: [
                            record.path, record.filename, record.fileExtension,
                            record.fileType, record.sizeBytes, record.folder,
                            record.depth, record.createdAt, record.modifiedAt, record.indexedAt
                        ]
                    )
                }
            }
            return nil
        } catch {
            let failure = FileIndexingFailure.classify(error)
            log("FileIndexer: Batch insert error (\(failure.logMessage)): \(error.localizedDescription)")
            return failure
        }
    }

    // MARK: - Incremental Scan Helpers

    /// Load all existing indexed file paths and their modifiedAt dates for O(1) lookup
    private func loadExistingIndex(from db: DatabasePool) -> [String: Date?] {
        do {
            return try db.read { database in
                var index: [String: Date?] = [:]
                let rows = try Row.fetchAll(database, sql: "SELECT path, modifiedAt FROM indexed_files")
                for row in rows {
                    guard let path: String = row["path"] else { continue }
                    let modifiedAt: Date? = row["modifiedAt"]
                    index[path] = modifiedAt
                }
                return index
            }
        } catch {
            log("FileIndexer: Failed to load existing index: \(error.localizedDescription)")
            return [:]
        }
    }

    /// Delete files from the index that no longer exist on disk
    private func deleteRemovedFiles(
        scannedPaths: Set<String>,
        existingPaths: Set<String>,
        db: DatabasePool
    ) -> FileIndexingFailure? {
        let removed = existingPaths.subtracting(scannedPaths)
        guard !removed.isEmpty else { return nil }

        log("FileIndexer: Removing \(removed.count) deleted files from index")

        let removedArray = Array(removed)
        var offset = 0
        while offset < removedArray.count {
            let end = min(offset + 500, removedArray.count)
            let chunk = Array(removedArray[offset..<end])
            do {
                try db.write { database in
                    let placeholders = chunk.map { _ in "?" }.joined(separator: ", ")
                    try database.execute(
                        sql: "DELETE FROM indexed_files WHERE path IN (\(placeholders))",
                        arguments: StatementArguments(chunk)
                    )
                }
            } catch {
                let failure = FileIndexingFailure.classify(error)
                log("FileIndexer: Batch delete error (\(failure.logMessage)): \(error.localizedDescription)")
                return failure
            }
            offset = end
        }
        return nil
    }

    // MARK: - Summary Generation

    /// Generate a compact text summary of the indexed files for AI analysis
    func generateFileSummary() async -> String {
        guard let db = try? await ensureDB() else { return "" }

        var sections: [String] = []

        do {
            // 1. Counts by file type
            let typeCounts: [(type: String, count: Int, totalSize: Int64)] = try await db.read { database in
                try Row.fetchAll(database, sql: """
                    SELECT fileType, COUNT(*) as cnt, SUM(sizeBytes) as totalSize
                    FROM indexed_files
                    GROUP BY fileType
                    ORDER BY cnt DESC
                """).compactMap { row in
                    guard let type: String = row["fileType"],
                          let count: Int = row["cnt"] else { return nil }
                    let totalSize: Int64 = row["totalSize"] ?? 0
                    return (type, count, totalSize)
                }
            }

            if !typeCounts.isEmpty {
                var lines = ["## Files by Type"]
                for item in typeCounts {
                    lines.append("- \(item.type): \(item.count) files (\(formatSize(item.totalSize)))")
                }
                sections.append(lines.joined(separator: "\n"))
            }

            // 2. Counts by folder
            let folderCounts: [(folder: String, count: Int)] = try await db.read { database in
                try Row.fetchAll(database, sql: """
                    SELECT folder, COUNT(*) as cnt
                    FROM indexed_files
                    GROUP BY folder
                    ORDER BY cnt DESC
                """).compactMap { row in
                    guard let folder: String = row["folder"],
                          let count: Int = row["cnt"] else { return nil }
                    return (folder, count)
                }
            }

            if !folderCounts.isEmpty {
                var lines = ["## Files by Folder"]
                for item in folderCounts {
                    lines.append("- ~/\(item.folder): \(item.count) files")
                }
                sections.append(lines.joined(separator: "\n"))
            }

            // 3. Top extensions (limit 25)
            let topExts: [(ext: String, count: Int)] = try await db.read { database in
                try Row.fetchAll(database, sql: """
                    SELECT fileExtension, COUNT(*) as cnt
                    FROM indexed_files
                    WHERE fileExtension IS NOT NULL
                    GROUP BY fileExtension
                    ORDER BY cnt DESC
                    LIMIT 25
                """).compactMap { row in
                    guard let ext: String = row["fileExtension"],
                          let count: Int = row["cnt"] else { return nil }
                    return (ext, count)
                }
            }

            if !topExts.isEmpty {
                var lines = ["## Top File Extensions"]
                for item in topExts {
                    lines.append("- .\(item.ext): \(item.count)")
                }
                sections.append(lines.joined(separator: "\n"))
            }

            // 4. Project indicators (package.json, Cargo.toml, etc.)
            let projectFiles = [
                "package.json", "Cargo.toml", "requirements.txt", "Pipfile",
                "Gemfile", "go.mod", "build.gradle", "pom.xml",
                "Makefile", "CMakeLists.txt", "Package.swift",
                "pyproject.toml", "setup.py", "composer.json",
                "Podfile", "Dockerfile", ".xcodeproj", ".xcworkspace"
            ]
            let placeholders = projectFiles.map { _ in "?" }.joined(separator: ", ")
            let projectHits: [(name: String, path: String)] = try await db.read { database in
                try Row.fetchAll(database, sql: """
                    SELECT filename, path FROM indexed_files
                    WHERE filename IN (\(placeholders))
                    ORDER BY filename
                    LIMIT 50
                """, arguments: StatementArguments(projectFiles)).compactMap { row in
                    guard let name: String = row["filename"],
                          let path: String = row["path"] else { return nil }
                    return (name, path)
                }
            }

            if !projectHits.isEmpty {
                var lines = ["## Project Indicators"]
                for item in projectHits {
                    lines.append("- \(item.name) at \(item.path)")
                }
                sections.append(lines.joined(separator: "\n"))
            }

            // 5. Recently modified files (last 30 days, limit 50)
            let thirtyDaysAgo = Calendar.current.date(byAdding: .day, value: -30, to: Date()) ?? Date()
            let recentFiles: [(name: String, path: String, modified: Date)] = try await db.read { database in
                try Row.fetchAll(database, sql: """
                    SELECT filename, path, modifiedAt FROM indexed_files
                    WHERE modifiedAt >= ?
                    ORDER BY modifiedAt DESC
                    LIMIT 50
                """, arguments: [thirtyDaysAgo]).compactMap { row in
                    guard let name: String = row["filename"],
                          let path: String = row["path"],
                          let modified: Date = row["modifiedAt"] else { return nil }
                    return (name, path, modified)
                }
            }

            if !recentFiles.isEmpty {
                let formatter = DateFormatter()
                formatter.dateFormat = "yyyy-MM-dd"
                var lines = ["## Recently Modified Files (last 30 days)"]
                for item in recentFiles {
                    lines.append("- \(item.name) (\(formatter.string(from: item.modified))) at \(item.path)")
                }
                sections.append(lines.joined(separator: "\n"))
            }

        } catch {
            log("FileIndexer: Summary generation error: \(error.localizedDescription)")
        }

        return sections.joined(separator: "\n\n")
    }

    // MARK: - Helpers

    private func formatSize(_ bytes: Int64) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: bytes)
    }
}

// MARK: - Errors

struct FileIndexingScanResult: Equatable {
    let indexedCount: Int
    let failure: FileIndexingFailure?

    init(indexedCount: Int, failure: FileIndexingFailure? = nil) {
        self.indexedCount = indexedCount
        self.failure = failure
    }
}

enum FileIndexingFailure: Error, Equatable, LocalizedError {
    case diskFull
    case localWriteFailed

    static func classify(_ error: Error) -> FileIndexingFailure {
        if isDiskFull(error) {
            return .diskFull
        }
        return .localWriteFailed
    }

    var userMessage: String {
        switch self {
        case .diskFull:
            return "Mac storage is full. Free up space and try again."
        case .localWriteFailed:
            return "Omi couldn't save the file index. Try again."
        }
    }

    var toolErrorMessage: String {
        "Error: \(userMessage)"
    }

    var logMessage: String {
        switch self {
        case .diskFull:
            return "disk full"
        case .localWriteFailed:
            return "local file index write failed"
        }
    }

    var errorDescription: String? {
        userMessage
    }

    private static func isDiskFull(_ error: Error) -> Bool {
        if let dbError = error as? DatabaseError {
            return dbError.resultCode == .SQLITE_FULL
        }

        let nsError = error as NSError
        if nsError.domain == NSPOSIXErrorDomain && nsError.code == Int(ENOSPC) {
            return true
        }
        if let underlying = nsError.userInfo[NSUnderlyingErrorKey] as? Error {
            return isDiskFull(underlying)
        }
        return false
    }
}

enum FileIndexerError: LocalizedError {
    case databaseNotInitialized

    var errorDescription: String? {
        switch self {
        case .databaseNotInitialized:
            return "File indexer database is not initialized"
        }
    }
}
