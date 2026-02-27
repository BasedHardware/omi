import Foundation
import GRDB

/// Syncs screenshot metadata + embeddings from the local GRDB database
/// to the backend API (`POST /v1/screen-activity/sync`), which stores them
/// in Firestore + Pinecone so the normal Flutter chat can answer screen
/// activity questions.
///
/// Only syncs screenshots that have embeddings (OCR'd ones).
/// Tracks cursor via UserDefaults to resume after restart.
actor ScreenActivitySyncService {
    static let shared = ScreenActivitySyncService()

    // MARK: - State

    private var lastSyncedId: Int64 = 0
    private var isRunning = false
    private var syncTask: Task<Void, Never>?
    private var consecutiveFailures = 0

    private let batchSize = 100
    private let baseSyncInterval: UInt64 = 10_000_000_000  // 10s in nanoseconds
    private let maxSyncInterval: UInt64 = 120_000_000_000  // 120s max backoff

    private let cursorKey = "screenActivitySync_lastId"

    // MARK: - Public API

    /// Start the sync loop. Call after auth is established and database is ready.
    func start() {
        guard !isRunning else {
            log("ScreenActivitySync: already running")
            return
        }
        isRunning = true
        loadCursor()
        log("ScreenActivitySync: starting (lastSyncedId=\(lastSyncedId))")
        syncLoop()
    }

    /// Stop the sync loop.
    func stop() {
        guard isRunning else { return }
        isRunning = false
        syncTask?.cancel()
        syncTask = nil
        log("ScreenActivitySync: stopped")
    }

    // MARK: - Sync loop

    private func syncLoop() {
        syncTask = Task {
            while !Task.isCancelled && isRunning {
                // Skip if user is signed out
                guard await AuthState.shared.isSignedIn else {
                    try? await Task.sleep(nanoseconds: baseSyncInterval)
                    continue
                }
                await syncTick()
                let interval = currentSyncInterval()
                try? await Task.sleep(nanoseconds: interval)
            }
        }
    }

    private func currentSyncInterval() -> UInt64 {
        if consecutiveFailures > 0 {
            // Exponential backoff: 10s, 20s, 40s, 80s, capped at 120s
            let backoff = baseSyncInterval * UInt64(1 << min(consecutiveFailures, 4))
            return min(backoff, maxSyncInterval)
        }
        return baseSyncInterval
    }

    private func syncTick() async {
        guard let dbPool = await getDBPool() else { return }

        do {
            // Query screenshots that have embeddings and are newer than our cursor
            let rows: [[String: Any]] = try await dbPool.read { [lastSyncedId, batchSize] db in
                let sql = """
                    SELECT id, timestamp, appName, windowTitle, ocrText, embedding
                    FROM screenshots
                    WHERE id > ? AND embedding IS NOT NULL
                    ORDER BY id ASC
                    LIMIT ?
                    """
                let dbRows = try Row.fetchAll(db, sql: sql, arguments: [lastSyncedId, batchSize])

                return dbRows.compactMap { row -> [String: Any]? in
                    guard let id = row["id"] as? Int64 else { return nil }

                    var dict: [String: Any] = ["id": id]

                    if let ts = row["timestamp"] as? String {
                        dict["timestamp"] = ts
                    } else if let ts = row["timestamp"] as? Double {
                        let date = Date(timeIntervalSince1970: ts)
                        dict["timestamp"] = ISO8601DateFormatter().string(from: date)
                    }

                    dict["appName"] = (row["appName"] as? String) ?? ""
                    dict["windowTitle"] = (row["windowTitle"] as? String) ?? ""
                    dict["ocrText"] = (row["ocrText"] as? String) ?? ""

                    // Convert embedding BLOB to [Double] array
                    if let blobValue = row["embedding"] as DatabaseValue {
                        if case .blob(let data) = blobValue.storage {
                            let floatCount = data.count / MemoryLayout<Float>.size
                            let floats = data.withUnsafeBytes { ptr in
                                Array(UnsafeBufferPointer(
                                    start: ptr.baseAddress?.assumingMemoryBound(to: Float.self),
                                    count: floatCount
                                ))
                            }
                            dict["embedding"] = floats.map { Double($0) }
                        }
                    }

                    return dict
                }
            }

            guard !rows.isEmpty else { return }

            // Push to backend
            let success = await pushRows(rows)
            if success {
                if let maxId = rows.compactMap({ $0["id"] as? Int64 }).max() {
                    lastSyncedId = maxId
                    saveCursor()
                }
                if consecutiveFailures > 0 {
                    log("ScreenActivitySync: reconnected after \(consecutiveFailures) failures")
                }
                consecutiveFailures = 0
                log("ScreenActivitySync: synced \(rows.count) rows (lastId=\(lastSyncedId))")
            } else {
                consecutiveFailures += 1
                if consecutiveFailures == 1 || consecutiveFailures % 10 == 0 {
                    log("ScreenActivitySync: push failed (failures=\(consecutiveFailures))")
                }
            }
        } catch {
            log("ScreenActivitySync: read error — \(error.localizedDescription)")
        }
    }

    // MARK: - HTTP push

    private func pushRows(_ rows: [[String: Any]]) async -> Bool {
        let payload: [String: Any] = ["rows": rows]

        guard let jsonData = try? JSONSerialization.data(withJSONObject: payload) else {
            log("ScreenActivitySync: JSON serialization error")
            return false
        }

        do {
            let headers = try await APIClient.shared.buildHeaders()
            let baseURL = await APIClient.shared.baseURL
            guard let url = URL(string: baseURL + "v1/screen-activity/sync") else {
                log("ScreenActivitySync: invalid URL")
                return false
            }

            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.httpBody = jsonData
            request.timeoutInterval = 30
            for (key, value) in headers {
                request.setValue(value, forHTTPHeaderField: key)
            }

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else { return false }

            if httpResponse.statusCode == 200 {
                return true
            } else {
                let body = String(data: data, encoding: .utf8) ?? ""
                log("ScreenActivitySync: HTTP \(httpResponse.statusCode): \(body)")
                return false
            }
        } catch {
            log("ScreenActivitySync: network error — \(error.localizedDescription)")
            return false
        }
    }

    // MARK: - Database access

    private func getDBPool() async -> DatabasePool? {
        try? await RewindDatabase.shared.initialize()
        return await RewindDatabase.shared.getDatabaseQueue()
    }

    // MARK: - Cursor persistence

    private func loadCursor() {
        lastSyncedId = Int64(UserDefaults.standard.integer(forKey: cursorKey))
        log("ScreenActivitySync: loaded cursor lastSyncedId=\(lastSyncedId)")
    }

    private func saveCursor() {
        UserDefaults.standard.set(Int(lastSyncedId), forKey: cursorKey)
    }
}
