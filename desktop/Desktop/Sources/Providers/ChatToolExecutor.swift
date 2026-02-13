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
            return "SQL Error: \(error.localizedDescription)"
        }
    }

    /// Execute a SELECT query and format results as text
    private static func executeSelectQuery(_ query: String, upper: String, dbQueue: DatabaseQueue) async throws -> String {
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
    private static func executeWriteQuery(_ query: String, dbQueue: DatabaseQueue) async throws -> String {
        let changes = try await dbQueue.write { db -> Int in
            try db.execute(sql: query)
            return db.changesCount
        }

        log("Tool execute_sql write: \(changes) row(s) affected")
        return "OK: \(changes) row(s) affected"
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
