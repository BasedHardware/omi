import Foundation
import GRDB

/// Proactive advice assistant that provides contextual suggestions based on screen content
actor AdviceAssistant: ProactiveAssistant {
    // MARK: - ProactiveAssistant Protocol

    nonisolated let identifier = "advice"
    nonisolated let displayName = "Proactive Advisor"

    var isEnabled: Bool {
        get async {
            await MainActor.run {
                AdviceAssistantSettings.shared.isEnabled
            }
        }
    }

    // MARK: - Properties

    private let geminiClient: GeminiClient
    private var isRunning = false
    private var lastAnalysisTime: Date = .distantPast
    private var previousAdvice: [ExtractedAdvice] = [] // Dedup window for advice context
    private let maxPreviousAdvice = 50
    private let maxAdviceInPrompt = 30 // Only include first 30 in prompt to keep token count reasonable
    private var currentApp: String?
    private var pendingFrame: CapturedFrame?
    private var cachedLanguage: String?
    private var languageFetchedAt: Date = .distantPast
    private var processingTask: Task<Void, Never>?
    private let frameSignal: AsyncStream<Void>
    private let frameSignalContinuation: AsyncStream<Void>.Continuation

    /// Get the current system prompt from settings (accessed on MainActor for thread safety)
    private var systemPrompt: String {
        get async {
            await MainActor.run {
                AdviceAssistantSettings.shared.analysisPrompt
            }
        }
    }

    /// Get the extraction interval from settings
    private var extractionInterval: TimeInterval {
        get async {
            await MainActor.run {
                AdviceAssistantSettings.shared.extractionInterval
            }
        }
    }

    /// Get the minimum confidence threshold from settings
    private var minConfidence: Double {
        get async {
            await MainActor.run {
                AdviceAssistantSettings.shared.minConfidence
            }
        }
    }

    // MARK: - Initialization

    init(apiKey: String? = nil) throws {
        // Use Gemini 3 Pro for better advice quality
        self.geminiClient = try GeminiClient(apiKey: apiKey, model: "gemini-3-pro-preview")

        let (stream, continuation) = AsyncStream.makeStream(of: Void.self, bufferingPolicy: .bufferingNewest(1))
        self.frameSignal = stream
        self.frameSignalContinuation = continuation

        // Start processing loop
        Task {
            await self.startProcessing()
        }
    }

    // MARK: - Processing

    private func startProcessing() {
        isRunning = true
        Task {
            await loadPreviousAdviceFromDB()
        }
        processingTask = Task {
            await processLoop()
        }
    }

    /// Load previous advice from SQLite to persist dedup across app restarts
    private func loadPreviousAdviceFromDB() async {
        do {
            let memories = try await MemoryStorage.shared.getLocalMemories(
                limit: maxPreviousAdvice,
                category: "system",
                tags: ["tips"]
            )
            for memory in memories {
                let advice = ExtractedAdvice(
                    advice: memory.content,
                    headline: nil,
                    reasoning: nil,
                    category: .other,
                    sourceApp: memory.sourceApp ?? "",
                    confidence: 0.0
                )
                previousAdvice.append(advice)
            }
            if !previousAdvice.isEmpty {
                log("Advice: Loaded \(previousAdvice.count) previous tips from DB for dedup")
            }
        } catch {
            logError("Advice: Failed to load previous tips from DB", error: error)
        }
    }

    private func processLoop() async {
        log("Advice assistant started")

        for await _ in frameSignal {
            guard isRunning else { break }
            guard pendingFrame != nil else { continue }

            // Wait until the extraction interval has passed
            let interval = await extractionInterval
            let timeSinceLastAnalysis = Date().timeIntervalSince(lastAnalysisTime)
            if timeSinceLastAnalysis < interval {
                let remaining = interval - timeSinceLastAnalysis
                try? await Task.sleep(nanoseconds: UInt64(remaining * 1_000_000_000))
            }

            // Grab the latest frame (may have been updated or cleared during sleep)
            guard let frame = pendingFrame else { continue }
            pendingFrame = nil
            lastAnalysisTime = Date()
            await processFrame(frame)
        }

        log("Advice assistant stopped")
    }

    // MARK: - Test Analysis (for test runner)

    /// Run the extraction pipeline on arbitrary JPEG data without side effects (no saving, no events).
    /// Used by the test runner to replay past screenshots.
    /// Returns (result, sqlQueryCount) where sqlQueryCount is the number of execute_sql tool calls made.
    func testAnalyze(jpegData: Data, appName: String, windowTitle: String? = nil) async throws -> (AdviceExtractionResult?, Int) {
        let frame = CapturedFrame(
            jpegData: jpegData,
            appName: appName,
            windowTitle: windowTitle,
            frameNumber: 0
        )
        var sqlCount = 0
        let result = try await extractAdviceForTest(from: frame, sqlQueryCount: &sqlCount)
        return (result, sqlCount)
    }

    /// Variant of extractAdvice that tracks SQL query count for test reporting.
    private func extractAdviceForTest(from frame: CapturedFrame, sqlQueryCount: inout Int) async throws -> AdviceExtractionResult? {
        let appName = frame.appName

        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "h:mm a, EEEE"
        var prompt = "LATEST SCREENSHOT from \(appName)."
        if let windowTitle = frame.windowTitle, !windowTitle.isEmpty {
            prompt += " Window: \"\(windowTitle)\"."
        }
        prompt += " Time: \(timeFormatter.string(from: Date()))."

        let activitySummary = await buildActivitySummary()
        if !activitySummary.isEmpty {
            prompt += "\n\n" + activitySummary
        }

        if let profile = await AIUserProfileService.shared.getLatestProfile() {
            prompt += "\n\nUSER PROFILE (who this user is):\n"
            prompt += profile.profileText + "\n"
        }

        if !previousAdvice.isEmpty {
            prompt += "\n\nPREVIOUSLY PROVIDED ADVICE (do not repeat these or semantically similar):\n"
            let adviceToInclude = previousAdvice.prefix(maxAdviceInPrompt)
            for (index, advice) in adviceToInclude.enumerated() {
                prompt += "\(index + 1). \(advice.advice)"
                if let reasoning = advice.reasoning {
                    prompt += " (Reasoning: \(reasoning))"
                }
                prompt += "\n"
            }
            prompt += "\nOnly provide advice if there's a genuinely NEW non-obvious insight not covered above."
        } else {
            prompt += "\n\nOnly provide advice if there's something specific and non-obvious that would help."
        }

        prompt += "\n\nAnalyze the activity summary and screenshot. Use execute_sql to investigate OCR text from interesting windows if needed. Then call provide_advice or no_advice."

        var currentSystemPrompt = await systemPrompt
        if let language = await getUserLanguage(), language != "en" {
            currentSystemPrompt += "\n\nIMPORTANT: Respond in the user's preferred language: \(language)"
        }
        currentSystemPrompt += "\n\nDATABASE SCHEMA for execute_sql:\nscreenshots table columns: id INTEGER, timestamp TEXT, appName TEXT, windowTitle TEXT, ocrText TEXT, focusStatus TEXT"

        let tools = buildAdviceTools()

        let base64Data = frame.jpegData.base64EncodedString()
        var contents: [GeminiImageToolRequest.Content] = [
            GeminiImageToolRequest.Content(
                role: "user",
                parts: [
                    GeminiImageToolRequest.Part(text: prompt),
                    GeminiImageToolRequest.Part(mimeType: "image/jpeg", data: base64Data),
                ]
            )
        ]

        for iteration in 0..<5 {
            let result = try await geminiClient.sendImageToolLoop(
                contents: contents,
                systemPrompt: currentSystemPrompt,
                tools: [tools],
                forceToolCall: iteration == 0
            )

            guard let toolCall = result.toolCalls.first else { break }

            switch toolCall.name {
            case "provide_advice":
                return parseProvideAdvice(toolCall)
            case "no_advice":
                let contextSummary = toolCall.arguments["context_summary"] as? String ?? "No context"
                let currentActivity = toolCall.arguments["current_activity"] as? String ?? "Unknown"
                return AdviceExtractionResult(hasAdvice: false, advice: nil, contextSummary: contextSummary, currentActivity: currentActivity)
            case "execute_sql":
                let query = toolCall.arguments["query"] as? String ?? ""
                sqlQueryCount += 1
                let sqlToolCall = ToolCall(name: "execute_sql", arguments: ["query": query], thoughtSignature: nil)
                let resultStr = await ChatToolExecutor.execute(sqlToolCall)
                contents.append(GeminiImageToolRequest.Content(
                    role: "model",
                    parts: [GeminiImageToolRequest.Part(
                        functionCall: .init(name: toolCall.name, args: ["query": query]),
                        thoughtSignature: toolCall.thoughtSignature
                    )]
                ))
                contents.append(GeminiImageToolRequest.Content(
                    role: "user",
                    parts: [GeminiImageToolRequest.Part(functionResponse: .init(
                        name: toolCall.name,
                        response: .init(result: resultStr)
                    ))]
                ))
                continue
            default:
                break
            }
        }

        return nil
    }

    // MARK: - ProactiveAssistant Protocol Methods

    func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool {
        // Advice assistant analyzes less frequently - every N seconds
        // The actual interval is checked in the processing loop
        // Here we just accept frames to store the latest one
        return true
    }

    func analyze(frame: CapturedFrame) async -> AssistantResult? {
        // Skip apps excluded from advice extraction (built-in + user's custom list)
        let excluded = await MainActor.run { AdviceAssistantSettings.shared.isAppExcluded(frame.appName) }
        if excluded {
            log("Advice: Skipping excluded app '\(frame.appName)'")
            return nil
        }

        // Store the latest frame - we'll process it when the interval has passed
        pendingFrame = frame
        // Signal the processing loop that a frame is available
        frameSignalContinuation.yield()
        return nil
    }

    func handleResult(_ result: AssistantResult, sendEvent: @escaping (String, [String: Any]) -> Void) async {
        // This method is required by protocol but we use handleResultWithScreenshot instead
        guard let adviceResult = result as? AdviceExtractionResult else { return }
        await handleResultWithScreenshot(adviceResult, screenshotId: nil, sendEvent: sendEvent)
    }

    /// Handle result with screenshot ID for SQLite storage
    private func handleResultWithScreenshot(
        _ adviceResult: AdviceExtractionResult,
        screenshotId: Int64?,
        windowTitle: String? = nil,
        sendEvent: @escaping (String, [String: Any]) -> Void
    ) async {
        // Check if AI has new advice (should almost always be true now - only false for duplicates)
        guard adviceResult.hasAdvice, let advice = adviceResult.advice else {
            log("Advice: Skipped (duplicate or no context)")
            return
        }

        // Get min confidence threshold
        let threshold = await minConfidence
        let confidencePercent = Int(advice.confidence * 100)

        // Check confidence threshold
        guard advice.confidence >= threshold else {
            log("Advice: [\(confidencePercent)% < \(Int(threshold * 100))%] Filtered: \"\(advice.advice)\"")
            return
        }

        log("Advice: [\(confidencePercent)% conf.] \"\(advice.advice)\"")

        // Add to previous advice (keep last 10 for context)
        previousAdvice.insert(advice, at: 0)
        if previousAdvice.count > maxPreviousAdvice {
            previousAdvice.removeLast()
        }

        // Save to SQLite first
        let extractionRecord = await saveAdviceToSQLite(
            advice: advice,
            screenshotId: screenshotId,
            contextSummary: adviceResult.contextSummary,
            currentActivity: adviceResult.currentActivity,
            windowTitle: windowTitle
        )

        // Sync to backend and update local record with backendId
        if let backendId = await syncAdviceToBackend(advice: advice, adviceResult: adviceResult, windowTitle: windowTitle) {
            if let recordId = extractionRecord?.id {
                do {
                    try await MemoryStorage.shared.markSynced(id: recordId, backendId: backendId)
                } catch {
                    logError("Advice: Failed to update sync status", error: error)
                }
            }
        }

        // Also update AdviceStorage cache (for UI display)
        await MainActor.run {
            AdviceStorage.shared.addAdvice(adviceResult)
        }

        // Track advice generated
        await MainActor.run {
            AnalyticsManager.shared.adviceGenerated(category: advice.category.rawValue)
        }

        // Send notification if enabled
        let notificationsEnabled = await MainActor.run {
            AdviceAssistantSettings.shared.notificationsEnabled
        }
        if notificationsEnabled {
            await sendAdviceNotification(advice: advice)
        }

        // Send event to Flutter
        sendEvent("adviceProvided", [
            "assistant": identifier,
            "advice": advice.toDictionary(),
            "contextSummary": adviceResult.contextSummary
        ])
    }

    /// Save advice to SQLite using MemoryStorage with tips tags
    private func saveAdviceToSQLite(
        advice: ExtractedAdvice,
        screenshotId: Int64?,
        contextSummary: String,
        currentActivity: String,
        windowTitle: String? = nil
    ) async -> MemoryRecord? {
        // Build tags: ["tips", "<category>"]
        let categoryTag = advice.category.rawValue.lowercased()
        let tags = ["tips", categoryTag]

        // Encode tags as JSON
        let tagsJson: String?
        if let data = try? JSONEncoder().encode(tags),
           let json = String(data: data, encoding: .utf8) {
            tagsJson = json
        } else {
            tagsJson = nil
        }

        let record = MemoryRecord(
            backendSynced: false,
            content: advice.advice,
            category: "system",  // Tips are stored as system category with tags
            tagsJson: tagsJson,
            source: "screenshot",
            screenshotId: screenshotId,
            confidence: advice.confidence,
            reasoning: advice.reasoning,
            sourceApp: advice.sourceApp,
            windowTitle: windowTitle,
            contextSummary: contextSummary,
            currentActivity: currentActivity,
            headline: advice.headline
        )

        do {
            let inserted = try await MemoryStorage.shared.insertLocalMemory(record)
            log("Advice: Saved to SQLite (id: \(inserted.id ?? -1)) with tags \(tags)")
            return inserted
        } catch {
            logError("Advice: Failed to save to SQLite", error: error)
            return nil
        }
    }

    /// Sync advice to backend API, returns backend ID if successful
    private func syncAdviceToBackend(advice: ExtractedAdvice, adviceResult: AdviceExtractionResult, windowTitle: String? = nil) async -> String? {
        do {
            // Build tags: ["tips", "<category>"]
            let categoryTag = advice.category.rawValue.lowercased()
            let tags = ["tips", categoryTag]

            let response = try await APIClient.shared.createMemory(
                content: advice.advice,
                visibility: "private",
                category: .system,
                confidence: advice.confidence,
                sourceApp: advice.sourceApp,
                contextSummary: adviceResult.contextSummary,
                tags: tags,
                reasoning: advice.reasoning,
                currentActivity: adviceResult.currentActivity,
                source: "screenshot",
                windowTitle: windowTitle,
                headline: advice.headline
            )

            log("Advice: Synced to backend (id: \(response.id))")
            return response.id
        } catch {
            logError("Advice: Failed to sync to backend", error: error)
            return nil
        }
    }

    /// Send a notification for the advice (uses short headline for notification body)
    private func sendAdviceNotification(advice: ExtractedAdvice) async {
        let message = advice.headline ?? advice.advice

        await MainActor.run {
            NotificationService.shared.sendNotification(
                title: "Tip",
                message: message,
                assistantId: identifier
            )
        }
    }

    func onAppSwitch(newApp: String) async {
        if newApp != currentApp {
            if let previousApp = currentApp {
                log("Advice: APP SWITCH: \(previousApp) -> \(newApp)")
            } else {
                log("Advice: Active app: \(newApp)")
            }
            currentApp = newApp
        }
    }

    func clearPendingWork() async {
        pendingFrame = nil
        log("Advice: Cleared pending frame")
    }

    func stop() async {
        isRunning = false
        frameSignalContinuation.finish()
        processingTask?.cancel()
        pendingFrame = nil
    }

    // MARK: - Helpers

    /// Get user's preferred language, cached for 1 hour
    private func getUserLanguage() async -> String? {
        // Return cached value if fresh (< 1 hour)
        if let cached = cachedLanguage, Date().timeIntervalSince(languageFetchedAt) < 3600 {
            return cached
        }

        do {
            let response = try await APIClient.shared.getUserLanguage()
            let lang = response.language
            cachedLanguage = lang
            languageFetchedAt = Date()
            return lang.isEmpty ? nil : lang
        } catch {
            // Fall back to transcription language setting
            let fallback = await MainActor.run { AssistantSettings.shared.transcriptionLanguage }
            return fallback.isEmpty || fallback == "en" ? nil : fallback
        }
    }

    // MARK: - Analysis

    private func processFrame(_ frame: CapturedFrame) async {
        guard await isEnabled else { return }
        do {
            guard let result = try await extractAdvice(from: frame) else {
                return
            }

            // Handle the result with screenshot ID for SQLite storage
            await handleResultWithScreenshot(result, screenshotId: frame.screenshotId, windowTitle: frame.windowTitle) { type, data in
                Task { @MainActor in
                    AssistantCoordinator.shared.sendEvent(type: type, data: data)
                }
            }
        } catch {
            logError("Advice extraction error", error: error)
        }
    }

    private func extractAdvice(from frame: CapturedFrame) async throws -> AdviceExtractionResult? {
        let appName = frame.appName

        // Build prompt with screenshot context
        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "h:mm a, EEEE"
        var prompt = "LATEST SCREENSHOT from \(appName)."
        if let windowTitle = frame.windowTitle, !windowTitle.isEmpty {
            prompt += " Window: \"\(windowTitle)\"."
        }
        prompt += " Time: \(timeFormatter.string(from: Date()))."

        // Add activity summary from database
        let activitySummary = await buildActivitySummary()
        if !activitySummary.isEmpty {
            prompt += "\n\n" + activitySummary
        }

        // Add user profile for context
        if let profile = await AIUserProfileService.shared.getLatestProfile() {
            prompt += "\n\nUSER PROFILE (who this user is):\n"
            prompt += profile.profileText + "\n"
        }

        // Add previous advice for dedup
        if !previousAdvice.isEmpty {
            prompt += "\n\nPREVIOUSLY PROVIDED ADVICE (do not repeat these or semantically similar):\n"
            let adviceToInclude = previousAdvice.prefix(maxAdviceInPrompt)
            for (index, advice) in adviceToInclude.enumerated() {
                prompt += "\(index + 1). \(advice.advice)"
                if let reasoning = advice.reasoning {
                    prompt += " (Reasoning: \(reasoning))"
                }
                prompt += "\n"
            }
            prompt += "\nOnly provide advice if there's a genuinely NEW non-obvious insight not covered above."
        } else {
            prompt += "\n\nOnly provide advice if there's something specific and non-obvious that would help."
        }

        prompt += "\n\nAnalyze the activity summary and screenshot. Use execute_sql to investigate OCR text from interesting windows if needed. Then call provide_advice or no_advice."

        // Build system prompt
        var currentSystemPrompt = await systemPrompt
        if let language = await getUserLanguage(), language != "en" {
            currentSystemPrompt += "\n\nIMPORTANT: Respond in the user's preferred language: \(language)"
        }
        currentSystemPrompt += "\n\nDATABASE SCHEMA for execute_sql:\nscreenshots table columns: id INTEGER, timestamp TEXT, appName TEXT, windowTitle TEXT, ocrText TEXT, focusStatus TEXT"

        // Build tool definitions
        let tools = buildAdviceTools()

        // Build initial contents with image
        let base64Data = frame.jpegData.base64EncodedString()
        var contents: [GeminiImageToolRequest.Content] = [
            GeminiImageToolRequest.Content(
                role: "user",
                parts: [
                    GeminiImageToolRequest.Part(text: prompt),
                    GeminiImageToolRequest.Part(mimeType: "image/jpeg", data: base64Data),
                ]
            )
        ]

        // Agentic loop (max 5 iterations)
        for iteration in 0..<5 {
            let result = try await geminiClient.sendImageToolLoop(
                contents: contents,
                systemPrompt: currentSystemPrompt,
                tools: [tools],
                forceToolCall: iteration == 0
            )

            guard let toolCall = result.toolCalls.first else {
                log("Advice: No tool call on iteration \(iteration), breaking")
                break
            }

            switch toolCall.name {
            case "provide_advice":
                log("Advice: provide_advice on iteration \(iteration)")
                return parseProvideAdvice(toolCall)

            case "no_advice":
                let contextSummary = toolCall.arguments["context_summary"] as? String ?? "No context"
                let currentActivity = toolCall.arguments["current_activity"] as? String ?? "Unknown"
                log("Advice: no_advice — \(contextSummary)")
                return AdviceExtractionResult(
                    hasAdvice: false,
                    advice: nil,
                    contextSummary: contextSummary,
                    currentActivity: currentActivity
                )

            case "execute_sql":
                let query = toolCall.arguments["query"] as? String ?? ""
                log("Advice: execute_sql iteration \(iteration): \(query)")
                let sqlToolCall = ToolCall(name: "execute_sql", arguments: ["query": query], thoughtSignature: nil)
                let resultStr = await ChatToolExecutor.execute(sqlToolCall)

                // Append model's tool call + function response
                contents.append(GeminiImageToolRequest.Content(
                    role: "model",
                    parts: [GeminiImageToolRequest.Part(
                        functionCall: .init(name: toolCall.name, args: ["query": query]),
                        thoughtSignature: toolCall.thoughtSignature
                    )]
                ))
                contents.append(GeminiImageToolRequest.Content(
                    role: "user",
                    parts: [GeminiImageToolRequest.Part(functionResponse: .init(
                        name: toolCall.name,
                        response: .init(result: resultStr)
                    ))]
                ))
                continue

            default:
                log("Advice: Unknown tool call: \(toolCall.name), breaking")
                break
            }
        }

        log("Advice: Loop exhausted without terminal tool")
        return nil
    }

    // MARK: - Activity Summary

    /// Query the screenshots table to build a summary of recent activity
    private func buildActivitySummary() async -> String {
        guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
            return ""
        }

        let now = Date()
        // Cap lookback: since last analysis or max 1 hour ago
        let lookbackStart = max(lastAnalysisTime, now.addingTimeInterval(-3600))

        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        let startStr = dateFormatter.string(from: lookbackStart)
        let endStr = dateFormatter.string(from: now)

        do {
            return try await dbQueue.read { db in
                let rows = try Row.fetchAll(db, sql: """
                    SELECT appName, windowTitle, COUNT(*) as count,
                           MIN(timestamp) as first_seen, MAX(timestamp) as last_seen
                    FROM screenshots
                    WHERE timestamp >= ? AND timestamp <= ?
                      AND appName IS NOT NULL AND appName != ''
                    GROUP BY appName, windowTitle
                    ORDER BY count DESC
                    LIMIT 30
                    """, arguments: [startStr, endStr])

                if rows.isEmpty {
                    return ""
                }

                let totalScreenshots = rows.reduce(0) { $0 + (($1["count"] as? Int) ?? 0) }
                let elapsedMin = now.timeIntervalSince(lookbackStart) / 60.0

                let timeOnlyFormatter = DateFormatter()
                timeOnlyFormatter.dateFormat = "HH:mm:ss"

                var lines: [String] = []
                lines.append("ACTIVITY SUMMARY (last \(Int(elapsedMin)) min, \(totalScreenshots) screenshots):")
                lines.append("Time range: \(timeOnlyFormatter.string(from: lookbackStart)) – \(timeOnlyFormatter.string(from: now))")
                lines.append("")
                lines.append("App | Window | Screenshots | Est. Duration")
                lines.append(String(repeating: "-", count: 60))

                for row in rows {
                    let app = row["appName"] as? String ?? "Unknown"
                    let window = row["windowTitle"] as? String ?? ""
                    let count = row["count"] as? Int ?? 0
                    let estMinutes = String(format: "%.1f", Double(count) / 60.0)
                    let windowDisplay = window.isEmpty ? "(no title)" : String(window.prefix(50))
                    lines.append("\(app) | \(windowDisplay) | \(count) | \(estMinutes) min")
                }

                let summary = lines.joined(separator: "\n")
                log("Advice: Activity summary (last \(Int(elapsedMin)) min, \(totalScreenshots) screenshots)")
                return summary
            }
        } catch {
            logError("Advice: Failed to build activity summary", error: error)
            return ""
        }
    }

    // MARK: - Tool Definitions

    /// Build the 3 advice tools: execute_sql, provide_advice, no_advice
    private func buildAdviceTools() -> GeminiTool {
        GeminiTool(functionDeclarations: [
            // execute_sql — investigation tool
            GeminiTool.FunctionDeclaration(
                name: "execute_sql",
                description: "Execute a SQL query on the local database to investigate screen activity. The screenshots table has: id INTEGER, timestamp TEXT, appName TEXT, windowTitle TEXT, ocrText TEXT, focusStatus TEXT. Use this to read OCR text from interesting windows, check what the user was doing, etc. SELECT queries only. Auto-limited to 200 rows.",
                parameters: GeminiTool.FunctionDeclaration.Parameters(
                    type: "object",
                    properties: [
                        "query": .init(type: "string", description: "SQL SELECT query to execute on the screenshots table")
                    ],
                    required: ["query"]
                )
            ),
            // provide_advice — terminal tool (produces advice)
            GeminiTool.FunctionDeclaration(
                name: "provide_advice",
                description: "Call this when you have a specific, non-obvious insight for the user. This ends the analysis.",
                parameters: GeminiTool.FunctionDeclaration.Parameters(
                    type: "object",
                    properties: [
                        "advice": .init(type: "string", description: "The advice text (1-2 sentences, max 100 chars). Start with the actionable part."),
                        "headline": .init(type: "string", description: "Ultra-short summary (max 5 words) for notification preview. E.g. 'Wrong year in calendar', 'Credentials visible in terminal'"),
                        "reasoning": .init(type: "string", description: "Brief explanation of why this advice is relevant"),
                        "category": .init(type: "string", description: "Category of advice", enumValues: ["productivity", "communication", "learning", "other"]),
                        "source_app": .init(type: "string", description: "App where context was observed"),
                        "confidence": .init(type: "number", description: "Confidence score 0.0-1.0. 0.90+: preventing clear mistake. 0.75-0.89: highly relevant non-obvious tip. 0.60-0.74: useful but user might know."),
                        "context_summary": .init(type: "string", description: "Brief summary of what user is looking at"),
                        "current_activity": .init(type: "string", description: "High-level description of user's activity")
                    ],
                    required: ["advice", "headline", "category", "source_app", "confidence", "context_summary", "current_activity"]
                )
            ),
            // no_advice — terminal tool (nothing worth mentioning)
            GeminiTool.FunctionDeclaration(
                name: "no_advice",
                description: "Call this when there is nothing worth advising about. Nothing qualifies as a specific, non-obvious insight. This ends the analysis.",
                parameters: GeminiTool.FunctionDeclaration.Parameters(
                    type: "object",
                    properties: [
                        "context_summary": .init(type: "string", description: "Brief summary of what user is looking at"),
                        "current_activity": .init(type: "string", description: "High-level description of user's activity")
                    ],
                    required: ["context_summary", "current_activity"]
                )
            ),
        ])
    }

    // MARK: - Parse Tool Results

    /// Parse the provide_advice tool call into an AdviceExtractionResult
    private func parseProvideAdvice(_ toolCall: ToolCall) -> AdviceExtractionResult {
        let adviceText = toolCall.arguments["advice"] as? String ?? ""
        let headline = toolCall.arguments["headline"] as? String
        let reasoning = toolCall.arguments["reasoning"] as? String
        let categoryStr = toolCall.arguments["category"] as? String ?? "other"
        let category = AdviceCategory(rawValue: categoryStr) ?? .other
        let sourceApp = toolCall.arguments["source_app"] as? String ?? ""
        let contextSummary = toolCall.arguments["context_summary"] as? String ?? ""
        let currentActivity = toolCall.arguments["current_activity"] as? String ?? ""

        let confidence: Double
        if let confValue = toolCall.arguments["confidence"] as? Double {
            confidence = confValue
        } else if let confInt = toolCall.arguments["confidence"] as? Int {
            confidence = Double(confInt)
        } else if let confStr = toolCall.arguments["confidence"] as? String, let parsed = Double(confStr) {
            confidence = parsed
        } else {
            confidence = 0.5
        }

        let advice = ExtractedAdvice(
            advice: adviceText,
            headline: headline,
            reasoning: reasoning,
            category: category,
            sourceApp: sourceApp,
            confidence: confidence
        )

        log("Advice: provide_advice — \"\(adviceText)\" (confidence: \(confidence))")
        return AdviceExtractionResult(
            hasAdvice: true,
            advice: advice,
            contextSummary: contextSummary,
            currentActivity: currentActivity
        )
    }
}
