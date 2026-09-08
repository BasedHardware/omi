import Combine
import CryptoKit
import ContextCore
import Foundation
// Row-level access to `frames`: the `Queries` façade returns display `Hit`s with the row id
// dropped and the OCR truncated, and a cursor needs the id and the untruncated text.
import GRDB

/// Pushes captured screen frames into the user's Omi account so the rest of Omi — chat, memories,
/// the phone app — can see what was on screen, not just what was said.
///
/// This runs for the lifetime of the app, so every decision here is about being cheap and quiet:
/// a cursor instead of a scan, a bounded batch instead of the whole table, and a backoff that lets
/// a backend outage cost one request every five minutes rather than one every minute.
///
/// The endpoint is the **Rust** desktop backend, not the Python API that `OmiAPI` is pointed at, so
/// the request is built here and only the auth/telemetry header set is borrowed from `OmiAPI`.
///
/// **Airgap Mode stops this outright.** This is the single most consequential client in the app for
/// that switch — the payload is the OCR'd contents of the user's screen — so the flag is read at the
/// top of every drain *and* again before every request, and nothing is read from disk while it is on.
/// No data is lost by stopping: the cursor only advances on a 2xx, so the whole backlog is still
/// owed and goes up when Airgap Mode is turned off.
@MainActor
final class ScreenActivityUploader: ObservableObject {
    static let shared = ScreenActivityUploader()

    // MARK: - Observable state

    /// Epoch seconds of the last drain that finished cleanly — including one that found nothing to
    /// send. It answers "is my screen history up to date?", which is what a UI wants to show.
    @Published private(set) var lastSyncedAt: Double?

    /// Nil while healthy. Holds the last user-meaningful reason a drain did not complete.
    @Published private(set) var lastError: String?

    // MARK: - Tuning

    private static let endpoint = URL(
        string: "https://desktop-backend-hhibjajaja-uc.a.run.app/v1/screen-activity/sync")!

    /// The server rejects 101+ rows with a 400, so this is a contract value, not a preference.
    private static let batchSize = 100

    /// A first sync after days of capture can have thousands of rows waiting. Draining several
    /// batches per tick clears that in minutes instead of hours, and the cap stops a large backlog
    /// from turning into an unbounded upload session that ignores `stop()`.
    private static let maxBatchesPerTick = 20

    private static let baseInterval: TimeInterval = 60
    private static let maxInterval: TimeInterval = 300
    private static let requestTimeout: TimeInterval = 60

    private static let cursorKey = "context.screenSync.lastId"
    private static let installIdKey = "context.screenSync.installId"
    private static let category = "screensync"

