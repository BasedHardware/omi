import Foundation
import GRDB

// MARK: - FileIndexerService

actor FileIndexerService {
    static let shared = FileIndexerService()

    private var _dbQueue: DatabasePool?
    private var isScanning = false

    /// Folders to skip during recursive scan
    private let skipFolders: Set<String> = [
        ".Trash", "node_modules", ".git", "__pycache__", ".venv", "venv",
        ".cache", ".npm", ".yarn", "Pods", "DerivedData", ".build",
        "build", "dist", ".next", ".nuxt", "target", "vendor",
        "Library", ".local", ".cargo", ".rustup"
    ]

    /// Max recursion depth (0 = root of scanned folder)
    private let maxDepth = 3

    /// Skip files larger than 500 MB
    private let maxFileSize: Int64 = 500 * 1024 * 1024

    /// Batch insert size
    private let batchSize = 500

    private init() {}

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
        let foldersToScan = [
            home.appendingPathComponent("Downloads"),
            home.appendingPathComponent("Documents"),
            home.appendingPathComponent("Desktop"),
        ]

        // 1. Scan files
        let totalFiles = await scanFolders(foldersToScan)
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

    // MARK: - File Scanning

    /// Scan folders and store file metadata in indexed_files table
    /// Returns total number of files indexed
    @discardableResult
    func scanFolders(_ folders: [URL]) async -> Int {
        let db: DatabasePool
        do {
            db = try await ensureDB()
        } catch {
            log("FileIndexer: DB init failed: \(error.localizedDescription)")
            return 0
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

            scanDirectory(
                url: folder,
                folderName: folderName,
                homePath: home,
                depth: 0,
                resourceKeys: resourceKeys,
                fm: fm,
                batch: &batch,
                totalFiles: &totalFiles,
                db: db
            )
        }

        // Flush remaining batch
        if !batch.isEmpty {
            insertBatch(batch, into: db)
        }

        return totalFiles
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
        db: DatabasePool
    ) {
        guard depth <= maxDepth else { return }

        let contents: [URL]
        do {
            contents = try fm.contentsOfDirectory(
                at: url,
                includingPropertiesForKeys: resourceKeys,
                options: [.skipsHiddenFiles]
            )
        } catch {
            log("FileIndexer: Cannot read \(url.lastPathComponent): \(error.localizedDescription)")
            return
        }

        for item in contents {
            let name = item.lastPathComponent

            // Check directory
            let resourceValues = try? item.resourceValues(forKeys: Set(resourceKeys))
            let isDirectory = resourceValues?.isDirectory ?? false

            if isDirectory {
                if skipFolders.contains(name) { continue }
                scanDirectory(
                    url: item,
                    folderName: folderName,
                    homePath: homePath,
                    depth: depth + 1,
                    resourceKeys: resourceKeys,
                    fm: fm,
                    batch: &batch,
                    totalFiles: &totalFiles,
                    db: db
                )
                continue
            }

            // Regular file
            guard resourceValues?.isRegularFile == true else { continue }

            let fileSize = Int64(resourceValues?.fileSize ?? 0)
            guard fileSize > 0, fileSize <= maxFileSize else { continue }

            let ext = item.pathExtension.isEmpty ? nil : item.pathExtension.lowercased()
            let fileType = FileTypeCategory.from(extension: ext)

            // Build relative path
            var relativePath = item.path
            if relativePath.hasPrefix(homePath) {
                relativePath = "~" + relativePath.dropFirst(homePath.count)
            }

            let record = IndexedFileRecord(
                path: relativePath,
                filename: name,
                fileExtension: ext,
                fileType: fileType.rawValue,
                sizeBytes: fileSize,
                folder: folderName,
                depth: depth,
                createdAt: resourceValues?.creationDate,
                modifiedAt: resourceValues?.contentModificationDate
            )

            batch.append(record)
            totalFiles += 1

            if batch.count >= batchSize {
                insertBatch(batch, into: db)
                batch.removeAll(keepingCapacity: true)
            }
        }
    }

    private func insertBatch(_ records: [IndexedFileRecord], into db: DatabasePool) {
        do {
            try db.write { database in
                for var record in records {
                    // Use INSERT OR IGNORE to skip duplicates (unique path constraint)
                    try record.insert(database, onConflict: .ignore)
                }
            }
        } catch {
            log("FileIndexer: Batch insert error: \(error.localizedDescription)")
        }
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

enum FileIndexerError: LocalizedError {
    case databaseNotInitialized

    var errorDescription: String? {
        switch self {
        case .databaseNotInitialized:
            return "File indexer database is not initialized"
        }
    }
}
