import Foundation

/// Every on-disk location the app and the MCP server agree on.
///
/// Deliberately independent of the Omi desktop app's own support directory — Context for Claude never reads or
/// writes Omi's data, and Omi never sees Context for Claude's. The one exception is **read-only** access to
/// Omi's `memories` table through `omiDatabaseURL`, so Claude can answer "what does Omi know about me"
/// without a round trip to the backend.
public enum ContextPaths {
    /// The identifier a notarized Developer ID release is signed as, and the only one that ever
    /// reaches a user. Also the fallback for any process that is not running from a bundle of ours.
    public static let shippingBundleIdentifier = "com.omi.context-for-claude"

    /// **The identifier this process actually runs under.**
    ///
    /// Not a constant, because a locally signed developer build carrying the *release's* identifier
    /// is a permission failure with no repair. macOS stores a code requirement beside every TCC
    /// grant, keyed by bundle id, and the two builds' requirements are mutually unsatisfiable —
    /// measured on this Mac, the dev build's is `identifier "com.omi.context-for-claude" and
    /// certificate leaf = H"bb9251…"` while the release's is `identifier "com.omi.context-for-claude"
    /// and anchor apple generic … certificate leaf[subject.OU] = "9536L8KLMP"`. Whichever build is
    /// granted first writes the record, and the other can never satisfy it — permanently, while
    /// System Settings still shows the toggle on. A build not signed by Developer ID therefore gets
    /// its own identity (`com.omi.context-for-claude.dev`, from `scripts/build.sh`) so the two own
    /// disjoint platform records and cannot collide.
    ///
    /// Everything keyed by the OS or shown to the user follows this: the `tccutil` line the app
    /// tells the user to run, the Keychain service, the log subsystem, and the Claude registration.
    /// The Application Support directory deliberately does **not** — it is shared, and repointing it
    /// would move the production database out from under the production app.
    public static let bundleIdentifier = ownIdentifier(reportedBy: Bundle.main.bundleIdentifier)

    /// The rule, over a stated report, so it can be proved rather than trusted.
    ///
    /// **Only our own family of identifiers is adopted.** `Bundle.main` is not ours in two of the
    /// three ways this code runs, and measured here rather than assumed: under `swift test` it is
    /// `com.apple.dt.xctest.tool` (the XCTest runner's own bundle, *not* nil — a comment elsewhere in
    /// this package claims nil and is wrong), and a bare `swift run` binary has no bundle at all and
    /// reports nil. Adopting either would put a foreign string on the log subsystem and the Keychain
    /// service. Only inside an `.app` — including for `context-for-claude-mcp`, the helper in
    /// `Contents/MacOS/`, which resolves `Bundle.main` to the enclosing bundle despite not being its
    /// `CFBundleExecutable` — is the reported id one we wrote into `Info.plist`.
    public static func ownIdentifier(reportedBy reported: String?) -> String {
        guard let reported,
            reported == shippingBundleIdentifier
                || reported.hasPrefix(shippingBundleIdentifier + ".")
        else { return shippingBundleIdentifier }
        return reported
    }

    /// Whether this build owns an identity of its own rather than the shipping one — true for the
    /// `.dev` bundle `scripts/build.sh` produces when it cannot sign with Developer ID.
    public static var isDevelopmentBuild: Bool {
        isDevelopmentBuild(bundleIdentifier)
    }

