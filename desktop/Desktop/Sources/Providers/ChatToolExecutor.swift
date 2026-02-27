import Foundation
import GRDB

/// Executes tool calls from Gemini and returns results
/// Tools: execute_sql (read/write SQL on omi.db), semantic_search (vector similarity)
@MainActor
class ChatToolExecutor {

    /// Execute a tool call and return the result as a string
    static func execute(_ toolCall: ToolCall) async -> String {
        log("Executing tool: \(toolCall.name) with args: \(toolCall.arguments)")

        switch toolCall.name {
        case "execute_sql":
            return await executeSQL(toolCall.arguments)

        case "semantic_search":
            return await executeSemanticSearch(toolCall.arguments)

        case "get_daily_recap":
            return await executeDailyRecap(toolCall.arguments)

        default:
            return "Unknown tool: \(toolCall.name)"
        }
    }

    /// Execute multiple tool calls and return results keyed by tool name
    static func executeAll(_ toolCalls: [ToolCall]) async -> [String: String] {
        var results: [String: String] = [:]

        for call in toolCalls {
            results[call.name] = await execute(call)
        }

        return results
    }

    // MARK: - SQL Execution

    /// Blocked SQL keywords that are never allowed
    private static let blockedKeywords: Set<String> = [
        "DROP", "ALTER", "CREATE", "PRAGMA", "ATTACH", "DETACH", "VACUUM"
    ]

    /// Execute a SQL query on omi.db
    private static func executeSQL(_ args: [String: Any]) async -> String {
        guard let query = args["query"] as? String, !query.isEmpty else {
            return "Error: query is required"
        }

        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let upper = trimmed.uppercased()

        // Block dangerous keywords
        for keyword in blockedKeywords {
            // Match keyword at word boundary (start of string or after whitespace/punctuation)
            if upper.range(of: "\\b\(keyword)\\b", options: .regularExpression) != nil {
                return "Error: \(keyword) statements are not allowed"
            }
        }

        // Block multi-statement queries (semicolon followed by another statement)
        let statements = trimmed.components(separatedBy: ";")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        if statements.count > 1 {
            return "Error: multi-statement queries are not allowed. Send one statement at a time."
        }

        // Determine query type
        let isSelect = upper.hasPrefix("SELECT") || upper.hasPrefix("WITH")
        let isInsert = upper.hasPrefix("INSERT")
        let isUpdate = upper.hasPrefix("UPDATE")
        let isDelete = upper.hasPrefix("DELETE")

        // Block UPDATE/DELETE without WHERE
        if (isUpdate || isDelete) && !upper.contains("WHERE") {
            return "Error: \(isUpdate ? "UPDATE" : "DELETE") without WHERE clause is not allowed"
        }

        // Get database queue
        guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
            return "Error: database not available"
        }

