import AppKit
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
        // Use Gemini 3.1 Pro for better advice quality (3-pro-preview retires March 9, 2026)
        self.geminiClient = try GeminiClient(apiKey: apiKey, model: "gemini-pro-latest")

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
    /// `screenshotTime` anchors the activity summary to the screenshot's actual timestamp.
    /// Returns (result, sqlQueryCount) where sqlQueryCount is the number of execute_sql tool calls made.
    func testAnalyze(jpegData: Data, appName: String, windowTitle: String? = nil, screenshotTime: Date) async throws -> (AdviceExtractionResult?, Int) {
        let interval = await extractionInterval
        let lookbackStart = screenshotTime.addingTimeInterval(-interval)
        return try await runAdviceExtraction(
            jpegData: nil,
            appName: appName,
            windowTitle: windowTitle,
            referenceTime: screenshotTime,
            lookbackStart: lookbackStart,
            trackSqlCount: true
        )
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

    // MARK: - Image Processing

    /// Resize and compress an image for Gemini analysis (max 1280px wide, JPEG quality 0.4)
    private static func compressForGemini(_ data: Data) -> Data? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else { return nil }

        let maxWidth = 1280
        let width = cgImage.width
        let height = cgImage.height
        let scale = width > maxWidth ? Double(maxWidth) / Double(width) : 1.0
        let newWidth = Int(Double(width) * scale)
        let newHeight = Int(Double(height) * scale)

        guard let context = CGContext(
            data: nil, width: newWidth, height: newHeight,
            bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return nil }

        context.interpolationQuality = .high
        context.draw(cgImage, in: CGRect(x: 0, y: 0, width: newWidth, height: newHeight))

        guard let resized = context.makeImage() else { return nil }

        let mutableData = NSMutableData()
        guard let dest = CGImageDestinationCreateWithData(mutableData as CFMutableData, "public.jpeg" as CFString, 1, nil) else { return nil }
        CGImageDestinationAddImage(dest, resized, [kCGImageDestinationLossyCompressionQuality: 0.4] as CFDictionary)
        guard CGImageDestinationFinalize(dest) else { return nil }
        return mutableData as Data
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
        let now = Date()
        // Cap lookback: since last analysis or max 1 hour ago
        let lookbackStart = max(lastAnalysisTime, now.addingTimeInterval(-3600))
        let (result, _) = try await runAdviceExtraction(
            jpegData: nil,
            appName: frame.appName,
            windowTitle: frame.windowTitle,
            referenceTime: now,
            lookbackStart: lookbackStart,
            trackSqlCount: false
        )
        return result
    }

    // MARK: - Core Extraction (shared by production + test)

    /// Two-phase advice extraction:
    /// Phase 1 (text-only): Activity summary + SQL investigation loop. Model investigates via
    ///   execute_sql, then calls `request_screenshot` with an ID and its findings so far.
    /// Phase 2 (single vision call): Load the chosen screenshot + Phase 1 findings → single
    ///   Gemini call with image → provide_advice or no_advice.
    /// Returns (result, sqlQueryCount).
    private func runAdviceExtraction(
        jpegData: Data?,
        appName: String,
        windowTitle: String?,
        referenceTime: Date,
        lookbackStart: Date,
        trackSqlCount: Bool
    ) async throws -> (AdviceExtractionResult?, Int) {
        var sqlCount = 0

        // Build prompt with current context
        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "h:mm a, EEEE"
        var prompt = "CURRENT APP: \(appName)."
        if let windowTitle = windowTitle, !windowTitle.isEmpty {
            prompt += " Window: \"\(windowTitle)\"."
        }
        prompt += " Time: \(timeFormatter.string(from: referenceTime))."

        // Add activity summary from database, anchored to the reference time
        let elapsed = referenceTime.timeIntervalSince(lookbackStart)
        log("Advice: Activity lookback: \(String(format: "%.0f", elapsed))s (\(lookbackStart) to \(referenceTime))")
        let activitySummary = await buildActivitySummary(from: lookbackStart, to: referenceTime)
        if !activitySummary.isEmpty {
            prompt += "\n\n" + activitySummary
            log("Advice: --- ACTIVITY SUMMARY ---\n\(activitySummary)")
        } else {
            log("Advice: --- ACTIVITY SUMMARY --- (empty, no screenshots in range)")
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

        prompt += "\n\nInvestigate the activity summary. Focus on apps with the HIGHEST screenshot count (that's where the user actually spent time). Use execute_sql to read OCR text from the user's primary activity — ignore sidebar previews and low-count apps. When you've identified the most interesting screenshot, call request_screenshot with the ID and your findings. Or call no_advice if nothing qualifies."

        log("Advice: --- PROMPT ---\n\(prompt)")

        // Build system prompt
        var currentSystemPrompt = await systemPrompt
        if let language = await getUserLanguage(), language != "en" {
            currentSystemPrompt += "\n\nIMPORTANT: Respond in the user's preferred language: \(language)"
        }
        currentSystemPrompt += "\n\nDATABASE SCHEMA for execute_sql:\nscreenshots table columns: id INTEGER, timestamp TEXT, appName TEXT, windowTitle TEXT, ocrText TEXT, focusStatus TEXT"

        // =============================================
        // PHASE 1: Text-only investigation loop
        // =============================================

        let phase1Tools = buildPhase1Tools()
        var contents: [GeminiImageToolRequest.Content] = [
            GeminiImageToolRequest.Content(
                role: "user",
                parts: [GeminiImageToolRequest.Part(text: prompt)]
            )
        ]

        let client = self.geminiClient
        var chosenScreenshotId: Int64?
        var investigationFindings: String?

        for iteration in 0..<7 {
            let iterContents = contents
            let iterSystemPrompt = currentSystemPrompt
            let iterTools = [phase1Tools]
            let iterForce = iteration == 0
            let result: ToolChatResult
            do {
                result = try await withThrowingTimeout(seconds: 120) {
                    try await client.sendImageToolLoop(
                        contents: iterContents,
                        systemPrompt: iterSystemPrompt,
                        tools: iterTools,
                        forceToolCall: iterForce
                    )
                }
            } catch {
                log("Advice: Phase 1 failed on iteration \(iteration): \(error.localizedDescription)")
                throw error
            }

            guard let toolCall = result.toolCalls.first else {
                log("Advice: Phase 1 — no tool call on iteration \(iteration), breaking")
                break
            }

            switch toolCall.name {
            case "execute_sql":
                let query = toolCall.arguments["query"] as? String ?? ""
                sqlCount += 1
                log("Advice: P1 execute_sql iter \(iteration): \(query)")
                let sqlToolCall = ToolCall(name: "execute_sql", arguments: ["query": query], thoughtSignature: nil)
                let resultStr = await ChatToolExecutor.execute(sqlToolCall)
                let truncated = resultStr.count > 2000 ? String(resultStr.prefix(2000)) + "... (truncated)" : resultStr
                log("Advice: P1 sql result (\(resultStr.count) chars): \(truncated)")

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

            case "request_screenshot":
                let findings = toolCall.arguments["findings"] as? String ?? ""
                investigationFindings = findings
                if let idInt = toolCall.arguments["screenshot_id"] as? Int {
                    chosenScreenshotId = Int64(idInt)
                } else if let idInt64 = toolCall.arguments["screenshot_id"] as? Int64 {
                    chosenScreenshotId = idInt64
                } else if let idStr = toolCall.arguments["screenshot_id"] as? String, let parsed = Int64(idStr) {
                    chosenScreenshotId = parsed
                } else if let idDouble = toolCall.arguments["screenshot_id"] as? Double {
                    chosenScreenshotId = Int64(idDouble)
                }
                log("Advice: P1 request_screenshot iter \(iteration): id=\(chosenScreenshotId ?? 0), findings=\(findings.prefix(200))")
                break // Exit phase 1

            case "no_advice":
                let contextSummary = toolCall.arguments["context_summary"] as? String ?? "No context"
                let currentActivity = toolCall.arguments["current_activity"] as? String ?? "Unknown"
                log("Advice: P1 no_advice — \(contextSummary)")
                return (AdviceExtractionResult(
                    hasAdvice: false,
                    advice: nil,
                    contextSummary: contextSummary,
                    currentActivity: currentActivity
                ), sqlCount)

            default:
                log("Advice: P1 unknown tool: \(toolCall.name), breaking")
                break
            }

            // Break out of loop if request_screenshot was called
            if chosenScreenshotId != nil { break }
        }

        // If Phase 1 exhausted without choosing a screenshot, no advice
        guard let screenshotId = chosenScreenshotId, let findings = investigationFindings else {
            log("Advice: Phase 1 exhausted without request_screenshot")
            return (nil, sqlCount)
        }

        // =============================================
        // PHASE 2: Single vision call with chosen screenshot
        // =============================================

        log("Advice: Phase 2 — loading screenshot \(screenshotId)")

        // Load the screenshot image
        let imageData: Data
        do {
            guard let screenshot = try await RewindDatabase.shared.getScreenshot(id: screenshotId) else {
                log("Advice: P2 screenshot not in DB: \(screenshotId)")
                return (nil, sqlCount)
            }
            // Check active chunk
            if screenshot.usesVideoStorage, let chunk = screenshot.videoChunkPath {
                let activeChunk = await VideoChunkEncoder.shared.currentChunkPath
                if chunk == activeChunk {
                    log("Advice: P2 screenshot is in active chunk, skipping")
                    return (nil, sqlCount)
                }
            }
            let rawData = try await RewindStorage.shared.loadScreenshotData(for: screenshot)
            imageData = Self.compressForGemini(rawData) ?? rawData
            log("Advice: P2 loaded \(imageData.count) bytes (\(rawData.count) raw) from \(screenshot.appName)")
        } catch {
            log("Advice: P2 screenshot load failed: \(error.localizedDescription)")
            return (nil, sqlCount)
        }

        // Build Phase 2 prompt — compact findings + image
        let phase2Prompt = """
            INVESTIGATION FINDINGS:
            \(findings)

            The screenshot below is from the app/window identified during investigation. Based on your findings AND what you see in the screenshot, call provide_advice if there's a specific non-obvious insight, or no_advice if nothing qualifies.
            """

        let phase2Tools = buildPhase2Tools()
        let base64 = imageData.base64EncodedString()
        let phase2Contents: [GeminiImageToolRequest.Content] = [
            GeminiImageToolRequest.Content(
                role: "user",
                parts: [
                    GeminiImageToolRequest.Part(text: phase2Prompt),
                    GeminiImageToolRequest.Part(mimeType: "image/jpeg", data: base64),
                ]
            )
        ]

        // Single Gemini call with image
        let phase2Result: ToolChatResult
        do {
            let p2Contents = phase2Contents
            let p2SystemPrompt = currentSystemPrompt
            let p2Tools = [phase2Tools]
            phase2Result = try await withThrowingTimeout(seconds: 120) {
                try await client.sendImageToolLoop(
                    contents: p2Contents,
                    systemPrompt: p2SystemPrompt,
                    tools: p2Tools,
                    forceToolCall: true
                )
            }
        } catch {
            log("Advice: Phase 2 Gemini call failed: \(error.localizedDescription)")
            throw error
        }

        guard let toolCall = phase2Result.toolCalls.first else {
            log("Advice: Phase 2 — no tool call returned")
            return (nil, sqlCount)
        }

        switch toolCall.name {
        case "provide_advice":
            log("Advice: P2 provide_advice")
            return (parseProvideAdvice(toolCall), sqlCount)
        case "no_advice":
            let contextSummary = toolCall.arguments["context_summary"] as? String ?? "No context"
            let currentActivity = toolCall.arguments["current_activity"] as? String ?? "Unknown"
            log("Advice: P2 no_advice — \(contextSummary)")
            return (AdviceExtractionResult(
                hasAdvice: false,
                advice: nil,
                contextSummary: contextSummary,
                currentActivity: currentActivity
            ), sqlCount)
        default:
            log("Advice: P2 unexpected tool: \(toolCall.name)")
            return (nil, sqlCount)
        }
    }

    // MARK: - Activity Summary

    /// Query the screenshots table to build a summary of recent activity.
    /// - `from`: lower bound (e.g. last analysis time or screenshot.timestamp - interval)
    /// - `to`: upper bound (e.g. now or the screenshot's timestamp)
    private func buildActivitySummary(from lookbackStart: Date, to referenceTime: Date) async -> String {
        guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
            return ""
        }

        do {
            return try await dbQueue.read { db in
                // Pass Date objects directly — GRDB encodes them as UTC strings
                // matching the stored format. Manual DateFormatter uses local timezone
                // which causes mismatches.
                let rows = try Row.fetchAll(db, sql: """
                    SELECT appName, windowTitle, COUNT(*) as count,
                           MIN(timestamp) as first_seen, MAX(timestamp) as last_seen
                    FROM screenshots
                    WHERE timestamp >= ? AND timestamp <= ?
                      AND appName IS NOT NULL AND appName != ''
                    GROUP BY appName, windowTitle
                    ORDER BY count DESC
                    LIMIT 30
                    """, arguments: [lookbackStart, referenceTime])

                if rows.isEmpty {
                    return ""
                }

                let totalScreenshots = rows.reduce(0) { $0 + (($1["count"] as? Int64).map(Int.init) ?? ($1["count"] as? Int) ?? 0) }
                let elapsedMin = referenceTime.timeIntervalSince(lookbackStart) / 60.0

                let timeOnlyFormatter = DateFormatter()
                timeOnlyFormatter.dateFormat = "HH:mm:ss"

                var lines: [String] = []
                lines.append("ACTIVITY SUMMARY (last \(Int(elapsedMin)) min, \(totalScreenshots) screenshots):")
                lines.append("Time range: \(timeOnlyFormatter.string(from: lookbackStart)) – \(timeOnlyFormatter.string(from: referenceTime))")
                lines.append("")
                lines.append("App | Window | Screenshots | Est. Duration")
                lines.append(String(repeating: "-", count: 60))

                for row in rows {
                    let app = row["appName"] as? String ?? "Unknown"
                    let window = row["windowTitle"] as? String ?? ""
                    let count = (row["count"] as? Int64).map(Int.init) ?? (row["count"] as? Int) ?? 0
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

    /// Phase 1 tools: text-only investigation (execute_sql, request_screenshot, no_advice)
    private func buildPhase1Tools() -> GeminiTool {
        GeminiTool(functionDeclarations: [
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
            GeminiTool.FunctionDeclaration(
                name: "request_screenshot",
                description: "Request to view a specific screenshot. Call this when you've found something interesting via SQL and want to see the actual screen. Provide the screenshot ID and a summary of your findings so far. The screenshot will be shown to you for final analysis.",
                parameters: GeminiTool.FunctionDeclaration.Parameters(
                    type: "object",
                    properties: [
                        "screenshot_id": .init(type: "integer", description: "The screenshot ID from the screenshots table"),
                        "findings": .init(type: "string", description: "Summary of what you found during investigation — what app, what OCR text caught your attention, and what you suspect might be worth advising about")
                    ],
                    required: ["screenshot_id", "findings"]
                )
            ),
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

    /// Phase 2 tools: vision call with screenshot (provide_advice, no_advice)
    private func buildPhase2Tools() -> GeminiTool {
        GeminiTool(functionDeclarations: [
            GeminiTool.FunctionDeclaration(
                name: "provide_advice",
                description: "Call this when you have a specific, non-obvious insight for the user based on the screenshot and your investigation findings.",
                parameters: GeminiTool.FunctionDeclaration.Parameters(
                    type: "object",
                    properties: [
                        "advice": .init(type: "string", description: "The advice text (1-2 sentences, max 100 chars). Start with what you noticed, then why it matters."),
                        "headline": .init(type: "string", description: "Ultra-short observation (max 5 words) for notification preview. E.g. 'Draft saved in /tmp', 'Credentials visible in terminal'"),
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
            GeminiTool.FunctionDeclaration(
                name: "no_advice",
                description: "Call this when the screenshot doesn't reveal anything worth advising about. Nothing qualifies as a specific, non-obvious insight.",
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

        log("Advice: --- PROVIDE_ADVICE ---")
        log("Advice:   advice: \(adviceText)")
        log("Advice:   headline: \(headline ?? "(none)")")
        log("Advice:   reasoning: \(reasoning ?? "(none)")")
        log("Advice:   category: \(categoryStr)")
        log("Advice:   source_app: \(sourceApp)")
        log("Advice:   confidence: \(confidence)")
        log("Advice:   context: \(contextSummary)")
        log("Advice:   activity: \(currentActivity)")
        return AdviceExtractionResult(
            hasAdvice: true,
            advice: advice,
            contextSummary: contextSummary,
            currentActivity: currentActivity
        )
    }
}

// MARK: - Timeout Helper

/// Run an async operation with a timeout. Throws `CancellationError` if the timeout expires.
private func withThrowingTimeout<T: Sendable>(seconds: Double, operation: @escaping @Sendable () async throws -> T) async throws -> T {
    try await withThrowingTaskGroup(of: T.self) { group in
        group.addTask {
            try await operation()
        }
        group.addTask {
            try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            throw CancellationError()
        }
        // First task to complete wins; cancel the other
        let result = try await group.next()!
        group.cancelAll()
        return result
    }
}
