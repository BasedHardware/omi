import Foundation

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
    private var previousAdvice: [ExtractedAdvice] = [] // Last 10 pieces of advice for context
    private let maxPreviousAdvice = 10
    private var currentApp: String?
    private var pendingFrame: CapturedFrame?
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
        processingTask = Task {
            await processLoop()
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
            currentActivity: currentActivity
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
                windowTitle: windowTitle
            )

            log("Advice: Synced to backend (id: \(response.id))")
            return response.id
        } catch {
            logError("Advice: Failed to sync to backend", error: error)
            return nil
        }
    }

    /// Send a notification for the advice
    private func sendAdviceNotification(advice: ExtractedAdvice) async {
        let message = advice.advice

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
            if let currentApp = currentApp {
                log("Advice: APP SWITCH: \(currentApp) -> \(newApp)")
            } else {
                log("Advice: Active app: \(newApp)")
            }
            currentApp = newApp
            // Don't clear previous advice on app switch - we want to track across apps
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

    // MARK: - Analysis

    private func processFrame(_ frame: CapturedFrame) async {
        guard await isEnabled else { return }
        do {
            guard let result = try await extractAdvice(from: frame.jpegData, appName: frame.appName) else {
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

    private func extractAdvice(from jpegData: Data, appName: String) async throws -> AdviceExtractionResult? {
        // Build context with previous advice
        var prompt = "Screenshot from \(appName). Is the user about to make a mistake or missing a non-obvious shortcut/tool for what they're doing?\n\n"

        if !previousAdvice.isEmpty {
            prompt += "PREVIOUSLY PROVIDED ADVICE (do not repeat these or semantically similar):\n"
            for (index, advice) in previousAdvice.enumerated() {
                prompt += "\(index + 1). \(advice.advice)"
                if let reasoning = advice.reasoning {
                    prompt += " (Reasoning: \(reasoning))"
                }
                prompt += "\n"
            }
            prompt += "\nOnly provide advice if there's a genuinely NEW non-obvious insight not covered above."
        } else {
            prompt += "Only provide advice if there's something specific and non-obvious that would help."
        }

        // Get current system prompt from settings
        let currentSystemPrompt = await systemPrompt

        // Build response schema for single advice extraction with conditional logic
        let adviceProperties: [String: GeminiRequest.GenerationConfig.ResponseSchema.Property] = [
            "advice": .init(type: "string", description: "The advice text (1-2 sentences, max 30 words)"),
            "reasoning": .init(type: "string", description: "Brief explanation of why this advice is relevant"),
            "category": .init(type: "string", enum: ["productivity", "communication", "learning", "other"], description: "Category of advice"),
            "source_app": .init(type: "string", description: "App where context was observed"),
            "confidence": .init(type: "number", description: "Confidence score 0.0-1.0")
        ]

        let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
            type: "object",
            properties: [
                "has_advice": .init(type: "boolean", description: "True only if there is a specific, non-obvious insight. False if nothing qualifies or would duplicate previous advice."),
                "advice": .init(
                    type: "object",
                    description: "The specific insight (only if has_advice is true)",
                    properties: adviceProperties,
                    required: ["advice", "category", "source_app", "confidence"]
                ),
                "context_summary": .init(type: "string", description: "Brief summary of what user is looking at"),
                "current_activity": .init(type: "string", description: "High-level description of user's activity")
            ],
            required: ["has_advice", "context_summary", "current_activity"]
        )

        do {
            let responseText = try await geminiClient.sendRequest(
                prompt: prompt,
                imageData: jpegData,
                systemPrompt: currentSystemPrompt,
                responseSchema: responseSchema
            )

            return try JSONDecoder().decode(AdviceExtractionResult.self, from: Data(responseText.utf8))
        } catch {
            logError("Advice analysis error", error: error)
            return nil
        }
    }
}
