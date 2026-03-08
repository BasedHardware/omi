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

    private let backendService: BackendProactiveService
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

    init(backendService: BackendProactiveService) {
        self.backendService = backendService

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

    // MARK: - Test Analysis (for test runner)

    /// Run extraction via backend for test runner. Returns (result, 0) for compatibility.
    func testAnalyze(jpegData: Data, appName: String, windowTitle: String? = nil, screenshotTime: Date) async throws -> (AdviceExtractionResult?, Int) {
        let base64 = autoreleasepool { jpegData.base64EncodedString() }
        let backendResult = try await backendService.generateAdvice(
            imageBase64: base64, appName: appName, windowTitle: windowTitle ?? ""
        )
        guard let adviceDict = backendResult.advice as? [String: Any] else {
            return (AdviceExtractionResult(hasAdvice: false, advice: nil, contextSummary: "Analyzed \(appName)", currentActivity: ""), 0)
        }
        let hasAdvice = adviceDict["has_advice"] as? Bool ?? !adviceDict.isEmpty
        guard hasAdvice, let adviceText = adviceDict["content"] as? String ?? adviceDict["advice"] as? String, !adviceText.isEmpty else {
            return (AdviceExtractionResult(hasAdvice: false, advice: nil, contextSummary: "Analyzed \(appName)", currentActivity: ""), 0)
        }
        let categoryStr = adviceDict["category"] as? String ?? "other"
        let category = AdviceCategory(rawValue: categoryStr) ?? .other
        let confidence = adviceDict["confidence"] as? Double ?? 0.5
        let advice = ExtractedAdvice(
            advice: adviceText, headline: adviceDict["headline"] as? String,
            reasoning: adviceDict["reasoning"] as? String, category: category,
            sourceApp: appName, confidence: confidence
        )
        let result = AdviceExtractionResult(hasAdvice: true, advice: advice, contextSummary: "Analyzed \(appName)", currentActivity: "")
        return (result, 0)
    }

    // MARK: - Backend Analysis (Phase 2 thin client)

    private func processFrame(_ frame: CapturedFrame) async {
        guard await isEnabled else { return }
        do {
            guard let result = try await extractAdvice(from: frame) else {
                return
            }

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
        let base64 = autoreleasepool { frame.jpegData.base64EncodedString() }
        let backendResult = try await backendService.generateAdvice(
            imageBase64: base64,
            appName: frame.appName,
            windowTitle: frame.windowTitle ?? ""
        )

        // Parse backend response into AdviceExtractionResult
        guard let adviceDict = backendResult.advice as? [String: Any] else {
            return AdviceExtractionResult(
                hasAdvice: false,
                advice: nil,
                contextSummary: "Analyzed \(frame.appName)",
                currentActivity: ""
            )
        }

        let hasAdvice = adviceDict["has_advice"] as? Bool ?? !adviceDict.isEmpty
        guard hasAdvice else {
            return AdviceExtractionResult(
                hasAdvice: false,
                advice: nil,
                contextSummary: "Analyzed \(frame.appName)",
                currentActivity: ""
            )
        }

        let adviceText = adviceDict["content"] as? String ?? adviceDict["advice"] as? String ?? ""
        guard !adviceText.isEmpty else {
            return AdviceExtractionResult(
                hasAdvice: false,
                advice: nil,
                contextSummary: "Analyzed \(frame.appName)",
                currentActivity: ""
            )
        }

        let categoryStr = adviceDict["category"] as? String ?? "other"
        let category = AdviceCategory(rawValue: categoryStr) ?? .other
        let confidence: Double
        if let confValue = adviceDict["confidence"] as? Double {
            confidence = confValue
        } else if let confInt = adviceDict["confidence"] as? Int {
            confidence = Double(confInt)
        } else {
            confidence = 0.5
        }

        let advice = ExtractedAdvice(
            advice: adviceText,
            headline: adviceDict["headline"] as? String,
            reasoning: adviceDict["reasoning"] as? String,
            category: category,
            sourceApp: frame.appName,
            confidence: confidence
        )

        return AdviceExtractionResult(
            hasAdvice: true,
            advice: advice,
            contextSummary: adviceDict["context_summary"] as? String ?? "Analyzed \(frame.appName)",
            currentActivity: adviceDict["current_activity"] as? String ?? ""
        )
    }
}
