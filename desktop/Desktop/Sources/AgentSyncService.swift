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

    private let batchSize = 100
    private let syncInterval: UInt64 = 3_000_000_000  // 3s in nanoseconds

    // MARK: - Table definitions

    private let tables: [TableSpec] = [
        // Append-only (cursor by id)
        TableSpec(name: "screenshots", appendOnly: true, excludedColumns: [
            "ocrDataJson",
        ]),
        TableSpec(name: "transcription_segments", appendOnly: true, excludedColumns: []),
        TableSpec(name: "focus_sessions", appendOnly: true, excludedColumns: []),
        TableSpec(name: "observations", appendOnly: true, excludedColumns: []),
        // Mutable (cursor by updatedAt)
        TableSpec(name: "action_items", appendOnly: false, excludedColumns: [
            "agentStatus", "agentSessionName", "agentPrompt", "agentPlan",
            "agentStartedAt", "agentCompletedAt", "agentEditedFilesJson",
            "chatSessionId",
        ]),
        TableSpec(name: "memories", appendOnly: false, excludedColumns: []),
        TableSpec(name: "staged_tasks", appendOnly: false, excludedColumns: []),
        TableSpec(name: "transcription_sessions", appendOnly: false, excludedColumns: []),
        TableSpec(name: "live_notes", appendOnly: false, excludedColumns: []),
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

    // MARK: - Sync loop

    private func syncLoop() {
        syncTask = Task {
            while !Task.isCancelled && isRunning {
                await syncTick()
                try? await Task.sleep(nanoseconds: syncInterval)
            }
        }
    }

    private func syncTick() async {
        var totalSynced = 0
        for spec in tables {
            totalSynced += await syncTable(spec)
        }
        if totalSynced > 0 {
            log("AgentSync: pushed \(totalSynced) rows")
            saveCursors()
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
            let success = await pushRows(spec.name, rows)
            if success {
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
            }
        } catch {
            log("AgentSync: error reading \(spec.name) — \(error.localizedDescription)")
        }
        return 0
    }

    // MARK: - HTTP push

    private func pushRows(_ table: String, _ rows: [[String: Any]]) async -> Bool {
        guard let vmIP = vmIP, let authToken = authToken else { return false }

        let url = URL(string: "http://\(vmIP):8080/sync?token=\(authToken)")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30

        let payload: [String: Any] = ["table": table, "rows": rows]
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        } catch {
            log("AgentSync: JSON serialization error for \(table) — \(error.localizedDescription)")
            return false
        }

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else { return false }

            if httpResponse.statusCode == 200 {
                return true
            } else {
                let body = String(data: data, encoding: .utf8) ?? ""
                log("AgentSync: push \(table) failed — HTTP \(httpResponse.statusCode): \(body)")
                return false
            }
        } catch {
            log("AgentSync: push \(table) network error — \(error.localizedDescription)")
            return false
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
