import Foundation

/// Every on-disk location the app and the MCP server agree on.
///
/// Deliberately independent of the Omi desktop app's own support directory — Context for Claude never reads or
/// writes Omi's data, and Omi never sees Context for Claude's. The one exception is **read-only** access to
/// Omi's `memories` table through `omiDatabaseURL`, so Claude can answer "what does Omi know about me"
/// without a round trip to the backend.
public enum ContextPaths {
    public static let bundleIdentifier = "com.omi.context-for-claude"

    /// `~/Library/Application Support/ContextForClaude`
    public static var supportDirectory: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let dir = base.appendingPathComponent("ContextForClaude", isDirectory: true)
        // Runs here rather than in `ensureSupportDirectory`: the store opens the database by path
        // and creates the directory itself, so anything gated on "the destination does not exist
        // yet" had already lost the race by the time that ran.
        migrateLegacyDirectoryIfNeeded(into: dir)
        migrateLegacyDatabaseIfNeeded(in: dir)
        return dir
    }

    /// `~/Library/Application Support/ContextForClaude/context.db`
    public static var databaseURL: URL {
        supportDirectory.appendingPathComponent("context.db")
    }

    /// The main Omi desktop app's per-user database, opened **read-only**.
    ///
    /// Context for Claude reads the `memories` table from here so Claude can answer
    /// "what does Omi know about me" without a round trip to the backend — and so
    /// memories that have not synced yet are still searchable.
    ///
    /// The path is `~/Library/Application Support/Omi/users/<userId>/omi.db`. The
    /// user id is not known here, so the directory is scanned for any subdirectory
    /// containing `omi.db`, preferring a real user over the `anonymous` fallback.
    /// `Omi Beta` is checked as a secondary root.
    public static var omiDatabaseURL: URL? {
        let fm = FileManager.default
        let base = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        for rootName in ["Omi", "Omi Beta"] {
            let usersDir = base.appendingPathComponent(rootName, isDirectory: true)
                .appendingPathComponent("users", isDirectory: true)
            guard let candidates = try? fm.contentsOfDirectory(atPath: usersDir.path) else { continue }
            let sorted = candidates.sorted { a, b in
                if a == "anonymous" { return false }
                if b == "anonymous" { return true }
                return a < b
            }
            for userId in sorted {
                let db = usersDir.appendingPathComponent(userId, isDirectory: true)
                    .appendingPathComponent("omi.db")
                if fm.fileExists(atPath: db.path) { return db }
            }
        }
        return nil
    }

    /// Where screen JPEGs live, one directory per day.
    public static var framesDirectory: URL {
        supportDirectory.appendingPathComponent("Frames", isDirectory: true)
    }

    public static func framesDirectory(for epoch: Double) -> URL {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        return framesDirectory.appendingPathComponent(f.string(from: Date(timeIntervalSince1970: epoch)), isDirectory: true)
    }

    /// Written by the app so the MCP server can report live capture state without an IPC channel.
    public static var heartbeatURL: URL {
        supportDirectory.appendingPathComponent("capture-state.json")
    }

    /// The heartbeat's mirror image: written by the MCP server when it serves a tool call, read by
    /// the app so the first-run tutorial can prove Claude really queried it. See `QueryStamp`.
    public static var queryStampURL: URL {
        supportDirectory.appendingPathComponent(queryStampFilename)
    }

    /// The stamp sits beside the database it was served from, not at a second independently-derived
    /// path. One process opened that database and the other watches this file; deriving both from one
    /// location is what keeps them talking about the same install.
    public static func queryStampURL(besideDatabaseAt databaseURL: URL) -> URL {
        databaseURL.deletingLastPathComponent().appendingPathComponent(queryStampFilename)
    }

    /// The lock guarding a stamp write. Never renamed or replaced, so concurrent MCP servers always
    /// contend over the same inode — see `QueryStamp.record`.
    public static func queryStampLockURL(for stampURL: URL) -> URL {
        stampURL.deletingLastPathComponent()
            .appendingPathComponent(stampURL.lastPathComponent + ".lock")
    }

    static let queryStampFilename = "last-query.json"

    @discardableResult
    public static func ensureSupportDirectory(at url: URL? = nil) throws -> URL {
        let dir = url ?? supportDirectory
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try? setPermissions(dir, mode: 0o700)
        return dir
    }

    /// Best-effort POSIX permission adjustment for sensitive directories/files. Failures are ignored
    /// because the path already had default-umask permissions; this is defence-in-depth, not a gate.
    public static func setPermissions(_ url: URL, mode: UInt16) {
        let fm = FileManager.default
        guard fm.fileExists(atPath: url.path) else { return }
        let current = (try? fm.attributesOfItem(atPath: url.path)[.posixPermissions] as? NSNumber)?.intValue ?? 0
        guard current != Int(mode) else { return }
        try? fm.setAttributes([.posixPermissions: mode], ofItemAtPath: url.path)
    }

    /// Directory names this app has shipped under, oldest first.
    private static let legacyDirectoryNames = ["Earshot", "OmiAmbient"]
    /// Database filenames this app has shipped under, oldest first.
    private static let legacyDatabaseNames = ["earshot.db", "ambient.db"]

    /// Moving the directory is not enough — the database inside it is named too, and a renamed
    /// folder holding a database nobody looks for is data loss that reports success. Carries the
    /// WAL and shared-memory sidecars with it; leaving those behind orphans uncheckpointed writes.
    private static func migrateLegacyDatabaseIfNeeded(in directory: URL) {
        let fm = FileManager.default
        let destination = directory.appendingPathComponent("context.db")
        guard !fm.fileExists(atPath: destination.path) else { return }

        for name in legacyDatabaseNames {
            let legacy = directory.appendingPathComponent(name)
            guard fm.fileExists(atPath: legacy.path) else { continue }
            for suffix in ["", "-wal", "-shm"] {
                let from = directory.appendingPathComponent(name + suffix)
                let to = directory.appendingPathComponent("context.db" + suffix)
                guard fm.fileExists(atPath: from.path) else { continue }
                try? fm.moveItem(at: from, to: to)
            }
            return
        }
    }

    /// Carries the database, the frames and the upload queue across a rename.
    ///
    /// A renamed product that silently abandons everything it recorded is a data-loss bug wearing a
    /// cosmetic change's clothing — the pending upload queue in particular, which is the only record
    /// of conversations owed to the account. Runs once: after the move the old directory is gone, so
    /// the guard below is false forever after.
    private static func migrateLegacyDirectoryIfNeeded(into destination: URL) {
        let fm = FileManager.default
        guard !fm.fileExists(atPath: destination.path) else { return }

        let base = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        for name in legacyDirectoryNames {
            let legacy = base.appendingPathComponent(name, isDirectory: true)
            guard fm.fileExists(atPath: legacy.path) else { continue }
            do {
                try fm.moveItem(at: legacy, to: destination)
                return
            } catch {
                // A failed move must not stop a launch: worst case the app starts empty, which is
                // recoverable, where refusing to start is not.
                continue
            }
        }
    }
}

