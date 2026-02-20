import Foundation
import GRDB

/// Polls the local GRDB database every 3 seconds for new/changed rows and
/// POSTs them to the cloud agent VM's `/sync` endpoint.
///
/// Cursor strategy:
/// - Append-only tables (screenshots, transcription_segments, …): track `lastSyncedId`
/// - Mutable tables (action_items, memories, …): track `lastSyncedUpdatedAt`
///
/// Cursors are persisted in UserDefaults so sync resumes after restart.
actor AgentSyncService {
    static let shared = AgentSyncService()

    // MARK: - Types

    private struct SyncCursor: Codable {
        var lastId: Int64
        var lastUpdatedAt: String  // ISO-8601
    }

    private struct TableSpec {
        let name: String
        let appendOnly: Bool  // true = cursor by id, false = cursor by updatedAt
        let excludedColumns: Set<String>
    }

    // MARK: - State

    private var cursors: [String: SyncCursor] = [:]
    private var vmIP: String?
    private var authToken: String?
    private var isRunning = false
    private var syncTask: Task<Void, Never>?
    private var consecutiveFailures = 0
    private var lastTokenRefresh: Date = .distantPast
    private var isPaused = false
    private var latencyBackoffMultiplier: UInt64 = 1

    private let batchSize = 100
    private let baseSyncInterval: UInt64 = 3_000_000_000  // 3s in nanoseconds
    private let maxSyncInterval: UInt64 = 60_000_000_000  // 60s max backoff
    private let tokenRefreshInterval: TimeInterval = 30 * 60  // 30 minutes

    // MARK: - Table definitions

    private let tables: [TableSpec] = [
        // Mutable (cursor by updatedAt) — sessions before segments (FK dependency)
        TableSpec(name: "transcription_sessions", appendOnly: false, excludedColumns: []),
        TableSpec(name: "action_items", appendOnly: false, excludedColumns: [
            "agentStatus", "agentSessionName", "agentPrompt", "agentPlan",
            "agentStartedAt", "agentCompletedAt", "agentEditedFilesJson",
            "chatSessionId",
        ]),
        TableSpec(name: "memories", appendOnly: false, excludedColumns: []),
        TableSpec(name: "staged_tasks", appendOnly: false, excludedColumns: []),
        TableSpec(name: "live_notes", appendOnly: false, excludedColumns: []),
        // Append-only (cursor by id) — segments after sessions
        TableSpec(name: "screenshots", appendOnly: true, excludedColumns: [
            "ocrDataJson",
        ]),
        TableSpec(name: "transcription_segments", appendOnly: true, excludedColumns: []),
        TableSpec(name: "focus_sessions", appendOnly: true, excludedColumns: []),
        TableSpec(name: "observations", appendOnly: true, excludedColumns: []),
    ]

    // Tables with only a createdAt (no updatedAt) that are append-only but not tracked
    // by id — handled via appendOnly=true above.

    // MARK: - Public API

    /// Start the sync loop. Called after the VM is ready and DB is uploaded.
    func start(vmIP: String, authToken: String) {
        guard !isRunning else {
            log("AgentSync: already running, updating VM address to \(vmIP)")
            self.vmIP = vmIP
            self.authToken = authToken
            return
        }
        self.vmIP = vmIP
        self.authToken = authToken
        self.isRunning = true
        loadCursors()
        log("AgentSync: starting (vm=\(vmIP), tables=\(tables.count))")
        syncLoop()
    }

    /// Flush pending changes and stop the sync loop.
    func stop() async {
        guard isRunning else { return }
        log("AgentSync: stopping — flushing final changes")
        // Do one final tick before stopping
        await syncTick()
        isRunning = false
        syncTask?.cancel()
        syncTask = nil
        log("AgentSync: stopped")
    }

    /// Pause sync — ticks are skipped but the loop keeps running.
    func pause() {
        guard !isPaused else { return }
        isPaused = true
        log("AgentSync: paused")
    }

    /// Resume sync after a pause.
    func resume() {
        guard isPaused else { return }
        isPaused = false
        log("AgentSync: resumed")
    }

    // MARK: - Sync loop

    private func syncLoop() {
        syncTask = Task {
            while !Task.isCancelled && isRunning {
                if isPaused {
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
        let base: UInt64
        if consecutiveFailures > 0 {
            // Exponential backoff: 3s, 6s, 12s, 24s, 48s, capped at 60s
            base = baseSyncInterval * UInt64(1 << min(consecutiveFailures, 5))
        } else {
            base = baseSyncInterval
        }
        return min(base * latencyBackoffMultiplier, maxSyncInterval)
    }

    private func syncTick() async {
        // Skip if user is signed out (tokens are cleared)
        guard AuthState.shared.isSignedIn else { return }
        let tickStart = ContinuousClock.now

        // Periodically refresh Firebase token on the VM (every 30 min)
        if Date().timeIntervalSince(lastTokenRefresh) >= tokenRefreshInterval {
            await refreshFirebaseToken()
        }

        var totalSynced = 0
        var anyFailed = false
        for spec in tables {
            let count = await syncTable(spec)
            if count < 0 {
                anyFailed = true
            } else {
                totalSynced += count
            }
        }
        if anyFailed && totalSynced == 0 {
            consecutiveFailures += 1
            if consecutiveFailures == 1 || consecutiveFailures % 10 == 0 {
                log("AgentSync: backend unreachable (failures=\(consecutiveFailures), next retry in \(currentSyncInterval() / 1_000_000_000)s)")
            }
        } else if totalSynced > 0 {
            if consecutiveFailures > 0 {
                log("AgentSync: backend reconnected after \(consecutiveFailures) failures")
            }
            consecutiveFailures = 0
            log("AgentSync: pushed \(totalSynced) rows")
            saveCursors()
        }

        // Latency-based backpressure
        let elapsed = ContinuousClock.now - tickStart
        let elapsedSeconds = elapsed / .seconds(1)
        if elapsedSeconds > 10 {
            let prev = latencyBackoffMultiplier
            latencyBackoffMultiplier = min(latencyBackoffMultiplier * 2, maxSyncInterval / baseSyncInterval)
            if latencyBackoffMultiplier != prev {
                log("AgentSync: tick took \(String(format: "%.1f", elapsedSeconds))s, backoff multiplier \(prev)x → \(latencyBackoffMultiplier)x (interval \(currentSyncInterval() / 1_000_000_000)s)")
            }
        } else if elapsedSeconds < 5 && latencyBackoffMultiplier > 1 {
            let prev = latencyBackoffMultiplier
            latencyBackoffMultiplier = max(latencyBackoffMultiplier / 2, 1)
            if latencyBackoffMultiplier != prev {
                log("AgentSync: tick fast (\(String(format: "%.1f", elapsedSeconds))s), backoff multiplier \(prev)x → \(latencyBackoffMultiplier)x")
            }
        }
    }

    // MARK: - Firebase token refresh

    private func refreshFirebaseToken() async {
        guard let vmIP = vmIP, let authToken = authToken else { return }

        do {
            let idToken = try await AuthService.shared.getIdToken()
            guard let url = URL(string: "http://\(vmIP):8080/auth?token=\(authToken)") else { return }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.timeoutInterval = 15

            let body: [String: String] = ["firebaseToken": idToken]
            request.httpBody = try JSONSerialization.data(withJSONObject: body)

            let (_, response) = try await URLSession.shared.data(for: request)
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                lastTokenRefresh = Date()
                log("AgentSync: Firebase token refreshed on VM")
            }
        } catch {
            log("AgentSync: Firebase token refresh failed — \(error.localizedDescription)")
        }
    }

    // MARK: - Per-table sync

    private func syncTable(_ spec: TableSpec) async -> Int {
        guard let dbPool = await getDBPool() else { return 0 }

        let cursor = cursors[spec.name] ?? SyncCursor(lastId: 0, lastUpdatedAt: "1970-01-01T00:00:00")

        do {
            let rows: [[String: Any]] = try await dbPool.read { db in
                // Get actual column names from the table
                let columnInfos = try Row.fetchAll(db, sql: "PRAGMA table_info('\(spec.name)')")
                let allColumns = columnInfos.compactMap { $0["name"] as? String }
                let columns = allColumns.filter { !spec.excludedColumns.contains($0) }

                guard !columns.isEmpty else { return [] }

                let selectCols = columns.map { "\"\($0)\"" }.joined(separator: ", ")
                let sql: String
                let args: [any DatabaseValueConvertible]

                if spec.appendOnly {
                    sql = "SELECT \(selectCols) FROM \"\(spec.name)\" WHERE id > ? ORDER BY id ASC LIMIT ?"
                    args = [cursor.lastId, self.batchSize]
                } else {
                    sql = "SELECT \(selectCols) FROM \"\(spec.name)\" WHERE updatedAt > ? ORDER BY updatedAt ASC LIMIT ?"
                    args = [cursor.lastUpdatedAt, self.batchSize]
                }

                let dbRows = try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args))

                return dbRows.map { row in
                    var dict: [String: Any] = [:]
                    for col in columns {
                        let dbValue = row[col] as DatabaseValue
                        switch dbValue.storage {
                        case .null:
                            // skip nulls — let the VM use its defaults
                            break
                        case .int64(let v):
                            dict[col] = v
                        case .double(let v):
                            dict[col] = v
                        case .string(let v):
                            dict[col] = v
                        case .blob(let data):
                            // Embeddings and other blobs → base64
                            dict[col] = data.base64EncodedString()
                        }
                    }
                    return dict
                }
            }

            guard !rows.isEmpty else { return 0 }

            // Push to VM
            let result = await pushRows(spec.name, rows)
            if result == .success {
                // Update cursor
                if spec.appendOnly {
                    if let lastId = rows.last?["id"] as? Int64 {
                        cursors[spec.name] = SyncCursor(
                            lastId: lastId,
                            lastUpdatedAt: cursor.lastUpdatedAt
                        )
                    }
                } else {
                    if let lastUpdatedAt = rows.last?["updatedAt"] as? String {
                        cursors[spec.name] = SyncCursor(
                            lastId: cursor.lastId,
                            lastUpdatedAt: lastUpdatedAt
                        )
                    }
                }
                return rows.count
            } else if result == .networkError {
                return -1  // Signal network failure for backoff
            }
        } catch {
            log("AgentSync: error reading \(spec.name) — \(error.localizedDescription)")
        }
        return 0
    }

    // MARK: - HTTP push

    private enum PushResult {
        case success
        case httpError
        case networkError
    }

    private func pushRows(_ table: String, _ rows: [[String: Any]]) async -> PushResult {
        guard let vmIP = vmIP, let authToken = authToken else { return .networkError }

        guard let url = URL(string: "http://\(vmIP):8080/sync?token=\(authToken)") else {
            log("AgentSync: invalid sync URL for vmIP=\(vmIP), skipping push")
            return .httpError
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30

        let payload: [String: Any] = ["table": table, "rows": rows]
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        } catch {
            log("AgentSync: JSON serialization error for \(table) — \(error.localizedDescription)")
            return .httpError
        }

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else { return .httpError }

            if httpResponse.statusCode == 200 {
                return .success
            } else {
                let body = String(data: data, encoding: .utf8) ?? ""
                log("AgentSync: push \(table) failed — HTTP \(httpResponse.statusCode): \(body)")
                return .httpError
            }
        } catch {
            log("AgentSync: push \(table) network error — \(error.localizedDescription)")
            return .networkError
        }
    }

    // MARK: - Database access

    private func getDBPool() async -> DatabasePool? {
        try? await RewindDatabase.shared.initialize()
        return await RewindDatabase.shared.getDatabaseQueue()
    }

    // MARK: - Cursor persistence

    private func loadCursors() {
        guard let data = UserDefaults.standard.data(forKey: "agentSync_cursors"),
              let decoded = try? JSONDecoder().decode([String: SyncCursor].self, from: data)
        else {
            log("AgentSync: no saved cursors, starting fresh")
            return
        }
        cursors = decoded
        log("AgentSync: loaded cursors for \(decoded.keys.sorted().joined(separator: ", "))")
    }

    private func saveCursors() {
        guard let data = try? JSONEncoder().encode(cursors) else { return }
        UserDefaults.standard.set(data, forKey: "agentSync_cursors")
    }
}