        do {
            if isSelect {
                return try await executeSelectQuery(trimmed, upper: upper, dbQueue: dbQueue)
            } else if isInsert || isUpdate || isDelete {
                return try await executeWriteQuery(trimmed, dbQueue: dbQueue)
            } else {
                return "Error: only SELECT, INSERT, UPDATE, DELETE statements are allowed"
            }
        } catch {
            logError("Tool execute_sql failed", error: error)
            return "SQL Error: \(error.localizedDescription)\nFailed query: \(trimmed)"
        }
    }

    /// Execute a SELECT query and format results as text
    private static func executeSelectQuery(_ query: String, upper: String, dbQueue: DatabasePool) async throws -> String {
        // Auto-append LIMIT 200 if no LIMIT clause
        var finalQuery = query
        if !upper.contains("LIMIT") {
            // Remove trailing semicolon if present
            if finalQuery.hasSuffix(";") {
                finalQuery = String(finalQuery.dropLast())
            }
            finalQuery += " LIMIT 200"
        }

        let query = finalQuery
        let rows = try await dbQueue.read { db in
            try Row.fetchAll(db, sql: query)
        }

        if rows.isEmpty {
            return "No results"
        }

        // Get column names from first row
        let columns = Array(rows[0].columnNames)
        var lines: [String] = []

        // Header
        lines.append(columns.joined(separator: " | "))
        lines.append(String(repeating: "-", count: min(columns.count * 20, 120)))

        // Rows (max 200) — Row is RandomAccessCollection of (String, DatabaseValue)
        for row in rows.prefix(200) {
            let values = row.map { (_, dbValue) -> String in
                let value: String
                switch dbValue.storage {
                case .null:
                    value = "NULL"
                case .int64(let i):
                    value = String(i)
                case .double(let d):
                    value = String(d)
                case .string(let s):
                    value = s
                case .blob(let data):
                    value = "<\(data.count) bytes>"
                }
                // Truncate long cell values
                if value.count > 500 {
                    return String(value.prefix(500)) + "..."
                }
                return value
            }
            lines.append(values.joined(separator: " | "))
        }

        lines.append("\n\(rows.count) row(s)")
        log("Tool execute_sql returned \(rows.count) rows")
        return lines.joined(separator: "\n")
    }

    /// Execute a write (INSERT/UPDATE/DELETE) query
    private static func executeWriteQuery(_ query: String, dbQueue: DatabasePool) async throws -> String {
        let changes = try await dbQueue.write { db -> Int in
            try db.execute(sql: query)
            return db.changesCount
        }

        log("Tool execute_sql write: \(changes) row(s) affected")

        // If the query modified the action_items table, refresh TasksStore from local cache
        if changes > 0 {
            let upper = query.uppercased()
            if upper.contains("ACTION_ITEMS") {
                log("Tool execute_sql: action_items modified, refreshing TasksStore")
                await TasksStore.shared.reloadFromLocalCache()
                // Sync newly inserted action items to the backend (Firestore)
                if upper.contains("INSERT") {
                    await TasksStore.shared.retryUnsyncedItems(includeRecent: true)
                }
            }
        }

        return "OK: \(changes) row(s) affected"
    }

    // MARK: - Daily Recap

    /// Get a pre-formatted daily activity recap
    private static func executeDailyRecap(_ args: [String: Any]) async -> String {
        let daysAgo = max(0, (args["days_ago"] as? Int) ?? 1)
        let dateLabel = daysAgo == 0 ? "Today" : daysAgo == 1 ? "Yesterday" : "Past \(daysAgo) days"

        guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
            return "Error: database not available"
        }

        // For today (daysAgo=0), upper bound is now; for past days, upper bound is start of today
        let upperBound = daysAgo == 0
            ? "datetime('now', 'localtime')"
            : "datetime('now', 'start of day', 'localtime')"

        do {
            return try await dbQueue.read { db in
                // Q1: App usage
                let apps = try Row.fetchAll(db, sql: """
                    SELECT appName, COUNT(*) as screenshots, ROUND(COUNT(*) * 10.0 / 60, 1) as minutes,
                        MIN(time(timestamp, 'localtime')) as first_seen, MAX(time(timestamp, 'localtime')) as last_seen
                    FROM screenshots
                    WHERE timestamp >= datetime('now', 'start of day', '-\(daysAgo) day', 'localtime')
                        AND timestamp < \(upperBound)
                        AND appName IS NOT NULL AND appName != ''
                    GROUP BY appName ORDER BY screenshots DESC
                    """)

                // Q2: Conversations
                let convos = try Row.fetchAll(db, sql: """
                    SELECT title, overview, emoji, category, startedAt, finishedAt,
                        ROUND((julianday(finishedAt) - julianday(startedAt)) * 1440, 1) as duration_min
                    FROM transcription_sessions
                    WHERE startedAt >= datetime('now', 'start of day', '-\(daysAgo) day', 'localtime')
                        AND startedAt < \(upperBound)
                        AND deleted = 0 AND discarded = 0
                    ORDER BY startedAt DESC
                    """)

                // Q3: Action items
                let tasks = try Row.fetchAll(db, sql: """
                    SELECT description, completed, priority, createdAt FROM action_items
                    WHERE createdAt >= datetime('now', 'start of day', '-\(daysAgo) day', 'localtime')
                        AND createdAt < \(upperBound)
                        AND deleted = 0
                    ORDER BY createdAt DESC
                    """)

                // Format compact markdown
                var out = "# \(dateLabel) Recap\n\n"

                out += "## Apps (\(apps.count) apps)\n"
                if apps.isEmpty {
                    out += "No screen activity recorded.\n"
                } else {
                    for app in apps.prefix(20) {
                        let name = app["appName"] as? String ?? "Unknown"
                        let minutes = app["minutes"] as? Double ?? 0
                        let screenshots = app["screenshots"] as? Int ?? 0
                        let firstSeen = app["first_seen"] as? String ?? ""
                        let lastSeen = app["last_seen"] as? String ?? ""
                        out += "- **\(name)**: \(minutes) min (\(screenshots) captures, \(firstSeen)–\(lastSeen))\n"
                    }
                    if apps.count > 20 { out += "- ...and \(apps.count - 20) more apps\n" }
                }

                out += "\n## Conversations (\(convos.count))\n"
                if convos.isEmpty {
                    out += "No conversations recorded.\n"
                } else {
                    for convo in convos {
                        let title = convo["title"] as? String ?? "Untitled"
                        let overview = convo["overview"] as? String ?? "No summary"
                        let emoji = convo["emoji"] as? String ?? ""
                        let durMin = convo["duration_min"] as? Double ?? 0
                        let dur = durMin > 0 ? " (\(durMin) min)" : ""
                        out += "- \(emoji) **\(title)**\(dur): \(overview)\n"
                    }
                }

                out += "\n## Tasks (\(tasks.count))\n"
                if tasks.isEmpty {
                    out += "No tasks created.\n"
                } else {
                    for task in tasks {
                        let desc = task["description"] as? String ?? ""
                        let completed = (task["completed"] as? Int ?? 0) == 1
                        let priority = task["priority"] as? String ?? ""
                        let check = completed ? "[x]" : "[ ]"
                        let pri = priority.isEmpty ? "" : " (\(priority))"
                        out += "- \(check) \(desc)\(pri)\n"
                    }
                }

                log("Tool get_daily_recap: \(apps.count) apps, \(convos.count) convos, \(tasks.count) tasks")
                return out
            }
        } catch {
            logError("Tool get_daily_recap failed", error: error)
            return "Error: \(error.localizedDescription)"
        }
    }

    // MARK: - Semantic Search

    /// Search screenshots using vector similarity
    private static func executeSemanticSearch(_ args: [String: Any]) async -> String {
        guard let query = args["query"] as? String, !query.isEmpty else {
            return "Error: query is required"
        }

        let days = (args["days"] as? Int) ?? 7
        let appFilter = args["app_filter"] as? String

        let calendar = Calendar.current
        let endDate = Date()
        let startDate = calendar.date(byAdding: .day, value: -days, to: endDate) ?? endDate

        do {
            let vectorResults = try await OCREmbeddingService.shared.searchSimilar(
                query: query,
                startDate: startDate,
                endDate: endDate,
                appFilter: appFilter,
                topK: 20
            )

            log("Tool semantic_search: vector returned \(vectorResults.count) results")

            // Filter by similarity threshold and fetch screenshot details
            let dateFormatter = DateFormatter()
            dateFormatter.dateStyle = .medium
            dateFormatter.timeStyle = .short

            var lines: [String] = []
            var count = 0

            for result in vectorResults where result.similarity > 0.3 {
                guard let screenshot = try? await RewindDatabase.shared.getScreenshot(id: result.screenshotId) else {
                    continue
                }

                count += 1
                let dateStr = dateFormatter.string(from: screenshot.timestamp)
                let windowTitle = screenshot.windowTitle ?? ""
                let titlePart = windowTitle.isEmpty ? "" : " - \(windowTitle)"
                lines.append("\n\(count). [\(dateStr)] \(screenshot.appName)\(titlePart) (similarity: \(String(format: "%.2f", result.similarity)))")

                // Include OCR text preview (truncated)
                if let ocrText = screenshot.ocrText, !ocrText.isEmpty {
                    let preview = String(ocrText.prefix(300))
                        .replacingOccurrences(of: "\n", with: " ")
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    lines.append("   Content: \(preview)")
                }

                if count >= 15 { break }
            }

            if lines.isEmpty {
                return "No screenshots found matching \"\(query)\" in the last \(days) day(s)."
            }

            lines.insert("Found \(count) screenshot(s) matching \"\(query)\":", at: 0)

            log("Tool semantic_search returned \(count) results")
            return lines.joined(separator: "\n")

        } catch {
            logError("Tool semantic_search failed", error: error)
            return "Failed to search: \(error.localizedDescription)"
        }
    }
}