/// The app writes this; `context-for-claude-mcp` reads it. A file rather than a socket because the MCP server
/// is spawned per Claude session and must work whether or not the app happens to be running.
public struct CaptureState: Codable, Sendable, Equatable {
    public var capturing: Bool
    public var pausedReason: String?
    public var capabilities: [CapabilityReport]
    public var updatedAt: Double

    public init(
        capturing: Bool,
        pausedReason: String? = nil,
        capabilities: [CapabilityReport] = [],
        updatedAt: Double = ContextTime.now
    ) {
        self.capturing = capturing
        self.pausedReason = pausedReason
        self.capabilities = capabilities
        self.updatedAt = updatedAt
    }

    /// Considered live only if the app touched it recently; otherwise the app is not running.
    public static let stalenessSeconds: Double = 90

    public var isStale: Bool { ContextTime.now - updatedAt > Self.stalenessSeconds }

    public func write(to url: URL = ContextPaths.heartbeatURL) throws {
        try ContextPaths.ensureSupportDirectory()
        let data = try JSONEncoder().encode(self)
        try data.write(to: url, options: .atomic)
        ContextPaths.setPermissions(url, mode: 0o600)
    }

    /// Why a reader could not open the capture database — and, crucially, whether "empty" is a
    /// fact about the user's life or a fault in the reader.
    ///
    /// This exists because the two were conflated and produced a confident falsehood. After a
    /// rename, Claude kept running the previous install's MCP binary from a bundle that had already
    /// been deleted. It looked for a database at the old path, did not find one, and reported that
    /// nothing had ever been captured on this Mac — while the current app was capturing a frame
    /// every three seconds. A stale reader asserting an empty life is the exact failure the
    /// coverage-window design exists to prevent, so absence of a database must never be reported as
    /// absence of history without checking this first.
    public enum ReaderFault: Sendable, Equatable {
        /// A live heartbeat says capture is running, so the database exists somewhere this reader
        /// cannot see. Its own view is wrong; the user's history is not empty.
        case readerIsStale(capturingSince: Double, heartbeatAgeSeconds: Double)
        /// No heartbeat at all, or a long-stale one: the app genuinely is not running here.
        case appNotRunning
        /// A database is there and readable, but predates this binary's queries. The history is
        /// intact and nothing is lost; the app simply has not relaunched since the update.
        case databaseAwaitingUpgrade
    }

    /// Classifies an unopenable database. Call this before saying anything about emptiness.
    public static func diagnoseMissingDatabase() -> ReaderFault {
        // Before the heartbeat, because this is the fault the heartbeat cannot see: capture can be
        // running perfectly while this reader still cannot query what it writes.
        if ContextStore.needsAppUpgrade() { return .databaseAwaitingUpgrade }
        guard let state = read() else { return .appNotRunning }
        let age = ContextTime.now - state.updatedAt
        guard !state.isStale else { return .appNotRunning }
        return .readerIsStale(capturingSince: state.updatedAt, heartbeatAgeSeconds: age)
    }

    public static func read(from url: URL = ContextPaths.heartbeatURL) -> CaptureState? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(CaptureState.self, from: data)
    }
}
