import Foundation
import GRDB

/// Executes tool calls from Gemini and returns results
/// Tools: execute_sql (read/write SQL on omi.db), semantic_search (vector similarity)
@MainActor
class ChatToolExecutor {

    // MARK: - Onboarding State

    /// Set by OnboardingChatView before starting the chat
    static var onboardingAppState: AppState?
    /// Called when AI invokes complete_onboarding
    static var onCompleteOnboarding: (() -> Void)?
    /// Called when AI invokes ask_followup — delivers quick-reply options to the UI
    static var onQuickReplyOptions: ((_ options: [String]) -> Void)?

    private static var fileScanStarted = false
    private static var fileScanFileCount = 0

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

        case "complete_task":
            return await executeCompleteTask(toolCall.arguments)

        case "delete_task":
            return await executeDeleteTask(toolCall.arguments)

        // Onboarding tools
        case "request_permission":
            return await executeRequestPermission(toolCall.arguments)

        case "check_permission_status":
            return await executeCheckPermissionStatus(toolCall.arguments)

        case "scan_files", "start_file_scan":
            return await executeScanFiles(toolCall.arguments)

        case "get_file_scan_results":
            return await executeScanFiles(toolCall.arguments)

        case "set_user_preferences":
            return await executeSetUserPreferences(toolCall.arguments)

        case "ask_followup":
            return await executeAskFollowup(toolCall.arguments)

        case "complete_onboarding":
            return await executeCompleteOnboarding(toolCall.arguments)

        case "save_knowledge_graph":
            return await executeSaveKnowledgeGraph(toolCall.arguments)

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

    // MARK: - Task Tools

