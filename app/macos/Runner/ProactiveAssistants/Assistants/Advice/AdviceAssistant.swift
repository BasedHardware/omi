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
        self.geminiClient = try GeminiClient(apiKey: apiKey)

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

        while isRunning {
            // Check if we have a pending frame and enough time has passed
            if let frame = pendingFrame {
                let interval = await extractionInterval
                let timeSinceLastAnalysis = Date().timeIntervalSince(lastAnalysisTime)

                if timeSinceLastAnalysis >= interval {
                    pendingFrame = nil
                    lastAnalysisTime = Date()
                    await processFrame(frame)
                }
            }

            try? await Task.sleep(nanoseconds: 500_000_000) // Check every 0.5 seconds
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
        // Store the latest frame - we'll process it when the interval has passed
        pendingFrame = frame
        // Note: This overwrites the previous frame, not a queue
        return nil
    }

    func handleResult(_ result: AssistantResult, sendEvent: @escaping (String, [String: Any]) -> Void) async {
        guard let adviceResult = result as? AdviceExtractionResult else { return }

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

        // Send notification
        await sendAdviceNotification(advice: advice)

        // Send event to Flutter
        sendEvent("adviceProvided", [
            "assistant": identifier,
            "advice": advice.toDictionary(),
            "contextSummary": adviceResult.contextSummary
        ])
    }

    /// Send a notification for the advice
    private func sendAdviceNotification(advice: ExtractedAdvice) async {
        let message = advice.advice

        // Use cooldown to prevent notification spam with frequent analysis
        await MainActor.run {
            NotificationService.shared.sendNotification(
                title: "",
                message: message,
                assistantId: identifier,
                applyCooldown: true
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
        processingTask?.cancel()
        pendingFrame = nil
    }

    // MARK: - Analysis

    private func processFrame(_ frame: CapturedFrame) async {
        do {
            guard let result = try await extractAdvice(from: frame.jpegData, appName: frame.appName) else {
                return
            }

            // Handle the result
            await handleResult(result) { type, data in
                Task { @MainActor in
                    AssistantCoordinator.shared.sendEvent(type: type, data: data)
                }
            }
        } catch {
            log("Advice extraction error: \(error)")
        }
    }

    private func extractAdvice(from jpegData: Data, appName: String) async throws -> AdviceExtractionResult? {
        // Build context with previous advice
        var prompt = "Analyze this screenshot from \(appName).\n\n"

        if !previousAdvice.isEmpty {
            prompt += "PREVIOUSLY PROVIDED ADVICE (do not repeat these or semantically similar advice):\n"
            for (index, advice) in previousAdvice.enumerated() {
                prompt += "\(index + 1). \(advice.advice)"
                if let reasoning = advice.reasoning {
                    prompt += " (Reasoning: \(reasoning))"
                }
                prompt += "\n"
            }
            prompt += "\nProvide ONE NEW piece of advice that is NOT similar to the above. Use an appropriate confidence score (0.0-1.0) based on how relevant/useful the advice is. Only set has_advice=false if the advice would be a duplicate."
        } else {
            prompt += "Provide ONE piece of contextual advice based on what you see. Use an appropriate confidence score (0.0-1.0) based on how relevant/useful the advice is."
        }

        // Get current system prompt from settings
        let currentSystemPrompt = await systemPrompt

        // Build response schema for single advice extraction with conditional logic
        let adviceProperties: [String: GeminiRequest.GenerationConfig.ResponseSchema.Property] = [
            "advice": .init(type: "string", description: "The advice text (1-2 sentences, max 30 words)"),
            "reasoning": .init(type: "string", description: "Brief explanation of why this advice is relevant"),
            "category": .init(type: "string", enum: ["productivity", "health", "communication", "learning", "other"], description: "Category of advice"),
            "source_app": .init(type: "string", description: "App where context was observed"),
            "confidence": .init(type: "number", description: "Confidence score 0.0-1.0")
        ]

        let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
            type: "object",
            properties: [
                "has_advice": .init(type: "boolean", description: "Almost always true. Only false if advice would duplicate previous advice."),
                "advice": .init(
                    type: "object",
                    description: "The advice with calibrated confidence score (0.0-1.0)",
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
            log("Advice analysis error: \(error)")
            return nil
        }
    }
}