    /// The same question over a stated identifier, so every value derived from it can be checked for
    /// both builds without a bundle to run inside.
    public static func isDevelopmentBuild(_ identifier: String) -> Bool {
        identifier != shippingBundleIdentifier
    }

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
    /// containing `omi.db`. `Omi Beta` is checked as a secondary root, and only when
    /// `Omi` offered nothing at all — a beta install is a fallback, never a competitor.
    ///
    /// **The winner is the largest database, not the first name in the alphabet, and that is a fix
    /// rather than a preference.** This scan used to sort the directory names and take the first
    /// candidate that existed, which assumed the users directory holds users. On a real machine it
    /// does not: the one measured here held **1,554 subdirectories**, all but a handful of them
    /// scaffolding left behind by the Omi desktop app's own test harness — `cancelled-status-
    /// reconcile-test-…`, `memories-vm-observer-…`, `transcription-storage-recovery-test-…` — each
    /// with an empty 4 KB `omi.db` inside it. The alphabetical rule therefore resolved to
    /// `cancelled-status-reconcile-test-049BFE18…`, a database with no `memories` table at all,
    /// while the signed-in user's real one sat two hundred entries later holding **6,598 memories in
    /// 58 MB**. Everything downstream read the empty file and reported, perfectly confidently, that
    /// the user had no memories — including the MCP `recall` tool, which advertises local memories to
    /// Claude as always available.
    ///
    /// Size is the right discriminator because it is the direct evidence: a database with the user's
    /// history in it is bigger than one with an empty schema in it, and no assumption about the
    /// *shape* of a user id has to hold for that to be true. `stat` on every candidate costs
    /// microseconds and opens nothing; asking each file whether its `memories` table is populated
    /// would be the more literal question and would mean opening fifteen hundred SQLite databases on
    /// a path the app waits behind. `anonymous` loses every tie, as it did before: it is the
    /// signed-out fallback and a signed-in user's database is always the better answer.
    public static var omiDatabaseURL: URL? {
        omiDatabaseURL(inApplicationSupport: FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask)[0])
    }

    /// The resolution itself, over a stated Application Support root.
    ///
    /// Split out so the rule above can be *proved* against a directory a test builds — the failure it
    /// exists for is entirely about which of many candidates wins, and that is exactly what cannot be
    /// asserted while the root is fixed to the real one. Nothing in this package may write to a real
    /// Omi install to set up a test.
    static func omiDatabaseURL(inApplicationSupport base: URL) -> URL? {
        let fm = FileManager.default
        for rootName in ["Omi", "Omi Beta"] {
            let usersDir = base.appendingPathComponent(rootName, isDirectory: true)
                .appendingPathComponent("users", isDirectory: true)
            guard let candidates = try? fm.contentsOfDirectory(atPath: usersDir.path) else { continue }

            let databases: [(url: URL, userId: String, bytes: Int64)] = candidates.compactMap { userId in
                let db = usersDir.appendingPathComponent(userId, isDirectory: true)
                    .appendingPathComponent("omi.db")
                guard fm.fileExists(atPath: db.path) else { return nil }
                let bytes = (try? fm.attributesOfItem(atPath: db.path)[.size] as? NSNumber)?.int64Value ?? 0
                return (db, userId, bytes)
            }
            guard !databases.isEmpty else { continue }

            let best = databases.max { a, b in
                if a.bytes != b.bytes { return a.bytes < b.bytes }
                // Deterministic tie-breaks, so two empty installs never resolve differently between
                // launches: a named user beats `anonymous`, then the name decides.
                if (a.userId == "anonymous") != (b.userId == "anonymous") { return a.userId == "anonymous" }
                return a.userId > b.userId
            }
            return best?.url
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

    /// The MCP server's running tally of tool calls, drained by the app when it reports. See
    /// `ToolCallLedger` — and note this is a *different* file from the query stamp on purpose: the
    /// stamp answers "did Claude call us just now", this answers "how much", and one file cannot be
    /// both monotonic-latest and cumulative.
    public static var toolCallLedgerURL: URL {
        supportDirectory.appendingPathComponent(toolCallLedgerFilename)
    }

    /// Beside the database the calls were served from, for the reason `queryStampURL(besideDatabaseAt:)`
    /// gives: two processes have to be talking about the same install.
    public static func toolCallLedgerURL(besideDatabaseAt databaseURL: URL) -> URL {
        databaseURL.deletingLastPathComponent().appendingPathComponent(toolCallLedgerFilename)
    }

    /// The lock guarding a ledger read-modify-write. Never renamed or replaced, so concurrent MCP
    /// servers always contend over the same inode — see `ToolCallLedger.bump`.
    public static func toolCallLedgerLockURL(for ledgerURL: URL) -> URL {
        ledgerURL.deletingLastPathComponent()
            .appendingPathComponent(ledgerURL.lastPathComponent + ".lock")
    }

    static let toolCallLedgerFilename = "tool-calls.json"

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
///
/// **`capturing` is derived, never asserted.** The initializer the app uses takes the per-stream
/// reports and works the boolean out from them, so there is no expression anywhere in this codebase
/// that can put `capturing: true` on a state whose screen stream is blocked. That combination is
/// what this file wrote once every thirty seconds for twenty-nine hours while the screen half was
/// dead; see ``CaptureHealth``.
public struct CaptureState: Codable, Sendable, Equatable {
    /// Everything that should be running is running. `private(set)` because it is a *conclusion*,
    /// and a conclusion nobody may edit is a conclusion that cannot disagree with its premises.
    public private(set) var capturing: Bool
    public var pausedReason: String?
    public var capabilities: [CapabilityReport]
    /// One entry per capture stream. Empty only on a state written by an older build, or by the
    /// legacy initializer below — readers must treat empty as "this writer had nothing to say",
    /// never as "there are no streams".
    public private(set) var streams: [StreamReport]
    public var updatedAt: Double

    /// **The initializer the app uses.** `capturing` is not a parameter: it is
    /// `CaptureHealth(of: streams) == .capturing`, and there is no other way to set it.
    public init(
        streams: [StreamReport],
        pausedReason: String? = nil,
        capabilities: [CapabilityReport] = [],
        updatedAt: Double = ContextTime.now
    ) {
        self.streams = streams
        self.capturing = CaptureHealth(of: streams) == .capturing
        self.pausedReason = pausedReason
        self.capabilities = Self.reconciled(capabilities, against: streams)
        self.updatedAt = updatedAt
    }

    /// **A permission may not be published as missing over a stream that is live.**
    ///
    /// The same rule as `capturing`, one field across, and it lives here for the same reason: this
    /// is the only place both halves are in front of each other, so it is the only place the
    /// contradiction can be refused. Measured on a running install, this file carried
    /// `{"name":"screen","state":"live","lastOutputAt":…}` and
    /// `{"name":"screen","granted":false,"detail":"Action required"}` in the same write, over a
    /// database taking screen frames minutes earlier — and the MCP `status` tool read the second of
    /// those and told Claude a whole class of local context was missing.
    ///
    /// A live stream is *observed capture*: the window server answered this process. Nothing
    /// arrived at by asking TCC outranks that, so where the two disagree the observation wins and
    /// the report is republished as granted rather than both being written down.
    ///
    /// Matched by name, and the names line up because both halves speak one vocabulary —
    /// `microphone`, `systemAudio`, `screen`. It is deliberately per stream rather than per file: a
    /// live microphone says nothing whatever about the separate consent for the system-audio tap,
    /// and vouching across the two would hide a genuinely denied permission, which is this same
    /// mistake pointing the other way. A capability with no stream of its own (`accessibility`
    /// enriches the screen stream's text rather than being a stream) is left exactly as the writer
    /// reported it: there is nothing observed to outrank it.
    private static func reconciled(
        _ capabilities: [CapabilityReport], against streams: [StreamReport]
    ) -> [CapabilityReport] {
        capabilities.map { capability in
            guard !capability.granted,
                streams.first(where: { $0.name == capability.name })?.state.isLive == true
            else { return capability }
            return CapabilityReport(
                name: capability.name, granted: true, detail: CapabilityReport.grantedDetail)
        }
    }

    /// A state with no per-stream detail: the terminal beat the app writes on its way out, and what
    /// an older build's file decodes into. Kept because "the app is gone" is a whole answer that
    /// needs no streams to justify it.
    public init(
        capturing: Bool,
        pausedReason: String? = nil,
        capabilities: [CapabilityReport] = [],
        updatedAt: Double = ContextTime.now
    ) {
        self.capturing = capturing
        self.pausedReason = pausedReason
        self.capabilities = capabilities
        self.streams = []
        self.updatedAt = updatedAt
    }

    /// The three-valued answer. Falls back to the boolean only for a state that carries no streams
    /// at all, which is exactly the older-writer and terminal-beat cases above.
    public var health: CaptureHealth {
        guard !streams.isEmpty else { return capturing ? .capturing : .off }
        return CaptureHealth(of: streams)
    }

    public func stream(_ name: String) -> StreamReport? {
        streams.first { $0.name == name }
    }

    /// Streams that are neither live nor deliberately off — the half of the recorder that is
    /// supposed to be working and is not.
    public var failingStreams: [StreamReport] {
        streams.filter { $0.state == .blocked || $0.state == .stalled }
    }

    // MARK: Coding
    //
    // Written by hand rather than synthesised for one reason: `streams` is new, and an older
    // heartbeat file has no such key. A synthesised `init(from:)` throws on a missing key
    // regardless of the property's default, which would make a newer MCP binary refuse to read the
    // file a slightly older app is still writing — reported to the user as "Context for Claude is
    // not running" while it demonstrably is. Decoding is therefore tolerant in both directions:
    // an old reader ignores `streams`, and a new reader treats its absence as "no detail offered".

    private enum CodingKeys: String, CodingKey {
        case capturing, pausedReason, capabilities, streams, updatedAt
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        capturing = try container.decodeIfPresent(Bool.self, forKey: .capturing) ?? false
        pausedReason = try container.decodeIfPresent(String.self, forKey: .pausedReason)
        capabilities =
            try container.decodeIfPresent([CapabilityReport].self, forKey: .capabilities) ?? []
        streams = try container.decodeIfPresent([StreamReport].self, forKey: .streams) ?? []
        updatedAt = try container.decodeIfPresent(Double.self, forKey: .updatedAt) ?? 0
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        // Always written, and written first, because it is the only key an older reader knows.
        try container.encode(capturing, forKey: .capturing)
        try container.encodeIfPresent(pausedReason, forKey: .pausedReason)
        try container.encode(capabilities, forKey: .capabilities)
        try container.encode(streams, forKey: .streams)
        try container.encode(updatedAt, forKey: .updatedAt)
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