    /// Toggle a task's completion status via TasksStore (handles local + API sync)
    private static func executeCompleteTask(_ args: [String: Any]) async -> String {
        guard let taskId = args["task_id"] as? String, !taskId.isEmpty else {
            return "Error: task_id is required"
        }

        do {
            guard let task = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: taskId) else {
                return "Error: task not found with id '\(taskId)'"
            }

            if task.deleted == true {
                return "Error: task '\(task.description)' has been deleted"
            }

            let wasCompleted = task.completed
            await TasksStore.shared.toggleTask(task)

            let newState = wasCompleted ? "incomplete" : "completed"
            log("Tool complete_task: toggled '\(task.description)' to \(newState)")
            return "OK: task '\(task.description)' marked as \(newState)"
        } catch {
            logError("Tool complete_task failed", error: error)
            return "Error: \(error.localizedDescription)"
        }
    }

    /// Delete a task via TasksStore (handles local + API sync)
    private static func executeDeleteTask(_ args: [String: Any]) async -> String {
        guard let taskId = args["task_id"] as? String, !taskId.isEmpty else {
            return "Error: task_id is required"
        }

        do {
            guard let task = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: taskId) else {
                return "Error: task not found with id '\(taskId)'"
            }

            if task.deleted == true {
                return "Error: task '\(task.description)' is already deleted"
            }

            await TasksStore.shared.deleteTask(task)

            log("Tool delete_task: deleted '\(task.description)'")
            return "OK: task '\(task.description)' deleted"
        } catch {
            logError("Tool delete_task failed", error: error)
            return "Error: \(error.localizedDescription)"
        }
    }

    // MARK: - Onboarding Tools

    /// Request a specific macOS permission
    private static func executeRequestPermission(_ args: [String: Any]) async -> String {
        guard let type = args["type"] as? String else {
            return "Error: 'type' parameter is required (screen_recording, microphone, notifications, accessibility, automation)"
        }

        guard let appState = onboardingAppState else {
            return "Error: onboarding not active"
        }

        AnalyticsManager.shared.permissionRequested(permission: type)

        switch type {
        case "screen_recording":
            appState.triggerScreenRecordingPermission()
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            appState.checkScreenRecordingPermission()
            try? await Task.sleep(nanoseconds: 500_000_000)
            if appState.hasScreenRecordingPermission {
                return "granted"
            } else {
                return "pending - user needs to toggle Screen Recording for Omi in System Settings, then quit and reopen the app"
            }

        case "microphone":
            appState.requestMicrophonePermission()
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            if appState.hasMicrophonePermission {
                return "granted"
            } else {
                return "pending - user needs to allow microphone access in the system dialog"
            }

        case "notifications":
            appState.requestNotificationPermission()
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            appState.checkNotificationPermission()
            try? await Task.sleep(nanoseconds: 500_000_000)
            if appState.hasNotificationPermission {
                return "granted"
            } else {
                return "pending - user needs to allow notifications in the system dialog"
            }

        case "accessibility":
            appState.triggerAccessibilityPermission()
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            appState.checkAccessibilityPermission()
            try? await Task.sleep(nanoseconds: 500_000_000)
            if appState.hasAccessibilityPermission {
                return "granted"
            } else {
                return "pending - user needs to toggle Accessibility for Omi in System Settings"
            }

        case "automation":
            appState.triggerAutomationPermission()
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            appState.checkAutomationPermission()
            try? await Task.sleep(nanoseconds: 500_000_000)
            if appState.hasAutomationPermission {
                return "granted"
            } else {
                return "pending - user needs to toggle Automation for Omi in System Settings"
            }

        default:
            return "Error: unknown permission type '\(type)'. Valid types: screen_recording, microphone, notifications, accessibility, automation"
        }
    }

    /// Check status of all macOS permissions
    private static func executeCheckPermissionStatus(_ args: [String: Any]) async -> String {
        guard let appState = onboardingAppState else {
            return "Error: onboarding not active"
        }

        appState.checkAllPermissions()
        try? await Task.sleep(nanoseconds: 500_000_000)

        let statuses: [String: String] = [
            "screen_recording": appState.hasScreenRecordingPermission ? "granted" : "not_granted",
            "microphone": appState.hasMicrophonePermission ? "granted" : "not_granted",
            "notifications": appState.hasNotificationPermission ? "granted" : "not_granted",
            "accessibility": appState.hasAccessibilityPermission ? "granted" : "not_granted",
            "automation": appState.hasAutomationPermission ? "granted" : "not_granted",
        ]

        if let data = try? JSONSerialization.data(withJSONObject: statuses, options: .prettyPrinted),
           let json = String(data: data, encoding: .utf8) {
            return json
        }
        return "screen_recording: \(statuses["screen_recording"]!), microphone: \(statuses["microphone"]!), notifications: \(statuses["notifications"]!), accessibility: \(statuses["accessibility"]!), automation: \(statuses["automation"]!)"
    }

    /// Scan files BLOCKING — triggers folder access dialogs, waits for scan, returns results
    private static func executeScanFiles(_ args: [String: Any]) async -> String {
        let fm = FileManager.default
        let homeDir = fm.homeDirectoryForCurrentUser
        let foldersToScan = ["Downloads", "Documents", "Desktop", "Developer", "Projects"]
            .map { homeDir.appendingPathComponent($0) }
            .filter { fm.fileExists(atPath: $0.path) }

        let applicationsURL = URL(fileURLWithPath: "/Applications")
        var allFolders = foldersToScan
        if fm.fileExists(atPath: applicationsURL.path) {
            allFolders.append(applicationsURL)
        }

        // Pre-check folder access — this triggers macOS TCC dialogs
        var deniedFolders: [String] = []
        var accessibleFolders: [URL] = []
        for folder in allFolders {
            do {
                _ = try fm.contentsOfDirectory(
                    at: folder,
                    includingPropertiesForKeys: [.fileSizeKey],
                    options: [.skipsHiddenFiles]
                )
                accessibleFolders.append(folder)
            } catch {
                let nsError = error as NSError
                if nsError.domain == NSCocoaErrorDomain && nsError.code == 257 {
                    // Permission denied — TCC dialog was shown or already denied
                    deniedFolders.append(folder.lastPathComponent)
                } else {
                    // Other error (e.g. folder doesn't exist) — skip silently
                    log("FileIndexer: Pre-check failed for \(folder.lastPathComponent): \(error.localizedDescription)")
                }
            }
        }

        // Actually scan accessible folders (blocking)
        let count = await FileIndexerService.shared.scanFolders(accessibleFolders)
        fileScanFileCount = count
        log("Onboarding file scan completed: \(count) files indexed, \(deniedFolders.count) folders denied")

        // Build results from database
        let resultsStr = await getFileScanResultsFromDB()

        var out = resultsStr

        if !deniedFolders.isEmpty {
            out += "\n\n## FOLDER ACCESS DENIED\n"
            out += "The following folders were NOT scanned because the user didn't grant access:\n"
            for folder in deniedFolders {
                out += "- ~/\(folder)\n"
            }
            out += "\nTell the user to click 'Allow' on the macOS dialogs, then call scan_files again to pick up those folders."
        }

        return out
    }

    /// Get file scan results from the database
    private static func getFileScanResultsFromDB() async -> String {
        guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
            return "Error: database not available"
        }

        do {
            return try await dbQueue.read { db in
                // File type breakdown
                let typeBreakdown = try Row.fetchAll(db, sql: """
                    SELECT fileType, COUNT(*) as count
                    FROM indexed_files
                    GROUP BY fileType
                    ORDER BY count DESC
                    LIMIT 10
                """)

                // Project indicators
                let projectIndicators = try Row.fetchAll(db, sql: """
                    SELECT filename, path FROM indexed_files
                    WHERE filename IN ('package.json', 'Cargo.toml', 'Podfile', 'go.mod',
                        'requirements.txt', 'Pipfile', 'setup.py', 'pyproject.toml',
                        'build.gradle', 'pom.xml', 'CMakeLists.txt', 'Makefile',
                        '.xcodeproj', '.xcworkspace', 'Package.swift', 'Gemfile',
                        'composer.json', 'mix.exs', 'pubspec.yaml')
                    LIMIT 30
                """)

                // Recently modified files
                let recentFiles = try Row.fetchAll(db, sql: """
                    SELECT filename, path, fileType, modifiedAt FROM indexed_files
                    ORDER BY modifiedAt DESC
                    LIMIT 15
                """)

                // Applications
                let apps = try Row.fetchAll(db, sql: """
                    SELECT filename, path FROM indexed_files
                    WHERE folder = '/Applications' AND fileExtension = 'app'
                    ORDER BY filename
                    LIMIT 30
                """)

                let totalCount = try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM indexed_files") ?? 0

                var out = "# File Scan Results (\(totalCount) files indexed)\n\n"

                out += "## File Types\n"
                for row in typeBreakdown {
                    let type = row["fileType"] as? String ?? "unknown"
                    let count = row["count"] as? Int ?? 0
                    out += "- \(type): \(count) files\n"
                }

                out += "\n## Project Indicators (build files found)\n"
                if projectIndicators.isEmpty {
                    out += "- No project build files found\n"
                } else {
                    for row in projectIndicators {
                        let filename = row["filename"] as? String ?? ""
                        let path = row["path"] as? String ?? ""
                        // Extract project directory name
                        let dir = (path as NSString).deletingLastPathComponent
                        let projectName = (dir as NSString).lastPathComponent
                        out += "- \(projectName)/\(filename)\n"
                    }
                }

                out += "\n## Recently Modified Files\n"
                for row in recentFiles {
                    let filename = row["filename"] as? String ?? ""
                    let fileType = row["fileType"] as? String ?? ""
                    let modifiedAt = row["modifiedAt"] as? String ?? ""
                    out += "- \(filename) (\(fileType)) — modified \(modifiedAt)\n"
                }

                if !apps.isEmpty {
                    out += "\n## Installed Applications\n"
                    let appNames = apps.compactMap { ($0["filename"] as? String)?.replacingOccurrences(of: ".app", with: "") }
                    out += appNames.joined(separator: ", ")
                    out += "\n"
                }

                log("Tool get_file_scan_results: \(totalCount) files, \(projectIndicators.count) projects, \(apps.count) apps")
                return out
            }
        } catch {
            logError("Tool get_file_scan_results failed", error: error)
            return "Error: \(error.localizedDescription)"
        }
    }

    /// Set user preferences (language, name)
    private static func executeSetUserPreferences(_ args: [String: Any]) async -> String {
        var results: [String] = []

        if let language = args["language"] as? String, !language.isEmpty {
            AssistantSettings.shared.transcriptionLanguage = language
            Task {
                _ = try? await APIClient.shared.updateUserLanguage(language)
            }
            results.append("Language set to \(language)")
        }

        if let name = args["name"] as? String, !name.isEmpty {
            await AuthService.shared.updateGivenName(name)
            results.append("Name updated to \(name)")
        }

        if results.isEmpty {
            return "No preferences were changed. Provide 'language' (code like 'en', 'es', 'ja') and/or 'name' (string)."
        }
        return results.joined(separator: ". ") + "."
    }

    // MARK: - Knowledge Graph Tool

    /// Save a knowledge graph extracted by the AI during file exploration
    private static func executeSaveKnowledgeGraph(_ args: [String: Any]) async -> String {
        guard let nodesArray = args["nodes"] as? [[String: Any]] else {
            return "Error: 'nodes' array is required"
        }
        let edgesArray = args["edges"] as? [[String: Any]] ?? []

        let now = Date()
        var nodeRecords: [LocalKGNodeRecord] = []
        var edgeRecords: [LocalKGEdgeRecord] = []

        // Deduplicate nodes by label (case-insensitive)
        var seenLabels: [String: String] = [:] // lowercase label → nodeId
        var idRemap: [String: String] = [:] // original id → canonical id

        for node in nodesArray {
            guard let id = node["id"] as? String,
                  let label = node["label"] as? String else { continue }

            let nodeType = node["node_type"] as? String ?? "concept"
            let aliases = node["aliases"] as? [String] ?? []
            let lowerLabel = label.lowercased()

            if let existingId = seenLabels[lowerLabel] {
                idRemap[id] = existingId
                continue
            }

            seenLabels[lowerLabel] = id
            idRemap[id] = id

            var aliasesJson: String?
            if !aliases.isEmpty, let data = try? JSONEncoder().encode(aliases) {
                aliasesJson = String(data: data, encoding: .utf8)
            }

            nodeRecords.append(LocalKGNodeRecord(
                nodeId: id,
                label: label,
                nodeType: nodeType,
                aliasesJson: aliasesJson,
                sourceFileIds: nil,
                createdAt: now,
                updatedAt: now
            ))
        }

        for edge in edgesArray {
            guard let sourceId = edge["source_id"] as? String,
                  let targetId = edge["target_id"] as? String,
                  let label = edge["label"] as? String else { continue }

            let remappedSource = idRemap[sourceId] ?? sourceId
            let remappedTarget = idRemap[targetId] ?? targetId

            // Skip self-referencing edges and edges to missing nodes
            guard remappedSource != remappedTarget,
                  seenLabels.values.contains(remappedSource),
                  seenLabels.values.contains(remappedTarget) else { continue }

            let edgeId = "\(remappedSource)_\(remappedTarget)_\(label.lowercased().replacingOccurrences(of: " ", with: "_"))"
            edgeRecords.append(LocalKGEdgeRecord(
                edgeId: edgeId,
                sourceNodeId: remappedSource,
                targetNodeId: remappedTarget,
                label: label,
                createdAt: now
            ))
        }

        do {
            try await KnowledgeGraphStorage.shared.saveGraph(nodes: nodeRecords, edges: edgeRecords)
            log("Local graph built with \(nodeRecords.count) nodes, \(edgeRecords.count) edges")
            return "OK: saved \(nodeRecords.count) nodes and \(edgeRecords.count) edges to local knowledge graph"
        } catch {
            logError("Tool save_knowledge_graph failed", error: error)
            return "Error: \(error.localizedDescription)"
        }
    }

    /// Present a follow-up question with quick-reply options to the user
    private static func executeAskFollowup(_ args: [String: Any]) async -> String {
        guard let question = args["question"] as? String else {
            return "Error: 'question' parameter is required"
        }
        let options = (args["options"] as? [String]) ?? []

        // Notify the UI to render quick-reply buttons
        onQuickReplyOptions?(options)

        return "Presented to user: \"\(question)\" with options: \(options.joined(separator: ", "))"
    }

    /// Complete the onboarding process
    private static func executeCompleteOnboarding(_ args: [String: Any]) async -> String {
        guard let appState = onboardingAppState else {
            return "Error: onboarding not active"
        }

        // Log analytics for each permission
        let permissions: [(String, Bool)] = [
            ("screen_recording", appState.hasScreenRecordingPermission),
            ("microphone", appState.hasMicrophonePermission),
            ("notifications", appState.hasNotificationPermission),
            ("accessibility", appState.hasAccessibilityPermission),
            ("automation", appState.hasAutomationPermission),
        ]
        for (name, granted) in permissions {
            if granted {
                AnalyticsManager.shared.permissionGranted(permission: name)
            } else {
                AnalyticsManager.shared.permissionSkipped(permission: name)
            }
        }

        // Call the completion callback
        onCompleteOnboarding?()

        // Clean up state
        onboardingAppState = nil
        onCompleteOnboarding = nil
        onQuickReplyOptions = nil
        fileScanStarted = false
        fileScanFileCount = 0

        return "Onboarding completed successfully! The app is now set up."
    }
}
