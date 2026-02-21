import Foundation

/// Memory extraction assistant that identifies facts and wisdom from screen content
actor MemoryAssistant: ProactiveAssistant {
    // MARK: - ProactiveAssistant Protocol

    nonisolated let identifier = "memory-extraction"
    nonisolated let displayName = "Memory Extractor"

    var isEnabled: Bool {
        get async {
            await MainActor.run {
                MemoryAssistantSettings.shared.isEnabled
            }
        }
    }

    // MARK: - Properties

    private let geminiClient: GeminiClient
    private var isRunning = false
    private var lastAnalysisTime: Date = .distantPast
    private var previousMemories: [ExtractedMemory] = [] // Last 20 extracted memories for deduplication
    private let maxPreviousMemories = 20
    private var currentApp: String?
    private var pendingFrame: CapturedFrame?
    private var processingTask: Task<Void, Never>?
    private let frameSignal: AsyncStream<Void>
    private let frameSignalContinuation: AsyncStream<Void>.Continuation

    /// Get the current system prompt from settings (accessed on MainActor for thread safety)
    private var systemPrompt: String {
        get async {
            await MainActor.run {
                MemoryAssistantSettings.shared.analysisPrompt
            }
        }
    }

    /// Get the extraction interval from settings
    private var extractionInterval: TimeInterval {
        get async {
            await MainActor.run {
                MemoryAssistantSettings.shared.extractionInterval
            }
        }
    }

    /// Get the minimum confidence threshold from settings
    private var minConfidence: Double {
        get async {
            await MainActor.run {
                MemoryAssistantSettings.shared.minConfidence
            }
        }
    }

    // MARK: - Initialization

    init(apiKey: String? = nil) throws {
        // Use Gemini 3 Pro for better memory extraction quality
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
        processingTask = Task {
            await processLoop()
        }
    }

    private func processLoop() async {
        log("Memory assistant started")

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
            let waited = Date().timeIntervalSince(lastAnalysisTime)
            log("Memory: Starting analysis (interval: \(Int(interval))s, waited: \(Int(waited))s)")
            pendingFrame = nil
            lastAnalysisTime = Date()
            await processFrame(frame)
        }

        log("Memory assistant stopped")
    }

    // MARK: - ProactiveAssistant Protocol Methods

    func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool {
        // Memory assistant analyzes less frequently - every N seconds
        // The actual interval is checked in the processing loop
        // Here we just accept frames to store the latest one
        return true
    }

    func analyze(frame: CapturedFrame) async -> AssistantResult? {
        // Skip apps excluded from memory extraction (built-in + user's custom list)
        let excluded = await MainActor.run { MemoryAssistantSettings.shared.isAppExcluded(frame.appName) }
        if excluded {
            log("Memory: Skipping excluded app '\(frame.appName)'")
            return nil
        }

        // Store the latest frame - we'll process it when the interval has passed
        let hadPending = pendingFrame != nil
        pendingFrame = frame
        if !hadPending {
            log("Memory: Received frame from \(frame.appName), queued for analysis")
        }
        // Signal the processing loop that a frame is available
        frameSignalContinuation.yield()
        return nil
    }

    func handleResult(_ result: AssistantResult, sendEvent: @escaping (String, [String: Any]) -> Void) async {
        // This method is required by protocol but we use handleResultWithScreenshot instead
        guard let memoryResult = result as? MemoryExtractionResult else { return }
        await handleResultWithScreenshot(memoryResult, screenshotId: nil, sendEvent: sendEvent)
    }

    /// Handle result with screenshot ID for SQLite storage
    private func handleResultWithScreenshot(
        _ memoryResult: MemoryExtractionResult,
        screenshotId: Int64?,
        windowTitle: String? = nil,
        sendEvent: @escaping (String, [String: Any]) -> Void
    ) async {
        // Check if AI found new memories
        guard memoryResult.hasNewMemory, !memoryResult.memories.isEmpty else {
            return
        }

        // Get min confidence threshold
        let threshold = await minConfidence

        // Only process the first memory (max 1 per analysis)
        guard let memory = memoryResult.memories.first else { return }

        let confidencePercent = Int(memory.confidence * 100)

        // Check confidence threshold
        guard memory.confidence >= threshold else {
            log("Memory: [\(confidencePercent)% < \(Int(threshold * 100))%] Filtered: \"\(memory.content)\"")
            return
        }

        log("Memory: [\(confidencePercent)% conf.] [\(memory.category.rawValue)] \"\(memory.content)\"")

        // Add to previous memories (keep last 20 for deduplication context)
        previousMemories.insert(memory, at: 0)
        if previousMemories.count > maxPreviousMemories {
            previousMemories.removeLast()
        }

        // Save to SQLite first
        let extractionRecord = await saveMemoryToSQLite(
            memory: memory,
            screenshotId: screenshotId,
            contextSummary: memoryResult.contextSummary,
            windowTitle: windowTitle
        )

        // Sync to backend with full extraction data
        if let backendId = await syncMemoryToBackend(memory: memory, contextSummary: memoryResult.contextSummary, windowTitle: windowTitle) {
            // Update SQLite record with backend ID
            if let recordId = extractionRecord?.id {
                do {
                    try await MemoryStorage.shared.markSynced(id: recordId, backendId: backendId)
                } catch {
                    logError("Memory: Failed to update sync status", error: error)
                }
            }
        }

        // Track memory extracted
        await MainActor.run {
            AnalyticsManager.shared.memoryExtracted(memoryCount: 1)
        }

        // Send notification if enabled
        let notificationsEnabled = await MainActor.run {
            MemoryAssistantSettings.shared.notificationsEnabled
        }
        if notificationsEnabled {
            await sendMemoryNotification(memory: memory)
        }

        // Send event to Flutter
        sendEvent("memoryExtracted", [
            "assistant": identifier,
            "memory": memory.toDictionary(),
            "contextSummary": memoryResult.contextSummary
        ])
    }

    /// Save extracted memory to SQLite using MemoryStorage
    private func saveMemoryToSQLite(
        memory: ExtractedMemory,
        screenshotId: Int64?,
        contextSummary: String,
        windowTitle: String? = nil
    ) async -> MemoryRecord? {
        // Convert ExtractedMemory category to MemoryCategory string
        let category = memory.category == .interesting ? "interesting" : "system"

        let record = MemoryRecord(
            backendSynced: false,
            content: memory.content,
            category: category,
            source: "desktop",
            screenshotId: screenshotId,
            confidence: memory.confidence,
            sourceApp: memory.sourceApp,
            windowTitle: windowTitle,
            contextSummary: contextSummary
        )

        do {
            let inserted = try await MemoryStorage.shared.insertLocalMemory(record)
            log("Memory: Saved to SQLite (id: \(inserted.id ?? -1))")
            return inserted
        } catch {
            logError("Memory: Failed to save to SQLite", error: error)
            return nil
        }
    }

    /// Sync memory to backend API, returns backend ID if successful
    private func syncMemoryToBackend(memory: ExtractedMemory, contextSummary: String? = nil, windowTitle: String? = nil) async -> String? {
        do {
            // Convert ExtractedMemory category to MemoryCategory
            let category: MemoryCategory = memory.category == .interesting ? .interesting : .system

            let response = try await APIClient.shared.createMemory(
                content: memory.content,
                visibility: "private",
                category: category,
                confidence: memory.confidence,
                sourceApp: memory.sourceApp,
                contextSummary: contextSummary,
                windowTitle: windowTitle
            )

            log("Memory: Synced to backend (id: \(response.id))")
            return response.id
        } catch {
            logError("Memory: Failed to sync to backend", error: error)
            return nil
        }
    }

    /// Send a notification for the extracted memory
    private func sendMemoryNotification(memory: ExtractedMemory) async {
        let title = memory.category == .interesting ? "Wisdom Captured" : "Memory Saved"
        let message = memory.content

        await MainActor.run {
            NotificationService.shared.sendNotification(
                title: title,
                message: message,
                assistantId: identifier
            )
        }
    }

    func onAppSwitch(newApp: String) async {
        if newApp != currentApp {
            if let currentApp = currentApp {
                log("Memory: APP SWITCH: \(currentApp) -> \(newApp)")
            } else {
                log("Memory: Active app: \(newApp)")
            }
            currentApp = newApp
            // Don't clear previous memories on app switch - we want to track across apps
        }
    }

    func clearPendingWork() async {
        pendingFrame = nil
        log("Memory: Cleared pending frame")
    }

    func stop() async {
        isRunning = false
        frameSignalContinuation.finish()
        processingTask?.cancel()
        pendingFrame = nil
    }

    // MARK: - Analysis

    private func processFrame(_ frame: CapturedFrame) async {
        let enabled = await isEnabled
        guard enabled else {
            log("Memory: Skipping analysis (disabled)")
            return
        }

        log("Memory: Analyzing frame from \(frame.appName)...")
        do {
            guard let result = try await extractMemories(from: frame.jpegData, appName: frame.appName) else {
                log("Memory: Analysis returned no result")
                return
            }

            log("Memory: Analysis complete - hasNewMemory: \(result.hasNewMemory), count: \(result.memories.count), context: \(result.contextSummary)")

            // Handle the result with screenshot ID for SQLite storage
            await handleResultWithScreenshot(result, screenshotId: frame.screenshotId, windowTitle: frame.windowTitle) { type, data in
                Task { @MainActor in
                    AssistantCoordinator.shared.sendEvent(type: type, data: data)
                }
            }
        } catch {
            logError("Memory extraction error", error: error)
        }
    }

    private func extractMemories(from jpegData: Data, appName: String) async throws -> MemoryExtractionResult? {
        // Build context with previous memories for deduplication
        var prompt = "Analyze this screenshot from \(appName).\n\n"

        if !previousMemories.isEmpty {
            prompt += "RECENTLY EXTRACTED MEMORIES (do not re-extract these or semantically similar ones):\n"
            for (index, memory) in previousMemories.enumerated() {
                prompt += "\(index + 1). [\(memory.category.rawValue)] \(memory.content)\n"
            }
            prompt += "\nLook for NEW memories that are NOT already in the list above."
        } else {
            prompt += "Look for memories to extract (system facts about the user, or interesting wisdom from others)."
        }

        // Get current system prompt from settings
        let currentSystemPrompt = await systemPrompt

        // Build response schema for memory extraction
        let memoryProperties: [String: GeminiRequest.GenerationConfig.ResponseSchema.Property] = [
            "content": .init(type: "string", description: "The memory content (max 15 words)"),
            "category": .init(type: "string", enum: ["system", "interesting"], description: "Memory category"),
            "source_app": .init(type: "string", description: "App where memory was found"),
            "confidence": .init(type: "number", description: "Confidence score 0.0-1.0")
        ]

        let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
            type: "object",
            properties: [
                "has_new_memory": .init(type: "boolean", description: "True if new memories were found"),
                "memories": .init(
                    type: "array",
                    description: "Array of extracted memories (0-3 max)",
                    items: .init(
                        type: "object",
                        properties: memoryProperties,
                        required: ["content", "category", "source_app", "confidence"]
                    )
                ),
                "context_summary": .init(type: "string", description: "Brief summary of what user is looking at"),
                "current_activity": .init(type: "string", description: "High-level description of user's activity")
            ],
            required: ["has_new_memory", "memories", "context_summary", "current_activity"]
        )

        do {
            let responseText = try await geminiClient.sendRequest(
                prompt: prompt,
                imageData: jpegData,
                systemPrompt: currentSystemPrompt,
                responseSchema: responseSchema
            )

            return try JSONDecoder().decode(MemoryExtractionResult.self, from: Data(responseText.utf8))
        } catch {
            logError("Memory analysis error", error: error)
            return nil
        }
    }
}