    /// Ephemeral, no-disk-cache session: the payloads are OCR text and window titles from the user's
    /// screen. Nothing about them belongs in a persistent URL cache.
    private static let urlSession: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = requestTimeout
        config.urlCache = nil
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.httpShouldSetCookies = false
        return URLSession(configuration: config)
    }()

    // MARK: - State

    private var loop: Task<Void, Never>?
    /// Whether the caller wants periodic syncing at all — lets a manual `syncNow()` revive a loop
    /// that a paywall stopped, without reviving one the caller deliberately stopped.
    private var wantsPeriodicSync = false
    private var isDraining = false
    private var consecutiveFailures = 0
    private var isTrialExpired = false
    private var didLogSignedOut = false
    private var didLogAirgap = false
    private var hadPendingWork = false

    /// Whether the loop is down *because of Airgap Mode*, as opposed to down for one of the other
    /// reasons that also leave `loop == nil` while `wantsPeriodicSync` is true.
    ///
    /// This exists because `ExclusionEngine.mutate` calls **every** observer on **every** change, so
    /// the airgap observer below fires when the user ticks any checkbox in Settings › Exclusions. Its
    /// resume branch used to key on `loop == nil` alone, which is not "airgap was on" — after a trial
    /// expiry the loop nils itself and `wantsPeriodicSync` stays true, so excluding an app would log
    /// "Airgap Mode off — resuming screen sync" about a switch that was never on and spend another
    /// authenticated round trip re-learning that the trial is over. `ListenSocket.observeAirgap` never
    /// had this bug because it gates its resume on `state == .airgapped`; this flag is that state.
    private var isSuspendedByAirgap = false

    /// Registered the first time `start()` is called, so turning Airgap Mode off resumes syncing
    /// without a relaunch — which is what the Settings row now promises.
    private var airgapObserver: UUID?

    /// A read-only handle. WAL means it never blocks the capture writer, and nothing here writes:
    /// the cursor lives in `UserDefaults`, so a failed upload leaves the database untouched.
    private var store: ContextStore?

    /// The highest local row id the server has acknowledged. Everything above it is still owed.
    private var lastSyncedId: Int64

    private lazy var clientDeviceId: String = Self.resolveClientDeviceId(in: defaults)
    private lazy var deviceName: String? = {
        let name = Host.current().localizedName ?? ""
        return name.isEmpty ? nil : name
    }()

    // MARK: - Dependencies

    // Everything this class needs from outside itself, as replaceable closures with the production
    // wiring as their defaults. The airgap guard is why: "this drain sent nothing" is only provable
    // against a transport that can record having been called, and a guard nobody can prove is a
    // guard that quietly stops working. See `AirgapEgressTests`.

    private let isAirgapped: @MainActor () -> Bool
    private let isSignedIn: @MainActor () -> Bool
    private let openStore: @Sendable () throws -> ContextStore
    private let authHeaders: (Bool) async throws -> [String: String]
    private let transport: @MainActor (URLRequest) async throws -> (Data, URLResponse)
    private let defaults: UserDefaults
    /// The engine whose changes are watched. Injected so a test drives a throwaway configuration file
    /// rather than the developer's own — and so registering an observer in a test cannot leave one on
    /// the process-wide singleton.
    private let exclusions: ExclusionEngine

    init(
        isAirgapped: @escaping @MainActor () -> Bool = { NetworkEgress.isSuppressed(.screenActivitySync) },
        isSignedIn: @escaping @MainActor () -> Bool = { OmiAuth.shared.isSignedIn },
        openStore: @escaping @Sendable () throws -> ContextStore = { try ContextStore(readOnly: true) },
        authHeaders: @escaping (Bool) async throws -> [String: String] = {
            try await OmiAPI.shared.headers(forceRefresh: $0)
        },
        // Defaulted through nil rather than as a default expression: `urlSession` is `private`, and a
        // default argument on an internal initializer may not name a private declaration.
        transport: (@MainActor (URLRequest) async throws -> (Data, URLResponse))? = nil,
        defaults: UserDefaults = .standard,
        exclusions: ExclusionEngine = .shared
    ) {
        self.isAirgapped = isAirgapped
        self.isSignedIn = isSignedIn
        self.openStore = openStore
        self.authHeaders = authHeaders
        self.transport = transport ?? Self.defaultTransport
        self.defaults = defaults
        self.exclusions = exclusions
        lastSyncedId = Int64(defaults.integer(forKey: Self.cursorKey))
    }

    private static func defaultTransport(_ request: URLRequest) async throws -> (Data, URLResponse) {
        try await urlSession.data(for: request)
    }

    // MARK: - Lifecycle

    /// Begins the periodic drain. Safe to call when already running.
    ///
    /// Under Airgap Mode no loop is started at all — a timer whose every tick would refuse itself is
    /// just a battery cost — but the observer *is* registered, so the sync resumes the moment the
    /// switch goes off.
    func start() {
        wantsPeriodicSync = true
        observeAirgap()
        guard !isAirgapped() else {
            noteSuppressedByAirgap()
            return
        }
        guard loop == nil else { return }
        isTrialExpired = false
        didLogAirgap = false
        isSuspendedByAirgap = false
        ContextLog.info("Screen sync started (cursor=\(lastSyncedId))", Self.category)

        loop = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.drain()
                // A paywall is a decision, not a transient failure: stop rather than spend a
                // request every interval learning the same thing.
                if self.isTrialExpired {
                    self.loop = nil
                    ContextLog.info("Screen sync loop stopped: desktop trial expired", Self.category)
                    return
                }
                let interval = self.currentInterval
                do {
                    try await Task.sleep(nanoseconds: UInt64(interval * 1_000_000_000))
                } catch {
                    return  // cancelled by stop()
                }
            }
        }
    }

    func stop() {
        wantsPeriodicSync = false
        // Removed ahead of the guard below, and not left registered the way it used to be. `start()`
        // re-registers, so keeping it buys nothing, and the engine holds the handler for the process
        // lifetime: every instance that ever started and stopped left a dead observer behind it.
        // Harmless for the singleton, not harmless now that `init` is internal — a suite that
        // constructs uploaders would grow `ExclusionEngine.shared`'s observer list test by test.
        // `ListenSocket.stop()` has always done this; this is the same removal.
        if let airgapObserver { exclusions.removeObserver(airgapObserver) }
        airgapObserver = nil
        isSuspendedByAirgap = false
        guard loop != nil else { return }
        loop?.cancel()
        loop = nil
        ContextLog.info("Screen sync stopped (cursor=\(lastSyncedId))", Self.category)
    }

    /// The other end of the observer's lifetime. `stop()` covers the app; this covers an instance
    /// that is simply released — a test's, or any future non-singleton — because the engine's
    /// observer table would otherwise hold a handler for an uploader that no longer exists.
    /// The handler captures `self` weakly, so this is reachable.
    deinit {
        if let airgapObserver { exclusions.removeObserver(airgapObserver) }
    }

    /// Drains now, outside the schedule. An explicit request also clears a paywall stop — a person
    /// who just upgraded should not have to relaunch, and one request is not the retry loop we
    /// refuse to run.
    ///
    /// Airgap Mode is *not* cleared here, and a manual sync does not override it: the paywall is
    /// someone else's decision about this account, but Airgap Mode is this user's own decision about
    /// this Mac, and a button that quietly overrode it would be the same broken promise again.
    func syncNow() async {
        isTrialExpired = false
        await drain()
        if !isTrialExpired, wantsPeriodicSync, loop == nil, !isAirgapped() { start() }
    }

    // MARK: - Airgap

    /// What an exclusion change means for the sync loop right now.
    enum AirgapTransition: Equatable {
        /// Nothing to do. Most changes land here — the user excluded an app, and this loop's state
        /// is already the state it should be in.
        case ignore
        /// Airgap Mode came on while the loop was running.
        case suspend
        /// Airgap Mode went off, and this loop is down *because* of it.
        case resume
    }

    /// The observer's whole decision, as a method rather than as three conditions inline.
    ///
    /// Split out because it is the thing that was wrong and the thing that has to stay right:
    /// `ExclusionEngine.mutate` fires every observer on every change, so this is called when the user
    /// ticks any checkbox in Settings › Exclusions, and it has to answer `.ignore` for all of them.
    /// The old inline version discriminated on `loop == nil` alone, which is true of *any* stopped
    /// loop — so a trial-expired stop read as an airgap one and every checkbox restarted a loop the
    /// paywall had deliberately stopped, cleared `isTrialExpired`, and spent another authenticated
    /// round trip. Asking `isSuspendedByAirgap` is what makes "resume" mean what it says.
    func airgapTransition(airgapMode: Bool) -> AirgapTransition {
        guard wantsPeriodicSync else { return .ignore }
        if airgapMode { return loop == nil ? .ignore : .suspend }
        return isSuspendedByAirgap ? .resume : .ignore
    }

    /// Airgap Mode is a live switch, not a launch-time one. Turning it on stops the loop before its
    /// next tick; turning it off starts the drain again and the backlog goes up from the cursor.
    private func observeAirgap() {
        guard airgapObserver == nil else { return }
        // The engine calls observers on whichever thread made the change, so hop before touching
        // any of this class's state.
        airgapObserver = exclusions.addObserver { [weak self] set in
            let airgapMode = set.airgapMode
            Task { @MainActor in
                guard let self else { return }
                switch self.airgapTransition(airgapMode: airgapMode) {
                case .ignore:
                    break
                case .suspend:
                    self.suspendForAirgap()
                case .resume:
                    ContextLog.info("Airgap Mode off — resuming screen sync", Self.category)
                    self.start()
                }
            }
        }
    }

    private func suspendForAirgap() {
        guard loop != nil else { return }
        loop?.cancel()
        loop = nil
        noteSuppressedByAirgap()
    }

    /// Records a suppression, and deliberately does **not** touch `lastSyncedAt`.
    ///
    /// Stamping it would make every reader believe the account is up to date while a backlog of
    /// screen frames sits on this Mac — the failure mode that looks exactly like success. `lastError`
    /// carries the honest sentence instead, and it names the setting so the state is undoable.
    private func noteSuppressedByAirgap() {
        lastError = NetworkEgress.explanation(.screenActivitySync)
        // Every route into this method — `start()`, `drain()`, `suspendForAirgap()` — means the same
        // thing: not syncing, and Airgap Mode is why. That is the one condition the observer's resume
        // branch may act on. `suspendForAirgap()` deliberately returns before reaching here when the
        // loop was already down, so a trial-expired stop is never mistaken for an airgap one.
        isSuspendedByAirgap = true
        guard !didLogAirgap else { return }
        didLogAirgap = true
        ContextLog.info(
            "Airgap Mode on — screen frames stay on this Mac (cursor=\(lastSyncedId))", Self.category)
        // Degraded, never dropped: the cursor has not moved, so every frame is still owed and still
        // on disk. Nothing here reaches the network — see `NetworkEgress`.
        NetworkEgress.recordSuppression(.screenActivitySync, outcome: .degraded)
    }

    // MARK: - Drain

    /// What one drain actually did.
    ///
    /// Returned rather than only logged because the airgap guard has to be provable: a `Void`
    /// function that "does nothing" is indistinguishable from one that silently sent.
    enum DrainOutcome: Equatable {
        /// Airgap Mode is on. Nothing was read, nothing was sent, the cursor did not move.
        case suppressedByAirgap
        case signedOut
        case alreadyDraining
        /// Nothing has been captured on this Mac yet, or the local database went away.
        case nothingToRead(String)
        /// Everything owed has been accepted.
        case caughtUp
        /// A batch went up and more is still owed; the next tick continues from the cursor.
        case moreToSend
        case cancelled
        /// A permanent stop with a user-meaningful reason (an expired trial, a lost session).
        case halted(String)
        case failed(String)
    }

    @discardableResult
    func drain() async -> DrainOutcome {
        // Airgap Mode first, and before a single row is read. The payload here is the OCR'd contents
        // of the user's screen; the cheapest way to keep a promise about a payload is never to build
        // one. This also means a suppressed drain touches no database and no Keychain.
        guard !isAirgapped() else {
            noteSuppressedByAirgap()
            return .suppressedByAirgap
        }
        didLogAirgap = false
        isSuspendedByAirgap = false

        guard !isDraining else { return .alreadyDraining }

        // Signed out is not an error state. Frames keep accumulating locally and go up whole after
        // sign-in, because the cursor has not moved.
        guard isSignedIn() else {
            if !didLogSignedOut {
                didLogSignedOut = true
                ContextLog.info("Signed out — screen frames stay local until sign-in", Self.category)
            }
            return .signedOut
        }
        didLogSignedOut = false

        isDraining = true
        defer { isDraining = false }

        var isDrained = false
        for _ in 0..<Self.maxBatchesPerTick {
            if Task.isCancelled { return .cancelled }

            let rows: [PendingRow]
            do {
                rows = try await loadPending()
            } catch ContextStoreError.notInitialized {
                return .nothingToRead("nothing has been captured yet")
            } catch {
                // Reopen next tick: the file may have been replaced or deleted underneath us.
                store = nil
                let message = "Could not read local frames: \(error.localizedDescription)"
                noteFailure(message)
                return .nothingToRead(message)
            }

            guard let first = rows.first, let last = rows.last else {
                isDrained = true
                break
            }

            switch await send(rows) {
            case .accepted(let synced):
                // Only here, on a 2xx, does the cursor move — and only to the id of the last row in
                // the batch the server accepted.
                advanceCursor(to: last.id)
                lastError = nil
                lastSyncedAt = ContextTime.now
                if consecutiveFailures > 0 {
                    ContextLog.info("Screen sync recovered after \(consecutiveFailures) failures", Self.category)
                }
                consecutiveFailures = 0
                hadPendingWork = true
                ContextLog.info(
                    "Uploaded \(rows.count) frames (ids \(first.id)–\(last.id), accepted=\(synced), cursor=\(lastSyncedId))",
                    Self.category)

            case .suppressedByAirgap:
                // Airgap Mode was turned on mid-drain. Stop before the next request rather than
                // finishing the batches this tick had already planned.
                noteSuppressedByAirgap()
                return .suppressedByAirgap

            case .paywalled(let message):
                isTrialExpired = true
                lastError = message
                ContextLog.error(
                    "Screen sync halted at ids \(first.id)–\(last.id): desktop trial expired", Self.category)
                ContextTelemetry.recordFallback(
                    area: .upload,
                    from: "screen-activity sync",
                    to: "halted",
                    reason: "desktop-trial-expired",
                    outcome: .degraded)
                return .halted(message)

            case .signedOut:
                ContextTelemetry.recordFallback(
                    area: .upload,
                    from: "screen-activity sync",
                    to: "halted",
                    reason: "firebase-session-lost",
                    outcome: .degraded)
                return .signedOut

            case .failed(let message):
                noteFailure("\(message) (\(rows.count) frames, ids \(first.id)–\(last.id))")
                ContextTelemetry.recordFallback(
                    area: .upload,
                    from: "screen-activity sync",
                    to: "retry-with-backoff",
                    reason: "backend-or-network-error",
                    outcome: .retried)
                return .failed(message)
            }

            // A short batch means the table is drained; wait for the next tick.
            if rows.count < Self.batchSize {
                isDrained = true
                break
            }
        }

        // Falling out with a full batch every time means the backlog outlasted this tick's budget.
        // The next tick picks it up from the cursor, so say nothing rather than claim "up to date".
        guard isDrained else { return .moreToSend }
        noteCaughtUp()
        return .caughtUp
    }

    /// A drain that ended with nothing owed. Recorded as a successful sync so the UI can say
    /// "up to date" rather than showing a stale timestamp from the last batch that happened to exist.
    private func noteCaughtUp() {
        lastError = nil
        lastSyncedAt = ContextTime.now
        consecutiveFailures = 0
        if hadPendingWork {
            hadPendingWork = false
            ContextLog.info("Screen sync caught up (cursor=\(lastSyncedId))", Self.category)
        }
    }

    private func noteFailure(_ message: String) {
        consecutiveFailures += 1
        lastError = message
        // Loud on the first failure and then every tenth: a backend outage must not turn the log
        // into its own incident.
        if consecutiveFailures == 1 || consecutiveFailures % 10 == 0 {
            ContextLog.error(
                "Screen sync failed (\(consecutiveFailures) in a row, cursor=\(lastSyncedId)): \(message)",
                Self.category)
        }
    }

    private func advanceCursor(to id: Int64) {
        guard id > lastSyncedId else { return }
        lastSyncedId = id
        defaults.set(Int(id), forKey: Self.cursorKey)
    }

    /// 60 s while healthy, doubling per consecutive failure to a 300 s ceiling.
    private var currentInterval: TimeInterval {
        guard consecutiveFailures > 0 else { return Self.baseInterval }
        let factor = pow(2.0, Double(min(consecutiveFailures, 4)))
        return min(Self.baseInterval * factor, Self.maxInterval)
    }

    // MARK: - Local reads

    private struct PendingRow: Sendable {
        let id: Int64
        let capturedAt: Double
        let appName: String
        let windowTitle: String
        let ocrText: String
    }

    private func loadPending() async throws -> [PendingRow] {
        let existing = store
        let cursor = lastSyncedId
        let limit = Self.batchSize
        let open = openStore

        // Off the main actor: a batch of frames carries up to a hundred pages of OCR text, and the
        // menu bar must not stall behind SQLite while that is decoded.
        let (opened, rows) = try await Task.detached(priority: .utility) {
            () async throws -> (ContextStore, [PendingRow]) in
            let store: ContextStore
            if let existing {
                store = existing
            } else {
                store = try open()
            }
            let batch = try Self.fetch(store, after: cursor, limit: limit)
            return (store, batch)
        }.value

        store = opened
        return rows
    }

    /// The next batch of frames worth uploading, oldest first.
    ///
    /// The "has any signal" test is in SQL on purpose. Filtering in Swift after the fetch would let
    /// a window of pure-noise rows produce an empty batch, and an empty batch has no id to move the
    /// cursor to — the drain would re-read the same rows forever. Excluding them in the query means
    /// every row that comes back is a row we send, so the batch always carries a cursor position.
    private nonisolated static func fetch(
        _ store: ContextStore, after cursor: Int64, limit: Int
    ) throws -> [PendingRow] {
        let sql = """
            SELECT id, capturedAt, appName, windowTitle, ocrText
            FROM frames
            WHERE id > ?
              AND (trim(coalesce(ocrText, ''), char(32, 9, 10, 13)) <> ''
                OR trim(coalesce(windowTitle, ''), char(32, 9, 10, 13)) <> '')
            ORDER BY id ASC
            LIMIT ?
            """

        let rows = try store.read { db in
            try Row.fetchAll(db, sql: sql, arguments: [cursor, limit])
        }

        return try rows.map { row in
            // `id` is the INTEGER PRIMARY KEY, so this cannot legitimately fail — and if it somehow
            // did, dropping the row would let the cursor step over data. Fail the batch instead.
            guard let id: Int64 = row["id"], let capturedAt: Double = row["capturedAt"] else {
                throw UploadError.unreadableRow
            }
            let appName: String = row["appName"] ?? ""
            let windowTitle: String = row["windowTitle"] ?? ""
            let ocrText: String = row["ocrText"] ?? ""
            return PendingRow(
                id: id, capturedAt: capturedAt, appName: appName,
                windowTitle: windowTitle, ocrText: ocrText)
        }
    }

    // MARK: - Upload

    private enum SendOutcome {
        case accepted(synced: Int)
        case suppressedByAirgap
        case paywalled(String)
        case signedOut
        case failed(String)
    }

    private func send(_ rows: [PendingRow]) async -> SendOutcome {
        let body: Data
        do {
            body = try encode(rows)
        } catch {
            return .failed("Could not encode batch: \(error.localizedDescription)")
        }

        var forceRefresh = false
        for attempt in 0..<2 {
            // Re-read per request, not once per drain. A drain runs up to twenty batches and each
            // one is a round trip, so a switch flipped in the middle has to stop the *next* request
            // rather than the next tick — which is what makes "takes effect immediately" true.
            guard !isAirgapped() else { return .suppressedByAirgap }

            let headers: [String: String]
            do {
                headers = try await authHeaders(forceRefresh)
            } catch OmiAPIError.notSignedIn {
                return .signedOut
            } catch OmiAPIError.airgapMode {
                return .suppressedByAirgap
            } catch {
                return .failed("Could not build auth headers: \(error.localizedDescription)")
            }

            var request = URLRequest(url: Self.endpoint)
            request.httpMethod = "POST"
            request.httpBody = body
            request.timeoutInterval = Self.requestTimeout
            for (key, value) in headers {
                request.setValue(value, forHTTPHeaderField: key)
            }
            // Set after the borrowed headers so this request's own contract always wins.
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("macos", forHTTPHeaderField: "X-App-Platform")

            do {
                let (data, response) = try await transport(request)
                guard let http = response as? HTTPURLResponse else {
                    return .failed("Malformed response from screen-activity sync")
                }

                switch http.statusCode {
                case 200..<300:
                    // The write already happened; a response we cannot parse must not undo it.
                    let synced = (try? JSONDecoder().decode(SyncResponse.self, from: data))?.synced
                    return .accepted(synced: synced ?? rows.count)

                case 401 where attempt == 0:
                    // A cached Firebase token expired mid-loop. One forced refresh, then give up.
                    forceRefresh = true
                    continue

                case 402:
                    return .paywalled(
                        "Your Omi desktop trial has expired, so screen activity is no longer syncing. "
                            + "Everything stays captured on this Mac; upgrade your plan and sync resumes.")

                default:
                    return .failed("HTTP \(http.statusCode): \(Self.detail(from: data))")
                }
            } catch {
                return .failed("Network error: \(error.localizedDescription)")
            }
        }

        return .failed("Authorization refused after a token refresh")
    }

    // MARK: - Wire format

    private struct WireRow: Encodable {
        let id: Int64
        let timestamp: String
        let appName: String
        let windowTitle: String
        let ocrText: String
        let deviceName: String?
        let clientDeviceId: String
    }

    private struct WireEnvelope: Encodable {
        let rows: [WireRow]
    }

    private struct SyncResponse: Decodable {
        let synced: Int
        let lastID: Int64

        enum CodingKeys: String, CodingKey {
            case synced
            case lastID = "last_id"
        }
    }

    private enum UploadError: LocalizedError {
        case unreadableRow

        var errorDescription: String? {
            switch self {
            case .unreadableRow: return "A frame row was missing its id or timestamp"
            }
        }
    }

    /// `yyyy-MM-dd HH:mm:ss.SSS`, UTC — the format the backend stores and **sorts by as a string**,
    /// not a preference.
    ///
    /// The server writes `row["timestamp"]` into Firestore verbatim and then range-filters it with
    /// `>=` / `<=` against `strftime('%Y-%m-%d %H:%M:%S.000')` (`backend/database/screen_activity.py`).
    /// Those comparisons are lexicographic, so the separator is load-bearing: this used to send
    /// RFC-3339 (`2026-08-14T12:08:49Z`), and `'T'` (0x54) sorts above `' '` (0x20). Every row this
    /// app wrote therefore sorted *after* every row the Omi desktop app wrote on the same day — an
    /// `end_date` on that day excluded all of ours, and an intra-day `start_date` admitted all of
    /// them whatever their real time. Confirmed in live data: 71 Omi rows from 04:57Z, then all 64
    /// of ours through 12:08Z, with no interleaving at all.
    ///
    /// The Omi desktop app never had this bug because it never formats anything: its `screenshots`
    /// row holds a `Date`, GRDB persists a `Date` as exactly this string in UTC, and its sync
    /// service forwards the stored text unchanged (`ScreenActivitySyncService.payloadRow`). Our
    /// `frames.capturedAt` is epoch seconds, so the same string has to be produced here.
    ///
    /// `en_US_POSIX` because a fixed-format formatter must not follow the user's region: without it
    /// a Japanese or Buddhist calendar locale silently emits a different era and year.
    private static let storageTimestamp: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss.SSS"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter
    }()

    private func encode(_ rows: [PendingRow]) throws -> Data {
        let device = deviceName
        let deviceId = clientDeviceId
        let wire = rows.map { row in
            WireRow(
                id: row.id,
                timestamp: Self.storageTimestamp.string(from: Date(timeIntervalSince1970: row.capturedAt)),
                appName: row.appName,
                windowTitle: row.windowTitle,
                ocrText: row.ocrText,
                deviceName: device,
                clientDeviceId: deviceId)
        }
        return try JSONEncoder().encode(WireEnvelope(rows: wire))
    }

    /// Server error text, capped. Bounded because an error body is not a place to discover that a
    /// backend echoed something large back at us.
    private static func detail(from data: Data) -> String {
        let text = String(data: data, encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !text.isEmpty else { return "no response body" }
        return text.count > 200 ? String(text.prefix(200)) + "…" : text
    }

    // MARK: - Device identity

    /// `{platform}_{hash}` — the same shape the Omi desktop client sends, because the backend's
    /// storage key is `"{clientDeviceId}-{id}"`. Local row ids restart at 1 on every install, so
    /// without this two Macs would write over each other's screen history.
    ///
    /// The install id lives in `UserDefaults` rather than the Keychain: it identifies a capture
    /// source, not the user, and a Keychain read here would risk a password prompt on launch for
    /// something no security decision depends on.
    private static func resolveClientDeviceId(in defaults: UserDefaults) -> String {
        let installId: String
        if let existing = defaults.string(forKey: installIdKey), !existing.isEmpty {
            installId = existing
        } else {
            installId = UUID().uuidString
            defaults.set(installId, forKey: installIdKey)
        }

        let digest = SHA256.hash(data: Data(installId.utf8))
        let hash = digest.map { String(format: "%02x", $0) }.joined().prefix(8)
        return "macos_\(hash)"
    }
}
