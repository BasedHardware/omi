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
    private var hadPendingWork = false

    /// A read-only handle. WAL means it never blocks the capture writer, and nothing here writes:
    /// the cursor lives in `UserDefaults`, so a failed upload leaves the database untouched.
    private var store: ContextStore?

    /// The highest local row id the server has acknowledged. Everything above it is still owed.
    private var lastSyncedId: Int64

    private lazy var clientDeviceId: String = Self.resolveClientDeviceId()
    private lazy var deviceName: String? = {
        let name = Host.current().localizedName ?? ""
        return name.isEmpty ? nil : name
    }()

    private init() {
        lastSyncedId = Int64(UserDefaults.standard.integer(forKey: Self.cursorKey))
    }

    // MARK: - Lifecycle

    /// Begins the periodic drain. Safe to call when already running.
    func start() {
        wantsPeriodicSync = true
        guard loop == nil else { return }
        isTrialExpired = false
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
        guard loop != nil else { return }
        loop?.cancel()
        loop = nil
        ContextLog.info("Screen sync stopped (cursor=\(lastSyncedId))", Self.category)
    }

    /// Drains now, outside the schedule. An explicit request also clears a paywall stop — a person
    /// who just upgraded should not have to relaunch, and one request is not the retry loop we
    /// refuse to run.
    func syncNow() async {
        isTrialExpired = false
        await drain()
        if !isTrialExpired, wantsPeriodicSync, loop == nil { start() }
    }

    // MARK: - Drain

    private func drain() async {
        guard !isDraining else { return }

        // Signed out is not an error state. Frames keep accumulating locally and go up whole after
        // sign-in, because the cursor has not moved.
        guard OmiAuth.shared.isSignedIn else {
            if !didLogSignedOut {
                didLogSignedOut = true
                ContextLog.info("Signed out — screen frames stay local until sign-in", Self.category)
            }
            return
        }
        didLogSignedOut = false

        isDraining = true
        defer { isDraining = false }

        var isDrained = false
        for _ in 0..<Self.maxBatchesPerTick {
            if Task.isCancelled { return }

            let rows: [PendingRow]
            do {
                rows = try await loadPending()
            } catch ContextStoreError.notInitialized {
                return  // nothing has been captured yet
            } catch {
                // Reopen next tick: the file may have been replaced or deleted underneath us.
                store = nil
                noteFailure("Could not read local frames: \(error.localizedDescription)")
                return
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
                return

            case .signedOut:
                ContextTelemetry.recordFallback(
                    area: .upload,
                    from: "screen-activity sync",
                    to: "halted",
                    reason: "firebase-session-lost",
                    outcome: .degraded)
                return

            case .failed(let message):
                noteFailure("\(message) (\(rows.count) frames, ids \(first.id)–\(last.id))")
                ContextTelemetry.recordFallback(
                    area: .upload,
                    from: "screen-activity sync",
                    to: "retry-with-backoff",
                    reason: "backend-or-network-error",
                    outcome: .retried)
                return
            }

            // A short batch means the table is drained; wait for the next tick.
            if rows.count < Self.batchSize {
                isDrained = true
                break
            }
        }

        // Falling out with a full batch every time means the backlog outlasted this tick's budget.
        // The next tick picks it up from the cursor, so say nothing rather than claim "up to date".
        if isDrained { noteCaughtUp() }
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
        UserDefaults.standard.set(Int(id), forKey: Self.cursorKey)
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

        // Off the main actor: a batch of frames carries up to a hundred pages of OCR text, and the
        // menu bar must not stall behind SQLite while that is decoded.
        let (opened, rows) = try await Task.detached(priority: .utility) {
            () async throws -> (ContextStore, [PendingRow]) in
            let store: ContextStore
            if let existing {
                store = existing
            } else {
                store = try ContextStore(readOnly: true)
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
            let headers: [String: String]
            do {
                headers = try await OmiAPI.shared.headers(forceRefresh: forceRefresh)
            } catch OmiAPIError.notSignedIn {
                return .signedOut
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
                let (data, response) = try await Self.urlSession.data(for: request)
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

    private static let rfc3339: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter
    }()

    private func encode(_ rows: [PendingRow]) throws -> Data {
        let device = deviceName
        let deviceId = clientDeviceId
        let wire = rows.map { row in
            WireRow(
                id: row.id,
                timestamp: Self.rfc3339.string(from: Date(timeIntervalSince1970: row.capturedAt)),
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
    private static func resolveClientDeviceId() -> String {
        let defaults = UserDefaults.standard
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
