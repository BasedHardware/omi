import ContextCore
import Foundation

/// What the Storage pane's header reports.
///
/// **Measured, never estimated.** `I27` in `docs/requirements-checklist.md` is explicit about this,
/// and the reason is that the number is the one thing on that pane a user checks against Finder: a
/// figure derived from `frames × average bytes` would disagree with what they see and would make every
/// other claim on the pane suspect. So this walks the real support directory and adds up real
/// allocated sizes.
struct StorageUsage: Equatable, Sendable {
    /// Total bytes under the app's support directory.
    var totalBytes: Int64
    /// The frames subtree, which is nearly all of it and the only part retention deletes.
    var frameBytes: Int64
    /// The database and its WAL sidecars.
    var databaseBytes: Int64
    /// How many files were counted, so an obviously-wrong total can be recognised as one.
    var fileCount: Int
    /// True when the walk could not complete — the total is then a floor, not a total, and the pane
    /// must not present it as exact.
    var isPartial: Bool

    static let unknown = StorageUsage(
        totalBytes: 0, frameBytes: 0, databaseBytes: 0, fileCount: 0, isPartial: true)

    var formattedTotal: String { StorageLimit.format(totalBytes) }
}

enum StorageMeasurement {

    /// Adds up the support directory, off the main thread.
    ///
    /// `totalFileAllocatedSize` rather than `fileSize`: the pane is answering "how much of my disk is
    /// this using", and on APFS those two differ by the block padding of every one of thousands of
    /// small HEICs. Falls back to `fileSize` for any item the allocated size is missing on, so one odd
    /// file cannot zero out a directory's contribution.
    static func measure(directory: URL = ContextPaths.supportDirectory) -> StorageUsage {
        let fileManager = FileManager.default
        let keys: [URLResourceKey] = [
            .isRegularFileKey, .totalFileAllocatedSizeKey, .fileSizeKey,
        ]

        var total: Int64 = 0
        var frames: Int64 = 0
        var database: Int64 = 0
        var count = 0
        var partial = false

        let framesRoot = ContextPaths.framesDirectory.standardizedFileURL.path
        let databaseStem = ContextPaths.databaseURL.lastPathComponent

        guard
            let walker = fileManager.enumerator(
                at: directory,
                includingPropertiesForKeys: keys,
                options: [],
                errorHandler: { _, _ in
                    // One unreadable subtree must not lose the whole figure; it makes it a floor.
                    partial = true
                    return true
                })
        else {
            return .unknown
        }

        for case let url as URL in walker {
            guard let values = try? url.resourceValues(forKeys: Set(keys)),
                values.isRegularFile == true
            else { continue }
            let bytes = Int64(values.totalFileAllocatedSize ?? values.fileSize ?? 0)
            total += bytes
            count += 1
            let path = url.standardizedFileURL.path
            if path.hasPrefix(framesRoot + "/") {
                frames += bytes
            } else if url.lastPathComponent.hasPrefix(databaseStem) {
                // `context.db`, `context.db-wal`, `context.db-shm`.
                database += bytes
            }
        }

        return StorageUsage(
            totalBytes: total,
            frameBytes: frames,
            databaseBytes: database,
            fileCount: count,
            isPartial: partial)
    }
}
